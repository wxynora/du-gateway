from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any

import requests

from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_CHAT_MODEL
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import _now_beijing, now_beijing_iso

logger = get_logger(__name__)


_DUP_SIM_THRESHOLD = 0.85
_BACKFILL_UPSERT_MAX = 50
_BACKFILL_UPSERT_SLEEP_SECONDS = 0.15
_DUP_EMBED_MAX = 80
_DUP_EMBED_SLEEP_SECONDS = 0.05
_DS_GROUP_MAX = 8
_EMBED_HEALTH_TIMEOUT_SECONDS = 3.0

_DUPLICATE_RESOLVE_PROMPT = """你在帮我整理一组疑似重复的动态记忆。

目标：
1. 判断这些条目是否其实在说同一件事 / 同一种偏好 / 同一个状态。
2. 如果是，选一条保留并输出 merge。
3. 如果不是，就 keep，不要硬合。

要求：
- merge 时必须输出一条“当前理解”，不是旧句拼接。
- importance 不用改；这里只做 merge/keep 判断。
- 只在明显同主题时才 merge；拿不准就 keep。

输出格式（严格 JSON，不要别的文字）：
{
  "action": "merge 或 keep",
  "keep_id": "保留的记忆 id；keep 时可留空",
  "drop_ids": ["需要删掉的重复项 id"],
  "content": "merge 后的新 content；keep 时可为空",
  "reason": "一句很短的判断理由"
}

当前候选组：
{group_json}
"""


