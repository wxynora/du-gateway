import json
import hashlib
import re
import uuid
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
    focus = card.get("xinyue_focus") if isinstance(card.get("xinyue_focus"), list) else []
    questions = card.get("open_questions") if isinstance(card.get("open_questions"), list) else []
    understanding = _compact_text(card.get("du_understanding"), 360)
    lines = ["[CO-READ CARD]"]
    if title:
        lines.append(f"书名：{title}")
    if progress:
        lines.append(f"当前进度：{progress}")
    if recent:
        lines.append("最近共读：")
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
