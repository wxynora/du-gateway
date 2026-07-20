from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes import chat as chat_route
from services import proactive_trigger_engine
from services import telegram_proactive


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_internal_wakeup_does_not_record_user_interaction() -> None:
    app = Flask(__name__)
    with app.test_request_context("/", headers={"X-DU-GATEWAY-WAKEUP": "1"}):
        _assert(
            not chat_route._should_record_user_interaction_side_effects(),
            "internal wakeup must not advance user activity or recent-entry state",
        )
    with app.test_request_context("/"):
        _assert(
            chat_route._should_record_user_interaction_side_effects(),
            "ordinary chat must keep the existing user-interaction path",
        )


def test_used_forum_tool_skips_appended_execution_round() -> None:
    decision = telegram_proactive.ProactiveDecision(
        False,
        action="forum",
        du_reason="已经看过论坛",
        executed_tools=("cli", "forum_open_thread"),
    )
    original_runner = telegram_proactive._run_proactive_forum_action

    def fail_if_called(**_kwargs):
        raise AssertionError("forum execution round must not run after the decision already used forum tools")

    telegram_proactive._run_proactive_forum_action = fail_if_called
    try:
        result = telegram_proactive._ensure_proactive_forum_action(
            decision,
            window_id="tg_test",
            hours_since_last=0.5,
        )
    finally:
        telegram_proactive._run_proactive_forum_action = original_runner

    _assert(result.get("ok") is True, f"already executed forum should be successful: {result}")
    _assert(result.get("already_executed") is True, f"missing already-executed marker: {result}")


def test_forum_action_without_tool_trace_keeps_existing_execution_round() -> None:
    decision = telegram_proactive.ProactiveDecision(False, action="forum", du_reason="想去看看")
    original_runner = telegram_proactive._run_proactive_forum_action
    calls: list[dict] = []

    def fake_runner(**kwargs):
        calls.append(dict(kwargs))
        return {"ok": True, "reply_preview": "看完了", "error": ""}

    telegram_proactive._run_proactive_forum_action = fake_runner
    try:
        result = telegram_proactive._ensure_proactive_forum_action(
            decision,
            window_id="tg_test",
            hours_since_last=0.5,
        )
    finally:
        telegram_proactive._run_proactive_forum_action = original_runner

    _assert(result.get("ok") is True, f"normal forum execution should remain available: {result}")
    _assert(len(calls) == 1, f"forum execution should run exactly once without prior tool use: {calls}")


def test_gateway_reports_executed_tools_to_proactive_scheduler() -> None:
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_forum",
                    "type": "function",
                    "function": {"name": "cli", "arguments": "{\"command\":\"list\"}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_forum", "content": "{\"ok\":true}"},
    ]
    names = chat_route._executed_tool_names_from_messages(messages)
    _assert(names == ["cli"], f"gateway lost executed forum tool trace: {names}")
    _assert(
        telegram_proactive._gateway_executed_tool_names({"du_gateway_executed_tools": names}) == ("cli",),
        "proactive scheduler did not consume the gateway tool marker",
    )


def test_sleep_narrative_is_not_treated_as_away_intent() -> None:
    narratives = (
        "你趁我睡觉还跑去种地了",
        "你在我睡觉的时候偷偷跑出去了",
        "昨晚我睡觉你又干嘛了",
        "我睡着后你又干嘛了",
        "不是我要睡觉，是你在我睡觉的时候跑出去了",
    )
    for text in narratives:
        _assert(
            not proactive_trigger_engine._user_announced_away(text),
            f"sleep narrative must not be treated as an away announcement: {text}",
        )

    for text in (
        "我去睡觉了",
        "我准备睡了",
        "现在我睡觉了",
        "晚安",
        "我还没睡，准备睡了",
        "你先睡吧，我也去睡觉了",
    ):
        _assert(
            proactive_trigger_engine._user_announced_away(text),
            f"real sleep intent must remain recognized: {text}",
        )


