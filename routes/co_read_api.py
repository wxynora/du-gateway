import json
import hashlib
import re
import uuid
import bisect
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from storage import r2_store, upstream_store

bp = Blueprint("co_read_api", __name__, url_prefix="/api/co-read")


def _book_key_from_title(title: str) -> str:
    raw = str(title or "").strip()
    if not raw:
        return ""
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", raw).strip("-").lower()
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"{slug[:40]}-{digest}" if slug else f"book-{digest}"


def _compact_text(text: str, limit: int = 260) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[:limit] + "..."


def _build_co_read_user_message(book_title: str, chapter_label: str, snippet: str, user_note: str) -> str:
    parts = [
        "[CO-READ]",
        f"Book: {book_title or ''}",
    ]
    if chapter_label:
        parts.append(f"Position: {chapter_label}")
    parts.extend(["Snippet:", snippet or ""])
    if user_note:
        parts.extend(["UserNote:", user_note])
    parts.extend(
        [
            "[/CO-READ]",
            "你正在陪辛玥一起读这本书。围绕选段和她的问题自然回应，不要解释这些标签。",
        ]
    )
    return "\n".join(parts)


def _build_card_system_context(card: dict | None) -> str:
    if not isinstance(card, dict):
        return ""
    title = _compact_text(card.get("book_title"), 120)
    progress = _compact_text(card.get("current_progress"), 80)
    recent = card.get("recent_co_read") if isinstance(card.get("recent_co_read"), list) else []
    story_recent = card.get("story_recent") if isinstance(card.get("story_recent"), list) else []
    story_milestones = card.get("story_milestones") if isinstance(card.get("story_milestones"), list) else []
    characters = card.get("characters") if isinstance(card.get("characters"), list) else []
    focus = card.get("xinyue_focus") if isinstance(card.get("xinyue_focus"), list) else []
    questions = card.get("open_questions") if isinstance(card.get("open_questions"), list) else []
    understanding = _compact_text(card.get("du_understanding"), 360)
    lines = ["[CO-READ CARD]"]
    if title:
        lines.append(f"书名：{title}")
    if progress:
        lines.append(f"当前进度：{progress}")
    if story_recent:
        lines.append("最近 10 小节剧情：")
        for item in story_recent[-10:]:
            if not isinstance(item, dict):
                continue
            idx = item.get("section_index") or ""
            rng = _compact_text(item.get("range"), 60)
            plot = _compact_text(item.get("plot"), 260)
            if plot:
                head = f"- 第 {idx} 小节" if idx else "-"
                if rng:
                    head += f"（{rng}）"
                lines.append(f"{head}：{plot}")
    if story_milestones:
        lines.append("重要剧情节点：")
        for item in story_milestones[:12]:
            if not isinstance(item, dict):
                continue
            event = _compact_text(item.get("event"), 120)
            why = _compact_text(item.get("why_matters"), 100)
            if event:
                lines.append(f"- {event}" + (f"；意义：{why}" if why else ""))
    if characters:
        lines.append("关键人物状态：")
        for item in characters[:12]:
            if not isinstance(item, dict):
                continue
            name = _compact_text(item.get("name"), 40)
            status = _compact_text(item.get("status"), 120)
            facts = item.get("known_facts") if isinstance(item.get("known_facts"), list) else []
            threads = item.get("open_threads") if isinstance(item.get("open_threads"), list) else []
            detail = []
            if status:
                detail.append(status)
            if facts:
                detail.append("事实：" + "；".join(_compact_text(x, 50) for x in facts[:3] if x))
            if threads:
                detail.append("疑点：" + "；".join(_compact_text(x, 50) for x in threads[:2] if x))
            if name and detail:
                lines.append(f"- {name}：" + "；".join(x for x in detail if x))
    if recent:
        lines.append("最近共读片段：")
        for item in recent[:3]:
            if not isinstance(item, dict):
                continue
            snippet = _compact_text(item.get("snippet"), 140)
            note = _compact_text(item.get("user_note"), 90)
            reply = _compact_text(item.get("du_reply"), 120)
            row = f"- 选段：{snippet}"
            if note:
                row += f"；辛玥关注：{note}"
            if reply:
                row += f"；渡的理解：{reply}"
            lines.append(row)
    if focus:
        lines.append("辛玥关注点：" + "；".join(_compact_text(x, 80) for x in focus[:5] if x))
    if understanding:
        lines.append(f"渡对这本书的当前理解：{understanding}")
    if questions:
        lines.append("待回看的问题：" + "；".join(_compact_text(x, 80) for x in questions[:5] if x))
    lines.extend(
        [
            "[/CO-READ CARD]",
            "上面的卡片只用于这次共读上下文。回复时自然延续即可，不要复述标签，也不要把读书卡片注入日常聊天。",
        ]
    )
    return "\n".join(lines)


