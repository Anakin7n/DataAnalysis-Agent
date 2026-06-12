"""
FeishuExcelTool — 分时汇报。
封装 feishu-bot 的核心逻辑：Excel URL → 下载 → 解析 → 生成排片情况汇报文案。
"""
from config import FEISHU_BOT_DIR
from tools.base import ToolInterface, ToolResult, bot_import


class FeishuExcelTool(ToolInterface):

    @property
    def name(self) -> str:
        return "feishu_excel"

    @property
    def description(self) -> str:
        return (
            "分时汇报——用户发送Excel文件链接（飞书文档链接），"
            "自动下载、解析目标影片未来两天的排片数据（场次数/劣势影城数/排片占比等），"
            "生成结构化的分时汇报文案"
        )

    @property
    def param_schema(self) -> dict:
        return {
            "urls": {
                "label": "Excel文件链接",
                "type": "list",
                "required": True,
                "aliases": ["链接", "URL", "文件", "地址"],
            },
        }

    def validate_params(self, params: dict) -> list[str]:
        missing = []
        urls = params.get("urls", [])
        if len(urls) < 2:
            missing.append("urls")
        return missing

    def execute(self, params: dict) -> ToolResult:
        feishu_main = bot_import(FEISHU_BOT_DIR, "main")
        process_urls = feishu_main.process_urls

        try:
            urls = params["urls"]

            # 调用 feishu-bot 核心处理逻辑
            result = process_urls(urls)

            if result is None:
                return ToolResult(
                    success=False,
                    error=(
                        "处理失败，请确认：\n"
                        "1. 提供了至少2个Excel文件链接\n"
                        "2. 文件名格式正确（如：影片名(2024-06-10+08:00-...)）\n"
                        "3. Excel中包含「综拓开场数据基础模板2」或类似Sheet\n"
                        "4. Sheet中包含「场次数」「劣势影城数」「排片占比」等列"
                    ),
                )

            main_msg, summary_msg = result

            return ToolResult(
                success=True,
                text=main_msg,
                extra_text=summary_msg,
                files=[],
            )

        except ImportError as e:
            return ToolResult(
                success=False,
                error=f"依赖缺失: {e}\n请确保 feishu-bot 的相关依赖已安装。"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Excel解析失败: {e}"
            )