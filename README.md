# DataAnalysis-Agent

飞书自然语言数据处理助手 — 一个 LLM Agent，统一三个数据 Bot 的入口，用户用自然语言描述需求，自动识别意图、提取参数、调用工具、返回结果。

## 解决的问题

三个独立 Bot（[ReelClean-bot](../ReelClean-bot) / [Prediction-Bot](../Prediction-Bot) / [feishu-bot](../feishu-bot)）各有严格参数格式要求，用户需要记住**哪个 Bot 干什么、参数按什么顺序写**。Agent 在它们之上加了一层 LLM 驱动的自然语言理解，用户只需：

```
帮我清洗数据，总成本30万，后台消耗32.8，上一时段83.4，D8 4.4
预测明天排片，封神2:17.6%, 哪吒:8.2%，大盘42万
```

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

## 启动

```
双击 start.vbs
```

## 项目结构

```
DataAnalysis-Agent/
├── agent/
│   ├── core.py                # Agent 主循环
│   ├── llm_client.py          # DeepSeek API 封装
│   └── prompts.py             # Prompt 模板
├── tools/
│   ├── base.py                # ToolResult + ToolInterface
│   ├── reelclean_tool.py      # 影院数据清洗
│   ├── prediction_tool.py     # 影片落位预测
│   └── feishu_excel_tool.py   # 开场数据提取
├── gateway/
│   ├── ws_client.py           # 飞书 WebSocket 客户端
│   └── feishu_api.py          # 飞书 REST API
├── main.py                    # 入口
├── config.py                  # 统一配置
├── test_agent.py              # LLM 离线验证
├── start.vbs / start.ps1      # 启动脚本
├── .env                       # API key（不入 git）
├── .env.example
└── requirements.txt
```

## 依赖

```
pip install -r requirements.txt
```

| 依赖 | 用途 |
|------|------|
| `openai` | DeepSeek API（兼容 OpenAI SDK） |
| `websockets` | 飞书 WebSocket 长连接 |
| `requests` | HTTP 请求 |
| `pandas` / `openpyxl` | Excel 数据处理 |
| `playwright` | 猫眼排片数据爬取（Prediction） |
| `python-dotenv` | 环境变量管理 |

## 环境变量 (.env)

```bash
# 飞书
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx

# DeepSeek
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
DEEPSEEK_MODEL=deepseek-chat

# 可选
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=800
SESSION_TIMEOUT=600
```

## 三个 Bot 原始项目

| Bot | 路径 | 核心函数 |
|-----|------|---------|
| ReelClean | `D:\ReelClean-bot` | `auto_clean.process_data()` |
| Prediction | `D:\Prediction-Bot` | `scraper.maoyan.MaoyanClient` / `excel.generator.generate_excel()` |
| Feishu | `D:\feishu-bot` | `main.process_urls()` / `main.build_message()` |

## 离线验证

```powershell
.venv\Scripts\python test_agent.py
```

测试 DeepSeek 连通性、意图分类（5 条）、参数提取（ReelClean + Prediction）、Agent 路由流程。