def _extract_chat_completion_result(result) -> tuple[int, dict]:
    response = result
    status = 200
    if isinstance(result, tuple):
        response = result[0] if result else None
        for item in result[1:]:
            if isinstance(item, int):
                status = item
                break
    if hasattr(response, "status_code"):
        try:
            status = int(response.status_code)
        except Exception:
            pass
    data = None
    if hasattr(response, "get_json"):
        try:
            data = response.get_json(silent=True)
        except Exception:
            data = None
    if data is None and hasattr(response, "get_data"):
        try:
            text = response.get_data(as_text=True)
            data = json.loads(text) if text else {}
        except Exception:
            data = {"raw": response.get_data(as_text=True) if hasattr(response, "get_data") else ""}
    if not isinstance(data, dict):
        data = {"content": data}
    return status, data


def _extract_assistant_content(resp_json: dict[str, Any]) -> str:
    if not isinstance(resp_json, dict):
        return ""
    choices = resp_json.get("choices")
    if not (isinstance(choices, list) and choices and isinstance(choices[0], dict)):
        return ""
    msg = ((choices[0] or {}).get("message") or {})
    if isinstance(msg, dict):
        return str(msg.get("content") or "")
    return ""


def _request_json_body() -> tuple[dict, tuple | None]:
    if not request.is_json:
        return {}, (jsonify({"ok": False, "error": "需要 application/json"}), 400)
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return {}, (jsonify({"ok": False, "error": "JSON 无效"}), 400)
    return body, None


def _co_read_section_id(index: int) -> str:
    return f"sec_{max(1, int(index)):04d}"


def _choose_section_break(candidates: list[int], min_end: int, target_end: int, max_end: int) -> int:
    left = bisect.bisect_left(candidates, min_end)
    right = bisect.bisect_right(candidates, max_end)
    if left >= right:
        return 0
    window = candidates[left:right]
    return min(window, key=lambda pos: abs(pos - target_end))


def _build_co_read_sections(content: str) -> list[dict]:
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    total = len(text)
    if total <= 0:
        return []
    target = 10000
    min_size = 6000
    max_size = 16000
    newline_breaks = [idx + 1 for idx, ch in enumerate(text) if ch == "\n"]
    sentence_breaks = [idx + 1 for idx, ch in enumerate(text) if ch in "。！？!?；;"]
    sections: list[dict] = []
    cursor = 0
    index = 1
    while cursor < total:
        raw_start = cursor
        while raw_start < total and text[raw_start].isspace():
            raw_start += 1
        if raw_start >= total:
            break
        remain = total - raw_start
        if remain <= max_size:
            raw_end = total
        else:
            min_end = min(total, raw_start + min_size)
            target_end = min(total, raw_start + target)
            max_end = min(total, raw_start + max_size)
            raw_end = (
                _choose_section_break(newline_breaks, min_end, target_end, max_end)
                or _choose_section_break(sentence_breaks, min_end, target_end, max_end)
                or max_end
            )
        char_end = raw_end
        while char_end > raw_start and text[char_end - 1].isspace():
            char_end -= 1
        if char_end <= raw_start:
            cursor = max(raw_end, raw_start + 1)
            continue
        sections.append(
            {
                "section_id": _co_read_section_id(index),
                "index": index,
                "char_start": raw_start,
                "char_end": char_end,
                "status": "reading",
                "user_marks": [],
                "du_marks": [],
                "user_section_note": "",
                "du_section_note": "",
            }
        )
        cursor = max(raw_end, char_end)
        index += 1
    return sections


