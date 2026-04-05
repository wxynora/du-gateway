import asyncio
import json
import queue
import threading
from typing import Optional
from urllib.parse import urlencode

import websockets

try:
    from config import (
        DEEPGRAM_API_KEY,
        DEEPGRAM_STT_LANGUAGE,
        DEEPGRAM_STT_MODEL,
        DEEPGRAM_STT_SMART_FORMAT,
        DEEPGRAM_STT_WS_URL,
    )
except Exception:
    DEEPGRAM_API_KEY = ""
    DEEPGRAM_STT_LANGUAGE = "zh-CN"
    DEEPGRAM_STT_MODEL = "nova-3"
    DEEPGRAM_STT_SMART_FORMAT = True
    DEEPGRAM_STT_WS_URL = "wss://api.deepgram.com/v1/listen"

from utils.log import get_logger

logger = get_logger(__name__)


def _build_ws_url(mime_type: str) -> str:
    mime = str(mime_type or "").strip().lower()
    params = {
        "model": str(DEEPGRAM_STT_MODEL or "nova-3").strip() or "nova-3",
        "interim_results": "true",
        "punctuate": "true",
        "smart_format": "true" if DEEPGRAM_STT_SMART_FORMAT else "false",
        "endpointing": "10",
    }
    language = str(DEEPGRAM_STT_LANGUAGE or "").strip()
    if language:
        params["language"] = language
    # webm/ogg/mp4 这类容器音频不显式带 encoding/sample_rate，避免和 Deepgram 解封装冲突
    if "wav" in mime or "pcm" in mime:
        params["encoding"] = "linear16"
        params["sample_rate"] = "16000"
    return "%s?%s" % (str(DEEPGRAM_STT_WS_URL or "").strip(), urlencode(params))


class DeepgramLiveSTT(object):
    def __init__(self, mime_type="audio/webm"):
        self.mime_type = str(mime_type or "audio/webm").strip().lower()
        self._send_queue = queue.Queue()
        self._event_queue = queue.Queue()
        self._closed = threading.Event()
        self._thread = None
        self._started = False

    def start(self):
        if self._started:
            return True
        if not DEEPGRAM_API_KEY:
            logger.warning("DEEPGRAM_API_KEY 未配置，跳过流式 STT")
            return False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._started = True
        return True

    def send_audio(self, chunk):
        if not chunk:
            return False
        if not self._started and not self.start():
            return False
        self._send_queue.put(bytes(chunk))
        return True

    def poll_events(self):
        items = []
        while True:
            try:
                items.append(self._event_queue.get_nowait())
            except queue.Empty:
                break
        return items

    def finish(self, timeout=1.8):
        if not self._started:
            return []
        self._send_queue.put(None)
        if self._thread:
            self._thread.join(timeout=max(0.2, float(timeout or 1.8)))
        return self.poll_events()

    def close(self):
        if self._closed.is_set():
            return
        self._closed.set()
        if self._started:
            self._send_queue.put(None)

    def _run(self):
        try:
            asyncio.run(self._run_async())
        except Exception as e:
            logger.warning("Deepgram 流式 STT 异常 err=%s", e)
            self._event_queue.put({"type": "error", "error": str(e)})

    async def _run_async(self):
        headers = {"Authorization": "Token %s" % DEEPGRAM_API_KEY}
        async with websockets.connect(_build_ws_url(self.mime_type), additional_headers=headers, max_size=8 * 1024 * 1024) as ws:
            receiver = asyncio.create_task(self._receiver(ws))
            try:
                while not self._closed.is_set():
                    item = await asyncio.to_thread(self._send_queue.get)
                    if item is None:
                        try:
                            await ws.send(json.dumps({"type": "CloseStream"}))
                        except Exception:
                            pass
                        break
                    await ws.send(item)
                await asyncio.sleep(0.6)
            finally:
                try:
                    await ws.close()
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(receiver, timeout=0.8)
                except Exception:
                    receiver.cancel()

    async def _receiver(self, ws):
        async for raw in ws:
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            alt = (((data.get("channel") or {}).get("alternatives") or [{}])[0] or {})
            text = str(alt.get("transcript") or "").strip()
            if not text:
                continue
            self._event_queue.put(
                {
                    "type": "transcript",
                    "text": text,
                    "is_final": bool(data.get("is_final")),
                    "speech_final": bool(data.get("speech_final")),
                }
            )


def create_live_stt(mime_type="audio/webm") -> Optional[DeepgramLiveSTT]:
    if not DEEPGRAM_API_KEY:
        return None
    client = DeepgramLiveSTT(mime_type=mime_type)
    if not client.start():
        return None
    return client
