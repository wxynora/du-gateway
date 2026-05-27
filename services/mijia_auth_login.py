from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import parse
from uuid import uuid4

import requests

from config import DATA_DIR, MIJIA_API_AUTH_PATH
from utils.time_aware import BEIJING_TZ, now_beijing_iso

_STATE_PATH = DATA_DIR / "mijia_login_state.json"
_LOCK = threading.Lock()
_THREAD_LOCK = threading.Lock()
_ACTIVE_THREAD: threading.Thread | None = None
_LOGIN_TIMEOUT_SECONDS = 120


def _default_auth_path() -> Path:
    raw = str(MIJIA_API_AUTH_PATH or "").strip()
    path = Path(raw).expanduser() if raw else Path.home() / ".config" / "mijia-api" / "auth.json"
    if path.is_dir():
        return path / "auth.json"
    return path


def _clip(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _auth_summary(path: Path) -> dict[str, Any]:
    auth = _read_json_file(path) if path.exists() else {}
    try:
        expire_ms = int(auth.get("expireTime") or 0)
    except Exception:
        expire_ms = 0
    now_ms = int(time.time() * 1000)
    return {
        "auth_exists": bool(path.exists()),
        "auth_path": str(path),
        "auth_updated_at": _mtime_iso(path),
        "auth_expires_at": _epoch_ms_to_iso(expire_ms),
        "auth_valid": bool(auth and expire_ms > now_ms),
        "user_id": _clip(auth.get("userId"), 80),
    }


def _mtime_iso(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=BEIJING_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    except Exception:
        return ""


def _epoch_ms_to_iso(value: int) -> str:
    if not value:
        return ""
    try:
        return datetime.fromtimestamp(value / 1000, tz=BEIJING_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    except Exception:
        return ""


def _parse_iso(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(BEIJING_TZ)
    except Exception:
        return None


def _load_state() -> dict[str, Any]:
    if not _STATE_PATH.exists():
        return {}
    return _read_json_file(_STATE_PATH)


def _write_state(data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data or {})
    payload["updated_at"] = now_beijing_iso()
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(_STATE_PATH) + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_STATE_PATH)
    return payload


def _current_session_id() -> str:
    with _LOCK:
        return str((_load_state() or {}).get("session_id") or "")


def _update_state(session_id: str, **fields: Any) -> dict[str, Any]:
    with _LOCK:
        state = _load_state()
        if str(state.get("session_id") or "") != str(session_id or ""):
            return state
        state.update(fields)
        return _write_state(state)


def get_mijia_auth_status() -> dict[str, Any]:
    auth_path = _default_auth_path()
    with _LOCK:
        state = _load_state()
    out = {
        "status": "idle",
        "message": "",
        "qr_url": "",
        "login_url": "",
        "session_id": "",
        "created_at": "",
        "updated_at": "",
        "expires_at": "",
        **_auth_summary(auth_path),
    }
    if isinstance(state, dict):
        for key in ("status", "message", "qr_url", "login_url", "session_id", "created_at", "updated_at", "expires_at", "error"):
            if key in state:
                out[key] = state.get(key) or ""
    status = str(out.get("status") or "")
    if status in {"starting", "waiting_scan"}:
        deadline = _parse_iso(str(out.get("expires_at") or ""))
        if deadline is None:
            updated_at = _parse_iso(str(out.get("updated_at") or ""))
            deadline = updated_at + timedelta(seconds=_LOGIN_TIMEOUT_SECONDS + 30) if updated_at else None
        if deadline is not None and datetime.now(BEIJING_TZ) > deadline:
            expired = {
                "status": "expired",
                "message": "二维码已过期，请重新生成",
                "qr_url": "",
                "login_url": "",
            }
            out.update(expired)
            with _LOCK:
                current = _load_state()
                if str(current.get("session_id") or "") == str(out.get("session_id") or ""):
                    current.update(expired)
                    _write_state(current)
    return out


def start_mijia_auth_login() -> dict[str, Any]:
    global _ACTIVE_THREAD
    auth_path = _default_auth_path()
    session_id = uuid4().hex
    now_iso = now_beijing_iso()
    state = {
        "session_id": session_id,
        "status": "starting",
        "message": "正在生成二维码",
        "qr_url": "",
        "login_url": "",
        "created_at": now_iso,
        "updated_at": now_iso,
        "expires_at": "",
        "auth_path": str(auth_path),
    }
    with _LOCK:
        _write_state(state)
    thread = threading.Thread(target=_login_worker, args=(session_id, auth_path), daemon=True)
    with _THREAD_LOCK:
        _ACTIVE_THREAD = thread
        thread.start()
    return get_mijia_auth_status()


def _login_worker(session_id: str, auth_path: Path) -> None:
    try:
        from mijiaAPI import mijiaAPI

        api = mijiaAPI(auth_data_path=str(auth_path))
        location_data = api._get_location()
        if location_data.get("code", -1) == 0 and location_data.get("message", "") == "刷新Token成功":
            api._save_auth_data()
            api._init_session()
            _update_state(
                session_id,
                status="success",
                message="授权已刷新",
                qr_url="",
                login_url="",
                **_auth_summary(auth_path),
            )
            return

        location_data.update(
            {
                "theme": "",
                "bizDeviceType": "",
                "_hasLogo": "false",
                "_qrsize": "240",
                "_dc": str(int(time.time() * 1000)),
            }
        )
        url = api.login_url + "?" + parse.urlencode(location_data)
        headers = {
            "User-Agent": api.user_agent,
            "Accept-Encoding": "gzip",
            "Content-Type": "application/x-www-form-urlencoded",
            "Connection": "keep-alive",
        }
        login_ret = requests.get(url, headers=headers, timeout=20)
        login_data = api._handle_ret(login_ret)
        expires_at = datetime.now(BEIJING_TZ) + timedelta(seconds=_LOGIN_TIMEOUT_SECONDS)
        _update_state(
            session_id,
            status="waiting_scan",
            message="等待米家 App 扫码确认",
            qr_url=_clip(login_data.get("qr"), 1000),
            login_url=_clip(login_data.get("loginUrl"), 1000),
            expires_at=expires_at.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        )

        session = requests.Session()
        lp_ret = session.get(login_data["lp"], headers=headers, timeout=_LOGIN_TIMEOUT_SECONDS)
        lp_data = api._handle_ret(lp_ret)
        if _current_session_id() != session_id:
            return

        for key in ["psecurity", "nonce", "ssecurity", "passToken", "userId", "cUserId"]:
            api.auth_data[key] = lp_data[key]
        session.get(lp_data["location"], headers=headers, timeout=20)
        api.auth_data.update(session.cookies.get_dict())
        api.auth_data["expireTime"] = int((datetime.now(BEIJING_TZ) + timedelta(days=30)).timestamp() * 1000)
        api._save_auth_data()
        api._init_session()
        _update_state(
            session_id,
            status="success",
            message="米家授权成功",
            qr_url="",
            login_url="",
            **_auth_summary(auth_path),
        )
    except requests.exceptions.Timeout:
        _update_state(session_id, status="expired", message="二维码已过期，请重新生成", qr_url="", login_url="")
    except Exception as e:
        _update_state(session_id, status="error", message="米家授权失败", error=_clip(e, 500), qr_url="", login_url="")
