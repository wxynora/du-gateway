from __future__ import annotations

from urllib.parse import urlparse

from config import GATEWAY_PUBLIC_BASE_URL, TELEGRAM_GATEWAY_URL


def _is_loopback_base(url: str) -> bool:
    raw = (url or "").strip()
    if not raw:
        return True
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    try:
        host = (urlparse(raw).hostname or "").lower()
    except Exception:
        return True
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    return host.startswith("127.")


def resolve_public_base_url() -> str:
    for raw in (GATEWAY_PUBLIC_BASE_URL, TELEGRAM_GATEWAY_URL):
        base = (raw or "").strip().rstrip("/")
        if base and not _is_loopback_base(base):
            return base
    return ""


def resolve_public_base_url_for_http_request(request_url_root: str) -> str:
    base = resolve_public_base_url()
    if base:
        return base
    root = (request_url_root or "").strip().rstrip("/")
    if root and not _is_loopback_base(root):
        return root
    return ""
