from __future__ import annotations

import io
import re
from pathlib import Path

from flask import jsonify, request

from services import codex_group_chat
from storage import r2_store


_MAX_IMPORT_BYTES = 16 * 1024 * 1024
_MAX_IMPORT_CHUNKS = 10
_IMPORT_CHUNK_TARGET_CHARS = 9000
_IMPORT_CHUNK_MAX_CHARS = 12000
_MAX_EXTRACT_CHARS = _MAX_IMPORT_CHUNKS * _IMPORT_CHUNK_MAX_CHARS
_TEXT_EXTS = {".txt", ".md", ".markdown"}
_PDF_EXTS = {".pdf"}
_WORD_EXTS = {".docx"}
_SOURCE_TYPE_OVERRIDES = {"pdf", "question_bank", "word", "text", "fenbi", "note", "wrong_question"}


def _clip_import_text(text: str) -> str:
    clean = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(clean) <= _MAX_EXTRACT_CHARS:
        return clean
    return clean[:_MAX_EXTRACT_CHARS].rstrip() + "\n\n...[导入时已截断，原文件仍可重新拆分导入]"


def _is_import_heading(line: str) -> bool:
    clean = str(line or "").strip()
    if not clean or len(clean) > 90:
        return False
    if re.match(r"^---\s*第\s*\d+\s*页\s*---$", clean):
        return False
    patterns = (
        r"^第[一二三四五六七八九十百千\d]+[章节讲课部分单元]\s*[:：、.\s-]?.{0,60}$",
        r"^[一二三四五六七八九十]+[、.．]\s*\S.{0,60}$",
        r"^\d+(?:\.\d+){0,3}[、.．\s]\s*\S.{0,60}$",
        r"^（[一二三四五六七八九十\d]+）\s*\S.{0,60}$",
    )
    return any(re.match(pattern, clean) for pattern in patterns)


def _chunk_label(label: str, fallback: str = "正文") -> str:
    clean = re.sub(r"\s+", " ", str(label or "").strip())
    clean = re.sub(r"^---\s*|\s*---$", "", clean).strip()
    return (clean or fallback)[:36]


