import base64
import json
import threading
import time
from uuid import uuid4

from flask import request

from config import MINIAPP_TELEGRAM_AUTH_ENABLED, TELEGRAM_BOT_TOKEN, VOICE_CALL_MAX_BYTES
from storage import r2_store
from utils.ip_allowlist import enforce_ip_allowlist
from utils.miniapp_panel_auth import panel_auth_enabled, verify_panel_token
from utils.telegram_webapp import verify_telegram_init_data
from utils.time_aware import now_beijing_iso
from utils.log import get_logger

from services.deepgram_live_stt import create_live_stt
from services.voice_call_pipeline import resolve_voice_call_window_id, run_voice_call

logger = get_logger(__name__)

_LOCK = threading.Lock()
_SESSIONS = {}


def _new_session(call_id="", call_started_at=""):
    return {
        "id": str(uuid4()),
        "call_id": str(call_id or "").strip() or str(uuid4()),
        "call_started_at": str(call_started_at or "").strip() or now_beijing_iso(),
        "created_at": time.time(),
        "updated_at": time.time(),
        "mime_type": "audio/webm",
        "filename": "voice.webm",
        "chunks": [],
        "total_bytes": 0,
        "stt_client": None,
        "last_partial_text": "",
    }


def _save_session(session):
    with _LOCK:
        _SESSIONS[session["id"]] = session


def _get_session(session_id):
    with _LOCK:
        session = _SESSIONS.get(str(session_id or "").strip())
        if session:
            session["updated_at"] = time.time()
        return session


def _pop_session(session_id):
    with _LOCK:
        return _SESSIONS.pop(str(session_id or "").strip(), None)


def _close_session(session):
    if not session:
        return
    client = session.get("stt_client")
    if client:
        try:
            client.close()
        except Exception:
            pass
        session["stt_client"] = None


def _append_chunk(session, chunk, mime_type, filename):
    total_bytes = int(session.get("total_bytes") or 0) + len(chunk)
    if total_bytes > max(1024, int(VOICE_CALL_MAX_BYTES or 0)):
        return False, "音频太大了，缩短一点再试"
    session.setdefault("chunks", []).append(bytes(chunk))
    session["total_bytes"] = total_bytes
    session["updated_at"] = time.time()
    if mime_type:
        session["mime_type"] = str(mime_type or "").strip().lower()
    if filename:
        session["filename"] = str(filename or "").strip() or session.get("filename") or "voice.webm"
    return True, ""


def _append_call_record(call_id, started_at, user_text, reply_text):
    items = r2_store.get_miniapp_call_records() or []
    found = None
    for item in items:
        if str(item.get("id") or "").strip() == str(call_id or "").strip():
            found = item
            break
    if not found:
        found = {"id": call_id, "mode": "voice", "started_at": started_at, "updated_at": started_at, "turns": []}
        items.append(found)
    now_ts = now_beijing_iso()
    found["updated_at"] = now_ts
    found.setdefault("turns", []).extend(
        [
            {"id": str(uuid4()), "role": "user", "text": user_text, "kind": "voice", "timestamp": now_ts},
            {"id": str(uuid4()), "role": "assistant", "text": reply_text, "kind": "voice", "timestamp": now_ts},
        ]
    )
    if found.get("turns"):
        first_text = str((found.get("turns") or [{}])[0].get("text") or "").strip()
        found["title"] = first_text[:24] if first_text else "语音通话"
    items = sorted(items or [], key=lambda x: str(x.get("updated_at") or x.get("started_at") or ""), reverse=True)
    r2_store.save_miniapp_call_records(items)


def _ws_auth_error():
    try:
        enforce_ip_allowlist()
    except Exception as e:
        return str(e)
    panel_token = (request.args.get("panel_token") or "").strip()
    if panel_auth_enabled():
        ok, payload, code = verify_panel_token(panel_token)
        if not ok:
            return code or "panel_token_invalid"
        request.environ["miniapp_panel_payload"] = payload or {}
    if MINIAPP_TELEGRAM_AUTH_ENABLED:
        init_data = (request.args.get("initData") or "").strip()
        ok, err = verify_telegram_init_data(init_data, TELEGRAM_BOT_TOKEN)
        if not ok:
            return err or "initdata_invalid"
    return ""


