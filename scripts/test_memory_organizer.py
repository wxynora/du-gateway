from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

from flask import Blueprint, Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routes.miniapp.memory_organizer import register_routes
from storage import memory_organizer_store, r2_store, recent_window_store


def _dynamic_items(count: int) -> list[dict]:
    items = []
    for index in range(count):
        tag = "日常"
        if index == 0:
            tag = "图书馆"
        elif index == 2:
            tag = "卧室"
        items.append(
            {
                "id": f"dynamic-{index:04d}",
                "content": f"动态记忆 {index}",
                "tag": tag,
                "importance": index % 5,
                "mention_count": index % 3,
                "created_at": "2026-01-01T00:00:00+08:00",
                "updated_at": f"2026-07-{(index % 20) + 1:02d}T12:00:00+08:00",
                "last_mentioned": "2026-01-01T00:00:00+08:00",
            }
        )
    return items


def _core_items(count: int) -> list[dict]:
    items = []
    for index in range(count):
        item = {
            "id": f"core-{index:04d}",
            "content": f"核心记忆 {index}",
            "promoted_at": f"2026-06-{(index % 20) + 1:02d}T12:00:00+08:00",
            "source_memory_id": "dynamic-0001" if index == 0 else "",
        }
        if index % 5 == 0:
            item["pending_merge"] = {"candidate": f"核心候选 {index}"}
        items.append(item)
    return items


def _audit_items(count: int) -> list[dict]:
    return [
        {
            "event_id": f"audit-{index:04d}",
            "timestamp": f"2026-07-{(index % 20) + 1:02d}T12:00:00+08:00",
            "final_action": "merge" if index % 2 else "new",
        }
        for index in range(count)
    ]


class MemoryOrganizerApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dynamic_items = _dynamic_items(568)
        self.core_items = _core_items(321)
        self.audit_items = _audit_items(95)

        self.db_path_patcher = patch.object(
            memory_organizer_store,
            "db_path",
            return_value=Path(self.temp_dir.name) / "memory-organizer.sqlite3",
        )
        self.db_path_patcher.start()
        memory_organizer_store._SCHEMA_PATH = ""

        self.patchers = [
            patch.object(r2_store, "get_dynamic_memory_list", side_effect=lambda: list(self.dynamic_items)),
            patch.object(r2_store, "get_core_cache_pending", side_effect=lambda: list(self.core_items)),
            patch.object(r2_store, "get_dynamic_ds_audit_events", side_effect=lambda limit=300: list(self.audit_items)),
            patch.object(r2_store, "get_summary", return_value="这是一段轻量记忆总结。"),
            patch.object(
                r2_store,
                "get_dynamic_recall_debug_events",
                side_effect=AssertionError("memory organizer must not read recall events"),
            ),
            patch.object(recent_window_store, "list_recent_windows", return_value=[{"id": "tg_test"}]),
        ]
        self.mocks = [patcher.start() for patcher in self.patchers]

        app = Flask(__name__)
        blueprint = Blueprint("memory_organizer_test", __name__, url_prefix="/miniapp-api")
        register_routes(blueprint)
        app.register_blueprint(blueprint)
        app.testing = True
        self.client = app.test_client()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.db_path_patcher.stop()
        memory_organizer_store._SCHEMA_PATH = ""
        self.temp_dir.cleanup()

    def _collect_pages(self, path: str, query: dict | None = None):
        params = dict(query or {})
        response = self.client.get(path, query_string=params)
        self.assertEqual(response.status_code, 200, response.get_json())
        self._assert_metrics(response)
        first = response.get_json()
        revision = first["revision"]
        items = list(first["items"])
        deleted_ids = list(first["deleted_ids"])
        while first["has_more"]:
            params = {
                "cursor": first["next_cursor"],
                "revision": revision,
                "limit": (query or {}).get("limit", 40),
            }
            response = self.client.get(path, query_string=params)
            self.assertEqual(response.status_code, 200, response.get_json())
            self._assert_metrics(response)
            first = response.get_json()
            self.assertEqual(first["revision"], revision)
            items.extend(first["items"])
            deleted_ids.extend(first["deleted_ids"])
        return revision, items, deleted_ids

    def test_summary_is_small_and_does_not_read_audit_or_recall_events(self):
        response = self.client.get("/miniapp-api/memory-organizer/summary")
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertEqual(payload["dynamic"]["total_count"], 568)
        self.assertEqual(payload["core"]["all_count"], 321)
        self.assertEqual(payload["core"]["pending_count"], 65)
        self.assertLess(len(response.get_data()), 50 * 1024)
        self.assertEqual(self.mocks[2].call_count, 0)
        self.assertEqual(self.mocks[4].call_count, 0)
        self._assert_metrics(response, expected_items=889)

    def test_dynamic_and_core_snapshots_page_without_duplicates_or_gaps(self):
        first_dynamic = self.client.get("/miniapp-api/memory-organizer/dynamic")
        self.assertEqual(first_dynamic.status_code, 200, first_dynamic.get_json())
        self.assertEqual(len(first_dynamic.get_json()["items"]), 40)
        self._assert_metrics(first_dynamic, expected_items=40)

        _, dynamic_items, dynamic_deleted = self._collect_pages(
            "/miniapp-api/memory-organizer/dynamic",
            {"limit": 37},
        )
        dynamic_ids = [item["id"] for item in dynamic_items]
        self.assertEqual(len(dynamic_ids), 568)
        self.assertEqual(len(set(dynamic_ids)), 568)
        self.assertEqual(dynamic_deleted, [])

        dynamic_by_id = {item["id"]: item for item in dynamic_items}
        self.assertEqual(dynamic_by_id["dynamic-0000"]["prune_at"], "")
        self.assertFalse(dynamic_by_id["dynamic-0000"]["at_risk"])
        self.assertTrue(dynamic_by_id["dynamic-0001"]["core_protected"])
        self.assertEqual(dynamic_by_id["dynamic-0001"]["prune_at"], "")
        self.assertTrue(dynamic_by_id["dynamic-0002"]["at_risk"])
        self.assertTrue(dynamic_by_id["dynamic-0002"]["prune_at"])

        _, core_items, core_deleted = self._collect_pages(
            "/miniapp-api/memory-organizer/core",
            {"limit": 43, "filter": "all"},
        )
        core_ids = [item["id"] for item in core_items]
        self.assertEqual(len(core_ids), 321)
        self.assertEqual(len(set(core_ids)), 321)
        self.assertEqual(core_deleted, [])

        _, pending_items, _ = self._collect_pages(
            "/miniapp-api/memory-organizer/core",
            {"filter": "pending"},
        )
        self.assertEqual(len(pending_items), 65)
        self.assertTrue(all(item["review_pending"] for item in pending_items))
        self.assertEqual(self.mocks[4].call_count, 0)

    def test_cursor_keeps_the_first_snapshot_when_r2_changes_mid_pagination(self):
        first_response = self.client.get(
            "/miniapp-api/memory-organizer/dynamic",
            query_string={"limit": 40},
        )
        self.assertEqual(first_response.status_code, 200, first_response.get_json())
        first_page = first_response.get_json()
        first_ids = [item["id"] for item in first_page["items"]]
        revision = first_page["revision"]

        self.dynamic_items = []
        collected_ids = list(first_ids)
        page = first_page
        while page["has_more"]:
            response = self.client.get(
                "/miniapp-api/memory-organizer/dynamic",
                query_string={
                    "cursor": page["next_cursor"],
                    "revision": revision,
                    "limit": 40,
                },
            )
            self.assertEqual(response.status_code, 200, response.get_json())
            page = response.get_json()
            collected_ids.extend(item["id"] for item in page["items"])

        self.assertEqual(len(collected_ids), 568)
        self.assertEqual(len(set(collected_ids)), 568)
        self.assertEqual(self.mocks[0].call_count, 1)

    def test_revision_returns_only_changes_and_deletions_then_not_modified(self):
        old_revision, _, _ = self._collect_pages(
            "/miniapp-api/memory-organizer/dynamic",
            {"limit": 50},
        )
        self.dynamic_items = [
            item for item in self.dynamic_items if item["id"] != "dynamic-0007"
        ]
        for item in self.dynamic_items:
            if item["id"] == "dynamic-0010":
                item["content"] = "动态记忆 10 已修改"
        self.dynamic_items.append(
            {
                "id": "dynamic-new",
                "content": "新增动态记忆",
                "tag": "日常",
                "importance": 3,
                "mention_count": 0,
                "created_at": "2026-07-26T12:00:00+08:00",
                "updated_at": "2026-07-26T12:00:00+08:00",
                "last_mentioned": "2026-07-26T12:00:00+08:00",
            }
        )

        new_revision, changed_items, deleted_ids = self._collect_pages(
            "/miniapp-api/memory-organizer/dynamic",
            {"revision": old_revision, "limit": 2},
        )
        self.assertNotEqual(new_revision, old_revision)
        self.assertEqual({item["id"] for item in changed_items}, {"dynamic-0010", "dynamic-new"})
        self.assertEqual(deleted_ids, ["dynamic-0007"])

        response = self.client.get(
            "/miniapp-api/memory-organizer/dynamic",
            query_string={"revision": new_revision},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertTrue(payload["not_modified"])
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["deleted_ids"], [])
        self.assertFalse(payload["has_more"])
        self.assertEqual(len(response.get_data()), int(response.headers["X-Memory-Organizer-Response-Bytes"]))

    def test_audit_details_are_only_loaded_by_their_paginated_endpoint(self):
        summary = self.client.get("/miniapp-api/memory-organizer/summary")
        self.assertEqual(summary.status_code, 200, summary.get_json())
        self.assertEqual(self.mocks[2].call_count, 0)

        _, audit_items, deleted_ids = self._collect_pages(
            "/miniapp-api/memory-organizer/audit",
            {"limit": 31},
        )
        self.assertEqual(len(audit_items), 95)
        self.assertEqual(len({item["id"] for item in audit_items}), 95)
        self.assertEqual(deleted_ids, [])
        self.assertEqual(self.mocks[2].call_count, 1)
        self.assertEqual(self.mocks[4].call_count, 0)

    def _assert_metrics(self, response, expected_items: int | None = None):
        self.assertGreaterEqual(float(response.headers["X-Memory-Organizer-Elapsed-Ms"]), 0)
        self.assertEqual(
            int(response.headers["X-Memory-Organizer-Response-Bytes"]),
            len(response.get_data()),
        )
        if expected_items is not None:
            self.assertEqual(int(response.headers["X-Memory-Organizer-Item-Count"]), expected_items)


if __name__ == "__main__":
    unittest.main()
