"""Short-lived recall targets for app-only SumiTalk message recall."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from storage import runtime_sqlite
from utils.log import get_logger

logger = get_logger(__name__)

_MAX_TURNS_PER_WINDOW = 10
_MAX_TARGETS_PER_TURN = 8
_MAX_TEXT_CHARS = 300
_TTL_SECONDS = 24 * 60 * 60


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _candidate_set_id(window_id: str, client_request_id: str) -> str:
    raw = f"{window_id}\n{client_request_id}"
    digest = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()
    return f"recall_targets_{digest[:24]}"


def _clean_text(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "..."
    return text


def _int_or_none(value: Any) -> int | None:
    try:
        out = int(value)
        return out if out > 0 else None
    except Exception:
        return None


def _normalize_targets(raw_targets: Any) -> list[dict]:
    if isinstance(raw_targets, dict):
        raw_targets = raw_targets.get("targets")
    if not isinstance(raw_targets, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for raw in raw_targets:
        if not isinstance(raw, dict):
            continue
        message_id = str(
            raw.get("id")
            or raw.get("messageId")
            or raw.get("message_id")
            or ""
        ).strip()
        if not message_id or message_id in seen:
            continue
        seen.add(message_id)
        index = _int_or_none(raw.get("index")) or len(out) + 1
        text = _clean_text(raw.get("text") or raw.get("content") or raw.get("preview"))
        created_at = str(raw.get("createdAt") or raw.get("created_at") or "").strip()
        source = str(raw.get("source") or "").strip()[:40]
        out.append({
            "index": index,
            "id": message_id[:160],
            "text": text,
            "createdAt": created_at,
            "source": source,
        })
        if len(out) >= _MAX_TARGETS_PER_TURN:
            break
    for pos, item in enumerate(out, start=1):
        item["index"] = pos
    return out


def _row_to_set(row) -> dict:
    targets = runtime_sqlite.json_loads(row["targets_json"], [])
    if not isinstance(targets, list):
        targets = []
    return {
        "candidateSetId": str(row["candidate_set_id"] or ""),
        "windowId": str(row["window_id"] or ""),
        "clientRequestId": str(row["client_request_id"] or ""),
        "targets": targets,
        "createdAt": str(row["created_at"] or ""),
        "expiresAt": str(row["expires_at"] or ""),
    }


def _prune(conn, window_id: str, now_iso: str) -> None:
    conn.execute("DELETE FROM recall_message_targets WHERE expires_at <= ?", (now_iso,))
    if not window_id:
        return
    conn.execute(
        """
        DELETE FROM recall_message_targets
        WHERE window_id = ?
          AND candidate_set_id NOT IN (
            SELECT candidate_set_id
            FROM recall_message_targets
            WHERE window_id = ?
            ORDER BY created_at DESC
            LIMIT ?
          )
        """,
        (window_id, window_id, _MAX_TURNS_PER_WINDOW),
    )


def record_recall_targets(
    *,
    window_id: str,
    client_request_id: str,
    targets: Any,
) -> dict:
    window = str(window_id or "").strip()
    client_id = str(client_request_id or "").strip()
    clean_targets = _normalize_targets(targets)
    if not window or not client_id or not clean_targets:
        return {"ok": False, "saved": False, "reason": "empty"}
    now = _utc_now()
    now_iso = _iso(now)
    expires_at = _iso(now + timedelta(seconds=_TTL_SECONDS))
    candidate_set_id = _candidate_set_id(window, client_id)
    try:
        with runtime_sqlite.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                _prune(conn, window, now_iso)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO recall_message_targets
                        (candidate_set_id, window_id, client_request_id, targets_json, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate_set_id,
                        window,
                        client_id,
                        runtime_sqlite.json_dumps(clean_targets),
                        now_iso,
                        expires_at,
                    ),
                )
                _prune(conn, window, now_iso)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        logger.info("recall_targets_recorded window_id=%s client_request_id=%s count=%s", window, client_id, len(clean_targets))
        return {"ok": True, "saved": True, "candidateSetId": candidate_set_id, "count": len(clean_targets)}
    except Exception as e:
        logger.warning("recall_targets_record_failed window_id=%s client_request_id=%s error=%s", window, client_id, e)
        return {"ok": False, "saved": False, "error": str(e)}


def consume_recall_targets_from_body(body: dict, *, window_id: str, client_request_id: str) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "saved": False, "reason": "body_not_object"}
    raw_targets = body.pop("recall_targets", None)
    if raw_targets is None:
        raw_targets = body.pop("recallTargets", None)
    if raw_targets is None:
        return {"ok": False, "saved": False, "reason": "missing"}
    return record_recall_targets(
        window_id=window_id,
        client_request_id=client_request_id,
        targets=raw_targets,
    )


def _load_candidate_sets(
    *,
    window_id: str,
    client_request_id: str = "",
    candidate_set_id: str = "",
    limit: int = _MAX_TURNS_PER_WINDOW,
) -> list[dict]:
    window = str(window_id or "").strip()
    client_id = str(client_request_id or "").strip()
    set_id = str(candidate_set_id or "").strip()
    if not window:
        return []
    now_iso = _iso(_utc_now())
    try:
        max_rows = max(1, min(int(limit or _MAX_TURNS_PER_WINDOW), _MAX_TURNS_PER_WINDOW))
    except Exception:
        max_rows = _MAX_TURNS_PER_WINDOW
    try:
        with runtime_sqlite.connect() as conn:
            _prune(conn, window, now_iso)
            if set_id:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM recall_message_targets
                    WHERE window_id = ?
                      AND candidate_set_id = ?
                      AND expires_at > ?
                    LIMIT 1
                    """,
                    (window, set_id, now_iso),
                ).fetchall()
            elif client_id:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM recall_message_targets
                    WHERE window_id = ?
                      AND client_request_id = ?
                      AND expires_at > ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (window, client_id, now_iso),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM recall_message_targets
                    WHERE window_id = ?
                      AND expires_at > ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (window, now_iso, max_rows),
                ).fetchall()
    except Exception as e:
        logger.warning("recall_targets_load_failed window_id=%s error=%s", window, e)
        return []
    return [_row_to_set(row) for row in rows]


