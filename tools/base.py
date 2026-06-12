"""
ToolInterface — 所有工具的抽象基类。
每个工具必须实现: name, description, param_schema, validate_params, execute
"""
import importlib.util
import sys
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

# ── 隔离导入 ──

_import_lock = threading.Lock()


def bot_import(bot_dir: Path, module_path: str):
    """从指定 Bot 目录加载模块，不污染 sys.path。

    用法:
        auto_clean = bot_import(REELCLEAN_DIR, "auto_clean")
        maoyan = bot_import(PREDICTION_DIR, "scraper.maoyan")

    原理:
        用 importlib 按精确文件路径加载，注册到 sys.modules 时加上
        Bot 目录名前缀（如 'ReelClean-bot.auto_clean'），避免与
        本项目或其他 Bot 的同名模块冲突。

    注意:
        被导入模块自身的内部 import 仍依赖 sys.path，因此首次导入时
        会临时将 bot_dir 加入 sys.path，导入完成后立即移除。
    """
    # 已缓存则直接返回
    namespace = bot_dir.name  # 如 "ReelClean-bot"
    cache_key = f"{namespace}.{module_path}"
    if cache_key in sys.modules:
        return sys.modules[cache_key]

    # module_path → 文件路径: "scraper.maoyan" → bot_dir/scraper/maoyan.py
    parts = module_path.split(".")
    file_path = bot_dir / Path(*parts[:-1]) / f"{parts[-1]}.py" if len(parts) > 1 else bot_dir / f"{parts[0]}.py"
    if not file_path.exists():
        # 尝试 __init__.py（包目录）
        pkg_init = bot_dir / Path(*parts) / "__init__.py"
        if pkg_init.exists():
            file_path = pkg_init
        else:
            raise ImportError(f"找不到模块: {file_path}")

    with _import_lock:
        # 再次检查（另一个线程可能已完成加载）
        if cache_key in sys.modules:
            return sys.modules[cache_key]

        # 确保父包在 sys.modules 中（importlib 要求）
        for i in range(len(parts) - 1):
            parent_key = f"{namespace}.{'.'.join(parts[:i+1])}"
            if parent_key not in sys.modules:
                parent_init = bot_dir / Path(*parts[:i+1]) / "__init__.py"
                if parent_init.exists():
                    pspec = importlib.util.spec_from_file_location(parent_key, parent_init)
                    pmod = importlib.util.module_from_spec(pspec)
                    sys.modules[parent_key] = pmod
                    pspec.loader.exec_module(pmod)

        # 临时加入 sys.path（被导入模块可能有自己的 import）
        path_str = str(bot_dir)
        sys.path.insert(0, path_str)
        try:
            spec = importlib.util.spec_from_file_location(cache_key, file_path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[cache_key] = mod
            spec.loader.exec_module(mod)
        finally:
            # 立即移除，不留污染
            try:
                sys.path.remove(path_str)
            except ValueError:
                pass

    return mod


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    text: str = ""                        # 主文案（发给用户）
    extra_text: str = ""                  # 第二条文案（单独发送，如总结跟进语）
    files: list[str] = field(default_factory=list)  # 输出文件路径列表
    error: str = ""                       # 失败时的错误描述


class ToolInterface(ABC):
    """工具抽象基类。

    子类需要：
    - name: 工具标识名 (如 "reelclean")
    - description: 一句话描述（给 LLM 路由用）
    - param_schema: 参数定义 dict
    - validate_params(params) → 返回缺失参数名列表
    - execute(params) → ToolResult
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def param_schema(self) -> dict: ...

    @abstractmethod
    def validate_params(self, params: dict) -> list[str]:
        """校验参数是否齐全。
        Returns: 缺失的参数名列表，空列表 = 全部齐全
        """
        ...

    def resolve_params(self, params: dict) -> dict:
        """参数齐全后、确认前的预处理。

        用于将用户输入的模糊值解析为精确值（如影片简称→猫眼全名）。
        返回更新后的 params，确认消息和后续执行都使用解析后的值。
        默认不做任何处理，子类按需覆盖。
        """
        return params

    @abstractmethod
    def execute(self, params: dict) -> ToolResult:
        """执行工具逻辑。
        params: 包含所有必需参数
        Returns: ToolResult
        """
        ...

    def format_params_for_display(self, params: dict) -> str:
        """将参数格式化为用户可读的确认消息（可选覆盖）。"""
        lines = []
        for key, value in params.items():
            schema = self.param_schema.get(key, {})
            label = schema.get("label", key)
            if isinstance(value, float):
                lines.append(f"  {label}：{value:,.1f}")
            elif isinstance(value, int) and value > 999:
                lines.append(f"  {label}：{value:,}")
            elif isinstance(value, list):
                lines.append(f"  {label}：{len(value)} 个")
            else:
                lines.append(f"  {label}：{value}")
        return "\n".join(lines)
