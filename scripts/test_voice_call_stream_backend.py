#!/usr/bin/env python3
"""Contract tests for the dedicated voice-call stream and segment TTS routes."""

from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def assert_true(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def assert_eq(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r} actual={actual!r}")


class FakeStreamResponse:
    def __init__(self, chunks: list[bytes], *, degraded: bool = False):
        self.status_code = 200
        self.headers = {"X-Du-Stream-Degraded": "upstream_nonstream"} if degraded else {}
        self.content = b""
        self._chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size=4096):
        del chunk_size
        yield from self._chunks

    def close(self):
        self.closed = True

    def json(self):
        return {}


def test_pipeline_visible_stream() -> None:
    from services import voice_call_pipeline as pipeline

    packets = [
        {"choices": [{"delta": {"content": "（脑内OS："}}]},
        {"choices": [{"delta": {"content": "这段不能播）你好，"}}]},
        {"reasoning": "私密思考不能外发", "choices": []},
        {"choices": [{"delta": {"content": "我在。"}, "finish_reason": "stop"}]},
    ]
    raw = "".join(
        "data: " + json.dumps(packet, ensure_ascii=False, separators=(",", ":")) + "\n\n"
        for packet in packets
    ) + "data: [DONE]\n\n"
    encoded = raw.encode("utf-8")
    response = FakeStreamResponse(
        [encoded[:17], encoded[17:43], encoded[43:89], encoded[89:]],
        degraded=True,
    )
    calls = []
    old_resolve = pipeline._resolve_voice_model
    old_post = pipeline.requests.post
    pipeline._resolve_voice_model = lambda: "active-model"

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return response

    pipeline.requests.post = fake_post
    try:
        events = list(
            pipeline.stream_voice_chat_pipeline(
                "听得到吗",
                window_id="tg_1",
                audio_observations="语速平稳",
            )
        )
    finally:
        pipeline._resolve_voice_model = old_resolve
        pipeline.requests.post = old_post

    assert_eq([event["kind"] for event in events], ["degraded", "assistant_delta", "assistant_delta", "assistant_done"], "event order")
    assert_eq("".join(event.get("delta", "") for event in events), "你好，我在。", "only visible text may stream")
    assert_eq(events[-1]["reply_text"], "你好，我在。", "final text must match visible deltas")
    assert_true(response.closed, "upstream response must close")
    assert_eq(len(calls), 1, "stream should use one upstream request")
    _url, kwargs = calls[0]
    assert_true(kwargs["json"]["stream"] is True, "voice model request must be true streaming")
    assert_eq(kwargs["headers"]["X-Window-Id"], "tg_1", "voice stream must keep the same window")
    assert_eq(kwargs["headers"]["X-Voice-Call-Slim"], "1", "voice stream must use the slim injection channel")


def parse_named_sse(text: str) -> list[tuple[str, dict]]:
    output = []
    event_name = "message"
    data_lines = []
    for line in text.splitlines() + [""]:
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
        elif not line and data_lines:
            output.append((event_name, json.loads("\n".join(data_lines))))
            event_name = "message"
            data_lines = []
    return output


