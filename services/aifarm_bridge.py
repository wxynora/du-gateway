from __future__ import annotations

import json
import os
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

try:
    import fcntl
except Exception:  # pragma: no cover - target Linux/macOS hosts provide fcntl.
    fcntl = None

from config import DATA_DIR


AIFARM_UPSTREAM_URL = os.environ.get("AIFARM_UPSTREAM_URL", "http://127.0.0.1:8080").strip().rstrip("/")
AIFARM_STATE_FILE = Path(
    os.environ.get("AIFARM_STATE_FILE", str(DATA_DIR / "aifarm_app_session.json"))
).expanduser()
AIFARM_FARM_NAME = os.environ.get("AIFARM_FARM_NAME", "渡的小农场").strip() or "渡的小农场"
AIFARM_AI_NAME = os.environ.get("AIFARM_AI_NAME", "渡").strip() or "渡"
AIFARM_HUMAN_NAME = os.environ.get("AIFARM_HUMAN_NAME", "辛玥").strip() or "辛玥"

_HUMAN_KEY_RE = re.compile(r"^[a-fA-F0-9]{32}$")
_AGENT_KEY_RE = re.compile(r"^[A-Za-z0-9]{8,32}$")
_ACTION_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_STATE_LOCK = threading.RLock()


class AIFarmBridgeError(RuntimeError):
    pass


@contextmanager
def _session_lock():
    with _STATE_LOCK:
        AIFARM_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        lock_path = AIFARM_STATE_FILE.with_suffix(AIFARM_STATE_FILE.suffix + ".lock")
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


def _read_state() -> dict[str, Any] | None:
    try:
        raw = json.loads(AIFARM_STATE_FILE.read_text(encoding="utf-8"))
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


def _write_state(state: dict[str, Any]) -> None:
    AIFARM_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = AIFARM_STATE_FILE.with_suffix(AIFARM_STATE_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    os.replace(tmp, AIFARM_STATE_FILE)


def _human_key_from_url(value: object) -> str:
    path = urlparse(str(value or "")).path
    parts = [part for part in path.split("/") if part]
    if len(parts) != 2 or parts[0] != "ui" or not _HUMAN_KEY_RE.fullmatch(parts[1]):
        raise AIFarmBridgeError("AI 农场返回了无效的人类页面钥匙。")
    return parts[1]


def _agent_path_from_url(value: object) -> str:
    parsed = urlparse(str(value or ""))
    parts = [part for part in parsed.path.split("/") if part]
    if (
        len(parts) != 2
        or parts[0] != "a"
        or not _AGENT_KEY_RE.fullmatch(parts[1])
        or parsed.query
        or parsed.fragment
    ):
        raise AIFarmBridgeError("AI 农场返回了无效的渡操作入口。")
    # 只保留上游返回 URL 的能力路径；实际请求永远钉在 AIFARM_UPSTREAM_URL，
    # 避免状态文件被改坏后把网关变成任意 URL 请求器。
    return f"/a/{parts[1]}"


def _agent_path_from_state(state: dict[str, Any]) -> str:
    value = state.get("agent_path") or state.get("play_url")
    return _agent_path_from_url(value)


def _is_running() -> bool:
    try:
        response = requests.get(f"{AIFARM_UPSTREAM_URL}/", timeout=0.8)
        return response.status_code == 200
    except requests.RequestException:
        return False


def session_status() -> dict[str, Any]:
    state = _read_state()
    return {
        "ok": True,
        "configured": state is not None,
        "running": _is_running(),
        "farm_name": str((state or {}).get("farm_name") or AIFARM_FARM_NAME),
    }


def public_session(state: dict[str, Any]) -> dict[str, Any]:
    human_key = str(state.get("human_key") or "").strip()
    if not _HUMAN_KEY_RE.fullmatch(human_key):
        raise AIFarmBridgeError("AI 农场会话记录已损坏。")
    return {
        "ok": True,
        "configured": True,
        "farm_name": str(state.get("farm_name") or AIFARM_FARM_NAME),
        "url": f"/aifarm/ui/{human_key}",
    }


def ensure_session() -> dict[str, Any]:
    with _session_lock():
        state = _read_state()
        if state is not None:
            if not _is_running():
                raise AIFarmBridgeError("AI 农场服务还没启动。")
            return state

        try:
            response = requests.post(
                f"{AIFARM_UPSTREAM_URL}/farms",
                json={
                    "name": AIFARM_FARM_NAME,
                    "aiName": AIFARM_AI_NAME,
                    "humanName": AIFARM_HUMAN_NAME,
                },
                timeout=10,
            )
        except requests.RequestException as exc:
            raise AIFarmBridgeError("AI 农场服务还没启动。") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise AIFarmBridgeError("AI 农场返回了无法识别的响应。") from exc
        if response.status_code >= 400 or not isinstance(payload, dict) or not payload.get("ok"):
            message = str((payload or {}).get("text") or (payload or {}).get("error") or "AI 农场创建失败。")
            raise AIFarmBridgeError(message)

        farm = payload.get("farm") if isinstance(payload.get("farm"), dict) else {}
        play_url = str(payload.get("playUrl") or "").strip()
        state = {
            "farm_id": str(farm.get("id") or "").strip(),
            "farm_name": str(farm.get("name") or AIFARM_FARM_NAME).strip() or AIFARM_FARM_NAME,
            "human_key": _human_key_from_url(payload.get("humanUrl")),
            # 渡的操作入口只留在本机状态里，绝不返回给 iframe。
            "play_url": play_url,
            "agent_path": _agent_path_from_url(play_url),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_state(state)
        return state


def run_agent_action(arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = dict(arguments) if isinstance(arguments, dict) else {}
    action = str(args.pop("action", "")).strip().lower()
    if not _ACTION_RE.fullmatch(action):
        raise AIFarmBridgeError("AI 农场动作无效；不知道怎么做时先用 action=help。")
    if action == "new-token":
        raise AIFarmBridgeError("聊天工具不允许轮换或回传农场主密钥。")

    state = _read_state()
    if state is None:
        state = ensure_session()
    agent_path = _agent_path_from_state(state)
    try:
        response = requests.post(
            f"{AIFARM_UPSTREAM_URL}{agent_path}/{action}",
            json=args,
            timeout=15,
        )
    except requests.RequestException as exc:
        raise AIFarmBridgeError("AI 农场服务还没启动。") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise AIFarmBridgeError("AI 农场返回了无法识别的动作结果。") from exc
    if not isinstance(payload, dict):
        raise AIFarmBridgeError("AI 农场返回了无法识别的动作结果。")

    text = str(payload.get("text") or payload.get("error") or "AI 农场动作没有返回说明。").strip()
    result: dict[str, Any] = {
        "ok": response.status_code < 400 and payload.get("ok") is not False,
        "text": text,
    }
    # 上游 detail=true 的 farm/farms 视图不含 token、humanKey 或 agentKey，可供渡精确决策。
    for key in ("farm", "farms"):
        if key in payload:
            result[key] = payload[key]
    return result
