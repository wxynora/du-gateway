"""Dynamic-memory query rewriting, retrieval, reranking, and prompt injection."""

import json
import math
import re
import time
from dataclasses import dataclass
from typing import Callable, Optional

import requests

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL,
    DYNAMIC_MEMORY_MIRROR_SHADOW_ENABLED,
    DYNAMIC_MEMORY_TOP_N,
)
from pipeline.prompt_layout import _append_to_dynamic_system
from pipeline.recent_context import _filter_rounds_for_recent_context
from services.dynamic_memory_citation import DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY
from services.dynamic_memory_recall_debug import DU_REQUEST_ID_BODY_KEY, normalize_debug_request_id
from services.dynamic_memory_weight import dynamic_memory_weight
from services.memory_bm25 import BM25QueryTerm, bm25_score_documents
from storage import r2_store
from utils.log import get_logger
from utils.tokens import estimate_tokens, memory_dynamic_budget


logger = get_logger("pipeline.pipeline")
_MEMORY_QUERY_REWRITE_MODEL = "deepseek-v4-pro"


@dataclass(frozen=True, slots=True)
class RecallResult:
    body: dict
    candidate_ids: list[str]
    topic_state: dict


def _strip_memory_query_media_placeholders(text: str) -> str:
    """图片占位只表示本轮带图，不参与关键词和 BM25 匹配。"""
    cleaned = re.sub(r"(?:\[\s*图片\s*\]|【\s*图片\s*】)", " ", str(text or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_keyword_candidates(text: str) -> list[dict]:
    """提取用于匹配动态层的关键词候选，并标注是否来自短语收敛层。"""
    if not text or not isinstance(text, str):
        return []
    text = _strip_memory_query_media_placeholders(text)
    if not text:
        return []

    stopwords = {
        "好的",
        "可以",
        "行吧",
        "行的",
        "嗯嗯",
        "哈哈",
        "收到",
        "知道了",
        "明白了",
        "没事",
        "谢谢",
        "好的呀",
        "好的呢",
        "记忆",
        "动态记忆",
        "窗口记忆",
        "回忆",
        "总结",
        "注入",
        "检索",
        "向量",
        "embedding",
        "embeddings",
    }
    shell_words = {
        "今天",
        "昨天",
        "刚刚",
        "最近",
        "这几天",
        "这个",
        "那个",
        "这样",
        "那样",
        "感觉",
        "觉得",
        "就是",
        "然后",
        "所以",
        "因为",
        "但是",
    }
    attitude_patterns = [
        r"(不太想[^\s,，。！？、；：]{1,8})",
        r"(不想[^\s,，。！？、；：]{1,8})",
        r"(想让[^\s,，。！？、；：]{1,8})",
        r"(想要[^\s,，。！？、；：]{1,8})",
        r"(更喜欢[^\s,，。！？、；：]{1,8})",
        r"(不喜欢[^\s,，。！？、；：]{1,8})",
        r"(喜欢[^\s,，。！？、；：]{1,8})",
        r"(讨厌[^\s,，。！？、；：]{1,8})",
        r"(更想[^\s,，。！？、；：]{1,8})",
        r"(宁愿[^\s,，。！？、；：]{1,8})",
        r"(不希望[^\s,，。！？、；：]{1,8})",
        r"(希望[^\s,，。！？、；：]{1,8})",
        r"(?:有点|有一点|很|特别|真的)?(?:委屈|生气|开心|难过|烦|不爽|害怕|担心|紧张|难受)",
        r"(?:很|特别|真的)?(?:在意|介意|失望|安心|心疼|依赖)",
        r"(?:受不了|接受不了)",
        r"(?:可以|不行)",
    ]
    fact_patterns = [
        r"(?:肚子|胃|头|喉咙|牙|鼻子|身上)[^\s,，。！？、；：]{0,4}(?:不舒服|疼|痛)",
        r"(?:不舒服|头疼|肚子疼|想吐|累|困|压力大|没睡好)",
        r"(?:跟|和)[^\s,，。！？、；：]{1,6}(?:吵架|冷战|和好)",
        r"(?:上班|请假|去医院|看书|搬家)",
    ]
    trim_prefix_re = re.compile(r"^(?:我(?:最近|今天|昨天)?|最近|今天|昨天|刚刚|其实|就是|感觉|觉得)+")
    clause_split_re = re.compile(r"(?:但是|但|不过|而且|然后|所以|因为)")
    def _dedup_keep_order(items: list[dict], limit: int = 24) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        for item in items:
            s = str((item or {}).get("text") or "").strip()
            if len(s) < 2 or s in seen or s in stopwords:
                continue
            seen.add(s)
            out.append({"text": s, "is_phrase": bool((item or {}).get("is_phrase"))})
            if len(out) >= limit:
                break
        return out

    def _extract_cjk_ngrams(s: str, max_keep: int = 24) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for seg in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", s or ""):
            seg = seg.strip()
            if len(seg) < 2:
                continue
            if len(seg) <= 24:
                if seg not in seen:
                    seen.add(seg)
                    out.append(seg)
                continue
            for n in (4, 3, 2):
                for i in range(0, max(0, len(seg) - n + 1)):
                    token = seg[i : i + n].strip()
                    if len(token) < 2 or token in seen:
                        continue
                    seen.add(token)
                    out.append(token)
                    if len(out) >= max_keep:
                        return out
        return out

    def _extract_raw_keywords(s: str) -> list[str]:
        parts = re.split(r"[\s,，。！？、；：]+", s)
        keywords: list[str] = []
        seen: set[str] = set()
        for p in parts:
            p = p.strip()
            if len(p) < 2 or p in stopwords:
                continue
            if len(p) > 24:
                for token in _extract_cjk_ngrams(p):
                    if token in stopwords or token in seen:
                        continue
                    seen.add(token)
                    keywords.append(token)
                continue
            if p not in seen:
                seen.add(p)
                keywords.append(p)
        return keywords

    def _extract_phrase_keywords(s: str) -> list[dict]:
        candidates: list[dict] = []
        clean = re.sub(r"[\n\r\t]+", " ", s or "")
        for pattern in attitude_patterns + fact_patterns:
            for m in re.finditer(pattern, clean):
                phrase = trim_prefix_re.sub("", m.group(0).strip())
                phrase = clause_split_re.split(phrase, maxsplit=1)[0].strip()
                phrase = re.sub(r"^(?:这次|还是|又)", "", phrase).strip()
                if 2 <= len(phrase) <= 12:
                    candidates.append({"text": phrase, "is_phrase": True})
        return _dedup_keep_order(candidates, limit=6)

    def _build_clause_fallback(s: str) -> str:
        clean = re.sub(r"[\n\r\t]+", " ", s or "").strip()
        if not clean:
            return ""
        clause = re.split(r"[，。！？；：,.!?;:]", clean, maxsplit=1)[0].strip()
        clause = clause_split_re.split(clause, maxsplit=1)[0].strip()
        clause = trim_prefix_re.sub("", clause).strip()
        clause = re.sub(r"^(?:这次|还是|又)", "", clause).strip()
        if 2 <= len(clause) <= 18 and clause not in shell_words:
            return clause
        return ""

    raw_keywords = _extract_raw_keywords(text)
    phrase_keywords = _extract_phrase_keywords(text)

    merged: list[dict] = []
    seen: set[str] = set()
    phrase_texts = [str((item or {}).get("text") or "").strip() for item in phrase_keywords]
    for item in phrase_keywords + [{"text": kw, "is_phrase": False} for kw in raw_keywords]:
        kw = str((item or {}).get("text") or "").strip()
        if len(kw) < 2 or kw in stopwords or kw in shell_words or kw in seen:
            continue
        if any((kw != other and kw in other) for other in phrase_texts):
            continue
        seen.add(kw)
        merged.append({"text": kw, "is_phrase": bool((item or {}).get("is_phrase"))})
    if not any(bool((item or {}).get("is_phrase")) for item in merged):
        clause = _build_clause_fallback(text)
        if clause and clause not in seen:
            merged.insert(0, {"text": clause, "is_phrase": True})
    return merged


def _extract_keywords(text: str) -> list:
    """从当前对话文本中提取用于匹配动态层的关键词/短语。"""
    return [str((item or {}).get("text") or "").strip() for item in _extract_keyword_candidates(text)]


def _build_retrieval_text(text: str) -> str:
    """生成更适合检索的内部短语表示，优先保留态度/感受/偏好短语。"""
    text = (text or "").strip()
    if not text:
        return ""
    candidates = _extract_keyword_candidates(text)
    if not candidates:
        return text
    pieces: list[str] = []
    seen: set[str] = set()
    phrase_count = 0
    for item in candidates:
        s = str((item or {}).get("text") or "").strip()
        if len(s) < 2 or s in seen:
            continue
        is_phrase = bool((item or {}).get("is_phrase"))
        if is_phrase:
            phrase_count += 1
        seen.add(s)
        pieces.append(s)
        if len(pieces) >= 5 or phrase_count >= 3:
            break
    if not pieces:
        return text
    return " ".join(pieces)


def _memory_retrieval_text(mem: dict) -> str:
    """读取记忆的检索文本；旧数据无 retrieval_text 时回退即时生成。"""
    if not isinstance(mem, dict):
        return ""
    retrieval_text = str(mem.get("retrieval_text") or "").strip()
    content = str(mem.get("content") or "").strip()
    if not retrieval_text:
        retrieval_text = _build_retrieval_text(content)
    if retrieval_text and content and retrieval_text not in content:
        return f"{retrieval_text}\n{content}"
    return retrieval_text or content


def _memory_keyword_search_text(mem: dict) -> str:
    """关键词召回同时搜索检索文本与完整正文，与 search_memory 保持一致。"""
    if not isinstance(mem, dict):
        return ""
    retrieval_text = str(mem.get("retrieval_text") or "").strip()
    content = str(mem.get("content") or "").strip()
    if retrieval_text and content and retrieval_text != content:
        return f"{retrieval_text}\n{content}"
    return retrieval_text or content


def _normalize_direct_keyword_text(text: str) -> str:
    """仅用于比较既有关键词；不重新分词。"""
    compact = re.sub(r"[\W_]+", "", str(text or "").strip().lower(), flags=re.UNICODE)
    return re.sub(r"([零〇一二两三四五六七八九十百千万0-9])个(?=[\u4e00-\u9fff])", r"\1", compact)


def _direct_keyword_hit(mem: dict, keyword_candidates: list[dict]) -> str:
    document = _normalize_direct_keyword_text(_memory_keyword_search_text(mem))
    if not document:
        return ""
    for item in keyword_candidates or []:
        keyword = str((item or {}).get("text") or "").strip()
        normalized = _normalize_direct_keyword_text(keyword)
        if len(normalized) >= 3 and normalized in document:
            return keyword
    return ""


def _topic_state_anchor_candidates(topic_state: dict, evidence_text: str) -> list[dict]:
    """只接纳能在既有 state、前四轮或当前消息中找到来源的模型 anchors。"""
    evidence = _normalize_direct_keyword_text(_strip_memory_query_media_placeholders(evidence_text))
    out: list[dict] = []
    seen: set[str] = set()
    for value in (topic_state or {}).get("anchors") or []:
        anchor = _strip_memory_query_media_placeholders(str(value or ""))
        normalized = _normalize_direct_keyword_text(anchor)
        if len(normalized) < 2 or normalized == "图片" or anchor in seen or normalized not in evidence:
            continue
        seen.add(anchor)
        out.append({"text": anchor, "is_phrase": True, "source": "topic_state_anchor"})
    return out


def _is_trivial_user_message(text: str) -> bool:
    """纯语气词/极短回应，不值得触发向量检索。只过滤最明确的无意义消息。"""
    t = (text or "").strip()
    if not t:
        return True
    if len(t) > 8:
        return False
    trivial = {
        "嗯嗯", "好的", "哈哈", "行吧", "收到", "知道了", "明白了", "没事",
        "谢谢", "ok", "好", "嗯", "哦", "啊", "噢", "哈", "嘿",
        "好的呀", "好的呢", "行", "可以", "好吧", "嗯嗯嗯",
    }
    return t in trivial


# ---------------------------------------------------------------------------
# 检索结果缓存：连续聊同一话题时复用上次结果，避免重复向量检索
# ---------------------------------------------------------------------------
_RECALL_CACHE: dict[str, dict] = {}  # {window_id: {"keywords": [...], "results": [...], "source": "...", "ts": float}}
_RECALL_CACHE_TTL = 120  # 秒


def _recall_cache_hit(
    window_id: str,
    keywords: list[str],
    excluded_source_ids: set[str] | None = None,
) -> dict | None:
    """关键词重叠 >= 70% 且未过期则命中缓存。"""
    import time as _time
    cache = _RECALL_CACHE.get(window_id)
    if not cache:
        return None
    if _time.time() - cache.get("ts", 0) > _RECALL_CACHE_TTL:
        _RECALL_CACHE.pop(window_id, None)
        return None
    cached_excluded = {
        str(value or "").strip()
        for value in cache.get("excluded_source_ids") or []
        if str(value or "").strip()
    }
    current_excluded = {
        str(value or "").strip()
        for value in excluded_source_ids or set()
        if str(value or "").strip()
    }
    if cached_excluded != current_excluded:
        return None
    old_kw = set(cache.get("keywords") or [])
    new_kw = set(keywords)
    if not old_kw or not new_kw:
        return None
    overlap = len(old_kw & new_kw) / max(len(old_kw), len(new_kw))
    if overlap >= 0.7:
        return cache
    return None


def _recall_cache_set(
    window_id: str,
    keywords: list[str],
    results: list[dict],
    source: str = "",
    excluded_source_ids: set[str] | None = None,
) -> None:
    import time as _time
    _RECALL_CACHE[window_id] = {
        "keywords": keywords,
        "results": results,
        "source": source,
        "excluded_source_ids": sorted(
            str(value or "").strip()
            for value in excluded_source_ids or set()
            if str(value or "").strip()
        ),
        "ts": _time.time(),
    }


def _invalidate_recall_cache() -> None:
    """记忆层级发生变化后清空进程内召回缓存，避免继续注入已晋升的动态副本。"""
    _RECALL_CACHE.clear()


def _is_memory_meta_query(text: str) -> bool:
    """
    用户在问“系统/记忆如何工作”的元问题时，不应触发动态记忆检索与注入。
    典型：问“你收到了哪些动态记忆/注入了什么/怎么检索的”等。
    """
    if not text or not isinstance(text, str):
        return False
    t = text.strip().lower()
    if not t:
        return False
    # 包含“记忆”相关词 + “展示/有哪些/收到/注入/检索”等动词，认为是元问题
    has_mem_word = any(w in t for w in ("动态记忆", "窗口记忆", "记忆", "回忆", "总结"))
    has_meta_verb = any(w in t for w in ("哪些", "有什么", "收到", "注入", "检索", "匹配", "召回", "向量", "embedding"))
    return bool(has_mem_word and has_meta_verb)


def _last_4_turns_text_for_rewrite(messages: list[dict]) -> str:
    """取最近 4 轮 user/assistant 文本，供检索查询改写时做参考。"""
    ua_msgs: list[tuple[str, str]] = []
    for m in messages or []:
        role = (m.get("role") or "").lower()
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            parts: list[str] = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    parts.append(str(c.get("text") or ""))
            text = " ".join(parts).strip()
        else:
            text = ""
        if not text:
            continue
        who = "老婆" if role == "user" else "渡"
        ua_msgs.append((who, text))
    if not ua_msgs:
        return ""
    recent = ua_msgs[-8:]  # 约 4 轮
    return "\n".join([f"[{who}] {txt}" for who, txt in recent])


class _PreviousFourRoundsText(str):
    def __new__(
        cls,
        value: str,
        round_indexes: list[int] | tuple[int, ...] = (),
        round_refs: list[tuple[str, int]] | tuple[tuple[str, int], ...] = (),
        used_global_last4: bool = False,
    ):
        obj = super().__new__(cls, value or "")
        obj.round_indexes = tuple(
            index
            for raw in round_indexes or ()
            if (index := _positive_round_index(raw)) > 0
        )
        normalized_refs: list[tuple[str, int]] = []
        for raw in round_refs or ():
            if not isinstance(raw, (list, tuple)) or len(raw) != 2:
                continue
            source_window_id = str(raw[0] or "").strip()
            round_index = _positive_round_index(raw[1])
            if source_window_id and round_index > 0:
                normalized_refs.append((source_window_id, round_index))
        obj.round_refs = tuple(normalized_refs)
        obj.used_global_last4 = bool(used_global_last4)
        return obj


def _positive_round_index(value) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _previous_4_rounds_text_for_rewrite(
    window_id: str,
    *,
    r2_store_module=r2_store,
    filter_rounds: Callable[[list[dict]], list[dict]] = _filter_rounds_for_recent_context,
    last_4_turns_text: Callable[[list[dict]], str] = _last_4_turns_text_for_rewrite,
) -> str:
    """读取与本轮可见 Last4 一致的已归档四轮；不依赖尚未注入的 system。"""
    target_window_id = str(window_id or "").strip()
    if not target_window_id:
        return _PreviousFourRoundsText("")
    use_global_last4 = (
        not target_window_id.startswith("tg_")
        and not r2_store_module.has_window_history(target_window_id)
    )
    if use_global_last4:
        source_rounds = r2_store_module.get_latest_4_rounds_global() or []
    else:
        source_rounds = r2_store_module.get_conversation_rounds(
            target_window_id,
            last_n=12,
        ) or []
    rounds = filter_rounds(source_rounds)[-4:]
    messages: list[dict] = []
    round_indexes: list[int] = []
    round_refs: list[tuple[str, int]] = []
    for round_obj in rounds:
        round_index = _positive_round_index(
            (round_obj or {}).get("index") or (round_obj or {}).get("round_index")
        )
        if round_index > 0:
            round_indexes.append(round_index)
            source_window_id = (
                str((round_obj or {}).get("_source_window_id") or "").strip()
                if use_global_last4
                else target_window_id
            )
            if source_window_id:
                round_refs.append((source_window_id, round_index))
        for message in (round_obj or {}).get("messages") or []:
            if isinstance(message, dict):
                messages.append(message)
    return _PreviousFourRoundsText(
        last_4_turns_text(messages),
        round_indexes,
        round_refs,
        use_global_last4,
    )


def _memory_source_ids(mem: dict) -> set[str]:
    if not isinstance(mem, dict):
        return set()
    out: set[str] = set()
    source_mid = str(mem.get("source_memory_id") or "").strip()
    if source_mid:
        out.add(source_mid)
    mid = str(mem.get("id") or "").strip()
    if mid:
        out.add(mid[len("core::") :] if mid.startswith("core::") else mid)
    return out


def _memory_has_excluded_source(mem: dict, excluded_source_ids: set[str]) -> bool:
    return bool(_memory_source_ids(mem) & (excluded_source_ids or set()))


def _exclude_memories_created_in_recent_rounds(
    memories: list[dict],
    excluded_source_ids: set[str],
) -> list[dict]:
    if not excluded_source_ids:
        return list(memories or [])
    return [
        mem
        for mem in memories or []
        if isinstance(mem, dict) and not _memory_has_excluded_source(mem, excluded_source_ids)
    ]


def _recent_round_created_memory_ids(
    window_id: str,
    previous_four_rounds: str,
    *,
    logger_instance=logger,
) -> set[str]:
    round_indexes = tuple(getattr(previous_four_rounds, "round_indexes", ()) or ())
    round_refs = tuple(getattr(previous_four_rounds, "round_refs", ()) or ())
    target_window_id = str(window_id or "").strip()
    if (
        not round_refs
        and target_window_id
        and not bool(getattr(previous_four_rounds, "used_global_last4", False))
    ):
        round_refs = tuple((target_window_id, index) for index in round_indexes)
    if not round_refs:
        return set()
    try:
        from services.dynamic_memory_provenance import memory_ids_created_in_rounds

        grouped_indexes: dict[str, list[int]] = {}
        for source_window_id, round_index in round_refs:
            grouped_indexes.setdefault(str(source_window_id), []).append(int(round_index))
        created_ids: set[str] = set()
        for source_window_id, source_indexes in grouped_indexes.items():
            created_ids.update(
                memory_ids_created_in_rounds(source_window_id, source_indexes)
            )
        return created_ids
    except Exception as e:
        logger_instance.warning(
            "动态记忆 last4 新建来源轮查询失败 window_id=%s refs=%s error=%s",
            target_window_id,
            list(round_refs),
            e,
        )
        return set()


def _parse_memory_query_rewrite_output(content: str) -> list[str]:
    """解析 DS 返回的“消歧主查询 + 两条扩展”，并兼容旧三行纯文本。"""
    resolved = ""
    queries: list[str] = []
    fallback: list[str] = []
    for raw_line in str(content or "").splitlines():
        line = re.sub(r"^\d+[\.、\)\s]+", "", raw_line.strip(" -\t\r")).strip()
        if not line:
            continue
        matched = re.match(r"^(RESOLVED|QUERY)\s*[:：]\s*(.+)$", line, flags=re.IGNORECASE)
        if matched:
            value = matched.group(2).strip()
            if len(value) < 2:
                continue
            if matched.group(1).upper() == "RESOLVED":
                if not resolved:
                    resolved = value
            else:
                queries.append(value)
            continue
        fallback.append(line)

    candidates = [resolved, *queries] if resolved else fallback
    out: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate = candidate.strip()
        if len(candidate) < 2 or candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)
        if len(out) >= 3:
            break
    return out


def _parse_memory_query_state_output(content: str, previous_topic_state: dict | None = None) -> dict:
    """解析 query LLM 的 JSON；旧三行格式仅保留 queries 兼容，不覆盖 topic state。"""
    from storage.query_topic_state_store import normalize_topic_state

    raw = str(content or "").strip()
    if raw.startswith("```") and raw.endswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        queries: list[str] = []
        seen: set[str] = set()
        for value in parsed.get("queries") or []:
            query = str(value or "").strip()
            if len(query) < 2 or query in seen:
                continue
            seen.add(query)
            queries.append(query)
        state = normalize_topic_state(parsed.get("topic_state"))
        return {
            "topic_state": state or normalize_topic_state(previous_topic_state),
            "queries": queries,
            "format": "json",
        }
    return {
        "topic_state": normalize_topic_state(previous_topic_state),
        "queries": _parse_memory_query_rewrite_output(raw),
        "format": "legacy" if raw else "empty",
    }


def _rewrite_memory_query_state_with_ds(
    previous_four_rounds: str,
    user_message: str,
    previous_topic_state: dict | None = None,
    *,
    deepseek_api_key: str = DEEPSEEK_API_KEY,
    deepseek_api_url: str = DEEPSEEK_API_URL,
    requests_module=requests,
    logger_instance=logger,
    model: str = _MEMORY_QUERY_REWRITE_MODEL,
    parse_output: Callable[[str, dict | None], dict] = _parse_memory_query_state_output,
) -> dict:
    """
    用现有 query rewrite LLM 同时更新 session topic state 和检索 queries。
    失败时保留上轮 topic state、返回空 queries，由主流程沿用原查询。
    """
    from storage.query_topic_state_store import normalize_topic_state

    fallback = {
        "topic_state": normalize_topic_state(previous_topic_state),
        "queries": [],
        "format": "fallback",
    }
    if not (deepseek_api_key and deepseek_api_url):
        return fallback
    user_message = (user_message or "").strip()
    if not user_message:
        return fallback
    previous_state_json = json.dumps(
        normalize_topic_state(previous_topic_state),
        ensure_ascii=False,
    )
    prompt = (
        "你在帮我维护连续对话的当前讨论主题，并把当前消息整理成可用于召回既有记忆的检索 query。\n\n"
        "规则：\n"
        "1. 根据上轮 session_topic_state、当前消息之前的最近四轮对话和当前消息，更新本轮 topic_state，不得每轮从零猜。\n"
        "2. 当前消息明确切换话题时，按新话题更新 topic_state，不得让旧主题黏住当前消息。\n"
        "3. 以当前消息表达的新动作、新问题和新指代为最高优先级；上一轮主题只用于补全省略信息，不得覆盖当前消息。\n"
        "4. 无法读取图片内容时，不得把“这个、是谁、还记得吗”等指代强行绑定到附近文本名词；保留为待结合图片判断的对象。\n"
        "5. 当前消息是简短承接、回答、纠正、指代或省略时，只从最近且直接相关的上下文补全被省略的对象或事件。\n"
        "6. 当前消息已经有明确动作、对象或状态时，不得擅自把旧话题带进来。\n"
        "7. active_topic 概括当前持续讨论的主题；current_focus 只描述本轮正在推进、追问或纠正的具体焦点。\n"
        "8. anchors 只保留当前消息、最近四轮或上轮 topic_state 中已经出现，且能明确区分当前话题的人名、专名、项目名、机制名和核心概念。不得填写“事情、问题、感觉、关系、记忆”等泛词，不得编造新锚点。\n"
        "9. queries 第一条是消歧后的主查询，其余是围绕同一讨论主题的不同召回角度。保留具体实体、事件、状态、判断和修正关系。\n"
        "10. 不得补写对话中没有确认的原因、意图、偏好、关系或结果。\n"
        "11. 保持谁说、谁做，不得交换主语或把对方的称呼改成自称。\n"
        "12. queries 都是记忆检索陈述，不得写成“如何回复、怎么安慰、怎样处理”等回复生成任务。\n\n"
        "上轮 session_topic_state：\n"
        f"{previous_state_json}\n\n"
        "当前消息之前的最近四轮对话：\n"
        f"{previous_four_rounds or '（无）'}\n\n"
        "当前消息：\n"
        f"{user_message}\n\n"
        "只输出合法 JSON，不要 Markdown、代码块、标题或解释：\n"
        '{"topic_state":{"active_topic":"","current_focus":"","anchors":[]},"queries":[]}\n'
    )
    headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "thinking": {"type": "disabled"},
        "max_tokens": 1024,
    }
    try:
        r = requests_module.post(deepseek_api_url, headers=headers, json=payload, timeout=8)
        r.raise_for_status()
        data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        return parse_output(content, previous_topic_state)
    except Exception as e:
        logger_instance.debug("rewrite memory queries with DS failed: %s", e)
        return fallback


