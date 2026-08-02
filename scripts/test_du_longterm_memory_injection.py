#!/usr/bin/env python3
"""Regression contract for long-term memory storage and prompt placement."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import pipeline
from services import du_longterm_memory


class DuLongtermMemoryInjectionTest(unittest.TestCase):
    def test_format_block_includes_coverage_boundary(self) -> None:
        block = du_longterm_memory.format_inject_block(
            {
                "content": "一段长期记忆。",
                "covered_through": "2026-07-12",
            }
        )

        self.assertEqual(
            block,
            "【长期记忆（截至 2026-07-12）】\n一段长期记忆。\n【以上为长期记忆】",
        )

    def test_longterm_is_an_independent_static_block_before_midterm(self) -> None:
        body = {
            "messages": [
                {"role": "system", "content": "core"},
                {
                    "role": "system",
                    "content": "dynamic",
                    pipeline._DYNAMIC_SYSTEM_MARKER: True,
                },
                {"role": "user", "content": "hello"},
            ]
        }

        with patch.object(
            du_longterm_memory,
            "get_latest_longterm_memory",
            return_value={
                "content": "一段长期记忆。",
                "covered_through": "2026-07-12",
            },
        ):
            body = du_longterm_memory.inject_into_static_system(body)
        with (
            patch("services.du_midterm_memory.refresh_if_due_background"),
            patch(
                "services.du_midterm_memory.format_inject_block",
                return_value="【最近一段时间（2026-07-13 至 2026-07-26）】\n中期正文\n【以上为最近一段时间】",
            ),
        ):
            body = pipeline.step_inject_du_midterm_memory(body, "window")

        contents = [str(message.get("content") or "").strip() for message in body["messages"]]
        self.assertEqual(
            contents,
            [
                "core",
                "【长期记忆（截至 2026-07-12）】\n一段长期记忆。\n【以上为长期记忆】",
                "【最近一段时间（2026-07-13 至 2026-07-26）】\n中期正文\n【以上为最近一段时间】",
                "dynamic",
                "hello",
            ],
        )
        self.assertIsNot(body["messages"][1], body["messages"][2])

    def test_chat_pipeline_calls_longterm_before_midterm(self) -> None:
        source = (ROOT / "routes" / "chat.py").read_text(encoding="utf-8")
        longterm_call = "body = inject_du_longterm_memory(body)"
        midterm_call = "body = step_inject_du_midterm_memory(body, window_id)"

        self.assertIn(longterm_call, source)
        self.assertIn(midterm_call, source)
        self.assertLess(source.index(longterm_call), source.index(midterm_call))


if __name__ == "__main__":
    unittest.main()
