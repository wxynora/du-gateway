from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Optional
from urllib.parse import urlencode

import requests
import websockets

from config import (
    DEEPGRAM_API_KEY,
    DEEPGRAM_STT_ENDPOINTING,
    DEEPGRAM_STT_LANGUAGE,
    DEEPGRAM_STT_LIVE_SAMPLE_RATE,
    DEEPGRAM_STT_MODEL,
    DEEPGRAM_STT_SMART_FORMAT,
    DEEPGRAM_STT_URL,
    DEEPGRAM_STT_WS_URL,
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


def _live_encoding_for_mime(mime_type: str) -> tuple[str, int]:
    mime = str(mime_type or "").strip().lower()
    if "aac" in mime or "mp4" in mime:
        return "", 0
    if "ogg" in mime or "opus" in mime or "webm" in mime:
        return "", 0
    return "linear16", max(8000, int(DEEPGRAM_STT_LIVE_SAMPLE_RATE or 16000))


class DeepgramLiveTranscriber:
    def __init__(self, mime_type: str = "audio/webm") -> None:
        self.mime_type = str(mime_type or "audio/webm").strip().lower()
        self._send_queue: queue.Queue[bytes | None] = queue.Queue()
        self._event_queue: queue.Queue[dict] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._closed = threading.Event()
        self._started = False

    def start(self) -> bool:
        if self._started:
            return True
        if not DEEPGRAM_API_KEY:
            return False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._started = True
        return True

    def send_audio(self, chunk: bytes) -> bool:
        if not chunk:
            return False
        if not self._started and not self.start():
            return False
        self._send_queue.put(bytes(chunk))
        return True

    def poll_events(self) -> list[dict]:
        items: list[dict] = []
        while True:
            try:
                items.append(self._event_queue.get_nowait())
            except queue.Empty:
                break
        return items

    def finish(self, wait_seconds: float = 1.8) -> list[dict]:
        if not self._started:
            return []
        self._send_queue.put(None)
        if self._thread:
            self._thread.join(timeout=max(0.2, wait_seconds))
        return self.poll_events()

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        if self._started:
            self._send_queue.put(None)

    def _run(self) -> None:
        try:
            asyncio.run(self._run_async())
        except Exception as e:
            logger.warning("Deepgram live STT 线程异常 err=%s", e)
            self._event_queue.put({"type": "error", "error": str(e)})

    async def _run_async(self) -> None:
        encoding, sample_rate = _live_encoding_for_mime(self.mime_type)
        params = {
            "model": DEEPGRAM_STT_MODEL or "flux",
            "interim_results": "true",
            "smart_format": "true" if DEEPGRAM_STT_SMART_FORMAT else "false",
            "punctuate": "true",
            "endpointing": str(DEEPGRAM_STT_ENDPOINTING or "10"),
        }
        language = (DEEPGRAM_STT_LANGUAGE or "").strip()
        if language:
            params["language"] = language
        if encoding:
            params["encoding"] = encoding
        if sample_rate:
            params["sample_rate"] = str(sample_rate)
        ws_url = f"{DEEPGRAM_STT_WS_URL}?{urlencode(params)}"
        headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
        async with websockets.connect(ws_url, additional_headers=headers, max_size=8 * 1024 * 1024) as ws:
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

    async def _receiver(self, ws) -> None:
        async for raw in ws:
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            transcript = str((((data.get("channel") or {}).get("alternatives") or [{}])[0].get("transcript")) or "").strip()
            if transcript:
                self._event_queue.put(
                    {
                        "type": "transcript",
                        "text": transcript,
                        "is_final": bool(data.get("is_final")),
                        "speech_final": bool(data.get("speech_final")),
                    }
                )
            if data.get("type") == "UtteranceEnd":
                self._event_queue.put({"type": "utterance_end"})


def create_live_transcriber(mime_type: str = "audio/webm") -> DeepgramLiveTranscriber | None:
    if not DEEPGRAM_API_KEY:
        return None
    transcriber = DeepgramLiveTranscriber(mime_type=mime_type)
    return transcriber if transcriber.start() else None
