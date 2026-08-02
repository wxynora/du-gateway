#!/usr/bin/env python3
"""Pure-local regression tests for Prompt Manager backup retention."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import prompt_manager
from storage import r2_store


class FakeR2:
    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}
        self.client = Mock()
        self.client.list_objects_v2.side_effect = self.list_objects_v2
        self.client.delete_object.side_effect = self.delete_object

    def read_json(self, _client, key: str):
        value = self.objects.get(key)
        return copy.deepcopy(value) if value is not None else None

    def write_json(self, _client, key: str, payload: dict) -> None:
        self.objects[key] = copy.deepcopy(payload)

    def list_objects_v2(self, **kwargs):
        prefix = str(kwargs.get("Prefix") or "")
        keys = sorted(key for key in self.objects if key.startswith(prefix))
        return {"Contents": [{"Key": key} for key in keys], "IsTruncated": False}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        del Bucket
        self.objects.pop(Key, None)

    def backup_keys(self, section_id: str) -> list[str]:
        prefix = f"{r2_store.R2_KEY_PROMPT_MANAGER_BACKUP_PREFIX}{section_id}/"
        return sorted(key for key in self.objects if key.startswith(prefix))

    def backup_contents(self, section_id: str) -> set[str]:
        return {str(self.objects[key].get("content") or "") for key in self.backup_keys(section_id)}


def _timestamps(count: int = 40) -> list[str]:
    return [f"2026-07-21T10:{index:02d}:00+08:00" for index in range(count)]


def _patch_store(fake: FakeR2):
    return (
        patch.object(r2_store, "_s3_client", return_value=fake.client),
        patch.object(r2_store, "_read_json", side_effect=fake.read_json),
        patch.object(r2_store, "_write_json", side_effect=fake.write_json),
        patch.object(r2_store, "now_beijing_iso", side_effect=_timestamps()),
    )


def test_prompt_detail_requests_only_three_backups() -> None:
    with (
        patch.object(r2_store, "get_prompt_manager_section", return_value=None),
        patch.object(r2_store, "list_prompt_manager_backups", return_value=[]) as list_backups,
    ):
        detail = prompt_manager.get_prompt_section_detail("thinking_rules")
    assert detail is not None
    list_backups.assert_called_once_with("thinking_rules", limit=3)


def test_five_saves_keep_latest_three_backups() -> None:
    fake = FakeR2()
    client_patch, read_patch, write_patch, time_patch = _patch_store(fake)
    with client_patch, read_patch, write_patch, time_patch:
        for index in range(5):
            result = r2_store.save_prompt_manager_section(
                "thinking_rules",
                f"version-{index}",
                backup_content="fallback",
                backup_revision=0,
            )
            assert result["ok"] is True
    assert len(fake.backup_keys("thinking_rules")) == 3
    assert fake.backup_contents("thinking_rules") == {"version-1", "version-2", "version-3"}


def test_rollback_keeps_latest_three_backups() -> None:
    fake = FakeR2()
    client_patch, read_patch, write_patch, time_patch = _patch_store(fake)
    with client_patch, read_patch, write_patch, time_patch:
        for index in range(5):
            result = r2_store.save_prompt_manager_section(
                "thinking_rules",
                f"version-{index}",
                backup_content="fallback",
                backup_revision=0,
            )
            assert result["ok"] is True
        backup_id = r2_store.list_prompt_manager_backups("thinking_rules", limit=3)[-1]["backup_id"]
        result = prompt_manager.rollback_prompt_section("thinking_rules", backup_id, updated_by_device="test")
        assert result["ok"] is True
    assert len(fake.backup_keys("thinking_rules")) == 3
    assert fake.backup_contents("thinking_rules") == {"version-2", "version-3", "version-4"}
    assert fake.objects[r2_store.R2_KEY_PROMPT_MANAGER_CONFIG]["sections"]["thinking_rules"]["content"] == "version-1"


def test_config_write_failure_does_not_prune_existing_backups() -> None:
    fake = FakeR2()
    section_id = "thinking_rules"
    fake.objects[r2_store.R2_KEY_PROMPT_MANAGER_CONFIG] = {
        "schema_version": 1,
        "sections": {
            section_id: {
                "section_id": section_id,
                "content": "current",
                "revision": 1,
                "updated_at": "2026-07-21T09:00:00+08:00",
                "updated_by_device": "test",
            }
        },
    }
    for index in range(4):
        key = f"{r2_store.R2_KEY_PROMPT_MANAGER_BACKUP_PREFIX}{section_id}/seed-{index}.json"
        fake.objects[key] = {
            "backup_id": f"seed-{index}",
            "section_id": section_id,
            "content": f"seed-{index}",
            "created_at": f"2026-07-21T08:0{index}:00+08:00",
        }
    original_keys = set(fake.backup_keys(section_id))

    def failing_write(client, key: str, payload: dict) -> None:
        if key == r2_store.R2_KEY_PROMPT_MANAGER_CONFIG:
            raise RuntimeError("config write failed")
        fake.write_json(client, key, payload)

    with (
        patch.object(r2_store, "_s3_client", return_value=fake.client),
        patch.object(r2_store, "_read_json", side_effect=fake.read_json),
        patch.object(r2_store, "_write_json", side_effect=failing_write),
        patch.object(r2_store, "now_beijing_iso", side_effect=_timestamps()),
        patch.object(r2_store.logger, "error") as error_log,
    ):
        result = r2_store.save_prompt_manager_section(section_id, "new-content")

    assert result["ok"] is False
    error_log.assert_called_once()
    assert original_keys.issubset(set(fake.backup_keys(section_id)))
    assert len(fake.backup_keys(section_id)) == 5
    fake.client.delete_object.assert_not_called()


def main() -> None:
    tests = (
        test_prompt_detail_requests_only_three_backups,
        test_five_saves_keep_latest_three_backups,
        test_rollback_keeps_latest_three_backups,
        test_config_write_failure_does_not_prune_existing_backups,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    main()
