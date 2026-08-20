"""Per-window continuity state produced by the existing memory query rewriter."""

from __future__ import annotations

import time

from storage import runtime_sqlite
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)


def normalize_topic_state(state: dict | None) -> dict:
    raw = state if isinstance(state, dict) else {}
    anchors: list[str] = []
    seen: set[str] = set()
    for value in raw.get("anchors") or []:
        anchor = str(value or "").strip()
        if not anchor or anchor in seen:
            continue
        seen.add(anchor)
        anchors.append(anchor)
    normalized = {
        "active_topic": str(raw.get("active_topic") or "").strip(),
        "current_focus": str(raw.get("current_focus") or "").strip(),
        "anchors": anchors,
    }
    if not any((normalized["active_topic"], normalized["current_focus"], normalized["anchors"])):
        return {}
    return normalized


def get_topic_state_record(window_id: str) -> dict:
    wid = str(window_id or "").strip()
    if not wid:
        return {"state": {}, "observed_at": None}
    try:
        with runtime_sqlite.connect() as conn:
            row = conn.execute(
                "SELECT state_json, observed_at FROM query_topic_states WHERE window_id = ?",
                (wid,),
            ).fetchone()
        if row is None:
            return {"state": {}, "observed_at": None}
        return {
            "state": normalize_topic_state(runtime_sqlite.json_loads(row["state_json"], {})),
            "observed_at": float(row["observed_at"]),
        }
    except Exception as exc:
        logger.warning("query topic state read failed window_id=%s error=%s", wid, exc)
        return {"state": {}, "observed_at": None}


def get_topic_state(window_id: str) -> dict:
    return dict(get_topic_state_record(window_id).get("state") or {})


def _save_topic_state_value(
    window_id: str,
    state: dict,
    *,
    observed_at: float | None,
    allow_empty: bool,
) -> bool:
    wid = str(window_id or "").strip()
    normalized = normalize_topic_state(state)
    if not wid or (not normalized and not allow_empty):
        return False
    observed = float(observed_at if observed_at is not None else time.time())
    try:
        with runtime_sqlite.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO query_topic_states (window_id, state_json, observed_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(window_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    observed_at = excluded.observed_at,
                    updated_at = excluded.updated_at
                WHERE excluded.observed_at >= query_topic_states.observed_at
                """,
                (
                    wid,
                    runtime_sqlite.json_dumps(normalized),
                    observed,
                    now_beijing_iso(),
                ),
            )
        return int(cursor.rowcount or 0) > 0
    except Exception as exc:
        logger.warning("query topic state save failed window_id=%s error=%s", wid, exc)
        return False


def save_topic_state(window_id: str, state: dict, *, observed_at: float | None = None) -> bool:
    return _save_topic_state_value(
        window_id,
        state,
        observed_at=observed_at,
        allow_empty=False,
    )


def clear_topic_state(window_id: str, *, observed_at: float | None = None) -> bool:
    return _save_topic_state_value(
        window_id,
        {},
        observed_at=observed_at,
        allow_empty=True,
    )
