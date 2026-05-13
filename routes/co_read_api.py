import json
import uuid
import threading
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from services.co_read_flow import (
    CO_READ_DU_VOICE_SYSTEM,
    _book_key_from_title,
    _build_card_system_context,
    _build_co_read_user_message,
    _build_section_complete_user_message,
    _co_read_book_summary_response,
    _compact_mark_lines,
    _extract_co_read_result,
    _find_section,
    _section_label,
    _section_text,
)
from services.co_read_books import (
    _normalize_marks_for_section,
    _replace_book_section,
    _save_co_read_book_from_content,
)
from storage import r2_store, upstream_store

bp = Blueprint("co_read_api", __name__, url_prefix="/api/co-read")


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


def _body_flag(body: dict, key: str, default: bool) -> bool:
    raw = body.get(key, request.args.get(key))
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _update_co_read_card_for_section(saved: dict, section_index: int, text: str) -> tuple[dict | None, str]:
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
            user_note=saved["sections"][section_index].get("user_section_note") or _compact_mark_lines(saved["sections"][section_index].get("user_marks") or [], ""),
            du_reply=saved["sections"][section_index].get("du_section_note") or "",
        )
    return next_card, card_update_error


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
    payload = {
        "ok": True,
        "section": saved["sections"][section_index],
        "book_summary": _co_read_book_summary_response(saved),
    }
    if _body_flag(body, "include_book", True):
        payload["book"] = saved
    return jsonify(payload)


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
    messages.append({"role": "system", "content": CO_READ_DU_VOICE_SYSTEM})
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
    defer_card_update = _body_flag(body, "defer_card_update", False)
    if defer_card_update:
        app = current_app._get_current_object()

        def _run_card_update():
            with app.app_context():
                _update_co_read_card_for_section(saved, section_index, text)

        threading.Thread(target=_run_card_update, name="co-read-card-update", daemon=True).start()
    else:
        next_card, card_update_error = _update_co_read_card_for_section(saved, section_index, text)

    payload = {
        "ok": True,
        "section": saved["sections"][section_index],
        "book_summary": _co_read_book_summary_response(saved),
        "du_marks": section.get("du_marks") or [],
        "du_section_note": section.get("du_section_note") or "",
        "raw_reply": raw_reply,
        "card_update_pending": defer_card_update,
        "card_update_error": card_update_error,
    }
    if next_card is not None:
        payload["card"] = next_card
    if _body_flag(body, "include_book", True):
        payload["book"] = saved
    return jsonify(payload)


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
