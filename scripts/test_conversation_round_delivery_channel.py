#!/usr/bin/env python3
from __future__ import annotations

import copy
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Blueprint, Flask

from pipeline import pipeline as pipeline_module
from routes import chat as chat_route
from routes.miniapp import reasoning as reasoning_route
from services import conversation_followup, telegram_proactive
from storage import chat_activity_store
from storage import r2_conversation_store as conversation_store


class _FakeResponse:
    status_code = 200
    content = b"{}"
    text = ""

    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return copy.deepcopy(self._payload)


def _memory_json_store(initial: dict | None = None):
    values = copy.deepcopy(initial or {})

    def read_json(_client, key: str):
        return copy.deepcopy(values.get(key))

    def write_json(_client, key: str, payload):
        values[key] = copy.deepcopy(payload)

    return values, read_json, write_json


def test_append_and_pipeline_channel_snapshot() -> None:
    values, read_json, write_json = _memory_json_store()
    sqlite_rounds: list[dict] = []
    with (
        mock.patch.object(conversation_store, "_s3_client", return_value=object()),
        mock.patch.object(conversation_store, "_read_json", side_effect=read_json),
        mock.patch.object(conversation_store, "_write_json", side_effect=write_json),
        mock.patch.object(
            conversation_store,
            "_ensure_compact_conversation_state",
            return_value={"last_round_index": 0, "round_count": 0},
        ),
        mock.patch.object(conversation_store, "_read_recent_rounds", return_value=[]),
        mock.patch.object(conversation_store, "_read_conversation_backup_rounds_for_dates", return_value=[]),
        mock.patch.object(conversation_store, "today_beijing", return_value="2026-07-31"),
        mock.patch.object(conversation_store.conversation_sqlite_store, "has_window", return_value=False),
        mock.patch.object(conversation_store.conversation_sqlite_store, "import_window_state"),
        mock.patch.object(
            conversation_store.conversation_sqlite_store,
            "upsert_round",
            side_effect=lambda _wid, item, recent_keep=0: sqlite_rounds.append(copy.deepcopy(item)) or True,
        ),
        mock.patch.object(chat_activity_store, "append_chat_activity_round"),
    ):
        assert conversation_store.append_conversation_round(
            "tg_1",
            1,
            [{"role": "assistant", "content": "hi"}],
            timestamp="2026-07-31T12:00:00+08:00",
            channel="tg",
        )

    round_key = conversation_store._conversation_round_key("tg_1", 1)
    recent_key = conversation_store._conversation_recent_key("tg_1")
    backup_key = conversation_store._conversations_key_for_date("tg_1", "2026-07-31")
    assert values[round_key]["channel"] == "tg"
    assert values[recent_key]["rounds"][0]["channel"] == "tg"
    assert values[backup_key]["rounds"][0]["channel"] == "tg"
    assert sqlite_rounds[0]["channel"] == "tg"

    captured_channels: list[str] = []

    def fake_append(*_args, **kwargs):
        captured_channels.append(str(kwargs.get("channel") or ""))
        return True

    with (
        mock.patch.object(pipeline_module.r2_store, "get_next_round_index", side_effect=range(2, 7)),
        mock.patch.object(pipeline_module.r2_store, "append_conversation_round", side_effect=fake_append),
        mock.patch.object(pipeline_module.r2_store, "get_conversation_rounds", return_value=[]),
        mock.patch.object(pipeline_module.r2_store, "update_latest_4_rounds_global", return_value=True),
    ):
        for reply_channel in ("sumitalk", "qq", "telegram", "wechat", "xiaoai"):
            archived = pipeline_module.step_archive_round(
                "tg_1",
                [{"role": "user", "content": "hello"}],
                {
                    "role": "assistant",
                    "content": "world",
                    "tool_calls": [{"id": "call-1", "function": {"name": "get_time_info", "arguments": "{}"}}],
                },
                round_cleaned_for_r2=[
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "world"},
                ],
                reply_channel=reply_channel,
            )
            assert archived
    assert captured_channels == ["sumitalk", "qq", "tg", "wechat", "xiaoai"]


