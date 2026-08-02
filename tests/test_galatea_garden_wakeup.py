from __future__ import annotations

import json

from scripts.galatea_garden_wake_injector import parse_wake_envelope, run_injector
from services import telegram_proactive


def test_garden_wake_uses_recent_context_and_preserves_message(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        telegram_proactive,
        "resolve_recent_reply_context",
        lambda: {"channel": "sumitalk", "window_id": "sumitalk-main", "target": "device-1"},
    )

    def fake_generate(**kwargs):
        calls["generate"] = kwargs
        return {"text": "我去看看。", "qq_group_id": "", "archive_round_index": 9}

    def fake_dispatch(channel, text, **kwargs):
        calls["dispatch"] = {"channel": channel, "text": text, **kwargs}
        return True

    monkeypatch.setattr(telegram_proactive, "_generate_schedule_reply", fake_generate)
    monkeypatch.setattr(telegram_proactive, "_dispatch_send", fake_dispatch)

    message = "游戏轮到你了。请调用 Garden MCP 的 get_my_status 查看当前局面。"
    result = telegram_proactive.handle_galatea_garden_wake("game_turn_required", message)

    assert result == {
        "ok": True,
        "injected": True,
        "delivered": True,
        "channel": "sumitalk",
        "window_id": "sumitalk-main",
        "archive_round_index": 9,
    }
    assert calls["generate"]["prompt"] == message
    assert calls["generate"]["preferred_channel"] == "sumitalk"
    assert calls["generate"]["reply_target"] == "device-1"
    assert calls["generate"]["wakeup_kind"] == "galatea_garden"
    assert calls["dispatch"]["window_id"] == "sumitalk-main"


def test_delivery_failure_is_still_successful_injection(monkeypatch):
    monkeypatch.setattr(
        telegram_proactive,
        "resolve_recent_reply_context",
        lambda: {"channel": "tg", "window_id": "tg_123", "target": "123"},
    )
    monkeypatch.setattr(
        telegram_proactive,
        "_generate_schedule_reply",
        lambda **kwargs: {"text": "醒了。", "qq_group_id": "", "archive_round_index": 3},
    )
    monkeypatch.setattr(telegram_proactive, "_dispatch_send", lambda *args, **kwargs: False)

    result = telegram_proactive.handle_galatea_garden_wake("game_turn_required", "轮到你了。")

    assert result["injected"] is True
    assert result["delivered"] is False


def test_gateway_failure_does_not_attempt_delivery(monkeypatch):
    delivered = []
    monkeypatch.setattr(
        telegram_proactive,
        "resolve_recent_reply_context",
        lambda: {"channel": "qq", "window_id": "qq-main", "target": ""},
    )
    monkeypatch.setattr(telegram_proactive, "_generate_schedule_reply", lambda **kwargs: None)
    monkeypatch.setattr(telegram_proactive, "_dispatch_send", lambda *args, **kwargs: delivered.append(True))

    result = telegram_proactive.handle_galatea_garden_wake("game_turn_required", "轮到你了。")

    assert result["injected"] is False
    assert result["error"] == "gateway_call_failed"
    assert delivered == []


def test_injector_accepts_one_protocol_line_and_does_not_retry_delivery_failure():
    calls = []

    def handler(reason, message):
        calls.append((reason, message))
        return {"ok": True, "injected": True, "delivered": False, "channel": "qq", "window_id": "qq-main"}

    raw = json.dumps(
        {
            "version": 1,
            "type": "garden_wake",
            "reason": "game_turn_required",
            "message": "轮到你了。",
        },
        ensure_ascii=False,
    )
    exit_code, response = run_injector(raw + "\n", handler)

    assert exit_code == 0
    assert response["injected"] is True
    assert response["delivered"] is False
    assert calls == [("game_turn_required", "轮到你了。")]


def test_injector_rejects_multiple_or_unsupported_lines():
    valid = '{"version":1,"type":"garden_wake","reason":"r","message":"m"}'
    assert parse_wake_envelope(valid)["message"] == "m"

    for raw in (valid + "\n" + valid, '{"version":2,"type":"garden_wake","reason":"r","message":"m"}'):
        try:
            parse_wake_envelope(raw)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid wake envelope was accepted")
