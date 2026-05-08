"""R2 storage helpers for co-read cards, books, and chunked uploads."""
import threading
from typing import Any, Optional
from uuid import uuid4

from config import R2_BUCKET_NAME
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

R2_KEY_CO_READ_CARDS = "co_read/cards.json"
R2_KEY_CO_READ_BOOK_INDEX = "co_read/books/index.json"
R2_KEY_CO_READ_BOOK_PREFIX = "co_read/books"
R2_KEY_CO_READ_UPLOAD_PREFIX = "co_read/uploads"

_co_read_cards_write_lock = threading.Lock()
_co_read_book_write_lock = threading.Lock()
_co_read_upload_write_lock = threading.Lock()

logger = get_logger(__name__)


def _r2_store():
    from storage import r2_store

    return r2_store


def _s3_client():
    return _r2_store()._s3_client()


def _read_json(client, key: str) -> Optional[Any]:
    return _r2_store()._read_json(client, key)


def _write_json(client, key: str, data: Any):
    return _r2_store()._write_json(client, key, data)


def _normalize_co_read_text(value: Any, limit: int = 600) -> str:
    text = str(value or "").strip()
    text = " ".join(text.split())
    return text[:limit]


def _normalize_co_read_recent(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        snippet = _normalize_co_read_text(item.get("snippet"), 420)
        du_reply = _normalize_co_read_text(item.get("du_reply"), 420)
        user_note = _normalize_co_read_text(item.get("user_note"), 180)
        if not (snippet or du_reply or user_note):
            continue
        out.append(
            {
                "at": _normalize_co_read_text(item.get("at"), 40),
                "progress": _normalize_co_read_text(item.get("progress"), 80),
                "snippet": snippet,
                "user_note": user_note,
                "du_reply": du_reply,
            }
        )
    return out[:8]


def _normalize_co_read_story_recent(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        plot = _normalize_co_read_text(item.get("plot"), 1200)
        if not plot:
            continue
        out.append(
            {
                "section_index": _co_read_int(item.get("section_index"), 0),
                "range": _normalize_co_read_text(item.get("range"), 80),
                "plot": plot,
            }
        )
    out.sort(key=lambda x: int(x.get("section_index") or 0))
    return out[-10:]


def _normalize_co_read_story_milestones(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        event = _normalize_co_read_text(item.get("event"), 260)
        why = _normalize_co_read_text(item.get("why_matters"), 220)
        if not event:
            continue
        out.append(
            {
                "section_index": _co_read_int(item.get("section_index"), 0),
                "event": event,
                "why_matters": why,
            }
        )
    return out[:12]


def _normalize_co_read_string_list(items: Any, item_limit: int = 160, count_limit: int = 8) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        text = _normalize_co_read_text(item, item_limit)
        if text and text not in out:
            out.append(text)
        if len(out) >= count_limit:
            break
    return out


def _normalize_co_read_characters(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _normalize_co_read_text(item.get("name"), 80)
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(
            {
                "name": name,
                "summary": _normalize_co_read_text(item.get("summary"), 120),
                "status": _normalize_co_read_text(item.get("status"), 260),
                "known_facts": _normalize_co_read_string_list(item.get("known_facts"), 160, 10),
                "open_threads": _normalize_co_read_string_list(item.get("open_threads"), 160, 8),
            }
        )
        if len(out) >= 20:
            break
    return out


def normalize_co_read_book_card(card: Any, book_key: str = "", book_title: str = "") -> dict:
    """规整一本书的共读卡片。"""
    now = now_beijing_iso()
    raw = card if isinstance(card, dict) else {}
    key = _normalize_co_read_text(raw.get("book_key") or book_key, 120)
    title = _normalize_co_read_text(raw.get("book_title") or book_title, 200)
    focus_raw = raw.get("xinyue_focus")
    questions_raw = raw.get("open_questions")
    focus = [
        _normalize_co_read_text(x, 160)
        for x in (focus_raw if isinstance(focus_raw, list) else [])
    ]
    questions = [
        _normalize_co_read_text(x, 160)
        for x in (questions_raw if isinstance(questions_raw, list) else [])
    ]
    focus = [x for x in focus if x][:8]
    questions = [x for x in questions if x][:6]
    return {
        "book_key": key,
        "book_title": title,
        "current_progress": _normalize_co_read_text(raw.get("current_progress"), 80),
        "recent_co_read": _normalize_co_read_recent(raw.get("recent_co_read")),
        "story_recent": _normalize_co_read_story_recent(raw.get("story_recent")),
        "story_milestones": _normalize_co_read_story_milestones(raw.get("story_milestones")),
        "characters": _normalize_co_read_characters(raw.get("characters")),
        "xinyue_focus": focus,
        "du_understanding": _normalize_co_read_text(raw.get("du_understanding"), 600),
        "open_questions": questions,
        "created_at": _normalize_co_read_text(raw.get("created_at"), 40) or now,
        "updated_at": _normalize_co_read_text(raw.get("updated_at"), 40) or now,
    }


def get_co_read_cards_payload() -> dict:
    client = _s3_client()
    if not client:
        return {"cards": {}, "updated_at": ""}
    data = _read_json(client, R2_KEY_CO_READ_CARDS)
    if not isinstance(data, dict):
        return {"cards": {}, "updated_at": ""}
    cards = data.get("cards")
    if not isinstance(cards, dict):
        cards = {}
    out = {}
    for key, value in cards.items():
        clean_key = _normalize_co_read_text(key, 120)
        if not clean_key:
            continue
        out[clean_key] = normalize_co_read_book_card(value, book_key=clean_key)
    return {"cards": out, "updated_at": _normalize_co_read_text(data.get("updated_at"), 40)}


def get_co_read_book_card(book_key: str) -> Optional[dict]:
    key = _normalize_co_read_text(book_key, 120)
    if not key:
        return None
    cards = get_co_read_cards_payload().get("cards") or {}
    card = cards.get(key)
    return normalize_co_read_book_card(card, book_key=key) if isinstance(card, dict) else None


def list_co_read_book_cards() -> list[dict]:
    cards = get_co_read_cards_payload().get("cards") or {}
    out = [normalize_co_read_book_card(card, book_key=key) for key, card in cards.items() if isinstance(card, dict)]
    out.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    return out


def save_co_read_book_card(card: dict) -> bool:
    clean = normalize_co_read_book_card(card)
    key = str(clean.get("book_key") or "").strip()
    if not key:
        return False
    client = _s3_client()
    if not client:
        return False
    with _co_read_cards_write_lock:
        try:
            payload = get_co_read_cards_payload()
            cards = payload.get("cards") if isinstance(payload.get("cards"), dict) else {}
            cards[key] = clean
            _write_json(client, R2_KEY_CO_READ_CARDS, {"cards": cards, "updated_at": now_beijing_iso()})
            return True
        except Exception as e:
            logger.error("save_co_read_book_card 失败 key=%s error=%s", key, e, exc_info=True)
            return False


def _prepend_unique_text(items: list[str], text: str, limit: int = 8) -> list[str]:
    clean = _normalize_co_read_text(text, 160)
    if not clean:
        return items[:limit]
    out = [clean]
    for item in items or []:
        old = _normalize_co_read_text(item, 160)
        if old and old != clean:
            out.append(old)
        if len(out) >= limit:
            break
    return out


def update_co_read_book_card(
    book_key: str,
    book_title: str,
    current_progress: str,
    snippet: str,
    user_note: str,
    du_reply: str,
) -> Optional[dict]:
    """用一轮共读更新一本书的轻量卡片。"""
    key = _normalize_co_read_text(book_key, 120)
    if not key:
        return None
    now = now_beijing_iso()
    card = get_co_read_book_card(key) or normalize_co_read_book_card({}, book_key=key, book_title=book_title)
    card["book_key"] = key
    card["book_title"] = _normalize_co_read_text(book_title, 200) or card.get("book_title") or key
    card["current_progress"] = _normalize_co_read_text(current_progress, 80) or card.get("current_progress") or ""
    recent = _normalize_co_read_recent(card.get("recent_co_read"))
    recent.insert(
        0,
        {
            "at": now,
            "progress": card.get("current_progress") or "",
            "snippet": _normalize_co_read_text(snippet, 420),
            "user_note": _normalize_co_read_text(user_note, 180),
            "du_reply": _normalize_co_read_text(du_reply, 420),
        },
    )
    card["recent_co_read"] = _normalize_co_read_recent(recent)
    card["du_understanding"] = _normalize_co_read_text(du_reply, 600) or card.get("du_understanding") or ""
    if user_note:
        card["xinyue_focus"] = _prepend_unique_text(card.get("xinyue_focus") or [], user_note, 8)
        if "?" in user_note or "？" in user_note:
            card["open_questions"] = _prepend_unique_text(card.get("open_questions") or [], user_note, 6)
    card["updated_at"] = now
    clean = normalize_co_read_book_card(card, book_key=key, book_title=book_title)
    return clean if save_co_read_book_card(clean) else None


def _normalize_co_read_key(value: Any) -> str:
    text = str(value or "").strip()
    out = []
    for ch in text:
        out.append(ch if ch.isalnum() or ch in "-_" else "-")
    return "".join(out).strip("-")[:160]


def _co_read_book_object_key(book_key: str) -> str:
    safe = _normalize_co_read_key(book_key)
    return f"{R2_KEY_CO_READ_BOOK_PREFIX}/{safe}.json" if safe else ""


def _co_read_upload_meta_key(upload_id: str) -> str:
    safe = _normalize_co_read_key(upload_id)
    return f"{R2_KEY_CO_READ_UPLOAD_PREFIX}/{safe}/meta.json" if safe else ""


def _co_read_upload_chunk_key(upload_id: str, index: int) -> str:
    safe = _normalize_co_read_key(upload_id)
    return f"{R2_KEY_CO_READ_UPLOAD_PREFIX}/{safe}/chunks/{max(0, int(index)):05d}.txt" if safe else ""


def _co_read_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def normalize_co_read_book_mark(mark: Any, source: str = "user") -> Optional[dict]:
    if not isinstance(mark, dict):
        return None
    quote = str(mark.get("quote") or "").strip()[:800]
    note = str(mark.get("note") or "").strip()[:1000]
    du_reply = str(mark.get("du_reply") or "").strip()[:1200]
    if not (quote or note):
        return None
    now = now_beijing_iso()
    char_start = _co_read_int(mark.get("char_start"), -1)
    char_end = _co_read_int(mark.get("char_end"), -1)
    if char_start < 0 or char_end <= char_start:
        char_start = -1
        char_end = -1
    clean_source = "du" if source == "du" or mark.get("source") == "du" else "user"
    return {
        "id": _normalize_co_read_text(mark.get("id"), 80) or str(uuid4()),
        "source": clean_source,
        "quote": quote,
        "note": note,
        "du_reply": du_reply,
        "char_start": char_start,
        "char_end": char_end,
        "created_at": _normalize_co_read_text(mark.get("created_at"), 40) or now,
        "updated_at": _normalize_co_read_text(mark.get("updated_at"), 40) or now,
    }


def _normalize_co_read_marks(items: Any, source: str) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in items:
        mark = normalize_co_read_book_mark(item, source=source)
        if not mark:
            continue
        key = str(mark.get("id") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(mark)
    return out[:200]


def normalize_co_read_section(section: Any) -> Optional[dict]:
    if not isinstance(section, dict):
        return None
    index = max(1, _co_read_int(section.get("index"), 1))
    char_start = max(0, _co_read_int(section.get("char_start"), 0))
    char_end = max(char_start, _co_read_int(section.get("char_end"), char_start))
    if char_end <= char_start:
        return None
    now = now_beijing_iso()
    status = "done" if str(section.get("status") or "").strip() == "done" else "reading"
    return {
        "section_id": _normalize_co_read_text(section.get("section_id"), 80) or f"sec_{index:04d}",
        "index": index,
        "char_start": char_start,
        "char_end": char_end,
        "status": status,
        "user_marks": _normalize_co_read_marks(section.get("user_marks"), "user"),
        "du_marks": _normalize_co_read_marks(section.get("du_marks"), "du"),
        "user_section_note": str(section.get("user_section_note") or "").strip()[:2000],
        "du_section_note": str(section.get("du_section_note") or "").strip()[:2000],
        "created_at": _normalize_co_read_text(section.get("created_at"), 40) or now,
        "updated_at": _normalize_co_read_text(section.get("updated_at"), 40) or now,
        "completed_at": _normalize_co_read_text(section.get("completed_at"), 40),
    }


def normalize_co_read_book_payload(book: Any) -> dict:
    raw = book if isinstance(book, dict) else {}
    now = now_beijing_iso()
    key = _normalize_co_read_key(raw.get("book_key"))
    title = str(raw.get("book_title") or raw.get("title") or "").strip()[:240]
    content = str(raw.get("content") or "").replace("\r\n", "\n").replace("\r", "\n")
    sections: list[dict] = []
    sections_raw = raw.get("sections") if isinstance(raw.get("sections"), list) else []
    for item in sections_raw:
        section = normalize_co_read_section(item)
        if section:
            sections.append(section)
    sections.sort(key=lambda x: int(x.get("index") or 0))
    current_index = _co_read_int(raw.get("current_section_index"), 0)
    if sections:
        current_index = max(0, min(len(sections) - 1, current_index))
    else:
        current_index = 0
    return {
        "book_key": key,
        "book_title": title,
        "content": content,
        "sections": sections,
        "current_section_index": current_index,
        "created_at": _normalize_co_read_text(raw.get("created_at"), 40) or now,
        "updated_at": _normalize_co_read_text(raw.get("updated_at"), 40) or now,
    }


def _co_read_book_summary(book: dict) -> dict:
    clean = normalize_co_read_book_payload(book)
    sections = clean.get("sections") if isinstance(clean.get("sections"), list) else []
    done_count = sum(1 for item in sections if str(item.get("status") or "") == "done")
    return {
        "book_key": clean.get("book_key") or "",
        "book_title": clean.get("book_title") or "",
        "content_chars": len(clean.get("content") or ""),
        "section_count": len(sections),
        "done_count": done_count,
        "current_section_index": clean.get("current_section_index") or 0,
        "created_at": clean.get("created_at") or "",
        "updated_at": clean.get("updated_at") or "",
    }


def get_co_read_book_index_payload() -> dict:
    client = _s3_client()
    if not client:
        return {"books": [], "updated_at": ""}
    data = _read_json(client, R2_KEY_CO_READ_BOOK_INDEX)
    if not isinstance(data, dict):
        return {"books": [], "updated_at": ""}
    books_raw = data.get("books") if isinstance(data.get("books"), list) else []
    books = []
    seen: set[str] = set()
    for item in books_raw:
        if not isinstance(item, dict):
            continue
        key = _normalize_co_read_key(item.get("book_key"))
        if not key or key in seen:
            continue
        seen.add(key)
        books.append(
            {
                "book_key": key,
                "book_title": str(item.get("book_title") or "").strip()[:240],
                "content_chars": max(0, _co_read_int(item.get("content_chars"), 0)),
                "section_count": max(0, _co_read_int(item.get("section_count"), 0)),
                "done_count": max(0, _co_read_int(item.get("done_count"), 0)),
                "current_section_index": max(0, _co_read_int(item.get("current_section_index"), 0)),
                "created_at": _normalize_co_read_text(item.get("created_at"), 40),
                "updated_at": _normalize_co_read_text(item.get("updated_at"), 40),
            }
        )
    books.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    return {"books": books, "updated_at": _normalize_co_read_text(data.get("updated_at"), 40)}


def list_co_read_books() -> list[dict]:
    return get_co_read_book_index_payload().get("books") or []


def get_co_read_book(book_key: str) -> Optional[dict]:
    key = _normalize_co_read_key(book_key)
    object_key = _co_read_book_object_key(key)
    if not object_key:
        return None
    client = _s3_client()
    if not client:
        return None
    data = _read_json(client, object_key)
    if not isinstance(data, dict):
        return None
    clean = normalize_co_read_book_payload(data)
    return clean if clean.get("book_key") else None


def save_co_read_book(book: dict) -> Optional[dict]:
    clean = normalize_co_read_book_payload(book)
    key = _normalize_co_read_key(clean.get("book_key"))
    if not key:
        return None
    clean["book_key"] = key
    clean["updated_at"] = now_beijing_iso()
    object_key = _co_read_book_object_key(key)
    client = _s3_client()
    if not client or not object_key:
        return None
    with _co_read_book_write_lock:
        try:
            _write_json(client, object_key, clean)
            index_payload = get_co_read_book_index_payload()
            books = [item for item in (index_payload.get("books") or []) if item.get("book_key") != key]
            books.insert(0, _co_read_book_summary(clean))
            _write_json(client, R2_KEY_CO_READ_BOOK_INDEX, {"books": books[:500], "updated_at": now_beijing_iso()})
            return clean
        except Exception as e:
            logger.error("save_co_read_book 失败 key=%s error=%s", key, e, exc_info=True)
            return None


def delete_co_read_book(book_key: str) -> bool:
    key = _normalize_co_read_key(book_key)
    object_key = _co_read_book_object_key(key)
    if not key or not object_key:
        return False
    client = _s3_client()
    if not client:
        return False
    with _co_read_book_write_lock:
        try:
            client.delete_object(Bucket=R2_BUCKET_NAME, Key=object_key)
            index_payload = get_co_read_book_index_payload()
            books = [item for item in (index_payload.get("books") or []) if item.get("book_key") != key]
            _write_json(client, R2_KEY_CO_READ_BOOK_INDEX, {"books": books, "updated_at": now_beijing_iso()})
            return True
        except Exception as e:
            logger.error("delete_co_read_book 失败 key=%s error=%s", key, e, exc_info=True)
            return False


def create_co_read_upload(book_title: str, total_chunks: int, book_key: str = "") -> Optional[dict]:
    title = str(book_title or "").strip()[:240]
    total = max(1, _co_read_int(total_chunks, 1))
    if not title or total > 20000:
        return None
    upload_id = str(uuid4())
    now = now_beijing_iso()
    payload = {
        "upload_id": upload_id,
        "book_key": _normalize_co_read_key(book_key),
        "book_title": title,
        "total_chunks": total,
        "received_chunks": [],
        "content_chars": 0,
        "created_at": now,
        "updated_at": now,
    }
    key = _co_read_upload_meta_key(upload_id)
    client = _s3_client()
    if not client or not key:
        return None
    try:
        _write_json(client, key, payload)
        return payload
    except Exception as e:
        logger.error("create_co_read_upload 失败 upload_id=%s error=%s", upload_id, e, exc_info=True)
        return None


def get_co_read_upload(upload_id: str) -> Optional[dict]:
    key = _co_read_upload_meta_key(upload_id)
    client = _s3_client()
    if not client or not key:
        return None
    data = _read_json(client, key)
    if not isinstance(data, dict):
        return None
    uid = _normalize_co_read_key(data.get("upload_id"))
    if not uid:
        return None
    received = data.get("received_chunks") if isinstance(data.get("received_chunks"), list) else []
    return {
        "upload_id": uid,
        "book_key": _normalize_co_read_key(data.get("book_key")),
        "book_title": str(data.get("book_title") or "").strip()[:240],
        "total_chunks": max(1, _co_read_int(data.get("total_chunks"), 1)),
        "received_chunks": sorted({max(0, _co_read_int(x, 0)) for x in received}),
        "content_chars": max(0, _co_read_int(data.get("content_chars"), 0)),
        "created_at": _normalize_co_read_text(data.get("created_at"), 40),
        "updated_at": _normalize_co_read_text(data.get("updated_at"), 40),
    }


def save_co_read_upload_chunk(upload_id: str, index: int, chunk: str) -> Optional[dict]:
    meta = get_co_read_upload(upload_id)
    if not meta:
        return None
    idx = _co_read_int(index, -1)
    total = int(meta.get("total_chunks") or 0)
    if idx < 0 or idx >= total:
        return None
    text = str(chunk or "")
    client = _s3_client()
    chunk_key = _co_read_upload_chunk_key(upload_id, idx)
    meta_key = _co_read_upload_meta_key(upload_id)
    if not client or not chunk_key or not meta_key:
        return None
    with _co_read_upload_write_lock:
        try:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=chunk_key,
                Body=text.encode("utf-8"),
                ContentType="text/plain; charset=utf-8",
            )
            received = set(meta.get("received_chunks") or [])
            received.add(idx)
            meta["received_chunks"] = sorted(received)
            meta["content_chars"] = int(meta.get("content_chars") or 0) + len(text)
            meta["updated_at"] = now_beijing_iso()
            _write_json(client, meta_key, meta)
            return meta
        except Exception as e:
            logger.error("save_co_read_upload_chunk 失败 upload_id=%s index=%s error=%s", upload_id, idx, e, exc_info=True)
            return None


def assemble_co_read_upload(upload_id: str) -> tuple[Optional[dict], str]:
    meta = get_co_read_upload(upload_id)
    if not meta:
        return None, ""
    total = int(meta.get("total_chunks") or 0)
    received = set(meta.get("received_chunks") or [])
    if total <= 0 or any(idx not in received for idx in range(total)):
        return meta, ""
    client = _s3_client()
    if not client:
        return meta, ""
    chunks: list[str] = []
    try:
        for idx in range(total):
            key = _co_read_upload_chunk_key(upload_id, idx)
            resp = client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
            chunks.append(resp["Body"].read().decode("utf-8"))
        return meta, "".join(chunks)
    except Exception as e:
        logger.error("assemble_co_read_upload 失败 upload_id=%s error=%s", upload_id, e, exc_info=True)
        return meta, ""


def delete_co_read_upload(upload_id: str) -> bool:
    safe = _normalize_co_read_key(upload_id)
    if not safe:
        return False
    client = _s3_client()
    if not client:
        return False
    prefix = f"{R2_KEY_CO_READ_UPLOAD_PREFIX}/{safe}/"
    try:
        continuation = None
        while True:
            kwargs = {"Bucket": R2_BUCKET_NAME, "Prefix": prefix}
            if continuation:
                kwargs["ContinuationToken"] = continuation
            resp = client.list_objects_v2(**kwargs)
            objects = [{"Key": item["Key"]} for item in resp.get("Contents", []) if item.get("Key")]
            if objects:
                client.delete_objects(Bucket=R2_BUCKET_NAME, Delete={"Objects": objects, "Quiet": True})
            if not resp.get("IsTruncated"):
                break
            continuation = resp.get("NextContinuationToken")
        return True
    except Exception as e:
        logger.error("delete_co_read_upload 失败 upload_id=%s error=%s", upload_id, e, exc_info=True)
        return False
