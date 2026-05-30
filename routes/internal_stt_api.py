from __future__ import annotations

from flask import Blueprint, jsonify, request

from config import GATEWAY_INTERNAL_STT_TOKEN, MAIN_GATEWAY_BEARER_TOKEN, XIAOAI_GATEWAY_TOKEN
from services.stt import transcribe_speech
from utils.log import get_logger

logger = get_logger(__name__)
bp = Blueprint("internal_stt_api", __name__, url_prefix="/api/internal")

_MAX_AUDIO_BYTES = 12 * 1024 * 1024


def _extract_bearer() -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _is_direct_local_request() -> bool:
    remote = (request.remote_addr or "").strip()
    host = (request.host or "").split(":", 1)[0].strip().lower()
    if request.headers.get("X-Forwarded-For"):
        return False
    return remote in {"127.0.0.1", "::1"} and host in {"127.0.0.1", "localhost", "::1"}


def _require_internal_auth():
    expected = [
        x
        for x in (
            GATEWAY_INTERNAL_STT_TOKEN,
            MAIN_GATEWAY_BEARER_TOKEN,
            XIAOAI_GATEWAY_TOKEN,
        )
        if str(x or "").strip()
    ]
    if expected:
        if _extract_bearer() in expected:
            return None
        return jsonify({"ok": False, "error": "UNAUTHORIZED"}), 401
    if _is_direct_local_request():
        return None
    return jsonify({"ok": False, "error": "UNAUTHORIZED"}), 401


@bp.route("/stt", methods=["POST"])
def internal_stt():
    blocked = _require_internal_auth()
    if blocked is not None:
        return blocked

    f = request.files.get("audio")
    if not f:
        return jsonify({"ok": False, "error": "缺少 audio"}), 400
    audio_bytes = f.read(_MAX_AUDIO_BYTES + 1)
    if not audio_bytes:
        return jsonify({"ok": False, "error": "音频为空"}), 400
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        return jsonify({"ok": False, "error": "音频过大"}), 413

    filename = (f.filename or request.form.get("filename") or "voice").strip() or "voice"
    mime_type = (
        f.mimetype
        or request.form.get("mime_type")
        or request.form.get("mimeType")
        or "application/octet-stream"
    ).strip().lower()
    if not mime_type.startswith("audio/") and mime_type != "application/octet-stream":
        return jsonify({"ok": False, "error": f"暂不支持的音频格式：{mime_type or 'unknown'}"}), 400

    try:
        result = transcribe_speech(audio_bytes=audio_bytes, mime_type=mime_type, filename=filename) or {}
    except Exception as e:
        logger.warning("internal STT 异常 filename=%s mime=%s err=%s", filename, mime_type, e)
        return jsonify({"ok": False, "error": "语音转写失败"}), 500

    text = str(result.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "语音转写为空"}), 422
    return jsonify(
        {
            "ok": True,
            "text": text,
            "audio_observations": str(result.get("audio_observations") or "").strip(),
            "events": result.get("events") if isinstance(result.get("events"), list) else [],
            "stt_provider": str(result.get("provider") or "").strip(),
            "stt_model": str(result.get("model") or "").strip(),
        }
    )
