"""
FeishuExcelTool — 分时汇报。
封装 feishu-bot 的核心逻辑：
  - URL 模式：Excel 链接 → 下载 → 解析 → 生成排片情况汇报文案
  - 文件模式：群聊直接发送 .xlsx 附件 → 解析 → 两文件配对合并 → 生成文案
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
            "files": {
                "label": "Excel文件",
                "type": "list",
                "required": False,
                "aliases": ["附件", "文件"],
            },
        }

    def validate_params(self, params: dict) -> list[str]:
        files = params.get("files", [])
        urls = params.get("urls", [])

        # 文件模式：2 个本地文件即够
        if files:
            if len(files) < 2:
                return ["files"]
            return []

        # URL 模式：至少 2 个链接
        if len(urls) < 2:
            return ["urls"]
        return []

    def execute(self, params: dict) -> ToolResult:
        feishu_main = bot_import(FEISHU_BOT_DIR, "main")
        process_urls = feishu_main.process_urls
        _parse_single_file = feishu_main._parse_single_file
        build_message = feishu_main.build_message

        files = params.get("files", [])
        urls = params.get("urls", [])

        try:
            if files:
                # ── 文件模式：本地解析每个 Excel → 配对合并 ──
                entries = []
                for fname, content in files:
                    entry = _parse_single_file(fname, content)
                    if entry:
                        entries.append(entry)

                if len(entries) < 2:
                    return ToolResult(
                        success=False,
                        error=(
                            f"至少需要 2 个有效文件，当前只有 {len(entries)} 个。\n"
                            "请确认：\n"
                            "1. 文件名格式正确（如：影片名(2024-06-10+08:00-...)）\n"
                            "2. Excel中包含「综拓开场数据基础模板2」或类似Sheet\n"
                            "3. Sheet中包含「场次数」「劣势影城数」「排片占比」等列"
                        ),
                    )

                entries.sort(key=lambda e: e["mon_start"])
                main_msg, summary_msg = build_message(entries)

                return ToolResult(
                    success=True,
                    text=main_msg,
                    extra_text=summary_msg,
                    files=[],
                )

            # ── URL 模式：feishu-bot 下载 + 解析 ──
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