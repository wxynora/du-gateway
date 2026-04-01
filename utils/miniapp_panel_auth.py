import base64
import hashlib
import hmac
import json
import secrets
import time

from flask import jsonify, request

from config import (
    MINIAPP_PANEL_PASSWORD,
    MINIAPP_PANEL_SECOND_ANSWER,
    MINIAPP_PANEL_SECOND_PROMPT,
    MINIAPP_PANEL_SIGNING_SECRET,
    MINIAPP_PANEL_TOKEN_TTL_SECONDS,
)
from storage.miniapp_panel_store import is_trusted_device, touch_trusted_device


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def panel_auth_enabled() -> bool:
    return bool(MINIAPP_PANEL_PASSWORD and MINIAPP_PANEL_SIGNING_SECRET)


def panel_auth_meta() -> dict:
    enabled = panel_auth_enabled()
    return {
        "enabled": enabled,
        "password_login_enabled": enabled,
        "misconfigured": bool(MINIAPP_PANEL_PASSWORD) != bool(MINIAPP_PANEL_SIGNING_SECRET),
        "token_ttl_seconds": max(300, int(MINIAPP_PANEL_TOKEN_TTL_SECONDS or 0)),
        "second_prompt": MINIAPP_PANEL_SECOND_PROMPT,
        "second_factor_enabled": bool(MINIAPP_PANEL_SECOND_PROMPT and MINIAPP_PANEL_SECOND_ANSWER),
    }


def _sign(payload_b64: str) -> str:
    mac = hmac.new(
        MINIAPP_PANEL_SIGNING_SECRET.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64url_encode(mac)


def issue_panel_token(subject: str = "browser", device_id: str = "") -> tuple[str, int]:
    ttl = max(300, int(MINIAPP_PANEL_TOKEN_TTL_SECONDS or 0))
    now = int(time.time())
    payload = {
        "sub": str(subject or "browser"),
        "device_id": str(device_id or "").strip(),
        "iat": now,
        "exp": now + ttl,
        "nonce": secrets.token_urlsafe(8),
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64)}", ttl


def extract_panel_token() -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header_token = (request.headers.get("X-Panel-Token") or "").strip()
    if header_token:
        return header_token
    return (request.args.get("panel_token") or "").strip()


def verify_panel_token(token: str) -> tuple[bool, dict | None, str]:
    token = (token or "").strip()
    if not token:
        return False, None, "panel_token_missing"
    if not panel_auth_enabled():
        return False, None, "panel_auth_misconfigured"
    try:
        payload_b64, sig = token.split(".", 1)
    except ValueError:
        return False, None, "panel_token_invalid"

    expected = _sign(payload_b64)
    if not hmac.compare_digest(expected, sig):
        return False, None, "panel_token_invalid"
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        return False, None, "panel_token_invalid"
    try:
        exp = int(payload.get("exp") or 0)
    except Exception:
        exp = 0
    if exp <= int(time.time()):
        return False, payload, "panel_token_invalid"
    device_id = str(payload.get("device_id") or "").strip()
    if device_id:
        if not is_trusted_device(device_id):
            return False, payload, "not_trusted"
        touch_trusted_device(device_id)
    return True, payload, ""


def panel_auth_error(code: str, status: int):
    messages = {
        "panel_token_missing": "请先输入面板密码",
        "panel_token_invalid": "登录已失效，请重新输入密码",
        "not_trusted": "这个浏览器已被撤销，请重新验证",
        "panel_auth_misconfigured": "服务端未完成面板密码配置",
    }
    return jsonify({"ok": False, "code": code, "error": messages.get(code, code)}), status


def enforce_panel_token():
    if not panel_auth_enabled():
        return None
    ok, payload, code = verify_panel_token(extract_panel_token())
    if ok:
        request.environ["miniapp_panel_payload"] = payload or {}
        return None
    status = 503 if code == "panel_auth_misconfigured" else (403 if code == "not_trusted" else 401)
    return panel_auth_error(code, status)
