# DataAnalysis-Agent

飞书群聊里的数据处理助手。用户在群里发消息（自然语言 + Excel 文件），Agent 自动识别意图、提取参数、执行分析、回复结果。目前支持三个场景：

- **地面任务分析** — 上传 3 个 Excel（落位表 `<影片名>-落.xlsx`、影城明细 `影城明细-<影片名>.xlsx`、任务明细表） + 4 个参数（总成本/后台消耗/上一时段/今日新增占比）。自动完成数据清洗、跨表关联、多条件筛选聚合、行列公式重算，输出消耗报告、催场情况、落位预估三份文案，并回传处理后的 Excel
- **排片占比预测** — 输入日期、影片及今日新增占比、大盘场次。自动从猫眼实时抓取排片数据（含未上映电影）、模糊匹配影片名（简称"两朵云"→全名"我看见两朵一样的云"），生成含 Excel 公式建模的落位占比预测表。支持混乱的输入格式（书名号《》、句号、混合分隔符等自动预处理）
- **分时汇报** — 发送 2 个固定时间段的排片数据 Excel 链接（或直接发文件）。自动下载解析、Sheet 定位、配对合并，提取场次数/劣势影城数/排片占比等指标，生成汇报文案和跟进语

所有工具共享同一个 LLM 自然语言入口——自动识别意图路由到对应工具、智能提取并标准化参数（容许多种表达方式）、缺失参数时逐项追问且上下文不丢失、模糊输入自动纠正匹配。

## 为什么做这个

影片发行部门由于行业特性，存在多项不分节假日的日常数据任务，单项耗时 10 min+。存在效率低、非工位场景操作不便、人工处理易出错三大痛点。

**V1 — 自动化脚本**：解决效率与正确率问题。任务模板固定，用 Python 自动完成数据清洗和文案输出。10min → <1min，准确率理论上 100%。

