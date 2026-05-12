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
from storage import r2_store
from utils.log import get_logger

logger = get_logger(__name__)

TTS_EMOTION_VALUES = {"", "happy", "sad", "angry", "fearful", "disgusted", "surprised", "calm", "fluent", "whisper"}


def _normalize_voice_emotion(value: object) -> str:
    emotion = str(value or "").strip().lower()
    return emotion if emotion in TTS_EMOTION_VALUES else ""


def _runtime_voice_emotion() -> str:
    try:
        conf = r2_store.get_miniapp_voice_config() or {}
        if isinstance(conf, dict) and "ttsEmotion" in conf:
            return _normalize_voice_emotion(conf.get("ttsEmotion"))
    except Exception as e:
        logger.debug("读取 MiniMax 运行时 emotion 配置失败: %s", e)
    return _normalize_voice_emotion(MINIMAX_VOICE_EMOTION)


def tts_to_audio_bytes(text: str, audio_format: Optional[str] = None) -> Optional[bytes]:
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
    fmt = str(audio_format or MINIMAX_AUDIO_FORMAT or "").strip() or "mp3"
    voice_setting = {
        "voice_id": MINIMAX_VOICE_ID,
        "speed": float(MINIMAX_VOICE_SPEED),
        "vol": int(MINIMAX_VOICE_VOL),
        "pitch": int(MINIMAX_VOICE_PITCH),
    }
    voice_emotion = _runtime_voice_emotion()
    if voice_emotion:
        voice_setting["emotion"] = voice_emotion
    payload = {
        "model": MINIMAX_T2A_MODEL,
        "text": t,
        "stream": False,
        "language_boost": "auto",
        "voice_setting": voice_setting,
        "audio_setting": {
            "sample_rate": MINIMAX_AUDIO_SAMPLE_RATE,
            "bitrate": MINIMAX_AUDIO_BITRATE,
            "format": fmt,
            "channel": MINIMAX_AUDIO_CHANNEL,
        },
        "pronunciation_dict": {"tone": []},
        "subtitle_enable": False,
        "output_format": "hex",
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
