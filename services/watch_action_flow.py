from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from services.hidden_blocks import HiddenBlockParser
from storage import watch_runtime_store


logger = logging.getLogger(__name__)
MARKER_START = "<<<DU_WATCH_ACTION>>>"
MARKER_END = "<<<END_DU_WATCH_ACTION>>>"
SHORT_MARKER = "[du:danmaku 00:32:18 弹幕内容]"
_HIDDEN_BLOCK = HiddenBlockParser.for_markers(
    "DU_WATCH_ACTION",
    MARKER_START,
    MARKER_END,
    short_markers=("du:danmaku",),
)

_SHORT_ACTION_RE = re.compile(r"^\s*(\d{1,3}:\d{2}(?::\d{2})?)\s+([\s\S]+?)\s*$")


def _clock_to_ms(value: str) -> int | None:
    parts = str(value or "").strip().split(":")
    if len(parts) not in {2, 3}:
        return None
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if any(number < 0 for number in numbers) or numbers[-1] >= 60:
        return None
    if len(numbers) == 2:
        minutes, seconds = numbers
        return (minutes * 60 + seconds) * 1000
    hours, minutes, seconds = numbers
    if minutes >= 60:
        return None
    return (hours * 3600 + minutes * 60 + seconds) * 1000


def _parse_action(raw: str) -> dict | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        item = json.loads(text)
    except Exception:
        item = None
    if isinstance(item, dict):
        return item
    match = _SHORT_ACTION_RE.match(text)
    if not match:
        return None
    target_ms = _clock_to_ms(match.group(1))
    action_text = match.group(2).replace("\x00", "").strip()
    if target_ms is None or not action_text:
        return None
    return {"type": "danmaku", "target_ms": target_ms, "text": action_text}


def compute_visible_streaming(text: str) -> str:
    return _HIDDEN_BLOCK.compute_visible_streaming(str(text or ""))


def split_watch_actions(text: str) -> tuple[str, list[dict]]:
    visible, raw_actions = _HIDDEN_BLOCK.split_all(str(text or ""))
    actions: list[dict] = []
    for raw in raw_actions:
        item = _parse_action(raw)
        if isinstance(item, dict):
            actions.append(item)
        else:
            logger.info("一起看弹幕标记未解析 reason=invalid_or_missing_media_time")
    return visible, actions


def build_watch_danmaku_event(action: dict, *, context: dict | None) -> dict | None:
    if not isinstance(action, dict) or not isinstance(context, dict):
        return None
    if str(action.get("type") or "").strip().lower() != "danmaku":
        return None

    session_id = str(context.get("session_id") or "").strip()
    legacy_session_id = str(action.get("session_id") or "").strip()
    if not session_id or (legacy_session_id and legacy_session_id != session_id):
        return None
    session = watch_runtime_store.get_session(session_id)
    if not session or session.get("ended_at"):
        return None
    if not bool((session.get("mode") or {}).get("danmaku_enabled")):
        return None

    snapshot = context.get("snapshot") if isinstance(context.get("snapshot"), dict) else {}
    media_id = str(context.get("media_id") or "").strip()
    if not media_id or media_id != str((session.get("media") or {}).get("id") or "").strip():
        return None
    try:
        snapshot_epoch = int(snapshot.get("timeline_epoch"))
        current_epoch = int((session.get("playback") or {}).get("timeline_epoch") or 0)
        current_playhead_ms = int((session.get("playback") or {}).get("playhead_ms") or 0)
        target_ms = int(float(action.get("target_ms")))
        seen_ms = int(float(snapshot.get("playhead_ms") or 0))
    except (TypeError, ValueError):
        return None
    legacy_epoch = action.get("timeline_epoch")
    if legacy_epoch is not None:
        try:
            if int(legacy_epoch) != snapshot_epoch:
                return None
        except (TypeError, ValueError):
            return None
    if snapshot_epoch != current_epoch:
        return None
    if target_ms <= max(seen_ms, current_playhead_ms):
        logger.info(
            "一起看弹幕未发出 reason=target_not_future session_id=%s target_ms=%s "
            "snapshot_playhead_ms=%s current_playhead_ms=%s reply_until_ms=%s",
            session_id,
            target_ms,
            seen_ms,
            current_playhead_ms,
            int(context.get("reply_until_ms") or 0),
        )
        return None
    if target_ms > seen_ms + 120_000:
        logger.info(
            "一起看弹幕未发出 reason=target_outside_future_window session_id=%s "
            "target_ms=%s snapshot_playhead_ms=%s",
            session_id,
            target_ms,
            seen_ms,
        )
        return None

    text = str(action.get("text") or "").replace("\x00", "").strip()
    if not text or len(text) > 120:
        return None
    digest = hashlib.sha256(
        f"{session_id}:{snapshot_epoch}:{target_ms}:{text}".encode("utf-8")
    ).hexdigest()[:20]
    action_id = f"watch_action_{digest}"
    return {
        "part_id": f"watch-danmaku-{action_id}",
        "action_id": action_id,
        "type": "danmaku",
        "session_id": session_id,
        "media_id": media_id,
        "timeline_epoch": snapshot_epoch,
        "target_ms": target_ms,
        "text": text,
        "created_from_snapshot": {
            "playhead_ms": seen_ms,
            "captured_at": str(snapshot.get("captured_at") or "").strip(),
        },
    }


def watch_action_dedup_key(event: dict) -> str:
    return ":".join(
        (
            str(event.get("session_id") or ""),
            str(event.get("timeline_epoch") or ""),
            str(event.get("action_id") or ""),
        )
    )
