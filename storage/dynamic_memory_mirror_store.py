"""SQLite searchable mirror for dynamic memory current.json.

This module stores a rebuildable R2 -> SQLite copy. It never writes back to R2.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import DYNAMIC_MEMORY_MIRROR_DB
from services.dynamic_memory_keywords import ids_hash, memory_content_hash, normalize_term, snapshot_hash
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

_SCHEMA_LOCK = threading.Lock()
_WRITE_LOCK = threading.Lock()
_SCHEMA_READY = False
_FTS_AVAILABLE = False
_ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.:/+-]{1,}")
_CJK_CHUNK_RE = re.compile(r"[\u4e00-\u9fff]{2,18}")


def db_path() -> Path:
    return Path(DYNAMIC_MEMORY_MIRROR_DB)


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _json_loads(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(str(raw or ""))
    except Exception:
        return fallback


def _connect_raw() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_schema() -> None:
    global _SCHEMA_READY, _FTS_AVAILABLE
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with _connect_raw() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS mirror_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS dynamic_memory_items (
                    memory_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL DEFAULT '',
                    retrieval_text TEXT NOT NULL DEFAULT '',
                    tag TEXT NOT NULL DEFAULT '',
                    emotion_label TEXT NOT NULL DEFAULT '',
                    scene_type TEXT NOT NULL DEFAULT '',
                    target_type TEXT NOT NULL DEFAULT '',
                    importance REAL NOT NULL DEFAULT 0,
                    mention_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT '',
                    last_mentioned TEXT NOT NULL DEFAULT '',
                    content_hash TEXT NOT NULL DEFAULT '',
                    source_snapshot_hash TEXT NOT NULL DEFAULT '',
                    ids_hash TEXT NOT NULL DEFAULT '',
                    memory_count INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    deleted_at TEXT NOT NULL DEFAULT '',
                    synced_at TEXT NOT NULL DEFAULT '',
                    raw_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_dynamic_memory_items_active_tag_time
                    ON dynamic_memory_items(active, tag, last_mentioned);
                CREATE INDEX IF NOT EXISTS idx_dynamic_memory_items_hash
                    ON dynamic_memory_items(content_hash);
                CREATE INDEX IF NOT EXISTS idx_dynamic_memory_items_snapshot
                    ON dynamic_memory_items(source_snapshot_hash);

                CREATE TABLE IF NOT EXISTS dynamic_memory_terms (
                    memory_id TEXT NOT NULL,
                    term TEXT NOT NULL,
                    normalized_term TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'auto',
                    weight REAL NOT NULL DEFAULT 1,
                    confidence REAL NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (memory_id, normalized_term, source)
                );
                CREATE INDEX IF NOT EXISTS idx_dynamic_memory_terms_term
                    ON dynamic_memory_terms(normalized_term, weight);
                CREATE INDEX IF NOT EXISTS idx_dynamic_memory_terms_memory
                    ON dynamic_memory_terms(memory_id);

                CREATE TABLE IF NOT EXISTS memory_keyword_overrides (
                    id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    op TEXT NOT NULL DEFAULT 'add',
                    term TEXT NOT NULL,
                    normalized_term TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1,
                    reason TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_memory_keyword_overrides_memory
                    ON memory_keyword_overrides(memory_id, active);

                CREATE TABLE IF NOT EXISTS sync_runs (
                    run_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    source_snapshot_hash TEXT NOT NULL DEFAULT '',
                    ids_hash TEXT NOT NULL DEFAULT '',
                    memory_count INTEGER NOT NULL DEFAULT 0,
                    inserted_count INTEGER NOT NULL DEFAULT 0,
                    updated_count INTEGER NOT NULL DEFAULT 0,
                    unchanged_count INTEGER NOT NULL DEFAULT 0,
                    inactive_count INTEGER NOT NULL DEFAULT 0,
                    keyword_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'ok',
                    error TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_sync_runs_finished
                    ON sync_runs(finished_at);
                """
            )
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS dynamic_memory_fts
                    USING fts5(memory_id UNINDEXED, content, retrieval_text, keywords, tag UNINDEXED)
                    """
                )
                _FTS_AVAILABLE = True
            except sqlite3.OperationalError as e:
                _FTS_AVAILABLE = False
                logger.warning("dynamic_memory_mirror fts5 unavailable error=%s", e)
        _SCHEMA_READY = True


def connect() -> sqlite3.Connection:
    ensure_schema()
    return _connect_raw()


def _memory_id(memory: dict[str, Any]) -> str:
    return str((memory or {}).get("id") or "").strip()


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _existing_rows(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    rows = conn.execute(
        "SELECT memory_id, content_hash, raw_json, active FROM dynamic_memory_items"
    ).fetchall()
    return {
        str(row["memory_id"]): {
            "content_hash": str(row["content_hash"] or ""),
            "raw_json": str(row["raw_json"] or ""),
            "active": str(row["active"] or "0"),
        }
        for row in rows
    }


def _replace_terms(
    conn: sqlite3.Connection,
    memory_id: str,
    terms: list[dict[str, Any]],
    now: str,
) -> int:
    conn.execute("DELETE FROM dynamic_memory_terms WHERE memory_id = ?", (memory_id,))
    count = 0
    for term in terms or []:
        normalized = str(term.get("normalized_term") or "").strip()
        raw_term = str(term.get("term") or "").strip()
        if not normalized or not raw_term:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO dynamic_memory_terms
                (memory_id, term, normalized_term, source, weight, confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                raw_term,
                normalized,
                str(term.get("source") or "auto"),
                _as_float(term.get("weight"), 1.0),
                _as_float(term.get("confidence"), 1.0),
                now,
                now,
            ),
        )
        count += 1
    return count


def _replace_fts(
    conn: sqlite3.Connection,
    memory_id: str,
    memory: dict[str, Any],
    terms: list[dict[str, Any]],
) -> None:
    if not _FTS_AVAILABLE:
        return
    conn.execute("DELETE FROM dynamic_memory_fts WHERE memory_id = ?", (memory_id,))
    keywords = " ".join(str(term.get("term") or "") for term in terms or [])
    conn.execute(
        """
        INSERT INTO dynamic_memory_fts (memory_id, content, retrieval_text, keywords, tag)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            memory_id,
            str(memory.get("content") or ""),
            str(memory.get("retrieval_text") or ""),
            keywords,
            str(memory.get("tag") or ""),
        ),
    )


