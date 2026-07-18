from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Optional

from memory_vector.config import (
    VECTOR_MIN_SIM,
    VECTOR_TOPK,
    VECTOR_TOPN,
    INCLUDE_DU_MEMORY_DOC_IN_VECTOR,
    INCLUDE_CORE_PENDING_IN_VECTOR,
)
from memory_vector.core_pending_index import CORE_PENDING_INDEX_TAG
from memory_vector.cosine import cosine
from memory_vector.embedding_client import embed_text
from memory_vector.vector_index_store import load_index
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import parse_iso_to_beijing, _now_beijing

logger = get_logger(__name__)


ROOM_TAGS = ("客厅", "书房", "图书馆", "卧室")
_RECENT_RANGE_DAYS = {"recent_7d": 7, "recent_15d": 15, "recent_30d": 30}


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


def _memory_event_timestamp(mem: dict) -> str:
    """事件时间/内容更新时间；last_mentioned 只表示最近被引用。"""
    return str(
        (mem or {}).get("updated_at")
        or (mem or {}).get("created_at")
        or (mem or {}).get("promoted_at")
        or (mem or {}).get("last_mentioned")
        or ""
    ).strip()


def _guess_tag_from_query(query: str) -> str:
    q = (query or "").strip()
    for t in ROOM_TAGS:
        if t in q:
            return t
    return ""


def _memory_matches_time_range(mem: dict, time_range: str) -> bool:
    s = str(time_range or "").strip()
    if not s or s == "all":
        return True
    now = _now_beijing()
    start_dt = None
    end_dt = None
    if s in _RECENT_RANGE_DAYS:
        start_dt = now - timedelta(days=_RECENT_RANGE_DAYS[s])
        end_dt = now
    else:
        import re

        m = re.fullmatch(r"between:(\d{4}-\d{2}-\d{2}),(\d{4}-\d{2}-\d{2})", s)
        if not m:
            return False
        start_s, end_s = m.groups()
        try:
            start = datetime.fromisoformat(start_s).replace(tzinfo=now.tzinfo)
            end = datetime.fromisoformat(end_s).replace(tzinfo=now.tzinfo)
        except Exception:
            return False
        if end < start:
            return False
        start_dt = datetime.combine(start.date(), time.min, tzinfo=now.tzinfo)
        end_dt = datetime.combine(end.date(), time.max, tzinfo=now.tzinfo)
    ts = parse_iso_to_beijing(_memory_event_timestamp(mem))
    if ts is None:
        return False
    if start_dt and ts < start_dt:
        return False
    if end_dt and ts > end_dt:
        return False
    return True


def _memory_matches_filters(mem: dict, scene_type: str = "", target_type: str = "", time_range: str = "") -> bool:
    if scene_type and str(mem.get("scene_type") or "").strip() != scene_type:
        return False
    if target_type and str(mem.get("target_type") or "").strip() != target_type:
        return False
    if time_range:
        if not _memory_matches_time_range(mem, time_range):
            return False
    return True


