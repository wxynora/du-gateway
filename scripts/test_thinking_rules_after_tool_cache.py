import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import pipeline
from services.prompt_cache_debug import build_prompt_cache_profile
from services.upstream_policy import strip_internal_prompt_region_markers


class ThinkingRulesPlacementTest(unittest.TestCase):
    def test_thinking_rules_are_after_tool_cache_breakpoint_before_entry_style(self) -> None:
        body = {
            "messages": [
                {"role": "system", "content": "核心 Prompt"},
                {"role": "system", "content": "其他固定静态规则"},
                {
                    "role": "system",
                    "content": "入口风格",
                    pipeline._ENTRY_STYLE_SYSTEM_MARKER: True,
                },
                {
                    "role": "system",
                    "content": "Real 模式",
                    pipeline._SUMITALK_REAL_MODE_SYSTEM_MARKER: True,
                },
                {
                    "role": "system",
                    "content": "【近期记忆】\n较稳定记忆",
                    pipeline._SUMMARY_CACHE_SYSTEM_MARKER: True,
                },
                {
                    "role": "system",
                    "content": "【近期记忆（最近）】\n最近记忆",
                    pipeline._SUMMARY_RECENT_SYSTEM_MARKER: True,
                },
                {
                    "role": "system",
                    "content": "常驻动态",
                    pipeline._DYNAMIC_SYSTEM_MARKER: True,
                },
                {"role": "user", "content": "你好"},
            ]
        }

        with (
            patch.object(
                pipeline,
                "_load_managed_static_prompt",
                return_value="Thinking 规范",
            ),
            patch(
                "services.tool_result_cache.prompt_system_contents",
                return_value=["工具缓存"],
            ),
        ):
            body = pipeline.step_inject_thinking_block_rules(body)
            body = pipeline.step_inject_tool_result_cache(body)

        self.assertEqual(
            [message["content"] for message in body["messages"]],
            [
                "核心 Prompt\n\n其他固定静态规则",
                "工具缓存",
                "Thinking 规范",
                "入口风格\n\nReal 模式\n\n【近期记忆】\n较稳定记忆\n\n【近期记忆（最近）】\n最近记忆",
                "常驻动态",
                "你好",
            ],
        )
        self.assertTrue(body["messages"][1][pipeline._TOOL_RESULT_CACHE_SYSTEM_MARKER])
        self.assertTrue(body["messages"][2][pipeline._THINKING_RULES_SYSTEM_MARKER])
        self.assertTrue(body["messages"][3][pipeline._SUMMARY_RECENT_SYSTEM_MARKER])

        breakdown = build_prompt_cache_profile(body)["static_breakdown"]
        self.assertIn(
            {"index": 2, "label": "thinking规则"},
            [{"index": item["index"], "label": item["label"]} for item in breakdown],
        )

        strip_internal_prompt_region_markers(body["messages"])
        self.assertNotIn(pipeline._THINKING_RULES_SYSTEM_MARKER, body["messages"][2])


if __name__ == "__main__":
    unittest.main()