def _rewrite_memory_queries_with_ds(
    last_4_turns: str,
    user_message: str,
    *,
    rewrite_query_state: Callable[..., dict] = _rewrite_memory_query_state_with_ds,
) -> list[str]:
    """兼容旧调用与定向测试；新主链使用 topic-state 版本。"""
    result = rewrite_query_state(last_4_turns, user_message, {})
    return list(result.get("queries") or [])


def _multi_query_recall_and_rerank(
    base_query: str,
    expanded_queries: list[str],
    *,
    pool_limit: Optional[Callable[[], int]] = None,
    logger_instance=logger,
) -> list[dict]:
    """
    原始 query 保底 + 扩展 query 增广：
    - 召回：每个 query 各取 top10
    - 合并：按 memory_id 去重
    - 归一化：原始 query、扩展 query 与多 query 支撑度都压到 0..1
    - 宽候选：保留 reranker 可消费的候选池，不在这里提前裁成最终 5 条
    - 保护：至少保留 2 条原始 query 命中（如果有）
    """
    from memory_vector.dynamic_vector_retriever import dynamic_vector_retrieve

    pool_limit = pool_limit or _dynamic_recall_pool_limit

    base = (base_query or "").strip()
    if not base:
        return []
    queries = [base] + [q.strip() for q in (expanded_queries or []) if (q or "").strip() and q.strip() != base]
    query_hits: list[tuple[str, list[dict]]] = []
    for q in queries:
        try:
            hit = dynamic_vector_retrieve(q, vector_topk=10, final_topn=10, return_scores=True)
            query_hits.append((q, hit or []))
        except Exception as e:
            logger_instance.debug("dynamic_vector_retrieve failed query=%s err=%s", q[:40], e)
            query_hits.append((q, []))

    by_id: dict[str, dict] = {}
    source_count: dict[str, int] = {}
    expanded_semantic: dict[str, float] = {}
    base_semantic: dict[str, float] = {}
    base_hit_ids: list[str] = []
    for idx, (_q, items) in enumerate(query_hits):
        seen_local: set[str] = set()
        for mem in items or []:
            mid = str(mem.get("id") or "").strip()
            if not mid:
                continue
            sem = float(mem.get("_semantic_score") or 0.0)
            if mid not in by_id:
                by_id[mid] = mem
            if mid not in seen_local:
                source_count[mid] = int(source_count.get(mid) or 0) + 1
                seen_local.add(mid)
            if idx == 0 and mid not in base_hit_ids:
                base_semantic[mid] = max(base_semantic.get(mid, 0.0), sem)
                base_hit_ids.append(mid)
            elif idx > 0:
                expanded_semantic[mid] = max(expanded_semantic.get(mid, 0.0), sem)
    if not by_id:
        return []

    query_count = len(query_hits)
    scored: list[tuple[float, dict]] = []
    for mid, mem in by_id.items():
        sem_user_raw = base_semantic.get(mid, 0.0)
        sem_ctx_raw = expanded_semantic.get(mid, 0.0)
        sem_user = _normalize_semantic_score(sem_user_raw)
        sem_ctx = _normalize_semantic_score(sem_ctx_raw)
        semantic = max(sem_user, sem_ctx * 0.85)
        src = int(source_count.get(mid) or 0)
        support = _normalize_query_support(src, query_count)
        vector_score = semantic * 0.95 + support * 0.05
        scored_mem = dict(mem)
        scored_mem["_recall_score"] = {
            "total": round(vector_score, 4),
            "sem_user": round(sem_user, 4),
            "sem_ctx": round(sem_ctx, 4),
            "semantic": round(semantic, 4),
            "support": round(support, 4),
            "base_cosine_raw": round(float(sem_user_raw), 4),
            "expanded_cosine_raw": round(float(sem_ctx_raw), 4),
        }
        by_id[mid] = scored_mem
        scored.append((vector_score, scored_mem))
    scored.sort(key=lambda x: -x[0])

    ranked = [mem for _, mem in scored]

    # 原始 query 保底：如果扩展 query 数量很多，仍至少把两个原句命中带进宽候选池。
    base_keep = [by_id[mid] for mid in base_hit_ids if mid in by_id][:2]
    out: list[dict] = []
    used: set[str] = set()
    for m in base_keep + ranked:
        mid = str(m.get("id") or "")
        if not mid or mid in used:
            continue
        used.add(mid)
        out.append(m)
        if len(out) >= pool_limit():
            break
    return out


