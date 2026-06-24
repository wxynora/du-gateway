"""
SumiTalk chat queue worker.

MiniApp chat routes only persist a job and return job_id quickly. This process
claims queued jobs and runs the normal gateway chat path outside gunicorn's
request lifecycle, so long replies are not lost when web workers recycle.

Run from the repo root:
    python scripts/run_sumitalk_chat_worker.py
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv:
    load_dotenv(ROOT / ".env", override=False)

from config import (  # noqa: E402
    DATA_DIR,
    SUMITALK_CHAT_QUEUE_STALE_SECONDS,
    SUMITALK_CHAT_WORKER_IDLE_SECONDS,
)
from utils.log import get_logger, setup_logging  # noqa: E402

setup_logging()
logger = get_logger("services.sumitalk_chat_worker")

from app import app as flask_app  # noqa: E402
from services.sumitalk_chat_queue import (  # noqa: E402
    ack_sumitalk_chat_queue_item,
    claim_next_sumitalk_chat_job,
    fail_sumitalk_chat_queue_item,
    is_sumitalk_chat_job_cancelled,
    run_sumitalk_chat_job,
    set_sumitalk_chat_job_stage,
    sumitalk_chat_queue_stats,
)


def run_worker_loop() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    idle = max(float(SUMITALK_CHAT_WORKER_IDLE_SECONDS or 0.5), 0.1)
    stale_after = max(float(SUMITALK_CHAT_QUEUE_STALE_SECONDS or 300), 30.0)
    logger.info(
        "SumiTalk chat queue worker 已启动 idle=%.1f stale_after=%.1f backend_retry=0 stats=%s",
        idle,
        stale_after,
        sumitalk_chat_queue_stats(),
    )

    while True:
        item = claim_next_sumitalk_chat_job(
            stale_after_seconds=stale_after,
        )
        if item is None:
            time.sleep(idle)
            continue

        if is_sumitalk_chat_job_cancelled(item.job_id):
            logger.info(
                "SumiTalk chat queue worker 跳过已取消任务 queue_id=%s job_id=%s attempts=%s",
                item.id,
                item.job_id,
                item.attempts,
            )
            ack_sumitalk_chat_queue_item(item.id, lease_token=item.lease_token)
            continue

        try:
            logger.info(
                "SumiTalk chat queue worker 消费 queue_id=%s job_id=%s attempts=%s request_key=%s",
                item.id,
                item.job_id,
                item.attempts,
                item.request_key,
            )
            status = run_sumitalk_chat_job(
                flask_app,
                item.job_id,
                item.payload,
                queue_id=item.id,
                lease_token=item.lease_token,
            )
            acked = ack_sumitalk_chat_queue_item(item.id, lease_token=item.lease_token)
            logger.info(
                "SumiTalk chat queue worker 完成 queue_id=%s job_id=%s status=%s acked=%s stats=%s",
                item.id,
                item.job_id,
                status,
                acked,
                sumitalk_chat_queue_stats(),
            )
        except Exception as e:
            logger.exception(
                "SumiTalk chat queue worker 处理失败 queue_id=%s job_id=%s attempts=%s: %s",
                item.id,
                item.job_id,
                item.attempts,
                e,
            )
            try:
                set_sumitalk_chat_job_stage(item.job_id, "queue_worker_exception", error=e)
            except Exception:
                pass
            fail_sumitalk_chat_queue_item(
                item.id,
                str(e),
                lease_token=item.lease_token,
            )


if __name__ == "__main__":
    run_worker_loop()
