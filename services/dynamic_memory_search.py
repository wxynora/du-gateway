from __future__ import annotations

import json
import re
from datetime import datetime, time, timedelta
from typing import Optional

from memory_vector.dynamic_vector_retriever import dynamic_vector_retrieve
from services.memory_bm25 import bm25_score_documents
from storage import r2_store
from utils.time_aware import now_beijing_iso
from utils.time_aware import BEIJING_TZ, _now_beijing, parse_iso_to_beijing


_RECENT_RANGE_DAYS = {
    "recent_7d": 7,
    "recent_15d": 15,
    "recent_30d": 30,
}
_SCENE_TYPES = {
    "problem_solving",
    "learning",
    "planning",
    "emotional_venting",
    "heart_to_heart",
    "casual_chat",
    "affection",
    "conflict",
}
_TARGET_TYPES = {
    "external_tools",
    "self_state",
    "work_career",
    "our_project",
    "our_relationship",
    "about_me",
    "third_party_people",
    "other_topic",
}


def normalize_search_memory_args(args: dict | None) -> tuple[dict, str]:
    if not isinstance(args, dict):
        return {}, "参数必须是对象"

    query = str(args.get("query") or "").strip()
    scene_type = str(args.get("scene_type") or "").strip()
    target_type = str(args.get("target_type") or "").strip()
    time_range = str(args.get("time_range") or "").strip()
    reason = str(args.get("reason") or "").strip()
    suspicion_level = str(args.get("suspicion_level") or "").strip().lower()

    if not query:
        return {}, "query 不能为空"
    if not reason:
        return {}, "reason 不能为空"
    if suspicion_level not in ("high", "medium", "low"):
        return {}, "suspicion_level 必须是 high / medium / low"
    if suspicion_level == "low":
        return {}, "suspicion_level=low 时不允许调用 search_memory"
    if scene_type and scene_type not in _SCENE_TYPES:
        return {}, "scene_type 无效"
    if target_type and target_type not in _TARGET_TYPES:
        return {}, "target_type 无效"
    if time_range:
        _, err = parse_time_range(time_range)
        if err:
            return {}, err

    return {
        "query": query,
        "scene_type": scene_type,
        "target_type": target_type,
        "time_range": time_range,
        "reason": reason,
        "suspicion_level": suspicion_level,
    }, ""


def parse_time_range(raw: str) -> tuple[Optional[tuple[Optional[datetime], Optional[datetime]]], str]:
    s = str(raw or "").strip()
    if not s or s == "all":
        return (None, None), ""
    if s in _RECENT_RANGE_DAYS:
        days = _RECENT_RANGE_DAYS[s]
        now = _now_beijing()
        return (now - timedelta(days=days), now), ""
    m = re.fullmatch(r"between:(\d{4}-\d{2}-\d{2}),(\d{4}-\d{2}-\d{2})", s)
    if not m:
        return None, "time_range 无效，只支持 recent_7d / recent_15d / recent_30d / all / between:YYYY-MM-DD,YYYY-MM-DD"
    start_s, end_s = m.groups()
    try:
        start_dt = datetime.fromisoformat(start_s).replace(tzinfo=BEIJING_TZ)
        end_dt = datetime.fromisoformat(end_s).replace(tzinfo=BEIJING_TZ)
    except Exception:
        return None, "between 时间格式无效"
    if end_dt < start_dt:
        return None, "between 的结束时间不能早于开始时间"
    return (
        datetime.combine(start_dt.date(), time.min, tzinfo=BEIJING_TZ),
        datetime.combine(end_dt.date(), time.max, tzinfo=BEIJING_TZ),
    ), ""


def memory_matches_time_range(mem: dict, time_range: str) -> bool:
    bounds, err = parse_time_range(time_range)
    if err:
        return False
    if not bounds:
        return True
    start_dt, end_dt = bounds
    if start_dt is None and end_dt is None:
        return True
    ts = parse_iso_to_beijing(mem.get("last_mentioned") or mem.get("created_at") or "")
    if ts is None:
        return False
    if start_dt and ts < start_dt:
        return False
    if end_dt and ts > end_dt:
        return False
    return True


def _memory_search_text(mem: dict) -> str:
    return "\n".join([
        str(mem.get("retrieval_text") or "").strip(),
        str(mem.get("content") or "").strip(),
    ])


def _freshness_score(mem: dict) -> float:
    ts = parse_iso_to_beijing(mem.get("last_mentioned") or mem.get("created_at") or "")
    if ts is None:
        return 0.0
    days = max(0, (_now_beijing() - ts).days)
    return max(0.0, 1.0 - min(days, 30) / 30.0)


