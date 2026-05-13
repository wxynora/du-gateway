from typing import Any

from services.co_read_flow import (
    _book_key_from_title,
    _build_co_read_sections,
    _locate_quote,
)
from storage import r2_store


def _normalize_marks_for_section(items: Any, source: str, section: dict, section_text: str) -> list[dict]:
    if not isinstance(items, list):
        return []
    absolute_start = int(section.get("char_start") or 0)
    out = []
    for item in items:
        mark = r2_store.normalize_co_read_book_mark(item, source=source)
        if not mark:
            continue
        char_start = int(mark.get("char_start") if mark.get("char_start") is not None else -1)
        char_end = int(mark.get("char_end") if mark.get("char_end") is not None else -1)
        if char_start < absolute_start or char_end > int(section.get("char_end") or absolute_start):
            located_start, located_end = _locate_quote(section_text, mark.get("quote") or "", absolute_start)
            mark["char_start"] = located_start
            mark["char_end"] = located_end
        out.append(mark)
    return out


def _replace_book_section(book: dict, index: int, section: dict) -> dict:
    sections = book.get("sections") if isinstance(book.get("sections"), list) else []
    if 0 <= index < len(sections):
        sections[index] = section
    book["sections"] = sections
    book["current_section_index"] = max(0, min(len(sections) - 1, index)) if sections else 0
    return book


def _save_co_read_book_from_content(title: str, content: str, book_key: str = "") -> tuple[dict | None, str]:
    clean_title = str(title or "").strip()
    clean_content = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    if not clean_title:
        return None, "缺少 book_title"
    if not clean_content.strip():
        return None, "缺少 content"
    clean_key = str(book_key or "").strip() or _book_key_from_title(clean_title)
    sections = _build_co_read_sections(clean_content)
    if not sections:
        return None, "无法切分文本"
    existing = r2_store.get_co_read_book(clean_key) or {}
    book = {
        "book_key": clean_key,
        "book_title": clean_title,
        "content": clean_content,
        "sections": sections,
        "current_section_index": int(existing.get("current_section_index") or 0) if existing else 0,
        "created_at": existing.get("created_at") or "",
    }
    saved = r2_store.save_co_read_book(book)
    if not saved:
        return None, "保存共读书籍失败"
    return saved, ""
