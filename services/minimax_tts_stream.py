import asyncio
import binascii
import json
from typing import Callable, Optional

import websockets

from config import (
    MINIMAX_API_KEY,
    MINIMAX_AUDIO_CHANNEL,
    MINIMAX_AUDIO_SAMPLE_RATE,
    MINIMAX_GROUP_ID,
    MINIMAX_T2A_MODEL,
    MINIMAX_T2A_WS_URL,
    MINIMAX_VOICE_EMOTION,
    MINIMAX_VOICE_ID,
    MINIMAX_VOICE_PITCH,
    MINIMAX_VOICE_SPEED,
    MINIMAX_VOICE_VOL,
)
from utils.log import get_logger

logger = get_logger(__name__)


def stream_tts_pcm_chunks(text: str, on_chunk: Callable[[bytes, dict], None]) -> bool:
    if not MINIMAX_API_KEY:
        logger.warning("MINIMAX_API_KEY 未配置，跳过流式 TTS")
        return False
    t = str(text or "").strip()
    if not t:
        return False
    if not callable(on_chunk):
        return False
    try:
        return asyncio.run(_stream_tts_pcm_chunks_async(t, on_chunk))
    except Exception as e:
        logger.warning("MiniMax 流式 TTS 异常: %s", e)
        return False


async def _stream_tts_pcm_chunks_async(text: str, on_chunk: Callable[[bytes, dict], None]) -> bool:
    headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}"}
    if MINIMAX_GROUP_ID:
        headers["GroupId"] = MINIMAX_GROUP_ID
    async with websockets.connect(MINIMAX_T2A_WS_URL, additional_headers=headers) as ws:
        connected = json.loads(await ws.recv())
        if str(connected.get("event") or "") != "connected_success":
            raise RuntimeError(str(((connected.get("base_resp") or {}).get("status_msg")) or "流式 TTS 建连失败"))

        await ws.send(
            json.dumps(
                {
                    "event": "task_start",
                    "model": MINIMAX_T2A_MODEL,
                    "voice_setting": {
                        "voice_id": MINIMAX_VOICE_ID,
                        "speed": float(MINIMAX_VOICE_SPEED),
                        "vol": float(MINIMAX_VOICE_VOL),
                        "pitch": int(MINIMAX_VOICE_PITCH),
                        "emotion": MINIMAX_VOICE_EMOTION,
                    },
                    "audio_setting": {
                        "sample_rate": int(MINIMAX_AUDIO_SAMPLE_RATE),
                        "format": "pcm",
                        "channel": int(MINIMAX_AUDIO_CHANNEL or 1),
                    },
                },
                ensure_ascii=False,
            )
        )
        started = json.loads(await ws.recv())
        if str(started.get("event") or "") != "task_started":
            raise RuntimeError(str(((started.get("base_resp") or {}).get("status_msg")) or "流式 TTS 启动失败"))

        await ws.send(json.dumps({"event": "task_continue", "text": text}, ensure_ascii=False))
        await ws.send(json.dumps({"event": "task_finish"}))
        while True:
            msg = json.loads(await ws.recv())
            event = str(msg.get("event") or "")
            base_resp = msg.get("base_resp") or {}
            if int(base_resp.get("status_code") or 0) not in (0,):
                raise RuntimeError(str(base_resp.get("status_msg") or "流式 TTS 返回异常"))
            if event == "task_failed":
                raise RuntimeError(str(base_resp.get("status_msg") or "流式 TTS 失败"))
            if event == "task_continued":
                audio_hex = str((((msg.get("data") or {}) or {}).get("audio")) or "").strip()
                if audio_hex:
                    on_chunk(
                        binascii.unhexlify(audio_hex),
                        {
                            "sample_rate": int((((msg.get("extra_info") or {}) or {}).get("audio_sample_rate")) or MINIMAX_AUDIO_SAMPLE_RATE),
                            "audio_channel": int((((msg.get("extra_info") or {}) or {}).get("audio_channel")) or (MINIMAX_AUDIO_CHANNEL or 1)),
                            "audio_format": str((((msg.get("extra_info") or {}) or {}).get("audio_format")) or "pcm"),
                            "is_final": bool(msg.get("is_final")),
                        },
                    )
                if bool(msg.get("is_final")):
                    break
            if event == "task_finished":
                break
    return True
