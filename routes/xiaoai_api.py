from __future__ import annotations

import base64
import re

import requests
from flask import Blueprint, Response, jsonify, request

from config import (
    TELEGRAM_CHAT_PATH,
    TELEGRAM_GATEWAY_URL,
    TELEGRAM_PROACTIVE_TARGET_USER_ID,
    XIAOAI_GATEWAY_TOKEN,
)
from services.minimax_tts import tts_to_audio_bytes
from services.xiaoai_audio_store import (
    create_xiaoai_audio,
    get_xiaoai_audio_row,
    resolve_xiaoai_audio_base_url_for_http_request,
)
from storage.xiaoai_store import (
    add_xiaoai_log,
    get_xiaoai_config,
    get_xiaoai_status,
    list_xiaoai_logs,
    update_xiaoai_status,
)
from utils.log import get_logger

logger = get_logger(__name__)
bp = Blueprint("xiaoai_api", __name__, url_prefix="/api/xiaoai")

_VOICE_TAG_RE = re.compile(r"<voice>([\s\S]*?)</voice>", flags=re.IGNORECASE)


def _extract_bearer() -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _require_xiaoai_auth():
    if not XIAOAI_GATEWAY_TOKEN:
        return None
    if _extract_bearer() == XIAOAI_GATEWAY_TOKEN:
        return None
    return (
        jsonify(
            {
                "ok": False,
                "error": {"code": "UNAUTHORIZED", "message": "Unauthorized"},
                "speak_text": "渡暂时无法接通。",
            }
        ),
        401,
    )


def _normalize_voice_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"\n{2,}", "\n", raw)
    raw = re.sub(r"[ \t]{2,}", " ", raw)
    return raw.strip()


def _extract_voice_tag(text: str) -> tuple[str, str]:
    raw = str(text or "")
    if not raw:
        return "", ""
    m = _VOICE_TAG_RE.search(raw)
    if not m:
        return _normalize_voice_text(raw), ""
    voice_text = _normalize_voice_text(m.group(1) or "")
    clean = _normalize_voice_text(raw[: m.start()] + raw[m.end() :])
    return clean, voice_text


def _fallback_voice_text(text: str) -> str:
    raw = _normalize_voice_text(text)
    if not raw:
        return ""
    raw = re.sub(r"</?voice>", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"</?[^>]+>", "", raw)
    return _normalize_voice_text(raw)


def _resolve_xiaoai_window_id(body: dict) -> str:
    if request.headers.get("X-Window-Id"):
        return (request.headers.get("X-Window-Id") or "").strip()
    window_id = str((body or {}).get("window_id") or "").strip()
    if window_id:
        return window_id
    tg_uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if tg_uid > 0:
        return f"tg_{tg_uid}"
    return ""


def _fetch_gateway_first_model() -> str:
    try:
        from storage.upstream_store import get_cached_active_model

        model = str(get_cached_active_model(refresh_if_missing=True) or "").strip()
        if model:
            return model
    except Exception as e:
        logger.warning("xiaoai fetch active model 异常 err=%s", e)
    return ""


def _gateway_base_url() -> str:
    return str(TELEGRAM_GATEWAY_URL or "").strip().rstrip("/")


def _error_payload(code: str, message: str, speak_text: str) -> dict:
    return {
        "ok": False,
        "error": {"code": code, "message": message},
        "speak_text": speak_text,
    }


def _header_utf8_b64(value: str) -> str:
    return base64.urlsafe_b64encode(str(value or "").encode("utf-8")).decode("ascii")


