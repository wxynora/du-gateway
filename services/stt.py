from __future__ import annotations

from typing import Optional

import requests

from config import (
    DEEPGRAM_API_KEY,
    DEEPGRAM_STT_LANGUAGE,
    DEEPGRAM_STT_MODEL,
    DEEPGRAM_STT_SMART_FORMAT,
    DEEPGRAM_STT_URL,
)
from utils.log import get_logger

logger = get_logger(__name__)


def speech_to_text(audio_bytes: bytes, mime_type: str = "audio/webm", filename: str = "voice.webm") -> Optional[str]:
    """调用 Deepgram 预录音接口做语音转文字。"""
    if not DEEPGRAM_API_KEY:
        logger.warning("DEEPGRAM_API_KEY 未配置，跳过 STT")
        return None
    if not audio_bytes:
        return None

    params = {
        "model": DEEPGRAM_STT_MODEL or "nova-3",
        "smart_format": "true" if DEEPGRAM_STT_SMART_FORMAT else "false",
        "punctuate": "true",
        "detect_language": "false",
    }
    language = (DEEPGRAM_STT_LANGUAGE or "").strip()
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
        return text
    except Exception as e:
        logger.warning("Deepgram STT 异常 filename=%s mime=%s err=%s", filename, mime_type, e)
        return None
