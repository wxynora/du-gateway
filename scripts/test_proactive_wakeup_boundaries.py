from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes import chat as chat_route
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


if __name__ == "__main__":
    test_internal_wakeup_does_not_record_user_interaction()
    test_used_forum_tool_skips_appended_execution_round()
    test_forum_action_without_tool_trace_keeps_existing_execution_round()
    test_gateway_reports_executed_tools_to_proactive_scheduler()
    print("proactive wakeup boundary tests ok")
