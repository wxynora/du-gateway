"""
Telegram Webhook 队列 worker（常驻进程）。

Webhook 入口仍挂在网关 /telegram/webhook，但 web worker 只写 SQLite 队列。
本进程负责顺序消费 update，并持有 TG 输入聚合 buffer/timer，避免 gunicorn worker
按 max-requests 回收时把 15 秒聚合状态丢掉。

在项目根目录执行：
    python scripts/run_telegram_webhook_worker.py
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from config import (  # noqa: E402
    DATA_DIR,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_WEBHOOK_QUEUE_MAX_ATTEMPTS,
    TELEGRAM_WEBHOOK_QUEUE_STALE_SECONDS,
    TELEGRAM_WEBHOOK_WORKER_IDLE_SECONDS,
)
from utils.log import get_logger, setup_logging  # noqa: E402

setup_logging()
logger = get_logger("services.telegram_webhook_worker")

from services.telegram_bot import handle_telegram_update, init_telegram_bot_runtime  # noqa: E402
from services.telegram_update_queue import (  # noqa: E402
    ack_update,
    claim_next_update,
    fail_update,
    queue_stats,
    summarize_update,
)


def _resolve_bot_token(bot_kind: str) -> str:
    if bot_kind != "main":
        return ""
    return (TELEGRAM_BOT_TOKEN or "").strip()


def run_worker_loop() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    init_telegram_bot_runtime()
    idle = max(float(TELEGRAM_WEBHOOK_WORKER_IDLE_SECONDS or 0.5), 0.1)
    stale_after = max(float(TELEGRAM_WEBHOOK_QUEUE_STALE_SECONDS or 300), 30.0)
    max_attempts = max(int(TELEGRAM_WEBHOOK_QUEUE_MAX_ATTEMPTS or 8), 1)
    logger.info(
        "Telegram webhook queue worker 已启动 idle=%.1f stale_after=%.1f max_attempts=%s stats=%s",
        idle,
        stale_after,
        max_attempts,
        queue_stats(),
    )

    while True:
        item = claim_next_update(
            stale_after_seconds=stale_after,
            max_attempts=max_attempts,
        )
        if item is None:
            time.sleep(idle)
            continue

        if item.bot_kind != "main":
            logger.info(
                "Telegram webhook queue worker 丢弃旧文游/非主 Bot 队列项 queued_id=%s bot=%s key=%s",
                item.id,
                item.bot_kind,
                item.update_key,
            )
            ack_update(item.id)
            continue

        token = _resolve_bot_token(item.bot_kind)
        if not token:
            logger.warning(
                "Telegram webhook queue worker 缺 bot token，回队列 queued_id=%s bot=%s attempts=%s key=%s",
                item.id,
                item.bot_kind,
                item.attempts,
                item.update_key,
            )
            fail_update(item.id, f"missing {item.bot_kind} bot token", max_attempts=max_attempts)
            time.sleep(min(idle * 2, 5.0))
            continue

        try:
            logger.info(
                "Telegram webhook queue worker 消费 queued_id=%s bot=%s attempts=%s key=%s %s",
                item.id,
                item.bot_kind,
                item.attempts,
                item.update_key,
                summarize_update(item.update),
            )
            handle_telegram_update(item.update, bot_token=token)
            ack_update(item.id)
        except Exception as e:
            logger.exception(
                "Telegram webhook queue worker 处理失败 queued_id=%s bot=%s attempts=%s key=%s: %s",
                item.id,
                item.bot_kind,
                item.attempts,
                item.update_key,
                e,
            )
            fail_update(item.id, str(e), max_attempts=max_attempts)


if __name__ == "__main__":
    run_worker_loop()
