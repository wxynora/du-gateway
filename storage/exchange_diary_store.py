from __future__ import annotations

import hashlib
import json
import threading
from typing import Any
from uuid import uuid4

from botocore.exceptions import ClientError

from storage import r2_store, runtime_sqlite
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing, today_beijing


logger = get_logger(__name__)

SCHEMA_VERSION = 1
R2_PREFIX = "exchange_diary/v1"
R2_MANIFEST_KEY = f"{R2_PREFIX}/manifest.json"

_WRITE_LOCK = threading.Lock()


def _clip_text(value: Any, limit: int) -> str:
    text = str(value or "").replace("\r", "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value or "").strip()))
    except Exception:
        return default


def _normalize_author(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"du", "渡", "assistant"}:
        return "du"
    if raw in {"xy", "xinyue", "辛玥", "小玥", "user", "me", "我"}:
        return "xy"
    if raw == "system":
        return "system"
    return "xy"


def _normalize_diary_date(value: Any, fallback_iso: str = "") -> str:
    raw = str(value or "").strip()
    if len(raw) >= 10 and raw[4:5] == "-" and raw[7:8] == "-":
        return raw[:10]
    dt = parse_iso_to_beijing(raw) if raw else None
    if dt is not None:
        return dt.strftime("%Y-%m-%d")
    if fallback_iso:
        dt = parse_iso_to_beijing(fallback_iso)
        if dt is not None:
            return dt.strftime("%Y-%m-%d")
    return today_beijing()


def _entry_key_for(entry_id: str, diary_date: str) -> str:
    y, m = (diary_date or today_beijing()).split("-")[:2]
    return f"{R2_PREFIX}/entries/{y}/{m}/{entry_id}.json"


def _month_key(month: str) -> str:
    return f"{R2_PREFIX}/months/{month}.json"


def _new_entry_id(diary_date: str) -> str:
    compact = str(diary_date or today_beijing()).replace("-", "")
    return f"ed_{compact}_{uuid4().hex[:8]}"


def _stable_entry_id(diary_date: str, namespace: str, value: Any) -> str:
    compact = str(diary_date or today_beijing()).replace("-", "")
    raw = str(value or "").strip()
    digest = hashlib.sha1(f"{namespace}:{raw}".encode("utf-8")).hexdigest()[:12]
    return f"ed_{compact}_{digest}"


def _new_comment_id() -> str:
    compact = today_beijing().replace("-", "")
    return f"edc_{compact}_{uuid4().hex[:8]}"


def _stable_comment_id(value: Any) -> str:
    compact = today_beijing().replace("-", "")
    raw = str(value or "").strip()
    digest = hashlib.sha1(f"comment:{raw}".encode("utf-8")).hexdigest()[:12]
    return f"edc_{compact}_{digest}"


def _normalize_comment(raw: Any) -> dict:
    src = raw if isinstance(raw, dict) else {}
    now = now_beijing_iso()
    created = str(src.get("created_at") or src.get("createdAt") or now).strip() or now
    updated = str(src.get("updated_at") or src.get("updatedAt") or created).strip() or created
    client_request_id = _clip_text(src.get("client_request_id") or src.get("clientRequestId"), 160)
    comment_id = str(src.get("id") or "").strip() or (
        _stable_comment_id(client_request_id) if client_request_id else _new_comment_id()
    )
    return {
        "id": comment_id,
        "author": _normalize_author(src.get("author")),
        "content": _clip_text(src.get("content"), 4000),
        "emoji": _clip_text(src.get("emoji") or src.get("mood"), 8),
        "client_request_id": client_request_id,
        "reply_to_comment_id": _clip_text(
            src.get("reply_to_comment_id")
            or src.get("replyToCommentId")
            or src.get("parent_comment_id")
            or src.get("parentCommentId"),
            160,
        ),
        "created_at": created,
        "updated_at": updated,
        "deleted_at": str(src.get("deleted_at") or src.get("deletedAt") or "").strip(),
    }


def _normalize_comments(value: Any) -> list[dict]:
    raw = value if isinstance(value, list) else []
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        comment = _normalize_comment(item)
        if not comment.get("content"):
            continue
        cid = str(comment.get("id") or "")
        if cid in seen:
            continue
        seen.add(cid)
        out.append(comment)
    return out[:500]


def normalize_entry(raw: dict) -> dict:
    src = raw if isinstance(raw, dict) else {}
    now = now_beijing_iso()
    created = str(src.get("created_at") or src.get("createdAt") or now).strip() or now
    updated = str(src.get("updated_at") or src.get("updatedAt") or created).strip() or created
    diary_date = _normalize_diary_date(src.get("diary_date") or src.get("diaryDate"), fallback_iso=created)
    client_request_id = _clip_text(src.get("client_request_id") or src.get("clientRequestId"), 160)
    source_notion_page_id = _clip_text(src.get("source_notion_page_id") or src.get("sourceNotionPageId"), 160)
    explicit_id = str(src.get("id") or "").strip()
    if explicit_id:
        entry_id = explicit_id
    elif client_request_id:
        entry_id = _stable_entry_id(diary_date, "client_request", client_request_id)
    elif source_notion_page_id:
        entry_id = _stable_entry_id(diary_date, "notion_page", source_notion_page_id)
    else:
        entry_id = _new_entry_id(diary_date)
    mood = _clip_text(src.get("mood") or src.get("emoji"), 8) or "✦"
    comments = _normalize_comments(src.get("comments"))
    visible_comments = [c for c in comments if not c.get("deleted_at")]
    latest_comment_at = ""
    for comment in visible_comments:
        latest_comment_at = max(latest_comment_at, str(comment.get("updated_at") or comment.get("created_at") or ""))
    content = _clip_text(src.get("content"), 30000)
    title = _clip_text(src.get("title"), 120) or "没有标题的小纸条"
    entry = {
        "schema_version": SCHEMA_VERSION,
        "id": entry_id,
        "entry_key": str(src.get("entry_key") or src.get("entryKey") or _entry_key_for(entry_id, diary_date)).strip(),
        "diary_date": diary_date,
        "title": title,
        "content": content,
        "excerpt": _clip_text(src.get("excerpt") or content, 160),
        "mood": mood,
        "emoji": mood,
        "author": _normalize_author(src.get("author")),
        "comments": comments,
        "comment_count": len(visible_comments),
        "latest_comment_at": latest_comment_at,
        "source": _clip_text(src.get("source"), 40) or "app",
        "source_window_id": _clip_text(src.get("source_window_id") or src.get("sourceWindowId"), 120),
        "client_request_id": client_request_id,
        "created_by_device_id": _clip_text(src.get("created_by_device_id") or src.get("createdByDeviceId"), 160),
        "source_notion_page_id": source_notion_page_id,
        "created_at": created,
        "updated_at": updated,
        "deleted_at": str(src.get("deleted_at") or src.get("deletedAt") or "").strip(),
        "imported_at": str(src.get("imported_at") or src.get("importedAt") or "").strip(),
        "raw_notion": src.get("raw_notion") if "raw_notion" in src else src.get("rawNotion"),
        "r2_synced_at": str(src.get("r2_synced_at") or src.get("r2SyncedAt") or "").strip(),
    }
    return entry


def _compact_entry(entry: dict) -> dict:
    src = normalize_entry(entry)
    return {
        "id": src["id"],
        "entry_key": src["entry_key"],
        "diary_date": src["diary_date"],
        "title": src["title"],
        "excerpt": src["excerpt"],
        "mood": src["mood"],
        "emoji": src["emoji"],
        "author": src["author"],
        "comment_count": src["comment_count"],
        "latest_comment_at": src["latest_comment_at"],
        "created_at": src["created_at"],
        "updated_at": src["updated_at"],
        "deleted_at": src["deleted_at"],
    }


def _connect():
    return runtime_sqlite.connect()


def _row_to_entry(row: Any) -> dict:
    if not row:
        return {}
    data = runtime_sqlite.json_loads(row["entry_json"], {})
    if not isinstance(data, dict):
        data = {}
    merged = {
        **data,
        "id": row["id"],
        "entry_key": row["entry_key"],
        "diary_date": row["diary_date"],
        "author": row["author"],
        "title": row["title"],
        "excerpt": row["excerpt"],
        "content": row["content"],
        "mood": row["mood"],
        "comment_count": row["comment_count"],
        "latest_comment_at": row["latest_comment_at"],
        "source": row["source"],
        "client_request_id": row["client_request_id"],
        "created_by_device_id": row["created_by_device_id"],
        "source_window_id": row["source_window_id"],
        "source_notion_page_id": row["source_notion_page_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "deleted_at": row["deleted_at"],
        "r2_synced_at": row["r2_synced_at"],
    }
    return normalize_entry(merged)


def _upsert_sqlite(entry: dict) -> None:
    item = normalize_entry(entry)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO exchange_diary_entries (
                id, entry_key, diary_date, author, title, excerpt, content, mood,
                comment_count, latest_comment_at, source, client_request_id,
                created_by_device_id, source_window_id, source_notion_page_id,
                created_at, updated_at, deleted_at, entry_json, r2_synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                entry_key=excluded.entry_key,
                diary_date=excluded.diary_date,
                author=excluded.author,
                title=excluded.title,
                excerpt=excluded.excerpt,
                content=excluded.content,
                mood=excluded.mood,
                comment_count=excluded.comment_count,
                latest_comment_at=excluded.latest_comment_at,
                source=excluded.source,
                client_request_id=excluded.client_request_id,
                created_by_device_id=excluded.created_by_device_id,
                source_window_id=excluded.source_window_id,
                source_notion_page_id=excluded.source_notion_page_id,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                deleted_at=excluded.deleted_at,
                entry_json=excluded.entry_json,
                r2_synced_at=excluded.r2_synced_at
            """,
            (
                item["id"],
                item["entry_key"],
                item["diary_date"],
                item["author"],
                item["title"],
                item["excerpt"],
                item["content"],
                item["mood"],
                item["comment_count"],
                item["latest_comment_at"],
                item["source"],
                item["client_request_id"],
                item["created_by_device_id"],
                item["source_window_id"],
                item["source_notion_page_id"],
                item["created_at"],
                item["updated_at"],
                item["deleted_at"],
                runtime_sqlite.json_dumps(item),
                item["r2_synced_at"],
            ),
        )


def _read_r2_json(key: str) -> Any:
    client = r2_store._s3_client()
    if not client:
        return None
    return r2_store._read_json(client, key)


def _write_r2_json(key: str, data: Any) -> bool:
    client = r2_store._s3_client()
    if not client:
        logger.warning("exchange_diary R2 client unavailable key=%s", key)
        return False
    try:
        r2_store._write_json(client, key, data)
        return True
    except Exception as e:
        logger.warning("exchange_diary R2 write failed key=%s error=%s", key, e)
        return False


def _read_r2_entry(entry_key: str) -> dict | None:
    client = r2_store._s3_client()
    if not client or not entry_key:
        return None
    try:
        resp = client.get_object(Bucket=r2_store.R2_BUCKET_NAME, Key=entry_key)
        data = json.loads(resp["Body"].read().decode("utf-8"))
        return normalize_entry(data) if isinstance(data, dict) else None
    except ClientError as e:
        code = (e.response or {}).get("Error", {}).get("Code", "")
        if code != "NoSuchKey":
            logger.warning("exchange_diary R2 entry read failed key=%s error=%s", entry_key, e)
        return None
    except Exception as e:
        logger.warning("exchange_diary R2 entry read failed key=%s error=%s", entry_key, e)
        return None


def _sync_month_index(entry: dict) -> bool:
    item = normalize_entry(entry)
    month = item["diary_date"][:7]
    key = _month_key(month)
    raw = _read_r2_json(key)
    payload = raw if isinstance(raw, dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    compact = _compact_entry(item)
    kept = [it for it in items if isinstance(it, dict) and str(it.get("id") or "") != item["id"]]
    if not item.get("deleted_at"):
        kept.append(compact)
    kept.sort(key=lambda it: (str(it.get("diary_date") or ""), str(it.get("created_at") or "")), reverse=True)
    now = now_beijing_iso()
    return _write_r2_json(
        key,
        {
            "schema_version": SCHEMA_VERSION,
            "month": month,
            "items": kept,
            "count": len(kept),
            "updated_at": now,
        },
    )


def _sync_manifest(entry: dict) -> bool:
    item = normalize_entry(entry)
    raw = _read_r2_json(R2_MANIFEST_KEY)
    payload = raw if isinstance(raw, dict) else {}
    months = payload.get("months") if isinstance(payload.get("months"), list) else []
    month = item["diary_date"][:7]
    if month and month not in months:
        months.append(month)
    months = sorted([str(m) for m in months if str(m or "").strip()], reverse=True)
    latest = payload.get("latest_entries") if isinstance(payload.get("latest_entries"), list) else []
    latest = [it for it in latest if isinstance(it, dict) and str(it.get("id") or "") != item["id"]]
    if not item.get("deleted_at"):
        latest.append(_compact_entry(item))
    latest.sort(key=lambda it: (str(it.get("diary_date") or ""), str(it.get("created_at") or "")), reverse=True)
    latest = latest[:50]
    return _write_r2_json(
        R2_MANIFEST_KEY,
        {
            "schema_version": SCHEMA_VERSION,
            "months": months,
            "latest_entries": latest,
            "latest_count": len(latest),
            "updated_at": now_beijing_iso(),
        },
    )


def _sync_r2(entry: dict) -> bool:
    item = normalize_entry(entry)
    ok_entry = _write_r2_json(item["entry_key"], item)
    ok_month = _sync_month_index(item) if ok_entry else False
    ok_manifest = _sync_manifest(item) if ok_entry else False
    return bool(ok_entry and ok_month and ok_manifest)


def _find_by_client_request_id(client_request_id: str) -> dict | None:
    cid = str(client_request_id or "").strip()
    if not cid:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM exchange_diary_entries WHERE client_request_id = ? LIMIT 1",
            (cid,),
        ).fetchone()
    return _row_to_entry(row) if row else None


def _find_by_source_notion_page_id(source_notion_page_id: str) -> dict | None:
    page_id = str(source_notion_page_id or "").strip()
    if not page_id:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM exchange_diary_entries WHERE source_notion_page_id = ? LIMIT 1",
            (page_id,),
        ).fetchone()
    return _row_to_entry(row) if row else None


def create_entry(data: dict) -> dict | None:
    src = data if isinstance(data, dict) else {}
    now = now_beijing_iso()
    item = normalize_entry(
        {
            **src,
            "created_at": src.get("created_at") or src.get("createdAt") or now,
            "updated_at": now,
        }
    )
    with _WRITE_LOCK:
        existing = _find_by_client_request_id(src.get("client_request_id") or src.get("clientRequestId"))
        if existing:
            return existing
        existing = _find_by_source_notion_page_id(src.get("source_notion_page_id") or src.get("sourceNotionPageId"))
        if existing:
            return existing
        synced = _sync_r2(item)
        if not synced:
            return None
        item["r2_synced_at"] = now_beijing_iso()
        _upsert_sqlite(item)
    return item


def get_entry(entry_id: str, include_deleted: bool = False) -> dict | None:
    target = str(entry_id or "").strip()
    if not target:
        return None
    with _connect() as conn:
        row = conn.execute("SELECT * FROM exchange_diary_entries WHERE id = ? LIMIT 1", (target,)).fetchone()
    item = _row_to_entry(row) if row else None
    if not item:
        return None
    if item.get("deleted_at") and not include_deleted:
        return None
    return item


def update_entry(entry_id: str, patch: dict, base_updated_at: str = "") -> tuple[dict | None, str]:
    target = str(entry_id or "").strip()
    if not target:
        return None, "missing_id"
    src = patch if isinstance(patch, dict) else {}
    allowed = {"title", "content", "mood", "emoji", "author"}
    with _WRITE_LOCK:
        current = get_entry(target, include_deleted=True)
        if not current:
            return None, "not_found"
        base = str(base_updated_at or "").strip()
        if base and base != str(current.get("updated_at") or ""):
            return current, "conflict"
        merged = {**current}
        for key in allowed:
            if key in src:
                if key == "emoji":
                    merged["mood"] = src.get(key)
                else:
                    merged[key] = src.get(key)
        merged["updated_at"] = now_beijing_iso()
        item = normalize_entry(merged)
        synced = _sync_r2(item)
        if not synced:
            return None, "sync_failed"
        item["r2_synced_at"] = now_beijing_iso()
        _upsert_sqlite(item)
    return item, "ok"


def soft_delete_entry(entry_id: str) -> dict | None:
    with _WRITE_LOCK:
        current = get_entry(entry_id, include_deleted=True)
        if not current:
            return None
        item = normalize_entry({**current, "deleted_at": now_beijing_iso(), "updated_at": now_beijing_iso()})
        synced = _sync_r2(item)
        if not synced:
            return None
        item["r2_synced_at"] = now_beijing_iso()
        _upsert_sqlite(item)
    return item


def add_comment(entry_id: str, data: dict) -> dict | None:
    src = data if isinstance(data, dict) else {}
    comment = _normalize_comment({**src, "created_at": src.get("created_at") or now_beijing_iso(), "updated_at": now_beijing_iso()})
    if not comment.get("content"):
        return None
    with _WRITE_LOCK:
        current = get_entry(entry_id, include_deleted=False)
        if not current:
            return None
        comments = [c for c in current.get("comments") or [] if isinstance(c, dict)]
        reply_to = str(comment.get("reply_to_comment_id") or "").strip()
        if reply_to:
            active_comment_ids = {
                str(c.get("id") or "").strip()
                for c in comments
                if str(c.get("id") or "").strip() and not str(c.get("deleted_at") or "").strip()
            }
            if reply_to not in active_comment_ids:
                return None
        cid = str(comment.get("client_request_id") or "").strip()
        if cid:
            for existing in comments:
                if str(existing.get("client_request_id") or "").strip() == cid:
                    return current
        comments.append(comment)
        item = normalize_entry({**current, "comments": comments, "updated_at": now_beijing_iso()})
        synced = _sync_r2(item)
        if not synced:
            return None
        item["r2_synced_at"] = now_beijing_iso()
        _upsert_sqlite(item)
    return item


def _query_entries(
    *,
    limit: int = 30,
    offset: int = 0,
    month: str = "",
    author: str = "",
    include_deleted: bool = False,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if not include_deleted:
        clauses.append("deleted_at = ''")
    m = str(month or "").strip()[:7]
    if m:
        clauses.append("substr(diary_date, 1, 7) = ?")
        params.append(m)
    a = _normalize_author(author) if str(author or "").strip() else ""
    if a:
        clauses.append("author = ?")
        params.append(a)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    n = max(1, min(200, _safe_int(limit, 30)))
    off = max(0, _safe_int(offset, 0))
    sql = f"""
        SELECT * FROM exchange_diary_entries
        {where}
        ORDER BY diary_date DESC, created_at DESC, id DESC
        LIMIT ? OFFSET ?
    """
    with _connect() as conn:
        rows = conn.execute(sql, (*params, n, off)).fetchall()
    return [_row_to_entry(row) for row in rows if row]


def _bootstrap_from_r2(month: str = "", *, max_months: int | None = None) -> int:
    target_months: list[str] = []
    m = str(month or "").strip()[:7]
    if m:
        target_months = [m]
    else:
        manifest = _read_r2_json(R2_MANIFEST_KEY)
        months = manifest.get("months") if isinstance(manifest, dict) and isinstance(manifest.get("months"), list) else []
        target_months = [str(x or "").strip()[:7] for x in months if str(x or "").strip()]
        if max_months is not None:
            target_months = target_months[: max(0, int(max_months))]
    count = 0
    for item_month in target_months:
        payload = _read_r2_json(_month_key(item_month))
        items = payload.get("items") if isinstance(payload, dict) and isinstance(payload.get("items"), list) else []
        for compact in items:
            if not isinstance(compact, dict):
                continue
            entry = _read_r2_entry(str(compact.get("entry_key") or ""))
            if not entry:
                entry = normalize_entry(compact)
            if entry:
                _upsert_sqlite({**entry, "r2_synced_at": entry.get("r2_synced_at") or now_beijing_iso()})
                count += 1
    return count


def list_entries(
    *,
    limit: int = 30,
    cursor: str = "",
    month: str = "",
    author: str = "",
    include_deleted: bool = False,
    compact: bool = True,
) -> dict:
    n = max(1, min(200, _safe_int(limit, 30)))
    offset = max(0, _safe_int(cursor, 0))
    items = _query_entries(limit=n + 1, offset=offset, month=month, author=author, include_deleted=include_deleted)
    if not items and offset == 0:
        _bootstrap_from_r2(month, max_months=6 if not str(month or "").strip() else None)
        items = _query_entries(limit=n + 1, offset=offset, month=month, author=author, include_deleted=include_deleted)
    has_more = len(items) > n
    visible = items[:n]
    out_items = [_compact_entry(item) for item in visible] if compact else visible
    return {
        "items": out_items,
        "next_cursor": str(offset + n) if has_more else "",
        "count": len(out_items),
    }


def rebuild_sqlite_from_r2(month: str = "") -> dict:
    count = _bootstrap_from_r2(month)
    return {"ok": True, "count": count, "month": str(month or "").strip()[:7]}
