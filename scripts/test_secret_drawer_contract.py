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
        with (
            patch.object(secret_drawer.secret_drawer_store, "stats", return_value={"total": 0}),
            patch.object(secret_drawer.secret_drawer_store, "get_config", return_value={}),
        ):
            prompt = secret_drawer.format_inject_block()
        self.assertIn("图片是 photo，不是 image", prompt)
        self.assertIn("对话是 message，不是 dialog", prompt)
        tool = secret_drawer.get_secret_drawer_tools_for_inject()[0]
        type_schema = tool["function"]["parameters"]["properties"]["payload"]["properties"]["type"]
        self.assertEqual(type_schema["enum"], ["message", "photo", "dream", "note", "surf", "misc"])

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


if __name__ == "__main__":
    unittest.main()
