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
                "label": "影片列表",
                "type": "list",
                "required": True,
                "aliases": ["影片", "电影", "片名"],
            },
            "dapan_total": {
                "label": "大盘场次",
                "type": "int",
                "required": True,
                "aliases": ["大盘", "大盘场次", "总场次"],
            },
        }

    def validate_params(self, params: dict) -> list[str]:
        missing = []
        if not params.get("date"):
            missing.append("date")
        if not params.get("movies"):
            missing.append("movies")
        if not params.get("dapan_total"):
            missing.append("dapan_total")
        return missing

    def execute(self, params: dict) -> ToolResult:
        from scraper.maoyan import MaoyanClient
        from excel.generator import generate_excel
        from bot.cards import summary as format_summary, result as format_result
        from datetime import date as dt_date

        try:
            date_str = params["date"]           # "6.15"
            movies = params["movies"]            # [{"name": "封神2", "share": 0.176}, ...]
            dapan_total = params["dapan_total"]  # 420000

            # 调用猫眼爬虫
            mc = MaoyanClient()
            movie_names = [m["name"] for m in movies]
            matched, total_show_count = mc.fetch_by_date(movie_names, date_str)

            if not matched:
                return ToolResult(
                    success=False,
                    error=f"未能从猫眼获取到 {date_str} 的影片排片数据，"
                          f"请确认影片名称与猫眼一致，或日期格式正确（如 6.15）。"
                )

            # 填充用户提供的累计占比
            for m in matched:
                for user_m in movies:
                    if user_m["name"] == m["name"]:
                        m["cumulative_share"] = user_m["share"]
                        break

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
