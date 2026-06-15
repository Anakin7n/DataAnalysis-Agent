"""
ToolInterface — 所有工具的抽象基类。
每个工具必须实现: name, description, param_schema, validate_params, execute
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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