def test_stream_archive_queue_keeps_sumitalk_channel() -> None:
    captured: dict = {}

    class OneTaskQueue:
        def __init__(self):
            self.calls = 0

        def get(self):
            self.calls += 1
            if self.calls == 1:
                return ("tg_1", [], {}, None, "sumitalk", False, False)
            raise KeyboardInterrupt

        def task_done(self):
            return None

    def fake_archive(*_args, **kwargs):
        captured.update(kwargs)

    with (
        mock.patch.object(chat_route, "_SUMITALK_STREAM_ARCHIVE_QUEUE", OneTaskQueue()),
        mock.patch.object(chat_route, "step_archive_and_maybe_summary", side_effect=fake_archive),
    ):
        try:
            chat_route._run_sumitalk_stream_archive_queue()
        except KeyboardInterrupt:
            pass
    assert captured["reply_channel"] == "sumitalk"


def test_delivery_update_syncs_every_round_copy() -> None:
    window_id = "tg_1"
    index = 8
    original = {
        "index": index,
        "timestamp": "2026-07-31T12:30:00+08:00",
        "channel": "",
        "messages": [{"role": "assistant", "content": "hello"}],
    }
    round_key = conversation_store._conversation_round_key(window_id, index)
    recent_key = conversation_store._conversation_recent_key(window_id)
    backup_key = conversation_store._conversations_key_for_date(window_id, "2026-07-31")
    values, read_json, write_json = _memory_json_store(
        {
            round_key: original,
            recent_key: {"rounds": [original]},
            backup_key: {"window_id": window_id, "date": "2026-07-31", "rounds": [original]},
        }
    )
    sqlite_rounds: list[dict] = []
    with (
        mock.patch.object(conversation_store, "_s3_client", return_value=object()),
        mock.patch.object(conversation_store, "_read_json", side_effect=read_json),
        mock.patch.object(conversation_store, "_write_json", side_effect=write_json),
        mock.patch.object(conversation_store, "today_beijing", return_value="2026-07-31"),
        mock.patch.object(conversation_store.conversation_sqlite_store, "has_window", return_value=True),
        mock.patch.object(
            conversation_store.conversation_sqlite_store,
            "upsert_round",
            side_effect=lambda _wid, item, recent_keep=0: sqlite_rounds.append(copy.deepcopy(item)) or True,
        ),
    ):
        assert conversation_store.update_conversation_round_channel(window_id, index, "wechat")

    assert values[round_key]["channel"] == "wechat"
    assert values[recent_key]["rounds"][0]["channel"] == "wechat"
    assert values[backup_key]["rounds"][0]["channel"] == "wechat"
    assert sqlite_rounds[0]["channel"] == "wechat"


def test_reasoning_latest_reads_saved_round_channel_only() -> None:
    app = Flask(__name__)
    bp = Blueprint("reasoning_test", __name__)
    reasoning_route.register_routes(bp)
    app.register_blueprint(bp, url_prefix="/miniapp-api")
    rounds = [
        {
            "index": 1,
            "timestamp": "2026-07-31T10:00:00+08:00",
            "messages": [{"role": "assistant", "reasoning": "old reasoning", "content": "old"}],
        },
        {
            "index": 2,
            "timestamp": "2026-07-31T11:00:00+08:00",
            "channel": "sumitalk",
            "messages": [{"role": "assistant", "reasoning": "new reasoning", "content": "new"}],
        },
        {
            "index": 3,
            "timestamp": "2026-07-31T12:00:00+08:00",
            "channel": "qq",
            "messages": [{"role": "assistant", "reasoning": "qq reasoning", "content": "qq"}],
        },
        {
            "index": 4,
            "timestamp": "2026-07-31T13:00:00+08:00",
            "channel": "tg",
            "messages": [{"role": "assistant", "reasoning": "tg reasoning", "content": "tg"}],
        },
        {
            "index": 5,
            "timestamp": "2026-07-31T14:00:00+08:00",
            "channel": "wechat",
            "messages": [{"role": "assistant", "reasoning": "wechat reasoning", "content": "wechat"}],
        },
    ]
    with (
        mock.patch.object(reasoning_route.recent_window_store, "list_recent_windows", return_value=[{"id": "tg_1"}]),
        mock.patch.object(reasoning_route, "_resolve_primary_chat_window_id", return_value="tg_1"),
        mock.patch.object(reasoning_route, "_load_memory_recall_debug_index", return_value={}),
        mock.patch.object(reasoning_route.r2_store, "get_conversation_rounds", return_value=rounds),
    ):
        response = app.test_client().get("/miniapp-api/reasoning/latest?limit=10")
    assert response.status_code == 200
    items = response.get_json()["items"]
    assert [item["channel"] for item in items] == ["wechat", "tg", "qq", "sumitalk", ""]


