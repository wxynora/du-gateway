"""
KOReader 划词/注释 webhook：与 co_read_api 相同，内部 HTTP 调 /v1/chat/completions。
"""

import uuid
from typing import Any

import requests
from flask import Blueprint, jsonify, request

bp = Blueprint("koreader_api", __name__, url_prefix="/api")


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


def _build_user_message(body: dict[str, Any]) -> str:
    book = body.get("book") if isinstance(body.get("book"), dict) else {}
    title = str((book or {}).get("title") or "").strip()
    author = str((book or {}).get("author") or "").strip()
    chapter = str((book or {}).get("chapter") or "").strip()
    progress = (book or {}).get("progress")
    try:
        progress_n = int(progress) if progress is not None else None
    except (TypeError, ValueError):
        progress_n = None
    highlight = str(body.get("highlight") or "").strip()
    note = str(body.get("note") or "")
    ts = str(body.get("timestamp") or "").strip()

    lines = ["[KOREADER]", f"BookTitle: {title}"]
    if author:
        lines.append(f"Author: {author}")
    if chapter:
        lines.append(f"Chapter: {chapter}")
    if progress_n is not None:
        lines.append(f"Progress: {progress_n}%")
    if ts:
        lines.append(f"Timestamp: {ts}")
    lines.append("Highlight:")
    lines.append(highlight or "")
    lines.append("Note:")
    lines.append(note)
    lines.append("[/KOREADER]")
    lines.append("读者刚在书里划了线并写了感想（Note 可能为空）。用简短、有临场感的话回应即可。")
    return "\n".join(lines)


@bp.route("/koreader", methods=["POST", "OPTIONS"])
def koreader_highlight():
    if request.method == "OPTIONS":
        return "", 204

    if not request.is_json:
        return jsonify({"ok": False, "error": "需要 application/json"}), 400
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON 无效"}), 400

    window_id = str(request.headers.get("X-Window-Id") or "").strip()
    highlight = str(body.get("highlight") or "").strip()
    if not highlight:
        return jsonify({"ok": False, "error": "缺少 highlight"}), 400
    if len(highlight) > 50000:
        body = dict(body)
        body["highlight"] = highlight[:50000] + "…"

    user_prompt = _build_user_message(body)
    host_root = (request.url_root or "").rstrip("/")
    chat_url = host_root + "/v1/chat/completions"

    chat_body = {
        "stream": False,
        "window_id": window_id,
        "messages": [{"role": "user", "content": user_prompt}],
    }

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
    return jsonify(
        {
            "ok": True,
            "event_id": str(uuid.uuid4()),
            "window_id": window_id,
            "du_reply": du_reply,
        }
    ), 200
