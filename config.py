"""
统一配置 — 所有环境变量和全局常量集中管理。
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── 飞书 ──
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_DOMAIN = "https://open.feishu.cn"
WS_ENDPOINT_URI = "/callback/ws/endpoint"

# ── LLM (DeepSeek) ──
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "800"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "15"))

# ── 猫眼 ──
MAOYAN_DASHBOARD_URL = "https://piaofang.maoyan.com/dashboard-ajax"

# ── Session ──
SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "600"))  # 10 分钟

# ── 日志 ──
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = Path(__file__).parent / "agent.log"