def _find_section(book: dict, section_id: str) -> tuple[int, dict | None]:
    sections = book.get("sections") if isinstance(book.get("sections"), list) else []
    raw_id = str(section_id or "").strip()
    for idx, section in enumerate(sections):
        if str(section.get("section_id") or "") == raw_id or str(section.get("index") or "") == raw_id:
            return idx, section
    return -1, None


def _section_text(book: dict, section: dict) -> str:
    content = str(book.get("content") or "")
    start = max(0, int(section.get("char_start") or 0))
    end = max(start, int(section.get("char_end") or start))
    return content[start:end]


def _section_label(book: dict, section: dict) -> str:
    sections = book.get("sections") if isinstance(book.get("sections"), list) else []
    total = max(1, len(sections))
    index = int(section.get("index") or 1)
    content_len = max(1, len(str(book.get("content") or "")))
    start_pct = int((int(section.get("char_start") or 0) / content_len) * 100)
    end_pct = int((int(section.get("char_end") or 0) / content_len) * 100)
    return f"第 {index}/{total} 小节（约 {start_pct}% - {end_pct}%）"


def _compact_mark_lines(marks: list[dict], empty_text: str = "无") -> str:
    lines = []
    for idx, item in enumerate(marks[:12], start=1):
        mark_id = _compact_text(item.get("id"), 80)
        quote = _compact_text(item.get("quote"), 120)
        note = _compact_text(item.get("note"), 160)
        prefix = f"{idx}. [mark_id={mark_id}] " if mark_id else f"{idx}. "
        if quote and note:
            lines.append(f"{prefix}「{quote}」：{note}")
        elif quote:
            lines.append(f"{prefix}「{quote}」")
        elif note:
            lines.append(f"{prefix}{note}")
    return "\n".join(lines) if lines else empty_text


def _compact_for_prompt(text: str, limit: int = 18000) -> str:
    raw = str(text or "").strip()
    return raw if len(raw) <= limit else raw[:limit] + "\n……（本小节过长，后文已截断）"


def _build_section_complete_user_message(book: dict, section: dict) -> str:
    title = str(book.get("book_title") or "").strip()
    section_text = _section_text(book, section)
    user_marks = section.get("user_marks") if isinstance(section.get("user_marks"), list) else []
    user_note = str(section.get("user_section_note") or "").strip()
    return "\n".join(
        [
            "[CO-READ SECTION]",
            f"书名：{title}",
            f"位置：{_section_label(book, section)}",
            "",
            "本小节原文：",
            _compact_for_prompt(section_text),
            "",
            "辛玥的粉色标记：",
            _compact_mark_lines(user_marks),
            "",
            "辛玥的小节感想：",
            user_note or "无",
            "[/CO-READ SECTION]",
            "",
            "你正在和辛玥一起读这本书。这次读完一个共读小节，等同一次日常对话。",
            "请用渡的第一人称完成三件事：",
            "0. 对辛玥的每一条粉色标记逐条回应；必须保留对应 mark_id。",
            "1. 给出 1-5 条你的蓝色标记，每条 quote 必须是本小节原文里连续出现的原句或短语，note 写你自己的感受；quote 可以包含引号，不需要转义。",
            "2. 写一段你的本小节感想，回应辛玥的粉色标记和小节感想。",
            "只返回下面的 XML 片段，不要 Markdown，不要解释，不要代码块：",
            "<co_read_result>",
            '<user_mark_reply mark_id="mark_xxx">我对这条粉色标记的回复</user_mark_reply>',
            "<du_mark><quote>原文中连续出现的短句</quote><note>我的标记感想</note></du_mark>",
            "<du_section_note>我的小节感想</du_section_note>",
            "</co_read_result>",
        ]
    )