def _public_candidates(candidate_sets: list[dict], *, matches: list[tuple[dict, dict]] | None = None) -> list[dict]:
    if matches is None:
        pairs: list[tuple[dict, dict]] = []
        for candidate_set in candidate_sets:
            for target in candidate_set.get("targets") or []:
                if isinstance(target, dict):
                    pairs.append((candidate_set, target))
    else:
        pairs = matches
    out: list[dict] = []
    for candidate_set, target in pairs[:24]:
        out.append({
            "candidateSetId": candidate_set.get("candidateSetId") or "",
            "clientRequestId": candidate_set.get("clientRequestId") or "",
            "index": int(target.get("index") or 0),
            "messageId": str(target.get("id") or ""),
            "textPreview": _clean_text(target.get("text") or "", 120),
        })
    return out


def _parse_indexes(value: Any) -> list[int]:
    if value is None:
        return []
    raw = value if isinstance(value, list) else [value]
    out: list[int] = []
    seen: set[int] = set()
    for item in raw:
        idx = _int_or_none(item)
        if idx is None or idx in seen:
            continue
        seen.add(idx)
        out.append(idx)
    return out


def resolve_recall_message_targets(
    *,
    window_id: str,
    client_request_id: str = "",
    candidate_set_id: str = "",
    indexes: Any = None,
    target_text: str = "",
    select_all_when_unqualified: bool = False,
) -> dict:
    candidate_sets = _load_candidate_sets(
        window_id=window_id,
        client_request_id=client_request_id,
        candidate_set_id=candidate_set_id,
    )
    if not candidate_sets:
        return {
            "ok": False,
            "needsSelection": True,
            "error": "没有找到最近十轮可撤回气泡候选。",
            "candidates": [],
        }

    parsed_indexes = _parse_indexes(indexes)
    if parsed_indexes:
        selected_set = candidate_sets[0]
        selected: list[dict] = []
        wanted = set(parsed_indexes)
        for target in selected_set.get("targets") or []:
            if not isinstance(target, dict):
                continue
            if int(target.get("index") or 0) in wanted:
                selected.append(target)
        if selected and len(selected) == len(wanted):
            return {
                "ok": True,
                "messageIds": [str(target.get("id") or "") for target in selected if str(target.get("id") or "")],
                "candidateSetId": selected_set.get("candidateSetId") or "",
                "candidates": _public_candidates(candidate_sets, matches=[(selected_set, target) for target in selected]),
            }
        return {
            "ok": False,
            "needsSelection": True,
            "error": "没有找到指定序号的可撤回气泡。",
            "candidates": _public_candidates(candidate_sets),
        }

    query = str(target_text or "").strip()
    if query:
        exact: list[tuple[dict, dict]] = []
        fuzzy: list[tuple[dict, dict]] = []
        for candidate_set in candidate_sets:
            for target in candidate_set.get("targets") or []:
                if not isinstance(target, dict):
                    continue
                text = str(target.get("text") or "").strip()
                if not text:
                    continue
                if text == query:
                    exact.append((candidate_set, target))
                elif query in text or text in query:
                    fuzzy.append((candidate_set, target))
        matches = exact or fuzzy
        if len(matches) == 1:
            candidate_set, target = matches[0]
            return {
                "ok": True,
                "messageIds": [str(target.get("id") or "")],
                "candidateSetId": candidate_set.get("candidateSetId") or "",
                "candidates": _public_candidates(candidate_sets, matches=matches),
            }
        return {
            "ok": False,
            "needsSelection": True,
            "error": "需要选择要撤回的具体气泡。" if matches else "没有按文本匹配到唯一气泡。",
            "candidates": _public_candidates(candidate_sets, matches=matches or None),
        }

    if select_all_when_unqualified and len(candidate_sets) == 1:
        selected_set = candidate_sets[0]
        selected = [target for target in selected_set.get("targets") or [] if isinstance(target, dict)]
        message_ids = [str(target.get("id") or "") for target in selected if str(target.get("id") or "")]
        if message_ids:
            return {
                "ok": True,
                "messageIds": message_ids,
                "candidateSetId": selected_set.get("candidateSetId") or "",
                "candidates": _public_candidates(candidate_sets, matches=[(selected_set, target) for target in selected]),
            }

    return {
        "ok": False,
        "needsSelection": True,
        "error": "请选择要撤回的气泡序号或 messageId。",
        "candidates": _public_candidates(candidate_sets),
    }
