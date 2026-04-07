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

_NOISE_PATTERNS = (
    r"(?:个性化推荐算法备案编号|推荐算法备案编号)[\s\S]{0,160}(?:\||$)",
    r"(?:信息服务资质提示|信息服务商备案)[\s\S]{0,160}(?:\||$)",
    r"(?:增值电信业务经营许可证|网络文化经营许可证|互联网药品信息服务资格证书)[\s\S]{0,160}(?:\||$)",
    r"(?:ICP备案|ICP证|网安备|公网安备)[\s\S]{0,120}(?:\||$)",
    r"(?:版权所有|Copyright)[\s\S]{0,120}(?:\||$)",
)


def _strip_common_noise(text: str) -> str:
    s = text or ""
    for p in _NOISE_PATTERNS:
        s = re.sub(rf"[\s\S]{{0,24}}{p}", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _dedup_sentences(text: str) -> str:
    parts = re.split(r"(?<=[。！？!?；;])|\s{2,}|\n+", text or "")
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        s = (p or "").strip()
        if not s:
            continue
        key = re.sub(r"\s+", "", s)
        if len(key) < 6:
            out.append(s)
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return " ".join(out).strip()


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


TOOL_READ_URL = {
    "type": "function",
    "function": {
        "name": "read_url",
        "description": "读取指定 URL 的网页内容，提取正文文本返回。",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要读取的网页链接"},
            },
            "required": ["url"],
        },
    },
}


def get_web_search_tools_for_inject() -> list[dict]:
    return [TOOL_WEB_SEARCH, TOOL_READ_URL]


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
    _SKIP_TAGS = frozenset(("script", "style", "noscript", "footer", "nav", "header", "aside", "svg"))
    _MAX_IMAGES = 3

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []
        self._title_parts: list[str] = []
        self._in_title = False
        self._og_image: str = ""
        self._img_urls: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        t = (tag or "").lower()
        if t in self._SKIP_TAGS:
            self._skip_depth += 1
        elif t == "title":
            self._in_title = True
        elif t == "meta":
            attr_dict = dict(attrs or [])
            prop = (attr_dict.get("property") or "").lower()
            if prop == "og:image" and not self._og_image:
                self._og_image = (attr_dict.get("content") or "").strip()
        elif t == "img" and self._skip_depth <= 0 and len(self._img_urls) < self._MAX_IMAGES:
            attr_dict = dict(attrs or [])
            src = (attr_dict.get("src") or "").strip()
            if src and src.startswith("http") and not any(x in src for x in ("icon", "logo", "avatar", "emoji")):
                self._img_urls.append(src)

    def handle_endtag(self, tag: str) -> None:
        t = (tag or "").lower()
        if t in self._SKIP_TAGS and self._skip_depth > 0:
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

    def image_urls(self) -> list[str]:
        """返回去重后的图片 URL 列表（og:image 优先）。"""
        seen: set[str] = set()
        out: list[str] = []
        for url in ([self._og_image] if self._og_image else []) + self._img_urls:
            if url and url not in seen:
                seen.add(url)
                out.append(url)
        return out[:self._MAX_IMAGES]

    def text(self) -> str:
        merged = " ".join(self._parts).strip()
        merged = re.sub(r"\s+", " ", merged)
        # 去除常见页脚噪音（备案号、营业执照等）
        merged = re.sub(r"[\s\S]{0,20}(?:ICP备|网安备|营业执照|经营许可证|违法不良信息举报|互联网举报中心)[\s\S]{0,60}(?:\||$)", " ", merged)
        merged = _strip_common_noise(merged)
        merged = _dedup_sentences(merged)
        return merged


def _describe_image_urls(img_urls: list[str], timeout: int = 10) -> list[str]:
    """下载图片并调用 IMAGE_DESC_API 生成描述，失败静默跳过。"""
    from services.image_desc import image_to_description

    descs: list[str] = []
    for img_url in (img_urls or [])[:3]:
        try:
            r = requests.get(img_url, timeout=timeout, headers={"User-Agent": "du-gateway/1.0"})
            if r.status_code != 200 or not r.content:
                continue
            ct = (r.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip()
            if not ct.startswith("image/"):
                continue
            b64 = __import__("base64").b64encode(r.content).decode("ascii")
            desc = image_to_description(b64, ct)
            if desc:
                descs.append(desc.strip())
        except Exception:
            continue
    return descs


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

        # 提取页面图片并生成描述
        img_urls = parser.image_urls()
        img_descs = _describe_image_urls(img_urls, timeout=timeout_seconds) if img_urls else []
        if img_descs:
            img_block = "\n".join(f"[图片：{d}]" for d in img_descs)
            text = img_block + "\n\n" + text

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


def execute_read_url(arguments: dict) -> str:
    url = str((arguments or {}).get("url") or "").strip()
    if not url:
        return json.dumps({"ok": False, "error": "url 不能为空"}, ensure_ascii=False)
    timeout_seconds = max(2, int(WEBSEARCH_TIMEOUT_SECONDS))
    page = _fetch_page(url, timeout_seconds)
    if page["status"] in ("error", "blocked"):
        return json.dumps({"ok": False, "error": f"读取失败: {page['status']}", "url": url}, ensure_ascii=False)
    return json.dumps({
        "ok": True,
        "url": url,
        "title": page.get("title", ""),
        "content": page.get("content", ""),
        "is_truncated": page.get("is_truncated", False),
        "content_chars": page.get("content_chars", 0),
    }, ensure_ascii=False)
