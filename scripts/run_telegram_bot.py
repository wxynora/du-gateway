"""
Telegram Bot 独立进程：长轮询收消息 → 调网关 chat → 回复发回。
在项目根目录执行：python scripts/run_telegram_bot.py
需在 .env 中配置 TELEGRAM_BOT_TOKEN、TELEGRAM_GATEWAY_URL（网关需已启动）。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# 先加载 .env（config 会读）
from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=False)

from config import DATA_DIR
from utils.log import setup_logging

setup_logging()

from services.telegram_bot import run_polling


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_polling()
