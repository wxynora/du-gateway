from __future__ import annotations

from typing import Optional

from memory_vector.config import VECTOR_MIN_SIM, VECTOR_TOPK, VECTOR_TOPN
from memory_vector.cosine import cosine
from memory_vector.embedding_client import embed_text
from memory_vector.vector_index_store import load_index
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import parse_iso_to_beijing, _now_beijing

logger = get_logger(__name__)


ROOM_TAGS = ("客厅", "书房", "图书馆", "卧室")


def _memory_weight(m: dict) -> float:
    """
    保持与 pipeline.py 的权重公式一致（不要改动逻辑）。
    """
    importance = int(m.get("importance") or 0)
    mention_count = int(m.get("mention_count") or 0)
    last_mentioned = m.get("last_mentioned") or m.get("created_at") or ""
    dt = parse_iso_to_beijing(last_mentioned)
    if dt is None:
        dt = _now_beijing()
    days_since = (_now_beijing() - dt).days
    time_decay = min(days_since * 0.5, 10)
    return importance + mention_count - time_decay


def _guess_tag_from_query(query: str) -> str:
    q = (query or "").strip()
    for t in ROOM_TAGS:
        if t in q:
            return t
    return ""


def dynamic_vector_retrieve(
    query: str,
    tag: Optional[str] = None,
    vector_topk: Optional[int] = None,
    final_topn: Optional[int] = None,
    min_sim: Optional[float] = None,
) -> list[dict]:
    """
    两阶段：
    1) 向量召回 topK（cosine）
    2) 用现有 weight 重排并取 topN

    返回：动态层 memory dict 列表（按最终排序）。
    """
    query = (query or "").strip()
    if not query:
        return []

    vector_topk = int(vector_topk or VECTOR_TOPK)
    final_topn = int(final_topn or VECTOR_TOPN)
    min_sim = float(min_sim if min_sim is not None else VECTOR_MIN_SIM)

    memories = r2_store.get_dynamic_memory_list() or []
    if not memories:
        return []

    # tag：优先显式传入，其次从 query 猜一把；否则全量扫当前 memories 的 tag 集合
    tag = (tag or "").strip() or _guess_tag_from_query(query)
    if tag:
        tags = [tag]
    else:
        tags = sorted({(m.get("tag") or "").strip() for m in memories if (m.get("tag") or "").strip()}) or ["ALL"]

    # query embedding
    q_emb = embed_text(query)
    if not q_emb:
        return []

    # 构建 memory_id -> memory
    mem_by_id: dict[str, dict] = {}
    for m in memories:
        mid = m.get("id")
        if mid:
            mem_by_id[str(mid)] = m

    # 向量召回
    candidates: list[tuple[float, dict]] = []
    for t in tags:
        idx = load_index(t)
        for r in (idx.get("records") or []):
            mid = (r or {}).get("memory_id")
            emb = (r or {}).get("embedding")
            if not mid or not isinstance(emb, list):
                continue
            sim = cosine(q_emb, emb)
            if sim < min_sim:
                continue
            candidates.append((sim, {"memory_id": str(mid), "cosine_sim": float(sim)}))

    if not candidates:
        return []

    candidates.sort(key=lambda x: -x[0])
    candidates = candidates[: max(1, vector_topk)]

    # weight 重排（tie-break 用 cosine）
    ranked: list[tuple[float, float, dict]] = []
    for sim, c in candidates:
        mid = c["memory_id"]
        mem = mem_by_id.get(mid)
        if not mem:
            continue
        w = _memory_weight(mem)
        ranked.append((w, sim, mem))

    ranked.sort(key=lambda x: (-x[0], -x[1]))
    out = [m for _, _, m in ranked[: max(1, final_topn)]]
    logger.debug("dynamic_vector_retrieve query_len=%s tags=%s hit=%s out=%s", len(query), tags, len(candidates), len(out))
    return out