def _clamp_unit(value: float) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except Exception:
        return 0.0


def _dynamic_recall_pool_limit(*, dynamic_memory_top_n: int = DYNAMIC_MEMORY_TOP_N) -> int:
    from config import DYNAMIC_MEMORY_RERANK_MAX_CANDIDATES

    return max(1, int(dynamic_memory_top_n or 1), int(DYNAMIC_MEMORY_RERANK_MAX_CANDIDATES or 30))


def _normalize_semantic_score(value: float) -> float:
    """把已过向量门槛的 cosine 映射到 0..1；放宽门槛仍保留可比较的小正分。"""
    from memory_vector.config import VECTOR_MIN_SIM

    floor = _clamp_unit(float(VECTOR_MIN_SIM) - 0.06)
    if floor >= 1.0:
        return 0.0
    return _clamp_unit((float(value or 0.0) - floor) / (1.0 - floor))


def _normalize_query_support(source_count: int, query_count: int) -> float:
    if query_count <= 1:
        return 0.0
    return _clamp_unit((max(0, int(source_count)) - 1) / float(query_count - 1))


def _normalize_bm25_score(raw_score: float) -> float:
    """固定饱和映射，避免“本轮最强但仍很弱”的唯一命中被归一成 1。"""
    raw = max(0.0, float(raw_score or 0.0))
    return raw / (raw + 1.0) if raw > 0.0 else 0.0


