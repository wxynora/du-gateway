"""
SumiTalk chat queue worker.

MiniApp chat routes only persist a job and return job_id quickly. This process
claims queued jobs and runs the normal gateway chat path outside gunicorn's
request lifecycle, so long replies are not lost when web workers recycle.

Run from the repo root:
    python scripts/run_sumitalk_chat_worker.py
"""
import os
import signal
import sys
import threading
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
    EVENT_RUNTIME_ENABLED,
    SUMITALK_CHAT_QUEUE_STALE_SECONDS,
    SUMITALK_CHAT_WORKER_IDLE_SECONDS,
)
from runtime.process_guard import RuntimeProcessGuard  # noqa: E402
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


def _run_worker_loop(stop_event: threading.Event) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    idle = max(float(SUMITALK_CHAT_WORKER_IDLE_SECONDS or 0.5), 0.1)
    stale_after = max(float(SUMITALK_CHAT_QUEUE_STALE_SECONDS or 300), 30.0)
    logger.info(
        "SumiTalk chat queue worker 已启动 idle=%.1f stale_after=%.1f backend_retry=0 stats=%s",
        idle,
        stale_after,
        sumitalk_chat_queue_stats(),
    )

    while not stop_event.is_set():
        item = claim_next_sumitalk_chat_job(
            stale_after_seconds=stale_after,
        )
        if item is None:
            stop_event.wait(idle)
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


def run_worker_loop(stop_event: threading.Event | None = None) -> None:
    if EVENT_RUNTIME_ENABLED:
        raise RuntimeError(
            "legacy SumiTalk polling worker refuses to start when EVENT_RUNTIME_ENABLED=1"
        )
    stop = stop_event or threading.Event()
    with RuntimeProcessGuard("sumitalk-consumer"):
        _run_worker_loop(stop)


def main() -> None:
    stop_event = threading.Event()

    def _stop(signum, _frame) -> None:
        logger.info("SumiTalk chat queue worker stopping signal=%s", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    run_worker_loop(stop_event)


if __name__ == "__main__":
    main()
