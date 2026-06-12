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

# ── 外部 Bot 路径（优先 .env，否则自动识别同级目录）──
_PROJECT_DIR = Path(__file__).parent
_PARENT_DIR = _PROJECT_DIR.parent


def _resolve_bot_dir(env_key: str, default_name: str) -> Path:
    """优先读 .env，否则在本项目的同级目录中查找。"""
    env_val = os.getenv(env_key)
    if env_val:
        return Path(env_val)
    return _PARENT_DIR / default_name


REELCLEAN_DIR = _resolve_bot_dir("REELCLEAN_DIR", "ReelClean-bot")
PREDICTION_DIR = _resolve_bot_dir("PREDICTION_DIR", "Prediction-Bot")
FEISHU_BOT_DIR = _resolve_bot_dir("FEISHU_BOT_DIR", "feishu-bot")

# ── Session ──
SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "600"))  # 10 分钟

# ── 日志 ──
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = _PROJECT_DIR / "agent.log"