def _mention_count_p95(memories: list[dict]) -> int:
    counts = sorted(max(0, int((mem or {}).get("mention_count") or 0)) for mem in memories or [])
    if not counts:
        return 0
    index = max(0, min(len(counts) - 1, math.ceil(len(counts) * 0.95) - 1))
    return counts[index]


def _normalized_memory_prior(mem: dict, mention_count_p95: int, now=None) -> float:
    """只用于相关候选间轻量排序；与物理淘汰使用的生命周期权重相互独立。"""
    from utils.time_aware import parse_iso_to_beijing, _now_beijing

    importance_norm = _clamp_unit(max(0, int((mem or {}).get("importance") or 0)) / 5.0)
    mention_count = max(0, int((mem or {}).get("mention_count") or 0))
    if mention_count_p95 > 0:
        mention_norm = _clamp_unit(math.log1p(mention_count) / math.log1p(max(1, mention_count_p95)))
    else:
        mention_norm = 0.0

    now = now or _now_beijing()
    last_mentioned = (mem or {}).get("last_mentioned") or (mem or {}).get("created_at") or ""
    dt = parse_iso_to_beijing(last_mentioned)
    days_since = max(0, (now - dt).days) if dt is not None else 0
    if days_since <= 15:
        recency_norm = 1.0
    else:
        recency_norm = _clamp_unit(1.0 - ((days_since - 15) / 20.0))
    return _clamp_unit(importance_norm * 0.60 + mention_norm * 0.25 + recency_norm * 0.15)


def _bm25_query_terms(keyword_candidates: list[dict]) -> list[BM25QueryTerm]:
    return [
        BM25QueryTerm(
            text=str((item or {}).get("text") or "").strip(),
            weight=2.0 if bool((item or {}).get("is_phrase")) else 1.0,
        )
        for item in keyword_candidates or []
        if str((item or {}).get("text") or "").strip()
    ]


def _bm25_recall_scores(
    query: str,
    keyword_candidates: list[dict],
    memories: list[dict],
) -> dict[str, dict]:
    ranked = bm25_score_documents(
        query,
        memories,
        lambda mem: _memory_keyword_search_text(mem),
        query_terms=_bm25_query_terms(keyword_candidates),
    )
    by_id: dict[str, dict] = {}
    for raw_score, mem in ranked:
        mid = str((mem or {}).get("id") or "").strip()
        if not mid or raw_score <= 0:
            continue
        old = by_id.get(mid)
        if old and float(old.get("raw") or 0.0) >= raw_score:
            continue
        by_id[mid] = {"raw": float(raw_score), "mem": mem}
    for item in by_id.values():
        item["norm"] = _normalize_bm25_score(float(item.get("raw") or 0.0))
    return by_id


def _merge_vector_and_bm25_recall(
    vector_recalled: list[dict],
    bm25_scores: dict[str, dict],
    *,
    pool_limit: Optional[Callable[[], int]] = None,
    memory_weight: Optional[Callable[[dict], float]] = None,
) -> list[dict]:
    """
    向量召回和 BM25 同时进入候选池，最后按一个融合分统一排序。
    BM25 只覆盖动态层；向量侧仍可带入 core:: pending。
    """
    pool_limit = pool_limit or _dynamic_recall_pool_limit
    memory_weight = memory_weight or _memory_weight
    by_id: dict[str, dict] = {}
    for mem in vector_recalled or []:
        mid = str((mem or {}).get("id") or "").strip()
        if not mid:
            continue
        score = mem.get("_recall_score") if isinstance(mem.get("_recall_score"), dict) else {}
        by_id[mid] = {
            "mem": mem,
            "sem_user": float(score["sem_user"] if "sem_user" in score else (mem.get("_semantic_score") or 0.0)),
            "sem_ctx": float(score["sem_ctx"] if "sem_ctx" in score else (mem.get("_semantic_score") or 0.0)),
            "semantic": float(score.get("semantic") or 0.0),
            "support": float(score.get("support") or 0.0),
            "vector_total": float(score.get("total") or mem.get("_final_score") or 0.0),
            "vector_hit": True,
            "bm25_raw": 0.0,
            "bm25_norm": 0.0,
        }

    for mid, item in (bm25_scores or {}).items():
        mem = item.get("mem") if isinstance(item, dict) else None
        if not isinstance(mem, dict):
            continue
        row = by_id.setdefault(
            mid,
            {
                "mem": mem,
                "sem_user": 0.0,
                "sem_ctx": 0.0,
                "semantic": 0.0,
                "support": 0.0,
                "vector_total": 0.0,
                "vector_hit": False,
                "bm25_raw": 0.0,
                "bm25_norm": 0.0,
            },
        )
        row["bm25_raw"] = max(float(row.get("bm25_raw") or 0.0), float(item.get("raw") or 0.0))
        row["bm25_norm"] = max(float(row.get("bm25_norm") or 0.0), float(item.get("norm") or 0.0))

    mention_count_p95 = _mention_count_p95([row["mem"] for row in by_id.values()])
    scored: list[tuple[float, float, dict]] = []
    for mid, row in by_id.items():
        mem = row["mem"]
        sem_user = _clamp_unit(float(row.get("sem_user") or 0.0))
        sem_ctx = _clamp_unit(float(row.get("sem_ctx") or 0.0))
        semantic = _clamp_unit(float(row.get("semantic") or max(sem_user, sem_ctx * 0.85)))
        support = _clamp_unit(float(row.get("support") or 0.0))
        bm25_norm = _clamp_unit(float(row.get("bm25_norm") or 0.0))
        memory_prior = _normalized_memory_prior(mem, mention_count_p95)
        recall_score = _clamp_unit(semantic * 0.70 + bm25_norm * 0.25 + support * 0.05)
        fallback_final = _clamp_unit(recall_score * 0.95 + memory_prior * 0.05)
        mem["_recall_score"] = {
            "total": round(float(recall_score), 4),
            "final_total": round(float(fallback_final), 4),
            "sem_user": round(float(sem_user), 4),
            "sem_ctx": round(float(sem_ctx), 4),
            "semantic": round(float(semantic), 4),
            "support": round(float(support), 4),
            "bm25": round(float(bm25_norm), 4),
            "bm25_raw": round(float(row.get("bm25_raw") or 0.0), 4),
            "memory_prior": round(float(memory_prior), 4),
            "lifecycle_weight": round(float(memory_weight(mem)), 4),
            "vector_total": round(float(row.get("vector_total") or 0.0), 4),
        }
        scored.append((fallback_final, recall_score, mem))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [mem for _, _, mem in scored[: pool_limit()]]


