from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import TextIO

from config import DATA_DIR


class RuntimeAlreadyRunning(RuntimeError):
    pass


class RuntimeProcessGuard:
    def __init__(self, name: str, *, lock_dir: Path | None = None) -> None:
        safe_name = "".join(char if char.isalnum() or char in "-_" else "_" for char in name)
        if not safe_name:
            raise ValueError("process guard name is required")
        self.path = Path(lock_dir or (DATA_DIR / "event_runtime_locks")) / f"{safe_name}.lock"
        self._handle: TextIO | None = None

    def acquire(self) -> "RuntimeProcessGuard":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise RuntimeAlreadyRunning(f"runtime process already owns {self.path.name}") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        self._handle = handle
        return self

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self) -> "RuntimeProcessGuard":
        return self.acquire()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()
