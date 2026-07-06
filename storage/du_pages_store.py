from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
from typing import Any

from config import ARTIFACT_MAX_BYTES, DATA_DIR
from services.public_url import resolve_public_base_url
from utils.time_aware import now_beijing_iso


DB_PATH = DATA_DIR / "du_pages.sqlite3"

_LOCK = threading.RLock()
_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS du_pages (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            emoji TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            html TEXT NOT NULL,
            tags_json TEXT NOT NULL DEFAULT '[]',
            source TEXT NOT NULL DEFAULT '',
            source_window_id TEXT NOT NULL DEFAULT '',
            source_round_index INTEGER,
            created_by TEXT NOT NULL DEFAULT 'du',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            deleted_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_du_pages_deleted_updated
            ON du_pages(deleted_at, updated_at);
        CREATE INDEX IF NOT EXISTS idx_du_pages_created
            ON du_pages(created_at);
        """
    )


def _safe_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 120:
        return ""
    if any(ch not in _ID_CHARS for ch in text):
        return ""
    return text


def _new_page_id() -> str:
    return f"dp_{secrets.token_urlsafe(18)}"


def _clip_text(value: Any, limit: int) -> str:
    text = str(value or "").replace("\r", "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _normalize_tags(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else [value] if value else []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = _clip_text(item, 40)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out[:20]


def _json_loads(value: str, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed
    except Exception:
        return fallback


def _title_from_html(html: str) -> str:
    match = _TITLE_RE.search(html or "")
    if match:
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        if title:
            return _clip_text(title, 120)
    text = _TAG_RE.sub(" ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return _clip_text(text, 40) or "未命名页笺"


def _normalize_html(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("html 须为字符串")
    html = value.strip()
    if not html:
        raise ValueError("html 不能为空")
    if len(html.encode("utf-8")) > ARTIFACT_MAX_BYTES:
        raise ValueError(f"HTML 超过上限 {ARTIFACT_MAX_BYTES} 字节")
    return html


def page_url_for_id(page_id: str, base_override: str | None = None) -> str:
    base = (base_override or resolve_public_base_url()).strip().rstrip("/")
    path = f"/du-pages/v/{page_id}"
    return f"{base}{path}" if base else path


def _row_to_item(row: sqlite3.Row | None, *, include_html: bool = False) -> dict:
    if not row:
        return {}
    item = {
        "id": row["id"],
        "title": row["title"],
        "emoji": row["emoji"],
        "description": row["description"],
        "tags": _normalize_tags(_json_loads(row["tags_json"], [])),
        "source": row["source"],
        "source_window_id": row["source_window_id"],
        "source_round_index": row["source_round_index"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "deleted_at": row["deleted_at"],
        "url": page_url_for_id(row["id"]),
        "html_bytes": len(str(row["html"] or "").encode("utf-8")),
    }
    if include_html:
        item["html"] = row["html"]
    return item


def save_page(payload: dict) -> dict:
    src = payload if isinstance(payload, dict) else {}
    html = _normalize_html(src.get("html"))
    now = now_beijing_iso()
    page_id = _safe_id(src.get("id")) or _new_page_id()
    title = _clip_text(src.get("title"), 120) or _title_from_html(html)
    tags = _normalize_tags(src.get("tags"))
    item = {
        "id": page_id,
        "title": title,
        "emoji": _clip_text(src.get("emoji"), 8),
        "description": _clip_text(src.get("description"), 500),
        "html": html,
        "tags_json": json.dumps(tags, ensure_ascii=False),
        "source": _clip_text(src.get("source"), 80) or "du",
        "source_window_id": _clip_text(src.get("source_window_id") or src.get("sourceWindowId"), 120),
        "source_round_index": _coerce_optional_int(src.get("source_round_index") or src.get("sourceRoundIndex")),
        "created_by": _clip_text(src.get("created_by") or src.get("createdBy"), 40) or "du",
        "created_at": _clip_text(src.get("created_at") or src.get("createdAt"), 40) or now,
        "updated_at": now,
        "deleted_at": "",
    }
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO du_pages (
                id, title, emoji, description, html, tags_json, source,
                source_window_id, source_round_index, created_by,
                created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                emoji=excluded.emoji,
                description=excluded.description,
                html=excluded.html,
                tags_json=excluded.tags_json,
                source=excluded.source,
                source_window_id=excluded.source_window_id,
                source_round_index=excluded.source_round_index,
                created_by=excluded.created_by,
                updated_at=excluded.updated_at,
                deleted_at=''
            """,
            (
                item["id"],
                item["title"],
                item["emoji"],
                item["description"],
                item["html"],
                item["tags_json"],
                item["source"],
                item["source_window_id"],
                item["source_round_index"],
                item["created_by"],
                item["created_at"],
                item["updated_at"],
                item["deleted_at"],
            ),
        )
        row = conn.execute("SELECT * FROM du_pages WHERE id = ?", (page_id,)).fetchone()
    return _row_to_item(row, include_html=False)


def _coerce_optional_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(str(value).strip()))
    except Exception:
        return None