def _dynamic_memory_rerank_query(
    last_user_text: str,
    retrieval_query: str,
    messages: list[dict],
    resolved_query: str,
    expanded_queries: list[str],
    previous_four_rounds: str = "",
    topic_state: dict | None = None,
) -> str:
    parts = [f"当前消息：{(last_user_text or '').strip()}"]
    resolved = (resolved_query or "").strip()
    if resolved and resolved != (last_user_text or "").strip():
        parts.append(f"消歧主查询：{resolved}")
    rq = (retrieval_query or "").strip()
    if rq and rq not in {(last_user_text or "").strip(), resolved}:
        parts.append(f"检索短语：{rq}")
    eq = [q.strip() for q in (expanded_queries or []) if q and q.strip()]
    if eq:
        parts.append("扩展检索：" + "；".join(eq[:3]))
    turns_text = (previous_four_rounds or "").strip() or _last_4_turns_text_for_rewrite(messages)
    if turns_text:
        parts.append("近几轮上下文：" + turns_text[-800:])
    if topic_state:
        parts.append("当前讨论主题：" + json.dumps(topic_state, ensure_ascii=False))
    return "\n".join(parts)


def _dynamic_memory_rerank_document(mem: dict) -> str:
    content = str((mem or {}).get("content") or "").strip()
    retrieval_text = _memory_retrieval_text(mem)
    parts: list[str] = []
    if retrieval_text:
        parts.append(f"检索文本：{retrieval_text}")
    if content and content not in retrieval_text:
        parts.append(f"记忆正文：{content}")
    labels = []
    for key, label in (
        ("tag", "标签"),
        ("scene_type", "场景"),
        ("target_type", "对象"),
        ("emotion_label", "情绪"),
    ):
        value = str((mem or {}).get(key) or "").strip()
        if value:
            labels.append(f"{label}={value}")
    if labels:
        parts.append("元信息：" + " ".join(labels))
    return "\n".join(parts).strip()


def _select_dynamic_memory_rerank_candidates(
    recalled: list[dict],
    keyword_candidates: list[dict],
    pool_limit: int,
    input_limit: int = 20,
) -> tuple[list[dict], list[dict], dict]:
    """从宽候选池选出 reranker 输入；保留原融合排序，并优先纳入直接关键词命中。"""
    pool = list(recalled[: max(1, int(pool_limit))])
    limit = max(1, min(int(input_limit), len(pool))) if pool else 0
    direct_mems = [mem for mem in pool if _direct_keyword_hit(mem, keyword_candidates)]
    selected_direct = direct_mems[:limit]
    selected_ids = {str((mem or {}).get("id") or "") for mem in selected_direct}
    remaining_slots = max(0, limit - len(selected_direct))
    for mem in pool:
        mid = str((mem or {}).get("id") or "")
        if mid in selected_ids:
            continue
        if remaining_slots <= 0:
            break
        selected_ids.add(mid)
        remaining_slots -= 1

    selected = [mem for mem in pool if str((mem or {}).get("id") or "") in selected_ids]
    unevaluated = [mem for mem in pool if str((mem or {}).get("id") or "") not in selected_ids]
    unevaluated.extend(recalled[len(pool) :])
    return selected, unevaluated, {
        "candidate_pool_count": len(pool),
        "rerank_input_limit": int(input_limit),
        "rerank_input_count": len(selected),
        "direct_keyword_candidate_count": len(direct_mems),
        "direct_keyword_selected_count": len(selected_direct),
    }


def _filter_dynamic_memory_timeout_fallback(
    recalled: list[dict],
    keyword_candidates: list[dict],
    min_score: float,
) -> list[dict]:
    """reranker 超时时复用现有融合分和门槛，不把宽候选直接当最终结果。"""
    scored: list[tuple[float, float, dict]] = []
    for mem in recalled or []:
        old_score = mem.get("_recall_score") if isinstance(mem.get("_recall_score"), dict) else {}
        fallback_base = _clamp_unit(float(old_score.get("final_total") or old_score.get("total") or 0.0))
        matched_keyword = _direct_keyword_hit(mem, keyword_candidates)
        direct_keyword_bonus = 0.15 if matched_keyword else 0.0
        final_score = _clamp_unit(fallback_base + direct_keyword_bonus)
        if final_score < float(min_score):
            continue
        merged_score = dict(old_score)
        merged_score.update(
            {
                "fallback_base_score": round(fallback_base, 4),
                "direct_keyword": matched_keyword,
                "direct_keyword_bonus": round(direct_keyword_bonus, 4),
                "final_total": round(final_score, 4),
                "rerank_fallback": "timeout",
            }
        )
        mem["_recall_score"] = merged_score
        scored.append((final_score, _clamp_unit(float(old_score.get("memory_prior") or 0.0)), mem))
    scored.sort(key=lambda item: (-item[0], -item[1]))
    return [mem for _, _, mem in scored]


def _apply_external_dynamic_memory_rerank(
    recalled: list[dict],
    last_user_text: str,
    retrieval_query: str,
    messages: list[dict],
    resolved_query: str,
    expanded_queries: list[str],
    recall_source: str,
    keyword_candidates: list[dict] | None = None,
    previous_four_rounds: str = "",
    topic_state: dict | None = None,
    *,
    rerank_query_builder: Callable[..., str] = _dynamic_memory_rerank_query,
    rerank_document_builder: Callable[[dict], str] = _dynamic_memory_rerank_document,
    select_candidates: Callable[..., tuple[list[dict], list[dict], dict]] = _select_dynamic_memory_rerank_candidates,
    timeout_fallback: Callable[..., list[dict]] = _filter_dynamic_memory_timeout_fallback,
    logger_instance=logger,
) -> tuple[list[dict], str, dict]:
    if not recalled:
        return recalled, recall_source, {"enabled": False, "reason": "empty_recalled"}
    try:
        from config import DYNAMIC_MEMORY_RERANK_MAX_CANDIDATES
        from memory_vector.config import RERANK_MIN_SCORE
        from services.dynamic_memory_reranker import dynamic_memory_rerank_enabled, rerank_dynamic_memory_documents

        if not dynamic_memory_rerank_enabled():
            return recalled, recall_source, {"enabled": False, "reason": "disabled"}

        max_candidates = max(1, int(DYNAMIC_MEMORY_RERANK_MAX_CANDIDATES or 30))
        candidate_mems, tail_mems, selection_debug = select_candidates(
            recalled,
            keyword_candidates or [],
            max_candidates,
            input_limit=20,
        )
        query = rerank_query_builder(
            last_user_text,
            retrieval_query,
            messages,
            resolved_query,
            expanded_queries,
            previous_four_rounds,
            topic_state,
        )
        docs = [
            {
                "memory_id": str((mem or {}).get("id") or ""),
                "text": rerank_document_builder(mem),
                "hybrid_score": float(((mem.get("_recall_score") or {}).get("total") or 0.0)),
            }
            for mem in candidate_mems
        ]
        result = rerank_dynamic_memory_documents(query, docs)
        if not result.get("ok"):
            if str(result.get("reason") or "") == "timeout":
                fallback = timeout_fallback(
                    recalled,
                    keyword_candidates or [],
                    float(RERANK_MIN_SCORE),
                )
                debug = dict(result)
                debug.update(selection_debug)
                debug["final_score_threshold"] = float(RERANK_MIN_SCORE)
                debug["relevant_count"] = len(fallback)
                debug["rejected_count"] = max(0, len(recalled) - len(fallback))
                debug["unevaluated_count"] = len(tail_mems)
                return fallback, recall_source, debug
            return recalled, recall_source, result

        score_weights = {
            "rerank": 0.45,
            "semantic": 0.30,
            "bm25": 0.15,
            "support": 0.05,
            "memory_prior": 0.05,
        }
        direct_keyword_bonus_value = 0.15
        scored: list[tuple[float, float, dict]] = []
        for item in result.get("ranked") or []:
            try:
                idx = int(item.get("index"))
            except Exception:
                continue
            if idx < 0 or idx >= len(candidate_mems):
                continue
            mem = candidate_mems[idx]
            score = _clamp_unit(float(item.get("score") or 0.0))
            old_score = mem.get("_recall_score") if isinstance(mem.get("_recall_score"), dict) else {}
            recall_score = _clamp_unit(float(old_score.get("total") or 0.0))
            semantic_score = _clamp_unit(float(old_score.get("semantic") or 0.0))
            bm25_score = _clamp_unit(float(old_score.get("bm25") or 0.0))
            support_score = _clamp_unit(float(old_score.get("support") or 0.0))
            memory_prior = _clamp_unit(float(old_score.get("memory_prior") or 0.0))
            matched_keyword = _direct_keyword_hit(mem, keyword_candidates or [])
            direct_keyword_bonus = direct_keyword_bonus_value if matched_keyword else 0.0
            base_score = _clamp_unit(
                score * score_weights["rerank"]
                + semantic_score * score_weights["semantic"]
                + bm25_score * score_weights["bm25"]
                + support_score * score_weights["support"]
                + memory_prior * score_weights["memory_prior"]
            )
            final_score = _clamp_unit(base_score + direct_keyword_bonus)
            if final_score < float(RERANK_MIN_SCORE):
                continue
            merged_score = dict(old_score)
            merged_score.update(
                {
                    "hybrid_total": round(recall_score, 4),
                    "rerank": round(score, 4),
                    "rerank_rank": int(item.get("rank") or 0),
                    "rerank_model": str(result.get("model") or ""),
                    "base_score": round(base_score, 4),
                    "direct_keyword": matched_keyword,
                    "direct_keyword_bonus": round(direct_keyword_bonus, 4),
                    "final_total": round(final_score, 4),
                }
            )
            mem["_recall_score"] = merged_score
            scored.append((final_score, memory_prior, mem))

        scored.sort(key=lambda x: (-x[0], -x[1]))
        reranked = [mem for _, _, mem in scored]
        debug = dict(result)
        debug["ranked"] = (result.get("ranked") or [])[:10]
        debug["score_weights"] = score_weights
        debug["direct_keyword_bonus"] = direct_keyword_bonus_value
        debug["final_score_threshold"] = float(RERANK_MIN_SCORE)
        debug["relevant_count"] = len(reranked)
        debug["rejected_count"] = max(0, len(candidate_mems) - len(reranked))
        debug["unevaluated_count"] = len(tail_mems)
        debug.update(selection_debug)
        return reranked, f"{recall_source}+rerank", debug
    except Exception as e:
        logger_instance.warning("动态记忆外部 rerank 失败，回退原排序 error=%s", e)
        return recalled, recall_source, {"enabled": True, "ok": False, "reason": "exception", "error": str(e)[:160]}


