"""
ReelCleanTool — 影院数据清洗。
封装 ReelClean-bot 的核心逻辑：3个Excel → 清洗 → 文案+处理后的文件。
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

# 引入 ReelClean-bot 的核心处理模块
_REELCLEAN_DIR = Path(r"D:\ReelClean-bot")
if str(_REELCLEAN_DIR) not in sys.path:
    sys.path.insert(0, str(_REELCLEAN_DIR))

from tools.base import ToolInterface, ToolResult


class ReelCleanTool(ToolInterface):

    @property
    def name(self) -> str:
        return "reelclean"

    @property
    def description(self) -> str:
        return (
            "影院数据清洗——接收3个Excel文件（<影片名>-落.xlsx、影城明细-<影片名>.xlsx、第3个文件）"
            "和4个参数（总成本/后台消耗/上一时段/D8百分比），输出3段文案和2个处理后Excel"
        )

    @property
    def param_schema(self) -> dict:
        return {
            "total_cost": {
                "label": "总成本",
                "type": "float",
                "required": True,
                "aliases": ["总成本", "成本", "总费用", "预算"],
            },
            "backend_consume": {
                "label": "后台消耗",
                "type": "float",
                "required": True,
                "aliases": ["后台消耗", "后台占比", "后台"],
            },
            "prev_actual": {
                "label": "上一时段实际消耗",
                "type": "float",
                "required": True,
                "aliases": ["上一时段", "上时段", "之前时段"],
            },
            "d8_pct": {
                "label": "D8百分比",
                "type": "float",
                "required": True,
                "aliases": ["D8百分比", "D8", "D8占比"],
            },
            "files": {
                "label": "Excel文件",
                "type": "list",
                "required": True,
                "aliases": ["文件", "Excel", "表格"],
            },
        }

    def validate_params(self, params: dict) -> list[str]:
        missing = []
        for key in ["total_cost", "backend_consume", "prev_actual", "d8_pct"]:
            if key not in params or params[key] is None:
                missing.append(key)
        if not params.get("files"):
            missing.append("files")
        return missing

    def execute(self, params: dict) -> ToolResult:
        from auto_clean import process_data

        work_dir = tempfile.mkdtemp(prefix="reelclean_")
        output_dir = tempfile.mkdtemp(prefix="reelclean_out_")

        try:
            # 写入临时文件
            files = params["files"]  # list of (filename, bytes)
            for fname, fcontent in files:
                fpath = os.path.join(work_dir, fname)
                with open(fpath, "wb") as f:
                    f.write(fcontent)

            # 调用原有处理逻辑
            result = process_data(
                work_dir=work_dir,
                output_dir=output_dir,
                total_cost=params["total_cost"],
                backend_consume=params["backend_consume"],
                prev_actual=params["prev_actual"],
                d8_pct=params["d8_pct"],
            )

            # 组装文案
            full_text = (
                f"=== 消耗报告 ===\n{result['wenan1']}\n\n"
                f"=== 开场情况 ===\n{result['wenan2']}\n\n"
                f"=== 落位预估 ===\n{result['wenan3']}"
            )

            # 收集输出文件
            output_files = []
            for key in ["file1_output", "file3_output"]:
                fpath = result.get(key, "")
                if fpath and os.path.exists(fpath):
                    output_files.append(fpath)

            return ToolResult(
                success=True,
                text=full_text,
                files=output_files,
            )

        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                error=f"文件识别失败: {e}\n请确认发送了3个正确命名的Excel文件。",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"清洗处理失败: {e}",
            )
        finally:
            # output_dir 中的文件会在发送后被清理
            shutil.rmtree(work_dir, ignore_errors=True)
            # 注意：output_dir 保留，调用方发完文件后再清理
