from __future__ import annotations

from flask import Blueprint, Response

from storage import du_pages_store


bp = Blueprint("du_pages", __name__, url_prefix="/du-pages")


@bp.route("/v/<page_id>", methods=["GET"])
def view_du_page(page_id: str):
    item = du_pages_store.get_page(page_id, include_html=True, include_deleted=False)
    if not item:
        return Response(
            "<!doctype html><meta charset='utf-8'><title>页笺不存在</title><body>页笺不存在或已被删除。</body>",
            status=404,
            content_type="text/html; charset=utf-8",
        )
    resp = Response(str(item.get("html") or ""), content_type="text/html; charset=utf-8")
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self' data: blob:; "
        "img-src 'self' data: blob: https: http:; "
        "style-src 'self' 'unsafe-inline' https: http:; "
        "font-src 'self' data: https: http:; "
        "script-src 'unsafe-inline' 'unsafe-eval'; "
        "connect-src 'none'; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "frame-ancestors 'self'"
    )
    return resp