def _mark_missing_inactive(
    conn: sqlite3.Connection,
    active_ids: list[str],
    now: str,
) -> int:
    if active_ids:
        placeholders = ",".join("?" for _ in active_ids)
        rows = conn.execute(
            f"""
            SELECT memory_id
            FROM dynamic_memory_items
            WHERE active = 1 AND memory_id NOT IN ({placeholders})
            """,
            tuple(active_ids),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT memory_id FROM dynamic_memory_items WHERE active = 1"
        ).fetchall()
    missing = [str(row["memory_id"]) for row in rows]
    if not missing:
        return 0
    placeholders = ",".join("?" for _ in missing)
    conn.execute(
        f"""
        UPDATE dynamic_memory_items
        SET active = 0, deleted_at = ?, synced_at = ?
        WHERE memory_id IN ({placeholders})
        """,
        (now, now, *missing),
    )
    if _FTS_AVAILABLE:
        for memory_id in missing:
            conn.execute("DELETE FROM dynamic_memory_fts WHERE memory_id = ?", (memory_id,))
    return len(missing)


def _set_meta(conn: sqlite3.Connection, key: str, value: Any, now: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO mirror_meta (key, value, updated_at)
        VALUES (?, ?, ?)
        """,
        (key, str(value), now),
    )


def sync_memories(
    memories: list[dict[str, Any]],
    *,
    terms_by_id: dict[str, list[dict[str, Any]]] | None = None,
    source: str = "manual",
    dry_run: bool = False,
) -> dict[str, Any]:
    valid_memories = [m for m in (memories or []) if isinstance(m, dict) and _memory_id(m)]
    source_hash = snapshot_hash(valid_memories)
    current_ids_hash = ids_hash(valid_memories)
    active_ids = [_memory_id(m) for m in valid_memories]
    terms_by_id = terms_by_id or {}
    keyword_count = sum(len(terms_by_id.get(memory_id) or []) for memory_id in active_ids)
    if dry_run:
        return {
            "dry_run": True,
            "source": source,
            "memory_count": len(valid_memories),
            "source_snapshot_hash": source_hash,
            "ids_hash": current_ids_hash,
            "keyword_count": keyword_count,
            "db_path": str(db_path()),
        }

    now = now_beijing_iso()
    run_id = str(uuid4())
    inserted = 0
    updated = 0
    unchanged = 0
    inactive = 0
    status = "ok"
    error = ""

    with _WRITE_LOCK:
        with connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = _existing_rows(conn)
                keyword_count = 0
                for memory in valid_memories:
                    memory_id = _memory_id(memory)
                    raw_json = _json_dumps(memory)
                    content_hash = memory_content_hash(memory)
                    prev = existing.get(memory_id)
                    if not prev:
                        inserted += 1
                    elif prev.get("content_hash") != content_hash or prev.get("raw_json") != raw_json or prev.get("active") != "1":
                        updated += 1
                    else:
                        unchanged += 1

                    conn.execute(
                        """
                        INSERT OR REPLACE INTO dynamic_memory_items
                            (
                                memory_id, content, retrieval_text, tag,
                                emotion_label, scene_type, target_type,
                                importance, mention_count, created_at, last_mentioned,
                                content_hash, source_snapshot_hash, ids_hash, memory_count,
                                active, deleted_at, synced_at, raw_json
                            )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, '', ?, ?)
                        """,
                        (
                            memory_id,
                            str(memory.get("content") or ""),
                            str(memory.get("retrieval_text") or ""),
                            str(memory.get("tag") or ""),
                            str(memory.get("emotion_label") or ""),
                            str(memory.get("scene_type") or ""),
                            str(memory.get("target_type") or ""),
                            _as_float(memory.get("importance"), 0.0),
                            _as_int(memory.get("mention_count"), 0),
                            str(memory.get("created_at") or ""),
                            str(memory.get("last_mentioned") or ""),
                            content_hash,
                            source_hash,
                            current_ids_hash,
                            len(valid_memories),
                            now,
                            raw_json,
                        ),
                    )
                    terms = terms_by_id.get(memory_id) or []
                    keyword_count += _replace_terms(conn, memory_id, terms, now)
                    _replace_fts(conn, memory_id, memory, terms)

                inactive = _mark_missing_inactive(conn, active_ids, now)
                for key, value in (
                    ("source_snapshot_hash", source_hash),
                    ("ids_hash", current_ids_hash),
                    ("memory_count", len(valid_memories)),
                    ("last_sync_source", source),
                    ("last_synced_at", now),
                ):
                    _set_meta(conn, key, value, now)
                conn.execute(
                    """
                    INSERT INTO sync_runs
                        (
                            run_id, source, started_at, finished_at,
                            source_snapshot_hash, ids_hash, memory_count,
                            inserted_count, updated_count, unchanged_count,
                            inactive_count, keyword_count, status, error
                        )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        source,
                        now,
                        now,
                        source_hash,
                        current_ids_hash,
                        len(valid_memories),
                        inserted,
                        updated,
                        unchanged,
                        inactive,
                        keyword_count,
                        status,
                        error,
                    ),
                )
                conn.execute("COMMIT")
            except Exception as e:
                status = "error"
                error = str(e)
                conn.execute("ROLLBACK")
                raise

    return {
        "dry_run": False,
        "source": source,
        "run_id": run_id,
        "memory_count": len(valid_memories),
        "inserted_count": inserted,
        "updated_count": updated,
        "unchanged_count": unchanged,
        "inactive_count": inactive,
        "keyword_count": keyword_count,
        "source_snapshot_hash": source_hash,
        "ids_hash": current_ids_hash,
        "status": status,
        "error": error,
        "db_path": str(db_path()),
    }