def _strip_model_fences(text: str) -> str:
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json|xml)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _unescape_model_text(text: str) -> str:
    raw = str(text or "").strip()
    raw = raw.replace("<![CDATA[", "").replace("]]>", "")
    raw = raw.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    raw = raw.replace("&quot;", '"').replace("&#34;", '"').replace("&#39;", "'")
    raw = raw.replace('\\"', '"').replace("\\n", "\n")
    return raw.strip()


def _extract_tag_text(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", str(text or ""), flags=re.I | re.S)
    return _unescape_model_text(match.group(1)) if match else ""


def _extract_xml_attr(attrs: str, name: str) -> str:
    match = re.search(rf"{name}\s*=\s*(['\"])(.*?)\1", str(attrs or ""), flags=re.I | re.S)
    return _unescape_model_text(match.group(2)) if match else ""


def _extract_loose_json_result(text: str) -> dict:
    raw = _strip_model_fences(text)
    marks = []
    for match in re.finditer(
        r'"quote"\s*:\s*"(?P<quote>.*?)"\s*,\s*"note"\s*:\s*"(?P<note>.*?)"\s*(?:\}|,\s*")',
        raw,
        flags=re.S,
    ):
        quote = _unescape_model_text(match.group("quote"))
        note = _unescape_model_text(match.group("note"))
        if quote or note:
            marks.append({"quote": quote, "note": note})
    note_match = re.search(r'"du_section_note"\s*:\s*"(?P<note>.*?)"\s*(?:\}|\n|$)', raw, flags=re.S)
    note = _unescape_model_text(note_match.group("note")) if note_match else ""
    replies = []
    for match in re.finditer(
        r'"mark_id"\s*:\s*"(?P<mark_id>.*?)"\s*,\s*"(?:reply|du_reply)"\s*:\s*"(?P<reply>.*?)"',
        raw,
        flags=re.S,
    ):
        mark_id = _unescape_model_text(match.group("mark_id"))
        reply = _unescape_model_text(match.group("reply"))
        if mark_id and reply:
            replies.append({"mark_id": mark_id, "reply": reply})
    return {"du_marks": marks, "du_section_note": note, "user_mark_replies": replies} if (marks or note or replies) else {}


def _extract_co_read_result(text: str) -> dict:
    raw = _strip_model_fences(text)
    user_replies = []
    for attrs, reply_text in re.findall(r"<user_mark_reply\b([^>]*)>(.*?)</user_mark_reply>", raw, flags=re.I | re.S):
        mark_id = _extract_xml_attr(attrs, "mark_id")
        reply = _unescape_model_text(reply_text)
        if mark_id and reply:
            user_replies.append({"mark_id": mark_id, "reply": reply})
    xml_marks = []
    for block in re.findall(r"<du_mark\b[^>]*>(.*?)</du_mark>", raw, flags=re.I | re.S):
        quote = _extract_tag_text(block, "quote")
        note = _extract_tag_text(block, "note")
        if quote or note:
            xml_marks.append({"quote": quote, "note": note})
    xml_note = _extract_tag_text(raw, "du_section_note")
    if xml_marks or xml_note or user_replies:
        return {"du_marks": xml_marks, "du_section_note": xml_note, "user_mark_replies": user_replies}
    parsed = _extract_json_object(raw)
    if parsed:
        return parsed
    return _extract_loose_json_result(raw)


def _extract_json_object(text: str) -> dict:
    raw = _strip_model_fences(text)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _compact_with_map(text: str) -> tuple[str, list[int]]:
    compact = []
    mapping = []
    for idx, ch in enumerate(text):
        if ch.isspace():
            continue
        compact.append(ch)
        mapping.append(idx)
    return "".join(compact), mapping


def _locate_quote(section_text: str, quote: str, absolute_start: int) -> tuple[int, int]:
    raw_quote = str(quote or "").strip()
    if not raw_quote:
        return -1, -1
    idx = section_text.find(raw_quote)
    if idx >= 0:
        return absolute_start + idx, absolute_start + idx + len(raw_quote)
    compact_text, mapping = _compact_with_map(section_text)
    compact_quote = "".join(ch for ch in raw_quote if not ch.isspace())
    if not compact_quote:
        return -1, -1
    idx = compact_text.find(compact_quote)
    if idx < 0 or idx + len(compact_quote) > len(mapping):
        return -1, -1
    start = mapping[idx]
    end = mapping[idx + len(compact_quote) - 1] + 1
    return absolute_start + start, absolute_start + end


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


def handle_co_read_books():
    if request.method == "GET":
        return jsonify({"ok": True, "books": r2_store.list_co_read_books()})

    body, error = _request_json_body()
    if error:
        return error
    title = str(body.get("book_title") or body.get("title") or "").strip()
    content = str(body.get("content") or "").replace("\r\n", "\n").replace("\r", "\n")
    book_key = str(body.get("book_key") or "").strip() or _book_key_from_title(title)
    saved, err = _save_co_read_book_from_content(title, content, book_key=book_key)
    if not saved:
        return jsonify({"ok": False, "error": err or "保存共读书籍失败"}), 400
    return jsonify({"ok": True, "book": saved}), 200


def handle_co_read_upload_start():
    body, error = _request_json_body()
    if error:
        return error
    title = str(body.get("book_title") or body.get("title") or "").strip()
    total_chunks = int(body.get("total_chunks") or 0)
    book_key = str(body.get("book_key") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "缺少 book_title"}), 400
    if total_chunks <= 0:
        return jsonify({"ok": False, "error": "缺少 total_chunks"}), 400
    upload = r2_store.create_co_read_upload(title, total_chunks, book_key=book_key)
    if not upload:
        return jsonify({"ok": False, "error": "创建上传任务失败"}), 500
    return jsonify({"ok": True, "upload": upload, "upload_id": upload.get("upload_id")}), 200


