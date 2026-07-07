#!/usr/bin/env python3
"""Smoke tests for SumiTalk recall_message candidate targeting.

Run from repo root:
  .venv/bin/python scripts/test_recall_message_targets.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = Path(tempfile.gettempdir()) / f"du-recall-message-targets-test-{os.getpid()}.sqlite3"
if DB_PATH.exists():
    DB_PATH.unlink()
os.environ["RUNTIME_STATE_DB"] = str(DB_PATH)


def assert_true(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def assert_eq(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r} actual={actual!r}")


def main() -> None:
    from services import recall_message_targets as target_store
    from services.device_action_tools import TOOL_RECALL_MESSAGE, execute_recall_message
    from storage import app_action_store

    body = {
        "messages": [{"role": "user", "content": "hello"}],
        "recall_targets": [
            {"id": "user-a", "text": "第一句", "index": 1, "createdAt": "2026-07-07T00:00:00Z"},
            {"id": "user-b", "text": "第二句", "index": 2, "createdAt": "2026-07-07T00:00:01Z"},
        ],
    }
    saved = target_store.consume_recall_targets_from_body(body, window_id="w1", client_request_id="cr1")
    assert_true(saved.get("saved"), f"recall_targets should be saved: {saved}")
    assert_true("recall_targets" not in body and "recallTargets" not in body, "sidecar must be removed from request body")
    assert_eq(body["messages"][0]["content"], "hello", "normal message body should stay unchanged")

    query = target_store.resolve_recall_message_targets(window_id="w1", client_request_id="cr1")
    assert_true(query.get("needsSelection") and len(query.get("candidates") or []) == 2, f"query should return two candidates: {query}")

    by_index = target_store.resolve_recall_message_targets(window_id="w1", client_request_id="cr1", indexes=2)
    assert_eq(by_index.get("messageIds"), ["user-b"], "index=2 should resolve the second user bubble")

    by_text = target_store.resolve_recall_message_targets(window_id="w1", client_request_id="cr1", target_text="第一句")
    assert_eq(by_text.get("messageIds"), ["user-a"], "exact targetText should resolve one user bubble")

    ambiguous = target_store.resolve_recall_message_targets(window_id="w1", client_request_id="cr1", target_text="句")
    assert_true(ambiguous.get("needsSelection") and not ambiguous.get("messageIds"), f"ambiguous targetText must not execute: {ambiguous}")

    cross_window = target_store.resolve_recall_message_targets(
        window_id="w2",
        candidate_set_id=str(saved.get("candidateSetId") or ""),
    )
    assert_true(cross_window.get("needsSelection") and not cross_window.get("candidates"), f"candidateSetId must stay window-bound: {cross_window}")

    old_now = target_store._utc_now
    base = datetime(2026, 7, 7, 0, 0, 0, tzinfo=timezone.utc)
    ticks = iter(base + timedelta(seconds=i) for i in range(13))
    try:
        target_store._utc_now = lambda: next(ticks)
        for i in range(12):
            target_store.record_recall_targets(
                window_id="w-trim",
                client_request_id=f"cr-{i:02d}",
                targets=[{"id": f"user-{i}", "text": f"text {i}"}],
            )
        trimmed = target_store.resolve_recall_message_targets(window_id="w-trim")
    finally:
        target_store._utc_now = old_now
    trimmed_ids = {item.get("messageId") for item in trimmed.get("candidates") or []}
    assert_eq(len(trimmed_ids), 10, f"only latest ten turns should remain: {trimmed}")
    assert_true("user-0" not in trimmed_ids and "user-1" not in trimmed_ids, f"oldest turns should be pruned: {trimmed_ids}")

    app_action_store._APP_ACTION_BOOTSTRAPPED = True
    app_action_store._publish_app_action = lambda item: None

    query_only = json.loads(execute_recall_message({
        "queryOnly": True,
        "_context": {"window_id": "w1", "client_request_id": "cr1", "reply_target": "device1"},
    }))
    assert_true(query_only.get("ok") and not query_only.get("queued") and query_only.get("needsSelection"), f"queryOnly must not enqueue: {query_only}")
    pending_after_query = app_action_store.poll_app_actions(device_id="device1", surface="chat_ui", window_id="w1")
    assert_eq(len(pending_after_query.get("actions") or []), 0, f"queryOnly should not create app actions: {pending_after_query}")

    enqueued = json.loads(execute_recall_message({
        "index": 2,
        "replyText": "这句话我先收起来。",
        "_context": {"window_id": "w1", "client_request_id": "cr1", "reply_target": "device1"},
    }))
    assert_true(enqueued.get("ok") and enqueued.get("queued"), f"index should enqueue when unique: {enqueued}")
    assert_eq(enqueued.get("messageIds"), ["user-b"], "index enqueue should use resolved message id")
    pending_after_enqueue = app_action_store.poll_app_actions(device_id="device1", surface="chat_ui", window_id="w1")
    assert_eq(len(pending_after_enqueue.get("actions") or []), 1, f"resolved recall should create one chat_ui action: {pending_after_enqueue}")
    queued_payload = (pending_after_enqueue.get("actions") or [{}])[0].get("payload") or {}
    assert_eq(queued_payload.get("replyText"), "这句话我先收起来。", "replyText should survive app action normalization")

    missing_index = json.loads(execute_recall_message({
        "index": 9,
        "_context": {"window_id": "w1", "client_request_id": "cr1", "reply_target": "device1"},
    }))
    assert_true(missing_index.get("ok") and not missing_index.get("queued") and missing_index.get("needsSelection"), f"missing index must not enqueue: {missing_index}")

    frontend_source = (ROOT / "miniapp/src/ui/MainChatScreen.tsx").read_text(encoding="utf-8")
    tool_props = TOOL_RECALL_MESSAGE["function"]["parameters"]["properties"]
    assert_true("replyText" in tool_props, "recall_message tool must expose replyText")
    assert_true("non_user_target" in frontend_source, "frontend must fail mixed user/non-user recall targets")
    assert_true("targets.length !== messageIds.length" in frontend_source, "frontend must not partially execute missing recall targets")
    assert_true("recallReply" in frontend_source, "frontend must render recall reply as Du's replacement message")

    print("recall_message target smoke ok")


if __name__ == "__main__":
    try:
        main()
    finally:
        if DB_PATH.exists() and not os.environ.get("KEEP_RECALL_TARGET_TEST_DB"):
            DB_PATH.unlink()
