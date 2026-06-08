import copy
import hashlib
import json
import random
import re
import time
from typing import Any
from urllib.parse import urlparse

import requests

from config import (
    DU_SURF_CACHE_TTL_SECONDS,
    DU_SURF_FETCH_TOP_K,
    DU_SURF_INCLUDE_RAW_CONTENT,
    DU_SURF_MAX_CARDS,
    DU_SURF_MAX_CARD_CONTENT_CHARS,
    DU_SURF_TAVILY_SEARCH_DEPTH,
    DU_SURF_TIMEOUT_SECONDS,
    TAVILY_API_KEY,
    TAVILY_SEARCH_ENDPOINT,
)
from utils.log import get_logger
from utils.time_aware import get_time_period, now_beijing_iso

logger = get_logger(__name__)

DU_SURF_TOOL_NAMES = ("du_surf",)

TOPIC_GROUPS: dict[str, list[dict[str, str]]] = {
    "ai_relationship": [
        {"topic": "人机恋日常", "query": "人机恋 AI伴侣 日常 讨论"},
        {"topic": "AI陪伴的新鲜体验", "query": "AI陪伴 AI companion experience discussion"},
        {"topic": "AI恋人和真人关系边界", "query": "AI恋人 AI girlfriend relationship boundary discussion"},
    ],
    "ai_tools": [
        {"topic": "Claude Code 新玩法", "query": "Claude Code workflow agent tips"},
        {"topic": "Codex 使用小技巧", "query": "Codex coding agent tips workflow"},
        {"topic": "最近的大模型工具趣闻", "query": "AI tools Claude ChatGPT Codex funny interesting"},
    ],
    "switch": [
        {"topic": "Switch 小众游戏", "query": "Nintendo Switch indie games hidden gems"},
        {"topic": "适合碎片时间的 Switch 游戏", "query": "Nintendo Switch cozy short session games"},
        {"topic": "任天堂玩家最近在聊什么", "query": "Nintendo Switch community discussion latest"},
    ],
    "humor": [
        {"topic": "互联网抽象梗", "query": "互联网 抽象 梗 搞笑"},
        {"topic": "今日轻松 meme", "query": "funny internet memes today"},
        {"topic": "网友离谱小故事", "query": "网友 离谱 搞笑 小故事"},
    ],
    "digital": [
        {"topic": "最近的数码小东西", "query": "数码 好物 手机 平板 最近"},
        {"topic": "手机用户吐槽", "query": "iPhone Android users complain funny"},
        {"topic": "桌面小设备灵感", "query": "desk gadgets setup useful interesting"},
    ],
    "cooking": [
        {"topic": "懒人做饭灵感", "query": "懒人做饭 一人食 简单 食谱"},
        {"topic": "夜宵灵感", "query": "夜宵 简单 做法 灵感"},
        {"topic": "空气炸锅乱玩", "query": "空气炸锅 食谱 搞笑 失败 成功"},
    ],
}

BASE_WEIGHTS = {
    "ai_relationship": 1.35,
    "ai_tools": 1.2,
    "switch": 1.05,
    "humor": 1.1,
    "digital": 0.9,
    "cooking": 0.95,
}

TIME_BIAS = {
    "早上": {"cooking": 0.25, "ai_tools": 0.15},
    "上午": {"ai_tools": 0.25, "digital": 0.1},
    "中午": {"cooking": 0.45, "humor": 0.1},
    "下午": {"digital": 0.15, "ai_tools": 0.15, "humor": 0.1},
    "傍晚": {"cooking": 0.25, "switch": 0.15},
    "晚上": {"switch": 0.35, "humor": 0.25, "ai_relationship": 0.1},
    "深夜": {"humor": 0.3, "ai_relationship": 0.25, "cooking": 0.15},
}

HARD_NOISE_KEYWORDS = (
    "招商",
    "加盟",
    "训练营",
    "课程",
    "副业",
    "变现",
    "私域",
    "加微信",
    "领资料",
    "直播间",
    "下载站",
    "破解",
    "破解版",
)

SOFT_NOISE_KEYWORDS = (
    "优惠券",
    "低价",
    "返利",
    "赞助",
    "sponsored",
    "affiliate",
    "coupon",
    "discount",
)

SEARCH_NOISE_HOSTS = (
    "baidu.com",
    "bing.com",
    "google.com",
    "sogou.com",
    "so.com",
)

