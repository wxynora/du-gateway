#!/usr/bin/env python3
"""Focused regressions for cross-process followup queue updates and stale wakeup plans."""

from __future__ import annotations

import sys
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import conversation_followup, wakeup_event_log
from storage import r2_store


def test_patch_preserves_followup_added_after_worker_snapshot() -> None:
    old = {
        "id": "followup_old",
        "status": "pending",
        "created_at": "2026-07-31T08:00:00+08:00",
    }
    concurrent = {
        "id": "followup_new",
        "status": "pending",
        "created_at": "2026-07-31T09:00:00+08:00",
    }
    r2_payload = {"items": [dict(old), dict(concurrent)]}
    writes: list[dict] = []

    def fake_write(_client, _key, payload):
        writes.append(payload)

    sent = dict(old)
    sent.update({"status": "sent", "sent_at": "2026-07-31T09:01:00+08:00"})
    with (
        patch.object(r2_store, "_conversation_followups_write_guard", lambda: nullcontext()),
        patch.object(r2_store, "_s3_client", return_value=object()),
        patch.object(r2_store, "_read_json", return_value=r2_payload),
        patch.object(r2_store, "_write_json", side_effect=fake_write),
        patch.object(r2_store.conversation_followup_store, "replace_items", return_value=True),
    ):
        ok, merged = r2_store.patch_conversation_followups({"followup_old": sent})

    assert ok is True
    assert [item["id"] for item in merged] == ["followup_old", "followup_new"]
    assert merged[0]["status"] == "sent"
    assert merged[1] == concurrent
    assert writes[-1]["items"] == merged


def test_queue_followup_mutates_authoritative_queue() -> None:
    existing = [
        {
            "id": "followup_previous",
            "thread_key": "sumitalk:window:test-target",
            "status": "pending",
        },
        {
            "id": "followup_unrelated",
            "thread_key": "sumitalk:window:other-target",
            "status": "pending",
        },
    ]
    saved: list[dict] = []

    def fake_mutate(mutator):
        next_items, result = mutator([dict(item) for item in existing])
        saved.extend(next_items)
        return True, result

    with (
        patch.object(
            conversation_followup,
            "extract_followup_marker",
            return_value=("正文", {"reason": "稍后续一句"}),
        ),
        patch.object(conversation_followup, "detect_reply_channel", return_value="sumitalk"),
        patch.object(conversation_followup, "detect_reply_target", return_value="test-target"),
        patch.object(conversation_followup, "_build_thread_key", return_value="sumitalk:window:test-target"),
        patch.object(conversation_followup.r2_store, "mutate_conversation_followups", side_effect=fake_mutate),
        patch.object(conversation_followup.wakeup_event_log, "cancel_active_event") as cancel_event,
        patch.object(conversation_followup.wakeup_event_log, "plan_event") as plan_event,
    ):
        clean, queued = conversation_followup.queue_followup(
            "sumitalk_window",
            {},
            "ignored",
            created_at="2026-07-31T09:00:00+08:00",
        )

    assert clean == "正文"
    assert queued is True
    assert saved[0]["status"] == "pending"
    assert saved[0]["id"].startswith("followup_")
    assert saved[1]["id"] == "followup_previous"
    assert saved[1]["status"] == "cancelled"
    assert saved[2] == existing[1]
    cancel_event.assert_called_once()
    plan_event.assert_called_once()


