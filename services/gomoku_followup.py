from __future__ import annotations


EMPTY_PLAYER_MESSAGE = "小玥没有回复内容"


def send_gomoku_wakeup(
    *,
    window_id: str,
    target: str,
    system_text: str,
    user_content: str,
    created_at: str | None = None,
    preferred_channel: str = "",
    preferred_meta: dict | None = None,
    return_only: bool = True,
) -> dict:
    from services.conversation_followup import _send_wakeup_event

    raw_player_content = str(user_content or "")
    player_content = raw_player_content if raw_player_content.strip() else EMPTY_PLAYER_MESSAGE
    return _send_wakeup_event(
        window_id=window_id,
        target=target,
        event_text=str(system_text or "").strip(),
        created_at=created_at,
        archive=True,
        wakeup_kind="gomoku",
        system_event=True,
        system_event_user_summary=player_content,
        dynamic_system_event=True,
        preferred_channel_override=preferred_channel,
        preferred_target_override=target,
        preferred_meta_override=preferred_meta,
        lock_preferred_channel=bool(preferred_channel),
        allow_followup=not return_only,
        return_only=return_only,
        sumitalk_prompt_assembly=True,
    )