def test_wakeup_records_only_successful_fallback_channel() -> None:
    gateway_payload = {
        "du_gateway_archive_round_index": 17,
        "choices": [{"message": {"role": "assistant", "content": "reply"}}],
    }
    updated: list[tuple[str, int, str]] = []
    with (
        mock.patch("storage.upstream_store.get_cached_active_model", return_value="model"),
        mock.patch.object(conversation_followup, "_choice_dialog_delivery_preference", return_value=("qq", "123", {})),
        mock.patch.object(conversation_followup, "_choice_dialog_delivery_channels", return_value=["qq", "wechat"]),
        mock.patch.object(conversation_followup, "_dispatch_choice_dialog_reply", side_effect=[False, True]),
        mock.patch.object(conversation_followup.requests, "post", return_value=_FakeResponse(gateway_payload)),
        mock.patch.object(conversation_followup, "_sanitize_reply_for_telegram", side_effect=lambda text: text),
        mock.patch(
            "services.telegram_proactive._sanitize_control_reply_for_delivery",
            side_effect=lambda text: text,
        ),
        mock.patch.object(
            conversation_followup.r2_store,
            "update_conversation_round_channel",
            side_effect=lambda wid, idx, channel: updated.append((wid, idx, channel)) or True,
        ),
    ):
        result = conversation_followup._send_wakeup_event(
            window_id="tg_1",
            target="123",
            event_text="event",
            archive=True,
        )
    assert result["ok"] is True
    assert result["channel"] == "wechat"
    assert updated == [("tg_1", 17, "wechat")]

    with (
        mock.patch("storage.upstream_store.get_cached_active_model", return_value="model"),
        mock.patch.object(conversation_followup, "_choice_dialog_delivery_preference", return_value=("qq", "123", {})),
        mock.patch.object(conversation_followup, "_choice_dialog_delivery_channels", return_value=["qq", "wechat"]),
        mock.patch.object(conversation_followup, "_dispatch_choice_dialog_reply", side_effect=[False, False]),
        mock.patch.object(conversation_followup.requests, "post", return_value=_FakeResponse(gateway_payload)),
        mock.patch.object(conversation_followup, "_sanitize_reply_for_telegram", side_effect=lambda text: text),
        mock.patch(
            "services.telegram_proactive._sanitize_control_reply_for_delivery",
            side_effect=lambda text: text,
        ),
        mock.patch.object(conversation_followup.r2_store, "update_conversation_round_channel") as update_mock,
    ):
        result = conversation_followup._send_wakeup_event(
            window_id="tg_1",
            target="123",
            event_text="event",
            archive=True,
        )
    assert result["ok"] is False
    update_mock.assert_not_called()


