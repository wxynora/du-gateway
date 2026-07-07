"""Local markers for app-only recalled SumiTalk messages."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from storage import runtime_sqlite
from utils.log import get_logger

logger = get_logger(__name__)

_RECALLED_PREFIX = "【已撤回】"
_MAX_MARKERS = 500


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text_from_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                elif "text" in item:
                    parts.append(str(item.get("text") or ""))
                elif "content" in item:
                    parts.append(_text_from_content(item.get("content")))
        return "".join(parts).strip()
    if isinstance(content, dict):
        if content.get("type") == "text":
            return str(content.get("text") or "").strip()
        if "text" in content:
            return str(content.get("text") or "").strip()
        if "content" in content:
            return _text_from_content(content.get("content"))
    return str(content).strip()


def _marker_id(window_id: str, message_id: str, content: str) -> str:
    raw = f"{window_id}\n{message_id}\n{content}"
    digest = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()
    return f"recall_{digest}"


def _recalled_text(content: str) -> str:
    text = str(content or "").strip()
    if text.startswith(_RECALLED_PREFIX):
        return text
    return f"{_RECALLED_PREFIX}{text}" if text else _RECALLED_PREFIX


def record_recall_message_result(item: dict) -> int:
    """Persist finished recall_message results so short context can preserve the trace."""
    if not isinstance(item, dict) or str(item.get("type") or "").strip() != "recall_message":
        return 0
    if str(item.get("status") or "").strip().lower() != "done":
        return 0
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    messages = result.get("recalledMessages")
    if not isinstance(messages, list):
        messages = result.get("recalled_messages")
    if not isinstance(messages, list):
        messages = []
    payload_window_id = str(payload.get("windowId") or payload.get("window_id") or "").strip()
    result_window_id = str(result.get("windowId") or result.get("window_id") or "").strip()
    reply_text = str(
        result.get("replyText")
        or result.get("reply_text")
        or payload.get("replyText")
        or payload.get("reply_text")
        or ""
    ).strip()[:500]
    if payload_window_id and result_window_id and payload_window_id != result_window_id:
        logger.warning(
            "recall_message_marker_window_mismatch action_id=%s payload_window=%s result_window=%s",
            str(item.get("id") or ""),
            payload_window_id,
            result_window_id,
        )
    window_id = payload_window_id or result_window_id
    created_at = _utc_now_iso()
    rows: list[tuple[str, str, str, str, str, str]] = []
    for raw in messages:
        if not isinstance(raw, dict):
            continue
        message_id = str(raw.get("id") or raw.get("messageId") or raw.get("message_id") or "").strip()
        content = str(raw.get("content") or raw.get("text") or "").strip()
        if not message_id or not content:
            continue
        safe_content = content[:3000]
        row_id = _marker_id(window_id, message_id, safe_content)
        rows.append((
            row_id,
            window_id,
            message_id,
            safe_content,
            runtime_sqlite.json_dumps({
                "choiceId": str(result.get("choiceId") or result.get("choice_id") or "").strip(),
                "choiceLabel": str(result.get("choiceLabel") or result.get("label") or "").strip()[:80],
                "autoSelected": bool(result.get("autoSelected") or result.get("auto_selected")),
                "actionId": str(item.get("id") or ""),
                "replyText": reply_text,
            }),
            created_at,
        ))
    if not rows:
        return 0
    try:
        with runtime_sqlite.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO recall_message_markers
                        (id, window_id, message_id, content, result_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                conn.execute(
                    """
                    DELETE FROM recall_message_markers
                    WHERE id NOT IN (
                        SELECT id
                        FROM recall_message_markers
                        ORDER BY created_at DESC
                        LIMIT ?
                    )
                    """,
                    (_MAX_MARKERS,),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        logger.info("recall_message_markers_recorded window_id=%s count=%s", window_id, len(rows))
        return len(rows)
    except Exception as e:
        logger.warning("recall_message_markers_record_failed window_id=%s error=%s", window_id, e)
        return 0


def _load_markers(window_id: str = "") -> list[dict]:
    wid = str(window_id or "").strip()
    try:
        with runtime_sqlite.connect() as conn:
            if wid:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM recall_message_markers
                    WHERE window_id = ? OR window_id = ''
                    ORDER BY created_at DESC
                    LIMIT 200
                    """,
                    (wid,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM recall_message_markers
                    ORDER BY created_at DESC
                    LIMIT 200
                    """
                ).fetchall()
    except Exception as e:
        logger.debug("recall_message_markers_load_failed window_id=%s error=%s", wid, e)
        return []
    return [
        {
            "windowId": str(row["window_id"] or ""),
            "messageId": str(row["message_id"] or ""),
            "content": str(row["content"] or ""),
            "createdAt": str(row["created_at"] or ""),
        }
        for row in rows
    ]


def apply_recall_markers_to_rounds(rounds: list, window_id: str = "") -> list:
    """Mark recalled user messages in recent context without deleting archive data."""
    markers = _load_markers(window_id)
    if not markers:
        return rounds
    by_id = {str(row.get("messageId") or "").strip(): row for row in markers if str(row.get("messageId") or "").strip()}
    by_text = {str(row.get("content") or "").strip(): row for row in markers if str(row.get("content") or "").strip()}
    if not by_id and not by_text:
        return rounds
    changed = False
    next_rounds = []
    for round_obj in rounds or []:
        if not isinstance(round_obj, dict):
            next_rounds.append(round_obj)
            continue
        next_round = dict(round_obj)
        next_messages = []
        for msg in next_round.get("messages") or []:
            if not isinstance(msg, dict):
                next_messages.append(msg)
                continue
            role = str(msg.get("role") or "").strip().lower()
            if role != "user":
                next_messages.append(msg)
                continue
            content_text = _text_from_content(msg.get("content"))
            if content_text.startswith(_RECALLED_PREFIX):
                next_messages.append(msg)
                continue
            message_ids = [
                str(msg.get("id") or "").strip(),
                str(msg.get("messageId") or msg.get("message_id") or "").strip(),
                str(msg.get("clientRequestId") or msg.get("client_request_id") or "").strip(),
            ]
            marker = next((by_id.get(mid) for mid in message_ids if mid and by_id.get(mid)), None)
            if marker is None and content_text:
                marker = by_text.get(content_text)
            if marker is None:
                next_messages.append(msg)
                continue
            next_msg = dict(msg)
            next_msg["content"] = _recalled_text(str(marker.get("content") or content_text))
            next_messages.append(next_msg)
            changed = True
        next_round["messages"] = next_messages
        next_rounds.append(next_round)
    return next_rounds if changed else rounds