def _memory_recall_sort_score(mem: dict) -> float:
    score = mem.get("_recall_score") if isinstance((mem or {}).get("_recall_score"), dict) else {}
    value = score.get("final_total")
    if value is None:
        value = score.get("total") or 0.0
    try:
        return float(value)
    except Exception:
        return 0.0


def _memory_recall_prior(mem: dict) -> float:
    score = mem.get("_recall_score") if isinstance((mem or {}).get("_recall_score"), dict) else {}
    return _clamp_unit(float(score.get("memory_prior") or 0.0))


def _memory_dedupe_keys(mem: dict) -> list[str]:
    if not isinstance(mem, dict):
        return []
    keys: list[str] = []
    mid = str(mem.get("id") or "").strip()
    source_mid = str(mem.get("source_memory_id") or "").strip()
    if source_mid:
        keys.append(f"id:{source_mid}")
    if mid:
        origin_mid = mid[len("core::") :] if mid.startswith("core::") else mid
        if origin_mid:
            keys.append(f"id:{origin_mid}")
    content = " ".join(str(mem.get("content") or "").split()).strip().lower()
    if len(content) >= 20:
        keys.append(f"content:{content}")
    return keys


def _prefer_recalled_memory(new_mem: dict, old_mem: dict) -> bool:
    new_id = str((new_mem or {}).get("id") or "")
    old_id = str((old_mem or {}).get("id") or "")
    if new_id.startswith("core::") and not old_id.startswith("core::"):
        return True
    return False


def _dedupe_recalled_memories(memories: list[dict]) -> list[dict]:
    """
    跨动态层与核心缓存层去重。
    同一条动态记忆进入 core_cache 后，召回可能同时命中 `id` 与 `core::id`；
    注入时只保留一条，优先保留核心缓存版本。
    """
    out: list[dict] = []
    seen: dict[str, int] = {}
    for mem in memories or []:
        if not isinstance(mem, dict):
            continue
        keys = _memory_dedupe_keys(mem)
        dup_indexes = [seen[k] for k in keys if k in seen]
        if not dup_indexes:
            out.append(mem)
            idx = len(out) - 1
            for k in keys:
                seen[k] = idx
            continue
        idx = min(dup_indexes)
        if _prefer_recalled_memory(mem, out[idx]):
            old_keys = _memory_dedupe_keys(out[idx])
            out[idx] = mem
            for k in old_keys + keys:
                seen[k] = idx
    return out


def _memory_weight(m: dict, now=None) -> float:
    """兼容现有调用；实际公式统一由共享模块维护。"""
    return dynamic_memory_weight(m, now=now)


def _append_dynamic_recall_debug_event_safe(
    event: dict,
    *,
    r2_store_module=r2_store,
    logger_instance=logger,
) -> None:
    try:
        ok = r2_store_module.append_dynamic_recall_debug_event(event)
        if not ok:
            logger_instance.warning(
                "动态记忆调试事件未落盘 window_id=%s reason=%s source=%s",
                str((event or {}).get("window_id") or ""),
                str((event or {}).get("reason") or ""),
                str((event or {}).get("source") or ""),
            )
    except Exception as e:
        logger_instance.warning(
            "动态记忆调试事件写入异常 window_id=%s reason=%s source=%s error=%s",
            str((event or {}).get("window_id") or ""),
            str((event or {}).get("reason") or ""),
            str((event or {}).get("source") or ""),
            e,
        )


def _canonical_memory_id(memory_id: str) -> str:
    mid = str(memory_id or "").strip()
    return mid[len("core::") :] if mid.startswith("core::") else mid


def _memory_event_timestamp(mem: dict) -> str:
    """事件发生/内容更新时间；不要用 last_mentioned，它只是最近被引用时间。"""
    return str(
        (mem or {}).get("updated_at")
        or (mem or {}).get("created_at")
        or (mem or {}).get("promoted_at")
        or (mem or {}).get("last_mentioned")
        or ""
    ).strip()


def _build_sqlite_shadow_compare(
    *,
    query: str,
    retrieval_query: str,
    keywords: list[str],
    actual_ids: list[str],
    valid_memory_ids: set[str],
    enabled: bool = DYNAMIC_MEMORY_MIRROR_SHADOW_ENABLED,
    dynamic_memory_top_n: int = DYNAMIC_MEMORY_TOP_N,
) -> dict:
    if not enabled:
        return {"enabled": False, "reason": "disabled"}
    try:
        from storage import dynamic_memory_mirror_store

        shadow_query = " ".join(
            x
            for x in [
                str(query or "").strip(),
                str(retrieval_query or "").strip(),
            ]
            if x
        ).strip()
        result = dynamic_memory_mirror_store.shadow_candidates(
            shadow_query,
            keywords=keywords,
            limit=max(10, dynamic_memory_top_n * 4),
        )
        candidates = result.get("candidates") if isinstance(result, dict) else []
        candidates = [c for c in (candidates or []) if isinstance(c, dict)]
        candidate_ids = [
            _canonical_memory_id(str((item or {}).get("memory_id") or ""))
            for item in candidates
            if str((item or {}).get("memory_id") or "").strip()
        ]
        actual_canonical = [
            _canonical_memory_id(x)
            for x in actual_ids or []
            if _canonical_memory_id(x)
        ]
        actual_set = set(actual_canonical)
        candidate_set = set(candidate_ids)
        valid_set = {_canonical_memory_id(x) for x in (valid_memory_ids or set()) if _canonical_memory_id(x)}
        stale_ids = [mid for mid in candidate_ids if mid and mid not in valid_set]
        overlap_ids = [mid for mid in candidate_ids if mid and mid in actual_set]
        missed_actual_ids = [mid for mid in actual_canonical if mid and mid not in candidate_set]
        clean_candidates = []
        for item in candidates[:20]:
            mid = _canonical_memory_id(str(item.get("memory_id") or ""))
            clean_candidates.append(
                {
                    "memory_id": mid,
                    "content": str(item.get("content") or "")[:120],
                    "tag": str(item.get("tag") or ""),
                    "score": float(item.get("score") or 0.0),
                    "high_signal_count": int(item.get("high_signal_count") or 0),
                    "reasons": item.get("reasons") or [],
                    "matched_terms": item.get("matched_terms") or [],
                    "in_actual": mid in actual_set,
                    "in_r2_valid": mid in valid_set,
                }
            )
        return {
            "enabled": True,
            "ok": bool(result.get("ok")) if isinstance(result, dict) else False,
            "query_terms": (result or {}).get("query_terms") or [],
            "candidate_count": len(candidate_ids),
            "candidate_ids": candidate_ids[:20],
            "actual_ids": actual_canonical[:20],
            "overlap_ids": overlap_ids[:20],
            "missed_actual_ids": missed_actual_ids[:20],
            "stale_candidate_ids": stale_ids[:20],
            "overlap_count": len(overlap_ids),
            "missed_actual_count": len(missed_actual_ids),
            "stale_candidate_count": len(stale_ids),
            "candidates": clean_candidates,
        }
    except Exception as e:
        return {"enabled": True, "ok": False, "error": str(e)}


def _replace_recall_candidate_ids(target: Optional[list[str]], candidates: list[dict]) -> None:
    if target is None:
        return
    target[:] = [
        memory_id
        for mem in candidates or []
        if (memory_id := str((mem or {}).get("id") or "").strip())
    ]


def _replace_recall_topic_state(target: Optional[dict], topic_state: dict) -> None:
    if target is None:
        return
    target.clear()
    target.update(topic_state or {})


