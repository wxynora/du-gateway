from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Optional

import requests

from config import (
    DEEPGRAM_API_KEY,
    DEEPGRAM_STT_LANGUAGE,
    DEEPGRAM_STT_MODEL,
    DEEPGRAM_STT_SMART_FORMAT,
    DEEPGRAM_STT_URL,
    VOICE_STT_FALLBACK_PROVIDER,
    VOICE_STT_OPENROUTER_API_KEY,
    VOICE_STT_OPENROUTER_API_URL,
    VOICE_STT_OPENROUTER_FALLBACK_MODEL,
    VOICE_STT_OPENROUTER_MODEL,
    VOICE_STT_PROVIDER,
    VOICE_STT_TIMEOUT_SECONDS,
)
from utils.log import get_logger

logger = get_logger(__name__)

_OPENROUTER_PROVIDER_NAMES = {"openrouter", "gemini", "google", "gemini-openrouter"}

_VOICE_TRANSCRIBE_PROMPT = """
你要把用户语音转成中文文字，并保留清楚听见的声音事件。

只返回一个 JSON 对象，不要 Markdown，不要解释。
JSON 字段：
{
  "text": "转写正文。可以在正文中用中文全角括号标明显声音事件，例如（哈哈大笑）（大笑）（轻笑）（哼唱）（唱着说）（压低声音）（停顿了约3秒）。",
  "audio_observations": "一小段自然、柔和的声音细节，直接写给渡参考。不要写成指标列表、检测报告或用分号堆参数；把听得见的细节揉进一句顺口的话里，例如：她离麦克风有点近，后半句气息轻下来，咬字也比前面含糊一点。没有明显线索就留空。",
  "events": ["可选，声音事件短标签列表"]
}

规则：
- 不要推测意图、关系、撒娇、逗人、委屈、生气、想让对方怎样。
- 不要写心理分析，不要写“像是在……”。
- `audio_observations` 可以比普通标签更细，但必须仍然只基于听得见的声音和身体线索；可以写“她离麦克风有点远，后半句气息变轻，咬字略含糊”，不要写“她想让你心疼”。
- `audio_observations` 不要输出成“语速：快；音量：低；气声：明显”这种数据化格式，也不要连续罗列项目；像人在描述听见的声音那样写。
- 只有明显听见笑、唱、哼、哭腔、气声、压低声音、停顿、语速或音高变化时才标。
- 停顿属于正文的一部分。超过约 1 秒的停顿要写在它发生的位置，按音频估算实际时长，例如：我就是……（停顿了约3秒）哎呀我反正有事！
- 很短的犹豫可以用省略号，不要每个喘气或换气都标成停顿。
- 听不准就不要标，不要为了完整而补。
- 正文要尽量贴近用户真实说法，保留口语感。
""".strip()


def _clean_text(value: Any, limit: int = 4000) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[: max(1, int(limit))]


def _normalize_provider(value: str) -> str:
    provider = str(value or "").strip().lower()
    if provider in _OPENROUTER_PROVIDER_NAMES:
        return "openrouter"
    if provider == "deepgram":
        return "deepgram"
    return provider or "deepgram"


def _audio_format(filename: str = "", mime_type: str = "") -> str:
    mt = (mime_type or "").split(";", 1)[0].strip().lower()
    by_mime = {
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/mp4": "m4a",
        "audio/x-m4a": "m4a",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/flac": "flac",
        "audio/aac": "aac",
        "audio/ogg": "ogg",
        "audio/aiff": "aiff",
        "audio/x-aiff": "aiff",
        "audio/webm": "webm",
    }
    if mt in by_mime:
        return by_mime[mt]
    suffix = (filename or "").rsplit(".", 1)[-1].strip().lower() if "." in (filename or "") else ""
    if suffix == "mpeg":
        return "mp3"
    if suffix in {"mp3", "m4a", "wav", "flac", "aac", "ogg", "aiff", "webm"}:
        return suffix
    return ""


def _audio_suffix(filename: str = "") -> str:
    raw = str(filename or "").strip().rsplit("/", 1)[-1]
    if "." not in raw:
        return ""
    return raw.rsplit(".", 1)[-1].strip().lower()