def test_proactive_contact_records_actual_channel_only_after_success() -> None:
    decision = telegram_proactive.ProactiveDecision(
        should_send=True,
        text="hello",
        reason="contact",
        action="send_message",
        channel="qq",
        archive_round_index=23,
    )
    updated: list[tuple[str, int, str]] = []
    common_patches = (
        mock.patch.object(telegram_proactive, "now_beijing_iso", return_value="2026-07-31T12:00:00+08:00"),
        mock.patch.object(telegram_proactive, "_get_last_message_activity_iso", return_value=None),
        mock.patch.object(telegram_proactive, "_probability", return_value=1.0),
        mock.patch.object(telegram_proactive, "_available_channels", return_value=["qq", "wechat"]),
        mock.patch.object(telegram_proactive, "_try_post_spring_dream_wakeup", return_value=None),
        mock.patch.object(telegram_proactive, "_try_spring_dream_wakeup", return_value=None),
        mock.patch.object(telegram_proactive, "_ask_du_should_contact", return_value=decision),
        mock.patch.object(telegram_proactive, "_sanitize_reply_for_telegram", side_effect=lambda text: text),
        mock.patch.object(telegram_proactive, "_sanitize_control_reply_for_delivery", side_effect=lambda text: text),
        mock.patch.object(telegram_proactive, "_build_du_daily_trigger_from_proactive", return_value=None),
        mock.patch.object(telegram_proactive.r2_store, "append_proactive_decision_memory", return_value=True),
        mock.patch.object(telegram_proactive.r2_store, "save_last_proactive_contact_at", return_value=True),
    )
    with ExitStack() as stack:
        for patcher in common_patches:
            stack.enter_context(patcher)
        stack.enter_context(mock.patch.object(
            telegram_proactive,
            "_dispatch_proactive_decision_message",
            return_value=(True, "wechat", ["qq", "wechat"]),
        ))
        stack.enter_context(mock.patch.object(
            telegram_proactive.r2_store,
            "update_conversation_round_channel",
            side_effect=lambda wid, idx, channel: updated.append((wid, idx, channel)) or True,
        ))
        result = telegram_proactive.proactive_tick(target_user_id=1)
    assert result["sent"] is True
    assert result["channel"] == "wechat"
    assert updated == [("tg_1", 23, "wechat")]

    failure_patches = (
        mock.patch.object(telegram_proactive, "now_beijing_iso", return_value="2026-07-31T12:00:00+08:00"),
        mock.patch.object(telegram_proactive, "_get_last_message_activity_iso", return_value=None),
        mock.patch.object(telegram_proactive, "_probability", return_value=1.0),
        mock.patch.object(telegram_proactive, "_available_channels", return_value=["qq", "wechat"]),
        mock.patch.object(telegram_proactive, "_try_post_spring_dream_wakeup", return_value=None),
        mock.patch.object(telegram_proactive, "_try_spring_dream_wakeup", return_value=None),
        mock.patch.object(telegram_proactive, "_ask_du_should_contact", return_value=decision),
        mock.patch.object(telegram_proactive, "_sanitize_reply_for_telegram", side_effect=lambda text: text),
        mock.patch.object(telegram_proactive, "_sanitize_control_reply_for_delivery", side_effect=lambda text: text),
        mock.patch.object(telegram_proactive, "_build_du_daily_trigger_from_proactive", return_value=None),
        mock.patch.object(telegram_proactive.r2_store, "append_proactive_decision_memory", return_value=True),
    )
    with ExitStack() as stack:
        for patcher in failure_patches:
            stack.enter_context(patcher)
        stack.enter_context(mock.patch.object(
            telegram_proactive,
            "_dispatch_proactive_decision_message",
            return_value=(False, "", ["qq", "wechat"]),
        ))
        update_mock = stack.enter_context(
            mock.patch.object(telegram_proactive.r2_store, "update_conversation_round_channel")
        )
        result = telegram_proactive.proactive_tick(target_user_id=1)
    assert result["sent"] is False
    update_mock.assert_not_called()


def main() -> None:
    tests = [
        test_append_and_pipeline_channel_snapshot,
        test_stream_archive_queue_keeps_sumitalk_channel,
        test_delivery_update_syncs_every_round_copy,
        test_reasoning_latest_reads_saved_round_channel_only,
        test_wakeup_records_only_successful_fallback_channel,
        test_proactive_contact_records_actual_channel_only_after_success,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")


if __name__ == "__main__":
    main()
