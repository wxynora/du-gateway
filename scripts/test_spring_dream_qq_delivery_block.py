from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import conversation_followup as followup
from services import spring_dream
from services import telegram_proactive
from storage import upstream_store


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class _Response:
    status_code = 200
    content = b"{}"
    text = ""

    def __init__(self, message: dict) -> None:
        self._message = message

    def json(self) -> dict:
        return {
            "choices": [{"message": self._message}],
            "du_gateway_archive_round_index": 0,
        }


def _run_case(
    *,
    wakeup_kind: str,
    preferred_channel: str,
    group_id: str = "",
    post_override: bool = False,
) -> tuple[dict, list[tuple], list[dict]]:
    dispatches: list[tuple] = []
    dream_archives: list[dict] = []
    message = {"role": "assistant", "content": "只用于验证的生成正文"}
    if group_id:
        message["du_qq_group_delivery"] = {"group_id": group_id}

    original_model = upstream_store.get_cached_active_model
    original_post_override = followup._post_spring_dream_prompt_override_for_trigger
    original_preference = followup._choice_dialog_delivery_preference
    original_available = telegram_proactive._available_channels
    original_dispatch = followup._dispatch_choice_dialog_reply
    original_group_send = followup._send_via_qq_group
    original_post = followup.requests.post
    original_archive = spring_dream.archive_spring_dream_body
    upstream_store.get_cached_active_model = lambda refresh_if_missing=False: "test-model"
    followup._post_spring_dream_prompt_override_for_trigger = (
        (lambda _kind, _created_at=None: {"prompt": "梦后提示", "sleep_session_key": "sleep-1"})
        if post_override
        else (lambda _kind, _created_at=None: {})
    )
    followup._choice_dialog_delivery_preference = lambda _target: (
        preferred_channel,
        "target-1",
        {"at": "2026-07-31T22:00:00+08:00"},
    )
    telegram_proactive._available_channels = lambda: ["qq", "sumitalk"]
    followup._dispatch_choice_dialog_reply = (
        lambda channel, target, text, **kwargs: dispatches.append((channel, target, text)) or True
    )
    followup._send_via_qq_group = (
        lambda text, target_group_id, split=True: dispatches.append(("qq_group", target_group_id, text)) or True
    )
    followup.requests.post = lambda *args, **kwargs: _Response(message)
    spring_dream.archive_spring_dream_body = lambda **kwargs: dream_archives.append(kwargs) or {
        "ok": True,
        "id": "dream-archive-1",
        "r2_key": "dreams/1.json",
    }
    try:
        result = followup._send_wakeup_event(
            window_id="tg_1",
            target="target-1",
            event_text="测试事件",
            wakeup_kind=wakeup_kind,
            stable_proactive_channel=False,
            archive=True,
            archive_after_delivery=True,
        )
    finally:
        upstream_store.get_cached_active_model = original_model
        followup._post_spring_dream_prompt_override_for_trigger = original_post_override
        followup._choice_dialog_delivery_preference = original_preference
        telegram_proactive._available_channels = original_available
        followup._dispatch_choice_dialog_reply = original_dispatch
        followup._send_via_qq_group = original_group_send
        followup.requests.post = original_post
        spring_dream.archive_spring_dream_body = original_archive
    return result, dispatches, dream_archives


def test_spring_dream_private_qq_is_blocked_and_archived() -> None:
    result, dispatches, archives = _run_case(wakeup_kind="spring_dream", preferred_channel="qq")
    _assert(result.get("error") == "qq_delivery_forbidden", f"unexpected result: {result}")
    _assert(result.get("dispatched") is False, f"blocked result marked dispatched: {result}")
    _assert(dispatches == [], f"QQ sender was called: {dispatches}")
    _assert(len(archives) == 1, f"spring dream body was not archived exactly once: {archives}")
    _assert(
        (archives[0].get("meta") or {}).get("delivery_status") == "not_dispatched",
        f"wrong archive delivery status: {archives[0]}",
    )


def test_post_spring_dream_private_qq_is_blocked() -> None:
    result, dispatches, archives = _run_case(wakeup_kind="post_spring_dream", preferred_channel="qq")
    _assert(result.get("error") == "qq_delivery_forbidden", f"unexpected result: {result}")
    _assert(dispatches == [], f"QQ sender was called: {dispatches}")
    _assert(archives == [], f"post-dream wakeup unexpectedly created a spring-dream archive: {archives}")


def test_prompt_override_path_is_also_blocked_from_qq() -> None:
    result, dispatches, _archives = _run_case(
        wakeup_kind="proactive_trigger",
        preferred_channel="qq",
        post_override=True,
    )
    _assert(result.get("error") == "qq_delivery_forbidden", f"override path leaked: {result}")
    _assert(dispatches == [], f"override path called QQ sender: {dispatches}")


def test_spring_dream_group_marker_is_blocked_before_group_sender() -> None:
    result, dispatches, archives = _run_case(
        wakeup_kind="spring_dream",
        preferred_channel="sumitalk",
        group_id="515831305",
    )
    _assert(result.get("error") == "qq_delivery_forbidden", f"group marker leaked: {result}")
    _assert(dispatches == [], f"group or fallback sender was called: {dispatches}")
    _assert(len(archives) == 1, f"blocked group dream was not archived: {archives}")


def test_ordinary_wakeup_can_still_use_qq() -> None:
    result, dispatches, archives = _run_case(wakeup_kind="proactive_trigger", preferred_channel="qq")
    _assert(result.get("ok") is True and result.get("channel") == "qq", f"ordinary QQ changed: {result}")
    _assert([item[0] for item in dispatches] == ["qq"], f"ordinary QQ sender was not called: {dispatches}")
    _assert(archives == [], f"ordinary wakeup created a dream archive: {archives}")


if __name__ == "__main__":
    test_spring_dream_private_qq_is_blocked_and_archived()
    test_post_spring_dream_private_qq_is_blocked()
    test_prompt_override_path_is_also_blocked_from_qq()
    test_spring_dream_group_marker_is_blocked_before_group_sender()
    test_ordinary_wakeup_can_still_use_qq()
    print("spring dream QQ delivery block tests passed")
