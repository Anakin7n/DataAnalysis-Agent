"""
DataAnalysis-Agent — 飞书自然语言数据处理助手。
一个飞书 Bot，统一入口，LLM 理解需求 → 自动路由到三个工具。

启动: python main.py
"""
import logging
import sys
from pathlib import Path

from config import FEISHU_APP_ID, FEISHU_APP_SECRET, LOG_LEVEL, LOG_FILE
from agent.core import DataAnalysisAgent
from gateway.ws_client import FeishuWsClient

# ── 日志 ──
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

log = logging.getLogger("main")


def main():
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        log.error("请先在 .env 中配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        sys.exit(1)

    log.info("=" * 50)
    log.info("DataAnalysis-Agent 启动中...")
    log.info(f"飞书 App ID: {FEISHU_APP_ID[:10]}...")
    log.info("工具: 地面任务分析 | 排片占比预测 | 分时汇报")
    log.info("=" * 50)

    agent = DataAnalysisAgent()
    ws = FeishuWsClient(agent)
    ws.start()


if __name__ == "__main__":
    main()
