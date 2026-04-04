import base64
import json
import re

from flask import current_app

from config import DEFAULT_CHAT_MODEL, GATEWAY_MODELS, TELEGRAM_PROACTIVE_TARGET_USER_ID, VOICE_CALL_WINDOW_ID
from utils.time_aware import now_beijing_iso
from utils.log import get_logger

logger = get_logger(__name__)


def resolve_voice_call_window_id(explicit_window_id=""):
    wid = str(explicit_window_id or "").strip()
    if wid:
        return wid
    tg_uid = int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
    if tg_uid > 0:
        return "tg_%s" % tg_uid
    return (VOICE_CALL_WINDOW_ID or "miniapp_voice_call").strip() or "miniapp_voice_call"


def sanitize_voice_call_reply(text):
    t = str(text or "").strip()
    if not t:
        return ""
    t = re.sub(r"^\s*[（(]\s*脑内\s*OS\s*[：:][\s\S]*?[)）]\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[（(][^()（）]{0,200}[)）]", "", t)
    t = re.sub(r"[【\[][^【】\[\]]{0,200}[】\]]", "", t)
    t = re.sub(r"[()（）【】\[\]]", "", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def call_voice_chat_pipeline(user_text, window_id=""):
    text = str(user_text or "").strip()
    if not text:
        return "", "语音识别结果为空"
    model = str(DEFAULT_CHAT_MODEL or "").strip()
    if not model:
        gateway_models = [str(x or "").strip() for x in (GATEWAY_MODELS or []) if str(x or "").strip()]
        model = gateway_models[0] if gateway_models else "gpt-4"
    body = {"messages": [{"role": "user", "content": text}], "model": model, "stream": False}
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": resolve_voice_call_window_id(window_id),
        "X-Voice-Call-Slim": "1",
    }
    try:
        from routes.chat import chat_completions

        with current_app.test_request_context("/v1/chat/completions", method="POST", json=body, headers=headers):
            rv = chat_completions()
            resp = current_app.make_response(rv)
        data = json.loads(resp.get_data(as_text=True) or "{}")
    except Exception as e:
        logger.warning("voice chat pipeline 异常 err=%s", e)
        return "", "聊天服务暂时不可用"
    if resp.status_code != 200:
        msg = ""
        if isinstance(data, dict):
            msg = str(data.get("error") or data.get("message") or "").strip()
        return "", (msg or "聊天服务返回 HTTP %s" % resp.status_code)
    try:
        reply_text = str((((data or {}).get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    except Exception:
        reply_text = ""
    reply_text = sanitize_voice_call_reply(reply_text)
    if not reply_text:
        return "", "聊天服务没有返回正文"
    return reply_text, None


def run_voice_call(audio_bytes, mime_type, filename, window_id="", status_cb=None, audio_chunk_cb=None, user_text_override=""):
    if not audio_bytes:
        return {"ok": False, "error": "音频为空"}, 400
    try:
        from services.stt import speech_to_text
        from services.minimax_tts import tts_to_audio_bytes
    except Exception as e:
        logger.warning("voice-call 依赖加载失败 err=%s", e)
        return {"ok": False, "error": "语音服务初始化失败"}, 500

    if callable(status_cb):
        try:
            status_cb("recognizing", "识别中...")
        except Exception:
            pass

    user_text = str(user_text_override or "").strip()
    if not user_text:
        user_text = speech_to_text(audio_bytes=audio_bytes, mime_type=mime_type, filename=filename)
    if not user_text:
        return {"ok": False, "error": "没识别出内容，再说一遍试试"}, 422

    if callable(status_cb):
        try:
            status_cb("thinking", "思考中...")
        except Exception:
            pass

    reply_text, reply_err = call_voice_chat_pipeline(user_text=user_text, window_id=window_id)
    if reply_err:
        return {"ok": False, "error": reply_err, "user_text": user_text}, 502

    if callable(status_cb):
        try:
            status_cb("speaking", "渡正在讲话...")
        except Exception:
            pass

    audio_reply = None
    audio_b64 = ""
    streamed_audio = False
    if callable(audio_chunk_cb):
        try:
            from services.minimax_tts_stream import stream_tts_pcm_chunks

            def _on_chunk(chunk, meta):
                audio_chunk_cb(chunk, meta or {})

            streamed_audio = bool(stream_tts_pcm_chunks(reply_text, _on_chunk))
        except Exception as e:
            logger.warning("voice-call 流式 TTS 失败，回退非流式 err=%s", e)
            streamed_audio = False
    if not streamed_audio:
        audio_reply = tts_to_audio_bytes(reply_text)
        if audio_reply:
            audio_b64 = base64.b64encode(audio_reply).decode("ascii")

    return {
        "ok": True,
        "user_text": user_text,
        "reply_text": reply_text,
        "audio_b64": audio_b64,
        "audio_format": "mp3" if audio_b64 else "",
        "streamed_audio": streamed_audio,
        "timestamp": now_beijing_iso(),
    }, 200
