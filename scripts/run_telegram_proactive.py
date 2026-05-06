"""
Telegram 主动调度器（常驻进程）。

在项目根目录执行：python scripts/run_telegram_proactive.py

依赖：
- 网关已启动（本机或服务器）
- .env 已配置 TELEGRAM_BOT_TOKEN（用于发消息）
- .env 已配置 TELEGRAM_GATEWAY_URL（用于调网关）
- 主动消息：.env 已配置 TELEGRAM_PROACTIVE_ENABLED=1 和 TELEGRAM_PROACTIVE_TARGET_USER_ID
- 日历闹钟：.env 已配置 MINIAPP_SCHEDULE_RUNTIME_ENABLED=1 和 TELEGRAM_PROACTIVE_TARGET_USER_ID
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from config import DATA_DIR
from utils.log import setup_logging

setup_logging()

from services.telegram_proactive import run_scheduler_loop


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_scheduler_loop()

