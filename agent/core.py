"""
Agent 主循环 — 意图识别 → 参数提取 → 追问/执行 → 回复。

设计原则（Karpathy 风格）：
- Session 是普通 dict，不搞状态机枚举
- 每个请求最多 2 次 LLM 调用（意图 + 提取参数）
- 工具执行在独立线程中，发完即返回
"""
import json
import time
import threading
import logging
from datetime import date as dt_date

from agent.llm_client import chat
from agent.prompts import (
    INTENT_PROMPT,
    EXTRACT_REELCLEAN_PROMPT,
    EXTRACT_PREDICTION_PROMPT,
    EXTRACT_FEISHU_EXCEL_PROMPT,
)
from tools.base import ToolResult
from tools.reelclean_tool import ReelCleanTool
from tools.prediction_tool import PredictionTool
from tools.feishu_excel_tool import FeishuExcelTool
from config import SESSION_TIMEOUT

log = logging.getLogger(__name__)

# 工具注册表 — 加新工具只需加一行
TOOLS = {
    "reelclean": ReelCleanTool(),
    "prediction": PredictionTool(),
    "feishu_excel": FeishuExcelTool(),
}

EXTRACT_PROMPTS = {
    "reelclean": EXTRACT_REELCLEAN_PROMPT,
    "prediction": EXTRACT_PREDICTION_PROMPT,
    "feishu_excel": EXTRACT_FEISHU_EXCEL_PROMPT,
}


class AgentSession:
    """单个用户的对话状态。纯数据对象，不包含逻辑。"""
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.intent: str | None = None
        self.params: dict = {}
        self.files: list = []  # [(filename, bytes), ...]
        self.last_active: float = time.time()

    def is_expired(self) -> bool:
        return time.time() - self.last_active > SESSION_TIMEOUT

    def touch(self):
        self.last_active = time.time()