def _split_sections_by_headings(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_label = "开头"
    current_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if _is_import_heading(line) and current_lines:
            body = "\n".join(current_lines).strip()
            if body:
                sections.append((current_label, body))
            current_label = line.strip()
            current_lines = [line]
        else:
            current_lines.append(line)
            if _is_import_heading(line):
                current_label = line.strip()
    body = "\n".join(current_lines).strip()
    if body:
        sections.append((current_label, body))
    return sections


def _split_sections_by_pages(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    parts = re.split(r"(?=^---\s*第\s*\d+\s*页\s*---$)", text, flags=re.MULTILINE)
    for index, part in enumerate(parts, start=1):
        body = part.strip()
        if not body:
            continue
        first_line = body.splitlines()[0].strip()
        label = first_line if re.match(r"^---\s*第\s*\d+\s*页\s*---$", first_line) else f"第 {index} 段"
        sections.append((label, body))
    return sections or [("正文", text.strip())]


def _split_long_section(label: str, body: str) -> list[tuple[str, str]]:
    clean = str(body or "").strip()
    if len(clean) <= _IMPORT_CHUNK_MAX_CHARS:
        return [(label, clean)] if clean else []
    out: list[tuple[str, str]] = []
    current: list[str] = []
    for paragraph in re.split(r"\n\s*\n", clean):
        part = paragraph.strip()
        if not part:
            continue
        while len(part) > _IMPORT_CHUNK_MAX_CHARS:
            head = part[:_IMPORT_CHUNK_MAX_CHARS].rstrip()
            if current:
                out.append((label, "\n\n".join(current).strip()))
                current = []
            out.append((label, head))
            part = part[_IMPORT_CHUNK_MAX_CHARS:].lstrip()
        candidate = "\n\n".join([*current, part]).strip()
        if current and len(candidate) > _IMPORT_CHUNK_MAX_CHARS:
            out.append((label, "\n\n".join(current).strip()))
            current = [part]
        else:
            current.append(part)
    if current:
        out.append((label, "\n\n".join(current).strip()))
    return out


def _split_import_chunks(text: str) -> list[dict]:
    clean = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not clean:
        return []
    if len(clean) <= _IMPORT_CHUNK_MAX_CHARS:
        return [{"label": "正文", "content": clean}]

    sections = _split_sections_by_headings(clean)
    if len(sections) <= 1:
        sections = _split_sections_by_pages(clean)

    pieces: list[tuple[str, str]] = []
    for label, body in sections:
        pieces.extend(_split_long_section(label, body))

    chunks: list[dict] = []
    current_parts: list[str] = []
    current_labels: list[str] = []
    for label, body in pieces:
        candidate = "\n\n".join([*current_parts, body]).strip()
        if current_parts and len(candidate) > _IMPORT_CHUNK_TARGET_CHARS:
            chunks.append({"label": _chunk_label(current_labels[0] if current_labels else "正文"), "content": "\n\n".join(current_parts).strip()})
            current_parts = [body]
            current_labels = [label]
        else:
            current_parts.append(body)
            if label and label not in current_labels:
                current_labels.append(label)
    if current_parts:
        chunks.append({"label": _chunk_label(current_labels[0] if current_labels else "正文"), "content": "\n\n".join(current_parts).strip()})

    if len(chunks) > _MAX_IMPORT_CHUNKS:
        chunks = chunks[:_MAX_IMPORT_CHUNKS]
        chunks[-1]["content"] = (
            str(chunks[-1].get("content") or "").rstrip()
            + "\n\n...[后续内容超过自动拆分上限，先保留前面重点段落]"
        )
    return [chunk for chunk in chunks if str(chunk.get("content") or "").strip()]


def _chunked_title(title: str, index: int, total: int, label: str) -> str:
    clean_title = str(title or "").strip() or "未命名资料"
    if total <= 1:
        return clean_title
    clean_label = _chunk_label(label, f"第 {index} 段")
    return f"{clean_title}（{index}/{total}：{clean_label}）"


def _decode_text_file(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _has_enough_import_text(parts: list[str]) -> bool:
    return sum(len(part) for part in parts) >= _MAX_EXTRACT_CHARS


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise RuntimeError("服务器缺少 pypdf，请先安装 requirements.txt") from exc

    reader = PdfReader(io.BytesIO(content))
    parts: list[str] = []
    for index, page in enumerate(reader.pages[:200], start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        page_text = page_text.strip()
        if page_text:
            parts.append(f"--- 第 {index} 页 ---\n{page_text}")
        if _has_enough_import_text(parts):
            break
    return "\n\n".join(parts)


def _extract_docx_text(content: bytes) -> str:
    try:
        from docx import Document
    except Exception as exc:
        raise RuntimeError("服务器缺少 python-docx，请先安装 requirements.txt") from exc

    doc = Document(io.BytesIO(content))
    parts: list[str] = []
    for paragraph in doc.paragraphs:
        if paragraph.text and paragraph.text.strip():
            parts.append(paragraph.text.strip())
        if _has_enough_import_text(parts):
            return "\n".join(parts)
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
            if _has_enough_import_text(parts):
                return "\n".join(parts)
    return "\n".join(parts)


def _extract_import_text(filename: str, content: bytes) -> tuple[str, str]:
    suffix = Path(filename or "").suffix.lower()
    if suffix in _TEXT_EXTS:
        return _clip_import_text(_decode_text_file(content)), "text"
    if suffix in _PDF_EXTS:
        return _clip_import_text(_extract_pdf_text(content)), "pdf"
    if suffix in _WORD_EXTS:
        return _clip_import_text(_extract_docx_text(content)), "word"
    raise ValueError("暂只支持 pdf、docx、txt、md")


def _with_auto_module(data: dict) -> dict:
    payload = dict(data or {})
    module_id = str(payload.get("module_id") or "").strip() or "inbox"
    if module_id == "inbox":
        payload["module_id"] = r2_store.guess_studyroom_module_id(
            payload.get("title"),
            payload.get("content"),
            payload.get("url"),
            payload.get("source_type"),
        )
    return payload


def register_routes(bp) -> None:
    @bp.route("/studyroom", methods=["GET"])
    def miniapp_studyroom_get():
        return jsonify({"ok": True, "data": r2_store.get_studyroom_data()})

    @bp.route("/studyroom/import", methods=["POST"])
    def miniapp_studyroom_import():
        if request.content_length and request.content_length > _MAX_IMPORT_BYTES:
            return jsonify({"ok": False, "error": "文件太大，先控制在 16MB 内"}), 413
        uploaded = request.files.get("file")
        if not uploaded:
            return jsonify({"ok": False, "error": "没有收到文件"}), 400
        filename = str(uploaded.filename or "资料").strip() or "资料"
        content = uploaded.read() or b""
        if not content:
            return jsonify({"ok": False, "error": "文件是空的"}), 400
        if len(content) > _MAX_IMPORT_BYTES:
            return jsonify({"ok": False, "error": "文件太大，先控制在 16MB 内"}), 413

        try:
            text, detected_source_type = _extract_import_text(filename, content)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 503
        except Exception as exc:
            return jsonify({"ok": False, "error": f"解析失败：{exc}"}), 400

        if not text:
            return jsonify({"ok": False, "error": "没有抽到文字；如果是扫描版 PDF/图片，需要 OCR，当前还没接。"}), 400

        title = str(request.form.get("title") or "").strip() or Path(filename).stem or "未命名资料"
        module_id = str(request.form.get("module_id") or "inbox").strip() or "inbox"
        requested_source_type = str(request.form.get("source_type") or "").strip()
        source_type = requested_source_type if requested_source_type in _SOURCE_TYPE_OVERRIDES else detected_source_type
        chunks = _split_import_chunks(text)
        created_items = []
        for index, chunk in enumerate(chunks, start=1):
            chunk_label = str(chunk.get("label") or "").strip()
            note = f"导入文件：{filename}"
            if len(chunks) > 1:
                note += f"\n自动拆分：第 {index}/{len(chunks)} 段 · {_chunk_label(chunk_label, f'第 {index} 段')}"
            item = r2_store.add_studyroom_item(
                _with_auto_module(
                    {
                        "title": _chunked_title(title, index, len(chunks), chunk_label),
                        "content": str(chunk.get("content") or "").strip(),
                        "module_id": module_id,
                        "source_type": source_type,
                        "status": "todo",
                        "note": note,
                    }
                )
            )
            if item:
                created_items.append(item)
        if not created_items:
            return jsonify({"ok": False, "error": "导入后保存失败"}), 500
        return jsonify(
            {
                "ok": True,
                "item": created_items[0],
                "items": created_items,
                "data": r2_store.get_studyroom_data(),
                "chars": len(text),
                "chunks": len(created_items),
            }
        )

    @bp.route("/studyroom/items", methods=["POST"])
    def miniapp_studyroom_add_item():
        data = request.get_json(silent=True) or {}
        item = r2_store.add_studyroom_item(_with_auto_module(data))
        if not item:
            return jsonify({"ok": False, "error": "资料内容不能为空"}), 400
        return jsonify({"ok": True, "item": item, "data": r2_store.get_studyroom_data()})

    @bp.route("/studyroom/items/<item_id>", methods=["PUT"])
    def miniapp_studyroom_update_item(item_id: str):
        data = request.get_json(silent=True) or {}
        item = r2_store.update_studyroom_item(item_id, data)
        if not item:
            return jsonify({"ok": False, "error": "未找到资料或内容无效"}), 404
        return jsonify({"ok": True, "item": item, "data": r2_store.get_studyroom_data()})

    @bp.route("/studyroom/items/<item_id>", methods=["DELETE"])
    def miniapp_studyroom_delete_item(item_id: str):
        ok = r2_store.delete_studyroom_item(item_id)
        if not ok:
            return jsonify({"ok": False, "error": "未找到资料"}), 404
        return jsonify({"ok": True, "data": r2_store.get_studyroom_data()})

    @bp.route("/studyroom/items/<item_id>/codex-sort", methods=["POST"])
    def miniapp_studyroom_codex_sort(item_id: str):
        data = r2_store.get_studyroom_data()
        items = data.get("items") or []
        item = next((x for x in items if str((x or {}).get("id") or "") == str(item_id or "")), None)
        if not item:
            return jsonify({"ok": False, "error": "未找到资料"}), 404
        modules = {str((m or {}).get("id") or ""): str((m or {}).get("label") or "") for m in data.get("modules") or []}
        content_parts = [
            str(item.get("content") or "").strip(),
            str(item.get("note") or "").strip(),
            str(item.get("url") or "").strip(),
        ]
        content = "\n\n".join([x for x in content_parts if x]).strip()
        if not content:
            return jsonify({"ok": False, "error": "这条资料没有可整理内容"}), 400
        task = codex_group_chat.create_task(
            {
                "mode": "studyroom",
                "window_id": "studyroom",
                "reply_target": "studyroom",
                "study_item_id": item_id,
                "study_title": item.get("title") or "",
                "study_module": modules.get(str(item.get("module_id") or ""), "待整理"),
                "study_source": item.get("source_type") or "",
                "study_url": item.get("url") or "",
                "user_message": content,
                "client_request_id": f"studyroom-{item_id}",
            }
        )
        if not task:
            return jsonify({"ok": False, "error": "创建整理任务失败"}), 500
        r2_store.update_studyroom_item(item_id, {"status": "sorting"})
        return jsonify({"ok": True, "task": task, "data": r2_store.get_studyroom_data()})

    @bp.route("/studyroom/items/<item_id>/auto-module", methods=["POST"])
    def miniapp_studyroom_auto_module(item_id: str):
        data = r2_store.get_studyroom_data()
        items = data.get("items") or []
        item = next((x for x in items if str((x or {}).get("id") or "") == str(item_id or "")), None)
        if not item:
            return jsonify({"ok": False, "error": "未找到资料"}), 404
        module_id = r2_store.guess_studyroom_module_id(
            item.get("title"),
            item.get("content"),
            item.get("url"),
            item.get("source_type"),
        )
        updated = r2_store.update_studyroom_item(item_id, {"module_id": module_id})
        if not updated:
            return jsonify({"ok": False, "error": "自动归类失败"}), 500
        return jsonify({"ok": True, "item": updated, "module_id": module_id, "data": r2_store.get_studyroom_data()})

    @bp.route("/studyroom/study-logs", methods=["POST"])
    def miniapp_studyroom_add_study_log():
        data = request.get_json(silent=True) or {}
        entry = r2_store.add_studyroom_log(str(data.get("content") or ""))
        if not entry:
            return jsonify({"ok": False, "error": "学习记录不能为空"}), 400
        return jsonify({"ok": True, "entry": entry, "data": r2_store.get_studyroom_data()})
