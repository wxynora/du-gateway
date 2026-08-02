import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import pipeline
from services import chat_prompt_injections


class CodexOauthPromptPlacementTest(unittest.TestCase):
    def test_codex_prompt_is_independent_and_before_core_prompt(self) -> None:
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
                    "content": "常驻动态",
                    pipeline._DYNAMIC_SYSTEM_MARKER: True,
                },
                {"role": "user", "content": "你好"},
            ]
        }

        with (
            patch.object(
                chat_prompt_injections,
                "is_local_cliproxyapi_url",
                return_value=True,
            ),
            patch(
                "services.prompt_manager.get_managed_prompt_text",
                return_value="Codex OAuth 专用 Prompt",
            ),
        ):
            body = chat_prompt_injections.inject_codex_oauth_prompt_system(
                body,
                upstream_url="http://127.0.0.1:8317/v1/chat/completions",
            )
            body = chat_prompt_injections.inject_codex_oauth_prompt_system(
                body,
                upstream_url="http://127.0.0.1:8317/v1/chat/completions",
            )

        self.assertEqual(
            [message["content"] for message in body["messages"][:3]],
            [
                "Codex OAuth 专用 Prompt",
                "核心 Prompt",
                "其他固定静态规则",
            ],
        )
        self.assertEqual(
            1,
            sum(
                message.get("content") == "Codex OAuth 专用 Prompt"
                for message in body["messages"]
            ),
        )

        with patch(
            "services.tool_result_cache.prompt_system_contents",
            return_value=["工具缓存"],
        ):
            body = pipeline.step_inject_tool_result_cache(body)

        self.assertEqual(
            body["messages"][0]["content"],
            "Codex OAuth 专用 Prompt\n\n核心 Prompt\n\n其他固定静态规则",
        )

    def test_non_codex_upstream_is_unchanged(self) -> None:
        body = {
            "messages": [
                {"role": "system", "content": "核心 Prompt"},
                {"role": "user", "content": "你好"},
            ]
        }

        with patch.object(
            chat_prompt_injections,
            "is_local_cliproxyapi_url",
            return_value=False,
        ):
            result = chat_prompt_injections.inject_codex_oauth_prompt_system(
                body,
                upstream_url="https://example.test/v1/chat/completions",
            )

        self.assertIs(result, body)

    def test_empty_codex_prompt_is_unchanged(self) -> None:
        body = {
            "messages": [
                {"role": "system", "content": "核心 Prompt"},
                {"role": "user", "content": "你好"},
            ]
        }

        with (
            patch.object(
                chat_prompt_injections,
                "is_local_cliproxyapi_url",
                return_value=True,
            ),
            patch(
                "services.prompt_manager.get_managed_prompt_text",
                return_value="",
            ),
        ):
            result = chat_prompt_injections.inject_codex_oauth_prompt_system(
                body,
                upstream_url="http://127.0.0.1:8317/v1/chat/completions",
            )

        self.assertIs(result, body)


if __name__ == "__main__":
    unittest.main()
