"""R2 storage helpers for the Stay with Du fixed-memory panel."""
import threading
from typing import Any, Optional
from uuid import uuid4

from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing, today_beijing

R2_KEY_STAY_WITH_DU = "global/stay_with_du.json"

_stay_with_du_write_lock = threading.Lock()

logger = get_logger(__name__)


def _r2_store():
    from storage import r2_store

    return r2_store


def _s3_client():
    return _r2_store()._s3_client()


def _read_json(client, key: str):
    return _r2_store()._read_json(client, key)


def _write_json(client, key: str, data: Any):
    return _r2_store()._write_json(client, key, data)


def _empty_stay_with_du_data() -> dict:
    return {
        "timeline": [],
        "moviesTodo": [],
        "moviesDone": [],
        "booksTodo": [],
        "booksDone": [],
    }


def _normalize_stay_text(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _normalize_stay_timeline(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _normalize_stay_text(item.get("title"), 120)
        if not title:
            continue
        out.append(
            {
                "id": _normalize_stay_text(item.get("id"), 80) or str(uuid4()),
                "date": _normalize_stay_text(item.get("date"), 32),
                "title": title,
                "desc": _normalize_stay_text(item.get("desc"), 600),
            }
        )
    out.sort(key=lambda x: str(x.get("date") or ""), reverse=True)
    return out[:200]


def _normalize_stay_media(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _normalize_stay_text(item.get("title"), 160)
        if not title:
            continue
        row = {
            "id": _normalize_stay_text(item.get("id"), 80) or str(uuid4()),
            "title": title,
            "note": _normalize_stay_text(item.get("note"), 600),
        }
        date = _normalize_stay_text(item.get("date"), 32)
        if date:
            row["date"] = date
        for key in ("work_key", "watch_session_id", "watched_at"):
            value = str(item.get(key) or "").strip()
            if value:
                row[key] = value
        ticket = item.get("ticket")
        if isinstance(ticket, dict):
            normalized_ticket = {
                key: str(ticket.get(key) or "").strip()
                for key in (
                    "ticket_id",
                    "viewing_id",
                    "created_at",
                    "completed_at",
                    "part_title",
                )
                if str(ticket.get(key) or "").strip()
            }
            for key in ("duration_ms", "played_duration_ms", "part_count"):
                try:
                    normalized_ticket[key] = max(0, int(ticket.get(key) or 0))
                except (TypeError, ValueError):
                    continue
            if normalized_ticket.get("ticket_id"):
                row["ticket"] = normalized_ticket
        out.append(row)
    return out[:300]


def normalize_stay_with_du_data(data: Any) -> dict:
    """规整 Stay with Du 数据结构，供 API、注入和 R2 写入共用。"""
    if not isinstance(data, dict):
        return _empty_stay_with_du_data()
    return {
        "timeline": _normalize_stay_timeline(data.get("timeline")),
        "moviesTodo": _normalize_stay_media(data.get("moviesTodo")),
        "moviesDone": _normalize_stay_media(data.get("moviesDone")),
        "booksTodo": _normalize_stay_media(data.get("booksTodo")),
        "booksDone": _normalize_stay_media(data.get("booksDone")),
    }


def get_stay_with_du_data() -> dict:
    """读取 Stay with Du 数据。"""
    client = _s3_client()
    if not client:
        return _empty_stay_with_du_data()
    data = _read_json(client, R2_KEY_STAY_WITH_DU)
    if not isinstance(data, dict):
        return _empty_stay_with_du_data()
    raw = data.get("data") if isinstance(data.get("data"), dict) else data
    return normalize_stay_with_du_data(raw)


def save_stay_with_du_data(data: dict) -> bool:
    """覆盖保存 Stay with Du 数据。"""
    client = _s3_client()
    if not client:
        return False
    payload = {
        "data": normalize_stay_with_du_data(data),
        "updated_at": now_beijing_iso(),
    }
    with _stay_with_du_write_lock:
        try:
            _write_json(client, R2_KEY_STAY_WITH_DU, payload)
            return True
        except Exception as e:
            logger.error("save_stay_with_du_data 失败 error=%s", e, exc_info=True)
            return False


def _stay_with_du_target_for_kind(kind: str) -> Optional[str]:
    raw_kind = (kind or "").strip().lower().replace("-", "_")
    target_map = {
        "timeline": "timeline",
        "node": "timeline",
        "important_node": "timeline",
        "movie_want": "moviesTodo",
        "movie_todo": "moviesTodo",
        "want_movie": "moviesTodo",
        "movie_done": "moviesDone",
        "watched_movie": "moviesDone",
        "book_want": "booksTodo",
        "book_todo": "booksTodo",
        "want_book": "booksTodo",
        "book_done": "booksDone",
        "read_book": "booksDone",
    }
    return target_map.get(raw_kind)


def add_stay_with_du_entry(kind: str, title: str, note: str = "", date: str = "") -> Optional[dict]:
    """向 Stay with Du 追加一条记录。kind: timeline/movie_want/movie_done/book_want/book_done。"""
    target = _stay_with_du_target_for_kind(kind)
    clean_title = _normalize_stay_text(title, 160)
    if not target or not clean_title:
        return None
    clean_note = _normalize_stay_text(note, 600)
    clean_date = _normalize_stay_text(date, 32)
    if target == "timeline" and not clean_date:
        clean_date = today_beijing()
    if target in {"moviesDone", "booksDone"} and not clean_date:
        clean_date = today_beijing()

    data = get_stay_with_du_data()
    item_id = str(uuid4())
    if target == "timeline":
        entry = {
            "id": item_id,
            "date": clean_date,
            "title": clean_title,
            "desc": clean_note,
        }
    else:
        entry = {
            "id": item_id,
            "title": clean_title,
            "note": clean_note,
        }
        if clean_date:
            entry["date"] = clean_date
    items = data.get(target)
    if not isinstance(items, list):
        items = []
    data[target] = [entry] + items
    ok = save_stay_with_du_data(data)
    return entry if ok else None


def delete_stay_with_du_entry(kind: str, entry_id: str = "", title: str = "", date: str = "") -> Optional[dict]:
    """删除 Stay with Du 一条记录。优先按 id；没有 id 时按 title 精确匹配，可用 date 缩小范围。"""
    target = _stay_with_du_target_for_kind(kind)
    if not target:
        return None
    clean_id = _normalize_stay_text(entry_id, 80)
    clean_title = _normalize_stay_text(title, 160)
    clean_date = _normalize_stay_text(date, 32)
    if not clean_id and not clean_title:
        return None

    data = get_stay_with_du_data()
    items = data.get(target)
    if not isinstance(items, list) or not items:
        return None

    delete_index = -1
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if clean_id:
            if str(item.get("id") or "").strip() == clean_id:
                delete_index = idx
                break
            continue
        item_title = str(item.get("title") or "").strip()
        item_date = str(item.get("date") or "").strip()
        if item_title == clean_title and (not clean_date or item_date == clean_date):
            delete_index = idx
            break
    if delete_index < 0:
        return None

    deleted = dict(items[delete_index])
    data[target] = items[:delete_index] + items[delete_index + 1:]
    ok = save_stay_with_du_data(data)
    return deleted if ok else None


def archive_watch_ticket(ticket: dict) -> Optional[dict]:
    """把已确认标题的观影票根幂等归档到 moviesDone。"""
    if not isinstance(ticket, dict):
        return None
    title = _normalize_stay_text(ticket.get("title"), 160)
    ticket_id = str(ticket.get("ticket_id") or "").strip()
    if not title or not ticket_id:
        return None
    work_key = str(ticket.get("work_key") or "").strip()
    watched_at = str(ticket.get("completed_at") or ticket.get("created_at") or "").strip()
    watched_date = parse_iso_to_beijing(watched_at)
    date = watched_date.strftime("%Y-%m-%d") if watched_date else today_beijing()
    normalized_title = title.casefold()

    def same_work(item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        item_ticket = item.get("ticket")
        item_ticket_id = (
            str(item_ticket.get("ticket_id") or "").strip()
            if isinstance(item_ticket, dict)
            else ""
        )
        if item_ticket_id and item_ticket_id == ticket_id:
            return True
        item_work_key = str(item.get("work_key") or "").strip()
        if work_key and item_work_key:
            return item_work_key == work_key
        return str(item.get("title") or "").strip().casefold() == normalized_title

    completed_parts = ticket.get("completed_parts")
    part_titles = [
        str(item.get("part_title") or "").strip()
        for item in completed_parts
        if isinstance(item, dict) and str(item.get("part_title") or "").strip()
    ] if isinstance(completed_parts, list) else []
    archived_ticket = {
        "ticket_id": ticket_id,
        "viewing_id": str(ticket.get("viewing_id") or "").strip(),
        "created_at": str(ticket.get("created_at") or "").strip(),
        "completed_at": watched_at,
        "duration_ms": max(0, int(ticket.get("played_duration_ms") or 0)),
        "part_count": max(0, int(ticket.get("part_count") or 0)),
        "part_title": " / ".join(part_titles),
    }

    client = _s3_client()
    if not client:
        return None
    with _stay_with_du_write_lock:
        try:
            stored = _read_json(client, R2_KEY_STAY_WITH_DU)
            raw = (
                stored.get("data")
                if isinstance(stored, dict) and isinstance(stored.get("data"), dict)
                else stored
            )
            data = normalize_stay_with_du_data(raw)
            todo = data.get("moviesTodo") if isinstance(data.get("moviesTodo"), list) else []
            done = data.get("moviesDone") if isinstance(data.get("moviesDone"), list) else []
            existing_done = next((dict(item) for item in done if same_work(item)), None)
            existing_todo = next((dict(item) for item in todo if same_work(item)), None)
            existing = existing_done or existing_todo or {}
            entry = {
                "id": str(existing.get("id") or uuid4()),
                "title": title,
                "note": str(existing.get("note") or "").strip(),
                "date": date,
                "work_key": work_key,
                "watch_session_id": str(ticket.get("last_session_id") or "").strip(),
                "watched_at": watched_at,
                "ticket": archived_ticket,
            }
            data["moviesTodo"] = [item for item in todo if not same_work(item)]
            data["moviesDone"] = [entry] + [item for item in done if not same_work(item)]
            payload = {
                "data": normalize_stay_with_du_data(data),
                "updated_at": now_beijing_iso(),
            }
            _write_json(client, R2_KEY_STAY_WITH_DU, payload)
            return payload["data"]["moviesDone"][0]
        except Exception as exc:
            logger.error("archive_watch_ticket 失败 ticket_id=%s error=%s", ticket_id, exc, exc_info=True)
            return None
