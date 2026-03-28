"""
临时 HTML 预览：POST 上传、GET 按 token 查看。独立 Blueprint，不参与聊天主链路。
"""
from __future__ import annotations

from typing import Optional

from flask import Blueprint, Response, jsonify, request

from config import HTML_PREVIEW_SECRET
from services.html_preview_store import (
    create_preview,
    get_preview_row,
    resolve_preview_base_url_for_http_request,
)

bp = Blueprint("html_preview", __name__, url_prefix="/html-preview")


def _extract_bearer_or_key() -> Optional[str]:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("X-HTML-Preview-Key") or "").strip() or None


@bp.route("/", methods=["POST"])
def create_preview_http():
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
    base = resolve_preview_base_url_for_http_request(request.url_root or "")
    ok, payload = create_preview(html, url_base=base)
    if not ok:
        msg = str(payload)
        if "超过上限" in msg:
            return jsonify({"ok": False, "error": msg}), 413
        if msg == "内容为空":
            return jsonify({"ok": False, "error": msg}), 400
        if "未配置公网域名" in msg:
            return jsonify({"ok": False, "error": msg}), 503
        return jsonify({"ok": False, "error": msg}), 400

    data = payload  # ok 时为 dict
    return jsonify(
        {
            "ok": True,
            "url": data["url"],
            "token": data["token"],
            "expires_in": data["expires_in"],
        }
    )


@bp.route("/v/<token>", methods=["GET"])
def get_preview(token: str):
    """按 token 返回 HTML（无额外鉴权；token 需保密）。"""
    row = get_preview_row(token)
    if not row:
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
