#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from flask import Blueprint, Flask

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes.miniapp import settings as settings_routes
from services import sumitalk_block_mode
from storage import sumitalk_block_mode_store


class SumiTalkBlockModePromptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_state_file = sumitalk_block_mode_store.SUMITALK_BLOCK_MODE_FILE
        sumitalk_block_mode_store.SUMITALK_BLOCK_MODE_FILE = Path(self.temp_dir.name) / "sumitalk_block_mode.json"

    def tearDown(self) -> None:
        sumitalk_block_mode_store.SUMITALK_BLOCK_MODE_FILE = self.original_state_file
        self.temp_dir.cleanup()

    def _client(self):
        app = Flask(__name__)
        bp = Blueprint("miniapp_test", __name__)
        settings_routes.register_routes(bp)
        app.register_blueprint(bp, url_prefix="/miniapp-api")
        return app.test_client()

    def test_route_switches_versions_and_saves_full_prompt_together(self) -> None:
        captured: list[str] = []
        original_append = sumitalk_block_mode._append_block_notice_to_global_context
        sumitalk_block_mode._append_block_notice_to_global_context = (
            lambda _created_at, content, reason="": captured.append(content) or True
        )
        try:
            long_text = "第一行\n" + ("完整文案" * 4_000) + "\n最后一行"
            client = self._client()
            first = client.put(
                "/miniapp-api/sumitalk-block-mode",
                json={
                    "enabled": False,
                    "prompt_version_id": "soft-v1",
                    "prompt_version_name": "温和版",
                    "prompt_text": "第一版",
                },
            )
            self.assertEqual(200, first.status_code)
            second = client.put(
                "/miniapp-api/sumitalk-block-mode",
                json={
                    "enabled": True,
                    "prompt_version_id": "strict-v2",
                    "prompt_version_name": "严格版",
                    "prompt_text": long_text,
                },
            )
            self.assertEqual(200, second.status_code)
            body = second.get_json()
            self.assertEqual("strict-v2", body["prompt_version_id"])
            self.assertEqual("严格版", body["prompt_version_name"])
            self.assertEqual(long_text, body["prompt_text"])
            self.assertEqual([long_text], captured)

            persisted = json.loads(sumitalk_block_mode_store.SUMITALK_BLOCK_MODE_FILE.read_text(encoding="utf-8"))
            self.assertTrue(persisted["enabled"])
            self.assertEqual("strict-v2", persisted["prompt_version_id"])
            self.assertEqual("严格版", persisted["prompt_version_name"])
            self.assertEqual(long_text, persisted["prompt_text"])
            self.assertEqual([], list(Path(self.temp_dir.name).glob("*.tmp")))
        finally:
            sumitalk_block_mode._append_block_notice_to_global_context = original_append

    def test_editing_prompt_while_enabled_preserves_reply_segment(self) -> None:
        started = sumitalk_block_mode_store.set_configuration(
            True,
            prompt_version_id="v1",
            prompt_version_name="版本一",
            prompt_text="文案一",
            updated_at="2026-07-22T04:00:00+08:00",
        )
        allowed, consumed = sumitalk_block_mode_store.try_consume_auto_reply(
            "incoming-1",
            now_ts="2026-07-22T04:01:00+08:00",
        )
        self.assertTrue(allowed)
        updated = sumitalk_block_mode_store.set_configuration(
            True,
            prompt_version_id="v2",
            prompt_version_name="版本二",
            prompt_text="文案二",
            updated_at="2026-07-22T04:02:00+08:00",
        )
        self.assertEqual(1, consumed["auto_reply_count"])
        self.assertEqual(1, updated["auto_reply_count"])
        self.assertNotEqual(started["segment_started_at"], consumed["segment_started_at"])
        self.assertEqual(consumed["segment_started_at"], updated["segment_started_at"])
        self.assertEqual("文案二", sumitalk_block_mode_store.get_notice_text())

    def test_persisted_prompt_survives_fresh_reads(self) -> None:
        expected = "重启后仍使用的完整文案\n第二行"
        sumitalk_block_mode_store.set_configuration(
            True,
            prompt_version_id="persisted",
            prompt_version_name="持久版",
            prompt_text=expected,
            updated_at="2026-07-22T04:03:00+08:00",
        )
        first = sumitalk_block_mode_store.get_state()
        second = sumitalk_block_mode_store.get_state()
        self.assertIsNot(first, second)
        self.assertEqual("persisted", second["prompt_version_id"])
        self.assertEqual("持久版", second["prompt_version_name"])
        self.assertEqual(expected, second["prompt_text"])

    def test_auto_reply_uses_selected_prompt_at_most_three_times(self) -> None:
        selected_text = "当前选中的自动回复文案"
        sumitalk_block_mode_store.set_configuration(
            True,
            prompt_version_id="selected",
            prompt_version_name="选中版",
            prompt_text=selected_text,
            updated_at="2026-07-22T04:04:00+08:00",
        )
        captured: list[tuple[str, str]] = []
        original_append = sumitalk_block_mode._append_block_notice_to_global_context
        sumitalk_block_mode._append_block_notice_to_global_context = (
            lambda _created_at, content, reason="": captured.append((content, reason)) or True
        )
        try:
            results = [
                sumitalk_block_mode.maybe_auto_reply_after_sumitalk_assistant(
                    incoming_message_id=f"incoming-{index}",
                    created_at=f"2026-07-22T04:0{index}:00+08:00",
                )
                for index in range(1, 5)
            ]
        finally:
            sumitalk_block_mode._append_block_notice_to_global_context = original_append
        self.assertEqual([True, True, True, False], [item["sent"] for item in results])
        self.assertEqual(
            [(selected_text, "sumitalk_block_mode_auto_reply")] * 3,
            captured,
        )

    def test_archive_message_keeps_existing_role_and_skip_flags(self) -> None:
        captured: dict = {}
        original_resolve = sumitalk_block_mode._resolve_global_archive_window_id
        original_next = sumitalk_block_mode.r2_store.get_next_round_index
        original_append = sumitalk_block_mode.r2_store.append_conversation_round
        original_rounds = sumitalk_block_mode.r2_store.get_conversation_rounds
        original_update = sumitalk_block_mode.r2_store.update_latest_4_rounds_global
        sumitalk_block_mode._resolve_global_archive_window_id = lambda: "tg-test"
        sumitalk_block_mode.r2_store.get_next_round_index = lambda _window_id: 7

        def fake_append(window_id, round_index, messages, **kwargs):
            captured.update(window_id=window_id, round_index=round_index, messages=messages, kwargs=kwargs)
            return True

        sumitalk_block_mode.r2_store.append_conversation_round = fake_append
        sumitalk_block_mode.r2_store.get_conversation_rounds = lambda _window_id, last_n=4: []
        sumitalk_block_mode.r2_store.update_latest_4_rounds_global = lambda _rounds: True
        try:
            self.assertTrue(
                sumitalk_block_mode._append_block_notice_to_global_context(
                    "2026-07-22T04:05:00+08:00",
                    "归档文案",
                    reason="test",
                )
            )
        finally:
            sumitalk_block_mode._resolve_global_archive_window_id = original_resolve
            sumitalk_block_mode.r2_store.get_next_round_index = original_next
            sumitalk_block_mode.r2_store.append_conversation_round = original_append
            sumitalk_block_mode.r2_store.get_conversation_rounds = original_rounds
            sumitalk_block_mode.r2_store.update_latest_4_rounds_global = original_update
        message = captured["messages"][0]
        self.assertEqual("user", message["role"])
        self.assertEqual("归档文案", message["content"])
        self.assertTrue(message["skip_memory_summary"])
        self.assertTrue(message["skip_dynamic_memory"])
        self.assertEqual("sumitalk_block_mode", message["source"])

    def test_legacy_state_migrates_to_existing_default_prompt(self) -> None:
        legacy = {
            "enabled": True,
            "updated_at": "2026-07-21T23:00:00+08:00",
            "auto_reply_count": 2,
        }
        sumitalk_block_mode_store.SUMITALK_BLOCK_MODE_FILE.write_text(
            json.dumps(legacy, ensure_ascii=False),
            encoding="utf-8",
        )
        state = sumitalk_block_mode_store.get_state()
        self.assertEqual("backend-current", state["prompt_version_id"])
        self.assertEqual("当前文案", state["prompt_version_name"])
        self.assertEqual(sumitalk_block_mode_store.BLOCK_NOTICE_TEXT, state["prompt_text"])
        self.assertEqual(2, state["auto_reply_count"])


if __name__ == "__main__":
    unittest.main()