def _call_gateway_chat(user_text: str, speaker: str, window_id: str) -> tuple[str, dict | None, int]:
    model = _fetch_gateway_first_model()
    if not model:
        return "", _error_payload("MODEL_UNAVAILABLE", "当前没有可用模型", "渡暂时没有连上模型。"), 503
    base_url = _gateway_base_url()
    if not base_url:
        return "", _error_payload("INTERNAL_ERROR", "TELEGRAM_GATEWAY_URL 未配置", "渡暂时无法接通。"), 500
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": window_id,
        "X-Reply-Channel": "xiaoai",
    }
    speaker_text = str(speaker or "").strip()
    if speaker_text:
        headers["X-XiaoAI-Speaker-B64"] = _header_utf8_b64(speaker_text)
    if XIAOAI_GATEWAY_TOKEN:
        headers["Authorization"] = f"Bearer {XIAOAI_GATEWAY_TOKEN}"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": user_text}],
        "stream": False,
    }
    url = f"{base_url}{TELEGRAM_CHAT_PATH}"
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=180)
        data = resp.json() if resp.content else {}
    except Exception as e:
        logger.warning("xiaoai gateway 调用异常 err=%s", e)
        return "", _error_payload("GATEWAY_TIMEOUT", "聊天服务暂时不可用", "渡暂时无法接通。"), 502

    if resp.status_code != 200:
        message = ""
        if isinstance(data, dict):
            if isinstance(data.get("error"), dict):
                message = str((data.get("error") or {}).get("message") or "").strip()
            else:
                message = str(data.get("error") or data.get("message") or "").strip()
        if not message:
            message = f"聊天服务返回 HTTP {resp.status_code}"
        code = "UPSTREAM_UNAVAILABLE" if resp.status_code >= 500 else "BAD_REQUEST"
        if resp.status_code == 401:
            code = "UNAUTHORIZED"
        elif resp.status_code == 403:
            code = "UNAUTHORIZED"
        return "", _error_payload(code, message, "渡暂时无法接通。"), resp.status_code

    try:
        reply = str((((data or {}).get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    except Exception:
        reply = ""
    if not reply:
        return "", _error_payload("EMPTY_REPLY", "聊天服务没有返回正文", "渡暂时没有说出话。"), 502
    return reply, None, 200


@bp.route("/message", methods=["POST"])
def xiaoai_message():
    auth_err = _require_xiaoai_auth()
    if auth_err:
        return auth_err
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(_error_payload("BAD_REQUEST", "需要 JSON 对象", "渡没有听清。")), 400
    user_text = str(body.get("text") or "").strip()
    speaker = str(body.get("speaker") or "").strip()
    window_id = _resolve_xiaoai_window_id(body)
    if not user_text:
        return jsonify(_error_payload("BAD_REQUEST", "缺少 text", "渡没有听清。")), 400
    if not window_id:
        return jsonify(_error_payload("BAD_REQUEST", "缺少 window_id", "渡暂时无法接通。")), 400

    cfg = get_xiaoai_config()
    if not bool((cfg or {}).get("enabled")):
        add_xiaoai_log("warn", "入口已关闭，拒绝小爱消息", speaker=speaker, text=user_text, event="message_disabled")
        update_xiaoai_status({"connected": True, "speaker": speaker, "last_event": "message_disabled", "last_text": user_text})
        return jsonify(_error_payload("XIAOAI_DISABLED", "小爱入口未启用", "小爱入口现在是关闭的。")), 403

    update_xiaoai_status({"connected": True, "speaker": speaker, "last_event": "message", "last_text": user_text})
    add_xiaoai_log("info", "收到小爱消息", speaker=speaker, text=user_text, event="message")

    reply, err_payload, status = _call_gateway_chat(user_text=user_text, speaker=speaker, window_id=window_id)
    if err_payload:
        add_xiaoai_log("error", "网关聊天失败", speaker=speaker, text=user_text, error=(err_payload.get("error") or {}).get("message"), event="gateway_error")
        update_xiaoai_status({"connected": True, "speaker": speaker, "last_event": "gateway_error", "last_error": (err_payload.get("error") or {}).get("message")})
        return jsonify(err_payload), status

    clean_text, voice_text = _extract_voice_tag(reply)
    if not voice_text:
        voice_text = _fallback_voice_text(reply)
    if not voice_text:
        return jsonify(_error_payload("EMPTY_VOICE", "没有可播报的 voice 文本", "渡暂时没有说出话。")), 502

    audio_url = ""
    audio_format = ""
    speak_mode = "text"
    tts_error = ""

    audio_bytes = tts_to_audio_bytes(voice_text, audio_format="mp3")
    if audio_bytes:
        ok, payload = create_xiaoai_audio(
            audio_bytes=audio_bytes,
            audio_format="mp3",
            url_base=resolve_xiaoai_audio_base_url_for_http_request(request.url_root or ""),
        )
        if ok:
            audio_url = str(payload.get("url") or "").strip()
            audio_format = str(payload.get("audio_format") or "").strip()
            speak_mode = "audio" if audio_url else "text"
            update_xiaoai_status({"connected": True, "speaker": speaker, "last_event": "audio_ready", "last_audio_url": audio_url})
            add_xiaoai_log("info", "MiniMax 音频已生成", speaker=speaker, text=voice_text, audio_url=audio_url, event="audio_ready")
        else:
            tts_error = str(payload or "").strip()
            logger.warning("xiaoai create audio 失败 err=%s", tts_error)
            update_xiaoai_status({"connected": True, "speaker": speaker, "last_event": "tts_error", "last_error": tts_error})
            add_xiaoai_log("error", "音频 URL 创建失败", speaker=speaker, text=voice_text, error=tts_error, event="tts_error")
    else:
        tts_error = "Minimax TTS 生成失败"
        logger.warning("xiaoai Minimax TTS 生成失败")
        update_xiaoai_status({"connected": True, "speaker": speaker, "last_event": "tts_error", "last_error": tts_error})
        add_xiaoai_log("error", tts_error, speaker=speaker, text=voice_text, event="tts_error")

    return jsonify(
        {
            "ok": True,
            "reply": reply,
            "clean_text": clean_text,
            "voice_text": voice_text,
            "audio_url": audio_url,
            "audio_format": audio_format,
            "speak_mode": speak_mode,
            "tts_error": tts_error,
        }
    )


@bp.route("/config", methods=["GET"])
def xiaoai_config():
    auth_err = _require_xiaoai_auth()
    if auth_err:
        return auth_err
    return jsonify({"ok": True, "config": get_xiaoai_config()})


@bp.route("/status", methods=["GET", "POST"])
def xiaoai_status():
    auth_err = _require_xiaoai_auth()
    if auth_err:
        return auth_err
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            body = {}
        status = update_xiaoai_status(body)
        message = str(body.get("message") or "").strip()
        if message:
            add_xiaoai_log(
                str(body.get("level") or "info"),
                message,
                event=str(body.get("event") or "status"),
                runner=str(body.get("runner") or ""),
                speaker=str(body.get("speaker") or ""),
                text=str(body.get("text") or ""),
                error=str(body.get("error") or ""),
            )
        return jsonify({"ok": True, "status": status})
    return jsonify({"ok": True, "status": get_xiaoai_status()})


@bp.route("/logs", methods=["GET", "POST"])
def xiaoai_logs():
    auth_err = _require_xiaoai_auth()
    if auth_err:
        return auth_err
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return jsonify(_error_payload("BAD_REQUEST", "需要 JSON 对象", "渡暂时无法接通。")), 400
        item = add_xiaoai_log(
            str(body.get("level") or "info"),
            str(body.get("message") or ""),
            event=str(body.get("event") or "client"),
            runner=str(body.get("runner") or ""),
            speaker=str(body.get("speaker") or ""),
            text=str(body.get("text") or ""),
            error=str(body.get("error") or ""),
            audio_url=str(body.get("audio_url") or ""),
        )
        return jsonify({"ok": True, "item": item})
    limit = request.args.get("limit", type=int, default=120)
    return jsonify({"ok": True, "logs": list_xiaoai_logs(limit=limit)})


@bp.route("/tts", methods=["POST"])
def xiaoai_tts():
    auth_err = _require_xiaoai_auth()
    if auth_err:
        return auth_err
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(_error_payload("BAD_REQUEST", "需要 JSON 对象", "渡暂时无法接通。")), 400
    text = str(body.get("text") or "").strip()
    if not text:
        return jsonify(_error_payload("BAD_REQUEST", "缺少 text", "渡暂时无法接通。")), 400
    audio_format = str(body.get("audio_format") or "mp3").strip().lower() or "mp3"
    if audio_format not in ("mp3", "wav"):
        return jsonify(_error_payload("BAD_REQUEST", f"暂不支持的音频格式：{audio_format}", "渡暂时无法接通。")), 400
    audio_bytes = tts_to_audio_bytes(text, audio_format=audio_format)
    if not audio_bytes:
        return jsonify(_error_payload("TTS_FAILED", "语音生成失败", "渡暂时说不出话。")), 502
    ok, payload = create_xiaoai_audio(
        audio_bytes=audio_bytes,
        audio_format=audio_format,
        url_base=resolve_xiaoai_audio_base_url_for_http_request(request.url_root or ""),
    )
    if not ok:
        return jsonify(_error_payload("PUBLIC_URL_UNAVAILABLE", str(payload), "渡暂时说不出话。")), 503
    return jsonify(
        {
            "ok": True,
            "audio_url": payload.get("url"),
            "expires_in": payload.get("expires_in"),
            "audio_format": payload.get("audio_format"),
        }
    )


@bp.route("/tts/<token>.<ext>", methods=["GET"])
def get_xiaoai_tts(token: str, ext: str):
    row = get_xiaoai_audio_row(token)
    if not row:
        return Response(b"", status=404, mimetype="text/plain; charset=utf-8")
    audio_format = str(row.get("format") or "").strip().lower()
    if audio_format and ext and audio_format != ext.strip().lower():
        return Response(b"", status=404, mimetype="text/plain; charset=utf-8")
    headers = {
        "Cache-Control": "no-store, max-age=0",
        "Content-Disposition": f'inline; filename="xiaoai.{audio_format or "mp3"}"',
    }
    return Response(row.get("audio") or b"", status=200, mimetype=row.get("mime") or "audio/mpeg", headers=headers)