def test_sleep_narrative_still_restarts_half_hour_trigger() -> None:
    latest = {
        "timestamp": "2026-07-19T18:55:44+08:00",
        "index": "14071",
        "user_text": "你趁我睡觉还跑去种地了",
    }
    original_latest = proactive_trigger_engine._latest_normal_chat_round
    original_global_activity = proactive_trigger_engine.r2_store.get_last_user_activity_at
    original_activity = proactive_trigger_engine._recent_app_activity_lines
    proactive_trigger_engine._latest_normal_chat_round = lambda _window_id: latest
    proactive_trigger_engine.r2_store.get_last_user_activity_at = lambda: "2026-07-19T18:55:44+08:00"
    proactive_trigger_engine._recent_app_activity_lines = lambda _doc, _history, _now_dt: ["19:24 打开Codex"]
    try:
        event = proactive_trigger_engine._build_no_reply_soft_trigger(
            {},
            [],
            "tg_test",
            datetime(2026, 7, 19, 19, 25, 45, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
    finally:
        proactive_trigger_engine._latest_normal_chat_round = original_latest
        proactive_trigger_engine.r2_store.get_last_user_activity_at = original_global_activity
        proactive_trigger_engine._recent_app_activity_lines = original_activity

    _assert(event is not None, "latest real message must restart and retain the half-hour trigger")
    _assert(
        event.trigger_type == "no_reply_30m_app_activity",
        f"unexpected half-hour trigger type: {event}",
    )
    _assert(
        event.dedupe_key.endswith(":2026-07-19T18:55:44+08:00"),
        f"half-hour trigger must be anchored to the unified interaction time: {event.dedupe_key}",
    )


def test_non_chat_activity_restarts_half_hour_trigger_clock() -> None:
    latest = {
        "timestamp": "2026-07-19T18:55:44+08:00",
        "index": "14071",
        "user_text": "我去睡觉了",
    }
    original_latest = proactive_trigger_engine._latest_normal_chat_round
    original_global_activity = proactive_trigger_engine.r2_store.get_last_user_activity_at
    original_activity = proactive_trigger_engine._recent_app_activity_lines
    proactive_trigger_engine._latest_normal_chat_round = lambda _window_id: latest
    proactive_trigger_engine.r2_store.get_last_user_activity_at = lambda: "2026-07-19T19:20:00+08:00"
    proactive_trigger_engine._recent_app_activity_lines = lambda _doc, _history, _now_dt: ["19:24 打开Codex"]
    try:
        too_early = proactive_trigger_engine._build_no_reply_soft_trigger(
            {},
            [],
            "tg_test",
            datetime(2026, 7, 19, 19, 25, 45, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        event = proactive_trigger_engine._build_no_reply_soft_trigger(
            {},
            [],
            "tg_test",
            datetime(2026, 7, 19, 19, 50, 1, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
    finally:
        proactive_trigger_engine._latest_normal_chat_round = original_latest
        proactive_trigger_engine.r2_store.get_last_user_activity_at = original_global_activity
        proactive_trigger_engine._recent_app_activity_lines = original_activity

    _assert(too_early is None, "a game or home interaction must restart the half-hour clock")
    _assert(
        event is not None,
        "the half-hour trigger must remain available 30 minutes after the latest interaction",
    )
    _assert(
        event.dedupe_key.endswith(":2026-07-19T19:20:00+08:00"),
        f"the trigger must be anchored to the non-chat interaction: {event.dedupe_key}",
    )


def test_user_only_round_restarts_half_hour_trigger_clock() -> None:
    rounds = [
        {
            "timestamp": "2026-07-19T18:50:00+08:00",
            "index": "14070",
            "messages": [
                {"role": "user", "content": "上一条消息"},
                {"role": "assistant", "content": "上一条回复"},
            ],
        },
        {
            "timestamp": "2026-07-19T18:55:44+08:00",
            "index": "14071",
            "messages": [
                {"role": "user", "content": "这条消息还没有生成回复"},
            ],
        },
    ]
    original_rounds = proactive_trigger_engine.r2_store.get_conversation_rounds
    proactive_trigger_engine.r2_store.get_conversation_rounds = lambda _window_id, last_n=30: rounds[-last_n:]
    try:
        latest = proactive_trigger_engine._latest_normal_chat_round("tg_test")
    finally:
        proactive_trigger_engine.r2_store.get_conversation_rounds = original_rounds

    _assert(latest is not None, "latest real user message must remain a valid trigger anchor")
    _assert(
        latest.get("index") == "14071",
        f"a user-only round must restart the half-hour clock: {latest}",
    )


if __name__ == "__main__":
    test_internal_wakeup_does_not_record_user_interaction()
    test_used_forum_tool_skips_appended_execution_round()
    test_forum_action_without_tool_trace_keeps_existing_execution_round()
    test_gateway_reports_executed_tools_to_proactive_scheduler()
    test_sleep_narrative_is_not_treated_as_away_intent()
    test_sleep_narrative_still_restarts_half_hour_trigger()
    test_non_chat_activity_restarts_half_hour_trigger_clock()
    test_user_only_round_restarts_half_hour_trigger_clock()
    print("proactive wakeup boundary tests ok")
