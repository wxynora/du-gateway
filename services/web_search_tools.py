import json
import re
import time
from html.parser import HTMLParser
from typing import Any

import requests

from config import (
    TAVILY_API_KEY,
    TAVILY_SEARCH_ENDPOINT,
    WEBSEARCH_FETCH_ENABLED,
    WEBSEARCH_FETCH_TOP_K,
    WEBSEARCH_MAX_PAGE_CHARS,
    WEBSEARCH_MAX_RESULTS,
    WEBSEARCH_PROVIDER_ORDER,
    WEBSEARCH_TIMEOUT_SECONDS,
)
from utils.log import get_logger

logger = get_logger(__name__)


TOOL_WEB_SEARCH = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "联网搜索最新公开信息（Tavily）。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "max_results": {"type": "integer", "description": "最多返回条数（默认 5，最大 10）"},
            },
            "required": ["query"],
        },
    },
}


def get_web_search_tools_for_inject() -> list[dict]:
    return [TOOL_WEB_SEARCH]


def _normalize_max_results(raw: Any) -> int:
    try:
        v = int(raw) if raw is not None else int(WEBSEARCH_MAX_RESULTS)
    except Exception:
        v = int(WEBSEARCH_MAX_RESULTS)
    return max(1, min(v, 10))


def _search_tavily(query: str, max_results: int, timeout_seconds: int) -> tuple[list[dict], str]:
    if not TAVILY_API_KEY:
        return [], "missing_key"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
    }
    r = requests.post(TAVILY_SEARCH_ENDPOINT, json=payload, timeout=timeout_seconds)
    if r.status_code >= 400:
        return [], f"http_{r.status_code}"
    data = r.json() if r.content else {}
    rows = data.get("results") or []
    items = []
    for it in rows[:max_results]:
        items.append(
            {
                "title": str(it.get("title") or "").strip(),
                "url": str(it.get("url") or "").strip(),
                "snippet": str(it.get("content") or it.get("snippet") or "").strip(),
                "source": "tavily",
                "published_at": str(it.get("published_date") or "").strip(),
            }
        )
    return items, ""


class _SimpleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []
        self._title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        t = (tag or "").lower()
        if t in ("script", "style", "noscript"):
            self._skip_depth += 1
        elif t == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        t = (tag or "").lower()
        if t in ("script", "style", "noscript") and self._skip_depth > 0:
            self._skip_depth -= 1
        elif t == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = (data or "").strip()
        if not text:
            return
        if self._in_title:
            self._title_parts.append(text)
        self._parts.append(text)

    def title(self) -> str:
        return " ".join(self._title_parts).strip()

    def text(self) -> str:
        merged = " ".join(self._parts).strip()
        merged = re.sub(r"\s+", " ", merged)
        return merged


def _fetch_page(url: str, timeout_seconds: int) -> dict:
    page = {
        "url": url,
        "title": "",
        "content": "",
        "status": "error",
        "is_truncated": False,
        "content_chars": 0,
        "original_chars": 0,
    }
    if not url:
        page["status"] = "error"
        return page
    try:
        resp = requests.get(
            url,
            timeout=timeout_seconds,
            headers={"User-Agent": "du-gateway-websearch/1.0"},
        )
        if resp.status_code in (401, 403, 429):
            page["status"] = "blocked"
            return page
        if resp.status_code >= 400:
            page["status"] = "error"
            return page

        html = resp.text or ""
        parser = _SimpleTextExtractor()
        parser.feed(html)
        title = parser.title()
        text = parser.text()
        max_chars = max(1000, int(WEBSEARCH_MAX_PAGE_CHARS))
        original_chars = len(text)
        truncated = original_chars > max_chars
        content = text[:max_chars] if truncated else text

        page["title"] = title
        page["content"] = content
        page["original_chars"] = original_chars
        page["content_chars"] = len(content)
        page["is_truncated"] = truncated
        page["status"] = "truncated" if truncated else "ok"
        return page
    except requests.Timeout:
        page["status"] = "timeout"
        return page
    except Exception as e:
        logger.warning("web_search fetch failed url=%s err=%s", url[:120], e)
        page["status"] = "error"
        return page


def _build_fetched_pages(items: list[dict], timeout_seconds: int) -> list[dict]:
    if not WEBSEARCH_FETCH_ENABLED:
        return []
    top_k = max(0, min(int(WEBSEARCH_FETCH_TOP_K), 5))
    if top_k <= 0:
        return []
    pages: list[dict] = []
    for it in items[:top_k]:
        url = str((it or {}).get("url") or "").strip()
        if not url:
            continue
        pages.append(_fetch_page(url, timeout_seconds))
    return pages


def execute_web_search(arguments: dict) -> str:
    query = str((arguments or {}).get("query") or "").strip()
    if not query:
        return json.dumps({"ok": False, "error": "query 不能为空"}, ensure_ascii=False)

    max_results = _normalize_max_results((arguments or {}).get("max_results"))
    timeout_seconds = max(2, int(WEBSEARCH_TIMEOUT_SECONDS))

    started = time.time()
    tried: list[str] = []
    last_error = ""
    providers = WEBSEARCH_PROVIDER_ORDER or ["tavily"]

    for p in providers:
        provider = (p or "").strip().lower()
        if provider != "tavily":
            continue
        tried.append(provider)
        try:
            items, err = _search_tavily(query, max_results, timeout_seconds)
            if err:
                last_error = f"{provider}:{err}"
                continue
            fetched_pages = _build_fetched_pages(items, timeout_seconds)
            latency_ms = int((time.time() - started) * 1000)
            return json.dumps(
                {
                    "ok": True,
                    "query": query,
                    "items": items,
                    "fetched_pages": fetched_pages,
                    "meta": {
                        "provider_used": provider,
                        "fallback_chain": tried,
                        "result_count": len(items),
                        "fetched_count": len(fetched_pages),
                        "latency_ms": latency_ms,
                        "degraded": any((p.get("status") or "") != "ok" for p in fetched_pages),
                    },
                },
                ensure_ascii=False,
            )
        except requests.Timeout:
            last_error = f"{provider}:timeout"
        except Exception as e:
            last_error = f"{provider}:{e}"
            logger.warning("web_search provider failed provider=%s err=%s", provider, e)

    latency_ms = int((time.time() - started) * 1000)
    return json.dumps(
        {
            "ok": False,
            "error": "web_search 所有 provider 均不可用",
            "query": query,
            "items": [],
            "fetched_pages": [],
            "meta": {
                "provider_used": "",
                "fallback_chain": tried,
                "result_count": 0,
                "fetched_count": 0,
                "latency_ms": latency_ms,
                "degraded": bool(tried),
                "last_error": last_error,
            },
        },
        ensure_ascii=False,
    )
