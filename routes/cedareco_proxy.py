from __future__ import annotations

from urllib.parse import quote

import requests
from flask import Blueprint, Response, request

from services.cedareco_bridge import CEDARECO_UPSTREAM_URL, is_valid_human_key


bp = Blueprint("cedareco_proxy", __name__)

_PASSTHROUGH_HEADERS = (
    "Content-Type",
    "Cache-Control",
    "Pragma",
    "Expires",
    "Access-Control-Allow-Origin",
    "Access-Control-Allow-Headers",
    "Access-Control-Allow-Methods",
    "Vary",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Content-Security-Policy",
)


def _upstream_path(subpath: str, method: str) -> str | None:
    if not subpath:
        return "/" if method == "GET" else None
    parts = subpath.split("/")
    if any(not part or part in {".", ".."} or "\\" in part for part in parts):
        return None
    if subpath in {"app.js", "style.css"}:
        return f"/{subpath}" if method == "GET" else None
    if subpath.startswith("assets/"):
        encoded = "/".join(quote(part, safe="") for part in parts[1:])
        return f"/assets/{encoded}" if method == "GET" else None
    if subpath.startswith("api/"):
        encoded = "/".join(quote(part, safe="") for part in parts[1:])
        return f"/api/{encoded}" if method in {"GET", "POST"} else None
    return None


@bp.route("/cedareco/ui/<human_key>/", defaults={"subpath": ""}, methods=["GET", "POST"])
@bp.route("/cedareco/ui/<human_key>/<path:subpath>", methods=["GET", "POST"])
def cedareco_ui_proxy(human_key: str, subpath: str):
    upstream_path = _upstream_path(subpath, request.method)
    if not is_valid_human_key(human_key) or upstream_path is None:
        return Response(
            "瓶中生态观察窗无效。",
            status=404,
            content_type="text/plain; charset=utf-8",
        )

    headers = {}
    if request.content_type:
        headers["Content-Type"] = request.content_type
    try:
        upstream = requests.request(
            method=request.method,
            url=f"{CEDARECO_UPSTREAM_URL}{upstream_path}",
            params=list(request.args.items(multi=True)),
            data=request.get_data(cache=False),
            headers=headers,
            allow_redirects=False,
            timeout=30,
        )
    except requests.RequestException:
        return Response(
            "瓶中生态服务还没启动。",
            status=503,
            content_type="text/plain; charset=utf-8",
        )

    response = Response(upstream.content, status=upstream.status_code)
    for name in _PASSTHROUGH_HEADERS:
        value = upstream.headers.get(name)
        if value:
            response.headers[name] = value
    return response
