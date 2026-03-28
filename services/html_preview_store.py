"""
HTML 临时预览：内存存储与创建逻辑。供 HTTP 路由与 publish_html_preview 工具共用。
"""
from __future__ import annotations

import secrets
import threading
import time
from typing import Any, Optional, Tuple, Union
from urllib.parse import urlparse

from config import (
    GATEWAY_PUBLIC_BASE_URL,
    HTML_PREVIEW_MAX_BYTES,
    HTML_PREVIEW_MAX_ITEMS,
    HTML_PREVIEW_PUBLIC_BASE_URL,
    HTML_PREVIEW_TTL_SECONDS,
    TELEGRAM_GATEWAY_URL,
)

_lock = threading.Lock()
# token -> {"html": str, "exp": float, "created": float}
_store: dict[str, dict[str, Any]] = {}


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


def _is_loopback_base(url: str) -> bool:
    """本机地址不可给手机打开，预览链接一律不用。"""
    u = (url or "").strip()
    if not u:
        return True
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        host = (urlparse(u).hostname or "").lower()
    except Exception:
        return True
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    if host.startswith("127."):
        return True
    return False


def resolve_preview_base_url() -> str:
    """
    工具 publish_html_preview 拼链接：只认公网配置或非本机的 TELEGRAM_GATEWAY_URL。
    """
    for raw in (HTML_PREVIEW_PUBLIC_BASE_URL, GATEWAY_PUBLIC_BASE_URL, TELEGRAM_GATEWAY_URL):
        base = (raw or "").strip().rstrip("/")
        if base and not _is_loopback_base(base):
            return base
    return ""


def resolve_preview_base_url_for_http_request(request_url_root: str) -> str:
    """
    HTTP POST /html-preview/：优先环境变量；仅当请求 Host 本身不是本机时，才用 request.url_root。
    """
    u = resolve_preview_base_url()
    if u:
        return u
    root = (request_url_root or "").strip().rstrip("/")
    if root and not _is_loopback_base(root):
        return root
    return ""


def preview_url_for_token(token: str, base_override: Optional[str] = None) -> str:
    base = (base_override or resolve_preview_base_url()).strip().rstrip("/")
    return f"{base}/html-preview/v/{token}"


def create_preview(html: str, url_base: Optional[str] = None) -> Tuple[bool, Union[dict, str]]:
    """
    写入一条预览。url_base 由调用方传入时用于拼链接（HTTP 层传 resolve_preview_base_url_for_http_request 的结果）。
    返回 (True, {"url","token","expires_in"}) 或 (False, 错误说明)。
    """
    if html is None or (isinstance(html, str) and not html.strip()):
        return False, "内容为空"
    if not isinstance(html, str):
        return False, "html 须为字符串"
    encoded = html.encode("utf-8")
    if len(encoded) > HTML_PREVIEW_MAX_BYTES:
        return False, f"HTML 超过上限 {HTML_PREVIEW_MAX_BYTES} 字节"

    token = secrets.token_urlsafe(32)
    now = time.time()
    exp = now + HTML_PREVIEW_TTL_SECONDS

    with _lock:
        _purge_expired()
        _store[token] = {"html": html, "exp": exp, "created": now}
        _trim_to_max()

    base = (url_base or "").strip().rstrip("/") if url_base else resolve_preview_base_url()
    if not base:
        return (
            False,
            "未配置公网域名：请在 .env 设置 GATEWAY_PUBLIC_BASE_URL 或 HTML_PREVIEW_PUBLIC_BASE_URL（https://你的域名，勿用 127.0.0.1）；"
            "Bot 可继续用 TELEGRAM_GATEWAY_URL=http://127.0.0.1:5000 调本机。",
        )

    return True, {
        "url": preview_url_for_token(token, base),
        "token": token,
        "expires_in": HTML_PREVIEW_TTL_SECONDS,
    }


def get_preview_row(token: str) -> Optional[dict[str, Any]]:
    """取未过期条目；过期或不存在返回 None。"""
    if not token or len(token) > 200:
        return None
    with _lock:
        _purge_expired()
        row = _store.get(token)
    if not row or row["exp"] <= time.time():
        return None
    return row