def get_status() -> dict[str, Any]:
    try:
        with connect() as conn:
            meta = {
                str(row["key"]): str(row["value"] or "")
                for row in conn.execute("SELECT key, value FROM mirror_meta").fetchall()
            }
            active_count = int(
                conn.execute("SELECT COUNT(*) AS c FROM dynamic_memory_items WHERE active = 1").fetchone()["c"] or 0
            )
            inactive_count = int(
                conn.execute("SELECT COUNT(*) AS c FROM dynamic_memory_items WHERE active = 0").fetchone()["c"] or 0
            )
            term_count = int(
                conn.execute("SELECT COUNT(*) AS c FROM dynamic_memory_terms").fetchone()["c"] or 0
            )
            last_run = conn.execute(
                """
                SELECT *
                FROM sync_runs
                ORDER BY finished_at DESC
                LIMIT 1
                """
            ).fetchone()
            return {
                "ok": True,
                "db_path": str(db_path()),
                "active_count": active_count,
                "inactive_count": inactive_count,
                "term_count": term_count,
                "meta": meta,
                "last_run": dict(last_run) if last_run else None,
            }
    except Exception as e:
        return {"ok": False, "db_path": str(db_path()), "error": str(e)}


def list_items(limit: int = 50, *, active_only: bool = True) -> list[dict[str, Any]]:
    try:
        lim = max(1, min(500, int(limit or 50)))
    except Exception:
        lim = 50
    where = "WHERE active = 1" if active_only else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM dynamic_memory_items
            {where}
            ORDER BY last_mentioned DESC, created_at DESC
            LIMIT ?
            """,
            (lim,),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["raw_json"] = _json_loads(item.get("raw_json"), {})
            item["keywords"] = [
                dict(term)
                for term in conn.execute(
                    """
                    SELECT term, normalized_term, source, weight, confidence
                    FROM dynamic_memory_terms
                    WHERE memory_id = ?
                    ORDER BY weight DESC, normalized_term ASC
                    """,
                    (item["memory_id"],),
                ).fetchall()
            ]
            out.append(item)
        return out


def find_by_keyword(term: str, limit: int = 50) -> list[dict[str, Any]]:
    normalized = str(term or "").strip().lower()
    if not normalized:
        return []
    try:
        lim = max(1, min(200, int(limit or 50)))
    except Exception:
        lim = 50
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT i.*, t.term, t.normalized_term, t.weight, t.source
            FROM dynamic_memory_terms t
            JOIN dynamic_memory_items i ON i.memory_id = t.memory_id
            WHERE i.active = 1 AND t.normalized_term = ?
            ORDER BY t.weight DESC, i.last_mentioned DESC
            LIMIT ?
            """,
            (normalized, lim),
        ).fetchall()
        return [dict(row) for row in rows]


