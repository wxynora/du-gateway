#!/usr/bin/env python3
"""Pure-local characterization tests for shared context storage."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import r2_store

context_store = sys.modules[r2_store.get_summary.__module__]


def _body(value: bytes) -> SimpleNamespace:
    return SimpleNamespace(read=Mock(return_value=value))


def test_r2_store_keeps_context_exports() -> None:
    names = (
        "get_summary",
        "save_summary",
        "get_summary_chunks",
        "save_summary_chunks",
        "get_latest_4_rounds_global",
        "update_latest_4_rounds_global",
        "save_recent_image_description",
        "get_recent_image_description_map",
        "has_window_history",
    )
    for name in names:
        assert getattr(r2_store, name) is getattr(context_store, name), name
    assert r2_store.R2_KEY_GLOBAL_SUMMARY == "global/summary.txt"
    assert r2_store.R2_KEY_GLOBAL_SUMMARY_CHUNKS == "global/summary_chunks.json"
    assert r2_store.R2_KEY_IMAGE_DESC_RECENT == "global/image_descriptions_recent.json"
    assert r2_store.IMAGE_DESC_RECENT_LIMIT == 4


def test_summary_read_strips_text_and_handles_missing_client() -> None:
    client = Mock()
    client.get_object.return_value = {"Body": _body(b"  shared context\n")}
    with patch.object(context_store, "_s3_client", return_value=client):
        assert r2_store.get_summary("ignored") == "shared context"
    with patch.object(context_store, "_s3_client", return_value=None):
        assert r2_store.get_summary("ignored") is None


def test_summary_save_backs_up_old_value_before_overwrite() -> None:
    client = Mock()
    client.get_object.return_value = {"Body": _body(b"old summary")}
    with patch.object(context_store, "_s3_client", return_value=client):
        assert r2_store.save_summary("ignored", "new summary") is True
    assert client.put_object.call_count == 2
    backup, current = client.put_object.call_args_list
    assert backup.kwargs["Key"].startswith("global/summary_backups/summary_")
    assert backup.kwargs["Body"] == b"old summary"
    assert current.kwargs == {
        "Bucket": r2_store.R2_BUCKET_NAME,
        "Key": "global/summary.txt",
        "Body": b"new summary",
        "ContentType": "text/plain; charset=utf-8",
    }


def test_summary_chunks_normalize_and_stamp_payload() -> None:
    client = object()
    writer = Mock()
    with (
        patch.object(context_store, "_s3_client", return_value=client),
        patch.object(context_store, "_read_json", return_value={"chunks": "bad", "version": 1}),
    ):
        assert r2_store.get_summary_chunks() == {"chunks": [], "version": 1}
    with (
        patch.object(context_store, "_s3_client", return_value=client),
        patch.object(context_store, "_write_json", writer),
        patch.object(context_store, "now_beijing_iso", return_value="2026-07-11T12:00:00+08:00"),
    ):
        assert r2_store.save_summary_chunks("ignored", {"chunks": "bad", "keep": True}) is True
    writer.assert_called_once_with(
        client,
        "global/summary_chunks.json",
        {
            "chunks": [],
            "keep": True,
            "version": 2,
            "updated_at": "2026-07-11T12:00:00+08:00",
        },
    )


def test_latest4_read_and_write_contract() -> None:
    client = object()
    writer = Mock()
    rounds = [{"index": index} for index in range(1, 7)]
    with (
        patch.object(context_store, "_s3_client", return_value=client),
        patch.object(context_store, "_read_json", return_value={"rounds": rounds}),
    ):
        assert r2_store.get_latest_4_rounds_global() == rounds
    with (
        patch.object(context_store, "_s3_client", return_value=client),
        patch.object(context_store, "_write_json", writer),
    ):
        assert r2_store.update_latest_4_rounds_global(rounds) is True
    writer.assert_called_once_with(
        client,
        r2_store.R2_KEY_LATEST_4_ROUNDS,
        {"rounds": rounds[-4:]},
    )


def test_image_description_upsert_deduplicates_and_keeps_latest_four() -> None:
    client = object()
    writer = Mock()
    existing = {
        "items": [
            {"image_id": f"img-{index}", "description": str(index), "updated_at": f"0{index}"}
            for index in range(1, 5)
        ]
    }
    item = {"image_id": "img-2", "description": "new", "updated_at": "09"}
    with (
        patch.object(context_store, "_read_json", return_value=existing),
        patch.object(context_store, "_write_json", writer),
    ):
        context_store._upsert_recent_image_description_locked(client, "images.json", item)
    payload = writer.call_args.args[2]
    assert [row["image_id"] for row in payload["items"]] == ["img-1", "img-3", "img-4", "img-2"]
    assert payload["limit"] == 4
    assert payload["updated_at"] == "09"


def test_image_description_save_writes_global_and_window_maps() -> None:
    client = object()
    upsert = Mock()
    with (
        patch.object(context_store, "_s3_client", return_value=client),
        patch.object(context_store, "now_beijing_iso", return_value="now"),
        patch.object(context_store, "_upsert_recent_image_description_locked", upsert),
    ):
        assert r2_store.save_recent_image_description(
            "  tg_1 ", " img-1 ", " blue cup ", mime_type=" IMAGE/PNG ", message_id=" m-1 "
        ) is True
    assert [call.args[1] for call in upsert.call_args_list] == [
        "global/image_descriptions_recent.json",
        "windows/tg_1/image_descriptions_recent.json",
    ]
    assert upsert.call_args_list[0].args[2] == {
        "image_id": "img-1",
        "description": "blue cup",
        "window_id": "tg_1",
        "message_id": "m-1",
        "mime_type": "image/png",
        "updated_at": "now",
    }


def test_image_description_map_filters_incomplete_items() -> None:
    client = object()
    rows = {
        "images": [
            {"image_id": " img-1 ", "description": " first "},
            {"image_id": "", "description": "missing id"},
            {"image_id": "img-2", "description": ""},
            "bad",
        ]
    }
    with (
        patch.object(context_store, "_s3_client", return_value=client),
        patch.object(context_store, "_read_json", return_value=rows) as reader,
    ):
        assert r2_store.get_recent_image_description_map("tg_1") == {"img-1": "first"}
    reader.assert_called_once_with(client, "windows/tg_1/image_descriptions_recent.json")


def test_window_history_prefers_meta_and_falls_back_to_backups() -> None:
    client = object()
    recent = Mock(side_effect=AssertionError("Meta hit must stop fallback"))
    with (
        patch.object(context_store, "_s3_client", return_value=client),
        patch.object(
            context_store,
            "_read_conversation_meta_status",
            return_value=({"last_round_index": 3}, True, True),
        ),
        patch.object(context_store, "_read_recent_rounds", recent),
    ):
        assert r2_store.has_window_history("tg_1") is True
    recent.assert_not_called()

    with (
        patch.object(context_store, "_s3_client", return_value=client),
        patch.object(context_store, "_read_conversation_meta_status", return_value=({}, True, True)),
        patch.object(context_store, "_read_recent_rounds", return_value=[]),
        patch.object(context_store, "_conversation_guard_dates", return_value=["fixed"]),
        patch.object(context_store, "_read_conversation_backup_rounds_for_dates", return_value=[{"index": 1}]) as backup,
    ):
        assert r2_store.has_window_history("tg_1") is True
    backup.assert_called_once_with(client, "tg_1", ["fixed"])


def main() -> None:
    tests = [
        test_r2_store_keeps_context_exports,
        test_summary_read_strips_text_and_handles_missing_client,
        test_summary_save_backs_up_old_value_before_overwrite,
        test_summary_chunks_normalize_and_stamp_payload,
        test_latest4_read_and_write_contract,
        test_image_description_upsert_deduplicates_and_keeps_latest_four,
        test_image_description_save_writes_global_and_window_maps,
        test_image_description_map_filters_incomplete_items,
        test_window_history_prefers_meta_and_falls_back_to_backups,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    main()