def step_inject_dynamic_memory(
    body: dict,
    window_id: str,
    *,
    use_recall_cache: bool = True,
    recall_candidate_ids_out: Optional[list[str]] = None,
    recall_topic_state_out: Optional[dict] = None,
    dynamic_memory_top_n: int,
    r2_store_module,
    prune_dynamic_memories: Callable[[list, list], list],
    is_memory_meta_query: Callable[[str], bool],
    is_trivial_user_message: Callable[[str], bool],
    extract_keyword_candidates: Callable[[str], list[dict]],
    previous_four_rounds_text: Callable[[str], str],
    rewrite_query_state: Callable[[str, str, dict | None], dict],
    topic_anchor_candidates: Callable[[dict, str], list[dict]],
    build_retrieval_text: Callable[[str], str],
    strip_memory_query_media_placeholders: Callable[[str], str],
    recall_cache_hit: Callable[[str, list[str], set[str]], dict | None],
    recall_cache_set: Callable[[str, list[str], list[dict], str, set[str]], None],
    dedupe_recalled_memories: Callable[[list[dict]], list[dict]],
    multi_query_recall_and_rerank: Callable[[str, list[str]], list[dict]],
    bm25_recall_scores: Callable[[str, list[dict], list[dict]], dict[str, dict]],
    merge_vector_and_bm25_recall: Callable[[list[dict], dict[str, dict]], list[dict]],
    external_rerank: Callable[..., tuple[list[dict], str, dict]],
    memory_recall_sort_score: Callable[[dict], float],
    memory_recall_prior: Callable[[dict], float],
    append_recall_debug_event: Callable[[dict], None],
    build_sqlite_shadow_compare: Callable[..., dict],
    dynamic_budget: Callable[[], int],
    token_estimator: Callable[[str], int],
    append_dynamic_system: Callable[[dict, str], dict],
    logger_instance=logger,
) -> dict:
    """
    每轮对话开始前：从 R2 读动态层，用向量召回 + BM25 关键词召回融合排序后注入 system 末尾。
    DYNAMIC_MEMORY_TOP_N<=0 时不注入、不调向量检索，便于测试延迟。
    """
    _replace_recall_candidate_ids(recall_candidate_ids_out, [])
    _replace_recall_topic_state(recall_topic_state_out, {})
    if dynamic_memory_top_n <= 0:
        return body
    du_request_id = normalize_debug_request_id((body or {}).get(DU_REQUEST_ID_BODY_KEY))
    memories = r2_store_module.get_dynamic_memory_list()
    core_pending = r2_store_module.get_core_cache_pending() or []
    if not memories and not core_pending:
        return body
    from utils.time_aware import now_beijing_iso

    memories = prune_dynamic_memories(memories, core_pending)
    messages = body.get("messages") or []
    # 取最后一条 user 内容做关键词
    last_user_text = ""
    for m in reversed(messages):
        if (m.get("role") or "").lower() == "user":
            content = m.get("content")
            if isinstance(content, str):
                last_user_text = content
            elif isinstance(content, list):
                last_user_text = " ".join(
                    str(c.get("text") or "")
                    for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ).strip()
            break
    # 元问题：不要触发动态记忆（避免”问记忆→召回一堆含记忆字样的记忆”）
    if is_memory_meta_query(last_user_text):
        return body
    # 短消息 / 日常闲聊跳过检索，省 token
    if is_trivial_user_message(last_user_text):
        return body
    original_keyword_candidates = extract_keyword_candidates(last_user_text)
    previous_four_rounds = previous_four_rounds_text(window_id)
    excluded_source_ids = _recent_round_created_memory_ids(
        window_id,
        previous_four_rounds,
        logger_instance=logger_instance,
    )
    if excluded_source_ids:
        memories = _exclude_memories_created_in_recent_rounds(memories, excluded_source_ids)
        core_pending = _exclude_memories_created_in_recent_rounds(core_pending, excluded_source_ids)
        logger_instance.info(
            "动态记忆召回排除 last4 新建来源 window_id=%s rounds=%s memory_count=%s",
            window_id,
            list(getattr(previous_four_rounds, "round_indexes", ()) or ()),
            len(excluded_source_ids),
        )
    if not memories and not core_pending:
        return body
    from storage import query_topic_state_store

    previous_topic_state = query_topic_state_store.get_topic_state(window_id)
    topic_state_observed_at = time.time()
    rewrite_result = rewrite_query_state(
        previous_four_rounds,
        last_user_text,
        previous_topic_state,
    )
    rewritten_queries = list(rewrite_result.get("queries") or [])
    resolved_query = rewritten_queries[0] if rewritten_queries else ""
    expanded_queries = rewritten_queries[1:3]
    topic_state = dict(rewrite_result.get("topic_state") or previous_topic_state or {})
    if rewrite_result.get("format") == "json" and topic_state:
        query_topic_state_store.save_topic_state(
            window_id,
            topic_state,
            observed_at=topic_state_observed_at,
        )
    _replace_recall_topic_state(recall_topic_state_out, topic_state)

    topic_anchor_evidence = "\n".join(
        [
            json.dumps(previous_topic_state or {}, ensure_ascii=False),
            previous_four_rounds,
            last_user_text,
        ]
    )
    anchor_candidates = topic_anchor_candidates(topic_state, topic_anchor_evidence)
    keyword_candidates: list[dict] = []
    seen_keyword_candidates: set[str] = set()
    for item in [*anchor_candidates, *original_keyword_candidates]:
        keyword = str((item or {}).get("text") or "").strip()
        if not keyword or keyword in seen_keyword_candidates:
            continue
        seen_keyword_candidates.add(keyword)
        keyword_candidates.append(item)
    keywords = [str((item or {}).get("text") or "").strip() for item in keyword_candidates]
    keyword_debug = [
        {
            "text": str((item or {}).get("text") or "").strip(),
            "is_phrase": bool((item or {}).get("is_phrase")),
            "source": str((item or {}).get("source") or "keyword_extractor"),
        }
        for item in keyword_candidates
        if str((item or {}).get("text") or "").strip()
    ]
    retrieval_query = build_retrieval_text(last_user_text)
    bm25_query = strip_memory_query_media_placeholders(resolved_query or last_user_text)
    valid_memory_ids = {str(mem.get("id") or "").strip() for mem in memories if str(mem.get("id") or "").strip()}

    # query rewrite 每轮先更新 topic state；缓存只复用召回结果，不再跳过话题理解。
    cached = recall_cache_hit(window_id, keywords, excluded_source_ids) if use_recall_cache else None
    if cached is not None:
        active_core_by_id = {
            f"core::{str((item or {}).get('id') or '').strip()}": item
            for item in core_pending
            if str((item or {}).get("id") or "").strip()
        }
        active_core_ids = set(active_core_by_id)
        dynamic_by_id = {
            str((item or {}).get("id") or "").strip(): item
            for item in memories
            if str((item or {}).get("id") or "").strip()
        }
        cached_results = [
            mem
            for mem in (cached.get("results") or [])
            if (
                str((mem or {}).get("id") or "") in active_core_ids
                if str((mem or {}).get("id") or "").startswith("core::")
                else str((mem or {}).get("id") or "") in valid_memory_ids
            )
        ]
        cached_content_stale = any(
            str((mem or {}).get("content") or "").strip()
            != str(
                (
                    active_core_by_id.get(str((mem or {}).get("id") or ""))
                    if str((mem or {}).get("id") or "").startswith("core::")
                    else dynamic_by_id.get(str((mem or {}).get("id") or ""))
                ).get("content")
                or ""
            ).strip()
            for mem in cached_results
        )
        if not cached_results or cached_content_stale:
            _RECALL_CACHE.pop(window_id, None)
            cached = None
    if cached is not None:
        recalled = dedupe_recalled_memories(cached_results)
        _replace_recall_candidate_ids(recall_candidate_ids_out, recalled)
        recall_source = str(cached.get("source") or "hybrid")
        vector_error = ""
        rerank_cache_hit = "+rerank" in recall_source
        rerank_debug = {"enabled": rerank_cache_hit, "ok": rerank_cache_hit, "reason": "cache_hit"}
        logger_instance.info("动态记忆检索缓存命中 window_id=%s keywords=%d results=%d", window_id, len(keywords), len(recalled))
    else:
        # 向量召回 + BM25 关键词召回同时进行，最后进入同一候选池融合排序。
        vector_recalled: list[dict] = []
        vector_error = ""
        try:
            vector_queries = [query for query in [resolved_query, *expanded_queries] if query]
            vector_recalled = multi_query_recall_and_rerank(last_user_text, vector_queries)
            if vector_recalled:
                valid_ids = {str(mem.get("id")) for mem in memories if mem.get("id")}
                vector_recalled = [
                    mem for mem in vector_recalled
                    if not _memory_has_excluded_source(mem, excluded_source_ids)
                    and (
                        # 动态层：只要求条目仍存在，不再按独立天数二次过滤。
                        str(mem.get("id") or "") in valid_ids
                        # 核心缓存层：dynamic_vector_retriever 产出的临时 id 形如 core::<entry_id>。
                        or str(mem.get("id") or "").startswith("core::")
                    )
                ]
                vector_recalled = dedupe_recalled_memories(vector_recalled)
        except Exception as e:
            vector_error = str(e)
            logger_instance.warning("dynamic_vector_retrieve 失败，仍保留 BM25 召回 error=%s", e)

        bm25_keyword_candidates: list[dict] = []
        seen_bm25_keywords: set[str] = set()
        for item in [*extract_keyword_candidates(bm25_query), *keyword_candidates]:
            text = str((item or {}).get("text") or "").strip()
            if not text or text in seen_bm25_keywords:
                continue
            seen_bm25_keywords.add(text)
            bm25_keyword_candidates.append(item)
        bm25_scores = bm25_recall_scores(bm25_query, bm25_keyword_candidates, memories)
        recalled = dedupe_recalled_memories(merge_vector_and_bm25_recall(vector_recalled, bm25_scores))
        _replace_recall_candidate_ids(recall_candidate_ids_out, recalled)
        has_vector = any(float(((m.get("_recall_score") or {}).get("sem_user") or 0.0)) > 0 for m in recalled)
        has_bm25 = any(float(((m.get("_recall_score") or {}).get("bm25") or 0.0)) > 0 for m in recalled)
        if has_vector and has_bm25:
            recall_source = "hybrid"
        elif has_vector:
            recall_source = "vector"
        elif has_bm25:
            recall_source = "keyword"
        else:
            recall_source = "keyword" if vector_error else "hybrid"

        recalled, recall_source, rerank_debug = external_rerank(
            recalled,
            last_user_text,
            retrieval_query,
            messages,
            resolved_query,
            expanded_queries,
            recall_source,
            bm25_keyword_candidates,
            previous_four_rounds,
            topic_state,
        )
        rerank_reason = str((rerank_debug or {}).get("reason") or "")
        rerank_attempted = bool((rerank_debug or {}).get("enabled"))
        cacheable_recall = (not rerank_attempted) or rerank_reason in (
            "disabled",
            "missing_api_key",
            "unsafe_api_url",
            "empty_documents",
            "empty_query",
        )
        if use_recall_cache and cacheable_recall:
            recall_cache_set(
                window_id,
                keywords,
                recalled,
                recall_source,
                excluded_source_ids,
            )

        if not recalled:
            event = {
                "timestamp": now_beijing_iso(),
                "window_id": (window_id or "").strip() or "__default__",
                "query": (last_user_text or "").strip(),
                "keywords": keywords,
                "keyword_debug": keyword_debug,
                "retrieval_query": retrieval_query,
                "resolved_query": resolved_query,
                "bm25_query": bm25_query,
                "source": recall_source,
                "expanded_queries": expanded_queries,
                "topic_state": topic_state,
                "previous_four_rounds": previous_four_rounds,
                "query_rewrite_format": str(rewrite_result.get("format") or ""),
                "recalled_lines": [],
                "recalled_count": 0,
                "reason": "no_hybrid_recall_hit",
                "vector_error": vector_error,
                "rerank": rerank_debug,
                "sqlite_shadow": build_sqlite_shadow_compare(
                    query=last_user_text,
                    retrieval_query=retrieval_query,
                    keywords=keywords,
                    actual_ids=[],
                    valid_memory_ids=valid_memory_ids,
                ),
            }
            if du_request_id:
                event["du_request_id"] = du_request_id
            append_recall_debug_event(event)
            return body

    scored = [(memory_recall_sort_score(mem), memory_recall_prior(mem), mem) for mem in recalled]
    scored.sort(key=lambda x: (-x[0], -x[1]))

    budget = dynamic_budget()
    def _fuzzy_time_label(mem: dict) -> str:
        from utils.time_aware import parse_iso_to_beijing, _now_beijing

        def _daypart(dt) -> str:
            hour = dt.hour
            if hour < 6:
                return "凌晨"
            if hour < 11:
                return "上午"
            if hour < 14:
                return "中午"
            if hour < 18:
                return "下午"
            if hour < 22:
                return "晚上"
            return "深夜"

        dt = parse_iso_to_beijing(_memory_event_timestamp(mem))
        if dt is None:
            return "之前"
        now_dt = _now_beijing()
        days = max(0, (now_dt.date() - dt.date()).days)
        daypart = _daypart(dt)
        if days == 0:
            return f"今天{daypart}"
        if days == 1:
            return f"昨天{daypart}"
        if days == 2:
            return f"前天{daypart}"
        if days <= 4:
            return f"{days}天前{daypart}"
        if days <= 9:
            return f"几天前{daypart}"
        return "好些天前"

    lines = []
    recalled_items = []
    citation_map: dict[str, str] = {}
    for t in scored[: max(1, dynamic_memory_top_n)]:
        mem = t[2]
        mid = str(mem.get("id") or "").strip()
        citation_label = ""
        if mid:
            citation_label = str(len(citation_map) + 1)
        citation_prefix = f"[memory {citation_label}] " if citation_label else ""
        line = f"- {citation_prefix}[{_fuzzy_time_label(mem)}] {mem.get('content', '').strip()}"
        new_text = "\n".join(lines) + ("\n" + line if lines else line)
        if token_estimator(new_text) > budget:
            break
        lines.append(line)
        recalled_items.append(
            {
                "label": citation_label,
                "memory_id": mid,
                "source": "core_cache" if mid.startswith("core::") else "dynamic_memory",
                "content": str(mem.get("content") or "").strip(),
                "line": line,
                "tag": str(mem.get("tag") or "").strip(),
                "emotion_label": str(mem.get("emotion_label") or "").strip(),
                "scene_type": str(mem.get("scene_type") or "").strip(),
                "target_type": str(mem.get("target_type") or "").strip(),
                "importance": int(mem.get("importance") or 0),
                "mention_count": int(mem.get("mention_count") or 0),
                "created_at": str(mem.get("created_at") or "").strip(),
                "updated_at": str(mem.get("updated_at") or "").strip(),
                "last_mentioned": str(mem.get("last_mentioned") or mem.get("created_at") or "").strip(),
            }
        )
        if citation_label:
            citation_map[citation_label] = mid
    if not lines:
        # 召回有候选但受预算/过滤后未注入：记录原因
        event = {
            "timestamp": now_beijing_iso(),
            "window_id": (window_id or "").strip() or "__default__",
            "query": (last_user_text or "").strip(),
            "keywords": keywords,
            "keyword_debug": keyword_debug,
            "retrieval_query": retrieval_query,
            "resolved_query": resolved_query,
            "bm25_query": bm25_query,
            "source": recall_source,
            "expanded_queries": expanded_queries,
            "topic_state": topic_state,
            "previous_four_rounds": previous_four_rounds,
            "query_rewrite_format": str(rewrite_result.get("format") or ""),
            "recalled_lines": [],
            "recalled_count": 0,
            "reason": "empty_after_budget_or_filter",
            "vector_error": vector_error,
            "rerank": rerank_debug,
            "sqlite_shadow": build_sqlite_shadow_compare(
                query=last_user_text,
                retrieval_query=retrieval_query,
                keywords=keywords,
                actual_ids=[],
                valid_memory_ids=valid_memory_ids,
            ),
        }
        if du_request_id:
            event["du_request_id"] = du_request_id
        append_recall_debug_event(event)
        return body
    # 收集注入记忆的 score 明细
    injected_scores = []
    for t in scored[: len(lines)]:
        mem = t[2]
        s = mem.get("_recall_score")
        if s:
            injected_scores.append(
                {
                    "id": str(mem.get("id") or ""),
                    "content": (mem.get("content") or "")[:60],
                    "retrieval_text": str(mem.get("retrieval_text") or "")[:60],
                    **s,
                }
            )
    event = {
        "timestamp": now_beijing_iso(),
        "window_id": (window_id or "").strip() or "__default__",
        "query": (last_user_text or "").strip(),
        "keywords": keywords,
        "keyword_debug": keyword_debug,
        "retrieval_query": retrieval_query,
        "resolved_query": resolved_query,
        "bm25_query": bm25_query,
        "source": recall_source,
        "expanded_queries": expanded_queries,
        "topic_state": topic_state,
        "previous_four_rounds": previous_four_rounds,
        "query_rewrite_format": str(rewrite_result.get("format") or ""),
        "recalled_lines": lines,
        "recalled_items": recalled_items,
        "recalled_count": len(lines),
        "scores": injected_scores,
        "rerank": rerank_debug,
        "citation_map": citation_map,
        "sqlite_shadow": build_sqlite_shadow_compare(
            query=last_user_text,
            retrieval_query=retrieval_query,
            keywords=keywords,
            actual_ids=[str((item or {}).get("memory_id") or "") for item in recalled_items],
            valid_memory_ids=valid_memory_ids,
        ),
    }
    if du_request_id:
        event["du_request_id"] = du_request_id
    append_recall_debug_event(event)
    citation_hint = ""
    if citation_map:
        citation_hint = (
            "\n如果回复实际参考了某条记忆，请在相关句尾写对应标记（如 [memory 1]）；"
        )
    inject = "\n\n听了老婆的话，我想起来了一些之前的事——\n" + "\n".join(lines) + "\n【以上为可召回记忆】" + citation_hint
    body = append_dynamic_system(body, inject)
    if citation_map:
        body[DYNAMIC_MEMORY_CITATION_MAP_BODY_KEY] = citation_map
    return body


def recall_dynamic_memory(
    body: dict,
    window_id: str,
    *,
    use_recall_cache: bool = True,
    **dependencies,
) -> RecallResult:
    candidate_ids: list[str] = []
    topic_state: dict = {}
    result_body = step_inject_dynamic_memory(
        body,
        window_id,
        use_recall_cache=use_recall_cache,
        recall_candidate_ids_out=candidate_ids,
        recall_topic_state_out=topic_state,
        **dependencies,
    )
    return RecallResult(
        body=result_body,
        candidate_ids=list(candidate_ids),
        topic_state=dict(topic_state),
    )
