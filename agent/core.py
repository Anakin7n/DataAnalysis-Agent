"""
Agent 主循环 — 意图识别 → 参数提取 → 追问/执行 → 回复。

设计原则（Karpathy 风格）：
- Session 是普通 dict，不搞状态机枚举
- 每个请求最多 2 次 LLM 调用（意图 + 提取参数）
- 工具执行在独立子进程中，超时可 terminate
"""
import json
import logging
import multiprocessing
import re
import threading
import time
from datetime import date as dt_date

from agent.llm_client import chat, chat_json
from agent.prompts import (
    INTENT_PROMPT,
    EXTRACT_REELCLEAN_PROMPT,
    EXTRACT_PREDICTION_PROMPT,
    EXTRACT_FEISHU_EXCEL_PROMPT,
    safe_format,
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


def _run_tool(intent: str, params: dict, result_queue: multiprocessing.Queue):
    """在子进程中执行工具。模块级函数——Windows multiprocessing (spawn) 要求。"""
    try:
        tool = TOOLS[intent]
        result = tool.execute(params)
        result_queue.put(("ok", result))
    except Exception as e:
        result_queue.put(("error", str(e)))

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
        self._gen: int = 0  # 消息版本号：并发消息只保留最新

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
        session._gen += 1
        my_gen = session._gen
        if files:
            session.files.extend(files)
        session.touch()
        self._cleanup_expired()

        def _ok(resp: dict) -> dict:
            """如果处理期间有新消息到达，当前结果已过时，静默丢弃。"""
            if session._gen != my_gen:
                return {"text": "", "files": [], "done": False}
            return resp

        # 纯文件消息（无文本）— 静默累积，不调 LLM，但需给用户反馈
        if not text and files:
            if session.intent is not None:
                session.params["files"] = session.files
                tool = TOOLS[session.intent]
                try:
                    session.params = tool.resolve_params(session.params)
                except Exception:
                    pass
                tool_name = tool.description.split("——")[0]
                missing = tool.validate_params(session.params)
                if missing:
                    received = self._format_received(session)
                    hints = self._missing_params_hint(session.intent, missing, session)
                    parts = [f"📎 已收到文件【{tool_name}】"]
                    if received:
                        parts.append(f"\n📎 已收到：\n{received}")
                    parts.append(f"\n📋 仍需提供：\n{hints}")
                    return _ok({"text": "\n".join(parts), "files": [], "done": False})
                else:
                    received = self._format_received(session)
                    parts = [f"✅ 收到文件，参数已齐全【{tool_name}】"]
                    if received:
                        parts.append(f"\n📎 已收到：\n{received}")
                    parts.append("\n⏳ 正在处理...")
                    return _ok({"text": "\n".join(parts), "files": [], "done": False, "_deferred": True})
            return _ok({"text": "", "files": [], "done": False})

        # 意图切换检测：当前已有意图时，判断用户是否想换工具
        if session.intent is not None:
            new_intent, confidence = self._detect_intent(text)
            if confidence >= 0.7 and new_intent not in (session.intent, "unknown", "multi_step"):
                old_name = TOOLS[session.intent].description.split("——")[0]
                new_name = TOOLS[new_intent].description.split("——")[0]
                log.info(f"[意图切换] {old_name} → {new_name}")
                # 重置 session 状态
                session.intent = None
                session.params = {}
                session.files = []
                # 重新分类
                return _ok(self._classify_intent(session, text))

        # Step 1: 意图识别
        if session.intent is None:
            return _ok(self._classify_intent(session, text))

        # Step 2: 参数提取
        if self._has_missing_params(session):
            return _ok(self._extract_params(session, text))

        # Step 3: 参数齐全 → 执行
        return _ok(self._execute_tool(session))

    # ── 意图检测（纯 LLM，不修改 session）──

    def _detect_intent(self, text: str) -> tuple[str, float]:
        """LLM 判断用户想用什么工具。返回 (intent, confidence)。"""
        try:
            prompt = safe_format(INTENT_PROMPT, user_message=text)
            result = chat_json("返回纯 JSON，不要 markdown 包裹。", prompt)
        except Exception:
            log.warning(f"意图检测失败，退化为 unknown")
            return "unknown", 0

        intent = result.get("intent", "unknown")
        confidence = result.get("confidence", 0)
        if intent not in TOOLS and intent != "multi_step":
            intent = "unknown"
            confidence = 0
        return intent, confidence

    # ── 内部步骤 ──

    def _classify_intent(self, session: AgentSession, text: str) -> dict:
        """意图识别 + 确认：检测意图、设置 session、检查参数、生成确认消息。"""
        intent, confidence = self._detect_intent(text)

        # 置信度低 → 追问
        if confidence < 0.7 or intent == "unknown":
            return {
                "text": (
                    "我还不太确定您想要做什么，可以再描述一下吗？\n\n"
                    "我能帮你做这些事：\n"
                    "1️⃣ 地面任务分析 — 发送3个Excel + 参数（总成本/后台消耗/上一时段/今日新增占比）→ 消耗报告/催场情况/落位预估\n"
                    "2️⃣ 排片占比预测 — 告诉我日期、影片占比和大盘场次 → 预测各影片（含竞品）排片占比\n"
                    "3️⃣ 分时汇报 — 发送Excel链接或直接发.xlsx文件 → 生成排片情况汇报"
                ),
                "files": [],
                "done": False,
            }

        # 多步骤 — 暂不支持一次处理多种操作
        if intent == "multi_step":
            return {
                "text": (
                    "检测到您想进行多项操作。目前我一次只能处理一种任务，"
                    "请先告诉我您想先做哪个：\n"
                    "1️⃣ 地面任务分析 — 消耗报告/催场情况/落位预估\n"
                    "2️⃣ 排片占比预测 — 预测各影片排片占比\n"
                    "3️⃣ 分时汇报 — 生成排片情况汇报\n\n"
                    "完成后可以继续告诉我下一个需求~"
                ),
                "files": [],
                "done": False,
            }

        session.intent = intent

        # feishu_excel: URL 直接正则提取，累积到 session
        if intent == "feishu_excel":
            normalized = text.replace("；", " ").replace("，", " ").replace(",", " ").replace("\n", " ")
            urls = re.findall(r'https?://\S+', normalized)
            if urls:
                existing = session.params.get("urls", [])
                session.params["urls"] = existing + urls

        # 尝试从同一句话中提取参数（用户可能一句话包含意图+参数）
        if text:
            self._try_extract_params_from_text(session, text)

        # 确认意图 — 只提示真正缺失的参数
        tool = TOOLS[intent]
        # 预处理已有参数（如影片简称→全名），确认消息与后续 LLM 上下文都用解析后的值
        try:
            session.params = tool.resolve_params(session.params)
        except Exception:
            pass
        # 用 session 当前状态（含已累积的文件）计算真正缺失的参数
        temp_params = dict(session.params)
        if session.files:
            temp_params["files"] = session.files
        missing = tool.validate_params(temp_params)
        if missing:
            received = self._format_received(session)
            hints = self._missing_params_hint(intent, missing, session)
            parts = [f"✅ 已识别为【{tool.description.split('——')[0]}】"]
            if received:
                parts.append(f"\n📎 已收到：\n{received}")
            parts.append(f"\n📋 仍需提供：\n{hints}")
            return {
                "text": "\n".join(parts),
                "files": [],
                "done": False,
            }
        # 参数已齐全 → 确认 → 后台执行（resolve_params 已在上面调用过，幂等）
        received = self._format_received(session)
        confirm = f"✅ 已识别为【{tool.description.split('——')[0]}】"
        if received:
            confirm += f"\n📎 已收到：\n{received}"
        return {"text": confirm, "files": [], "done": False, "_deferred": True}

    def _try_extract_params_from_text(self, session: AgentSession, text: str):
        """从文本中提取参数并写入 session。LLM 失败时静默跳过。
        用于意图分类后的首轮参数提取，与 _extract_params 不同的是：
        - 不返回用户可见的错误消息
        - 不调用 _execute_tool
        """
        prompt_template = EXTRACT_PROMPTS.get(session.intent)
        if not prompt_template:
            return
        try:
            today = dt_date.today().strftime("%Y-%m-%d")
            # 构建 LLM 上下文时排除 files（含原始字节，不能进 prompt）
            ctx_params = {k: v for k, v in session.params.items() if k != "files"}
            context = json.dumps(ctx_params, ensure_ascii=False, default=str)
            prompt = safe_format(prompt_template, user_message=text, today=today, context=context)
            extract = chat_json("返回纯 JSON，不要 markdown 包裹。", prompt)
        except Exception as e:
            log.warning(f"首轮参数提取失败 ({session.intent}): {e}")
            return  # LLM 提取失败，静默跳过（不打断意图确认流程）

        params = extract.get("params", {})
        for key, value in params.items():
            if key == "files":
                continue  # files 来自实际文件上传，不用 LLM 的布尔值
            if value is None:
                continue
            if key not in session.params:
                session.params[key] = value
            elif key == "movies" and isinstance(value, list):
                existing = {m["name"]: m for m in session.params["movies"]}
                for new_m in value:
                    name = new_m.get("name")
                    if name and name in existing:
                        if new_m.get("share") is not None:
                            existing[name]["share"] = new_m["share"]
                    elif name:
                        session.params["movies"].append(new_m)

    def _extract_params(self, session: AgentSession, text: str) -> dict:
        """LLM 从自然语言中提取参数。"""
        prompt_template = EXTRACT_PROMPTS.get(session.intent)
        if not prompt_template:
            return self._fallback_error("内部错误：未知意图。")

        # feishu_excel: 用正则提取 URL 并累积，不依赖 LLM
        if session.intent == "feishu_excel":
            normalized = text.replace("；", " ").replace("，", " ").replace(",", " ").replace("\n", " ")
            new_urls = re.findall(r'https?://\S+', normalized)
            if new_urls:
                existing = session.params.get("urls", [])
                existing_set = set(existing)
                for u in new_urls:
                    if u not in existing_set:
                        existing.append(u)
                        existing_set.add(u)
                session.params["urls"] = existing

        try:
            # 注入当天日期用于解析相对日期
            today = dt_date.today().strftime("%Y-%m-%d")
            # 构建 LLM 上下文时排除 files（含原始字节，不能进 prompt）
            ctx_params = {k: v for k, v in session.params.items() if k != "files"}
            context = json.dumps(ctx_params, ensure_ascii=False, default=str)
            prompt = safe_format(prompt_template, user_message=text, today=today, context=context)
            extract = chat_json("返回纯 JSON，不要 markdown 包裹。", prompt)
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

        # 更新 session（files 跳过 LLM 的布尔值，用实际文件替换）
        for key, value in params.items():
            if key == "files":
                continue  # LLM 返回的 files 只是 true/false 指示，不覆盖实际文件
            if value is None:
                continue
            if key not in session.params:
                session.params[key] = value
            elif key == "movies" and isinstance(value, list):
                # 影片列表需要合并：用新的占比更新已有影片
                existing = {m["name"]: m for m in session.params["movies"]}
                for new_m in value:
                    name = new_m.get("name")
                    if name and name in existing:
                        if new_m.get("share") is not None:
                            existing[name]["share"] = new_m["share"]
                    elif name:
                        session.params["movies"].append(new_m)
            elif key == "urls" and isinstance(value, list):
                # URL 列表合并去重
                existing_set = set(session.params.get("urls", []))
                for u in value:
                    if u not in existing_set:
                        session.params["urls"].append(u)
                        existing_set.add(u)

        # 补上实际文件
        if session.files:
            session.params["files"] = session.files

        # 预处理已有参数（如影片简称→全名），确认消息与后续 LLM 上下文都用解析后的值
        try:
            session.params = tool.resolve_params(session.params)
        except Exception:
            pass

        # 重新计算缺失
        actual_missing = tool.validate_params(session.params)

        if actual_missing:
            tool_name = tool.description.split("——")[0]
            received = self._format_received(session)
            hints = self._missing_params_hint(session.intent, actual_missing, session)
            parts = [f"📋 【{tool_name}】"]
            if received:
                parts.append(f"\n📎 已收到：\n{received}")
            parts.append(f"\n📋 仍需提供：\n{hints}")
            return {
                "text": "\n".join(parts),
                "files": [],
                "done": False,
            }

        # 参数齐全 → 确认 → 后台执行（resolve_params 已在上面调用过，幂等）
        tool_name = tool.description.split("——")[0]
        received = self._format_received(session)
        parts = [f"✅ 参数已齐全【{tool_name}】"]
        if received:
            parts.append(f"\n📎 已收到：\n{received}")
        parts.append("\n⏳ 正在处理...")
        return {"text": "\n".join(parts), "files": [], "done": False, "_deferred": True}

    def _execute_tool(self, session: AgentSession) -> dict:
        """在子进程中执行工具，超时则 terminate。"""
        q = multiprocessing.Queue()
        p = multiprocessing.Process(
            target=_run_tool,
            args=(session.intent, session.params, q),
            daemon=True,
        )
        p.start()
        p.join(timeout=60)

        if p.is_alive():
            # 超时 → 真正杀掉子进程（含 Playwright 浏览器等子资源）
            p.terminate()
            p.join(timeout=5)
            if p.is_alive():
                p.kill()  # terminate 没杀掉则强制 kill
            self._clear_session(session.user_id)
            return {"text": "⏰ 处理超时，请稍后重试。", "files": [], "done": True}

        self._clear_session(session.user_id)

        # 从队列取结果
        try:
            status, payload = q.get_nowait()
        except Exception:
            return {"text": "❌ 工具执行异常（未返回结果）", "files": [], "done": True}

        if status == "error":
            return {"text": f"❌ {payload}", "files": [], "done": True}

        result: ToolResult = payload
        if not result.success:
            return {"text": f"❌ {result.error}", "files": [], "done": True}

        return {
            "text": result.text,
            "extra_text": result.extra_text,
            "files": result.files,
            "done": True,
        }

    # ── 公开接口 ──

    def execute_deferred(self, user_id: str) -> dict:
        """执行延迟任务：确认消息已发送后，运行工具并返回结果。"""
        with self._lock:
            session = self._sessions.get(user_id)
        if not session or session.intent is None:
            return {"text": "", "files": [], "done": True}
        return self._execute_tool(session)

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

    def _missing_params_hint(self, intent: str, missing: list[str], session: AgentSession | None = None) -> str:
        """为缺失参数生成友好的提示。"""
        hints = {
            "total_cost": "• 总成本 — 如 300000 或 30万",
            "backend_consume": "• 后台消耗 — 如 32.8 或 32.8%",
            "prev_actual": "• 上一时段实际消耗 — 如 83.4 或 83.4%",
            "d8_pct": "• 今日新增占比 — 如 4.4 或 4.4%",
            "files": (
                "• Excel文件 — 需发送3个：落位表、影城场次明细、任务合作明细"
            ),
            "落位表": "• 落位表",
            "影城场次明细": "• 影城场次明细",
            "任务合作明细": "• 任务合作明细",
            "date": "• 预测日期 — 如 6.15 或 明天",
            "movies": "• 影片及今日新增占比 — 如 封神2:17.6%, 哪吒:8.2%",
            "dapan_total": "• 大盘场次 — 如 42万 或 420000",
            "urls": "• Excel文件链接 — 请发送2个文件链接",
        }
        if intent == "feishu_excel":
            if "files" in missing:
                existing = len(session.files) if session else 0
                remain = max(0, 2 - existing)
                if remain == 0:
                    hints["files"] = "• Excel文件"
                elif remain == 2:
                    hints["files"] = "• Excel文件 — 请发送2个 .xlsx 文件"
                else:
                    hints["files"] = f"• Excel文件 — 还需 {remain} 个"
            if "urls" in missing:
                hints["urls"] = "• Excel文件 — 发送2个文件链接，或直接发送2个 .xlsx 文件"
        return "\n".join(hints.get(m, f"• {m}") for m in missing)

    def _format_received(self, session: AgentSession) -> str:
        """生成「已收到」确认信息，列出用户已提供的参数。"""
        intent = session.intent
        lines = []

        if intent == "reelclean":
            labels = {
                "total_cost": "总成本", "backend_consume": "后台消耗",
                "prev_actual": "上一时段实际消耗", "d8_pct": "今日新增占比",
            }
            for key, label in labels.items():
                val = session.params.get(key)
                if val is not None:
                    if key == "total_cost":
                        lines.append(f"• {label}：{val:,.0f}")
                    else:
                        lines.append(f"• {label}：{val}%")
            if session.files:
                from tools.reelclean_tool import ReelCleanTool
                found = ReelCleanTool.classify_files(session.files)
                if found:
                    lines.append(f"• 文件：{'、'.join(found.keys())}（共{len(session.files)}个）")

        elif intent == "prediction":
            if session.params.get("date"):
                lines.append(f"• 预测日期：{session.params['date']}")
            movies = session.params.get("movies", [])
            if movies:
                names = [m["name"] for m in movies if m.get("name")]
                shares = [m for m in movies if m.get("share") is not None]
                if names:
                    share_str = ""
                    if shares:
                        share_str = "（" + "、".join(
                            f"{m['name']}:{m['share']*100:.1f}%" for m in shares
                        ) + "）"
                    lines.append(f"• 影片：{'、'.join(names)}{share_str}")
            if session.params.get("dapan_total"):
                lines.append(f"• 大盘场次：{session.params['dapan_total']:,}")

        elif intent == "feishu_excel":
            urls = session.params.get("urls", [])
            files = session.files
            if urls:
                if len(urls) == 1:
                    lines.append(f"• 链接：1 个（还需 1 个）")
                else:
                    lines.append(f"• 链接：{len(urls)} 个")
            elif files:
                fnames = [f[0] for f in files]
                if len(files) == 1:
                    lines.append(f"• 文件：{fnames[0]}（还需 1 个）")
                else:
                    lines.append(f"• 文件：{'、'.join(fnames)}")

        return "\n".join(lines) if lines else ""

    def _fallback_error(self, msg: str) -> dict:
        return {"text": f"❌ {msg}", "files": [], "done": True}
