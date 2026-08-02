#!/usr/bin/env python3
"""Regression checks for keeping the static followup prompt cache-stable."""

from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_disable_queue_header_keeps_archived_wakeup_static_rule() -> None:
    import routes.chat as chat_route
    from services.conversation_followup import build_followup_system_instruction

    app = Flask("followup-disable-static-prompt")
    body = {"messages": [{"role": "user", "content": "回应后端事件"}]}
    headers = {
        "X-DU-FOLLOWUP-GEN": "1",
        "X-DU-FOLLOWUP-ARCHIVE": "1",
        "X-DU-DISABLE-FOLLOWUP": "1",
    }

    with app.test_request_context("/", headers=headers):
        assert chat_route._disable_followup_request() is True
        result = chat_route._inject_static_followup_instruction_for_request(
            body,
            prompt_reply_channel="sumitalk",
        )

    messages = result.get("messages") or []
    assert messages and messages[0].get("role") == "system"
    assert build_followup_system_instruction().strip() in str(messages[0].get("content") or "")


def test_unarchived_delayed_followup_keeps_static_rule_identical() -> None:
    import routes.chat as chat_route
    from services.conversation_followup import build_followup_system_instruction

    app = Flask("delayed-followup-static-prompt")
    body = {"messages": [{"role": "user", "content": "延迟续话"}]}
    header_cases = [
        {},
        {"X-DU-FOLLOWUP-GEN": "1"},
        {"X-DU-FOLLOWUP-GEN": "1", "X-DU-FOLLOWUP-ARCHIVE": "1"},
        {"X-DU-DISABLE-FOLLOWUP": "1"},
        {
            "X-DU-FOLLOWUP-GEN": "1",
            "X-DU-FOLLOWUP-COUNT": "1",
            "X-DU-FOLLOWUP-CHAIN-ID": "followup-chain",
            "X-DU-FOLLOWUP-ROOT-AT": "2026-07-28T17:10:16+08:00",
        },
        {
            "X-DU-FOLLOWUP-GEN": "1",
            "X-DU-FOLLOWUP-ARCHIVE": "1",
            "X-DU-DISABLE-FOLLOWUP": "1",
        },
    ]
    results = []
    for headers in header_cases:
        with app.test_request_context("/", headers=headers):
            results.append(
                chat_route._inject_static_followup_instruction_for_request(
                    body,
                    prompt_reply_channel="sumitalk",
                )
            )

    assert all(result == results[0] for result in results[1:])
    messages = results[0].get("messages") or []
    assert messages and messages[0].get("role") == "system"
    assert build_followup_system_instruction().strip() in str(messages[0].get("content") or "")


if __name__ == "__main__":
    test_disable_queue_header_keeps_archived_wakeup_static_rule()
    test_unarchived_delayed_followup_keeps_static_rule_identical()
    print("followup disable prompt cache boundary tests passed")
