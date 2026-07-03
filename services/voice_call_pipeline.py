import base64
import json
import re

import requests

# 项目约定：语音通话禁止默认兜底模型。拉不到当前可用模型就直接报错，不要补 DEFAULT_CHAT_MODEL / GATEWAY_MODELS[0] / gpt-4。
from config import (
    CHAT_RESPONSE_TIMEOUT_SECONDS,
    MAIN_GATEWAY_BASE_URL,
    MAIN_GATEWAY_BEARER_TOKEN,
    TELEGRAM_PROACTIVE_TARGET_USER_ID,
    VOICE_CALL_WINDOW_ID,
)
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


def _fetch_gateway_first_model():
    try:
        from storage.upstream_store import get_cached_active_model

        model = str(get_cached_active_model(refresh_if_missing=False) or "").strip()
        if model:
            return model
    except Exception as e:
        logger.warning("voice fetch active model 异常 err=%s", e)
    return ""


# 注意：语音通话禁止默认兜底模型。
# 拉不到当前可用模型就直接报错，不要补 DEFAULT_CHAT_MODEL / GATEWAY_MODELS[0] / gpt-4。
def _resolve_voice_model():
    model = _fetch_gateway_first_model()
    return str(model or "").strip()


def _build_voice_user_messages(user_text, audio_observations=""):
    text = str(user_text or "").strip()
    observations = str(audio_observations or "").strip()
    messages = []
    if observations:
        messages.append(
            {
                "role": "system",
                "content": (
                    "【用户语音的客观声音旁白】\n"
                    f"{observations}\n"
                    "这只是可听见的声学线索，不是情绪或意图判断。回复时自然参考，不要复述这段旁白。"
                ),
            }
        )
    messages.append({"role": "user", "content": text})
    return messages


def call_voice_chat_pipeline(user_text, window_id="", audio_observations=""):
    text = str(user_text or "").strip()
    if not text:
        return "", "语音识别结果为空"
    model = _resolve_voice_model()
    if not model:
        return "", "当前没有可用模型"
    body = {"messages": _build_voice_user_messages(text, audio_observations), "model": model, "stream": False}
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": resolve_voice_call_window_id(window_id),
        "X-Voice-Call-Slim": "1",
    }
    if MAIN_GATEWAY_BEARER_TOKEN:
        headers["Authorization"] = "Bearer %s" % MAIN_GATEWAY_BEARER_TOKEN
    base_url = str(MAIN_GATEWAY_BASE_URL or "").strip().rstrip("/")
    url = "%s/v1/chat/completions" % base_url
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=CHAT_RESPONSE_TIMEOUT_SECONDS)
        data = resp.json() if resp.content else {}
    except Exception as e:
        logger.warning("voice chat pipeline 异常 err=%s", e)
        return "", "聊天服务暂时不可用"
    if resp.status_code in (401, 403):
        new_model = _fetch_gateway_first_model()
        if new_model and new_model != body.get("model"):
            logger.warning("voice chat %s: model=%s -> %s 重试一次", resp.status_code, body.get("model"), new_model)
            body["model"] = new_model
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=CHAT_RESPONSE_TIMEOUT_SECONDS)
                data = resp.json() if resp.content else {}
            except Exception as e:
                logger.warning("voice chat retry 异常 err=%s", e)
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


def run_voice_call(audio_bytes, mime_type, filename, window_id="", status_cb=None, audio_chunk_cb=None, user_text_override="", duration_ms=0):
    if not audio_bytes:
        return {"ok": False, "error": "音频为空"}, 400
    try:
        from services.stt import transcribe_speech
        from services.stt import sanitize_transcript_for_duration
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
    audio_observations = ""
    stt_result = None
    if not user_text:
        stt_result = transcribe_speech(audio_bytes=audio_bytes, mime_type=mime_type, filename=filename)
        user_text = sanitize_transcript_for_duration((stt_result or {}).get("text") or "", duration_ms=duration_ms)
        audio_observations = str((stt_result or {}).get("audio_observations") or "").strip()
    if not user_text:
        return {"ok": False, "error": "没识别出内容，再说一遍试试"}, 422

    if callable(status_cb):
        try:
            status_cb("thinking", "思考中...")
        except Exception:
            pass

    reply_text, reply_err = call_voice_chat_pipeline(
        user_text=user_text,
        window_id=window_id,
        audio_observations=audio_observations,
    )
    if reply_err:
        return {"ok": False, "error": reply_err, "user_text": user_text}, 502

    if callable(status_cb):
        try:
            status_cb("speaking", "渡正在讲话...")
        except Exception:
            pass

    audio_b64 = ""
    audio_reply = tts_to_audio_bytes(reply_text)
    if audio_reply:
        audio_b64 = base64.b64encode(audio_reply).decode("ascii")
    else:
        return {"ok": False, "error": "语音生成失败", "user_text": user_text, "reply_text": reply_text}, 502

    return {
        "ok": True,
        "user_text": user_text,
        "audio_observations": audio_observations,
        "stt_provider": str((stt_result or {}).get("provider") or "").strip(),
        "reply_text": reply_text,
        "audio_b64": audio_b64,
        "audio_format": "mp3" if audio_b64 else "",
        "streamed_audio": False,
        "timestamp": now_beijing_iso(),
    }, 200
