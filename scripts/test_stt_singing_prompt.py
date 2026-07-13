#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.stt import _VOICE_TRANSCRIBE_PROMPT


class SttSingingPromptTests(unittest.TestCase):
    def test_sung_lyrics_must_not_be_flattened_to_speech(self) -> None:
        self.assertIn("明显听出旋律性的音高变化", _VOICE_TRANSCRIBE_PROMPT)
        self.assertIn("即使歌词听得很清楚，整段仍是唱歌", _VOICE_TRANSCRIBE_PROMPT)
        self.assertIn("（哼唱）嗯嗯……（唱歌）", _VOICE_TRANSCRIBE_PROMPT)
        self.assertIn("不能把歌词当普通说话转写", _VOICE_TRANSCRIBE_PROMPT)

    def test_ambiguous_prosody_is_not_forced_to_singing(self) -> None:
        self.assertIn("只有单个拖长音、语气起伏或证据不足时", _VOICE_TRANSCRIBE_PROMPT)
        self.assertIn("不要猜成唱歌", _VOICE_TRANSCRIBE_PROMPT)

    def test_continuous_singing_is_labeled_once(self) -> None:
        self.assertIn("连续保持同一种方式时只标一次", _VOICE_TRANSCRIBE_PROMPT)
        self.assertIn("不要只在 `events` 里写“唱歌”", _VOICE_TRANSCRIBE_PROMPT)


if __name__ == "__main__":
    unittest.main()
