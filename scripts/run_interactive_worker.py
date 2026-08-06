"""Consume SumiTalk and Telegram jobs from the shared interactive Stream."""

import os
import signal
import sys
import threading
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

from config import EVENT_RUNTIME_ENABLED  # noqa: E402
from runtime.consumers import run_interactive_worker  # noqa: E402
from runtime.process_guard import RuntimeProcessGuard  # noqa: E402
from utils.log import get_logger, setup_logging  # noqa: E402

setup_logging()
logger = get_logger("runtime.interactive_worker")

from app import app as flask_app  # noqa: E402


def main() -> None:
    if not EVENT_RUNTIME_ENABLED:
        raise RuntimeError("interactive worker requires EVENT_RUNTIME_ENABLED=1")
    stop_event = threading.Event()

    def _stop(signum, _frame) -> None:
        logger.info("interactive worker stopping signal=%s", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    with ExitStack() as stack:
        stack.enter_context(RuntimeProcessGuard("sumitalk-consumer"))
        stack.enter_context(RuntimeProcessGuard("telegram-consumer"))
        run_interactive_worker(flask_app, stop_event)


if __name__ == "__main__":
    main()
