#!/usr/bin/env python3
"""Shared merge rules and plain-text memory rewrite contract; no external writes."""

from __future__ import annotations

import sys
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

storage_package = types.ModuleType("storage")
storage_package.__path__ = [str(ROOT / "storage")]
fake_r2_store = types.ModuleType("storage.r2_store")
fake_r2_store.get_dynamic_memory_list = lambda: []
fake_r2_store.save_dynamic_memory_list = lambda _items: False
fake_r2_store.get_core_cache_pending = lambda: []
fake_r2_store.save_core_cache_pending = lambda _items: False
fake_r2_store._upsert_core_cache_pending_index_safe = lambda _items: None
sys.modules.setdefault("storage", storage_package)
sys.modules.setdefault("storage.r2_store", fake_r2_store)
storage_package.r2_store = fake_r2_store

requests_module = types.ModuleType("requests")
requests_module.post = lambda *_args, **_kwargs: None
sys.modules.setdefault("requests", requests_module)

from services import dynamic_layer_ds, memory_rewrite


class _DeepSeekResponse:
    def __init__(self, content: str) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": self.content,
                    }
                }
            ]
        }


class MemoryRewriteSharedMergeTest(unittest.TestCase):
    def _request_patches(self, responses: list[_DeepSeekResponse]) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(patch.object(memory_rewrite, "DEEPSEEK_API_KEY", "test-key"))
        stack.enter_context(
            patch.object(memory_rewrite, "DEEPSEEK_API_URL", "https://deepseek.test/chat/completions")
        )
        stack.enter_context(patch.object(memory_rewrite, "DEEPSEEK_CHAT_MODEL", "deepseek-chat"))
        stack.post = stack.enter_context(
            patch.object(memory_rewrite.requests, "post", side_effect=responses)
        )
        return stack

    def test_dynamic_and_manual_rewrite_use_the_same_merge_rules(self):
        from services.memory_merge_rules import MERGE_ITERATION_RULES

        item = {"id": "core-1", "content": "正式原文"}
        rewrite_prompt = memory_rewrite._rewrite_prompt(
            "core",
            item,
            "按修正重新融合。",
        )

        self.assertIn(MERGE_ITERATION_RULES, dynamic_layer_ds._DYNAMIC_LAYER_PROMPT)
        self.assertIn(MERGE_ITERATION_RULES, rewrite_prompt)
        self.assertIn("未冲突内容继续按合并同类项处理", MERGE_ITERATION_RULES)
        self.assertIn("不能只写本轮新发生的事", MERGE_ITERATION_RULES)

    def test_dynamic_preview_accepts_plain_text_and_never_writes(self):
        current = {
            "id": "dynamic-1",
            "content": "我以前总会回避争执。",
            "tag": "关系",
        }
        rewritten = "我以前总会回避争执，后来开始愿意把问题说清楚。"
        save_dynamic = Mock()
        save_core = Mock()
        with (
            patch.object(memory_rewrite.r2_store, "get_dynamic_memory_list", return_value=[current]),
            patch.object(memory_rewrite.r2_store, "save_dynamic_memory_list", save_dynamic),
            patch.object(memory_rewrite.r2_store, "save_core_cache_pending", save_core),
            self._request_patches([_DeepSeekResponse(rewritten)]),
        ):
            candidate = memory_rewrite.preview_memory_rewrite(
                "dynamic",
                "dynamic-1",
                "保留过去的情况，再写清后来发生的变化。",
            )

        self.assertEqual(rewritten, candidate["rewritten_content"])
        self.assertEqual("", candidate["reason"])
        self.assertTrue(candidate["changed"])
        save_dynamic.assert_not_called()
        save_core.assert_not_called()

    def test_core_prompt_contains_formal_pending_reason_and_user_correction(self):
        current = {
            "id": "core-1",
            "content": "我不喜欢出门。",
            "tag": "偏好",
            "pending_merge": {
                "original_content": "我不喜欢出门。",
                "rewritten_content": "我始终拒绝出门。",
                "reason": "本轮召回核心记忆后生成的 merge 候选",
                "merge_reason": "supersede",
            },
        }
        instruction = "现在会在天气舒服时出门，旧候选的绝对判断不对。"
        rewritten = "我以前不喜欢出门，现在天气舒服时也愿意出去走走。"
        save_core = Mock()
        with (
            patch.object(memory_rewrite.r2_store, "get_core_cache_pending", return_value=[current]),
            patch.object(memory_rewrite.r2_store, "save_core_cache_pending", save_core),
            self._request_patches([_DeepSeekResponse(rewritten)]) as request_patches,
        ):
            candidate = memory_rewrite.preview_memory_rewrite(
                "core",
                "core-1",
                instruction,
            )

        prompt = request_patches.post.call_args.kwargs["json"]["messages"][0]["content"]
        self.assertIn("original_content", prompt)
        self.assertIn(current["content"], prompt)
        self.assertIn("pending_candidate", prompt)
        self.assertIn(current["pending_merge"]["rewritten_content"], prompt)
        self.assertIn("merge_reason", prompt)
        self.assertIn("supersede", prompt)
        self.assertIn("rewrite_instructions", prompt)
        self.assertIn(instruction, prompt)
        self.assertIn("最高优先级", prompt)
        self.assertIn("只返回完整的新版记忆正文", prompt)
        self.assertNotIn('{"content"', prompt)
        self.assertEqual(rewritten, candidate["rewritten_content"])
        self.assertEqual("", candidate["reason"])
        save_core.assert_not_called()

    def test_each_invalid_plain_text_shape_retries_once(self):
        original = "旧正文。"
        valid = "旧正文里的判断后来被修正了。"
        invalid_outputs = (
            "",
            original,
            "抱歉，我无法按要求修改这条记忆。",
            '{"content":"JSON 候选"}',
            "```text\n代码块候选\n```",
            "修改后的记忆：这里是候选正文。",
        )
        for invalid in invalid_outputs:
            with self.subTest(invalid=invalid):
                with self._request_patches(
                    [_DeepSeekResponse(invalid), _DeepSeekResponse(valid)]
                ) as request_patches:
                    rewritten, reason = memory_rewrite._request_deepseek_rewrite(
                        "dynamic",
                        {"id": "dynamic-1", "content": original},
                        "重新融合。",
                    )

                self.assertEqual(valid, rewritten)
                self.assertEqual("", reason)
                self.assertEqual(2, request_patches.post.call_count)
                retry_prompt = request_patches.post.call_args_list[1].kwargs["json"][
                    "messages"
                ][0]["content"]
                self.assertIn("上一次结果不可用", retry_prompt)
                self.assertIn("只返回完整的新版记忆正文", retry_prompt)

    def test_two_invalid_results_raise_accurate_502_error(self):
        with self._request_patches(
            [_DeepSeekResponse(""), _DeepSeekResponse("")]
        ) as request_patches:
            with self.assertRaisesRegex(
                memory_rewrite.MemoryRewriteUpstreamError,
                "连续两次.*完整记忆正文",
            ):
                memory_rewrite._request_deepseek_rewrite(
                    "core",
                    {"id": "core-1", "content": "正式原文"},
                    "重新生成。",
                )

        self.assertEqual(2, request_patches.post.call_count)


if __name__ == "__main__":
    unittest.main()
