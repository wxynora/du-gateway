#!/usr/bin/env python3
"""Pure-local compatibility checks for extracted R2 object stores."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import r2_media_store, r2_sticker_store, r2_store


STICKER_EXPORTS = (
    "_merge_default_sticker_meta",
    "_sticker_reserved_keys",
    "add_sticker_category",
    "delete_sticker_object",
    "get_sticker_tag_keys",
    "get_stickers_mapping",
    "get_stickers_meta",
    "rebuild_stickers_mapping_from_r2",
    "save_stickers_mapping",
    "save_stickers_meta",
    "upload_sticker_file",
)

MEDIA_EXPORTS = (
    "_sumitalk_chat_media_ext",
    "get_device_screenshot",
    "get_object_bytes",
    "get_sumitalk_chat_media_file",
    "save_device_screenshot",
    "upload_sumitalk_chat_media_file",
    "upload_sumitalk_chat_media_thumbnail_file",
)


def test_r2_store_keeps_object_store_exports() -> None:
    for name in STICKER_EXPORTS:
        assert getattr(r2_store, name) is getattr(r2_sticker_store, name), name
    for name in MEDIA_EXPORTS:
        assert getattr(r2_store, name) is getattr(r2_media_store, name), name
    assert r2_store.R2_KEY_STICKERS_MAPPING == "stickers/mapping.json"
    assert r2_store.R2_KEY_STICKERS_META == "stickers/meta.json"
    assert r2_store.R2_KEY_SUMITALK_CHAT_MEDIA_PREFIX == "sumitalk/chat_media"


def test_sticker_meta_merge_keeps_defaults_and_valid_extras() -> None:
    merged = r2_sticker_store._merge_default_sticker_meta(
        {
            "tags": [
                {"key": "custom_1", "label_zh": "Custom"},
                {"key": "NOT VALID", "label_zh": "Ignored"},
            ],
            "updated_at": "fixed",
        }
    )
    rows = {row["key"]: row for row in merged["tags"]}
    assert rows["custom_1"]["label_zh"] == "Custom"
    assert "NOT VALID" not in rows
    assert merged["updated_at"] == "fixed"


def test_sticker_mapping_scan_filters_reserved_objects() -> None:
    client = Mock()
    client.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "stickers/meta.json"},
            {"Key": "stickers/mapping.json"},
            {"Key": "stickers/happy/a.png"},
            {"Key": "stickers/happy/a.png"},
            {"Key": "stickers/happy/b.webp"},
            {"Key": "stickers/"},
        ],
        "IsTruncated": False,
    }
    with patch.object(r2_sticker_store, "_s3_client", return_value=client):
        assert r2_sticker_store.rebuild_stickers_mapping_from_r2() == {
            "happy": ["stickers/happy/a.png", "stickers/happy/b.webp"]
        }


def test_reserved_sticker_delete_is_rejected_without_r2() -> None:
    factory = Mock(side_effect=AssertionError("Reserved or unsafe keys must be rejected before R2 access"))
    with patch.object(r2_sticker_store, "_s3_client", factory):
        assert r2_sticker_store.delete_sticker_object("stickers/meta.json") is False
        assert r2_sticker_store.delete_sticker_object("stickers/happy/../meta.json") is False
    factory.assert_not_called()


def test_sumitalk_media_type_contract() -> None:
    assert r2_media_store._sumitalk_chat_media_ext("voice.m4a", "audio/mp4", "audio") == (".m4a", "audio/mp4")
    assert r2_media_store._sumitalk_chat_media_ext("note.md", "text/plain", "document") == (".md", "text/markdown")
    assert r2_media_store._sumitalk_chat_media_ext("photo.png", "", "image") == (".png", "image/png")


def test_sumitalk_upload_metadata_contract() -> None:
    client = Mock()
    fixed_uuid = SimpleNamespace(hex="abc123")
    with (
        patch.object(r2_media_store, "_s3_client", return_value=client),
        patch.object(r2_media_store, "uuid4", return_value=fixed_uuid),
        patch.object(r2_media_store, "today_beijing", return_value="2026-07-11"),
        patch.object(r2_media_store, "now_beijing_iso", return_value="2026-07-11T10:00:00+08:00"),
    ):
        row = r2_media_store.upload_sumitalk_chat_media_file("image", "photo.png", b"png", "image/png")
    assert row == {
        "key": "sumitalk/chat_media/image/2026-07-11/abc123.png",
        "kind": "image",
        "name": "photo.png",
        "contentType": "image/png",
        "size": 3,
        "createdAt": "2026-07-11T10:00:00+08:00",
    }
    client.put_object.assert_called_once_with(
        Bucket=r2_media_store.R2_BUCKET_NAME,
        Key=row["key"],
        Body=b"png",
        ContentType="image/png",
    )


def test_media_path_traversal_is_rejected_without_r2() -> None:
    factory = Mock(side_effect=AssertionError("Unsafe media keys must be rejected before R2 access"))
    with patch.object(r2_media_store, "_s3_client", factory):
        assert r2_media_store.get_sumitalk_chat_media_file("sumitalk/chat_media/../secret") == (None, "")
        assert r2_media_store.get_device_screenshot("device_screenshots/../secret", "token") == (None, "")
    factory.assert_not_called()


def test_device_screenshot_token_gate() -> None:
    body = Mock()
    body.read.return_value = b"screen"
    client = Mock()
    client.get_object.return_value = {"Body": body, "ContentType": "image/png"}
    with (
        patch.object(r2_media_store, "_s3_client", return_value=client),
        patch.object(r2_media_store, "_read_json", return_value={"accessToken": "right", "contentType": "image/png"}),
    ):
        assert r2_media_store.get_device_screenshot("device_screenshots/latest/phone.png", "wrong") == (None, "")
        assert r2_media_store.get_device_screenshot("device_screenshots/latest/phone.png", "right") == (b"screen", "image/png")
    client.get_object.assert_called_once()


def main() -> None:
    tests = [
        test_r2_store_keeps_object_store_exports,
        test_sticker_meta_merge_keeps_defaults_and_valid_extras,
        test_sticker_mapping_scan_filters_reserved_objects,
        test_reserved_sticker_delete_is_rejected_without_r2,
        test_sumitalk_media_type_contract,
        test_sumitalk_upload_metadata_contract,
        test_media_path_traversal_is_rejected_without_r2,
        test_device_screenshot_token_gate,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    main()