**V2 — 飞书 Bot**：解决非工位场景不便。把脚本分别接入飞书机器人，手机发消息即可远程触发。[分时汇报](https://github.com/Anakin7n/feishu-bot)、[地面任务分析](https://github.com/Anakin7n/ReelClean-bot)、[排片占比预测](https://github.com/Anakin7n/Prediction-Bot)——三个 Bot 各自独立运行。

**V3 — LLM Agent（当前版本）**：Bot 分享给团队后，参数格式问题频发——"大盘42万"还是"420000"？"封神2"还是"封神第二部：战火西岐"？三个 Bot 之间还得切来切去。接入 LLM 做自然语言理解，用一个入口实现意图自动路由、参数模糊匹配、缺参追问、格式归一。从"人适应机器"变成"机器适应人"。

## 相较于独立 Bot ——解决的问题

三个独立数据 Bot——[分时汇报](https://github.com/Anakin7n/feishu-bot)、[地面任务分析](https://github.com/Anakin7n/ReelClean-bot)、[排片占比预测](https://github.com/Anakin7n/Prediction-Bot)——功能各异、参数繁杂。用户需要记住**哪个工具干什么、参数什么格式怎么排**——

- "2万"还是"20000"？"32.8"还是"32.8%"？格式错一处就失败
- "封神2"不行，得写"封神第二部：战火西岐"——影片名必须和猫眼逐字一致。像熊出没这种每年一部的系列，只说"熊出没"压根不知道是哪部。机械式的if-else模糊匹配可短暂解决问题，但本质上换汤不换药，代码臃肿
- 参数不全时直接报错，没有上下文记忆，只能从头输入参数

Agent 用 LLM 加了一层自然语言理解：自动识别意图路由工具、"30万"→300000、缩写"封神2""熊出没"→匹配猫眼全名（同系列优先匹配预测日期附近上映的版本）、缺参数逐项追问。

## 三个工具的输出物

| 工具 | 输入 | 输出 |
|------|------|------|
| **地面任务分析** | 3 个 Excel + 4 个参数（总成本/后台消耗/上一时段/今日新增占比） | 3 段文案（消耗报告/催场情况/落位预估）+ 2 个处理后 Excel |
| **排片占比预测** | 日期 + 影片及新增占比 + 大盘场次 | 预测结果总结 + 预测 Excel |
| **分时汇报** | 2 个 Excel 文件链接 或 直接发送 .xlsx 文件 | 排片情况汇报文案 + 跟进语 |

## 对话流程

```
用户消息
  │
  ├─ 意图未定 → LLM 分类 → 识别工具 → 检查参数
  ├─ 意图已定、参数不全 → LLM 提取参数 → 追问缺失项
  ├─ 意图已定、参数齐全 → 确认 → 后台执行 → 结果推送
  └─ 意图切换 → 高置信度不同工具 → 自动重置上下文
```

每轮最多 2 次 LLM 调用。Session 超时 10 分钟自动清理。

## 架构

```
飞书群聊 (WebSocket)
    │
    ▼
gateway/        ← WebSocket 长连接 + 飞书 REST API
    │
    ▼
agent/          ← LLM 路由器（意图识别 + 参数提取 + 多轮追问）
    │
    ▼
tools/          ← 三个工具（核心逻辑全部内嵌）
    ├── reelclean/      地面任务分析（Excel 合并 + 落位计算 + 文案）
    ├── prediction/     排片占比预测（猫眼爬虫 + Excel 生成 + 文案）
    └── feishu_excel/   分时汇报（Excel 解析 + 文案生成）
```

## 快速部署

### 一键安装（推荐）

项目根目录提供了 `install_all.bat`，自动完成全部安装步骤。**前提：已安装 Python 3.12+ 并勾选"Add Python to PATH"**。

```powershell
git clone <仓库地址>
cd DataAnalysis-Agent
.\install_all.bat
```

安装程序会自动完成：

| 步骤 | 内容 |
|------|------|
| 检查 Python | 验证 3.12+ 版本 |
| 创建虚拟环境 | `.venv` |
| 安装 pip 依赖 | openai / websockets / pandas / openpyxl / xlwings / playwright 等 |
| Playwright 浏览器 | 安装 Chromium（~180MB，排片预测爬虫依赖） |
| 配置 .env | 生成模板，提示填入飞书 + DeepSeek 凭证 |

安装完成后，打开 `.env` 填入三个关键凭证即可启动：

```bash
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxx
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxx
```

```powershell
.venv\Scripts\python main.py   # 或双击 start.vbs（无控制台窗口）
```

### 手动安装

```powershell
git clone <仓库地址>
cd DataAnalysis-Agent

python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install chromium

# 复制 .env.example 为 .env，填入飞书 + DeepSeek 凭证
.venv\Scripts\python main.py
```

## 飞书应用配置

1. [飞书开放平台](https://open.feishu.cn) → 创建应用 → 开启**机器人**能力
2. **权限管理**中添加：

   | 权限 | 说明 |
   |------|------|
   | `im:message` | 获取消息 |
   | `im:message.group_msg` | 获取群组中所有消息（敏感权限，需审核） |
   | `im:message.p2p_msg:readonly` | 读取用户发给机器人的单聊消息 |
   | `im:message:send_as_bot` | 以应用的身份发消息 |
   | `im:resource` | 获取与上传图片或文件资源 |

3. **事件订阅**添加 `im.message.receive_v1`（WebSocket 模式无需回调地址）
4. 发布应用并等待管理员审核通过
5. 获取 App ID / App Secret 填入 `.env`

## 项目结构

```
DataAnalysis-Agent/
├── agent/
│   ├── core.py                # Agent 主循环
│   ├── llm_client.py          # DeepSeek API 封装
│   └── prompts.py             # Prompt 模板
├── tools/
│   ├── base.py                # ToolResult + ToolInterface
│   ├── reelclean_tool.py      # 地面任务分析 wrapper
│   ├── prediction_tool.py     # 排片占比预测 wrapper
│   ├── feishu_excel_tool.py   # 分时汇报 wrapper
│   ├── reelclean/
│   │   └── auto_clean.py      # 核心：3 Excel 合并 + 落位 + 文案
│   ├── prediction/
│   │   ├── maoyan.py          # 猫眼排片客户端
│   │   ├── generator.py       # 预测 Excel 生成
│   │   └── cards.py           # 文案模板
│   └── feishu_excel/
│       ├── parser.py          # Excel 文件名/Sheet/数据解析
│       └── messages.py        # 分时汇报文案生成
├── gateway/
│   ├── ws_client.py           # 飞书 WebSocket
│   └── feishu_api.py          # 飞书 REST API
├── main.py                    # 入口
├── config.py                  # 统一配置
├── test_agent.py              # 离线冒烟测试
├── test_prediction_extract.py # 预测参数提取回归测试（20 用例）
├── start.vbs / start.ps1 / start.bat
├── .env.example
└── requirements.txt
```

## 依赖

| 包 | 用途 |
|---|---|
| `openai` | DeepSeek API |
| `websockets` | 飞书长连接 |
| `requests` | HTTP |
| `pandas` / `openpyxl` / `numpy` | Excel 数据处理 |
| `xlwings` | Excel 公式写入（需安装 Microsoft Excel） |
| `playwright` | 猫眼排片爬虫 |
| `python-dotenv` | 环境变量 |

## 测试

```powershell
# 基础冒烟测试（LLM 连通性 + 意图分类 + 参数提取 + Agent 路由）
.venv\Scripts\python test_agent.py

# 预测参数提取回归测试（20 用例覆盖 6 类格式场景）
.venv\Scripts\python test_prediction_extract.py
```

## 故障排查

| 现象 | 原因 | 排查 |
|------|------|------|
| LLM 调用失败 | API Key 无效或欠费 | `test_agent.py` 验证连通性 |
| WebSocket 连不上 | 飞书凭证错误 | 检查应用是否已发布、是否开通机器人能力 |
| 地面任务分析报"文件识别失败" | 文件名不匹配 | 需命名：`<影片名>-落.xlsx`、`影城明细-<影片名>.xlsx` + 第 3 个文件 |
| 排片预测报"未获取到排片数据" | 影名缩写未能匹配 | 改用猫眼完整片名重试（如"我看见两朵一样的云"而非"两朵云"） |
| 分时汇报报"未找到数据 Sheet" | Excel 结构不符 | 文件需含"综拓开场数据基础模板2"等 Sheet |
| `xlwings` 报错 | 未安装 Excel | 地面任务分析需本机安装 Microsoft Excel |
| `playwright` 报"Executable doesn't exist" | 浏览器未安装 | 运行 `playwright install chromium` |
