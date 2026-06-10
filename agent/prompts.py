"""
Prompt 模板 — 纯字符串拼接，不用模板引擎。

三个核心 prompt:
  INTENT_PROMPT  — 判断用户意图 → 路由到工具
  EXTRACT_PROMPT — 从自然语言提取结构化参数
  CONFIRM_PROMPT — 将参数格式化为用户确认消息
"""


def safe_format(template: str, **kwargs) -> str:
    """安全的模板填充：先转义所有值中的花括号，再调用 .format()。
    防止用户消息中的 { } 导致 KeyError 崩溃。
    """
    escaped = {k: str(v).replace("{", "{{").replace("}", "}}") for k, v in kwargs.items()}
    return template.format(**escaped)

# ── 意图分类 ──
# 输入: user_message
# 输出: {"intent": "reelclean|prediction|feishu_excel|unknown", "confidence": 0.0-1.0}
INTENT_PROMPT = """你是数据处理助手的路由器。根据用户消息判断意图，只返回 JSON。

工具列表：
- reelclean: 影院数据清洗。关键词：清洗、总成本、后台消耗、D8、Excel文件、处理数据、上一时段
- prediction: 影片落位预测。关键词：预测、落位、排片、占比、大盘、猫眼、明天/后天/日期
- feishu_excel: 开场数据提取。关键词：链接、URL、文件链接、解析Excel、开场数据、汇报

规则：
1. 如果用户明确说出了某个工具的典型操作，返回对应 intent
2. 如果用户说了多个工具的操作（如"先清洗再预测"），返回 "multi_step"
3. 如果是闲聊、问候、感谢、无关话题，返回 "unknown"
4. confidence 是你对判断的把握 (0.0-1.0)。低于 0.7 时 Agent 会追问用户

用户消息：{user_message}

返回 JSON（不要其他内容）：
{{"intent": "...", "confidence": 0.0-1.0}}"""


# ── 参数提取 ──
# 输入: user_message + intent
# 输出: {"params": {...}, "missing": [...]}

EXTRACT_REELCLEAN_PROMPT = """从用户消息中提取影院数据清洗的参数。用户可能以任意顺序、任意格式输入。

参数说明：
- total_cost: 总成本（数字，如 300000）。用户可能说"总成本30万""成本300000""30w"
- backend_consume: 后台消耗（百分比数字，如 32.8）。用户可能说"后台消耗32.8%""后台32.8"
- prev_actual: 上一时段实际消耗（百分比数字，如 83.4）。用户可能说"上一时段83.4""上时段83.4%"
- d8_pct: 今日新增占比（数字，如 4.4）。用户可能说"今日新增4.4""今日新增占比4.4%""新增占比4.4""D8是4.4""D8:4.4"
- files: 用户是否提到了文件/Excel。有则为 true 否则 false（不要求数字）

提取规则：
1. "X万" → 解析为 X*10000（如 30万 → 300000）
2. 百分比数字自动去掉 % 符号
3. 无法提取的参数设为 null
4. missing 列出值为 null 的参数名

用户消息：{user_message}

返回 JSON（不要其他内容）：
{{"params": {{"total_cost": 数字或null, "backend_consume": 数字或null, "prev_actual": 数字或null, "d8_pct": 数字或null, "files": true或false}}, "missing": ["缺失参数名"...]}}"""

EXTRACT_PREDICTION_PROMPT = """从用户消息中提取影片落位预测的参数。用户可能以任意顺序、任意格式输入。

参数说明：
- date: 预测日期。如用户说"6.15""6月15日""明天""后天"，统一转为 "M.D" 格式（如"6.15"）
  * "明天"：当前日期 + 1天 → 转为 M.D
  * "后天"：当前日期 + 2天 → 转为 M.D
- movies: 影片及今日新增占比，格式 [{{"name": "片名", "share": 0.176}}, ...]
  * 占比支持：17.6% → 0.176, 0.176 → 0.176, 17.6 → 0.176（>1 则除以 100）
  * 如果用户只说了片名没给占比，share 填 null
  * 分隔符可能是：逗号、中文逗号、分号、顿号、换行
- dapan_total: 大盘场次（整数）。如"42万""420000""四十二万"

当前日期参考：{today}

用户消息：{user_message}

返回 JSON（不要其他内容）：
{{"params": {{"date": "M.D格式"或null, "movies": [{{"name": "...", "share": 小数}}]或[], "dapan_total": 整数或null}}, "missing": ["缺失参数名"...]}}"""

EXTRACT_FEISHU_EXCEL_PROMPT = """从用户消息中提取 Excel 文件链接。

- urls: 从文本中提取所有 https?:// 开头的 URL 列表
- 如果找到了 URL，missing 为空列表 []；如果没找到，urls 为空列表，missing 为 ["urls"]

用户消息：{user_message}

返回 JSON（不要其他内容）。示例：
找到链接时：{{"params": {{"urls": ["https://example.com/file.xlsx"]}}, "missing": []}}
未找到时：{{"params": {{"urls": []}}, "missing": ["urls"]}}"""


# ── 确认消息格式 ──
CONFIRM_PROMPT = """将以下参数格式化为用户友好的确认消息。简洁清晰，用 emoji 点缀。

工具：{intent}
参数：{params}

要求：
- 用自然语言简要列出参数
- 数字加上千分位（如 300,000）
- 百分比加上 % 符号（如 32.8%）
- 最后问一句"确认执行吗？"
- 不超过 5 行"""


# ── 结果格式化 ──
RESPONSE_PROMPT = """将以下工具执行结果格式化为飞书群聊回复。保持原数据准确，语气友好。

工具：{intent}
执行结果：{result_text}

要求：
- 保持原数据不变（数字、百分比等不修改）
- 可以添加简短的说明或 emoji
- 如果有多个段落，用空行分隔
- 如果结果包含分项数据，保留编号"""
