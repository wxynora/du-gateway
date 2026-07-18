from __future__ import annotations

import json
from typing import Any

from storage import watch_runtime_store


WATCH_SESSION_BODY_KEY = "watch_session_id"
WATCH_SNAPSHOT_BODY_KEY = "watch_snapshot"
PAST_WINDOW_MS = 5 * 60_000
FUTURE_WINDOW_MS = 2 * 60_000


def _int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def _compact_text(value: Any, limit: int = 900) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return text[:limit]


def _normalize_snapshot(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {}
    required = {
        "media_id",
        "playhead_ms",
        "is_playing",
        "playback_rate",
        "timeline_epoch",
        "snapshot_seq",
        "captured_at",
    }
    if any(key not in raw for key in required):
        return {}
    media_id = _compact_text(raw.get("media_id"), 240)
    captured_at = _compact_text(raw.get("captured_at"), 80)
    if not media_id or not captured_at:
        return {}
    try:
        playback_rate = min(4.0, max(0.25, float(raw.get("playback_rate") or 1.0)))
    except (TypeError, ValueError):
        playback_rate = 1.0
    return {
        "media_id": media_id,
        "playhead_ms": _int(raw.get("playhead_ms"), 0),
        "is_playing": raw.get("is_playing") is True,
        "playback_rate": playback_rate,
        "timeline_epoch": _int(raw.get("timeline_epoch"), 0),
        "snapshot_seq": _int(raw.get("snapshot_seq"), 0),
        "captured_at": captured_at,
    }


def _chunk_view(chunk: dict) -> dict:
    return {
        "start_ms": _int(chunk.get("start_ms"), 0),
        "end_ms": _int(chunk.get("end_ms"), 0),
        "summary": _compact_text(chunk.get("summary")),
        "visual_description": _compact_text(chunk.get("visual_description")),
        "dialogue_summary": _compact_text(chunk.get("dialogue_summary")),
        "characters": chunk.get("characters") if isinstance(chunk.get("characters"), list) else [],
    }


def _eligible_story_summary(session: dict, playhead_ms: int) -> dict:
    if str((session.get("mode") or {}).get("knowledge_mode") or "") != "needs_summary":
        return {}
    summary = (session.get("analysis") or {}).get("story_so_far")
    if not isinstance(summary, dict) or not summary:
        return {}
    try:
        through_ms = int(float(summary["through_ms"]))
    except (KeyError, TypeError, ValueError):
        return {}
    if through_ms < 0 or through_ms > playhead_ms:
        return {}
    return summary


def build_watch_context(
    *,
    session_id: str,
    snapshot: dict,
    window_id: str,
) -> tuple[str, dict] | None:
    session = watch_runtime_store.get_session(session_id)
    if not session or session.get("ended_at"):
        return None
    session_window_id = str(session.get("window_id") or "").strip()
    if session_window_id and window_id and session_window_id != window_id:
        return None
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    if snapshot.get("media_id") != media.get("id"):
        return None

    playhead_ms = _int(snapshot.get("playhead_ms"), 0)
    timeline_epoch = _int(snapshot.get("timeline_epoch"), 0)
    chunks = watch_runtime_store.get_plot_chunks(
        session_id,
        timeline_epoch=timeline_epoch,
        start_before_ms=playhead_ms + FUTURE_WINDOW_MS,
        end_after_ms=max(0, playhead_ms - PAST_WINDOW_MS),
        limit=24,
    )
    completed_chunks = [item for item in chunks if _int(item.get("end_ms")) <= playhead_ms]
    past = [
        _chunk_view(item)
        for item in completed_chunks
        if _int(item.get("end_ms")) < max(0, playhead_ms - 30_000)
    ][-6:]
    current = [
        _chunk_view(item)
        for item in completed_chunks
        if _int(item.get("end_ms")) >= max(0, playhead_ms - 30_000)
    ][-4:]
    future = [
        _chunk_view(item)
        for item in chunks
        if playhead_ms < _int(item.get("start_ms")) <= playhead_ms + FUTURE_WINDOW_MS
    ][:8]
    story_summary = _eligible_story_summary(session, playhead_ms)
    analysis = session.get("analysis") if isinstance(session.get("analysis"), dict) else {}
    mode = session.get("mode") if isinstance(session.get("mode"), dict) else {}

    visible_context = {
        "work": {
            "title": media.get("title") or "",
            "part_title": media.get("part_title") or "",
            "identity": analysis.get("identity") or "",
        },
        "snapshot": snapshot,
        "knowledge_mode": mode.get("knowledge_mode") or "known",
        "analysis_status": analysis.get("status") or "pending",
        "story_so_far": story_summary,
        "recent_chunks": past,
        "current_chunks": current,
    }
    future_context = {
        "window_end_ms": playhead_ms + FUTURE_WINDOW_MS,
        "chunks": future,
    }
    action_context = {
        "session_id": session_id,
        "media_id": str(media.get("id") or ""),
        "snapshot": snapshot,
        "future_until_ms": playhead_ms + FUTURE_WINDOW_MS,
    }

    lines = [
        "【一起看动态上下文】",
        "这是小玥发送这条消息时的真实播放快照。当前回合看到哪里的边界只认 snapshot.playhead_ms，不能用后台更新后的进度改写。",
        "可见回复只能使用 work、story_so_far、recent_chunks 和 current_chunks 中不晚于播放快照的信息；不要剧透，也不要暗示后续走向。",
        "如果当前分析片段为空或 analysis_status 尚未 ready，就自然承认这一小段没看清，不要编造画面或剧情。",
        "VISIBLE_CONTEXT=" + json.dumps(visible_context, ensure_ascii=False, separators=(",", ":")),
    ]
    if bool(mode.get("danmaku_enabled")) and future:
        lines.extend(
            [
                "下面 FUTURE_ACTION_CONTEXT 最多覆盖快照后两分钟，只能用来决定是否安排一条稍后显示的隐藏弹幕。",
                "这些未来信息绝对不能出现在可见回复里；如果无法严格分开，就不要生成弹幕动作。",
                "FUTURE_ACTION_CONTEXT=" + json.dumps(future_context, ensure_ascii=False, separators=(",", ":")),
                "想安排弹幕时，在正常回复末尾追加且最多追加一个隐藏块，正文中不要解释：",
                "<<<DU_WATCH_ACTION>>>",
                '{"type":"danmaku","session_id":"'
                + session_id
                + '","timeline_epoch":'
                + str(timeline_epoch)
                + ',"target_ms":整数媒体时间,"text":"弹幕文字","action_id":"稳定唯一标识"}',
                "<<<END_DU_WATCH_ACTION>>>",
                "target_ms 必须大于当前 playhead_ms，且不超过 FUTURE_ACTION_CONTEXT.window_end_ms。没有自然想说的弹幕就不要输出隐藏块。",
            ]
        )
    else:
        lines.append("本轮没有可用的未来动作片段，不要生成 DU_WATCH_ACTION 隐藏块。")
    return "\n".join(lines), action_context


def inject_watch_context(
    body: dict,
    *,
    window_id: str,
    reply_channel: str,
) -> tuple[dict, dict]:
    if not isinstance(body, dict):
        return body, {}
    next_body = dict(body)
    session_id = str(next_body.pop(WATCH_SESSION_BODY_KEY, "") or "").strip()
    snapshot = _normalize_snapshot(next_body.pop(WATCH_SNAPSHOT_BODY_KEY, None))
    if str(reply_channel or "").strip().lower() != "sumitalk" or not session_id or not snapshot:
        return next_body, {}
    built = build_watch_context(session_id=session_id, snapshot=snapshot, window_id=window_id)
    if built is None:
        return next_body, {}
    prompt, action_context = built
    messages = next_body.get("messages") if isinstance(next_body.get("messages"), list) else []
    next_body["messages"] = [
        {"role": "system", "content": prompt, "__dynamic__": True},
        *list(messages),
    ]
    return next_body, action_context