def handle_co_read_upload_chunk(upload_id: str):
    body, error = _request_json_body()
    if error:
        return error
    try:
        index = int(body.get("index"))
    except Exception:
        return jsonify({"ok": False, "error": "缺少 index"}), 400
    chunk = str(body.get("chunk") or "")
    if not chunk:
        return jsonify({"ok": False, "error": "缺少 chunk"}), 400
    if len(chunk) > 260000:
        return jsonify({"ok": False, "error": "chunk 过大"}), 413
    upload = r2_store.save_co_read_upload_chunk(upload_id, index, chunk)
    if not upload:
        return jsonify({"ok": False, "error": "保存分片失败"}), 500
    return jsonify({"ok": True, "upload": upload}), 200


def handle_co_read_upload_finish(upload_id: str):
    meta, content = r2_store.assemble_co_read_upload(upload_id)
    if not meta:
        return jsonify({"ok": False, "error": "上传任务不存在"}), 404
    if not content:
        total = int(meta.get("total_chunks") or 0)
        received = len(meta.get("received_chunks") or [])
        return jsonify({"ok": False, "error": f"分片还没传完：{received}/{total}"}), 400
    saved, err = _save_co_read_book_from_content(
        str(meta.get("book_title") or ""),
        content,
        book_key=str(meta.get("book_key") or ""),
    )
    if not saved:
        return jsonify({"ok": False, "error": err or "保存共读书籍失败"}), 500
    r2_store.delete_co_read_upload(upload_id)
    return jsonify({"ok": True, "book": saved}), 200