def test_tick_reconciles_only_against_merged_pending_queue() -> None:
    old = {
        "id": "followup_old",
        "context_window_id": "sumitalk_window",
        "reply_channel": "sumitalk",
        "reply_target": "target",
        "thread_key": "sumitalk:window:target",
        "chain_id": "chain-old",
        "followup_index": 1,
        "root_created_at": "2026-07-31T08:00:00+08:00",
        "created_at": "2026-07-31T08:00:00+08:00",
        "trigger_at": "2026-07-31T08:05:00+08:00",
        "status": "pending",
        "attempts": 0,
    }
    concurrent = {
        "id": "followup_new",
        "status": "pending",
        "created_at": "2026-07-31T09:00:00+08:00",
        "trigger_at": "2026-07-31T09:05:00+08:00",
    }
    reconciliations: list[dict] = []

    def fake_patch(updates, *, deleted_item_ids=()):
        assert set(updates) == {"followup_old"}
        assert not deleted_item_ids
        return True, [dict(updates["followup_old"]), dict(concurrent)]

    def fake_reconcile(**kwargs):
        reconciliations.append(dict(kwargs))
        return 1

    with (
        patch.object(conversation_followup, "now_beijing_iso", return_value="2026-07-31T09:00:30+08:00"),
        patch.object(conversation_followup.r2_store, "get_conversation_followups", return_value=[dict(old)]),
        patch.object(conversation_followup.r2_store, "patch_conversation_followups", side_effect=fake_patch),
        patch.object(conversation_followup, "_has_new_user_activity", return_value=False),
        patch.object(conversation_followup, "_call_gateway_followup", return_value="续话正文"),
        patch.object(conversation_followup, "_dispatch_followup", return_value=True),
        patch.object(conversation_followup.wakeup_event_log, "start_event", return_value={"event_id": "event-old"}),
        patch.object(conversation_followup.wakeup_event_log, "finish_event"),
        patch.object(conversation_followup.wakeup_event_log, "cancel_missing_plans", side_effect=fake_reconcile),
        patch("services.sumitalk_block_mode.maybe_auto_reply_after_sumitalk_assistant", return_value=None),
    ):
        result = conversation_followup.tick_conversation_followups()

    assert result["ok"] is True
    assert result["sent"] == 1
    assert reconciliations == [
        {
            "kind": "followup",
            "active_source_keys": {"followup:followup_new"},
            "reason": "对应续话任务已不存在",
            "updated_before": "2026-07-31T09:00:30+08:00",
        }
    ]


def test_reconciliation_does_not_cancel_plans_created_at_or_after_tick_start() -> None:
    with TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "wakeup.sqlite3")
        original_ready = wakeup_event_log._SCHEMA_READY
        wakeup_event_log._SCHEMA_READY = False
        try:
            with patch.object(wakeup_event_log, "WAKEUP_STATE_DB", db_path):
                with patch.object(wakeup_event_log, "now_beijing_iso", return_value="2026-07-31T08:59:59+08:00"):
                    old = wakeup_event_log.plan_event(
                        kind="followup",
                        source_key="followup:missing-old",
                        planned_at="2026-07-31T09:05:00+08:00",
                        reason="旧计划",
                    )
                with patch.object(wakeup_event_log, "now_beijing_iso", return_value="2026-07-31T09:00:30+08:00"):
                    new = wakeup_event_log.plan_event(
                        kind="followup",
                        source_key="followup:just-created",
                        planned_at="2026-07-31T09:10:00+08:00",
                        reason="新计划",
                    )
                    count = wakeup_event_log.cancel_missing_plans(
                        kind="followup",
                        active_source_keys=set(),
                        reason="对应续话任务已不存在",
                        updated_before="2026-07-31T09:00:30+08:00",
                    )

                assert count == 1
                assert wakeup_event_log.get_event(old["event_id"])["status"] == "cancelled"
                assert wakeup_event_log.get_event(new["event_id"])["status"] == "planned"
        finally:
            wakeup_event_log._SCHEMA_READY = original_ready


if __name__ == "__main__":
    test_patch_preserves_followup_added_after_worker_snapshot()
    test_queue_followup_mutates_authoritative_queue()
    test_tick_reconciles_only_against_merged_pending_queue()
    test_reconciliation_does_not_cancel_plans_created_at_or_after_tick_start()
    print("followup queue reconciliation tests passed")
