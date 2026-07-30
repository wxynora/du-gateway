from __future__ import annotations

import json
import os
import re
import secrets
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

try:
    import fcntl
except Exception:  # pragma: no cover - target Linux/macOS hosts provide fcntl.
    fcntl = None

from config import DATA_DIR


CEDARECO_UPSTREAM_URL = os.environ.get(
    "CEDARECO_UPSTREAM_URL",
    "http://127.0.0.1:8765",
).strip().rstrip("/")
CEDARECO_SESSION_FILE = Path(
    os.environ.get(
        "CEDARECO_SESSION_FILE",
        str(DATA_DIR / "cedareco_app_session.json"),
    )
).expanduser()
CEDARECO_POND_NAME = os.environ.get("CEDARECO_POND_NAME", "瓶中生态").strip() or "瓶中生态"

_HUMAN_KEY_RE = re.compile(r"^[a-f0-9]{32}$")
_STATE_LOCK = threading.RLock()


class CedarEcoBridgeError(RuntimeError):
    pass


@contextmanager
def _session_lock():
    with _STATE_LOCK:
        CEDARECO_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        lock_path = CEDARECO_SESSION_FILE.with_suffix(CEDARECO_SESSION_FILE.suffix + ".lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            try:
                lock_path.chmod(0o600)
            except OSError:
                pass
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_session() -> dict[str, Any] | None:
    try:
        raw = json.loads(CEDARECO_SESSION_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    human_key = str(raw.get("human_key") or "").strip()
    if not _HUMAN_KEY_RE.fullmatch(human_key):
        return None
    return raw


def _write_session(state: dict[str, Any]) -> None:
    CEDARECO_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = CEDARECO_SESSION_FILE.with_suffix(CEDARECO_SESSION_FILE.suffix + ".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, CEDARECO_SESSION_FILE)


def _read_upstream_state() -> dict[str, Any] | None:
    try:
        response = requests.get(f"{CEDARECO_UPSTREAM_URL}/api/state", timeout=0.8)
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None
    if response.status_code >= 400 or not isinstance(payload, dict) or not payload.get("ok"):
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def _populated_species_count(state: dict[str, Any]) -> int:
    total = 0
    groups = state.get("populations")
    if not isinstance(groups, list):
        return total
    for group in groups:
        if not isinstance(group, dict):
            continue
        species = group.get("species")
        if not isinstance(species, list):
            continue
        for item in species:
            if not isinstance(item, dict):
                continue
            count = item.get("count")
            if isinstance(count, (int, float)) and count > 0:
                total += 1
    return total


def session_status() -> dict[str, Any]:
    session = _read_session()
    state = _read_upstream_state()
    return {
        "ok": True,
        "configured": session is not None,
        "running": state is not None,
        "pond_name": CEDARECO_POND_NAME,
        "day": int((state or {}).get("day") or 0),
        "season": str((state or {}).get("season") or "").strip(),
        "score": int((state or {}).get("score") or 0),
        "species_count": _populated_species_count(state or {}),
    }


def public_session(state: dict[str, Any]) -> dict[str, Any]:
    human_key = str(state.get("human_key") or "").strip()
    if not _HUMAN_KEY_RE.fullmatch(human_key):
        raise CedarEcoBridgeError("瓶中生态观察窗记录已损坏。")
    return {
        "ok": True,
        "configured": True,
        "pond_name": CEDARECO_POND_NAME,
        "url": f"/cedareco/ui/{human_key}/",
    }


def ensure_session() -> dict[str, Any]:
    with _session_lock():
        state = _read_session()
        if _read_upstream_state() is None:
            raise CedarEcoBridgeError("瓶中生态服务还没启动。")
        if state is not None:
            return state
        state = {
            "human_key": secrets.token_hex(16),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_session(state)
        return state


def is_valid_human_key(value: object) -> bool:
    candidate = str(value or "").strip()
    state = _read_session()
    expected = str((state or {}).get("human_key") or "").strip()
    return (
        _HUMAN_KEY_RE.fullmatch(candidate) is not None
        and _HUMAN_KEY_RE.fullmatch(expected) is not None
        and secrets.compare_digest(candidate, expected)
    )


def run_command(command: object) -> dict[str, Any]:
    text = str(command or "").strip()
    if not text:
        raise CedarEcoBridgeError("瓶中生态指令不能为空；不知道做什么时先用 help。")
    ensure_session()
    try:
        response = requests.post(
            f"{CEDARECO_UPSTREAM_URL}/api/command",
            json={"command": text},
            timeout=30,
        )
        payload = response.json()
    except requests.RequestException as exc:
        raise CedarEcoBridgeError("瓶中生态服务还没启动。") from exc
    except ValueError as exc:
        raise CedarEcoBridgeError("瓶中生态返回了无法识别的响应。") from exc
    if not isinstance(payload, dict):
        raise CedarEcoBridgeError("瓶中生态返回了无法识别的响应。")
    result_text = str(payload.get("text") or payload.get("error") or "").strip()
    return {
        "ok": response.status_code < 400 and payload.get("ok") is not False,
        "text": result_text or "瓶中生态没有返回文字。",
    }
