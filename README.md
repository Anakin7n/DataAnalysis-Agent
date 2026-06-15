# DataAnalysis-Agent

飞书自然语言数据处理助手 — 一个 LLM Agent，统一三个数据 Bot 的入口，用户用自然语言描述需求，自动识别意图、提取参数、调用工具、返回结果。

## 解决的问题

三个独立 Bot（[ReelClean-bot](../ReelClean-bot) / [Prediction-Bot](../Prediction-Bot) / [feishu-bot](../feishu-bot)）各有严格参数格式要求，用户需要记住**哪个 Bot 干什么、参数按什么顺序写**。Agent 在它们之上加了一层 LLM 驱动的自然语言理解，用户只需：

```
帮我清洗数据，总成本30万，后台消耗32.8，上一时段83.4，D8 4.4
预测明天排片，封神2:17.6%, 哪吒:8.2%，大盘42万
```

## 三个工具的输出物

Agent 本身不做数据处理——它充当路由和参数提取层，实际计算由三个 Bot 完成。

| 工具 | 输入 | 输出 |
|------|------|------|
| **地面任务分析** (ReelClean) | 3 个 Excel + 4 个参数（总成本/后台消耗/上一时段/今日新增占比） | 消耗报告 + 催场情况 + 落位预估（3 段文案）+ 2 个处理后 Excel |
| **排片占比预测** (Prediction) | 日期 + 影片及新增占比 + 大盘场次 | 预测结果总结 + 各影片（含竞品）落位占比文案 + 1 个预测 Excel |
| **分时汇报** (Feishu Excel) | 2 个 Excel 文件链接 或 直接发送 .xlsx 文件 | 目标影片未来两天排片情况汇报文案 + 跟进语（两文件配对合并） |

## 对话流程

Agent 使用多轮会话状态机，每轮最多 2 次 LLM 调用：

```
用户消息
  │
  ├─ 意图已定 → LLM 检测是否意图切换 (高置信度不同工具 → 自动重置切换)
  │
  ├─ 意图未定 → LLM 分类 (confidence < 0.7 追问，unknown 提示能力范围)
  │
  ├─ 意图已定、参数不全 → LLM 提取参数 → 缺失则追问、齐全则执行
  │
  └─ 参数齐全 → 确认消息先发出 → 后台执行工具 (60s 超时) → 结果单独推送
```

用户可以随时切换工具，Agent 会智能识别新意图并自动重置上下文。多轮对话中逐步补充参数会被记住，Session 超时（默认 10 分钟）后自动清理。

## 架构

```
飞书群聊 (WebSocket)
    │
    ▼
gateway/ws_client.py          ← WebSocket 长连接 + protobuf
    │
    ▼
agent/core.py                 ← LLM 路由器
    ├── 意图识别 (DeepSeek)
    ├── 参数提取 (DeepSeek)
    └── 多轮对话追问
    │
    ▼
tools/                        ← 三个工具的封装
    ├── reelclean_tool.py     → D:\ReelClean-bot\auto_clean.py
    ├── prediction_tool.py    → D:\Prediction-Bot\scraper + excel
    └── feishu_excel_tool.py  → D:\feishu-bot\main.py
```

> **路径依赖**：Agent 自动在父目录中查找三个 Bot（如 `D:\ReelClean-bot`）。如需自定义路径，在 `.env` 中设置 `REELCLEAN_DIR` / `PREDICTION_DIR` / `FEISHU_BOT_DIR`。

## 快速部署

### 一键安装（推荐）

项目根目录提供了 `install_all.bat`，自动完成所有安装步骤。**前提：已安装 Python 3.12+ 并勾选 "Add Python to PATH"**。

#### 1. 克隆四个仓库到同一父目录

四个项目必须在**同一父目录**下（如 `D:\`）：

```
D:\
├── DataAnalysis-Agent\    ← 本项目（LLM Agent）
├── ReelClean-bot\         ← 地面任务分析
├── Prediction-Bot\        ← 排片占比预测
└── feishu-bot\            ← 分时汇报
```

```powershell
cd D:\
git clone <DataAnalysis-Agent 仓库地址>
git clone <ReelClean-bot 仓库地址>
git clone <Prediction-Bot 仓库地址>
git clone <feishu-bot 仓库地址>
```

#### 2. 运行一键安装

```powershell
cd D:\DataAnalysis-Agent
.\install_all.bat
```

安装程序会自动完成：

| 步骤 | 内容 |
|------|------|
| 检查 Python | 验证 3.12+ 版本 |
| ReelClean-bot | 创建 venv → 安装依赖（openpyxl/requests/pandas/xlwings/lark-oapi 等） |
| Prediction-Bot | 创建 venv → 安装依赖（openpyxl/requests/playwright 等） |
| feishu-bot | 创建 venv → 安装依赖（openpyxl/requests/websockets 等） |
| DataAnalysis-Agent | 创建 venv → 安装依赖（openai/playwright/numpy 等全部 4 个项目所需） |
| Playwright 浏览器 | 安装 Chromium（~180MB，排片预测爬虫依赖） |
| 配置 .env | 生成模板，提示填入飞书 + DeepSeek 凭证 |

#### 3. 配置凭证

安装完成后，打开 `.env` 填入三个关键凭证：

```bash
FEISHU_APP_ID=cli_xxxxxxxxxxxx        # 飞书应用 App ID
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxx    # 飞书应用 App Secret
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxx      # DeepSeek API Key
```

#### 4. 启动

双击 `start.vbs`（推荐，零闪屏），或运行：

```powershell
.venv\Scripts\python main.py
```

#### 5. 三个 Bot 已同步安装，可独立运行

`install_all.bat` 为每个 Bot 创建了独立的虚拟环境并安装了各自的依赖。启动方式：

| Bot | 启动方式 | 说明 |
|-----|---------|------|
| ReelClean-bot | 双击 `D:\ReelClean-bot\start.vbs` | 地面任务分析独立服务 |
| Prediction-Bot | 双击 `D:\Prediction-Bot\start.vbs` | 排片预测独立服务 |
| feishu-bot | 双击 `D:\feishu-bot\start.vbs` | 分时汇报独立服务 |

> ⚠️ **注意**：每个 Bot 独立运行时需要各自的 `.env` 文件中配置 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET`（与 Agent 的凭证相同）。安装脚本已自动创建 `.env` 模板，用记事本打开填入凭证即可。