def handle_co_read_book_detail(book_key: str):
    book = r2_store.get_co_read_book(book_key)
    if not book:
        return jsonify({"ok": False, "error": "书不存在"}), 404
    return jsonify({"ok": True, "book": book})


def handle_co_read_book_delete(book_key: str):
    ok = r2_store.delete_co_read_book(book_key)
    return jsonify({"ok": ok})


def handle_co_read_section_update(book_key: str, section_id: str):
    body, error = _request_json_body()
    if error:
        return error
    book = r2_store.get_co_read_book(book_key)
    if not book:
        return jsonify({"ok": False, "error": "书不存在"}), 404
    section_index, section = _find_section(book, section_id)
    if not section:
        return jsonify({"ok": False, "error": "小节不存在"}), 404
    text = _section_text(book, section)
    if "user_marks" in body:
        section["user_marks"] = _normalize_marks_for_section(body.get("user_marks"), "user", section, text)
    if "user_section_note" in body:
        section["user_section_note"] = str(body.get("user_section_note") or "").strip()[:2000]
    section["updated_at"] = r2_store.now_beijing_iso() if hasattr(r2_store, "now_beijing_iso") else ""
    saved = r2_store.save_co_read_book(_replace_book_section(book, section_index, section))
    if not saved:
        return jsonify({"ok": False, "error": "保存小节失败"}), 500
    return jsonify({"ok": True, "book": saved, "section": saved["sections"][section_index]})


