#!/usr/bin/env python3
"""Pure-local characterization tests for conversation compact storage."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import chat_activity_store, r2_store

conversation_store = sys.modules[r2_store.get_conversation_rounds.__module__]


def test_r2_store_keeps_conversation_exports() -> None:
    names = (
        "append_conversation_round",
        "delete_conversation_round",
        "get_conversation_round_by_index",
        "get_conversation_rounds",
        "get_next_round_index",
        "get_pseudo_cot_state",
        "list_conversation_rounds_preview",
        "normalize_window_id",
        "overwrite_conversation_rounds",
        "save_pseudo_cot_state",
    )
    for name in names:
        assert getattr(r2_store, name) is getattr(conversation_store, name), name
    assert r2_store.CONVERSATION_COMPACT_SCHEMA_VERSION == 2
    assert r2_store.CONVERSATION_RECENT_MAX_ROUNDS == 120


def _round(index: int, timestamp: str, text: str = "") -> dict:
    return {
        "index": index,
        "timestamp": timestamp,
        "messages": [{"role": "user", "content": text or f"round-{index}"}],
    }


def test_window_keys_and_round_merge_contract() -> None:
    assert r2_store.normalize_window_id("") == "__default__"
    assert r2_store.normalize_window_id("  tg_1 ") == "tg_1"
    assert r2_store._conversation_round_key("tg_1", 7) == "windows/tg_1/rounds/000007.json"
    merged = r2_store._merge_rounds_by_index(
        [[_round(2, "2026-07-11T01:00:00"), _round(1, "one")], [_round(2, "2026-07-11T02:00:00"), {"index": 0}]]
    )
    assert [(item["index"], item["timestamp"]) for item in merged] == [
        (1, "one"),
        (2, "2026-07-11T02:00:00"),
    ]


def test_sqlite_hot_read_skips_r2() -> None:
    rounds = [_round(1, "one"), _round(2, "two")]
    sqlite = SimpleNamespace(
        get_window_meta=Mock(return_value={"round_count": 2, "recent_keep": 120}),
        get_rounds=Mock(return_value=rounds),
        max_rounds_per_window=Mock(return_value=250),
    )
    r2_factory = Mock(side_effect=AssertionError("Complete SQLite hot data must skip R2"))
    with (
        patch.object(conversation_store, "conversation_sqlite_store", sqlite),
        patch.object(conversation_store, "_s3_client", r2_factory),
    ):
        assert r2_store.get_conversation_rounds("tg_1", last_n=2) == rounds
    r2_factory.assert_not_called()


def test_r2_fallback_merges_recent_and_backup_without_regression() -> None:
    sqlite = SimpleNamespace(
        get_window_meta=Mock(return_value=None),
        get_rounds=Mock(return_value=[]),
        max_rounds_per_window=Mock(return_value=250),
        import_window_state=Mock(),
    )
    client = object()
    recent = [_round(1, "one"), _round(2, "2026-07-11T01:00:00")]
    backup = [_round(2, "2026-07-11T02:00:00"), _round(3, "three")]
    with (
        patch.object(conversation_store, "conversation_sqlite_store", sqlite),
        patch.object(conversation_store, "_s3_client", return_value=client),
        patch.object(conversation_store, "_ensure_compact_conversation_state", return_value={"last_round_index": 3}),
        patch.object(conversation_store, "_read_recent_rounds", return_value=recent),
        patch.object(conversation_store, "_read_conversation_backup_rounds_for_dates", return_value=backup),
        patch.object(conversation_store, "_conversation_guard_dates", return_value=["fixed"]),
    ):
        result = r2_store.get_conversation_rounds("tg_1", last_n=2)
    assert [(item["index"], item["timestamp"]) for item in result] == [
        (2, "2026-07-11T02:00:00"),
        (3, "three"),
    ]
    sqlite.import_window_state.assert_called_once()


def test_next_index_repairs_stale_meta_from_guard_rounds() -> None:
    sqlite = SimpleNamespace(import_window_state=Mock())
    client = object()
    writer = Mock()
    with (
        patch.object(conversation_store, "conversation_sqlite_store", sqlite),
        patch.object(conversation_store, "_s3_client", return_value=client),
        patch.object(
            conversation_store,
            "_ensure_compact_conversation_state",
            return_value={"last_round_index": 1, "next_round_index": 2, "round_count": 1},
        ),
        patch.object(conversation_store, "_read_recent_rounds", return_value=[_round(4, "four")]),
        patch.object(conversation_store, "_read_conversation_backup_rounds_for_dates", return_value=[]),
        patch.object(conversation_store, "_conversation_guard_dates", return_value=["fixed"]),
        patch.object(conversation_store, "_write_json", writer),
        patch.object(conversation_store, "now_beijing_iso", return_value="now"),
    ):
        assert r2_store.get_next_round_index("tg_1") == 5
    assert writer.call_args.args[1] == "windows/tg_1/conversation_meta.json"
    assert writer.call_args.args[2]["next_round_index"] == 5


def test_append_refuses_blind_write_after_meta_read_failure() -> None:
    client = object()
    writer = Mock(side_effect=AssertionError("Unsafe append must stop before writing"))
    with (
        patch.object(conversation_store, "_s3_client", return_value=client),
        patch.object(conversation_store, "_ensure_compact_conversation_state", return_value={"read_failed": True}),
        patch.object(conversation_store, "_read_recent_rounds", return_value=[]),
        patch.object(conversation_store, "_read_conversation_backup_rounds_for_dates", return_value=[]),
        patch.object(conversation_store, "_conversation_guard_dates", return_value=["fixed"]),
        patch.object(conversation_store, "_write_json", writer),
    ):
        assert r2_store.append_conversation_round("tg_1", 1, []) is False
    writer.assert_not_called()


def test_append_writes_round_recent_meta_backup_and_sqlite() -> None:
    sqlite = SimpleNamespace(
        has_window=Mock(return_value=True),
        upsert_round=Mock(return_value=True),
    )
    client = object()
    writer = Mock()
    messages = [{"role": "user", "content": "hello"}]
    with (
        patch.object(conversation_store, "conversation_sqlite_store", sqlite),
        patch.object(conversation_store, "_s3_client", return_value=client),
        patch.object(
            conversation_store,
            "_ensure_compact_conversation_state",
            return_value={"last_round_index": 1, "next_round_index": 2, "round_count": 1},
        ),
        patch.object(conversation_store, "_read_recent_rounds", return_value=[_round(1, "one")]),
        patch.object(conversation_store, "_read_conversation_backup_rounds_for_dates", return_value=[]),
        patch.object(conversation_store, "_conversation_guard_dates", return_value=["fixed"]),
        patch.object(conversation_store, "_read_json", return_value=None),
        patch.object(conversation_store, "_write_json", writer),
        patch.object(conversation_store, "now_beijing_iso", return_value="now"),
        patch.object(conversation_store, "today_beijing", return_value="2026-07-11"),
        patch.object(chat_activity_store, "append_chat_activity_round", return_value=True),
    ):
        assert r2_store.append_conversation_round("tg_1", 2, messages, timestamp="two", action_note="note") is True
    keys = [call.args[1] for call in writer.call_args_list]
    assert keys == [
        "windows/tg_1/rounds/000002.json",
        "windows/tg_1/recent_rounds.json",
        "windows/tg_1/conversation_meta.json",
        "conversations/2026-07-11/window_tg_1.json",
    ]
    sqlite.upsert_round.assert_called_once()
    assert sqlite.upsert_round.call_args.args[1]["action_note"] == "note"


def test_round_by_index_prefers_compact_object() -> None:
    compact = _round(5, "five")
    sqlite = SimpleNamespace(has_window=Mock(return_value=True), upsert_round=Mock(return_value=True))
    client = object()
    with (
        patch.object(conversation_store, "conversation_sqlite_store", sqlite),
        patch.object(conversation_store, "_s3_client", return_value=client),
        patch.object(conversation_store, "_read_json", return_value=compact),
        patch.object(conversation_store, "_read_recent_rounds", side_effect=AssertionError("Compact hit should stop fallback")),
    ):
        assert r2_store.get_conversation_round_by_index("tg_1", 5) == compact
    sqlite.upsert_round.assert_called_once()


def test_pseudo_cot_state_writes_normalized_window() -> None:
    client = object()
    writer = Mock()
    with (
        patch.object(conversation_store, "_s3_client", return_value=client),
        patch.object(conversation_store, "_write_json", writer),
    ):
        assert r2_store.save_pseudo_cot_state("", {"enabled": True}) is True
    writer.assert_called_once_with(
        client,
        "windows/__default__/pseudo_cot_state.json",
        {"enabled": True, "window_id": "__default__"},
    )


def test_preview_text_and_truncation_contract() -> None:
    content = [{"type": "text", "text": "hello"}, {"type": "image_url"}]
    assert r2_store._content_to_text_for_preview(content) == "hello [image_url]"
    client = object()
    row = {
        "index": 1,
        "messages": [
            {"role": "user", "content": "abcdef"},
            {"role": "assistant", "content": "ghijkl"},
        ],
    }
    sqlite = SimpleNamespace(import_window_state=Mock())
    with (
        patch.object(conversation_store, "conversation_sqlite_store", sqlite),
        patch.object(conversation_store, "_s3_client", return_value=client),
        patch.object(conversation_store, "_read_recent_rounds", return_value=[row]),
        patch.object(conversation_store, "_read_conversation_backup_rounds_for_dates", return_value=[]),
        patch.object(conversation_store, "_conversation_guard_dates", return_value=["fixed"]),
        patch.object(conversation_store, "_ensure_compact_conversation_state", return_value={}),
    ):
        preview = r2_store.list_conversation_rounds_preview("tg_1", preview_chars=12)
    assert preview == [{"index": 1, "preview": "user:abcdef …"}]


def test_delete_round_rebuilds_compact_and_sqlite() -> None:
    client = Mock()
    client.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
    sqlite = SimpleNamespace(replace_window_rounds=Mock(return_value=True))
    writer = Mock()
    first = [_round(1, "one"), _round(2, "two")]
    after = [_round(1, "one")]
    with (
        patch.object(conversation_store, "conversation_sqlite_store", sqlite),
        patch.object(conversation_store, "_s3_client", return_value=client),
        patch.object(conversation_store, "_read_recent_rounds", side_effect=[first, after, after]),
        patch.object(conversation_store, "_read_conversation_backup_rounds_for_dates", return_value=[]),
        patch.object(conversation_store, "_conversation_guard_dates", return_value=["fixed"]),
        patch.object(conversation_store, "_write_json", writer),
        patch.object(conversation_store, "now_beijing_iso", return_value="now"),
    ):
        assert r2_store.delete_conversation_round("tg_1", 2) is True
    client.delete_object.assert_called_once_with(
        Bucket=r2_store.R2_BUCKET_NAME,
        Key="windows/tg_1/rounds/000002.json",
    )
    sqlite.replace_window_rounds.assert_called_once()
    assert sqlite.replace_window_rounds.call_args.args[1] == after


def main() -> None:
    tests = [
        test_r2_store_keeps_conversation_exports,
        test_window_keys_and_round_merge_contract,
        test_sqlite_hot_read_skips_r2,
        test_r2_fallback_merges_recent_and_backup_without_regression,
        test_next_index_repairs_stale_meta_from_guard_rounds,
        test_append_refuses_blind_write_after_meta_read_failure,
        test_append_writes_round_recent_meta_backup_and_sqlite,
        test_round_by_index_prefers_compact_object,
        test_pseudo_cot_state_writes_normalized_window,
        test_preview_text_and_truncation_contract,
        test_delete_round_rebuilds_compact_and_sqlite,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    main()
