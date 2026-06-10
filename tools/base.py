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