def handle_co_read_section_complete(book_key: str, section_id: str):
    body, error = _request_json_body()
    if error:
        return error
    window_id = str(body.get("window_id") or request.headers.get("X-Window-Id") or "").strip()
    model = upstream_store.get_cached_active_model(refresh_if_missing=False)
    if not window_id:
        return jsonify({"ok": False, "error": "缺少 window_id"}), 400
    if not model:
        return jsonify({"ok": False, "error": "当前未设置全局模型"}), 400
    book = r2_store.get_co_read_book(book_key)
    if not book:
        return jsonify({"ok": False, "error": "书不存在"}), 404
    section_index, section = _find_section(book, section_id)
    if not section:
        return jsonify({"ok": False, "error": "小节不存在"}), 404

    text = _section_text(book, section)
    if "user_marks" in body:
        section["user_marks"] = _normalize_marks_for_section(body.get("user_marks"), "user", section, text)
    if "user_section_note" in body:
        section["user_section_note"] = str(body.get("user_section_note") or "").strip()[:2000]

    card = r2_store.get_co_read_book_card(book.get("book_key") or "") if book.get("book_key") else None
    card_context = _build_card_system_context(card)
    messages = []
    if card_context:
        messages.append({"role": "system", "content": card_context})
    messages.append({"role": "user", "content": _build_section_complete_user_message(book, section)})
    chat_body = {
        "model": model,
        "stream": False,
        "window_id": window_id,
        "messages": messages,
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": request.headers.get("User-Agent") or "SumiTalk CoRead",
        "X-Force-Last4": str(request.headers.get("X-Force-Last4") or body.get("force_last4") or "1"),
        "X-Reply-Channel": "sumitalk",
        "X-Reply-Target": "co_read_section",
        "X-Skip-Dynamic-Memory": "1",
        "X-Window-Id": window_id,
    }
    try:
        from routes.chat import chat_completions

        with current_app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            json=chat_body,
            headers=headers,
            environ_base={"REMOTE_ADDR": request.remote_addr or "127.0.0.1"},
        ):
            result = chat_completions()
            status_code, resp_json = _extract_chat_completion_result(result)
    except Exception as e:
        return jsonify({"ok": False, "error": f"调用聊天管道失败: {e}"}), 502

    if status_code >= 400:
        err = resp_json.get("error") or resp_json.get("message") or "upstream error"
        return jsonify({"ok": False, "error": str(err), "status_code": status_code, "resp": resp_json}), status_code

    raw_reply = _extract_assistant_content(resp_json).strip()
    if not raw_reply:
        return jsonify({"ok": False, "error": "上游没有返回内容", "resp": resp_json}), 502
    parsed = _extract_co_read_result(raw_reply)
    du_note = str(parsed.get("du_section_note") or "").strip() if parsed else ""
    du_marks_raw = parsed.get("du_marks") if isinstance(parsed.get("du_marks"), list) else []
    user_mark_replies = parsed.get("user_mark_replies") if isinstance(parsed.get("user_mark_replies"), list) else []
    if not du_note:
        du_note = raw_reply[:2000]
    if user_mark_replies:
        reply_map = {}
        for item in user_mark_replies:
            if not isinstance(item, dict):
                continue
            mark_id = str(item.get("mark_id") or "").strip()
            reply = str(item.get("reply") or item.get("du_reply") or "").strip()
            if mark_id and reply:
                reply_map[mark_id] = reply[:1200]
        if reply_map:
            next_user_marks = []
            section_user_marks = section.get("user_marks") if isinstance(section.get("user_marks"), list) else []
            for mark in section_user_marks:
                if not isinstance(mark, dict):
                    continue
                mark_id = str(mark.get("id") or "").strip()
                if mark_id in reply_map:
                    mark = {**mark, "du_reply": reply_map[mark_id]}
                next_user_marks.append(mark)
            section["user_marks"] = next_user_marks
    section["du_marks"] = _normalize_marks_for_section(du_marks_raw, "du", section, text)
    section["du_section_note"] = du_note[:2000]
    section["status"] = "done"
    section["completed_at"] = r2_store.now_beijing_iso() if hasattr(r2_store, "now_beijing_iso") else ""
    section["updated_at"] = section["completed_at"]

    saved = r2_store.save_co_read_book(_replace_book_section(book, section_index, section))
    if not saved:
        return jsonify({"ok": False, "error": "保存小节完成结果失败"}), 500

    next_card = None
    card_update_error = ""
    try:
        from services.co_read_card_qwen import build_co_read_card_update

        old_card = r2_store.get_co_read_book_card(saved.get("book_key") or "") if saved.get("book_key") else {}
        section_for_card = dict(saved["sections"][section_index])
        section_for_card["current_progress"] = _section_label(saved, section_for_card)
        section_for_card["range"] = _section_label(saved, section_for_card)
        next_card, card_update_error = build_co_read_card_update(
            old_card=old_card or {},
            book=saved,
            section=section_for_card,
            section_text=text,
        )
        if next_card:
            next_card["current_progress"] = _section_label(saved, saved["sections"][section_index])
            if not r2_store.save_co_read_book_card(next_card):
                card_update_error = "保存千问读书卡片失败"
                next_card = None
    except Exception as e:
        current_app.logger.warning("千问读书卡片更新失败 book_key=%s error=%s", saved.get("book_key"), e, exc_info=True)
        card_update_error = str(e)
    if not next_card:
        next_card = r2_store.update_co_read_book_card(
            book_key=saved.get("book_key") or "",
            book_title=saved.get("book_title") or "",
            current_progress=_section_label(saved, saved["sections"][section_index]),
            snippet=text,
            user_note=section.get("user_section_note") or _compact_mark_lines(section.get("user_marks") or [], ""),
            du_reply=section.get("du_section_note") or "",
        )

    return jsonify(
        {
            "ok": True,
            "book": saved,
            "section": saved["sections"][section_index],
            "du_marks": section.get("du_marks") or [],
            "du_section_note": section.get("du_section_note") or "",
            "raw_reply": raw_reply,
            "card": next_card,
            "card_update_error": card_update_error,
        }
    )


