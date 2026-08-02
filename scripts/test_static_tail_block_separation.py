#!/usr/bin/env python3
"""Regression contract for independent static-tail prompt-cache blocks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import pipeline


class StaticTailBlockSeparationTest(unittest.TestCase):
    def test_static_tail_regions_remain_separate_and_ordered(self) -> None:
        body = {
            "messages": [
                {"role": "system", "content": "core"},
                {
                    "role": "system",
                    "content": "entry",
                    pipeline._ENTRY_STYLE_SYSTEM_MARKER: True,
                },
                {
                    "role": "system",
                    "content": "mode",
                    pipeline._SUMITALK_REAL_MODE_SYSTEM_MARKER: True,
                },
                {
                    "role": "system",
                    "content": "daily",
                    pipeline._DU_DAILY_SYSTEM_MARKER: True,
                },
                {
                    "role": "system",
                    "content": "stable",
                    pipeline._SUMMARY_CACHE_SYSTEM_MARKER: True,
                },
                {
                    "role": "system",
                    "content": "recent",
                    pipeline._SUMMARY_RECENT_SYSTEM_MARKER: True,
                },
                {
                    "role": "system",
                    "content": "dynamic",
                    pipeline._DYNAMIC_SYSTEM_MARKER: True,
                },
                {"role": "user", "content": "hello"},
            ]
        }

        with patch(
            "services.tool_result_cache.prompt_system_contents",
            return_value=["tool-cache"],
        ):
            result = pipeline.step_inject_tool_result_cache(body)

        self.assertEqual(
            [message["content"] for message in result["messages"]],
            [
                "core",
                "tool-cache",
                "entry",
                "mode",
                "daily",
                "stable",
                "recent",
                "dynamic",
                "hello",
            ],
        )
        self.assertTrue(result["messages"][1][pipeline._TOOL_RESULT_CACHE_SYSTEM_MARKER])
        self.assertTrue(result["messages"][2][pipeline._ENTRY_STYLE_SYSTEM_MARKER])
        self.assertTrue(result["messages"][3][pipeline._SUMITALK_REAL_MODE_SYSTEM_MARKER])
        self.assertTrue(result["messages"][5][pipeline._SUMMARY_CACHE_SYSTEM_MARKER])
        self.assertTrue(result["messages"][6][pipeline._SUMMARY_RECENT_SYSTEM_MARKER])
        self.assertTrue(result["messages"][7][pipeline._DYNAMIC_SYSTEM_MARKER])

    def test_missing_recent_region_does_not_merge_the_remaining_tail(self) -> None:
        body = {
            "messages": [
                {"role": "system", "content": "core"},
                {
                    "role": "system",
                    "content": "entry",
                    pipeline._ENTRY_STYLE_SYSTEM_MARKER: True,
                },
                {
                    "role": "system",
                    "content": "stable",
                    pipeline._SUMMARY_CACHE_SYSTEM_MARKER: True,
                },
                {
                    "role": "system",
                    "content": "dynamic",
                    pipeline._DYNAMIC_SYSTEM_MARKER: True,
                },
                {"role": "user", "content": "hello"},
            ]
        }

        with patch(
            "services.tool_result_cache.prompt_system_contents",
            return_value=["tool-cache"],
        ):
            result = pipeline.step_inject_tool_result_cache(body)

        self.assertEqual(
            [message["content"] for message in result["messages"]],
            ["core", "tool-cache", "entry", "stable", "dynamic", "hello"],
        )
        self.assertTrue(result["messages"][3][pipeline._SUMMARY_CACHE_SYSTEM_MARKER])


if __name__ == "__main__":
    unittest.main()
