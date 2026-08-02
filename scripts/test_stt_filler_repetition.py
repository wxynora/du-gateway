from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.modules.setdefault("requests", MagicMock())

from services import stt


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected={expected!r} actual={actual!r}")


def main():
    assert_equal(
        stt._compact_long_filler_repetition("嗯" * 12),
        "嗯……嗯……嗯",
        "long uninterrupted filler run",
    )
    assert_equal(
        stt._compact_long_filler_repetition("我就是" + "呃" * 8 + "不知道"),
        "我就是呃……呃……呃不知道",
        "long filler run inside meaningful text",
    )
    assert_equal(
        stt._compact_long_filler_repetition("嗯……嗯……嗯……嗯……嗯"),
        "嗯……嗯……嗯",
        "long filler run already separated by ellipses",
    )
    assert_equal(
        stt._compact_long_filler_repetition("嗯嗯嗯嗯"),
        "嗯嗯嗯嗯",
        "short filler repetition stays verbatim",
    )
    assert_equal(
        stt._compact_long_filler_repetition("快快快快快"),
        "快快快快快",
        "meaningful word repetition stays verbatim",
    )
    assert_equal(
        stt._compact_long_filler_repetition("嗯啊嗯啊嗯啊"),
        "嗯啊嗯啊嗯啊",
        "mixed vocalizations are not treated as one repeated run",
    )
    assert_equal(
        stt._clean_transcript_text("嗯（停顿了约1秒）嗯（停顿了约1秒）"),
        "嗯",
        "existing short pause cleanup stays unchanged",
    )
    assert_equal(
        stt._clean_transcript_text("嗯（停顿了约1秒）" * 5),
        "嗯……嗯……嗯",
        "long filler run with pause notes keeps extended hesitation",
    )

    gemini_result = stt._normalize_transcription_payload(
        {"text": "嗯" * 10, "events": []},
        provider="openrouter",
    )
    with (
        patch.object(stt, "_prepare_audio_for_stt", return_value=(b"audio", "audio/webm", "voice.webm")),
        patch.object(stt, "_normalize_provider", side_effect=lambda value: str(value or "deepgram")),
        patch.object(stt, "VOICE_STT_PROVIDER", "openrouter"),
        patch.object(stt, "VOICE_STT_FALLBACK_PROVIDER", ""),
        patch.object(stt, "_openrouter_transcribe", return_value=gemini_result),
    ):
        result = stt.transcribe_speech(b"audio")
    assert_equal(result["text"], "嗯……嗯……嗯", "Gemini/OpenRouter result boundary")

    with (
        patch.object(stt, "_prepare_audio_for_stt", return_value=(b"audio", "audio/webm", "voice.webm")),
        patch.object(stt, "_normalize_provider", side_effect=lambda value: str(value or "deepgram")),
        patch.object(stt, "VOICE_STT_PROVIDER", "deepgram"),
        patch.object(stt, "VOICE_STT_FALLBACK_PROVIDER", ""),
        patch.object(
            stt,
            "_deepgram_transcribe",
            return_value={"text": "哦" * 9, "audio_observations": "", "events": [], "provider": "deepgram"},
        ),
    ):
        result = stt.transcribe_speech(b"audio")
    assert_equal(result["text"], "哦……哦……哦", "Deepgram result boundary")

    print("stt filler repetition regression: PASS")


if __name__ == "__main__":
    main()
