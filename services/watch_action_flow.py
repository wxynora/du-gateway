from __future__ import annotations

import hashlib
import json
from typing import Any

from services.hidden_blocks import HiddenBlockParser
from storage import watch_runtime_store


MARKER_START = "<<<DU_WATCH_ACTION>>>"
MARKER_END = "<<<END_DU_WATCH_ACTION>>>"
_HIDDEN_BLOCK = HiddenBlockParser.for_markers(
    "DU_WATCH_ACTION",
    MARKER_START,
    MARKER_END,
)


def compute_visible_streaming(text: str) -> str:
    return _HIDDEN_BLOCK.compute_visible_streaming(str(text or ""))


def split_watch_actions(text: str) -> tuple[str, list[dict]]:
    visible, raw_actions = _HIDDEN_BLOCK.split_all(str(text or ""))
    actions: list[dict] = []
    for raw in raw_actions:
        try:
            item = json.loads(str(raw or "").strip())
        except Exception:
            item = None
        if isinstance(item, dict):
            actions.append(item)
    return visible, actions


def build_watch_danmaku_event(action: dict, *, context: dict | None) -> dict | None:
    if not isinstance(action, dict) or not isinstance(context, dict):
        return None
    if str(action.get("type") or "").strip().lower() != "danmaku":
        return None

    session_id = str(context.get("session_id") or "").strip()
    if not session_id or str(action.get("session_id") or "").strip() != session_id:
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
        action_epoch = int(action.get("timeline_epoch"))
        snapshot_epoch = int(snapshot.get("timeline_epoch"))
        current_epoch = int((session.get("playback") or {}).get("timeline_epoch") or 0)
        current_playhead_ms = int((session.get("playback") or {}).get("playhead_ms") or 0)
        target_ms = int(float(action.get("target_ms")))
        seen_ms = int(float(snapshot.get("playhead_ms") or 0))
    except (TypeError, ValueError):
        return None
    if action_epoch != snapshot_epoch or action_epoch != current_epoch:
        return None
    if target_ms <= max(seen_ms, current_playhead_ms) or target_ms > seen_ms + 120_000:
        return None

    text = str(action.get("text") or "").replace("\x00", "").strip()
    if not text or len(text) > 120:
        return None
    action_id = str(action.get("action_id") or "").strip()
    if not action_id:
        digest = hashlib.sha256(
            f"{session_id}:{action_epoch}:{target_ms}:{text}".encode("utf-8")
        ).hexdigest()[:20]
        action_id = f"watch_action_{digest}"
    action_id = action_id[:160]
    return {
        "part_id": f"watch-danmaku-{action_id}",
        "action_id": action_id,
        "type": "danmaku",
        "session_id": session_id,
        "media_id": media_id,
        "timeline_epoch": action_epoch,
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
