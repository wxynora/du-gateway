"""
临时 HTML 预览：POST 上传、GET 按 token 查看。独立 Blueprint，不参与聊天主链路。
"""
from __future__ import annotations

import secrets
import threading
import time
from typing import Optional

from flask import Blueprint, Response, jsonify, request

from config import (
    HTML_PREVIEW_MAX_BYTES,
    HTML_PREVIEW_MAX_ITEMS,
    HTML_PREVIEW_PUBLIC_BASE_URL,
    HTML_PREVIEW_SECRET,
    HTML_PREVIEW_TTL_SECONDS,
)

bp = Blueprint("html_preview", __name__, url_prefix="/html-preview")

_lock = threading.Lock()
# token -> {"html": str, "exp": float, "created": float}
_store: dict[str, dict] = {}


def _purge_expired() -> None:
    now = time.time()
    dead = [t for t, v in _store.items() if v["exp"] <= now]
    for t in dead:
        del _store[t]


def _trim_to_max() -> None:
    if len(_store) <= HTML_PREVIEW_MAX_ITEMS:
        return
    order = sorted(_store.keys(), key=lambda t: _store[t]["created"])
    while len(_store) > HTML_PREVIEW_MAX_ITEMS and order:
        del _store[order.pop(0)]


def _extract_bearer_or_key() -> Optional[str]:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("X-HTML-Preview-Key") or "").strip() or None


def _preview_url(token: str) -> str:
    base = HTML_PREVIEW_PUBLIC_BASE_URL or (request.url_root or "").rstrip("/")
    return f"{base}/html-preview/v/{token}"


@bp.route("/", methods=["POST"])
def create_preview():
    """存一段 HTML，返回带 token 的预览 URL（需密钥）。"""
    if not HTML_PREVIEW_SECRET:
        return jsonify({"ok": False, "error": "HTML_PREVIEW_SECRET 未配置"}), 503
    key = _extract_bearer_or_key()
    if not key or key != HTML_PREVIEW_SECRET:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    html: Optional[str] = None
    ct = (request.content_type or "").split(";")[0].strip().lower()
    if ct == "application/json":
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"ok": False, "error": "需要 JSON 对象，含 html 字段"}), 400
        raw = body.get("html")
        if raw is None:
            return jsonify({"ok": False, "error": "缺少 html 字段"}), 400
        if not isinstance(raw, str):
            return jsonify({"ok": False, "error": "html 须为字符串"}), 400
        html = raw
    elif ct in ("text/html", "text/plain"):
        # text/plain 也收，方便 curl -d @file
        html = request.get_data(as_text=True)
    else:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Content-Type 须为 application/json 或 text/html",
                }
            ),
            415,
        )

    if html is None:
        return jsonify({"ok": False, "error": "空内容"}), 400
    encoded = html.encode("utf-8")
    if len(encoded) > HTML_PREVIEW_MAX_BYTES:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": f"HTML 超过上限 {HTML_PREVIEW_MAX_BYTES} 字节",
                }
            ),
            413,
        )

    token = secrets.token_urlsafe(32)
    now = time.time()
    exp = now + HTML_PREVIEW_TTL_SECONDS

    with _lock:
        _purge_expired()
        _store[token] = {"html": html, "exp": exp, "created": now}
        _trim_to_max()

    return jsonify(
        {
            "ok": True,
            "url": _preview_url(token),
            "token": token,
            "expires_in": HTML_PREVIEW_TTL_SECONDS,
        }
    )


@bp.route("/v/<token>", methods=["GET"])
def get_preview(token: str):
    """按 token 返回 HTML（无额外鉴权；token 需保密）。"""
    if not token or len(token) > 200:
        return Response("Not Found", status=404, mimetype="text/plain; charset=utf-8")

    with _lock:
        _purge_expired()
        row = _store.get(token)

    if not row or row["exp"] <= time.time():
        return Response(
            "<!DOCTYPE html><html><head><meta charset=utf-8><title>预览失效</title></head>"
            "<body><p>链接已过期或无效。</p></body></html>",
            status=404,
            mimetype="text/html; charset=utf-8",
        )

    return Response(
        row["html"],
        status=200,
        mimetype="text/html; charset=utf-8",
    )
