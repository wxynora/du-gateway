"""R2 storage helpers for the shared cyber home state."""
from __future__ import annotations

from contextlib import contextmanager
import copy
import threading
from typing import Any, Callable, Optional

from config import DATA_DIR
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

try:
    import fcntl
except Exception:  # pragma: no cover - production Linux and local macOS provide fcntl.
    fcntl = None

R2_KEY_PIXEL_HOME_STATE = "global/pixel_home_state.json"

_pixel_home_write_lock = threading.Lock()
_pixel_home_lock_path = DATA_DIR / "pixel_home_state.lock"
logger = get_logger(__name__)


@contextmanager
def _pixel_home_write_guard():
    with _pixel_home_write_lock:
        if fcntl is None:
            yield
            return
        _pixel_home_lock_path.parent.mkdir(parents=True, exist_ok=True)
        with _pixel_home_lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _r2_store():
    from storage import r2_store

    return r2_store


def _s3_client():
    return _r2_store()._s3_client()


def _read_json(client, key: str) -> Optional[Any]:
    return _r2_store()._read_json(client, key)


def _write_json(client, key: str, data: Any):
    return _r2_store()._write_json(client, key, data)


def get_pixel_home_state() -> Optional[dict]:
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, R2_KEY_PIXEL_HOME_STATE)
    return data if isinstance(data, dict) else None


def save_pixel_home_state(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    client = _s3_client()
    if not client:
        return False
    payload = dict(data)
    payload["updated_at"] = str(payload.get("updated_at") or "").strip() or now_beijing_iso()
    with _pixel_home_write_guard():
        try:
            current = _read_json(client, R2_KEY_PIXEL_HOME_STATE)
            if isinstance(current, dict):
                if "du_body_state" in current:
                    payload["du_body_state"] = current.get("du_body_state")
                else:
                    payload.pop("du_body_state", None)
                if "du_body_delta_applied_ids" in current:
                    payload["du_body_delta_applied_ids"] = current.get("du_body_delta_applied_ids")
                else:
                    payload.pop("du_body_delta_applied_ids", None)
            _write_json(client, R2_KEY_PIXEL_HOME_STATE, payload)
            return True
        except Exception as e:
            logger.error("save_pixel_home_state failed error=%s", e, exc_info=True)
            return False


def update_pixel_home_state(patch: dict) -> Optional[dict]:
    if not isinstance(patch, dict):
        return None
    client = _s3_client()
    if not client:
        return None
    with _pixel_home_write_guard():
        try:
            current = _read_json(client, R2_KEY_PIXEL_HOME_STATE)
            if not isinstance(current, dict):
                current = {}
            current.update(patch)
            current["updated_at"] = now_beijing_iso()
            _write_json(client, R2_KEY_PIXEL_HOME_STATE, current)
            return current
        except Exception as e:
            logger.error("update_pixel_home_state failed error=%s", e, exc_info=True)
            return None


def mutate_pixel_home_state(mutator: Callable[[dict], dict]) -> Optional[dict]:
    """Read, mutate and write the shared state under thread and process locks."""
    if not callable(mutator):
        return None
    client = _s3_client()
    if not client:
        return None
    with _pixel_home_write_guard():
        try:
            current = _read_json(client, R2_KEY_PIXEL_HOME_STATE)
            if not isinstance(current, dict):
                current = {}
            original = copy.deepcopy(current)
            next_state = mutator(dict(current))
            if not isinstance(next_state, dict):
                return None
            next_state["updated_at"] = str(next_state.get("updated_at") or "").strip() or now_beijing_iso()
            if next_state != original:
                _write_json(client, R2_KEY_PIXEL_HOME_STATE, next_state)
            return next_state
        except Exception as e:
            logger.error("mutate_pixel_home_state failed error=%s", e, exc_info=True)
            return None
