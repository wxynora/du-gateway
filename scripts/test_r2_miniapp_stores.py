#!/usr/bin/env python3
"""Pure-local checks for extracted MiniApp, reporting, and StudyRoom stores."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import (
    r2_device_reporting_store,
    r2_miniapp_store,
    r2_store,
    r2_studyroom_store,
)


MINIAPP_EXPORTS = (
    "_miniapp_bg_image_versioned_key",
    "_miniapp_voice_avatar_versioned_key",
    "add_du_notebook_entry",
    "delete_du_notebook_entry",
    "delete_miniapp_call_record",
    "get_du_notebook_entries",
    "get_miniapp_bg_config",
    "get_miniapp_bg_image",
    "get_miniapp_call_records",
    "get_miniapp_daily_report",
    "get_miniapp_daily_whisper",
    "get_miniapp_mood_meter",
    "get_miniapp_voice_avatar",
    "get_miniapp_voice_config",
    "save_du_notebook_entries",
    "save_miniapp_bg_config",
    "save_miniapp_bg_image",
    "save_miniapp_call_records",
    "save_miniapp_daily_report",
    "save_miniapp_daily_whisper",
    "save_miniapp_mood_meter",
    "save_miniapp_voice_avatar",
    "save_miniapp_voice_config",
    "update_du_notebook_entry",
)

DEVICE_EXPORTS = (
    "_device_reporting_config_doc",
    "_ensure_device_reporting_config_bootstrapped",
    "_normalize_device_reporting_config",
    "get_device_reporting_config",
    "is_device_reporting_bucket_enabled",
    "save_device_reporting_config",
    "update_device_reporting_bucket_config",
)

STUDYROOM_EXPORTS = (
    "_normalize_studyroom_item",
    "_normalize_studyroom_log",
    "_trim_study_text",
    "add_studyroom_item",
    "add_studyroom_log",
    "delete_studyroom_item",
    "get_studyroom_data",
    "guess_studyroom_module_id",
    "normalize_studyroom_data",
    "save_studyroom_data",
    "update_studyroom_item",
)


def test_r2_store_keeps_third_cut_exports() -> None:
    for name in MINIAPP_EXPORTS:
        assert getattr(r2_store, name) is getattr(r2_miniapp_store, name), name
    for name in DEVICE_EXPORTS:
        assert getattr(r2_store, name) is getattr(r2_device_reporting_store, name), name
    for name in STUDYROOM_EXPORTS:
        assert getattr(r2_store, name) is getattr(r2_studyroom_store, name), name
    assert r2_store.R2_KEY_MINIAPP_BG_CONFIG == "global/miniapp_bg_config.json"
    assert r2_store.R2_KEY_DEVICE_REPORTING_CONFIG == "global/device_reporting_config.json"
    assert r2_store.R2_KEY_STUDYROOM == "global/studyroom.json"


def test_versioned_background_write_keeps_latest_alias() -> None:
    client = Mock()
    with patch.object(r2_miniapp_store, "_s3_client", return_value=client):
        assert r2_miniapp_store.save_miniapp_bg_image(b"image", "image/png", image_version=7) is True
    assert client.put_object.call_count == 2
    assert client.put_object.call_args_list[0].kwargs["Key"] == "global/miniapp_bg_image"
    assert client.put_object.call_args_list[1].kwargs["Key"] == "global/miniapp_bg_image_v_7"


def test_dashboard_write_uses_original_key() -> None:
    client = object()
    writer = Mock()
    payload = {"date": "2026-07-11", "text": "hello"}
    with (
        patch.object(r2_miniapp_store, "_s3_client", return_value=client),
        patch.object(r2_miniapp_store, "_write_json", writer),
    ):
        assert r2_miniapp_store.save_miniapp_daily_whisper(payload) is True
    writer.assert_called_once_with(client, "global/miniapp_daily_whisper.json", payload)


def test_call_record_delete_preserves_other_rows() -> None:
    rows = [{"id": "a"}, {"id": "b"}]
    saver = Mock(return_value=True)
    with (
        patch.object(r2_miniapp_store, "get_miniapp_call_records", return_value=rows),
        patch.object(r2_miniapp_store, "save_miniapp_call_records", saver),
    ):
        assert r2_miniapp_store.delete_miniapp_call_record("a") is True
    saver.assert_called_once_with([{"id": "b"}])


def test_notebook_read_sorts_newest_first() -> None:
    client = object()
    with (
        patch.object(r2_miniapp_store, "_s3_client", return_value=client),
        patch.object(
            r2_miniapp_store,
            "_read_json",
            return_value={"items": [{"id": "old", "updated_at": "1"}, {"id": "new", "updated_at": "2"}]},
        ),
    ):
        assert [row["id"] for row in r2_miniapp_store.get_du_notebook_entries()] == ["new", "old"]


def test_device_reporting_sqlite_primary_skips_r2() -> None:
    sqlite = SimpleNamespace(get_config=Mock(return_value={"battery": False}))
    r2_factory = Mock(side_effect=AssertionError("SQLite primary state should avoid an R2 read"))
    with (
        patch.object(r2_device_reporting_store, "device_reporting_store", sqlite),
        patch.object(r2_device_reporting_store, "_DEVICE_REPORTING_CONFIG_BOOTSTRAPPED", True),
        patch.object(r2_device_reporting_store, "_s3_client", r2_factory),
    ):
        assert r2_device_reporting_store.get_device_reporting_config("phone") == {"battery": False}
    r2_factory.assert_not_called()


def test_device_bucket_update_writes_r2_and_sqlite() -> None:
    sqlite = SimpleNamespace(
        DEVICE_REPORTING_BUCKETS=("battery", "screen", "foreground", "location", "usage"),
        DEFAULT_DEVICE_REPORTING_CONFIG={
            "battery": True,
            "screen": True,
            "foreground": True,
            "location": True,
            "usage": True,
        },
        normalize_device_reporting_config=lambda config: {
            key: bool((config or {}).get(key, True))
            for key in ("battery", "screen", "foreground", "location", "usage")
        },
        save_config=Mock(return_value=True),
    )
    client = object()
    writer = Mock()
    with (
        patch.object(r2_device_reporting_store, "device_reporting_store", sqlite),
        patch.object(r2_device_reporting_store, "DEVICE_REPORTING_BUCKETS", sqlite.DEVICE_REPORTING_BUCKETS),
        patch.object(r2_device_reporting_store, "_s3_client", return_value=client),
        patch.object(r2_device_reporting_store, "_read_json", return_value={}),
        patch.object(r2_device_reporting_store, "_write_json", writer),
        patch.object(r2_device_reporting_store, "now_beijing_iso", return_value="fixed"),
    ):
        result = r2_device_reporting_store.update_device_reporting_bucket_config("phone", "screen", False)
    assert result and result["screen"] is False and result["battery"] is True
    sqlite.save_config.assert_called_once_with("phone", result)
    assert writer.call_args.args[1] == "global/device_reporting_config.json"
    assert writer.call_args.args[2]["devices"]["phone"]["screen"] is False


def test_studyroom_guess_and_normalize_contract() -> None:
    assert r2_studyroom_store.guess_studyroom_module_id(content="这是一道错题，包含题干和正确答案") == "wrong_questions"
    assert r2_studyroom_store.guess_studyroom_module_id(content="普通临时资料") == "inbox"
    with patch.object(r2_studyroom_store, "now_beijing_iso", return_value="fixed"):
        item = r2_studyroom_store._normalize_studyroom_item(
            {"id": "x", "title": "Title", "module_id": "bad", "source_type": "bad", "status": "bad"}
        )
    assert item and item["module_id"] == "inbox"
    assert item["source_type"] == "note"
    assert item["status"] == "todo"


def test_studyroom_add_uses_normalized_payload() -> None:
    saved = Mock(return_value=True)
    with (
        patch.object(r2_studyroom_store, "get_studyroom_data", return_value={"items": [], "study_logs": []}),
        patch.object(r2_studyroom_store, "save_studyroom_data", saved),
        patch.object(r2_studyroom_store, "now_beijing_iso", return_value="fixed"),
        patch.object(r2_studyroom_store, "uuid4", return_value=SimpleNamespace(__str__=lambda self: "ignored")),
    ):
        item = r2_studyroom_store.add_studyroom_item({"id": "item-1", "title": "Material"})
    assert item and item["id"] == "item-1" and item["created_at"] == "fixed"
    assert saved.call_args.args[0]["items"][0] == item


def main() -> None:
    tests = [
        test_r2_store_keeps_third_cut_exports,
        test_versioned_background_write_keeps_latest_alias,
        test_dashboard_write_uses_original_key,
        test_call_record_delete_preserves_other_rows,
        test_notebook_read_sorts_newest_first,
        test_device_reporting_sqlite_primary_skips_r2,
        test_device_bucket_update_writes_r2_and_sqlite,
        test_studyroom_guess_and_normalize_contract,
        test_studyroom_add_uses_normalized_payload,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    main()
