"""Publish transactional SQLite outbox events to Redis Streams."""

import os
import signal
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from runtime.dispatcher import run_dispatcher  # noqa: E402
from runtime.process_guard import RuntimeProcessGuard  # noqa: E402
from utils.log import get_logger, setup_logging  # noqa: E402

setup_logging()
logger = get_logger("runtime.event_dispatcher")


def main() -> None:
    stop_event = threading.Event()

    def _stop(signum, _frame) -> None:
        logger.info("event dispatcher stopping signal=%s", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    with RuntimeProcessGuard("event-dispatcher"):
        run_dispatcher(stop_event)


if __name__ == "__main__":
    main()
