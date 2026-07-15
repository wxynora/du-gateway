#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

from flask import Blueprint, Flask, request


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected={expected!r} actual={actual!r}")


def message(index: int, *, content: str | None = None) -> dict:
    return {
        "id": f"message-{index:03d}",
        "role": "user" if index % 2 == 0 else "assistant",
        "content": content or f"content-{index}",
        "createdAt": f"2026-07-{1 + index // 24:02d}T{index % 24:02d}:00:00+08:00",
    }


def test_merge_is_unbounded_and_newer_copy_wins() -> None:
    from routes.miniapp.sumitalk_history import _merge_sumitalk_messages

    legacy = [message(index, content=f"legacy-{index}") for index in range(100)]
    canonical = [message(index, content=f"canonical-{index}") for index in range(50, 150)]
    merged = _merge_sumitalk_messages(legacy, canonical)

    assert_equal(len(merged), 150, "merge must not truncate histories to 80 messages")
    by_id = {item["id"]: item for item in merged}
    assert_equal(by_id["message-075"]["content"], "canonical-75", "later canonical row must replace stale legacy content")


def test_migration_groups_legacy_rows_and_reports_final_counts() -> None:
    from routes.miniapp import sumitalk_history

    old_device_id = "android-old"
    new_device_id = "device-native"
    group_messages = [
        {
            **message(index),
            "id": f"group-{index:03d}",
            "content": f"group-content-{index}",
        }
        for index in range(90)
    ]
    state = {
        old_device_id: {
            "device_id": old_device_id,
            "updated_at": "2026-07-10T10:00:00+08:00",
            "messages": [message(index, content=f"legacy-{index}") for index in range(100)],
        },
        f"{old_device_id}::sumitalk-main": {
            "device_id": old_device_id,
            "window_id": "sumitalk-main",
            "updated_at": "2026-07-11T10:00:00+08:00",
            "messages": [message(index, content=f"canonical-{index}") for index in range(50, 150)],
        },
        f"{old_device_id}::sumitalk-group": {
            "device_id": old_device_id,
            "window_id": "sumitalk-group",
            "updated_at": "2026-07-11T10:01:00+08:00",
            "messages": group_messages,
        },
        f"{new_device_id}::sumitalk-main": {
            "device_id": new_device_id,
            "window_id": "sumitalk-main",
            "updated_at": "2026-07-12T10:00:00+08:00",
            "messages": [
                message(75, content="partial-migration-copy"),
                {
                    "id": "native-only",
                    "role": "user",
                    "content": "native-only-content",
                    "createdAt": "2026-07-15T10:00:00+08:00",
                },
            ],
        },
    }

    old_load = sumitalk_history._load_sumitalk_histories
    old_save = sumitalk_history._save_sumitalk_histories
    old_is_trusted = sumitalk_history.is_trusted_device
    old_upsert = sumitalk_history.upsert_trusted_device
    old_auth_enabled = sumitalk_history.panel_auth_enabled
    try:
        sumitalk_history._load_sumitalk_histories = lambda: deepcopy(state)

        def save(data: dict) -> bool:
            state.clear()
            state.update(deepcopy(data))
            return True

        sumitalk_history._save_sumitalk_histories = save
        sumitalk_history.is_trusted_device = lambda device_id: device_id == old_device_id
        sumitalk_history.upsert_trusted_device = lambda device_id: None
        sumitalk_history.panel_auth_enabled = lambda: False

        app = Flask(__name__)
        bp = Blueprint("sumitalk_history_test", __name__, url_prefix="/miniapp-api")

        @bp.before_request
        def inject_device() -> None:
            request.environ["miniapp_panel_payload"] = {
                "device_id": old_device_id,
                "sub": f"device:{old_device_id}",
            }

        sumitalk_history.register_routes(bp)
        app.register_blueprint(bp)
        response = app.test_client().post(
            "/miniapp-api/sumitalk-history/migrate",
            json={"new_device_id": new_device_id},
        )
    finally:
        sumitalk_history._load_sumitalk_histories = old_load
        sumitalk_history._save_sumitalk_histories = old_save
        sumitalk_history.is_trusted_device = old_is_trusted
        sumitalk_history.upsert_trusted_device = old_upsert
        sumitalk_history.panel_auth_enabled = old_auth_enabled

    assert_equal(response.status_code, 200, "migration endpoint should succeed")
    payload = response.get_json()
    assert_equal(payload["source_rows"], 3, "response should report physical source rows")
    assert_equal(payload["rows"], 2, "legacy and canonical main rows must map to one target row")
    assert_equal(payload["source_count"], 240, "source count should use logical message ids")
    assert_equal(payload["existing_count"], 2, "existing destination count should be exact")
    assert_equal(payload["count"], 241, "count should equal final messages stored across target windows")

    target_main = state[f"{new_device_id}::sumitalk-main"]["messages"]
    target_group = state[f"{new_device_id}::sumitalk-group"]["messages"]
    assert_equal(len(target_main), 151, "main history must retain the full source union plus destination-only messages")
    assert_equal(len(target_group), 90, "group history must not be truncated")
    by_id = {item["id"]: item for item in target_main}
    assert_equal(by_id["message-075"]["content"], "canonical-75", "canonical source must repair a partial legacy copy")
    assert_equal(len(state[old_device_id]["messages"]), 100, "legacy source row must remain untouched")
    assert_equal(len(state[f"{old_device_id}::sumitalk-main"]["messages"]), 100, "canonical source row must remain untouched")


def main() -> None:
    test_merge_is_unbounded_and_newer_copy_wins()
    test_migration_groups_legacy_rows_and_reports_final_counts()
    print("SumiTalk history migration tests passed")


if __name__ == "__main__":
    main()