def get_page(page_id: str, *, include_html: bool = False, include_deleted: bool = False) -> dict | None:
    page_id = _safe_id(page_id)
    if not page_id:
        return None
    sql = "SELECT * FROM du_pages WHERE id = ?"
    params: list[Any] = [page_id]
    if not include_deleted:
        sql += " AND deleted_at = ''"
    with _LOCK, _connect() as conn:
        row = conn.execute(sql, params).fetchone()
    item = _row_to_item(row, include_html=include_html)
    return item or None


def list_pages(
    *,
    include_deleted: bool = False,
    query: str = "",
    tag: str = "",
    limit: int = 100,
) -> list[dict]:
    limit = max(1, min(500, int(limit or 100)))
    tag_text = str(tag or "").strip()
    where = []
    params: list[Any] = []
    if not include_deleted:
        where.append("deleted_at = ''")
    q = str(query or "").strip()
    if q:
        like = f"%{q}%"
        where.append("(title LIKE ? OR description LIKE ? OR html LIKE ?)")
        params.extend([like, like, like])
    sql = "SELECT * FROM du_pages"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC, created_at DESC LIMIT ?"
    params.append(500 if tag_text else limit)
    with _LOCK, _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    items = [_row_to_item(row, include_html=False) for row in rows]
    if tag_text:
        items = [item for item in items if tag_text in (item.get("tags") or [])]
    return items[:limit]


def update_page(page_id: str, patch: dict) -> dict | None:
    page_id = _safe_id(page_id)
    if not page_id:
        return None
    src = patch if isinstance(patch, dict) else {}
    allowed: dict[str, Any] = {}
    if "title" in src:
        allowed["title"] = _clip_text(src.get("title"), 120)
    if "emoji" in src:
        allowed["emoji"] = _clip_text(src.get("emoji"), 8)
    if "description" in src:
        allowed["description"] = _clip_text(src.get("description"), 500)
    if "tags" in src:
        allowed["tags_json"] = json.dumps(_normalize_tags(src.get("tags")), ensure_ascii=False)
    if "html" in src:
        allowed["html"] = _normalize_html(src.get("html"))
        if "title" not in allowed and not str(src.get("title") or "").strip():
            allowed.setdefault("title", _title_from_html(allowed["html"]))
    if "source" in src:
        allowed["source"] = _clip_text(src.get("source"), 80)
    if "source_window_id" in src or "sourceWindowId" in src:
        allowed["source_window_id"] = _clip_text(src.get("source_window_id") or src.get("sourceWindowId"), 120)
    if "source_round_index" in src or "sourceRoundIndex" in src:
        allowed["source_round_index"] = _coerce_optional_int(src.get("source_round_index") or src.get("sourceRoundIndex"))
    if not allowed:
        return get_page(page_id, include_html=False)
    allowed["updated_at"] = now_beijing_iso()
    assignments = ", ".join(f"{key}=?" for key in allowed)
    params = [*allowed.values(), page_id]
    with _LOCK, _connect() as conn:
        cur = conn.execute(f"UPDATE du_pages SET {assignments} WHERE id = ? AND deleted_at = ''", params)
        if cur.rowcount <= 0:
            return None
        row = conn.execute("SELECT * FROM du_pages WHERE id = ?", (page_id,)).fetchone()
    return _row_to_item(row, include_html=False)


def soft_delete_page(page_id: str) -> dict | None:
    page_id = _safe_id(page_id)
    if not page_id:
        return None
    now = now_beijing_iso()
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "UPDATE du_pages SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at = ''",
            (now, now, page_id),
        )
        if cur.rowcount <= 0:
            return None
        row = conn.execute("SELECT * FROM du_pages WHERE id = ?", (page_id,)).fetchone()
    return _row_to_item(row, include_html=False)


def restore_page(page_id: str) -> dict | None:
    page_id = _safe_id(page_id)
    if not page_id:
        return None
    now = now_beijing_iso()
    with _LOCK, _connect() as conn:
        cur = conn.execute(
            "UPDATE du_pages SET deleted_at = '', updated_at = ? WHERE id = ?",
            (now, page_id),
        )
        if cur.rowcount <= 0:
            return None
        row = conn.execute("SELECT * FROM du_pages WHERE id = ?", (page_id,)).fetchone()
    return _row_to_item(row, include_html=False)


def stats() -> dict:
    with _LOCK, _connect() as conn:
        visible = int(conn.execute("SELECT COUNT(*) FROM du_pages WHERE deleted_at = ''").fetchone()[0])
        deleted = int(conn.execute("SELECT COUNT(*) FROM du_pages WHERE deleted_at != ''").fetchone()[0])
        rows = conn.execute("SELECT tags_json FROM du_pages WHERE deleted_at = ''").fetchall()
    tags: dict[str, int] = {}
    for row in rows:
        for tag in _normalize_tags(_json_loads(row["tags_json"], [])):
            tags[tag] = tags.get(tag, 0) + 1
    return {
        "count": visible,
        "deleted_count": deleted,
        "tags": tags,
    }