def _prepare_audio_for_stt(audio_bytes: bytes, mime_type: str, filename: str) -> tuple[bytes, str, str]:
    """Convert QQ/NapCat voice formats into a model-friendly wav when needed."""
    if not audio_bytes or _audio_format(filename=filename, mime_type=mime_type):
        return audio_bytes, mime_type, filename

    mt = (mime_type or "").split(";", 1)[0].strip().lower()
    suffix = _audio_suffix(filename)
    should_transcode = suffix in {"amr", "silk", "slk"} or mt in {
        "audio/amr",
        "audio/x-amr",
        "audio/silk",
        "audio/x-silk",
    }
    if not should_transcode:
        return audio_bytes, mime_type, filename

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.warning("STT 音频需要转码但 ffmpeg 不存在 filename=%s mime=%s", filename, mime_type)
        return audio_bytes, mime_type, filename

    ext = suffix or ("amr" if "amr" in mt else "silk" if "silk" in mt else "audio")
    try:
        with tempfile.TemporaryDirectory(prefix="du_stt_") as tmp:
            src = os.path.join(tmp, f"input.{ext}")
            dst = os.path.join(tmp, "voice.wav")
            with open(src, "wb") as f:
                f.write(audio_bytes)
            proc = subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    src,
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    dst,
                ],
                capture_output=True,
                timeout=45,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or b"").decode("utf-8", errors="ignore")[:300]
                logger.warning("STT 音频转码失败 filename=%s mime=%s err=%s", filename, mime_type, err)
                return audio_bytes, mime_type, filename
            with open(dst, "rb") as f:
                out = f.read()
            if not out:
                return audio_bytes, mime_type, filename
            return out, "audio/wav", "voice.wav"
    except Exception as e:
        logger.warning("STT 音频转码异常 filename=%s mime=%s err=%s", filename, mime_type, e)
        return audio_bytes, mime_type, filename


def _extract_json_object(text: str) -> Optional[dict]:
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


def _normalize_transcription_payload(data: dict, provider: str) -> Optional[dict]:
    text = _clean_text(data.get("text") or data.get("transcript") or "", limit=4000)
    if not text:
        return None
    events = data.get("events")
    if isinstance(events, str):
        events = [events]
    if not isinstance(events, list):
        events = []
    clean_events = []
    for item in events[:12]:
        label = _clean_text(item, limit=40)
        if label:
            clean_events.append(label)
    observations = _clean_text(
        data.get("audio_observations") or data.get("voice_observations") or data.get("observations") or "",
        limit=300,
    )
    return {
        "text": text,
        "audio_observations": observations,
        "events": clean_events,
        "provider": provider,
    }


def _deepgram_transcribe(audio_bytes: bytes, mime_type: str = "audio/webm", filename: str = "voice.webm") -> Optional[dict]:
    """调用 Deepgram 预录音接口做语音转文字。"""
    if not DEEPGRAM_API_KEY:
        logger.warning("DEEPGRAM_API_KEY 未配置，跳过 STT")
        return None
    if not audio_bytes:
        return None

    params = {
        "model": str(DEEPGRAM_STT_MODEL or "nova-3").strip() or "nova-3",
        "smart_format": "true" if DEEPGRAM_STT_SMART_FORMAT else "false",
        "punctuate": "true",
        "detect_language": "false",
    }
    language = str(DEEPGRAM_STT_LANGUAGE or "").strip()
    if language:
        params["language"] = language

    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": (mime_type or "application/octet-stream").strip() or "application/octet-stream",
    }
    try:
        r = requests.post(
            DEEPGRAM_STT_URL,
            params=params,
            headers=headers,
            data=audio_bytes,
            timeout=90,
        )
        if r.status_code != 200:
            logger.warning("Deepgram STT 非 200 status=%s body=%s", r.status_code, (r.text or "")[:300])
            return None
        data = r.json() if r.content else {}
        text = (
            (((data or {}).get("results") or {}).get("channels") or [{}])[0].get("alternatives") or [{}]
        )[0].get("transcript")
        text = str(text or "").strip()
        if not text:
            logger.warning("Deepgram STT 空结果 filename=%s mime=%s", filename, mime_type)
            return None
        return {"text": text, "audio_observations": "", "events": [], "provider": "deepgram"}
    except Exception as e:
        logger.warning("Deepgram STT 异常 filename=%s mime=%s err=%s", filename, mime_type, e)
        return None


