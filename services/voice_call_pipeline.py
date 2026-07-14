import base64
import codecs
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


class VoiceCallPipelineError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(str(message or "语音通话失败"))
        self.status_code = int(status_code or 502)


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


def transcribe_voice_call_input(
    audio_bytes,
    mime_type,
    filename,
    *,
    user_text_override="",
    duration_ms=0,
):
    user_text = str(user_text_override or "").strip()
    audio_observations = ""
    stt_provider = ""
    if not user_text:
        try:
            from services.stt import sanitize_transcript_for_duration, transcribe_speech

            stt_result = transcribe_speech(
                audio_bytes=audio_bytes,
                mime_type=mime_type,
                filename=filename,
            ) or {}
        except Exception as e:
            logger.warning("voice stream STT 异常 err=%s", e, exc_info=True)
            raise VoiceCallPipelineError("语音识别失败", 502) from e
        user_text = sanitize_transcript_for_duration(
            stt_result.get("text") or "",
            duration_ms=duration_ms,
        )
        audio_observations = str(stt_result.get("audio_observations") or "").strip()
        stt_provider = str(stt_result.get("provider") or "").strip()
    if not user_text:
        raise VoiceCallPipelineError("没识别出内容，再说一遍试试", 422)
    return {
        "user_text": user_text,
        "audio_observations": audio_observations,
        "stt_provider": stt_provider,
    }


def _voice_stream_message_text(message):
    content = (message or {}).get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item.get("text"))
    return "".join(parts)


def _iter_voice_sse_data(response):
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    buffer = ""
    data_lines = []

    def consume_line(line):
        nonlocal data_lines
        line = line.rstrip("\r")
        if not line:
            if not data_lines:
                return None
            data = "\n".join(data_lines)
            data_lines = []
            return data
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip(" "))
        return None

    for chunk in response.iter_content(chunk_size=4096):
        if not chunk:
            continue
        buffer += decoder.decode(chunk, final=False)
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            data = consume_line(line)
            if data is not None:
                yield data
    buffer += decoder.decode(b"", final=True)
    if buffer:
        data = consume_line(buffer)
        if data is not None:
            yield data
    if data_lines:
        yield "\n".join(data_lines)


class _StreamingVoiceReplySanitizer:
    _OPEN_TO_CLOSE = {"(": ")", "（": "）", "[": "]", "【": "】"}
    _CLOSERS = set(_OPEN_TO_CLOSE.values())

    def __init__(self):
        self._closers = []

    def feed(self, text):
        visible = []
        for char in str(text or ""):
            expected = self._OPEN_TO_CLOSE.get(char)
            if expected:
                self._closers.append(expected)
                continue
            if char in self._CLOSERS:
                if self._closers and char == self._closers[-1]:
                    self._closers.pop()
                continue
            if not self._closers:
                visible.append(char)
        return "".join(visible)


def _voice_stream_error_message(response):
    try:
        data = response.json() if response.content else {}
    except Exception:
        data = {}
    if isinstance(data, dict):
        error = data.get("error") or data.get("message")
        if isinstance(error, dict):
            error = error.get("message") or error.get("error")
        if str(error or "").strip():
            return str(error).strip()
    return "聊天服务返回 HTTP %s" % int(getattr(response, "status_code", 502) or 502)


def stream_voice_chat_pipeline(user_text, window_id="", audio_observations=""):
    text = str(user_text or "").strip()
    if not text:
        raise VoiceCallPipelineError("语音识别结果为空", 422)
    model = _resolve_voice_model()
    if not model:
        raise VoiceCallPipelineError("当前没有可用模型", 503)
    body = {
        "messages": _build_voice_user_messages(text, audio_observations),
        "model": model,
        "stream": True,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Window-Id": resolve_voice_call_window_id(window_id),
        "X-Voice-Call-Slim": "1",
    }
    if MAIN_GATEWAY_BEARER_TOKEN:
        headers["Authorization"] = "Bearer %s" % MAIN_GATEWAY_BEARER_TOKEN
    url = "%s/v1/chat/completions" % str(MAIN_GATEWAY_BASE_URL or "").strip().rstrip("/")

    response = None
    try:
        response = requests.post(
            url,
            headers=headers,
            json=body,
            stream=True,
            timeout=CHAT_RESPONSE_TIMEOUT_SECONDS,
        )
        if response.status_code in (401, 403):
            new_model = _fetch_gateway_first_model()
            if new_model and new_model != body.get("model"):
                response.close()
                body["model"] = new_model
                response = requests.post(
                    url,
                    headers=headers,
                    json=body,
                    stream=True,
                    timeout=CHAT_RESPONSE_TIMEOUT_SECONDS,
                )
        if response.status_code != 200:
            raise VoiceCallPipelineError(_voice_stream_error_message(response), 502)

        degraded_reason = str(response.headers.get("X-Du-Stream-Degraded") or "").strip()
        if degraded_reason:
            yield {"kind": "degraded", "reason": degraded_reason}

        sanitizer = _StreamingVoiceReplySanitizer()
        visible_parts = []
        done_seen = False
        finish_reason = ""
        for raw_data in _iter_voice_sse_data(response):
            if raw_data.strip() == "[DONE]":
                done_seen = True
                break
            try:
                packet = json.loads(raw_data)
            except Exception:
                continue
            if not isinstance(packet, dict):
                continue
            if packet.get("error"):
                error = packet.get("error")
                if isinstance(error, dict):
                    error = error.get("message") or error.get("error")
                raise VoiceCallPipelineError(str(error or "聊天服务暂时不可用"), 502)
            choices = packet.get("choices") or []
            choice = choices[0] if choices and isinstance(choices[0], dict) else {}
            delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
            visible = sanitizer.feed(_voice_stream_message_text(delta))
            if visible:
                visible_parts.append(visible)
                yield {"kind": "assistant_delta", "delta": visible}
            if choice.get("finish_reason") is not None:
                finish_reason = str(choice.get("finish_reason") or "")
        if not done_seen and not finish_reason:
            raise VoiceCallPipelineError("流式响应异常中断", 502)
        reply_text = sanitize_voice_call_reply("".join(visible_parts))
        if not reply_text:
            raise VoiceCallPipelineError("聊天服务没有返回正文", 502)
        yield {"kind": "assistant_done", "reply_text": reply_text}
    except VoiceCallPipelineError:
        raise
    except Exception as e:
        logger.warning("voice stream chat pipeline 异常 err=%s", e, exc_info=True)
        raise VoiceCallPipelineError("聊天服务暂时不可用", 502) from e
    finally:
        try:
            if response is not None:
                response.close()
        except Exception:
            pass


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