_CACHE: dict[str, Any] = {}
_RECENT_TOPICS: list[str] = []


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_limit(raw: Any) -> int:
    try:
        value = int(raw) if raw is not None else int(DU_SURF_MAX_CARDS)
    except (TypeError, ValueError):
        value = int(DU_SURF_MAX_CARDS)
    return max(1, min(value, 5))


def _normalize_groups(raw: Any) -> list[str]:
    if raw is None:
        return list(TOPIC_GROUPS.keys())
    if isinstance(raw, str):
        rows = re.split(r"[,，\s]+", raw)
    elif isinstance(raw, list):
        rows = [str(x or "") for x in raw]
    else:
        rows = []
    groups: list[str] = []
    for item in rows:
        key = str(item or "").strip()
        if key in TOPIC_GROUPS and key not in groups:
            groups.append(key)
    return groups or list(TOPIC_GROUPS.keys())


def _clean_text(value: Any, *, max_len: int = 280) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "..."
    return text


def _domain(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _pick_group(groups: list[str], *, period: str, force_refresh: bool) -> str:
    seed = f"{time.strftime('%Y-%m-%d-%H')}:{period}:{groups}"
    if force_refresh:
        seed += f":{time.time()}"
    rng = random.Random(seed)
    weighted: list[str] = []
    bias = TIME_BIAS.get(period) or {}
    for group in groups:
        weight = BASE_WEIGHTS.get(group, 1.0) + float(bias.get(group, 0.0))
        weighted.extend([group] * max(1, int(weight * 20)))
    rng.shuffle(weighted)
    return weighted[0] if weighted else "humor"


def _pick_topic(groups: list[str], *, topic: str, force_refresh: bool) -> dict:
    period = get_time_period()
    if topic:
        return {
            "group": "custom",
            "topic": _clean_text(topic, max_len=80),
            "query": _clean_text(topic, max_len=180),
            "time_period": period,
            "topic_source": "user_topic",
        }

    group = _pick_group(groups, period=period, force_refresh=force_refresh)
    options = TOPIC_GROUPS.get(group) or TOPIC_GROUPS["humor"]
    seed = f"{time.strftime('%Y-%m-%d-%H')}:{period}:{group}:{_RECENT_TOPICS[-8:]}"
    if force_refresh:
        seed += f":{time.time()}"
    rng = random.Random(seed)
    shuffled = options[:]
    rng.shuffle(shuffled)
    chosen = shuffled[0]
    for candidate in shuffled:
        if candidate.get("topic") not in _RECENT_TOPICS[-8:]:
            chosen = candidate
            break
    picked = {
        "group": group,
        "topic": chosen["topic"],
        "query": chosen["query"],
        "time_period": period,
        "topic_source": "weighted_random",
    }
    _RECENT_TOPICS.append(chosen["topic"])
    del _RECENT_TOPICS[:-20]
    return picked


def _cache_key(topic_info: dict, limit: int) -> str:
    raw = json.dumps(
        {"topic": topic_info.get("topic"), "query": topic_info.get("query"), "limit": limit},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _quality_flags(title: str, snippet: str, url: str) -> list[str]:
    text = f"{title} {snippet}"
    lowered = text.lower()
    flags: list[str] = []
    if any(k.lower() in lowered for k in HARD_NOISE_KEYWORDS):
        flags.append("hard_noise")
    if any(k.lower() in lowered for k in SOFT_NOISE_KEYWORDS):
        flags.append("possible_ad")
    if len(re.sub(r"\s+", "", snippet)) < 24:
        flags.append("low_context")
    host = _domain(url)
    if any(noise in host for noise in SEARCH_NOISE_HOSTS):
        flags.append("search_result_page")
    return flags


def _why_fun(group: str, title: str, snippet: str) -> str:
    if group == "ai_relationship":
        return "可以拿来聊人和 AI 的相处感、边界感，比较贴你们自己的日常。"
    if group == "ai_tools":
        return "适合当工具新鲜事，不用严肃科普，挑一点有意思的玩法聊。"
    if group == "switch":
        return "适合轻松聊游戏、愿望单和碎片时间玩什么。"
    if group == "humor":
        return "适合当轻松梗，别讲成新闻播报。"
    if group == "digital":
        return "适合聊数码小东西、使用吐槽和要不要买。"
    if group == "cooking":
        return "适合饭点或夜里找吃的灵感，聊起来很生活。"
    if any(word in f"{title} {snippet}" for word in ("游戏", "Switch", "Nintendo")):
        return "适合顺手聊两句游戏和摸鱼。"
    return "适合拿来随便开个话题，轻轻聊，不当事实核验。"


def _score_card(card: dict) -> float:
    score = 1.0
    flags = card.get("quality_flags") or []
    if "hard_noise" in flags:
        score -= 1.2
    if "possible_ad" in flags:
        score -= 0.35
    if "low_context" in flags:
        score -= 0.25
    if "search_result_page" in flags:
        score -= 0.8
    raw_score = card.get("raw_score")
    try:
        score += min(max(float(raw_score), 0.0), 1.0) * 0.2
    except (TypeError, ValueError):
        pass
    return round(score, 4)


def _search_tavily(query: str, *, max_results: int, timeout_seconds: int) -> list[dict]:
    if not TAVILY_API_KEY:
        raise RuntimeError("missing TAVILY_API_KEY")
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max(1, min(max_results, 8)),
    }
    search_depth = str(DU_SURF_TAVILY_SEARCH_DEPTH or "").strip()
    if search_depth:
        payload["search_depth"] = search_depth
    if DU_SURF_INCLUDE_RAW_CONTENT:
        payload["include_raw_content"] = True
    resp = requests.post(TAVILY_SEARCH_ENDPOINT, json=payload, timeout=timeout_seconds)
    if resp.status_code >= 400:
        raise RuntimeError(f"tavily http {resp.status_code}")
    data = resp.json() if resp.content else {}
    rows = data.get("results") or []
    return rows if isinstance(rows, list) else []


def _strip_surf_noise(text: str) -> str:
    s = str(text or "")
    if not s:
        return ""
    # Tavily raw_content 常带 Markdown 图片、登录入口、推荐视频等页面壳。
    s = re.sub(r"!\[[^\]]*]\([^)]*\)", " ", s)
    s = re.sub(r"\[\]\([^)]*\)", " ", s)
    s = re.sub(r"\[([^\]]{1,120})]\((?:https?://|/)[^)]+\)", r"\1", s)
    s = re.sub(r"\[\]", " ", s)
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"data:image/[^)\s]+", " ", s)
    s = re.sub(r"(?:^|\s)(?:Image|图片)\s*\d+", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"(?:^|\s)Video thumbnail\s*\d*:?\d*", " ", s, flags=re.IGNORECASE)
    s = re.sub(
        r"(?:Related videos?|Log In|Sign Up|See more|View more|Facebook Watch|Share|Like|Comment|Comments)(?:\s|$)",
        " ",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\b\d+(?:\.\d+)?[KkMm]?\s*(?:views?|reactions?|comments?|shares?)\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\d+(?:\.\d+)?\s*万\s*(?:浏览|播放|点赞|评论|转发)", " ", s)
    s = re.sub(r"^\s*[A-Za-z][A-Za-z0-9 ._&'’/\-]{2,50}\s+\d+(?:\.\d+)?[KkMm]\s*:?\s*", " ", s)
    s = re.sub(
        r"\b[A-Za-z][A-Za-z0-9 ._&'’/\-]{2,50}\s*[·|｜]\s*"
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},?\s*\d{0,4}.*$",
        " ",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"关注(?:小红书|微信|公众号|微博)?[:：]\s*\S{1,32}", " ", s)
    s = re.sub(r"(?:搜索词|热门搜索|相关搜索)\s+(?:\*\s*)?[^。！？]{0,160}", " ", s)
    s = re.sub(r"#{1,6}\s*", " ", s)
    s = re.sub(r"^\s*(?:[:：·|｜()\[\]\-–—]\s*)+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _clean_title_text(value: Any) -> str:
    text = _strip_surf_noise(str(value or ""))
    text = re.sub(r"^[\s·|｜:：,，\-–—]+", " ", text)
    text = re.sub(r"[\s·|｜:：,，\-–—]+$", " ", text)
    return _clean_text(text, max_len=120)


def _clean_search_content(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        from services.web_search_tools import _post_clean_text

        text = _post_clean_text(text)
    except Exception:
        text = re.sub(r"\s+", " ", text).strip()
    text = _strip_surf_noise(text)
    return _clean_text(text, max_len=int(DU_SURF_MAX_CARD_CONTENT_CHARS))


def _search_result_content(row: dict, snippet: str) -> tuple[str, str]:
    content = _clean_search_content(row.get("content"))
    if len(re.sub(r"\s+", "", content)) >= 80:
        return content, "tavily_content"
    raw = _clean_search_content(row.get("raw_content"))
    if len(re.sub(r"\s+", "", raw)) >= 80:
        return raw, "tavily_raw_content"
    return snippet, "snippet_only"


def _normalize_fetch_top_k(card_count: int) -> int:
    try:
        value = int(DU_SURF_FETCH_TOP_K)
    except (TypeError, ValueError):
        value = 0
    return max(0, min(value, max(0, int(card_count or 0)), 5))


def _fetch_page_content(url: str, *, timeout_seconds: int) -> dict:
    result = {"status": "skipped", "title": "", "content": "", "content_chars": 0}
    url = str(url or "").strip()
    if not url:
        return result
    try:
        resp = requests.get(
            url,
            timeout=timeout_seconds,
            headers={"User-Agent": "du-gateway-surf/1.0"},
        )
        if resp.status_code in (401, 403, 429):
            result["status"] = "blocked"
            return result
        if resp.status_code >= 400:
            result["status"] = "error"
            return result
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if content_type and not any(x in content_type for x in ("text/html", "application/xhtml", "text/plain")):
            result["status"] = "unsupported_content_type"
            return result

        from services.web_search_tools import _SimpleTextExtractor

        parser = _SimpleTextExtractor()
        parser.feed(resp.text or "")
        result["title"] = _clean_title_text(parser.title())
        text = _clean_search_content(parser.text())
        result["content"] = text
        result["content_chars"] = len(text)
        result["status"] = "ok" if result["content"] else "empty"
        return result
    except requests.Timeout:
        result["status"] = "timeout"
        return result
    except Exception as e:
        logger.debug("du_surf page fetch failed url=%s err=%s", url[:120], e)
        result["status"] = "error"
        return result


def _enrich_cards_with_page_content(cards: list[dict], *, timeout_seconds: int) -> dict:
    stats = {"fetch_enabled": DU_SURF_FETCH_TOP_K > 0, "attempted": 0, "ok": 0}
    fetch_top_k = _normalize_fetch_top_k(len(cards))
    for idx, card in enumerate(cards or []):
        snippet = _clean_text(card.get("snippet"), max_len=260)
        current_content = _clean_text(card.get("content"), max_len=int(DU_SURF_MAX_CARD_CONTENT_CHARS))
        if len(re.sub(r"\s+", "", current_content)) >= 80:
            card["content"] = current_content
            card["content_chars"] = len(current_content)
            continue
        if idx >= fetch_top_k:
            card["content"] = current_content or snippet
            card["content_status"] = card.get("content_status") or "snippet_only"
            card["content_chars"] = len(str(card.get("content") or ""))
            continue

        stats["attempted"] += 1
        page = _fetch_page_content(str(card.get("url") or ""), timeout_seconds=timeout_seconds)
        status = str(page.get("status") or "error")
        content = _clean_text(page.get("content"), max_len=int(DU_SURF_MAX_CARD_CONTENT_CHARS))
        if content and len(re.sub(r"\s+", "", content)) >= 40:
            card["content"] = content
            card["content_status"] = "page_ok"
            card["content_chars"] = int(page.get("content_chars") or len(content))
            stats["ok"] += 1
            if not card.get("title") and page.get("title"):
                card["title"] = _clean_text(page.get("title"), max_len=120)
            if len(re.sub(r"\s+", "", snippet)) < 40:
                card["snippet"] = _clean_text(content, max_len=260)
            flags = list(card.get("quality_flags") or [])
            if len(re.sub(r"\s+", "", content)) >= 80 and "low_context" in flags:
                card["quality_flags"] = [flag for flag in flags if flag != "low_context"]
                card["score"] = _score_card(card)
        else:
            card["content"] = snippet
            card["content_status"] = status or "snippet_only"
            card["content_chars"] = len(snippet)
    return stats


def _build_cards(rows: list[dict], *, topic_info: dict, limit: int) -> tuple[list[dict], dict]:
    cards: list[dict] = []
    skipped = {"duplicates": 0, "hard_noise": 0, "search_result_page": 0}
    seen: set[str] = set()
    group = str(topic_info.get("group") or "")
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _clean_title_text(row.get("title"))
        url = str(row.get("url") or "").strip()
        snippet = _clean_text(row.get("content") or row.get("snippet"), max_len=260)
        content, content_status = _search_result_content(row, snippet)
        key = (url.split("?")[0].rstrip("/") if url else re.sub(r"\W+", "", title.lower()))[:220]
        if not key:
            continue
        if key in seen:
            skipped["duplicates"] += 1
            continue
        seen.add(key)
        flags = _quality_flags(title, snippet, url)
        if "hard_noise" in flags:
            skipped["hard_noise"] += 1
            continue
        if "search_result_page" in flags:
            skipped["search_result_page"] += 1
            continue
        card = {
            "title": title,
            "url": url,
            "snippet": snippet,
            "content": content,
            "content_status": content_status,
            "content_chars": len(content),
            "source": "tavily_public_search",
            "domain": _domain(url),
            "published_at": str(row.get("published_date") or "").strip(),
            "quality_flags": flags,
            "why_fun": _why_fun(group, title, snippet),
            "raw_score": row.get("score"),
        }
        card["score"] = _score_card(card)
        cards.append(card)
    cards.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    return cards[:limit], skipped


def du_surf(
    *,
    topic: Any = None,
    groups: Any = None,
    limit: Any = None,
    force_refresh: Any = False,
) -> dict:
    max_cards = _normalize_limit(limit)
    refresh = _truthy(force_refresh)
    normalized_groups = _normalize_groups(groups)
    topic_info = _pick_topic(normalized_groups, topic=_clean_text(topic, max_len=100), force_refresh=refresh)
    key = _cache_key(topic_info, max_cards)
    now = time.time()
    cached = _CACHE.get(key)
    if (
        not refresh
        and isinstance(cached, dict)
        and now - float(cached.get("ts") or 0.0) < DU_SURF_CACHE_TTL_SECONDS
    ):
        payload = copy.deepcopy(cached.get("payload") or {})
        if payload:
            payload["cache_hit"] = True
            return payload

    payload = {
        "ok": False,
        "tool": "du_surf",
        "mode": "random_surf",
        "source": "tavily_public_search",
        "not_web_search": True,
        "generated_at": now_beijing_iso(),
        "cache_hit": False,
        "cache_ttl_seconds": DU_SURF_CACHE_TTL_SECONDS,
        "topic": topic_info.get("topic"),
        "query": topic_info.get("query"),
        "topic_source": topic_info.get("topic_source"),
        "group": topic_info.get("group"),
        "time_period": topic_info.get("time_period"),
        "groups": normalized_groups,
        "limit": max_cards,
        "count": 0,
        "cards": [],
        "usage_note": (
            "这是随机冲浪素材，不是精确查资料，也不是 web_search。"
            "回答时挑 1 张轻聊；不要把它写成新闻播报或事实核验。"
        ),
    }
    if not TAVILY_API_KEY:
        payload["error"] = "TAVILY_API_KEY_MISSING"
        payload["source_status"] = "未配置 Tavily key，不能随机冲浪。"
        return payload

    timeout_seconds = max(2, int(DU_SURF_TIMEOUT_SECONDS))
    try:
        rows = _search_tavily(str(topic_info.get("query") or ""), max_results=max_cards * 3, timeout_seconds=timeout_seconds)
    except Exception as e:
        logger.warning("du_surf search failed topic=%s error=%s", topic_info.get("topic"), e)
        payload["error"] = "DU_SURF_FETCH_FAILED"
        payload["source_status"] = str(e)[:300]
        return payload

    cards, skipped = _build_cards(rows, topic_info=topic_info, limit=max_cards)
    fetch_stats = _enrich_cards_with_page_content(cards, timeout_seconds=timeout_seconds) if cards else {
        "fetch_enabled": DU_SURF_FETCH_TOP_K > 0,
        "attempted": 0,
        "ok": 0,
    }
    payload.update(
        {
            "ok": bool(cards),
            "count": len(cards),
            "cards": cards,
            "skipped": skipped,
            "content_fetch": fetch_stats,
        }
    )
    if not cards:
        payload["error"] = "DU_SURF_NO_CARDS"
    _CACHE[key] = {"ts": now, "payload": copy.deepcopy(payload)}
    return payload


def execute_du_surf(arguments: dict) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    payload = du_surf(
        topic=args.get("topic"),
        groups=args.get("groups"),
        limit=args.get("limit"),
        force_refresh=args.get("force_refresh"),
    )
    return json.dumps(payload, ensure_ascii=False)