def _openrouter_transcribe(audio_bytes: bytes, mime_type: str = "audio/webm", filename: str = "voice.webm") -> Optional[dict]:
    if not VOICE_STT_OPENROUTER_API_KEY:
        logger.warning("VOICE_STT_OPENROUTER_API_KEY/OPENROUTER_API_KEY 未配置，跳过 OpenRouter STT")
        return None
    if not audio_bytes:
        return None
    fmt = _audio_format(filename=filename, mime_type=mime_type)
    if not fmt:
        logger.warning("OpenRouter STT 不支持的音频格式 filename=%s mime=%s", filename, mime_type)
        return None

    models = [_clean_text(VOICE_STT_OPENROUTER_MODEL, limit=120) or "google/gemini-2.5-flash"]
    fallback = _clean_text(VOICE_STT_OPENROUTER_FALLBACK_MODEL, limit=120)
    if fallback and fallback not in models:
        models.append(fallback)

    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    headers = {
        "Authorization": f"Bearer {VOICE_STT_OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    last_error = ""
    for idx, model in enumerate(models):
        payload = {
            "model": model,
            "stream": False,
            "temperature": 0,
            "max_tokens": 900,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VOICE_TRANSCRIBE_PROMPT},
                        {"type": "input_audio", "input_audio": {"data": audio_b64, "format": fmt}},
                    ],
                }
            ],
        }
        try:
            resp = requests.post(
                VOICE_STT_OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=max(20, int(VOICE_STT_TIMEOUT_SECONDS or 120)),
            )
        except Exception as e:
            last_error = str(e)
            logger.warning("OpenRouter STT 请求异常 model=%s err=%s", model, e)
            continue
        if resp.status_code >= 400:
            last_error = (resp.text or "")[:500]
            logger.warning("OpenRouter STT 非 2xx model=%s status=%s body=%s", model, resp.status_code, last_error[:300])
            continue
        try:
            data = resp.json() if resp.content else {}
        except Exception as e:
            last_error = str(e)
            logger.warning("OpenRouter STT 响应不是 JSON model=%s err=%s", model, e)
            continue
        content = str((((data or {}).get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if not content:
            last_error = "empty content"
            logger.warning("OpenRouter STT 返回空内容 model=%s", model)
            continue
        parsed = _extract_json_object(content) or {"text": content}
        result = _normalize_transcription_payload(parsed, provider="openrouter")
        if result:
            if idx > 0:
                result["fallback_used"] = True
                result["model"] = model
            else:
                result["model"] = model
            return result
        last_error = "empty transcript"
    if last_error:
        logger.warning("OpenRouter STT 失败: %s", last_error[:300])
    return None


def transcribe_speech(audio_bytes: bytes, mime_type: str = "audio/webm", filename: str = "voice.webm") -> Optional[dict]:
    """返回结构化语音转写：text + 可选客观声音旁白。"""
    audio_bytes, mime_type, filename = _prepare_audio_for_stt(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        filename=filename,
    )
    provider = _normalize_provider(VOICE_STT_PROVIDER)
    fallback_provider = _normalize_provider(VOICE_STT_FALLBACK_PROVIDER)
    ordered = [provider]
    if fallback_provider and fallback_provider not in ordered:
        ordered.append(fallback_provider)

    for item in ordered:
        if item == "openrouter":
            result = _openrouter_transcribe(audio_bytes=audio_bytes, mime_type=mime_type, filename=filename)
        elif item == "deepgram":
            result = _deepgram_transcribe(audio_bytes=audio_bytes, mime_type=mime_type, filename=filename)
        else:
            logger.warning("未知 STT provider=%s", item)
            result = None
        if result and result.get("text"):
            return result
    return None


def speech_to_text(audio_bytes: bytes, mime_type: str = "audio/webm", filename: str = "voice.webm") -> Optional[str]:
    result = transcribe_speech(audio_bytes=audio_bytes, mime_type=mime_type, filename=filename)
    return str((result or {}).get("text") or "").strip() or None
