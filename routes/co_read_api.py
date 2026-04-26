import uuid
from typing import Any

import requests
from flask import Blueprint, jsonify, request

bp = Blueprint("co_read_api", __name__, url_prefix="/api/co-read")


def _build_co_read_user_message(book_title: str, chapter_label: str, snippet: str, user_note: str) -> str:
    msg = "[CO-READ]\n"
    msg += f"Book: {book_title or ''}\n"
    if chapter_label:
        msg += f"Chapter: {chapter_label}\n"
    msg += "Snippet:\n" + (snippet or "") + "\n"
    if user_note:
        msg += "UserNote:\n" + user_note + "\n"
    msg += "[/CO-READ]\n"
    msg += "回应这段共读内容即可。"
    return msg


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


def _resolve_active_model() -> tuple[str, str]:
    try:
        from storage.upstream_store import get_cached_active_model

        model = str(get_cached_active_model(refresh_if_missing=True) or "").strip()
        return model, ""
    except Exception as e:
        return "", str(e)


@bp.route("/session", methods=["POST", "OPTIONS"])
def co_read_session():
    if request.method == "OPTIONS":
        return "", 204

    if not request.is_json:
        return jsonify({"ok": False, "error": "需要 application/json"}), 400
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON 无效"}), 400

    window_id = str(body.get("window_id") or request.headers.get("X-Window-Id") or "").strip()
    book_title = str(body.get("book_title") or "").strip()
    chapter_label = str(body.get("chapter_label") or "").strip()
    snippet = str(body.get("snippet") or "").strip()
    user_note = str(body.get("user_note") or "").strip()

    if not snippet:
        return jsonify({"ok": False, "error": "缺少 snippet"}), 400

    # 防止超长 payload 把上游/自身请求搞爆
    if len(snippet) > 50000:
        snippet = snippet[:50000] + "…"

    user_prompt = _build_co_read_user_message(book_title, chapter_label, snippet, user_note)
    model, model_err = _resolve_active_model()
    if not model:
        msg = "缺少当前可用模型"
        if model_err:
            msg += f": {model_err}"
        return jsonify({"ok": False, "error": msg}), 502

    # 复用现有聊天管道：注入总结/动态层、存档到 R2、再把渡回复返回给插件。
    # 这里走同一进程的“HTTP 内部调用”，避免复制 chat.py 的管道逻辑。
    host_root = (request.url_root or "").rstrip("/")
    chat_url = host_root + "/v1/chat/completions"

    chat_body = {
        "model": model,
        "stream": False,
        "window_id": window_id,
        "messages": [
            {
                "role": "user",
                "content": user_prompt,
            }
        ],
    }

    # timeout：上游平均 10~30s，给足一点以满足插件“约 60s 内返回”的体验目标
    try:
        r = requests.post(
            chat_url,
            json=chat_body,
            headers={"Content-Type": "application/json", "X-Window-Id": window_id},
            timeout=75,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"转发到 /v1/chat/completions 失败: {e}"}), 502

    try:
        resp_json = r.json() if r.content else {}
    except Exception:
        resp_json = {}

    if r.status_code >= 400:
        return jsonify({"ok": False, "error": "upstream error", "status_code": r.status_code, "resp": resp_json}), r.status_code

    du_reply = _extract_assistant_content(resp_json)
    session_id = str(uuid.uuid4())
    return jsonify(
        {
            "ok": True,
            "session_id": session_id,
            "window_id": window_id,
            "du_reply": du_reply,
        }
    ), 200


@bp.route("/sessions", methods=["GET"])
def co_read_sessions():
    # P1：未来可以从 R2 reading/events 之类读取；当前先兜底，保证插件能跑通。
    return jsonify({"ok": True, "sessions": [], "count": 0})


@bp.route("/books/<book_key>/card", methods=["GET"])
def co_read_book_card(book_key: str):
    # P1：未来可从动态层里按书检索并返回粗记忆卡；当前先兜底。
    return jsonify({"ok": True, "book_key": book_key, "card": None})

