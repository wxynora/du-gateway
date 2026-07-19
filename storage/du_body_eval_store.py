"""Persistent local queue and audit log for the independent body-state evaluator."""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

from config import (
    DU_BODY_EVAL_AUDIT_KEEP,
    DU_BODY_EVAL_BATCH_SIZE,
    DU_BODY_EVAL_GRACE_SECONDS,
    DU_BODY_EVAL_LEASE_SECONDS,
    DU_BODY_EVAL_MAX_ATTEMPTS,
    DU_BODY_EVAL_PROMPT_VERSION,
)
from storage import runtime_sqlite

_FINAL_STATUSES = ("applied", "already_applied", "no_delta", "shadow", "skipped")


def _canonical_messages(messages: Any) -> list[dict]:
    out: list[dict] = []
    for item in messages if isinstance(messages, list) else []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        out.append({"role": role, "content": item.get("content")})
    return out


def round_hash(messages: Any) -> str:
    raw = runtime_sqlite.json_dumps(_canonical_messages(messages))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def idempotency_key(window_id: str, round_index: int, digest: str, prompt_version: str = "") -> str:
    version = str(prompt_version or DU_BODY_EVAL_PROMPT_VERSION).strip() or DU_BODY_EVAL_PROMPT_VERSION
    return f"body_delta:{str(window_id or '').strip()}:{int(round_index)}:{digest}:{version}"


def _prune_audit(conn) -> None:
    conn.execute(
        """
        DELETE FROM du_body_eval_audit
        WHERE id NOT IN (
            SELECT id FROM du_body_eval_audit ORDER BY id DESC LIMIT ?
        )
        """,
        (int(DU_BODY_EVAL_AUDIT_KEEP),),
    )


def enqueue_round(
    window_id: str,
    round_index: int,
    messages: list,
    *,
    round_timestamp: str = "",
    prompt_version: str = "",
    now: float | None = None,
) -> dict:
    wid = str(window_id or "").strip()
    idx = int(round_index or 0)
    canonical = _canonical_messages(messages)
    if not wid or idx <= 0 or not canonical:
        return {"queued": False, "reason": "invalid_round"}
    version = str(prompt_version or DU_BODY_EVAL_PROMPT_VERSION).strip() or DU_BODY_EVAL_PROMPT_VERSION
    digest = round_hash(canonical)
    idem = idempotency_key(wid, idx, digest, version)
    ts = float(now if now is not None else time.time())
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        finished = conn.execute(
            """
            SELECT 1 FROM du_body_eval_audit
            WHERE window_id = ? AND round_index = ? AND round_hash = ? AND prompt_version = ?
              AND status IN (?, ?, ?, ?, ?)
            LIMIT 1
            """,
            (wid, idx, digest, version, *_FINAL_STATUSES),
        ).fetchone()
        if finished is not None:
            conn.execute("COMMIT")
            return {"queued": False, "reason": "already_finished", "idempotency_key": idem}
        conn.execute(
            """
            INSERT INTO du_body_eval_pending(
                window_id, round_index, round_hash, round_timestamp, messages_json,
                prompt_version, status, attempts, batch_id, lease_until,
                next_attempt_at, queued_at, updated_at, last_error
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, '', 0, 0, ?, ?, '')
            ON CONFLICT(window_id, round_index) DO UPDATE SET
                round_hash = excluded.round_hash,
                round_timestamp = excluded.round_timestamp,
                messages_json = excluded.messages_json,
                prompt_version = excluded.prompt_version,
                status = 'pending', attempts = 0, batch_id = '', lease_until = 0,
                next_attempt_at = 0, queued_at = excluded.queued_at,
                updated_at = excluded.updated_at, last_error = ''
            WHERE du_body_eval_pending.round_hash != excluded.round_hash
               OR du_body_eval_pending.prompt_version != excluded.prompt_version
            """,
            (
                wid,
                idx,
                digest,
                str(round_timestamp or "").strip(),
                runtime_sqlite.json_dumps(canonical),
                version,
                ts,
                ts,
            ),
        )
        row = conn.execute(
            "SELECT status, attempts FROM du_body_eval_pending WHERE window_id = ? AND round_index = ?",
            (wid, idx),
        ).fetchone()
        conn.execute("COMMIT")
    return {
        "queued": row is not None,
        "status": str(row["status"] or "") if row is not None else "",
        "attempts": int(row["attempts"] or 0) if row is not None else 0,
        "round_hash": digest,
        "idempotency_key": idem,
    }