class DataAnalysisAgent:
    """飞书数据处理 Agent。"""

    def __init__(self):
        self._sessions: dict[str, AgentSession] = {}
        self._lock = threading.Lock()

    # ── 公开接口 ──

    def handle_message(
        self, user_id: str, chat_id: str, text: str, files: list | None = None
    ) -> dict:
        """
        处理一条用户消息。返回 {'text': str, 'files': list[str], 'done': bool}

        done=True 表示最终回复，之后清理 session。
        done=False 表示追问，等待用户补充。
        """
        session = self._get_or_create_session(user_id)
        if files:
            session.files.extend(files)
        session.touch()
        self._cleanup_expired()

        # Step 1: 意图识别
        if session.intent is None:
            return self._classify_intent(session, text)

        # Step 2: 参数提取
        if self._has_missing_params(session):
            return self._extract_params(session, text)

        # Step 3: 参数齐全 → 执行
        return self._execute_tool(session)

    # ── 内部步骤 ──

    def _classify_intent(self, session: AgentSession, text: str) -> dict:
        """LLM 判断用户想用什么工具。"""
        try:
            prompt = INTENT_PROMPT.format(user_message=text)
            raw = chat("返回纯 JSON，不要 markdown 包裹。", prompt)
            result = json.loads(raw)
        except Exception as e:
            log.warning(f"意图识别失败: {e}，退化为 unknown")
            result = {"intent": "unknown", "confidence": 0}

        intent = result.get("intent", "unknown")
        confidence = result.get("confidence", 0)

        # 不认识的意图
        if intent not in TOOLS and intent != "multi_step":
            intent = "unknown"
            confidence = 0

        # 置信度低 → 追问
        if confidence < 0.7 or intent == "unknown":
            return {
                "text": (
                    "我还不太确定您想要做什么，可以再描述一下吗？\n\n"
                    "我能帮你做这些事：\n"
                    "1️⃣ **数据清洗** — 发送3个Excel文件 + 参数（总成本/后台消耗/上一时段/D8百分比）\n"
                    "2️⃣ **落位预测** — 告诉我日期、影片占比和大盘场次\n"
                    "3️⃣ **开场数据提取** — 发送Excel文件链接，帮你生成汇报文案"
                ),
                "files": [],
                "done": False,
            }

        session.intent = intent

        # 确认意图
        tool = TOOLS[intent]
        return {
            "text": f"✅ 已识别为【{tool.description.split('——')[0]}】\n请继续提供参数，或者直接告诉我所有信息。",
            "files": [],
            "done": False,
        }

    def _extract_params(self, session: AgentSession, text: str) -> dict:
        """LLM 从自然语言中提取参数。"""
        prompt_template = EXTRACT_PROMPTS.get(session.intent)
        if not prompt_template:
            return self._fallback_error("内部错误：未知意图。")

        try:
            # 注入当天日期用于解析相对日期
            today = dt_date.today().strftime("%Y-%m-%d")
            prompt = prompt_template.format(user_message=text, today=today)
            raw = chat("返回纯 JSON，不要 markdown 包裹。", prompt)
            extract = json.loads(raw)
        except Exception as e:
            log.warning(f"参数提取失败: {e}")
            return {
                "text": "抱歉，参数解析出错了，请尝试用更简单的格式重新输入（如：总成本300000，后台消耗32.8...）",
                "files": [],
                "done": False,
            }

        params = extract.get("params", {})
        missing = extract.get("missing", [])

        # 检查用户是否提到了文件
        tool = TOOLS[session.intent]
        if session.intent == "reelclean" and not session.files:
            if "files" not in missing:
                missing.append("files")

        # 更新 session
        for key, value in params.items():
            if value is not None and key not in session.params:
                session.params[key] = value

        # 补上文件
        if session.files and "files" not in session.params:
            session.params["files"] = session.files

        # 重新计算缺失
        actual_missing = tool.validate_params(session.params)

        if actual_missing:
            tool_name = tool.description.split("——")[0]
            hints = self._missing_params_hint(session.intent, actual_missing)
            return {
                "text": f"📋 【{tool_name}】还需要以下信息：\n{hints}",
                "files": [],
                "done": False,
            }

        # 参数齐全 → 确认并执行
        try:
            confirm = tool.format_params_for_display(session.params)
        except Exception:
            confirm = json.dumps(session.params, ensure_ascii=False, indent=2)

        # 直接执行，不再确认（省一步交互）
        return self._execute_tool(session)

    def _execute_tool(self, session: AgentSession) -> dict:
        """调用工具，格式化结果。"""
        tool = TOOLS[session.intent]

        # 在后台线程执行（有些工具耗时较长，如猫眼爬虫）
        result_holder = {"result": None}
        error_holder = {"error": None}

        def run():
            try:
                result_holder["result"] = tool.execute(session.params)
            except Exception as e:
                error_holder["error"] = str(e)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout=60)  # 最多等 60 秒

        if error_holder["error"]:
            self._clear_session(session.user_id)
            return {"text": f"❌ {error_holder['error']}", "files": [], "done": True}

        if result_holder["result"] is None:
            self._clear_session(session.user_id)
            return {"text": "⏰ 处理超时，请稍后重试。", "files": [], "done": True}

        result: ToolResult = result_holder["result"]

        # 清理 session
        self._clear_session(session.user_id)

        if not result.success:
            return {"text": f"❌ {result.error}", "files": [], "done": True}

        return {
            "text": result.text,
            "files": result.files,
            "done": True,
        }

    # ── 辅助方法 ──

    def _has_missing_params(self, session: AgentSession) -> bool:
        if session.intent not in TOOLS:
            return True
        tool = TOOLS[session.intent]
        return len(tool.validate_params(session.params)) > 0

    def _get_or_create_session(self, user_id: str) -> AgentSession:
        with self._lock:
            session = self._sessions.get(user_id)
            if session is None or session.is_expired():
                session = AgentSession(user_id)
                self._sessions[user_id] = session
            return session

    def _clear_session(self, user_id: str):
        with self._lock:
            self._sessions.pop(user_id, None)

    def _cleanup_expired(self):
        with self._lock:
            expired = [
                uid for uid, s in self._sessions.items() if s.is_expired()
            ]
            for uid in expired:
                del self._sessions[uid]

    def _missing_params_hint(self, intent: str, missing: list[str]) -> str:
        """为缺失参数生成友好的提示。"""
        hints = {
            "total_cost": "• **总成本** — 如 300000 或 30万",
            "backend_consume": "• **后台消耗** — 如 32.8 或 32.8%",
            "prev_actual": "• **上一时段实际消耗** — 如 83.4 或 83.4%",
            "d8_pct": "• **D8百分比** — 如 4.4 或 4.4%",
            "files": "• **Excel文件** — 请在群聊中发送3个Excel文件",
            "date": "• **预测日期** — 如 6.15 或 明天",
            "movies": "• **影片占比列表** — 如 封神2:17.6%, 哪吒:8.2%",
            "dapan_total": "• **大盘场次** — 如 42万 或 420000",
            "urls": "• **Excel文件链接** — 请发送文件链接",
        }
        return "\n".join(hints.get(m, f"• {m}") for m in missing)

    def _fallback_error(self, msg: str) -> dict:
        return {"text": f"❌ {msg}", "files": [], "done": True}
