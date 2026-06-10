# PRD: DataAnalysis-Agent — 飞书自然语言数据处理助手

**Author:** maoyan
**Date:** 2026-06-10
**Status:** Draft
**Version:** 1.0
**Taskmaster Optimized:** Yes

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Problem Statement](#problem-statement)
3. [Goals & Success Metrics](#goals--success-metrics)
4. [User Stories](#user-stories)
5. [Functional Requirements](#functional-requirements)
6. [Non-Functional Requirements](#non-functional-requirements)
7. [Technical Considerations](#technical-considerations)
8. [Implementation Roadmap](#implementation-roadmap)
9. [Out of Scope](#out-of-scope)
10. [Open Questions & Risks](#open-questions--risks)
11. [Validation Checkpoints](#validation-checkpoints)
12. [Appendix: Task Breakdown Hints](#appendix-task-breakdown-hints)

---

## Executive Summary

当前有 3 个独立的飞书数据处理 Bot（ReelClean-bot 影院数据清洗、Prediction-Bot 影片落位预测、feishu-bot 开场数据提取），每个都有各自的参数格式要求，用户需要记住"哪个 Bot 干什么、参数顺序是什么"。本 Agent 在三个 Bot 之上加一层 LLM 驱动的自然语言理解层，用户只需用自然语言描述需求，Agent 自动识别意图、提取参数、路由到正确的工具、并以自然语言返回结果。飞书群聊作为唯一交互入口。

期待效果：业务同事无需任何培训即可使用，参数格式错误率趋近于零。

---

## Problem Statement

### Current Situation

三个飞书 Bot 各自独立运行：
- **ReelClean-bot**（`auto_clean.py`）：接收 3 个 Excel 文件 + 4 个数值参数（总成本/后台消耗/上一时段/D8百分比），正则解析参数
- **Prediction-Bot**（`maoyan.py` + `generator.py`）：状态机引导 `/start → 日期 → 影片占比 → 大盘场次`，严格按序输入
- **feishu-bot**（`main.py`）：自动识别消息中的 Excel URL，下载解析生成汇报文案

**痛点：**
1. **工具分散**：用户需要知道"清洗数据找 Bot A，预测排片找 Bot B"
2. **参数死板**：正则匹配对格式敏感，`"总成本:300000"` 可以、`"成本30万"` 失败
3. **错误不友好**：参数解析失败只能报错，无法引导纠正
4. **无上下文**：每次都是全新对话，上次的参数不能复用

### User Impact

- **受影响用户**：2-5 人的业务团队，非技术背景
- **痛点严重度**：Medium — 可以靠记住格式绕过去，但每次出错都要重新来一遍
- **当前 workaround**：老用户死记格式，新用户问老用户

### Business Impact

- **时间浪费**：每次格式错误重试平均浪费 2-3 分钟
- **使用率抑制**：新同事宁愿手动处理也不愿意学 Bot 用法
- **机会成本**：三个 Bot 的核心处理能力已经稳定，卡在交互层

### Why Solve This Now?

三个 Bot 的核心处理逻辑已成熟（已稳定运行），LLM（特别是 DeepSeek 等国产模型）的工具调用能力已经足够强，改造交互层成本低、收益高。1-2 周可交付 MVP。

---

## Goals & Success Metrics

### Goal 1: 消除参数格式错误（最高优先级）

- **Metric:** 参数解析失败率
- **Baseline:** 当前正则模式约 30% 的首次输入需要重试（预估）
- **Target:** < 5% 首次输入需要重试
- **Timeframe:** MVP 上线即验证
- **Measurement:** 统计 Agent 追问次数 / 总请求次数

### Goal 2: 降低使用门槛（第二优先级）

- **Metric:** 新用户首次使用成功所需时间
- **Baseline:** 当前需要找到正确 Bot → 学习参数格式 → 可能需要 2-3 次尝试
- **Target:** 新用户自然语言一句话搞定，无需外部指导
- **Timeframe:** MVP 上线即验证
- **Measurement:** 观察新同事的首次使用情况

### Goal 3: 处理效率提升（第三优先级）

- **Metric:** 单次数据处理从发起到拿到结果的时间
- **Baseline:** 当前 2-5 分钟（含格式纠错、bot 切换）
- **Target:** < 1 分钟（一句话 + 等待处理）
- **Timeframe:** MVP 上线即验证

---

## User Stories

### Story 1: 自然语言触发数据清洗（核心场景）

**As a** 业务同事，
**I want to** 在飞书群聊里用口语描述清洗需求，
**So that I can** 不用记参数格式就能完成数据清洗。

**对话示例：**
```
用户: "帮我清洗一下数据，总成本30万，后台消耗32.8，上一时段83.4，D8百分比4.4"
      [附带 3 个 Excel 文件]

Agent: "✅ 已识别为【影院数据清洗】，参数确认：
       总成本：300,000
       后台消耗：32.8%
       上一时段实际消耗：83.4%
       D8百分比：4.4%
       文件：3个Excel已收到
       开始处理..."

       [处理完成后]

Agent: "📊 清洗完成！
       === 消耗报告 ===
       6月10日《封神2》单体任务后台消耗32.8%，实际消耗34.2%...
       
       === 开场情况 ===
       截止6月10日17点...
       
       [附带 2 个处理后 Excel]"
```

**Acceptance Criteria:**
- [ ] Agent 能从任意顺序的口语输入中提取 4 个数值参数
- [ ] 支持多种格式：`"30万"/"300000"/"总成本:300000"`
- [ ] 参数缺失时明确追问具体缺少什么
- [ ] 处理结果以自然语言总结 + 文件方式回复
- [ ] 处理失败时给出可操作的错误信息

**Task Breakdown Hint:**
- 封装 ReelClean 核心逻辑为无状态函数（3h）
- 设计参数提取 prompt + 测试各种输入变体（4h）
- 实现多轮追问对话状态机（3h）

**Dependencies:** 三个 Bot 源码可用

---

### Story 2: 自然语言触发落位预测

**As a** 业务同事，
**I want to** 用口语描述预测需求，
**So that I can** 不需要按 `/start → 日期 → 影片 → 大盘` 的固定流程操作。

**对话示例：**
```
用户: "预测一下6月15号的排片，封神2占17.6%，哪吒占8.2%，大盘42万场"

Agent: "✅ 已识别为【影片落位预测】，参数确认：
       日期：6月15日
       影片：封神2(17.6%)、哪吒(8.2%)
       大盘场次：420,000
       正在查询猫眼排片数据..."

       [处理完成后]

Agent: "📊 预测结果：
       周三落位：
       封神2：21.3%
       哪吒：11.8%
       
       [附带预测 Excel]"
```

**Acceptance Criteria:**
- [ ] Agent 能从口语中提取日期、多部影片名称及占比
- [ ] 日期支持：`"6.15"/"6月15日"/"明天"` → 正确解析
- [ ] 占比支持：`"17.6%"/"0.176"/"17.6"` → 自动归一化
- [ ] 任意参数缺失时追问
- [ ] 猫眼 API 失败时优雅降级

**Task Breakdown Hint:**
- 封装 Prediction 爬虫+Excel生成逻辑（4h）
- 设计影片列表提取 prompt（处理多影片多种分隔符）（3h）
- 相对日期解析（"明天"/"后天" → 实际日期）（1h）

**Dependencies:** Prediction-Bot 源码可用

---

### Story 3: Excel 链接解析（feishu-bot 功能）

**As a** 业务同事，
**I want to** 直接把 Excel 链接丢到群里，
**So that I can** 自动获得解析后的数据汇报文案。

**对话示例：**
```
用户: "帮我看看这两个文件的数据
      https://xxx.feishu.cn/file/xxx.xlsx
      https://xxx.feishu.cn/file/yyy.xlsx"

Agent: "✅ 已识别为【开场数据提取】，正在下载解析..."

       [处理完成后]

Agent: "辛苦同步
       1）优先推进已开预售未开《封神2》的影城...
       2）目标进度低于均值的小伙伴们继续加油
       
       截止至6月10日10点，【封神2】6月9日-10日开场数据如上..."
```

**Acceptance Criteria:**
- [ ] Agent 能从混合文本中提取文件 URL
- [ ] 自动下载、解析、生成文案
- [ ] 文件名格式不符时给出明确提示
- [ ] 文件数量不足 2 个时追问

**Task Breakdown Hint:**
- 封装 feishu-bot 的 URL→下载→解析→文案生成流程（3h）

**Dependencies:** feishu-bot 源码可用

---

### Story 4: 意图模糊/多步需求

**As a** 业务同事，
**I want to** 说模糊需求时 Agent 能引导我补充信息，
**So that I can** 在不确定怎么表达时也能完成操作。

**对话示例：**
```
用户: "帮我处理下排片"
Agent: "我理解您需要处理排片数据，有两种可能：
       1️⃣ 【数据清洗】：上传Excel文件，进行影院数据清洗
       2️⃣ 【落位预测】：输入影片占比，预测排片落位
       您想做哪个？或者直接发文件/参数给我也可以自动判断。"

用户: "先清洗再预测"
Agent: "好的，我会分两步执行。
       第一步：请发送3个Excel文件，并提供清洗参数（总成本/后台消耗/上一时段/D8百分比）。
       第二步：根据清洗结果，提供预测所需的影片占比和大盘场次。"
```

**Acceptance Criteria:**
- [ ] Agent 能识别模糊意图并引导用户澄清
- [ ] Agent 能识别多步需求并分步执行
- [ ] 闲聊/问候消息友好回应，不误触工具

**Task Breakdown Hint:**
- 意图分类 prompt 设计（含 confidence threshold）（2h）
- 多步任务编排（2h）

**Dependencies:** Story 1-3 完成

---

### Story 5: 上下文记忆

**As a** 经常使用的业务同事，
**I want to** 某些参数能记住上次的值，
**So that I can** 不需要每次都重复输入。

**对话示例：**
```
用户: "跟上次一样的参数，再清洗一次"
Agent: "上次参数：总成本300,000 / 后台消耗32.8% / 上一时段83.4% / D8百分比4.4%
       确认使用这些参数吗？请发送新的3个Excel文件。"

用户: "对"
Agent: "收到，等待Excel文件..."
```

**Acceptance Criteria:**
- [ ] 记住每个用户的上一组参数（按工具分别存储）
- [ ] "跟上次一样"触发参数复用
- [ ] 复用前必须确认

**Task Breakdown Hint:**
- Session 参数持久化（JSON 文件）（2h）

**Dependencies:** Story 1-3 完成
**Priority:** P1（MVP 不做）

---

## Functional Requirements

### Must Have (P0) - MVP 必须

#### REQ-001: 统一飞书消息入口
**Description:** 单一飞书 Bot 接收所有消息，WebSocket 长连接

**Acceptance Criteria:**
- [ ] 一个 App ID 同时服务于三种工具
- [ ] 支持文本消息（自然语言指令）
- [ ] 支持文件消息（Excel 文件上传）
- [ ] 消息去重（与现有 seen 机制兼容）

**Technical Specification:**
```python
# 复用现有 FeishuWsClient，统一事件入口
class AgentGateway:
    def __init__(self, agent: DataAnalysisAgent):
        self.agent = agent
        self.ws = FeishuWsClient(APP_ID, APP_SECRET)

    def on_message(self, chat_id, msg_type, content, files):
        # 所有消息统一交给 Agent 处理
        response = await self.agent.handle(chat_id, msg_type, content, files)
```

**Dependencies:** 复用现有 WS 客户端代码

---

#### REQ-002: LLM 意图识别
**Description:** 使用 DeepSeek API 判断用户想执行哪种操作

**Acceptance Criteria:**
- [ ] 准确识别 3 种工具：reelclean / prediction / feishu_excel
- [ ] 非业务消息识别为 unknown 并友好回应
- [ ] 置信度 < 0.7 时追问用户澄清
- [ ] 同上一次 API 调用 < 1s

**Technical Specification:**
```python
def classify_intent(text: str) -> dict:
    prompt = f"""你是数据处理助手的路由器。判断用户意图：
    工具：
    1. reelclean - 影院数据清洗（涉及 总成本/后台消耗/Excel文件 等关键词）
    2. prediction - 影片落位预测（涉及 预测/落位/排片/占比/大盘 等关键词）
    3. feishu_excel - 开场数据提取（发Excel链接做数据解析）

    用户消息: {text}

    返回JSON: {{"intent": "...", "confidence": 0.0-1.0}}
    如果无法判断，intent 为 "unknown"
    """
```

**Task Breakdown:**
- DeepSeek API 客户端封装（1h）
- 意图分类 prompt + 单元测试（2h）
- 降级策略（API 不可用时的默认行为）（1h）

**Dependencies:** 无

---

#### REQ-003: 自然语言参数提取
**Description:** 从用户口语中提取结构化参数，支持多种表达方式

**参数定义：**

| 工具 | 参数 | 类型 | 支持格式 |
|------|------|------|----------|
| reelclean | total_cost | float | `"30万"/"300000"/"总成本:300000"` |
| reelclean | backend_consume | float | `"32.8%"/"32.8"/"后台消耗三十二点八"` |
| reelclean | prev_actual | float | 同上 |
| reelclean | d8_pct | float | `"4.4%"/"4.4"/"D8:4.4"` |
| prediction | date | str | `"6.15"/"6月15日"/"明天"/"后天"` |
| prediction | movies | list | `"封神2:17.6%, 哪吒:8.2%"/"封神2 0.176 哪吒 0.082"` |
| prediction | dapan_total | int | `"42万"/"420000"/"四十二万"` |
| feishu_excel | urls | list | URL 从文本中自动提取 |

**Acceptance Criteria:**
- [ ] 每种参数至少支持 3 种常见口语表达
- [ ] 缺失参数标记为 null，不猜测
- [ ] 数字格式自动归一化（百分比 → 小数，万 → ×10000）

**Task Breakdown:**
- 各工具参数提取 prompt（3h）
- 参数归一化函数（1h）
- 测试 20+ 输入变体（2h）

**Dependencies:** REQ-002

---

#### REQ-004: 多轮对话追问
**Description:** 参数不全时不报错，用自然语言追问缺失参数

**Acceptance Criteria:**
- [ ] 明确指出缺失哪个参数
- [ ] 提供示例帮助用户补全
- [ ] 支持单次追问补充多个参数
- [ ] 超时（10分钟）自动清理未完成的 session

**Technical Specification:**
```python
class SessionState:
    user_id: str
    intent: str
    params: dict          # 已提取的参数
    missing: list[str]    # 缺失的参数名
    files: list           # 已收到的文件
    last_active: float    # 最后活跃时间
```

**Dependencies:** REQ-003

---

#### REQ-005: 工具执行 & 结果回复
**Description:** 参数齐全后调用对应工具，将结果自然语言化后回复

**Acceptance Criteria:**
- [ ] 三个工具均可正常执行与独立 Bot 一致的处理逻辑
- [ ] 处理结果先以自然语言总结 + 再发原始数据文件
- [ ] 工具执行失败时给出可读的错误提示（而非堆栈）
- [ ] 单个工具执行在独立线程中，不阻塞消息接收

**Dependencies:** REQ-001, REQ-003

---

### Should Have (P1) - MVP 之后

#### REQ-006: 用户级参数记忆
**Description:** 记住用户上次使用的参数，支持"跟上次一样"

#### REQ-007: 多步任务编排
**Description:** 支持"先清洗再预测"这类链式需求

#### REQ-008: LLM 降级处理
**Description:** DeepSeek API 不可用时，自动降级到本地正则匹配（保证基本可用）

---

### Nice to Have (P2) - 远期

#### REQ-009: 主动推送
每日定时报告 / 异常数据告警

#### REQ-010: 使用统计
每个工具的使用频次、成功率、用户分布

---

## Non-Functional Requirements

### Performance

**Response Time:**
- 消息接收 → 意图识别 → 首次回复（确认/追问）：< 2s
- DeepSeek API 调用：< 3s（含网络延迟）
- 数据处理（不含 LLM）：与现有 Bot 一致（< 10s）

**Concurrency:**
- 支持 5 个用户同时发起请求
- 使用 ThreadPoolExecutor 隔离工具执行

**Resource Usage:**
- 内存：< 256MB（单实例）
- CPU：低，主要是 I/O 等待

---

### Reliability

**Uptime:**
- 飞书 WS 断开自动重连（复用现有机制）
- 工具执行失败不影响其他用户

**Error Handling:**
- DeepSeek API 超时（> 10s）：告知用户稍后重试
- 猫眼（Maoyan）API 不可用：明确告知是外部数据源问题
- Excel 解析失败：指出是哪个文件、什么问题

---

### Security

- App Secret 存放在 `.env`，不提交到 Git
- DeepSeek API Key 同上
- 用户 session 仅存内存，不持久化敏感数据
- 飞书消息内容不存储（除非用户主动要求）

---

### Compatibility

- Python 3.12+（与现有 Bot 一致）
- 飞书 API v3
- DeepSeek API（兼容 OpenAI SDK 格式）

---

## Technical Considerations

### System Architecture

```
┌──────────────────────────────────────────────────┐
│                  飞书群聊                         │
└──────────────────────┬───────────────────────────┘
                       │ WebSocket (protobuf)
┌──────────────────────▼───────────────────────────┐
│            gateway/feishu_gateway.py              │
│  · WebSocket 连接管理 (复用现有 FeishuWsClient)     │
│  · 消息去重 + 事件分发                             │
│  · 飞书 REST API (消息/文件 发送接收)              │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│              agent/core.py (DataAnalysisAgent)    │
│  ┌─────────────────────────────────────────────┐ │
│  │ 1. Intent Classifier  (DeepSeek API)        │ │
│  │    → 路由到 tool                             │ │
│  └──────────────┬──────────────────────────────┘ │
│  ┌──────────────▼──────────────────────────────┐ │
│  │ 2. Parameter Extractor (DeepSeek API)       │ │
│  │    → 自然语言 → 结构化参数                    │ │
│  └──────────────┬──────────────────────────────┘ │
│  ┌──────────────▼──────────────────────────────┐ │
│  │ 3. Session Manager                          │ │
│  │    → 多轮对话状态机 + 参数记忆                │ │
│  └──────────────┬──────────────────────────────┘ │
│  ┌──────────────▼──────────────────────────────┐ │
│  │ 4. Tool Executor                            │ │
│  │    → 调用对应工具，收集结果                    │ │
│  └──────────────┬──────────────────────────────┘ │
│  ┌──────────────▼──────────────────────────────┐ │
│  │ 5. Response Formatter (DeepSeek API)        │ │
│  │    → 结构化结果 → 自然语言回复                │ │
│  └─────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
  ┌────────────┐ ┌──────────┐ ┌──────────┐
  │ reelclean  │ │prediction│ │feishu    │
  │  Tool      │ │  Tool    │ │excel Tool│
  │            │ │          │ │          │
  │ auto_clean │ │ maoyan   │ │ process  │
  │ .py 核心   │ │ scraper  │ │ _urls()  │
  │ process_   │ │ + excel  │ │ + build  │
  │ data()     │ │ generator│ │ _msg()   │
  └────────────┘ └──────────┘ └──────────┘
```

### Key Components

1. **Feishu Gateway**: 复用现有 `FeishuWsClient`，使用相同的 protobuf 编解码、token 管理、消息去重
2. **Agent Core**: 新增，LLM 驱动的路由器 + 状态机
3. **Tools Layer**: 从三个 Bot 抽取核心处理函数，封装为统一接口
4. **LLM Client**: DeepSeek API 封装，通过 OpenAI 兼容 SDK 调用

### API Specifications

**DeepSeek API 调用（兼容 OpenAI SDK）：**
```python
from openai import OpenAI

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

def call_llm(system_prompt: str, user_message: str) -> str:
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=0.1,   # 低温度，保证稳定输出
        max_tokens=500,
    )
    return response.choices[0].message.content
```

**ToolInterface 抽象：**
```python
class ToolInterface(ABC):
    name: str
    description: str

    @abstractmethod
    def validate_params(self, params: dict) -> list[str]:
        """返回缺失的参数名列表"""

    @abstractmethod
    def execute(self, params: dict) -> dict:
        """返回 {'text': '...', 'files': ['path1', 'path2']}"""

    def format_params_for_display(self, params: dict) -> str:
        """将参数格式化为用户可读的确认消息"""
```

### Technology Stack

**Core:**
- Python 3.12+
- asyncio + websockets（飞书长连接）
- openai SDK（DeepSeek API 调用）

**Reused from existing bots:**
- `auto_clean.py` — 数据清洗核心逻辑 (ReelClean-bot)
- `maoyan.py` + `generator.py` — 猫眼爬虫 + Excel 生成 (Prediction-Bot)
- `build_message()` + `process_urls()` — 开场数据解析 (feishu-bot)

**New:**
- `agent/core.py` — Agent 主循环
- `agent/llm_client.py` — DeepSeek 封装
- `agent/prompts.py` — 所有 prompt 模板
- `tools/base.py` — ToolInterface 抽象
- `tools/reelclean_tool.py`
- `tools/prediction_tool.py`
- `tools/feishu_excel_tool.py`

### External Dependencies

1. **DeepSeek API:**
   - Purpose: 意图识别、参数提取、结果格式化
   - Failure handling: 降级到正则匹配（P1），告知用户

2. **飞书 Open API:**
   - Purpose: 消息收发、文件上传下载
   - Failure handling: 自动重试，错误日志

3. **猫眼 API + Playwright:**
   - Purpose: Prediction-Bot 获取排片数据
   - Failure handling: 明确告知用户数据源异常

---

## Implementation Roadmap

### Phase 1: 基础设施 + 工具封装 (Day 1-2)
**Goal:** 项目骨架、三个工具可独立调用

**Tasks:**
- [ ] 项目初始化（目录结构、requirements.txt、config.py）
  - Complexity: Small (1h)
  - Dependencies: None

- [ ] ToolInterface 抽象基类
  - Complexity: Small (0.5h)
  - Dependencies: None

- [ ] ReelCleanTool — 封装 `auto_clean.process_data()`
  - Complexity: Medium (3h)
  - Dependencies: ToolInterface

- [ ] PredictionTool — 封装 `maoyan.fetch_by_date()` + `generator.generate_excel()`
  - Complexity: Medium (4h)
  - Dependencies: ToolInterface

- [ ] FeishuExcelTool — 封装 URL 下载解析 + 文案生成
  - Complexity: Medium (3h)
  - Dependencies: ToolInterface

**Validation Checkpoint:** 三个 Tool 可通过 Python 代码独立调用并返回正确结果

---

### Phase 2: LLM 集成 + Agent 核心 (Day 2-4)
**Goal:** 从自然语言到工具调用的完整链路

**Tasks:**
- [ ] DeepSeek API 客户端 + 配置
  - Complexity: Small (1h)
  - Dependencies: None

- [ ] 意图分类 Prompt + Router 实现
  - Complexity: Medium (3h)
  - Dependencies: LLM 客户端

- [ ] 参数提取 Prompt（3 个工具各一套）
  - Complexity: Medium (4h)
  - Dependencies: LLM 客户端

- [ ] Session 管理器（多轮对话状态机）
  - Complexity: Medium (3h)
  - Dependencies: 意图分类

- [ ] Agent 主循环（意图 → 提取 → 追问 → 执行 → 回复）
  - Complexity: Medium (4h)
  - Dependencies: 以上全部

- [ ] Response Formatter（LLM 自然语言化结果）
  - Complexity: Small (2h)
  - Dependencies: LLM 客户端

**Validation Checkpoint:** 在命令行中可以输入自然语言 → 得到正确的工具调用和结果

---

### Phase 3: 飞书集成 (Day 4-5)
**Goal:** 接入飞书，群聊中可用

**Tasks:**
- [ ] Feishu Gateway（复用现有 WS 客户端 + 事件分发到 Agent）
  - Complexity: Medium (3h)
  - Dependencies: Phase 2

- [ ] 文件消息处理（接收 Excel → 暂存 → 关联到 session）
  - Complexity: Small (2h)
  - Dependencies: Feishu Gateway

- [ ] 端到端联调（飞书群聊 → Agent → 工具 → 回复）
  - Complexity: Small (2h)
  - Dependencies: 以上全部

**Validation Checkpoint:** 在飞书群聊中发自然语言消息，Agent 正确识别、处理并回复

---

### Phase 4: 测试 + 打磨 (Day 5-6)
**Goal:** 覆盖边界情况，写测试

**Tasks:**
- [ ] 参数提取测试集（20+ 输入变体）
  - Complexity: Small (2h)
  - Dependencies: Phase 2

- [ ] 意图分类测试集（10+ 场景含模糊/闲聊）
  - Complexity: Small (1h)
  - Dependencies: Phase 2

- [ ] 多轮对话测试（参数不全追问流程）
  - Complexity: Medium (2h)
  - Dependencies: Phase 2

- [ ] 错误场景测试（LLM 超时、工具失败、文件格式错）
  - Complexity: Small (2h)
  - Dependencies: Phase 3

- [ ] Bug 修复
  - Complexity: Variable
  - Dependencies: 测试结果

**Validation Checkpoint:** 所有测试通过，5 个典型用户场景端到端可用

---

### Phase 5: 部署 + 文档 (Day 6-7)
**Goal:** 实际跑起来，团队可用

**Tasks:**
- [ ] 部署到运行环境（与现有 Bot 共存）
  - Complexity: Small (1h)

- [ ] 编写用户使用指南（3 句话 + 5 个示例）
  - Complexity: Small (0.5h)

- [ ] 团队试用 + 反馈收集
  - Complexity: Small (1h)

**Validation Checkpoint:** 团队有人实际使用并成功完成至少一次完整流程

---

### Effort Estimation

| Phase | Hours | 说明 |
|-------|-------|------|
| Phase 1: 基础设施 | 11.5h | 工具封装为主 |
| Phase 2: LLM + Agent | 17h | 核心难点 |
| Phase 3: 飞书集成 | 7h | 胶水代码 |
| Phase 4: 测试 | 7h | 边界覆盖 |
| Phase 5: 部署 | 2.5h | |
| **Total** | **~45h** | 约 6-7 个工作日 |

**Risk Buffer:** +30%（约 14h）用于 LLM prompt 调优
**Final Estimate:** ~60h（约 8 个工作日）

---

## Out of Scope

**第一版明确不做的：**

1. **Web 管理后台** — 飞书群聊是唯一交互入口
2. **多语言支持** — 只做中文
3. **用户权限管理** — 飞书群聊本身就是天然权限边界
4. **数据看板** — 不做使用统计
5. **定时任务/主动推送** — 只做被动响应
6. **新工具接入框架** — 不做插件系统，需要新工具时直接在 Agent 加
7. **语音/图片输入** — 纯文本 + Excel 文件
8. **mCP/function calling** — 先用 prompt 工程方式做 router，不引入额外复杂度

---

## Open Questions & Risks

### Open Questions

#### Q1: DeepSeek API 延迟是否满足实时对话体验？
- **Status:** 需实测
- **Options:** (A) 直接调用，接受 2-3s 延迟 (B) 流式输出降低感知延迟
- **Owner:** 开发
- **Deadline:** Phase 2
- **Impact:** Medium（影响用户体验但非 blocker）

#### Q2: 三个 Bot 是否需要在 Agent 之外继续独立运行？
- **Status:** 待定
- **Options:** (A) Agent 唯一入口，旧 Bot 下线 (B) Agent 和旧 Bot 并行
- **Owner:** maoyan
- **Deadline:** Phase 3 前
- **Impact:** Low（部署方式不同，核心逻辑一致）

#### Q3: LLM token 消耗成本？
- **Status:** 需估算
- **Options:** DeepSeek 价格较低（约 ¥1/百万 token），单次对话约 2000 token
- **Impact:** Low（预计月成本 < ¥50）

---

### Risks & Mitigation

| Risk | Likelihood | Impact | Severity | Mitigation | Contingency |
|------|------------|--------|----------|------------|-------------|
| DeepSeek API 不稳定 | Medium | High | High | 设置 timeout + retry | 降级到正则匹配（保留原有解析逻辑） |
| LLM 参数提取错误（幻觉） | Medium | Medium | Medium | 参数确认步骤 + 用户最终审核 | 用户发现错误后手动修正 |
| Prompt 注入/越狱 | Low | Low | Low | 系统 prompt 限定行为边界 | 不处理敏感操作，接受低风险 |
| 猫眼 API 反爬加强 | Medium | Medium | Medium | 降低请求频率 | 告知用户手动查看 |
| 文件暂存超时丢失 | Low | Medium | Low | 延长 timeout 到 20min + 提醒用户 | 用户重新发送 |

---

## Validation Checkpoints

### Checkpoint 1: 工具封装完成 (Phase 1)
- [ ] 三个 Tool 类可独立 import 并执行
- [ ] 各 Tool 的 validate_params 正确返回缺失参数
- [ ] 处理结果与原 Bot 一致

### Checkpoint 2: Agent 核心可用 (Phase 2)
- [ ] 10 条自然语言输入中，8+ 条正确识别意图和提取参数
- [ ] 参数不全时正确追问
- [ ] 完整的处理 → 回复链路走通

### Checkpoint 3: 飞书可用 (Phase 3)
- [ ] 飞书群聊中发消息，Agent 正常响应
- [ ] Excel 文件上传后能被识别和处理
- [ ] 多用户同时请求互不干扰

### Checkpoint 4: 质量达标 (Phase 4)
- [ ] 所有测试用例通过
- [ ] 5 个端到端场景均可用
- [ ] 错误场景有友好提示

### Checkpoint 5: 部署上线 (Phase 5)
- [ ] 至少 1 个真实用户成功使用
- [ ] 无阻塞性 bug

---

## Appendix: Task Breakdown Hints

### TaskMaster 任务结构建议

**Setup & Infrastructure (4 tasks, ~6h)**
1. 项目目录结构 + 依赖配置 (1h)
2. ToolInterface 抽象类 (0.5h)
3. DeepSeek API 客户端封装 (1.5h)
4. 配置文件（.env 模板 + config.py）(0.5h)

**Tool 封装 (3 tasks, ~10h)**
5. ReelCleanTool 封装与测试 (3h)
6. PredictionTool 封装与测试 (4h)
7. FeishuExcelTool 封装与测试 (3h)

**Agent 核心 (5 tasks, ~16h)**
8. 意图分类 Prompt + Router (3h)
9. 参数提取 Prompt（三个工具）(4h)
10. Session 管理器 (3h)
11. Agent 主循环 (4h)
12. Response Formatter (2h)

**飞书集成 (3 tasks, ~7h)**
13. Feishu Gateway 适配 (3h)
14. 文件消息处理 (2h)
15. 端到端联调 (2h)

**测试 (3 tasks, ~5h)**
16. 参数提取 + 意图分类测试集 (2h)
17. 多轮对话测试 (1.5h)
18. 错误场景覆盖 (1.5h)

**部署 (2 tasks, ~2.5h)**
19. 部署 + 启动脚本 (1.5h)
20. 用户指南 (1h)

**Total: 20 tasks, ~46.5h**

### Parallelizable Tasks

- Tasks 5、6、7（三个工具封装）可并行
- Tasks 8、9（意图分类 + 参数提取）部分可并行
- Tasks 16、17、18（测试）可并行

### Critical Path

1 → 2 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 18 → 19

---

**End of PRD**

*This PRD is optimized for taskmaster AI task generation. All requirements include task breakdown hints, complexity estimates, and dependency mapping.*