def _candidate_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "memory_id": str(row["memory_id"] or ""),
        "content": str(row["content"] or ""),
        "retrieval_text": str(row["retrieval_text"] or ""),
        "tag": str(row["tag"] or ""),
        "importance": _as_float(row["importance"], 0.0),
        "mention_count": _as_int(row["mention_count"], 0),
        "last_mentioned": str(row["last_mentioned"] or row["created_at"] or ""),
        "content_hash": str(row["content_hash"] or ""),
    }


def _query_terms(query: str, keywords: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        raw = str(value or "").strip()
        norm = normalize_term(raw)
        if not norm or norm in seen or len(norm) < 2:
            return
        seen.add(norm)
        out.append(raw)

    for keyword in keywords or []:
        add(str(keyword or ""))

    text = str(query or "")
    for token in _ASCII_TOKEN_RE.findall(text):
        add(token)
    for chunk in _CJK_CHUNK_RE.findall(text):
        add(chunk)
    return out[:16]


def shadow_candidates(
    query: str,
    *,
    keywords: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return SQLite-only candidate ids for recall shadow comparison."""
    try:
        lim = max(1, min(50, int(limit or 20)))
    except Exception:
        lim = 20
    terms = _query_terms(query, keywords)
    if not terms:
        return {"ok": True, "query_terms": [], "candidate_count": 0, "candidates": []}
    if not db_path().exists():
        return {
            "ok": False,
            "error": "mirror_db_missing",
            "query_terms": terms,
            "candidate_count": 0,
            "candidates": [],
        }

    by_id: dict[str, dict[str, Any]] = {}

    def remember(row: sqlite3.Row, score: float, reason: str, term: str) -> None:
        item = by_id.setdefault(
            str(row["memory_id"] or ""),
            {
                **_candidate_row(row),
                "score": 0.0,
                "reasons": [],
                "matched_terms": [],
            },
        )
        item["score"] = round(float(item.get("score") or 0.0) + float(score or 0.0), 4)
        if reason not in item["reasons"]:
            item["reasons"].append(reason)
        if term and term not in item["matched_terms"]:
            item["matched_terms"].append(term)

    with connect() as conn:
        for term in terms:
            norm = normalize_term(term)
            if not norm:
                continue
            rows = conn.execute(
                """
                SELECT i.*, t.weight AS term_weight, t.source AS term_source, t.term AS matched_term
                FROM dynamic_memory_terms t
                JOIN dynamic_memory_items i ON i.memory_id = t.memory_id
                WHERE i.active = 1 AND t.normalized_term = ?
                ORDER BY t.weight DESC, i.last_mentioned DESC
                LIMIT ?
                """,
                (norm, lim),
            ).fetchall()
            for row in rows:
                remember(row, float(row["term_weight"] or 1.0) * 2.0, "term", str(row["matched_term"] or term))

            like = f"%{str(term).strip()}%"
            rows = conn.execute(
                """
                SELECT *
                FROM dynamic_memory_items
                WHERE active = 1
                  AND (content LIKE ? OR retrieval_text LIKE ? OR tag LIKE ?)
                ORDER BY last_mentioned DESC
                LIMIT ?
                """,
                (like, like, like, lim),
            ).fetchall()
            for row in rows:
                remember(row, 1.0, "like", str(term))

    candidates = sorted(
        by_id.values(),
        key=lambda item: (
            -float(item.get("score") or 0.0),
            -float(item.get("importance") or 0.0),
            -float(item.get("mention_count") or 0.0),
            str(item.get("last_mentioned") or ""),
        ),
    )[:lim]
    return {
        "ok": True,
        "query_terms": terms,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def clear_all() -> int:
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for table in (
                "dynamic_memory_terms",
                "dynamic_memory_items",
                "memory_keyword_overrides",
                "sync_runs",
                "mirror_meta",
            ):
                conn.execute(f"DELETE FROM {table}")
            if _FTS_AVAILABLE:
                conn.execute("DELETE FROM dynamic_memory_fts")
            conn.execute("COMMIT")
            return 5
        except Exception:
            conn.execute("ROLLBACK")
            raise