def _extract_json_obj(text: str) -> dict | None:
    if not text or not isinstance(text, str):
        return None
    raw = text.strip()
    if "```" in raw:
        for marker in ("```json", "```"):
            if marker in raw:
                raw = raw.split(marker, 1)[1].strip()
                if "```" in raw:
                    raw = raw.split("```", 1)[0].strip()
                break
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(raw[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _resolve_duplicate_group_with_ds(group: list[dict]) -> dict | None:
    if not group or len(group) < 2:
        return None
    if not (DEEPSEEK_API_KEY and DEEPSEEK_API_URL):
        return None
    prompt = _DUPLICATE_RESOLVE_PROMPT.format(
        group_json=json.dumps(
            [
                {
                    "id": str((m or {}).get("id") or ""),
                    "tag": str((m or {}).get("tag") or ""),
                    "content": str((m or {}).get("content") or ""),
                    "retrieval_text": str((m or {}).get("retrieval_text") or ""),
                    "importance": int((m or {}).get("importance") or 0),
                    "mention_count": int((m or {}).get("mention_count") or 0),
                    "last_mentioned": str((m or {}).get("last_mentioned") or ""),
                }
                for m in group
            ],
            ensure_ascii=False,
        )
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "model": DEEPSEEK_CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
    }
    try:
        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=25)
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        obj = _extract_json_obj(content)
        if not isinstance(obj, dict):
            return None
        action = str(obj.get("action") or "").strip().lower()
        if action not in ("merge", "keep"):
            return None
        keep_id = str(obj.get("keep_id") or "").strip()
        drop_ids = obj.get("drop_ids")
        if not isinstance(drop_ids, list):
            drop_ids = []
        return {
            "action": action,
            "keep_id": keep_id,
            "drop_ids": [str(x).strip() for x in drop_ids if str(x).strip()],
            "content": str(obj.get("content") or "").strip(),
            "reason": str(obj.get("reason") or "").strip(),
        }
    except Exception as e:
        logger.warning("memory maintenance DS resolve failed error=%s", e)
        return None


def _embedding_backend_healthy() -> tuple[bool, str]:
    """
    离线整理的快速探针：embedding 后端不通时直接降级，避免长时间卡住请求。
    """
    try:
        from memory_vector.config import (
            CF_ACCOUNT_ID,
            CF_API_TOKEN,
            CF_EMBEDDING_MODEL,
            OPENAI_API_KEY,
            EMBEDDING_MODEL,
            current_embedding_backend,
        )
    except Exception as e:
        return False, f"embedding_config_import_failed: {e}"

    backend = str(current_embedding_backend() or "").strip()
    try:
        if backend == "cloudflare_bge":
            if not (CF_ACCOUNT_ID and CF_API_TOKEN and CF_EMBEDDING_MODEL):
                return False, "cloudflare_config_missing"
            url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{CF_EMBEDDING_MODEL}"
            headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
            payload = {"text": "health-check", "truncate_inputs": True}
            resp = requests.post(url, headers=headers, json=payload, timeout=_EMBED_HEALTH_TIMEOUT_SECONDS)
            if resp.status_code >= 400:
                return False, f"cloudflare_http_{resp.status_code}"
            data = resp.json() if resp.text else {}
            result = data.get("result") if isinstance(data, dict) else None
            obj = result if isinstance(result, dict) else (data if isinstance(data, dict) else {})
            emb_list = obj.get("data")
            if not isinstance(emb_list, list) or not emb_list:
                return False, "cloudflare_no_data"
            return True, ""

        if backend == "openai_compatible":
            if not (OPENAI_API_KEY and EMBEDDING_MODEL):
                return False, "openai_config_missing"
            url = "https://api.openai.com/v1/embeddings"
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            payload = {"model": EMBEDDING_MODEL, "input": "health-check"}
            resp = requests.post(url, headers=headers, json=payload, timeout=_EMBED_HEALTH_TIMEOUT_SECONDS)
            if resp.status_code >= 400:
                return False, f"openai_http_{resp.status_code}"
            data = resp.json() if resp.text else {}
            emb = (((data.get("data") or [{}])[0]) or {}).get("embedding")
            if not isinstance(emb, list):
                return False, "openai_no_embedding"
            return True, ""
        return False, "embedding_backend_disabled"
    except Exception as e:
        return False, f"embedding_probe_failed: {e}"


def run_memory_maintenance(limit_candidates: int = 20, dry_run: bool = False) -> dict:
    """
    动态记忆离线慢整理：
    1. 为旧记忆补 retrieval_text
    2. 清理明显边缘且未进入核心缓存层的低权重旧记忆
    3. 用同 tag 下 retrieval_text 的向量近邻粗筛疑似平行条
    4. 对少量候选组调用 DS 做 merge/keep 判断
    """
    from memory_vector.cosine import cosine
    from memory_vector.embedding_client import embed_text
    from memory_vector.vector_index_store import remove_memory_ids_from_all_indices
    from pipeline.pipeline import (
        _build_retrieval_text,
        _core_protected_dynamic_memory_ids,
        _should_prune_dynamic_memory,
        _upsert_dynamic_memory_index,
    )

    memories = r2_store.get_dynamic_memory_list() or []
    current_memories, changed = r2_store.ensure_dynamic_memory_ids(memories)
    core_pending = r2_store.get_core_cache_pending() or []
    protected_ids = _core_protected_dynamic_memory_ids(core_pending)
    now = _now_beijing()

    before_count = len(current_memories)
    backfilled_ids: list[str] = []
    retained: list[dict] = []
    removed_ids: set[str] = set()

    for mem in current_memories:
        if not isinstance(mem, dict):
            continue
        mid = str(mem.get("id") or "").strip()
        content = str(mem.get("content") or "").strip()
        if not mid or not content:
            continue
        if not str(mem.get("retrieval_text") or "").strip():
            mem["retrieval_text"] = _build_retrieval_text(content)
            backfilled_ids.append(mid)
            changed = True
        if _should_prune_dynamic_memory(mem, now, protected_ids):
            removed_ids.add(mid)
            changed = True
            continue
        retained.append(mem)

    tag_buckets: dict[str, list[dict]] = defaultdict(list)
    for mem in retained:
        retrieval_text = str(mem.get("retrieval_text") or "").strip()
        if retrieval_text:
            tag_buckets[str(mem.get("tag") or "").strip() or "ALL"].append(mem)

    candidate_groups: list[list[dict]] = []
    duplicate_candidates: list[dict] = []
    duplicate_embed_count = 0
    embed_ok, embed_skip_reason = _embedding_backend_healthy()

    if embed_ok:
        for tag, items in tag_buckets.items():
            if len(items) < 2:
                continue
            emb_cache: dict[str, list[float]] = {}
            for mem in items:
                if duplicate_embed_count >= _DUP_EMBED_MAX:
                    break
                mid = str(mem.get("id") or "").strip()
                retrieval_text = str(mem.get("retrieval_text") or "").strip()
                if not mid or not retrieval_text:
                    continue
                try:
                    emb = embed_text(retrieval_text)
                except Exception as e:
                    logger.warning("memory maintenance duplicate embed failed memory_id=%s error=%s", mid, e)
                    continue
                if emb:
                    emb_cache[mid] = emb
                    duplicate_embed_count += 1
                    if _DUP_EMBED_SLEEP_SECONDS > 0:
                        time.sleep(_DUP_EMBED_SLEEP_SECONDS)
            if duplicate_embed_count >= _DUP_EMBED_MAX:
                logger.info("memory maintenance duplicate embed reached limit=%s", _DUP_EMBED_MAX)

            visited: set[str] = set()
            for i, base in enumerate(items):
                base_id = str(base.get("id") or "").strip()
                base_text = str(base.get("retrieval_text") or "").strip()
                if not base_id or not base_text or base_id in visited or base_id not in emb_cache:
                    continue
                group = [base]
                visited.add(base_id)
                for cand in items[i + 1 :]:
                    cand_id = str(cand.get("id") or "").strip()
                    cand_text = str(cand.get("retrieval_text") or "").strip()
                    if not cand_id or not cand_text or cand_id in visited or cand_id not in emb_cache:
                        continue
                    sim = cosine(emb_cache[base_id], emb_cache[cand_id])
                    if sim >= _DUP_SIM_THRESHOLD:
                        cc = dict(cand)
                        cc["_dup_sim"] = round(float(sim), 4)
                        group.append(cc)
                        visited.add(cand_id)
                if len(group) < 2:
                    continue
                candidate_groups.append(group)
                sims = [float((m or {}).get("_dup_sim") or 1.0) for m in group[1:]]
                duplicate_candidates.append(
                    {
                        "tag": tag,
                        "retrieval_text": base_text,
                        "count": len(group),
                        "avg_sim": round(sum(sims) / len(sims), 4) if sims else 1.0,
                        "ids": [str((m or {}).get("id") or "") for m in group[:5]],
                        "contents": [str((m or {}).get("content") or "")[:80] for m in group[:3]],
                    }
                )
    else:
        logger.warning("memory maintenance skip duplicate scan: %s", embed_skip_reason)

    candidate_groups.sort(
        key=lambda group: (
            -len(group),
            -max([float((m or {}).get("_dup_sim") or 1.0) for m in group[1:]] or [1.0]),
            str((group[0] or {}).get("retrieval_text") or ""),
        )
    )
    duplicate_candidates.sort(
        key=lambda x: (
            -int(x.get("count") or 0),
            -float(x.get("avg_sim") or 0.0),
            str(x.get("retrieval_text") or ""),
        )
    )
    duplicate_candidates = duplicate_candidates[: max(1, int(limit_candidates or 20))]

    ds_resolutions: list[dict] = []
    if not dry_run:
        for group in candidate_groups[:_DS_GROUP_MAX]:
            result = _resolve_duplicate_group_with_ds(group)
            if not result:
                continue
            ds_resolutions.append(
                {
                    "action": result.get("action"),
                    "keep_id": result.get("keep_id"),
                    "drop_ids": result.get("drop_ids") or [],
                    "reason": result.get("reason") or "",
                }
            )
            if str(result.get("action") or "") != "merge":
                continue
            keep_id = str(result.get("keep_id") or "").strip()
            drop_ids = {str(x).strip() for x in (result.get("drop_ids") or []) if str(x).strip()}
            if not keep_id or not drop_ids:
                continue
            keep_mem = next((m for m in retained if str((m or {}).get("id") or "") == keep_id), None)
            if not keep_mem:
                continue
            merged_content = str(result.get("content") or "").strip() or str(keep_mem.get("content") or "").strip()
            content_before = str(keep_mem.get("content") or "").strip()
            keep_mem["content"] = merged_content
            keep_mem["retrieval_text"] = _build_retrieval_text(merged_content)
            keep_mem["last_mentioned"] = now_beijing_iso()
            keep_mem["mention_count"] = sum(
                int((m or {}).get("mention_count") or 0)
                for m in retained
                if str((m or {}).get("id") or "") == keep_id or str((m or {}).get("id") or "") in drop_ids
            )
            removed_ids.update(drop_ids)
            retained = [m for m in retained if str((m or {}).get("id") or "") not in drop_ids]
            backfilled_ids.append(keep_id)
            changed = True
            try:
                from services.dynamic_memory_provenance import record_event

                record_event(
                    memory_id=keep_id,
                    action="maintenance_merge",
                    event_time=str(keep_mem.get("last_mentioned") or ""),
                    content_before=content_before,
                    content_after=merged_content,
                    related_memory_ids=sorted(drop_ids),
                    tag=str(keep_mem.get("tag") or ""),
                    importance=int(keep_mem.get("importance") or 0),
                    emotion_label=str(keep_mem.get("emotion_label") or ""),
                    scene_type=str(keep_mem.get("scene_type") or ""),
                    target_type=str(keep_mem.get("target_type") or ""),
                    source="memory_maintenance",
                    decision=result,
                )
            except Exception as e:
                logger.warning("memory maintenance provenance record failed keep_id=%s error=%s", keep_id, e)

    report = {
        "timestamp": now_beijing_iso(),
        "dry_run": bool(dry_run),
        "embedding_skipped": (not embed_ok),
        "embedding_skip_reason": embed_skip_reason if not embed_ok else "",
        "memory_count_before": before_count,
        "memory_count_after": len(retained),
        "backfilled_count": len(backfilled_ids),
        "pruned_count": len(removed_ids),
        "backfill_upsert_limit": _BACKFILL_UPSERT_MAX,
        "duplicate_embed_limit": _DUP_EMBED_MAX,
        "duplicate_candidate_count": len(duplicate_candidates),
        "duplicate_candidates": duplicate_candidates,
        "ds_resolution_count": len(ds_resolutions),
        "ds_resolutions": ds_resolutions[:10],
    }

    if dry_run:
        return report

    if changed:
        ok = r2_store.save_dynamic_memory_list(retained)
        if not ok:
            raise RuntimeError("保存动态记忆失败")
        if removed_ids:
            try:
                remove_memory_ids_from_all_indices(removed_ids)
            except Exception as e:
                logger.warning("memory maintenance remove indices failed: %s", e, exc_info=True)
            try:
                from services.dynamic_memory_provenance import delete_events_for_memories

                deleted = delete_events_for_memories(removed_ids)
                report["provenance_deleted_count"] = deleted
            except Exception as e:
                logger.warning("memory maintenance provenance cleanup failed: %s", e, exc_info=True)
        updated_ids = set(backfilled_ids)
        upserted_count = 0
        if embed_ok:
            for mem in retained:
                mid = str(mem.get("id") or "").strip()
                if mid in updated_ids:
                    if upserted_count >= _BACKFILL_UPSERT_MAX:
                        break
                    try:
                        _upsert_dynamic_memory_index(mem)
                        upserted_count += 1
                        if _BACKFILL_UPSERT_SLEEP_SECONDS > 0:
                            time.sleep(_BACKFILL_UPSERT_SLEEP_SECONDS)
                    except Exception as e:
                        logger.warning("memory maintenance upsert failed memory_id=%s error=%s", mid, e, exc_info=True)
        else:
            report["backfill_upsert_skipped_reason"] = embed_skip_reason
        report["backfill_upserted_count"] = upserted_count

    saved = r2_store.save_dynamic_memory_maintenance_report(report)
    if not saved:
        raise RuntimeError("保存离线整理报告失败")
    return report
