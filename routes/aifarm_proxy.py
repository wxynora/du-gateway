from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

import requests
from flask import Blueprint, Response, request

from services.aifarm_bridge import AIFARM_UPSTREAM_URL


bp = Blueprint("aifarm_proxy", __name__)

_HUMAN_KEY_RE = re.compile(r"^[a-fA-F0-9]{32}$")
_PASSTHROUGH_HEADERS = ("Content-Type", "Cache-Control", "Pragma", "Expires", "X-Robots-Tag")
_POST_ACTIONS = {
    "harvest": {""},
    "title": {""},
    "cooking": {"buy-ingredient", "buy-recipe", "cook", "use", "sell"},
    "ranch": {
        "collect", "feed", "remit", "dress", "decorate", "wear", "takeoff", "place", "unplace",
        "upgrade", "name-animal", "name-pet", "name-goose", "pin", "dispatch-raid", "catch-raid",
    },
    "ta": {"names", "welcome", "design", "message", "craft", "social"},
    "expedition": {"roll", "charm"},
    "codex": {"star"},
}
_GET_SECTIONS = {"", "ranch", "ta", "expedition", "codex", "leaderboard", "messages", "cooking"}
_UPSTREAM_PARSED_URL = urlparse(AIFARM_UPSTREAM_URL)
_UPSTREAM_BASE_PATH = _UPSTREAM_PARSED_URL.path.rstrip("/")
_UPSTREAM_UI_PREFIXES = tuple(dict.fromkeys((f"{_UPSTREAM_BASE_PATH}/ui/", "/ui/")))
_UPSTREAM_ORIGIN = (
    _UPSTREAM_PARSED_URL.scheme.lower(),
    (_UPSTREAM_PARSED_URL.hostname or "").lower(),
    _UPSTREAM_PARSED_URL.port or (443 if _UPSTREAM_PARSED_URL.scheme.lower() == "https" else 80),
)


def _rewrite_html(body: bytes) -> bytes:
    text = body.decode("utf-8", errors="replace")
    for prefix in _UPSTREAM_UI_PREFIXES:
        text = text.replace(f'="{prefix}', '="/aifarm/ui/')
        text = text.replace(f"='{prefix}", "='/aifarm/ui/")
    return text.encode("utf-8")


def _rewrite_location(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        try:
            origin = (
                parsed.scheme.lower(),
                (parsed.hostname or "").lower(),
                parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
            )
        except ValueError:
            return value
        if origin != _UPSTREAM_ORIGIN:
            return value
        for prefix in _UPSTREAM_UI_PREFIXES:
            if parsed.path.startswith(prefix):
                path = "/aifarm/ui/" + parsed.path[len(prefix):]
                return urlunparse(("", "", path, parsed.params, parsed.query, parsed.fragment))
        return value

    for prefix in _UPSTREAM_UI_PREFIXES:
        if value.startswith(prefix):
            return "/aifarm/ui/" + value[len(prefix):]
    return value


def _allowed_ui_path(subpath: str, method: str) -> bool:
    if not subpath:
        return method == "GET"
    parts = subpath.split("/")
    if any(not part or part in {".", ".."} or "\\" in part for part in parts):
        return False
    section = parts[0]
    action = parts[1] if len(parts) == 2 else ""
    if len(parts) > 2:
        return False
    if method == "GET":
        if section == "ta" and action.startswith("link-"):
            return action[5:] in {"design", "message", "craft", "visit"}
        return section in _GET_SECTIONS and not action
    return action in _POST_ACTIONS.get(section, set())


@bp.route("/aifarm/ui/<human_key>", defaults={"subpath": ""}, methods=["GET", "POST"])
@bp.route("/aifarm/ui/<human_key>/<path:subpath>", methods=["GET", "POST"])
def aifarm_ui_proxy(human_key: str, subpath: str):
    if not _HUMAN_KEY_RE.fullmatch(human_key) or not _allowed_ui_path(subpath, request.method):
        return Response("AI 农场入口无效。", status=404, content_type="text/plain; charset=utf-8")

    suffix = f"/{subpath}" if subpath else ""
    upstream_url = f"{AIFARM_UPSTREAM_URL}/ui/{human_key}{suffix}"
    headers = {}
    if request.content_type:
        headers["Content-Type"] = request.content_type
    try:
        upstream = requests.request(
            method=request.method,
            url=upstream_url,
            params=list(request.args.items(multi=True)),
            data=request.get_data(cache=False),
            headers=headers,
            allow_redirects=False,
            timeout=15,
        )
    except requests.RequestException:
        return Response(
            "AI 农场服务还没启动。",
            status=503,
            content_type="text/plain; charset=utf-8",
        )

    body = upstream.content
    content_type = upstream.headers.get("Content-Type", "")
    if "text/html" in content_type.lower():
        body = _rewrite_html(body)

    response = Response(body, status=upstream.status_code)
    for name in _PASSTHROUGH_HEADERS:
        value = upstream.headers.get(name)
        if value:
            response.headers[name] = value
    location = upstream.headers.get("Location")
    if location:
        response.headers["Location"] = _rewrite_location(location)
    return response
