#!/usr/bin/env python3
"""Local compatibility checks for the extracted Wenyou R2 store."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import r2_client, r2_store, r2_wenyou_store


PUBLIC_NAMES = (
    "delete_wenyou_active_session",
    "get_wenyou_archive_by_game_id",
    "get_wenyou_candidates",
    "get_wenyou_card",
    "get_wenyou_last_archive",
    "get_wenyou_session",
    "get_wenyou_wallet",
    "list_wenyou_archives",
    "save_wenyou_archive_copy",
    "save_wenyou_candidates",
    "save_wenyou_card",
    "save_wenyou_last_archive",
    "save_wenyou_session",
    "save_wenyou_wallet",
    "wenyou_active_session_key",
    "wenyou_candidates_key",
    "wenyou_card_key",
    "wenyou_last_archive_key",
    "wenyou_wallet_key",
)


def test_r2_store_keeps_compatibility_exports() -> None:
    for name in PUBLIC_NAMES:
        assert getattr(r2_store, name) is getattr(r2_wenyou_store, name), name
    assert r2_store.wenyou_active_session_key(7) == "wenyou/active/7/session.json"
    assert r2_store.wenyou_wallet_key(7) == "wenyou/wallet/7.json"


def test_sqlite_primary_save_skips_r2() -> None:
    sqlite = SimpleNamespace(save_session=Mock(return_value=True))
    r2_factory = Mock(side_effect=AssertionError("R2 should not be used for a successful primary write"))
    payload = {"gameId": "local-primary"}
    with (
        patch.object(r2_wenyou_store, "wenyou_sqlite_store", sqlite),
        patch.object(r2_wenyou_store, "WENYOU_R2_BACKUP_ENABLED", False),
        patch.object(r2_wenyou_store, "_s3_client", r2_factory),
    ):
        assert r2_wenyou_store.save_wenyou_session(11, payload) is True
    sqlite.save_session.assert_called_once_with(11, payload)
    r2_factory.assert_not_called()


def test_missing_sqlite_value_backfills_from_r2() -> None:
    sqlite = SimpleNamespace(
        get_card=Mock(return_value=None),
        save_card=Mock(return_value=True),
    )
    client = object()
    payload = {"summary": "continuity"}
    read_json = Mock(return_value=payload)
    with (
        patch.object(r2_wenyou_store, "wenyou_sqlite_store", sqlite),
        patch.object(r2_wenyou_store, "_s3_client", return_value=client),
        patch.object(r2_wenyou_store, "_read_json", read_json),
    ):
        assert r2_wenyou_store.get_wenyou_card(12) == payload
    read_json.assert_called_once_with(client, "wenyou/cards/12.json")
    sqlite.save_card.assert_called_once_with(12, payload)


def test_cleared_sqlite_session_does_not_resurrect_from_r2() -> None:
    sqlite = SimpleNamespace(
        has_session_record=Mock(return_value=True),
        get_session=Mock(return_value=None),
    )
    r2_factory = Mock(side_effect=AssertionError("A cleared SQLite session must block legacy R2 fallback"))
    with (
        patch.object(r2_wenyou_store, "wenyou_sqlite_store", sqlite),
        patch.object(r2_wenyou_store, "_s3_client", r2_factory),
    ):
        assert r2_wenyou_store.get_wenyou_session(21) is None
    r2_factory.assert_not_called()


def test_optional_r2_backup_can_recover_a_failed_sqlite_write() -> None:
    sqlite = SimpleNamespace(save_wallet=Mock(return_value=False))
    client = object()
    write_json = Mock()
    payload = {"points": 8}
    with (
        patch.object(r2_wenyou_store, "wenyou_sqlite_store", sqlite),
        patch.object(r2_wenyou_store, "WENYOU_R2_BACKUP_ENABLED", True),
        patch.object(r2_wenyou_store, "_s3_client", return_value=client),
        patch.object(r2_wenyou_store, "_write_json", write_json),
    ):
        assert r2_wenyou_store.save_wenyou_wallet(13, payload) is True
    write_json.assert_called_once_with(client, "wenyou/wallet/13.json", payload)


def test_r2_archive_fallback_keeps_summary_contract() -> None:
    sqlite = SimpleNamespace(
        list_archives=Mock(return_value=[]),
        save_archive_copy=Mock(return_value=True),
    )
    client = Mock()
    client.list_objects_v2.return_value = {
        "Contents": [{"Key": "wenyou/archive/22/game-1.json", "LastModified": "2026-07-11T01:00:00Z"}],
        "IsTruncated": False,
    }
    archive = {
        "gameId": "game-1",
        "endedAt": "2026-07-11T09:00:00+08:00",
        "framework": {
            "instance_code": "ZS-001",
            "instance_name": "测试副本",
            "instance_genre": "规则怪谈",
            "difficulty": "D",
            "player1_name": "玩家一",
            "player2_name": "渡",
        },
        "stats": {"points": 7, "player1": {"level": 2}, "player2": {"level": 3}},
        "history": [{"round": 1}],
    }
    with (
        patch.object(r2_wenyou_store, "wenyou_sqlite_store", sqlite),
        patch.object(r2_wenyou_store, "_s3_client", return_value=client),
        patch.object(r2_wenyou_store, "_read_json", return_value=archive),
    ):
        rows = r2_wenyou_store.list_wenyou_archives(22, limit=5)
    assert rows == [
        {
            "key": "wenyou/archive/22/game-1.json",
            "gameId": "game-1",
            "endedAt": "2026-07-11T09:00:00+08:00",
            "instance_code": "ZS-001",
            "instance_name": "测试副本",
            "instance_genre": "规则怪谈",
            "difficulty": "D",
            "points": 7,
            "player1_name": "玩家一",
            "player2_name": "渡",
            "player1_level": 2,
            "player2_level": 3,
            "history_count": 1,
        }
    ]
    sqlite.save_archive_copy.assert_called_once_with(22, "game-1", archive)


def test_r2_json_helpers_preserve_payload_shape() -> None:
    payload = {"text": "hello", "items": [1, 2]}
    client = Mock()
    r2_client._write_json(client, "test/key.json", payload)
    put_call = client.put_object.call_args.kwargs
    assert put_call["ContentType"] == "application/json"
    assert json.loads(put_call["Body"].decode("utf-8")) == payload

    body = Mock()
    body.read.return_value = put_call["Body"]
    client.get_object.return_value = {"Body": body}
    assert r2_client._read_json(client, "test/key.json") == payload


def main() -> None:
    tests = [
        test_r2_store_keeps_compatibility_exports,
        test_sqlite_primary_save_skips_r2,
        test_missing_sqlite_value_backfills_from_r2,
        test_cleared_sqlite_session_does_not_resurrect_from_r2,
        test_optional_r2_backup_can_recover_a_failed_sqlite_write,
        test_r2_archive_fallback_keeps_summary_contract,
        test_r2_json_helpers_preserve_payload_shape,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    main()
