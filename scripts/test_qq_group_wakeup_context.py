#!/usr/bin/env python3
"""Regression checks for the QQ group-context wakeup whitelist."""

from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes import chat as chat_routes  # noqa: E402
from routes.chat import _qq_group_activity_context_allowed  # noqa: E402


APP = Flask(__name__)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_only_confirmed_wakeup_sources_can_use_qq_context() -> None:
    allowed = [
        {"X-DU-PROACTIVE-DECISION": "1"},
        {"X-DU-GATEWAY-WAKEUP": "1", "X-DU-WAKEUP-KIND": "proactive_trigger"},
        {"X-DU-GATEWAY-WAKEUP": "1", "X-DU-WAKEUP-KIND": "calendar_event"},
        {"X-DU-GATEWAY-WAKEUP": "1", "X-DU-WAKEUP-KIND": "system_alarm"},
    ]
    for headers in allowed:
        _assert(
            _qq_group_activity_context_allowed(headers),
            f"confirmed wakeup source lost QQ context: {headers}",
        )


def test_other_backend_events_and_normal_chat_are_rejected() -> None:
    rejected_kinds = [
        "",
        "pixel_home",
        "screen_check",
        "choice_dialog",
        "private_draw",
        "private_board",
        "captivity_simulator",
        "exchange_diary_comment",
        "listen_invite_response",
        "spring_dream",
        "post_spring_dream",
        "proactive_diary",
        "proactive_forum",
        "proactive_drawer",
        "proactive_game",
    ]
    _assert(not _qq_group_activity_context_allowed({}), "normal chat must not receive QQ context")
    for wakeup_kind in rejected_kinds:
        headers = {"X-DU-GATEWAY-WAKEUP": "1"}
        if wakeup_kind:
            headers["X-DU-WAKEUP-KIND"] = wakeup_kind
        _assert(
            not _qq_group_activity_context_allowed(headers),
            f"backend event unexpectedly received QQ context: {wakeup_kind or 'generic'}",
        )
    _assert(
        not _qq_group_activity_context_allowed(
            {"X-DU-GATEWAY-WAKEUP": "1", "X-DU-FOLLOWUP-GEN": "1"}
        ),
        "delayed followup must not receive QQ context",
    )


def test_explicit_skip_overrides_the_whitelist() -> None:
    _assert(
        not _qq_group_activity_context_allowed(
            {
                "X-DU-PROACTIVE-DECISION": "1",
                "X-Skip-QQ-Group-Activity": "1",
            }
        ),
        "explicit skip must override random proactive wakeup",
    )
    _assert(
        not _qq_group_activity_context_allowed(
            {
                "X-DU-GATEWAY-WAKEUP": "1",
                "X-DU-WAKEUP-KIND": "system_alarm",
                "X-Skip-QQ-Group-Activity": "true",
            }
        ),
        "explicit skip must override calendar/alarm wakeup",
    )


def test_real_injection_path_rejects_pixel_home_and_accepts_whitelist() -> None:
    original_builder = chat_routes._build_qq_group_activity_context_for_wakeup
    chat_routes._build_qq_group_activity_context_for_wakeup = lambda: "QQ群上下文"
    try:
        base = {"messages": [{"role": "user", "content": "后端事件"}]}
        with APP.test_request_context(
            headers={"X-DU-GATEWAY-WAKEUP": "1", "X-DU-WAKEUP-KIND": "pixel_home"}
        ):
            rejected = chat_routes._inject_qq_group_activity_context(base)
        _assert(rejected == base, f"pixel_home still received QQ context: {rejected}")

        for headers in (
            {"X-DU-PROACTIVE-DECISION": "1"},
            {"X-DU-GATEWAY-WAKEUP": "1", "X-DU-WAKEUP-KIND": "proactive_trigger"},
            {"X-DU-GATEWAY-WAKEUP": "1", "X-DU-WAKEUP-KIND": "calendar_event"},
            {"X-DU-GATEWAY-WAKEUP": "1", "X-DU-WAKEUP-KIND": "system_alarm"},
        ):
            with APP.test_request_context(headers=headers):
                injected = chat_routes._inject_qq_group_activity_context(base)
            content = str(injected["messages"][-1].get("content") or "")
            _assert("QQ群上下文" in content, f"whitelisted request lost QQ context: {headers}")
    finally:
        chat_routes._build_qq_group_activity_context_for_wakeup = original_builder


if __name__ == "__main__":
    test_only_confirmed_wakeup_sources_can_use_qq_context()
    test_other_backend_events_and_normal_chat_are_rejected()
    test_explicit_skip_overrides_the_whitelist()
    test_real_injection_path_rejects_pixel_home_and_accepts_whitelist()
    print("qq group wakeup context whitelist checks passed")
