from __future__ import annotations

import io
from pathlib import Path

from flask import jsonify, request

from services import codex_group_chat
from storage import r2_store


_MAX_IMPORT_BYTES = 16 * 1024 * 1024
_MAX_EXTRACT_CHARS = 20000
_TEXT_EXTS = {".txt", ".md", ".markdown"}
_PDF_EXTS = {".pdf"}
_WORD_EXTS = {".docx"}


def _clip_import_text(text: str) -> str:
    clean = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(clean) <= _MAX_EXTRACT_CHARS:
        return clean
    return clean[:_MAX_EXTRACT_CHARS].rstrip() + "\n\n...[导入时已截断，原文件仍可重新拆分导入]"


def _decode_text_file(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


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
    return "\n\n".join(parts)


def _extract_docx_text(content: bytes) -> str:
    try:
        from docx import Document
    except Exception as exc:
        raise RuntimeError("服务器缺少 python-docx，请先安装 requirements.txt") from exc

    doc = Document(io.BytesIO(content))
    parts: list[str] = []
    parts.extend(p.text.strip() for p in doc.paragraphs if p.text and p.text.strip())
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
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
            text, source_type = _extract_import_text(filename, content)
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
        item = r2_store.add_studyroom_item(
            {
                "title": title,
                "content": text,
                "module_id": module_id,
                "source_type": source_type,
                "status": "todo",
                "note": f"导入文件：{filename}",
            }
        )
        if not item:
            return jsonify({"ok": False, "error": "导入后保存失败"}), 500
        return jsonify({"ok": True, "item": item, "data": r2_store.get_studyroom_data(), "chars": len(text)})

    @bp.route("/studyroom/items", methods=["POST"])
    def miniapp_studyroom_add_item():
        data = request.get_json(silent=True) or {}
        item = r2_store.add_studyroom_item(data)
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

    @bp.route("/studyroom/study-logs", methods=["POST"])
    def miniapp_studyroom_add_study_log():
        data = request.get_json(silent=True) or {}
        entry = r2_store.add_studyroom_log(str(data.get("content") or ""))
        if not entry:
            return jsonify({"ok": False, "error": "学习记录不能为空"}), 400
        return jsonify({"ok": True, "entry": entry, "data": r2_store.get_studyroom_data()})
