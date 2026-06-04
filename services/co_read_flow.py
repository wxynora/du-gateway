import bisect
import hashlib
import json
import re


CO_READ_DU_VOICE_SYSTEM = """【共读语气】
这些蓝色标记、对粉色标记的回复、小节感想，都是写给小玥看的。
像平时和她聊天那样写就行：第一人称，自然一点，亲近一点，有你自己的感受。
不要写成读书报告，也不要用第三人称说“渡认为”。"""


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
            "你正在陪小玥一起读这本书。围绕选段和她的问题自然回应，不要解释这些标签。",
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
            summary = _compact_text(item.get("summary"), 80)
            status = _compact_text(item.get("status"), 120)
            facts = item.get("known_facts") if isinstance(item.get("known_facts"), list) else []
            threads = item.get("open_threads") if isinstance(item.get("open_threads"), list) else []
            detail = []
            if summary:
                detail.append(summary)
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
                row += f"；小玥关注：{note}"
            if reply:
                row += f"；渡的理解：{reply}"
            lines.append(row)
    if focus:
        lines.append("小玥关注点：" + "；".join(_compact_text(x, 80) for x in focus[:5] if x))
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


def _co_read_book_summary_response(book: dict) -> dict:
    sections = book.get("sections") if isinstance(book.get("sections"), list) else []
    done_count = sum(1 for item in sections if isinstance(item, dict) and str(item.get("status") or "") == "done")
    try:
        current_index = int(book.get("current_section_index") or 0)
    except Exception:
        current_index = 0
    return {
        "book_key": str(book.get("book_key") or ""),
        "book_title": str(book.get("book_title") or ""),
        "content_chars": len(str(book.get("content") or "")),
        "section_count": len(sections),
        "done_count": done_count,
        "current_section_index": max(0, current_index),
        "created_at": str(book.get("created_at") or ""),
        "updated_at": str(book.get("updated_at") or ""),
    }


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
            "小玥的粉色标记：",
            _compact_mark_lines(user_marks),
            "",
            "小玥的小节感想：",
            user_note or "无",
            "[/CO-READ SECTION]",
            "",
            "你正在和小玥一起读这本书。这次读完一个共读小节，等同一次日常对话。",
            "请完成三件事：",
            "0. 对小玥的每一条粉色标记逐条回应；必须保留对应 mark_id。",
            "1. 给出 1-5 条你的蓝色标记，每条 quote 必须是本小节原文里连续出现的原句或短语，note 写你自己的感受；quote 可以包含引号，不需要转义。",
            "2. 写一段你的本小节感想，回应小玥的粉色标记和小节感想。",
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