def dynamic_vector_retrieve(
    query: str,
    tag: Optional[str] = None,
    vector_topk: Optional[int] = None,
    final_topn: Optional[int] = None,
    min_sim: Optional[float] = None,
    include_du_memory_doc: Optional[bool] = None,
    include_core_pending: Optional[bool] = None,
    scene_type: Optional[str] = None,
    target_type: Optional[str] = None,
    time_range: Optional[str] = None,
    return_scores: bool = False,
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
    scene_type = str(scene_type or "").strip()
    target_type = str(target_type or "").strip()
    time_range = str(time_range or "").strip()
    if scene_type or target_type or time_range:
        memories = [m for m in memories if _memory_matches_filters(m, scene_type, target_type, time_range)]

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

    # 构建 memory_id -> memory（动态层）
    mem_by_id: dict[str, dict] = {}
    for m in memories:
        mid = m.get("id")
        if mid:
            mem_by_id[str(mid)] = m

    # 可选：把「小渡的记忆文档」作为一条特殊记忆参与召回（默认关闭）
    if include_du_memory_doc is None:
        include_du_memory_doc = INCLUDE_DU_MEMORY_DOC_IN_VECTOR
    du_doc = r2_store.get_du_memory_doc() if include_du_memory_doc else ""
    du_doc_id = "__du_memory_doc_v1__"
    if du_doc:
        du_mem = {
            "id": du_doc_id,
            "content": du_doc,
            "importance": 4,
            "mention_count": 3,
            "last_mentioned": _now_beijing().isoformat(),
            "tag": "图书馆",
        }
        mem_by_id[du_doc_id] = du_mem

    # 可选：核心缓存 pending 也参与检索（默认关闭）
    if include_core_pending is None:
        include_core_pending = INCLUDE_CORE_PENDING_IN_VECTOR
    core_pending = (r2_store.get_core_cache_pending() or []) if include_core_pending else []
    core_mems: list[dict] = []
    for p in core_pending:
        cid = p.get("id")
        if not cid:
            continue
        dynamic_base = mem_by_id.get(str(cid)) or {}
        mem_id = f"core::{cid}"
        mem = {
            "id": mem_id,
            "source_memory_id": str((p or {}).get("source_memory_id") or "").strip(),
            "content": (p.get("content") or "").strip(),
            "importance": int(p.get("importance") or 0),
            "mention_count": int(p.get("mention_count") or 0),
            "created_at": p.get("created_at") or dynamic_base.get("created_at") or "",
            "updated_at": p.get("updated_at") or dynamic_base.get("updated_at") or dynamic_base.get("created_at") or "",
            "last_mentioned": p.get("last_mentioned") or dynamic_base.get("last_mentioned") or p.get("promoted_at") or _now_beijing().isoformat(),
            "promoted_at": p.get("promoted_at") or "",
            "tag": (p.get("tag") or "").strip() or "图书馆",
            "emotion_label": str((p or {}).get("emotion_label") or "").strip(),
            "scene_type": str((p or {}).get("scene_type") or "").strip(),
            "target_type": str((p or {}).get("target_type") or "").strip(),
        }
        core_mems.append(mem)
        mem_by_id[mem_id] = mem

    if not (memories or du_doc or core_mems):
        return []

    def _collect_candidates(sim_threshold: float) -> list[tuple[float, dict]]:
        cands: list[tuple[float, dict]] = []
        # 向量召回（动态层：用向量索引）
        for t in tags:
            idx = load_index(t)
            for r in (idx.get("records") or []):
                mid = (r or {}).get("memory_id")
                emb = (r or {}).get("embedding")
                if not mid or not isinstance(emb, list):
                    continue
                sim = cosine(q_emb, emb)
                if sim < sim_threshold:
                    continue
                cands.append((sim, {"memory_id": str(mid), "cosine_sim": float(sim)}))

        # 「小渡记忆文档」单独 embedding 参与召回（不依赖向量索引）
        if du_doc:
            du_text_for_embed = du_doc[:3000]
            du_emb = embed_text(du_text_for_embed)
            if du_emb:
                sim = cosine(q_emb, du_emb)
                if sim >= sim_threshold:
                    cands.append((sim, {"memory_id": du_doc_id, "cosine_sim": float(sim)}))

        # 核心缓存 pending：读取预建索引，避免每轮聊天逐条现场 embedding。
        if core_mems:
            idx = load_index(CORE_PENDING_INDEX_TAG)
            for r in (idx.get("records") or []):
                mid = str((r or {}).get("memory_id") or "").strip()
                emb = (r or {}).get("embedding")
                if not mid or mid not in mem_by_id or not isinstance(emb, list):
                    continue
                sim = cosine(q_emb, emb)
                if sim >= sim_threshold:
                    cands.append((sim, {"memory_id": mid, "cosine_sim": float(sim)}))
        return cands

    candidates = _collect_candidates(min_sim)
    # 命中为 0 时再做一次温和放宽，避免“看起来完全不触发”
    if not candidates:
        relaxed = max(0.30, min_sim - 0.06)
        if relaxed < min_sim:
            candidates = _collect_candidates(relaxed)
            if candidates:
                logger.debug("dynamic_vector_retrieve relax min_sim %s -> %s hit=%s", min_sim, relaxed, len(candidates))

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
    out: list[dict] = []
    for w, sim, mem in ranked[: max(1, final_topn)]:
        if return_scores:
            mm = dict(mem)
            mm["_semantic_score"] = round(float(sim), 4)
            mm["_final_score"] = round(float(w), 4)
            out.append(mm)
        else:
            out.append(mem)
    logger.debug("dynamic_vector_retrieve query_len=%s tags=%s hit=%s out=%s", len(query), tags, len(candidates), len(out))
    return out
