#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import types
import unittest
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

from flask import Blueprint, Flask

from routes.miniapp.memory_panel import register_routes
from services import memory_rewrite


class _DeepSeekResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "content": "我记得自己会先直接回应她，再处理事情。",
                                "reason": "去掉第三人称和元身份表述。",
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }


class MemoryRewriteServiceTest(unittest.TestCase):
    def test_preview_uses_current_memory_and_does_not_write(self):
        current = {
            "id": "dynamic-1",
            "content": "渡在面对用户时应该先回应她。",
            "tag": "关系",
            "importance": 4,
            "mention_count": 3,
        }
        with (
            patch.object(memory_rewrite.r2_store, "get_dynamic_memory_list", return_value=[current]),
            patch.object(memory_rewrite.r2_store, "save_dynamic_memory_list") as save_dynamic,
            patch.object(memory_rewrite.r2_store, "save_core_cache_pending") as save_core,
            patch.object(memory_rewrite, "DEEPSEEK_API_KEY", "test-key"),
            patch.object(memory_rewrite, "DEEPSEEK_API_URL", "https://deepseek.test/chat/completions"),
            patch.object(memory_rewrite, "DEEPSEEK_CHAT_MODEL", "deepseek-chat"),
            patch.object(memory_rewrite.requests, "post", return_value=_DeepSeekResponse()) as post,
        ):
            candidate = memory_rewrite.preview_memory_rewrite("dynamic", "dynamic-1")

        self.assertEqual(current["content"], candidate["original_content"])
        self.assertEqual("我记得自己会先直接回应她，再处理事情。", candidate["rewritten_content"])
        self.assertTrue(candidate["changed"])
        save_dynamic.assert_not_called()
        save_core.assert_not_called()
        request_payload = post.call_args.kwargs["json"]
        prompt = request_payload["messages"][0]["content"]
        self.assertIn("使用渡的第一人称", prompt)
        self.assertIn("不新增经历", prompt)
        self.assertIn(current["content"], prompt)

    def test_confirmed_dynamic_rewrite_preserves_metadata_and_refreshes_derived_data(self):
        current = {
            "id": "dynamic-1",
            "content": "渡在面对用户时应该先回应她。",
            "retrieval_text": "旧检索词",
            "tag": "关系",
            "importance": 4,
            "mention_count": 3,
            "last_mentioned": "2026-07-12T10:00:00+08:00",
            "created_at": "2026-07-01T10:00:00+08:00",
        }
        save = Mock(return_value=True)
        with (
            patch.object(memory_rewrite.r2_store, "get_dynamic_memory_list", return_value=[current]),
            patch.object(memory_rewrite.r2_store, "save_dynamic_memory_list", save),
            patch.object(memory_rewrite, "_build_dynamic_retrieval_text", return_value="直接回应 她"),
            patch.object(memory_rewrite, "_refresh_dynamic_index") as refresh_index,
            patch.object(memory_rewrite, "_sync_dynamic_mirror") as sync_mirror,
            patch.object(memory_rewrite, "_record_dynamic_rewrite", return_value=True) as record,
            patch.object(memory_rewrite, "now_beijing_iso", return_value="2026-07-14T12:00:00+08:00"),
        ):
            result = memory_rewrite.apply_memory_rewrite(
                "dynamic",
                "dynamic-1",
                current["content"],
                "我会先直接回应她，再处理事情。",
            )

        saved_item = save.call_args.args[0][0]
        self.assertEqual("我会先直接回应她，再处理事情。", saved_item["content"])
        self.assertEqual("直接回应 她", saved_item["retrieval_text"])
        self.assertEqual(3, saved_item["mention_count"])
        self.assertEqual(current["last_mentioned"], saved_item["last_mentioned"])
        self.assertEqual(current["importance"], saved_item["importance"])
        self.assertEqual("2026-07-14T12:00:00+08:00", saved_item["updated_at"])
        refresh_index.assert_called_once_with(saved_item)
        sync_mirror.assert_called_once_with(save.call_args.args[0])
        record.assert_called_once()
        self.assertTrue(result["changed"])

    def test_confirmed_core_rewrite_only_updates_content_and_updated_at(self):
        current = {
            "id": "core-1",
            "content": "渡要记住用户不喜欢被说教。",
            "tag": "边界",
            "importance": 5,
            "mention_count": 8,
            "promoted_at": "2026-07-01T10:00:00+08:00",
        }
        save = Mock(return_value=True)
        with (
            patch.object(memory_rewrite.r2_store, "get_core_cache_pending", return_value=[current]),
            patch.object(memory_rewrite.r2_store, "save_core_cache_pending", save),
            patch.object(memory_rewrite.r2_store, "_upsert_core_cache_pending_index_safe") as refresh_index,
            patch.object(memory_rewrite, "now_beijing_iso", return_value="2026-07-14T12:00:00+08:00"),
        ):
            result = memory_rewrite.apply_memory_rewrite(
                "core",
                "core-1",
                current["content"],
                "我记得她不喜欢被说教。",
            )

        saved_item = save.call_args.args[0][0]
        self.assertEqual("我记得她不喜欢被说教。", saved_item["content"])
        self.assertEqual(current["tag"], saved_item["tag"])
        self.assertEqual(current["importance"], saved_item["importance"])
        self.assertEqual(current["mention_count"], saved_item["mention_count"])
        self.assertEqual(current["promoted_at"], saved_item["promoted_at"])
        refresh_index.assert_called_once_with([saved_item])
        self.assertTrue(result["changed"])

    def test_stale_preview_cannot_overwrite_newer_memory(self):
        current = {"id": "dynamic-1", "content": "已经被后台更新的新正文"}
        with (
            patch.object(memory_rewrite.r2_store, "get_dynamic_memory_list", return_value=[current]),
            patch.object(memory_rewrite.r2_store, "save_dynamic_memory_list") as save,
        ):
            with self.assertRaises(memory_rewrite.MemoryRewriteConflict):
                memory_rewrite.apply_memory_rewrite(
                    "dynamic",
                    "dynamic-1",
                    "旧正文",
                    "候选正文",
                )
        save.assert_not_called()


class MemoryRewriteRouteTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        bp = Blueprint("memory_rewrite_test", __name__, url_prefix="/miniapp-api")
        register_routes(bp)
        app.register_blueprint(bp)
        self.client = app.test_client()

    def test_preview_and_apply_keep_separate_http_steps(self):
        candidate = {
            "layer": "core",
            "memory_id": "core-1",
            "original_content": "原文",
            "rewritten_content": "候选",
            "reason": "理由",
            "changed": True,
        }
        result = {"layer": "core", "memory_id": "core-1", "changed": True, "warnings": []}
        with (
            patch("services.memory_rewrite.preview_memory_rewrite", return_value=candidate) as preview,
            patch("services.memory_rewrite.apply_memory_rewrite", return_value=result) as apply,
        ):
            preview_response = self.client.post(
                "/miniapp-api/memory-rewrite/preview",
                json={"layer": "core", "memory_id": "core-1"},
            )
            apply_response = self.client.post(
                "/miniapp-api/memory-rewrite/apply",
                json={
                    "layer": "core",
                    "memory_id": "core-1",
                    "original_content": "原文",
                    "rewritten_content": "候选",
                },
            )

        self.assertEqual(200, preview_response.status_code)
        self.assertEqual(candidate, preview_response.get_json()["candidate"])
        preview.assert_called_once_with("core", "core-1")
        self.assertEqual(200, apply_response.status_code)
        self.assertEqual(result, apply_response.get_json()["result"])
        apply.assert_called_once_with("core", "core-1", "原文", "候选")

    def test_memory_debug_returns_dynamic_items_with_the_existing_snapshot(self):
        dynamic_items = [{"id": "dynamic-1", "content": "原始动态记忆", "mention_count": 2}]
        with (
            patch("routes.miniapp.memory_panel.recent_window_store.list_recent_windows", return_value=[]),
            patch.object(memory_rewrite.r2_store, "get_summary", return_value="", create=True),
            patch.object(memory_rewrite.r2_store, "get_dynamic_recall_debug_events", return_value=[], create=True),
            patch.object(memory_rewrite.r2_store, "get_dynamic_ds_audit_events", return_value=[], create=True),
            patch.object(memory_rewrite.r2_store, "get_dynamic_memory_maintenance_report", return_value={}, create=True),
            patch.object(memory_rewrite.r2_store, "get_core_cache_pending", return_value=[]),
            patch.object(memory_rewrite.r2_store, "get_dynamic_memory_list", return_value=dynamic_items),
        ):
            response = self.client.get("/miniapp-api/memory-debug")

        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertEqual(dynamic_items, body["dynamic_memories"])
        self.assertEqual(1, body["dynamic_stats"]["memory_count"])


if __name__ == "__main__":
    unittest.main()
