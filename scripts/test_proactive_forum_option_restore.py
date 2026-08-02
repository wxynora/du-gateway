from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import proactive_prompt_templates
from services import prompt_manager
from services import telegram_proactive


class _Response:
    status_code = 200
    content = b"{}"
    text = "{}"

    def __init__(self, content: str) -> None:
        self._content = content

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": self._content,
                    }
                }
            ]
        }


def test_default_random_wakeup_prompt_exposes_forum_action() -> None:
    template = proactive_prompt_templates.RANDOM_PROACTIVE_DECISION_TEMPLATE

    assert "逛论坛" in template
    assert "send_message|no_contact|diary|forum|surf|drawer|game|other" in template


def test_managed_random_wakeup_prompt_keeps_forum_action(monkeypatch) -> None:
    managed = """这是托管模板，逛论坛。
{"action":"send_message|no_contact|diary|forum|surf|other","channel":"{{default_channel}}"}"""
    monkeypatch.setattr(prompt_manager, "get_managed_prompt_text", lambda *_args, **_kwargs: managed)

    rendered = telegram_proactive._render_random_proactive_decision_prompt(
        recent_exchange="刚聊过",
        hours_since_last=1.0,
        channel_field_desc="channel 说明",
        default_channel="qq",
        no_contact_token="NO_CONTACT",
    )

    assert "逛论坛" in rendered
    assert "diary|forum|surf" in rendered


def test_after_surf_decision_allows_forum(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(_url, *, headers, json, timeout):
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response('{"action":"no_contact","reason":"看过了","message":"","channel":"qq"}')

    monkeypatch.setattr(telegram_proactive.requests, "post", fake_post)
    monkeypatch.setattr(telegram_proactive, "_available_channels", lambda: ["qq"])
    monkeypatch.setattr(telegram_proactive, "_preferred_proactive_channel", lambda _channels: "qq")
    monkeypatch.setattr(telegram_proactive, "_get_chat_model", lambda: "test-model")

    telegram_proactive._ask_du_after_surf_result(
        window_id="test-window",
        hours_since_last=1.0,
        surf_result={"ok": True, "topic": "test", "count": 0, "cards": []},
        initial_reason="想看看",
    )

    prompt = captured["json"]["messages"][-1]["content"]
    assert '"diary" | "forum" | "drawer"' in prompt


def test_forum_execution_round_uses_galatea_garden(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(_url, *, headers, json, timeout):
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response("看了论坛里的一篇帖子。")

    monkeypatch.setattr(telegram_proactive.requests, "post", fake_post)
    monkeypatch.setattr(telegram_proactive, "_available_channels", lambda: ["qq"])
    monkeypatch.setattr(telegram_proactive, "_preferred_proactive_channel", lambda _channels: "qq")
    monkeypatch.setattr(telegram_proactive, "_get_chat_model", lambda: "test-model")

    result = telegram_proactive._run_proactive_forum_action(
        window_id="test-window",
        hours_since_last=1.0,
        initial_reason="想看看",
    )

    prompt = captured["json"]["messages"][-1]["content"]
    assert result["ok"] is True
    assert "galatea_garden" in prompt
    assert "action=list_threads" in prompt
    assert "action=get_thread" in prompt
    assert "forum_read_feed" not in prompt
    assert "forum_open_thread" not in prompt