def test_routes_without_external_writes() -> None:
    from flask import Blueprint, Flask

    from routes.miniapp import media
    from services import minimax_tts, voice_call_pipeline, voice_call_tts_cache

    app = Flask("voice-call-stream-contract")
    bp = Blueprint("voice_call_stream_contract", __name__, url_prefix="/miniapp-api")
    media.register_routes(bp)
    app.register_blueprint(bp)
    client = app.test_client()

    appended = []
    old_append = media._append_call_record_turns
    old_stream = voice_call_pipeline.stream_voice_chat_pipeline
    old_tts = minimax_tts.tts_to_audio_bytes
    old_cache_dir = voice_call_tts_cache._CACHE_DIR
    media._append_call_record_turns = lambda **kwargs: appended.append(kwargs) or True
    voice_call_pipeline.stream_voice_chat_pipeline = lambda *args, **kwargs: iter(
        [
            {"kind": "assistant_delta", "delta": "先说第一句。"},
            {"kind": "assistant_delta", "delta": "再说第二句。"},
            {"kind": "assistant_done", "reply_text": "先说第一句。再说第二句。"},
        ]
    )
    minimax_tts.tts_to_audio_bytes = lambda text, audio_format="mp3": f"audio:{audio_format}:{text}".encode()
    try:
        with tempfile.TemporaryDirectory(prefix="du-voice-call-tts-") as temp_dir:
            voice_call_tts_cache._CACHE_DIR = Path(temp_dir)
            stream_response = client.post(
                "/miniapp-api/voice-call/stream",
                data={
                    "audio": (io.BytesIO(b"fake-audio"), "voice.webm"),
                    "mime_type": "audio/webm",
                    "user_text_override": "这是用户说的话",
                    "call_id": "call-test",
                    "call_started_at": "2026-07-14T00:00:00+08:00",
                    "window_id": "tg_1",
                    "duration_ms": "1200",
                },
                content_type="multipart/form-data",
            )
            assert_eq(stream_response.status_code, 200, "stream route status")
            assert_true(stream_response.content_type.startswith("text/event-stream"), "stream route content type")
            assert_eq(stream_response.headers.get("Cache-Control"), "no-store", "stream response must not cache")
            assert_eq(stream_response.headers.get("X-Accel-Buffering"), "no", "proxy buffering must be disabled")
            events = parse_named_sse(stream_response.get_data(as_text=True))
            assert_eq(
                [name for name, _payload in events],
                ["phase", "transcript", "phase", "assistant_delta", "assistant_delta", "assistant_done", "done"],
                "route event sequence",
            )
            assert_eq(events[1][1]["text"], "这是用户说的话", "transcript event")
            assert_eq(events[-1][1]["call_id"], "call-test", "done event call id")
            assert_eq(len(appended), 1, "a completed stream must append exactly one call turn pair")
            assert_eq(len(appended[0]["turns"]), 2, "call record must contain user and assistant once")

            tts_response = client.post(
                "/miniapp-api/voice-call/tts-segment",
                json={
                    "turn_id": "turn-test",
                    "segment_id": "seg-1",
                    "text": "这是一小段。",
                    "audio_format": "mp3",
                },
            )
            assert_eq(tts_response.status_code, 200, "segment TTS status")
            tts_payload = tts_response.get_json()
            assert_true(tts_payload["ok"], "segment TTS should succeed")
            assert_true("audio_b64" not in tts_payload, "segment TTS must use a short URL instead of base64")
            audio_path = urlsplit(tts_payload["audio_url"]).path
            audio_response = client.get(audio_path, headers={"Range": "bytes=0-4"})
            assert_eq(audio_response.status_code, 206, "short audio URL must support Range")
            assert_eq(audio_response.headers.get("Cache-Control"), "private, no-store, max-age=0", "short audio must not be public cached")
            assert_eq(audio_response.data, b"audio", "Range bytes")

            cancel_response = client.post(
                "/miniapp-api/voice-call/tts-cancel",
                json={"turn_id": "turn-test"},
            )
            assert_eq(cancel_response.status_code, 200, "TTS cancel status")
            assert_eq(cancel_response.get_json()["removed"], 1, "cancel must remove this turn's short audio")
            assert_eq(client.get(audio_path).status_code, 404, "cancelled short audio must no longer play")

            too_long = client.post(
                "/miniapp-api/voice-call/tts-segment",
                json={"turn_id": "turn-test", "segment_id": "seg-long", "text": "长" * 121},
            )
            assert_eq(too_long.status_code, 400, "segment hard limit must reject oversized text")
    finally:
        media._append_call_record_turns = old_append
        voice_call_pipeline.stream_voice_chat_pipeline = old_stream
        minimax_tts.tts_to_audio_bytes = old_tts
        voice_call_tts_cache._CACHE_DIR = old_cache_dir


def test_public_short_audio_auth_boundary() -> None:
    source = (ROOT / "routes" / "miniapp_api.py").read_text(encoding="utf-8")
    assert_true(
        '"/miniapp-api/voice-call/tts-audio/" in request.path' in source,
        "opaque short audio URLs must be downloadable without a header-only panel token",
    )


def main() -> None:
    test_pipeline_visible_stream()
    test_routes_without_external_writes()
    test_public_short_audio_auth_boundary()
    print("voice call stream backend contract ok")


if __name__ == "__main__":
    main()
