#!/usr/bin/env python3
from __future__ import annotations

import sys
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import secret_drawer
from storage import secret_drawer_store
from pipeline.pipeline import step_inject_secret_drawer, step_inject_tool_result_cache


class SecretDrawerContractTests(unittest.TestCase):
    def test_r2_none_return_still_means_success(self) -> None:
        client = Mock()
        with (
            patch.object(secret_drawer_store.r2_store, "_s3_client", return_value=client),
            patch.object(secret_drawer_store.r2_store, "_write_json", return_value=None) as write_json,
        ):
            self.assertTrue(secret_drawer_store._write_json("test/key.json", {"ok": True}))
        write_json.assert_called_once_with(client, "test/key.json", {"ok": True})

    def test_r2_exception_returns_failure(self) -> None:
        with (
            patch.object(secret_drawer_store.r2_store, "_s3_client", return_value=Mock()),
            patch.object(secret_drawer_store.r2_store, "_write_json", side_effect=RuntimeError("boom")),
        ):
            self.assertFalse(secret_drawer_store._write_json("test/key.json", {}))

    def test_prompt_and_tool_schema_expose_exact_categories(self) -> None:
        prompt = secret_drawer.format_rule_block()
        self.assertIn("图片是 photo，不是 image", prompt)
        self.assertIn("对话是 message，不是 dialog", prompt)
        tool = secret_drawer.get_secret_drawer_tools_for_inject()[0]
        type_schema = tool["function"]["parameters"]["properties"]["payload"]["properties"]["type"]
        self.assertEqual(type_schema["enum"], ["message", "photo", "dream", "note", "surf", "misc"])

    def test_prompt_places_rules_in_static_and_only_current_state_in_dynamic(self) -> None:
        stats = {
            "total": 3,
            "by_type": {"message": 1, "photo": 1, "note": 1},
            "pinned": 1,
            "sealed": 1,
            "needs整理": 2,
        }
        body = {
            "messages": [
                {"role": "system", "content": "CORE"},
                {"role": "user", "content": "看看抽屉"},
            ]
        }
        with (
            patch.object(secret_drawer.secret_drawer_store, "stats", return_value=stats),
            patch.object(secret_drawer.secret_drawer_store, "get_config") as get_config,
            patch("services.tool_result_cache.prompt_system_contents", return_value=[]),
        ):
            result = step_inject_tool_result_cache(step_inject_secret_drawer(body, "tg_test"))

        static_text = "\n".join(
            str(msg.get("content") or "")
            for msg in result["messages"]
            if msg.get("role") == "system" and not msg.get("__dynamic__")
        )
        dynamic_text = "\n".join(
            str(msg.get("content") or "")
            for msg in result["messages"]
            if msg.get("role") == "system"
            and msg.get("__dynamic__")
            and not msg.get("__temporary_dynamic__")
            and not msg.get("__last4__")
        )

        self.assertIn("你有自己的秘密抽屉", static_text)
        self.assertIn("整理/查看用工具 secret_drawer", static_text)
        self.assertNotIn("当前抽屉：", static_text)
        self.assertIn("###当前秘密抽屉", dynamic_text)
        self.assertIn("当前抽屉：共 3 条。", dynamic_text)
        self.assertNotIn("你有自己的秘密抽屉", dynamic_text)
        self.assertNotIn("PIN 未设置", static_text + dynamic_text)
        get_config.assert_not_called()

    def test_update_rejects_image_instead_of_silently_using_misc(self) -> None:
        result = json.loads(
            secret_drawer.execute_secret_drawer_tool(
                "secret_drawer",
                {"action": "update", "payload": {"id": "sd_1", "type": "image"}},
            )
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "INVALID_TYPE")
        self.assertIn("photo", result["valid_types"])

    def test_save_dream_prefers_assistant_text_then_falls_back_to_user(self) -> None:
        item, error = secret_drawer._build_item_from_payload(
            {"action": "save_dream"},
            {
                "assistant_text": "渡刚刚生成的完整梦境",
                "user_message": {"role": "user", "content": "把这个梦存起来"},
            },
        )
        self.assertEqual(error, "")
        self.assertEqual(item["content"], "渡刚刚生成的完整梦境")

        fallback, error = secret_drawer._build_item_from_payload(
            {"action": "save_dream"},
            {"user_message": {"role": "user", "content": "昨晚梦见下雨了"}},
        )
        self.assertEqual(error, "")
        self.assertEqual(fallback["content"], "昨晚梦见下雨了")


if __name__ == "__main__":
    unittest.main()