def claim_due_batch(window_id: str, *, now: float | None = None) -> dict | None:
    wid = str(window_id or "").strip()
    if not wid:
        return None
    ts = float(now if now is not None else time.time())
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            UPDATE du_body_eval_pending
            SET status = 'pending', attempts = MAX(0, attempts - 1),
                batch_id = '', lease_until = 0, updated_at = ?,
                last_error = 'processing lease expired; retrying same attempt'
            WHERE window_id = ? AND status = 'processing' AND lease_until <= ?
              AND attempts <= ?
            """,
            (ts, wid, ts, int(DU_BODY_EVAL_MAX_ATTEMPTS)),
        )
        rows = conn.execute(
            """
            SELECT * FROM du_body_eval_pending
            WHERE window_id = ? AND status = 'pending' AND attempts < ? AND next_attempt_at <= ?
            ORDER BY round_index ASC
            """,
            (wid, int(DU_BODY_EVAL_MAX_ATTEMPTS), ts),
        ).fetchall()
        if not rows:
            conn.execute("COMMIT")
            return None
        oldest = min(float(row["queued_at"] or ts) for row in rows)
        if len(rows) < int(DU_BODY_EVAL_BATCH_SIZE) and ts - oldest < int(DU_BODY_EVAL_GRACE_SECONDS):
            conn.execute("COMMIT")
            return None
        selected = rows[: int(DU_BODY_EVAL_BATCH_SIZE)]
        batch_id = "body_" + uuid.uuid4().hex
        indices = [int(row["round_index"] or 0) for row in selected]
        placeholders = ",".join("?" for _ in indices)
        conn.execute(
            f"""
            UPDATE du_body_eval_pending
            SET status = 'processing', attempts = attempts + 1, batch_id = ?,
                lease_until = ?, updated_at = ?, last_error = ''
            WHERE window_id = ? AND round_index IN ({placeholders})
            """,
            (batch_id, ts + int(DU_BODY_EVAL_LEASE_SECONDS), ts, wid, *indices),
        )
        claimed = conn.execute(
            f"""
            SELECT * FROM du_body_eval_pending
            WHERE window_id = ? AND batch_id = ? AND round_index IN ({placeholders})
            ORDER BY round_index ASC
            """,
            (wid, batch_id, *indices),
        ).fetchall()
        conn.execute("COMMIT")
    return {
        "batch_id": batch_id,
        "window_id": wid,
        "rows": [
            {
                **dict(row),
                "messages": runtime_sqlite.json_loads(row["messages_json"], []),
                "idempotency_key": idempotency_key(
                    wid,
                    int(row["round_index"] or 0),
                    str(row["round_hash"] or ""),
                    str(row["prompt_version"] or ""),
                ),
            }
            for row in claimed
        ],
    }


def complete_round(row: dict, *, batch_id: str, status: str, event: dict, now: float | None = None) -> bool:
    ts = float(now if now is not None else time.time())
    wid = str(row.get("window_id") or "").strip()
    idx = int(row.get("round_index") or 0)
    digest = str(row.get("round_hash") or "")
    version = str(row.get("prompt_version") or DU_BODY_EVAL_PROMPT_VERSION)
    event_id = f"{str(row.get('idempotency_key') or idempotency_key(wid, idx, digest, version))}:{status}"
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        exists = conn.execute(
            """
            SELECT 1 FROM du_body_eval_pending
            WHERE window_id = ? AND round_index = ? AND batch_id = ? AND status = 'processing'
            """,
            (wid, idx, str(batch_id or "")),
        ).fetchone()
        if exists is None:
            conn.execute("COMMIT")
            return False
        conn.execute(
            """
            INSERT OR REPLACE INTO du_body_eval_audit(
                event_id, window_id, round_index, round_hash, prompt_version,
                batch_id, status, event_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                wid,
                idx,
                digest,
                version,
                str(batch_id or ""),
                str(status or ""),
                runtime_sqlite.json_dumps(event if isinstance(event, dict) else {}),
                ts,
            ),
        )
        conn.execute(
            "DELETE FROM du_body_eval_pending WHERE window_id = ? AND round_index = ? AND batch_id = ?",
            (wid, idx, str(batch_id or "")),
        )
        _prune_audit(conn)
        conn.execute("COMMIT")
    return True


