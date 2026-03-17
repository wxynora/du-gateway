import binascii
from typing import Optional

import requests

from config import (
    MINIMAX_API_KEY,
    MINIMAX_T2A_URL,
    MINIMAX_T2A_MODEL,
    MINIMAX_VOICE_ID,
    MINIMAX_VOICE_SPEED,
    MINIMAX_VOICE_VOL,
    MINIMAX_VOICE_PITCH,
    MINIMAX_VOICE_EMOTION,
    MINIMAX_AUDIO_SAMPLE_RATE,
    MINIMAX_AUDIO_BITRATE,
    MINIMAX_AUDIO_FORMAT,
    MINIMAX_AUDIO_CHANNEL,
)
from utils.log import get_logger

logger = get_logger(__name__)


def tts_to_audio_bytes(text: str) -> Optional[bytes]:
    """
    MiniMax T2A v2：返回音频 bytes（默认 mp3）。
    文档：POST https://api.minimaxi.com/v1/t2a_v2
    返回 data.audio 为 hex 编码音频。
    """
    if not MINIMAX_API_KEY:
        logger.warning("MINIMAX_API_KEY 未配置，跳过 TTS")
        return None
    t = (text or "").strip()
    if not t:
        return None
    headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MINIMAX_T2A_MODEL,
        "text": t,
        "stream": False,
        "voice_setting": {
            "voice_id": MINIMAX_VOICE_ID,
            "speed": MINIMAX_VOICE_SPEED,
            "vol": MINIMAX_VOICE_VOL,
            "pitch": MINIMAX_VOICE_PITCH,
            "emotion": MINIMAX_VOICE_EMOTION,
        },
        "audio_setting": {
            "sample_rate": MINIMAX_AUDIO_SAMPLE_RATE,
            "bitrate": MINIMAX_AUDIO_BITRATE,
            "format": MINIMAX_AUDIO_FORMAT,
            "channel": MINIMAX_AUDIO_CHANNEL,
        },
        "subtitle_enable": False,
    }
    try:
        r = requests.post(MINIMAX_T2A_URL, headers=headers, json=payload, timeout=60)
        if r.status_code != 200:
            logger.warning("MiniMax TTS 非 200 status=%s body=%s", r.status_code, (r.text or "")[:300])
            return None
        data = r.json() if r.content else None
        base = (data or {}).get("base_resp") or {}
        if int(base.get("status_code") or 0) != 0:
            logger.warning("MiniMax TTS 失败 status_code=%s msg=%s", base.get("status_code"), base.get("status_msg"))
            return None
        hex_audio = ((data or {}).get("data") or {}).get("audio") or ""
        if not isinstance(hex_audio, str) or not hex_audio.strip():
            return None
        return binascii.unhexlify(hex_audio.strip())
    except Exception as e:
        logger.warning("MiniMax TTS 异常: %s", e)
        return None

