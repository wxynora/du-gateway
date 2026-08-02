#!/usr/bin/env python3
"""Regression test for verbatim chat-media speech transcripts."""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

from flask import Blueprint, Flask


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ChatMediaTranscribeVerbatimTests(unittest.TestCase):
    def test_short_recording_keeps_all_stt_markers_verbatim(self) -> None:
        from routes.miniapp import media
        from services import stt

        transcript = "嗯（停顿了约1秒）嗯（停顿了约1秒）（笑）好呀（哼唱）啦啦啦～"
        app = Flask("chat-media-transcribe-verbatim")
        bp = Blueprint("chat_media_transcribe_verbatim", __name__, url_prefix="/miniapp-api")
        media.register_routes(bp)
        app.register_blueprint(bp)

        old_transcribe = stt.transcribe_speech
        old_sanitize = stt.sanitize_transcript_for_duration
        old_upload = media.r2_store.upload_sumitalk_chat_media_file

        def reject_sanitizer(*_args, **_kwargs):
            raise AssertionError("chat-media route must not sanitize STT text by duration")

        stt.transcribe_speech = lambda **_kwargs: {
            "text": transcript,
            "audio_observations": "短录音",
            "provider": "gemini",
        }
        stt.sanitize_transcript_for_duration = reject_sanitizer
        media.r2_store.upload_sumitalk_chat_media_file = lambda kind, filename, content, mime_type: {
            "key": "sumitalk/chat-media/audio/test.webm",
            "kind": kind,
            "name": filename,
            "contentType": mime_type,
            "size": len(content),
            "createdAt": "2026-07-24T00:00:00+08:00",
        }
        try:
            response = app.test_client().post(
                "/miniapp-api/chat-media/transcribe",
                data={
                    "audio": (io.BytesIO(b"short-audio"), "voice.webm", "audio/webm"),
                    "mime_type": "audio/webm",
                    "duration_ms": "1800",
                },
                content_type="multipart/form-data",
            )
        finally:
            stt.transcribe_speech = old_transcribe
            stt.sanitize_transcript_for_duration = old_sanitize
            media.r2_store.upload_sumitalk_chat_media_file = old_upload

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["text"], transcript)
        self.assertEqual(payload["attachment"]["transcript"], transcript)
        self.assertEqual(payload["attachment"]["durationMs"], 1800)


if __name__ == "__main__":
    unittest.main(verbosity=2)