def handle_co_read_session():
    if not request.is_json:
        return jsonify({"ok": False, "error": "需要 application/json"}), 400
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON 无效"}), 400

    window_id = str(body.get("window_id") or request.headers.get("X-Window-Id") or "").strip()
    book_title = str(body.get("book_title") or "").strip()
    book_key = str(body.get("book_key") or "").strip() or _book_key_from_title(book_title)
    chapter_label = str(body.get("chapter_label") or "").strip()
    snippet = str(body.get("snippet") or "").strip()
    user_note = str(body.get("user_note") or "").strip()
    reply_target = str(body.get("reply_target") or request.headers.get("X-Reply-Target") or "co_read").strip()
    model = str(body.get("model") or "").strip() or upstream_store.get_cached_active_model(refresh_if_missing=False)

    if not window_id:
        return jsonify({"ok": False, "error": "缺少 window_id"}), 400
    if not model:
        return jsonify({"ok": False, "error": "当前未设置全局模型"}), 400
    if not snippet:
        return jsonify({"ok": False, "error": "缺少 snippet"}), 400

    if len(snippet) > 50000:
        snippet = snippet[:50000] + "..."

    card = r2_store.get_co_read_book_card(book_key) if book_key else None
    card_context = _build_card_system_context(card)
    user_prompt = _build_co_read_user_message(book_title, chapter_label, snippet, user_note)
    messages = []
    if card_context:
        messages.append({"role": "system", "content": card_context})
    messages.append({"role": "user", "content": user_prompt})
    chat_body = {
        "model": model,
        "stream": False,
        "window_id": window_id,
        "messages": messages,
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": request.headers.get("User-Agent") or "SumiTalk CoRead",
        "X-Force-Last4": str(request.headers.get("X-Force-Last4") or body.get("force_last4") or "1"),
        "X-Reply-Channel": "sumitalk",
        "X-Reply-Target": reply_target,
        "X-Window-Id": window_id,
    }

    try:
        from routes.chat import chat_completions

        with current_app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            json=chat_body,
            headers=headers,
            environ_base={"REMOTE_ADDR": request.remote_addr or "127.0.0.1"},
        ):
            result = chat_completions()
            status_code, resp_json = _extract_chat_completion_result(result)
    except Exception as e:
        return jsonify({"ok": False, "error": f"调用聊天管道失败: {e}"}), 502

    if status_code >= 400:
        err = resp_json.get("error") or resp_json.get("message") or "upstream error"
        return jsonify({"ok": False, "error": str(err), "status_code": status_code, "resp": resp_json}), status_code

    du_reply = _extract_assistant_content(resp_json).strip()
    if not du_reply:
        return jsonify({"ok": False, "error": "上游没有返回内容", "resp": resp_json}), 502
    next_card = r2_store.update_co_read_book_card(
        book_key=book_key,
        book_title=book_title,
        current_progress=chapter_label,
        snippet=snippet,
        user_note=user_note,
        du_reply=du_reply,
    ) if book_key else None

    return jsonify(
        {
            "ok": True,
            "session_id": str(uuid.uuid4()),
            "window_id": window_id,
            "du_reply": du_reply,
            "book_key": book_key,
            "card": next_card,
        }
    ), 200


@bp.route("/session", methods=["POST", "OPTIONS"])
def co_read_session():
    if request.method == "OPTIONS":
        return "", 204
    return handle_co_read_session()


@bp.route("/sessions", methods=["GET"])
def co_read_sessions():
    cards = r2_store.list_co_read_book_cards()
    return jsonify({"ok": True, "sessions": cards, "count": len(cards)})


@bp.route("/books/<book_key>/card", methods=["GET"])
def co_read_book_card(book_key: str):
    card = r2_store.get_co_read_book_card(book_key)
    return jsonify({"ok": True, "book_key": book_key, "card": card})