def register_voice_call_ws(sock):
    @sock.route("/miniapp-api/voice-call/ws")
    def miniapp_voice_call_ws(ws):
        err = _ws_auth_error()
        if err:
            ws.send(json.dumps({"type": "error", "error": err}, ensure_ascii=False))
            return

        session_id = ""
        while True:
            raw = ws.receive()
            if raw is None:
                session = _pop_session(session_id)
                _close_session(session)
                break
            try:
                msg = json.loads(raw)
            except Exception:
                ws.send(json.dumps({"type": "error", "error": "消息格式不对"}, ensure_ascii=False))
                continue
            event_type = str((msg or {}).get("type") or "").strip()

            if event_type == "start":
                session = _new_session(msg.get("call_id"), msg.get("call_started_at"))
                session_id = session["id"]
                session["stt_client"] = create_live_stt(mime_type="audio/webm")
                _save_session(session)
                ws.send(json.dumps({"type": "ready", "session_id": session_id, "call_id": session["call_id"], "call_started_at": session["call_started_at"]}, ensure_ascii=False))
                ws.send(json.dumps({"type": "status", "status": "recording", "text": "正在听你说话..."}, ensure_ascii=False))
                continue

            session = _get_session(session_id)
            if not session:
                ws.send(json.dumps({"type": "error", "error": "语音会话不存在或已过期"}, ensure_ascii=False))
                continue

            if event_type == "audio_chunk":
                audio_b64 = str(msg.get("audio_b64") or "").strip()
                if not audio_b64:
                    continue
                try:
                    chunk = base64.b64decode(audio_b64)
                except Exception:
                    ws.send(json.dumps({"type": "error", "error": "音频分片解码失败"}, ensure_ascii=False))
                    continue
                ok, err = _append_chunk(session, chunk, msg.get("mime_type"), msg.get("filename"))
                if not ok:
                    ws.send(json.dumps({"type": "error", "error": err}, ensure_ascii=False))
                    continue
                client = session.get("stt_client")
                if client:
                    try:
                        client.send_audio(chunk)
                        for item in client.poll_events():
                            if str(item.get("type") or "") != "transcript":
                                continue
                            text = str(item.get("text") or "").strip()
                            if not text or text == str(session.get("last_partial_text") or ""):
                                continue
                            session["last_partial_text"] = text
                            ws.send(json.dumps({"type": "transcript_partial", "text": text, "is_final": bool(item.get("is_final"))}, ensure_ascii=False))
                    except Exception as e:
                        logger.warning("voice ws stt chunk 失败 err=%s", e)
                continue

            if event_type == "finish":
                session = _pop_session(session_id)
                session_id = ""
                if not session:
                    ws.send(json.dumps({"type": "error", "error": "语音会话不存在或已过期"}, ensure_ascii=False))
                    continue
                user_text = ""
                client = session.get("stt_client")
                if client:
                    try:
                        events = client.finish()
                        finals = []
                        partial = ""
                        for item in events:
                            if str(item.get("type") or "") != "transcript":
                                continue
                            text = str(item.get("text") or "").strip()
                            if not text:
                                continue
                            if item.get("is_final"):
                                finals.append(text)
                            else:
                                partial = text
                        user_text = " ".join(finals or ([partial] if partial else [])).strip()
                    except Exception as e:
                        logger.warning("voice ws stt finish 失败 err=%s", e)
                payload, status = run_voice_call(
                    audio_bytes=b"".join(session.get("chunks") or []),
                    mime_type=session.get("mime_type") or "audio/webm",
                    filename=session.get("filename") or "voice.webm",
                    window_id=resolve_voice_call_window_id(msg.get("window_id") or ""),
                    status_cb=lambda st, text: ws.send(json.dumps({"type": "status", "status": st, "text": text}, ensure_ascii=False)),
                    audio_chunk_cb=lambda chunk, meta: ws.send(json.dumps({"type": "audio_chunk", "audio_b64": base64.b64encode(chunk).decode("ascii"), "sample_rate": int(meta.get("sample_rate") or 32000), "audio_channel": int(meta.get("audio_channel") or 1), "audio_format": str(meta.get("audio_format") or "pcm"), "is_final": bool(meta.get("is_final"))}, ensure_ascii=False)),
                    user_text_override=user_text,
                )
                _close_session(session)
                if status >= 400:
                    ws.send(json.dumps({"type": "error", "error": str(payload.get("error") or "语音请求失败")}, ensure_ascii=False))
                    continue
                call_id = str(msg.get("call_id") or session.get("call_id") or "").strip() or str(uuid4())
                call_started_at = str(msg.get("call_started_at") or session.get("call_started_at") or "").strip() or now_beijing_iso()
                _append_call_record(call_id, call_started_at, payload.get("user_text"), payload.get("reply_text"))
                payload["call_id"] = call_id
                payload["call_started_at"] = call_started_at
                ws.send(json.dumps({"type": "result", **payload}, ensure_ascii=False))
                if payload.get("streamed_audio"):
                    ws.send(json.dumps({"type": "audio_stream_end"}, ensure_ascii=False))
                continue

            if event_type == "cancel":
                session = _pop_session(session_id)
                session_id = ""
                _close_session(session)
                ws.send(json.dumps({"type": "cancelled"}, ensure_ascii=False))
                continue

            ws.send(json.dumps({"type": "error", "error": "未知消息类型"}, ensure_ascii=False))
