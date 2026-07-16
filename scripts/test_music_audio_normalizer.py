#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services import music_melody_analyzer
from services.music_audio_normalizer import MusicAudioNormalizationError, prepare_music_audio


def _make_audio(codec: str, suffix: str) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise unittest.SkipTest("ffmpeg 不存在")
    with tempfile.TemporaryDirectory(prefix="du_music_normalizer_test_") as tmp:
        output = Path(tmp) / f"tone.{suffix}"
        cmd = [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.25",
            "-codec:a",
            codec,
            str(output),
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=30)
        return output.read_bytes()


class MusicAudioNormalizerTest(unittest.TestCase):
    max_source = 4 * 1024 * 1024
    max_output = 2 * 1024 * 1024

    def test_common_non_mp3_inputs_are_converted_to_real_mp3(self) -> None:
        cases = [
            ("pcm_s16le", "wav", "pcm_s16le"),
            ("flac", "flac", "flac"),
            ("aac", "m4a", "aac"),
        ]
        for encoder, suffix, expected_codec in cases:
            with self.subTest(suffix=suffix):
                source_bytes = _make_audio(encoder, suffix)
                prepared = prepare_music_audio(
                    source_bytes,
                    max_source_bytes=self.max_source,
                    max_output_bytes=self.max_output,
                )

                self.assertTrue(prepared.converted)
                self.assertEqual(prepared.source_codec, expected_codec)
                self.assertEqual(prepared.audio_format, "mp3")
                self.assertNotEqual(prepared.audio_bytes, source_bytes)

    def test_real_mp3_passes_through_even_if_caller_metadata_is_wrong(self) -> None:
        mp3_bytes = _make_audio("libmp3lame", "mp3")

        prepared = prepare_music_audio(
            mp3_bytes,
            max_source_bytes=self.max_source,
            max_output_bytes=self.max_output,
        )

        self.assertFalse(prepared.converted)
        self.assertEqual(prepared.source_codec, "mp3")
        self.assertEqual(prepared.audio_bytes, mp3_bytes)
        self.assertEqual(prepared.audio_format, "mp3")

    def test_non_audio_is_rejected_before_model_call(self) -> None:
        with self.assertRaisesRegex(MusicAudioNormalizationError, "无法识别音频格式|没有可分析的音频流"):
            prepare_music_audio(
                b"not an audio file",
                max_source_bytes=self.max_source,
                max_output_bytes=self.max_output,
            )

    def test_encrypted_ncm_cache_has_actionable_error(self) -> None:
        with self.assertRaisesRegex(MusicAudioNormalizationError, "加密缓存文件"):
            prepare_music_audio(
                b"CTENFDAM" + b"encrypted-cache",
                max_source_bytes=self.max_source,
                max_output_bytes=self.max_output,
            )

    def test_analyzer_sends_normalized_mp3_for_mislabeled_input(self) -> None:
        wav_bytes = _make_audio("pcm_s16le", "wav")
        captured: dict = {}

        def fake_model(model, title, artist, audio_bytes, audio_format, **kwargs):
            captured["bytes"] = audio_bytes
            captured["format"] = audio_format
            return (
                '{"overall_trend":"平稳","segments":[{"start":0,"end":0.25,"section":"片段","plain":"测试。"}]}',
                {"usage": {}},
            )

        with (
            mock.patch.object(music_melody_analyzer, "get_music_melody_entry", return_value=None),
            mock.patch.object(music_melody_analyzer, "_call_music_model", side_effect=fake_model),
            mock.patch.object(music_melody_analyzer, "save_music_melody_entry", return_value={"id": "test"}),
        ):
            result = music_melody_analyzer.analyze_music_melody(
                title="伪装格式测试",
                audio_bytes=wav_bytes,
                filename="actually-not.mp3",
                mime_type="audio/mpeg",
                force=True,
                duration_seconds=0.25,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(captured["format"], "mp3")
        self.assertNotEqual(captured["bytes"], wav_bytes)

    def test_cache_hit_does_not_probe_or_convert_audio(self) -> None:
        cached = {"id": "already-analyzed"}
        with (
            mock.patch.object(music_melody_analyzer, "get_music_melody_entry", return_value=cached),
            mock.patch.object(music_melody_analyzer, "prepare_music_audio") as prepare,
        ):
            result = music_melody_analyzer.analyze_music_melody(
                title="已经分析过",
                audio_bytes=b"not needed",
            )

        self.assertTrue(result["cached"])
        self.assertEqual(result["entry"], cached)
        prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
