"""
PredictionTool — 影片落位预测。
封装 Prediction-Bot 的核心逻辑：猫眼排片数据获取 + Excel 生成。
"""
import sys
import tempfile
from io import BytesIO
from pathlib import Path

# 引入 Prediction-Bot 的核心模块
_PREDICTION_DIR = Path(r"D:\Prediction-Bot")
if str(_PREDICTION_DIR) not in sys.path:
    sys.path.insert(0, str(_PREDICTION_DIR))

from tools.base import ToolInterface, ToolResult


class PredictionTool(ToolInterface):

    @property
    def name(self) -> str:
        return "prediction"

    @property
    def description(self) -> str:
        return (
            "影片落位预测——根据用户输入的电影名称和累计新增占比，"
            "从猫眼获取当前排片数据，计算落位占比并生成预测Excel"
        )

    @property
    def param_schema(self) -> dict:
        return {
            "date": {
                "label": "预测日期",
                "type": "str",
                "required": True,
                "aliases": ["日期", "预测日期", "哪天"],
            },
            "movies": {
                "label": "影片及今日新增占比",
                "type": "list",
                "required": True,
                "aliases": ["影片", "电影", "片名", "今日新增占比", "占比"],
            },
            "dapan_total": {
                "label": "大盘场次",
                "type": "int",
                "required": True,
                "aliases": ["大盘", "大盘场次", "总场次"],
            },
        }

    @staticmethod
    def _resolve_movie_names(mc, user_names: list[str], date_str: str) -> list[str]:
        """用 LLM 将用户输入的简称匹配为猫眼完整影片名。
        优先匹配预测日期当天会上映的版本（如同系列多部的选择）。
        """
        import json as _json
        from agent.llm_client import chat

        all_movies = mc.fetch_movies()
        all_names = [m["name"] for m in all_movies if m["name"]]

        # 已有精确匹配的跳过 LLM
        if all(n in all_names for n in user_names):
            return user_names

        prompt = (
            "将用户输入的影片简称匹配为猫眼平台完整名称。\n\n"
            f"预测日期：{date_str}\n"
            f"候选影片：{_json.dumps(all_names, ensure_ascii=False)}\n"
            f"用户输入：{_json.dumps(user_names, ensure_ascii=False)}\n\n"
            "规则：\n"
            "1. 每个简称匹配一个完整名称\n"
            "2. 同系列电影（如熊出没），优先匹配预测日期附近上映的版本\n"
            "3. 返回 JSON 数组，顺序与用户输入一致\n\n"
            "只返回 JSON 数组，不要其他内容。"
        )
        try:
            raw = chat("返回纯 JSON 数组，不要 markdown 包裹。", prompt)
            resolved = _json.loads(raw)
            if isinstance(resolved, list) and len(resolved) == len(user_names):
                return resolved
        except Exception:
            pass
        return user_names  # LLM 失败则降级返回原名

    def validate_params(self, params: dict) -> list[str]:
        missing = []
        if not params.get("date"):
            missing.append("date")
        movies = params.get("movies", [])
        if not movies or any(m.get("share") is None for m in movies):
            missing.append("movies")
        if not params.get("dapan_total"):
            missing.append("dapan_total")
        return missing

    def execute(self, params: dict) -> ToolResult:
        from scraper.maoyan import MaoyanClient
        from excel.generator import generate_excel
        from bot.cards import summary as format_summary, result as format_result

        try:
            date_str = params["date"]           # "6.15"
            movies = params["movies"]            # [{"name": "封神2", "share": 0.176}, ...]
            dapan_total = params["dapan_total"]  # 420000

            mc = MaoyanClient()

            # LLM 模糊匹配：将用户简称映射为猫眼完整片名
            user_names = [m["name"] for m in movies]
            resolved = self._resolve_movie_names(mc, user_names, date_str)

            # 构建完整片名→占比的映射（按顺序对应）
            name_share = {}
            for i, full_name in enumerate(resolved):
                if i < len(movies) and movies[i].get("share") is not None:
                    name_share[full_name] = movies[i]["share"]

            matched, total_show_count = mc.fetch_by_date(resolved, date_str)

            if not matched:
                return ToolResult(
                    success=False,
                    error=f"未能从猫眼获取到 {date_str} 的影片排片数据，"
                          f"请确认影片名称与猫眼一致，或日期格式正确（如 6.15）。"
                )

            # 填充用户提供的累计占比
            for m in matched:
                if m["name"] in name_share:
                    m["cumulative_share"] = name_share[m["name"]]

            # 生成 Excel
            excel_bytes = generate_excel(
                date_str=date_str,
                movies=matched,
                dapan_total=dapan_total,
                total_show_count=total_show_count,
            )

            # 保存到临时文件
            tmp = tempfile.NamedTemporaryFile(
                suffix=".xlsx", prefix="prediction_", delete=False
            )
            excel_bytes.seek(0)
            with open(tmp.name, "wb") as f:
                f.write(excel_bytes.read())
            excel_bytes.seek(0)

            # 生成总结文案
            result_text = format_result(date_str, len(matched), dapan_total)
            summary_text = format_summary(date_str, matched, dapan_total, total_show_count)

            full_text = f"{result_text}\n\n{summary_text}"

            return ToolResult(
                success=True,
                text=full_text,
                files=[tmp.name],
            )

        except ImportError as e:
            return ToolResult(
                success=False,
                error=f"依赖缺失: {e}\n请确保 Prediction-Bot 已安装 playwright 等依赖。"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"预测处理失败: {e}"
            )