def _weight_score(mem: dict) -> float:
    importance = max(0, int(mem.get("importance") or 0))
    mention_count = max(0, int(mem.get("mention_count") or 0))
    return min(1.0, (importance * 0.15) + (mention_count * 0.08))


def search_dynamic_memories(
    query: str,
    scene_type: str = "",
    target_type: str = "",
    time_range: str = "",
    limit: int = 3,
) -> dict:
    query = str(query or "").strip()
    scene_type = str(scene_type or "").strip()
    target_type = str(target_type or "").strip()
    time_range = str(time_range or "").strip()
    limit = max(1, min(int(limit or 3), 10))

    if not query:
        return {"ok": False, "error": "query 不能为空", "results": []}
    if time_range:
        _, err = parse_time_range(time_range)
        if err:
            return {"ok": False, "error": err, "results": []}

    candidates = dynamic_vector_retrieve(
        query=query,
        vector_topk=30,
        final_topn=20,
        include_du_memory_doc=False,
        include_core_pending=False,
        scene_type=scene_type or None,
        target_type=target_type or None,
        time_range=time_range or None,
        return_scores=True,
    )
    bm25_by_key: dict[str, float] = {}
    for bm25_score, mem in bm25_score_documents(query, candidates or [], _memory_search_text):
        key = str(mem.get("id") or id(mem))
        bm25_by_key[key] = float(bm25_score)

    results: list[dict] = []
    for mem in candidates or []:
        semantic_score = float(mem.get("_semantic_score") or 0.0)
        if semantic_score <= 0:
            continue
        if time_range and not memory_matches_time_range(mem, time_range):
            continue
        keyword_score = bm25_by_key.get(str(mem.get("id") or id(mem)), 0.0)
        if keyword_score <= 0:
            continue
        final_score = semantic_score * 0.7 + min(keyword_score, 3.0) * 0.15 + _freshness_score(mem) * 0.1 + _weight_score(mem) * 0.05
        row = {
            "id": str(mem.get("id") or "").strip(),
            "content": str(mem.get("content") or "").strip(),
            "emotion_label": str(mem.get("emotion_label") or "").strip(),
            "scene_type": str(mem.get("scene_type") or "").strip(),
            "target_type": str(mem.get("target_type") or "").strip(),
            "importance": int(mem.get("importance") or 0),
            "mention_count": int(mem.get("mention_count") or 0),
            "last_mentioned": str(mem.get("last_mentioned") or mem.get("created_at") or "").strip(),
            "semantic_score": round(semantic_score, 4),
            "final_score": round(final_score, 4),
            "_keyword_score": keyword_score,
        }
        if row["id"] and row["content"]:
            results.append(row)

    results.sort(
        key=lambda x: (
            -float(x.get("final_score") or 0.0),
            -float(x.get("semantic_score") or 0.0),
            -int(x.get("importance") or 0),
            str(x.get("last_mentioned") or ""),
        )
    )
    trimmed = []
    for row in results[:limit]:
        obj = dict(row)
        obj.pop("_keyword_score", None)
        trimmed.append(obj)

    return {
        "ok": True,
        "query": query,
        "scene_type": scene_type,
        "target_type": target_type,
        "time_range": time_range or "all",
        "count": len(trimmed),
        "results": trimmed,
    }


def execute_search_memory_tool(args: dict | None) -> str:
    normalized, err = normalize_search_memory_args(args)
    if err:
        return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
    result = search_dynamic_memories(
        query=normalized["query"],
        scene_type=normalized["scene_type"],
        target_type=normalized["target_type"],
        time_range=normalized["time_range"],
        limit=3,
    )
    result["reason"] = normalized["reason"]
    result["suspicion_level"] = normalized["suspicion_level"]
    try:
        recalled_lines = []
        for row in result.get("results") or []:
            if not isinstance(row, dict):
                continue
            line = {
                "id": str(row.get("id") or ""),
                "content": str(row.get("content") or "")[:120],
                "emotion_label": str(row.get("emotion_label") or ""),
                "scene_type": str(row.get("scene_type") or ""),
                "target_type": str(row.get("target_type") or ""),
                "semantic_score": row.get("semantic_score"),
                "final_score": row.get("final_score"),
            }
            recalled_lines.append(line)
        r2_store.append_dynamic_recall_debug_event(
            {
                "timestamp": now_beijing_iso(),
                "window_id": "__search_memory__",
                "query": normalized["query"],
                "scene_type": normalized["scene_type"],
                "target_type": normalized["target_type"],
                "time_range": normalized["time_range"] or "all",
                "reason": normalized["reason"],
                "suspicion_level": normalized["suspicion_level"],
                "source": "search_memory",
                "recalled_lines": recalled_lines,
                "recalled_count": len(recalled_lines),
            }
        )
    except Exception:
        pass
    return json.dumps(result, ensure_ascii=False)
