import json
import time
from typing import Any

import requests

from config import (
    TAVILY_API_KEY,
    TAVILY_SEARCH_ENDPOINT,
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
            latency_ms = int((time.time() - started) * 1000)
            return json.dumps(
                {
                    "ok": True,
                    "query": query,
                    "items": items,
                    "meta": {
                        "provider_used": provider,
                        "fallback_chain": tried,
                        "result_count": len(items),
                        "latency_ms": latency_ms,
                        "degraded": len(tried) > 1,
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
            "meta": {
                "provider_used": "",
                "fallback_chain": tried,
                "result_count": 0,
                "latency_ms": latency_ms,
                "degraded": bool(tried),
                "last_error": last_error,
            },
        },
        ensure_ascii=False,
    )