### 手动安装

如果不使用一键安装脚本，可按以下步骤手动设置：

## 环境准备

### 1. Python 版本

需要 **Python 3.12+**。

### 2. 创建虚拟环境

```powershell
python -m venv .venv
```

### 3. 安装依赖

```powershell
.venv\Scripts\pip install -r requirements.txt
```

### 4. 安装 Playwright 浏览器

Prediction 工具使用 Playwright 爬取猫眼排片数据，需要额外安装浏览器二进制：

```powershell
.venv\Scripts\playwright install chromium
```

### 5. 配置环境变量

复制 `.env.example` 为 `.env`，填入实际凭证：

```bash
# 飞书
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx

# DeepSeek
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# LLM 参数
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=800
LLM_TIMEOUT=15

# Session 超时（秒）
SESSION_TIMEOUT=600

# 日志级别 (DEBUG / INFO / WARNING / ERROR)
LOG_LEVEL=INFO
```

### 6. 安装 Excel（地面任务分析需要）

地面任务分析使用 `xlwings` 写入 Excel 公式，要求运行机器上**安装了 Microsoft Excel**。排片占比预测和分时汇报不需要 Excel。

## 启动

```
双击 start.vbs
```

`start.vbs` 会启动 `start.ps1`，自动完成：检查 `.env` 是否存在 → 检测 `.venv` 虚拟环境 → 启动 `main.py`。

也可以用 `start.bat`（自动检测 Windows Terminal 以获得更好的终端体验），或直接运行：

```powershell
.venv\Scripts\python main.py
```

## 项目结构

```
DataAnalysis-Agent/
├── agent/
│   ├── core.py                # Agent 主循环（多轮对话状态机）
│   ├── llm_client.py          # DeepSeek API 封装
│   └── prompts.py             # Prompt 模板（意图分类 + 3 个参数提取）
├── tools/
│   ├── base.py                # ToolResult + ToolInterface
│   ├── reelclean_tool.py      # 地面任务分析（消耗/催场/落位）
│   ├── prediction_tool.py     # 排片占比预测
│   └── feishu_excel_tool.py   # 分时汇报
├── gateway/
│   ├── ws_client.py           # 飞书 WebSocket 客户端
│   └── feishu_api.py          # 飞书 REST API
├── main.py                    # 入口
├── config.py                  # 统一配置
├── test_agent.py              # LLM 离线验证
├── start.vbs / start.ps1 / start.bat  # 启动脚本
├── .env                       # API key（不入 git）
├── .env.example
└── requirements.txt
```

## 依赖

| 依赖 | 用途 |
|------|------|
| `openai` | DeepSeek API（兼容 OpenAI SDK） |
| `websockets` | 飞书 WebSocket 长连接 |
| `requests` | HTTP 请求 |
| `pandas` / `openpyxl` | Excel 数据处理 |
| `xlwings` | Excel 公式写入（地面任务分析，需安装 Excel） |
| `numpy` | 数值计算（地面任务分析） |
| `playwright` | 猫眼排片数据爬取（排片占比预测） |
| `python-dotenv` | 环境变量管理 |

## 三个 Bot 原始项目

| Bot | 路径 | 核心函数 |
|-----|------|---------|
| ReelClean | `D:\ReelClean-bot` | `auto_clean.process_data()` |
| Prediction | `D:\Prediction-Bot` | `scraper.maoyan.MaoyanClient` / `excel.generator.generate_excel()` |
| Feishu | `D:\feishu-bot` | `main.process_urls()` / `main._parse_single_file()` / `main.build_message()` |

## 离线验证

```powershell
.venv\Scripts\python test_agent.py
```

测试 DeepSeek 连通性、意图分类（5 条）、参数提取（ReelClean + Prediction）、Agent 路由流程。

## 故障排查

| 现象 | 可能原因 | 排查方向 |
|------|---------|---------|
| LLM 调用失败 | API Key 未配或余额不足 | 检查 `.env` 中 `DEEPSEEK_API_KEY`；运行 `test_agent.py` 验证连通性 |
| 飞书 WebSocket 连不上 | App ID/Secret 错误 | 检查飞书应用是否已发布并开通了"机器人"和"事件订阅"能力 |
| 地面任务分析报"文件识别失败" | 文件名不匹配 | 3 个文件需命名为：`<影片名>-落.xlsx`、`影城明细-<影片名>.xlsx` 及第 3 个文件 |
| 排片占比预测报"未获取到排片数据" | 影片名与猫眼不一致 | 尝试使用与猫眼一致的完整片名，或检查日期是否在可查询范围内 |
| 分时汇报报"未找到数据 Sheet" | Excel 结构不符 | 文件需包含"综拓开场数据基础模板2"或含"综拓""开场数据"关键词的 Sheet |
| `xlwings` 报错 | 机器未安装 Excel | 地面任务分析依赖 Excel 应用程序，需在装有 Excel 的 Windows 上运行 |
| `playwright` 报"Executable doesn't exist" | 浏览器未安装 | 运行 `.venv\Scripts\playwright install chromium` |