def fail_batch(batch_id: str, *, error: str, now: float | None = None) -> int:
    bid = str(batch_id or "").strip()
    if not bid:
        return 0
    ts = float(now if now is not None else time.time())
    error_text = str(error or "")[:500]
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT * FROM du_body_eval_pending WHERE batch_id = ? AND status = 'processing'",
            (bid,),
        ).fetchall()
        for row in rows:
            attempts = int(row["attempts"] or 0)
            failed = attempts >= int(DU_BODY_EVAL_MAX_ATTEMPTS)
            status = "failed" if failed else "retry_pending"
            next_attempt = 0.0 if failed else ts + min(600, 60 * (2 ** max(0, attempts - 1)))
            conn.execute(
                """
                UPDATE du_body_eval_pending
                SET status = ?, batch_id = '', lease_until = 0, next_attempt_at = ?,
                    updated_at = ?, last_error = ?,
                    messages_json = CASE WHEN ? = 1 THEN '[]' ELSE messages_json END
                WHERE window_id = ? AND round_index = ? AND batch_id = ?
                """,
                (
                    "failed" if failed else "pending",
                    next_attempt,
                    ts,
                    error_text,
                    1 if failed else 0,
                    str(row["window_id"] or ""),
                    int(row["round_index"] or 0),
                    bid,
                ),
            )
            digest = str(row["round_hash"] or "")
            version = str(row["prompt_version"] or DU_BODY_EVAL_PROMPT_VERSION)
            idem = idempotency_key(str(row["window_id"] or ""), int(row["round_index"] or 0), digest, version)
            conn.execute(
                """
                INSERT OR REPLACE INTO du_body_eval_audit(
                    event_id, window_id, round_index, round_hash, prompt_version,
                    batch_id, status, event_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{idem}:{status}:{attempts}",
                    str(row["window_id"] or ""),
                    int(row["round_index"] or 0),
                    digest,
                    version,
                    bid,
                    status,
                    runtime_sqlite.json_dumps({"error": error_text, "attempt": attempts}),
                    ts,
                ),
            )
        _prune_audit(conn)
        conn.execute("COMMIT")
    return len(rows)


def pending_stats(window_id: str = "") -> dict:
    wid = str(window_id or "").strip()
    where = "WHERE window_id = ?" if wid else ""
    params = (wid,) if wid else ()
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            f"SELECT status, COUNT(*) AS count FROM du_body_eval_pending {where} GROUP BY status",
            params,
        ).fetchall()
    return {str(row["status"] or ""): int(row["count"] or 0) for row in rows}


def active_window_ids() -> list[str]:
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT window_id
            FROM du_body_eval_pending
            WHERE (status = 'pending' AND attempts < ?)
               OR (status = 'processing' AND attempts <= ?)
            ORDER BY window_id ASC
            """,
            (int(DU_BODY_EVAL_MAX_ATTEMPTS), int(DU_BODY_EVAL_MAX_ATTEMPTS)),
        ).fetchall()
    return [str(row["window_id"] or "").strip() for row in rows if str(row["window_id"] or "").strip()]


def next_wakeup_delay(window_id: str, *, now: float | None = None) -> float | None:
    wid = str(window_id or "").strip()
    if not wid:
        return None
    ts = float(now if now is not None else time.time())
    with runtime_sqlite.connect() as conn:
        pending_rows = conn.execute(
            """
            SELECT queued_at, next_attempt_at
            FROM du_body_eval_pending
            WHERE window_id = ? AND status = 'pending' AND attempts < ?
            ORDER BY next_attempt_at ASC, round_index ASC
            """,
            (wid, int(DU_BODY_EVAL_MAX_ATTEMPTS)),
        ).fetchall()
        processing_rows = conn.execute(
            """
            SELECT lease_until
            FROM du_body_eval_pending
            WHERE window_id = ? AND status = 'processing' AND attempts <= ?
            ORDER BY lease_until ASC
            """,
            (wid, int(DU_BODY_EVAL_MAX_ATTEMPTS)),
        ).fetchall()
    due_candidates: list[float] = []
    if pending_rows:
        next_attempts = sorted(float(row["next_attempt_at"] or 0) for row in pending_rows)
        if len(pending_rows) >= int(DU_BODY_EVAL_BATCH_SIZE):
            due_candidates.append(next_attempts[int(DU_BODY_EVAL_BATCH_SIZE) - 1])
        else:
            oldest = min(float(row["queued_at"] or ts) for row in pending_rows)
            due_candidates.append(max(oldest + int(DU_BODY_EVAL_GRACE_SECONDS), next_attempts[0]))
    if processing_rows:
        due_candidates.append(min(float(row["lease_until"] or ts) for row in processing_rows))
    if not due_candidates:
        return None
    return max(0.0, min(due_candidates) - ts)
