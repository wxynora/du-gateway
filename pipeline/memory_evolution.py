"""Dynamic-memory pruning, persistence, promotion, provenance, and post-round evolution."""

import copy
from typing import Callable, Optional

from config import (
    DYNAMIC_MEMORY_BEDROOM_DAYS_VALID,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT,
    DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS,
    DYNAMIC_MEMORY_REVIEW_ALL_MERGES,
    DU_DYNAMIC_LAYER_BODY_DELTA_ENABLED,
)
from pipeline.memory_recall import (
    _build_retrieval_text,
    _invalidate_recall_cache,
    _memory_event_timestamp,
    _memory_retrieval_text,
    _memory_weight,
)
from storage import r2_store
from utils.log import get_logger


logger = get_logger("pipeline.pipeline")

_EMOTION_LABELS = {"positive", "negative", "neutral"}
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


def _normalize_memory_labels(decision: dict) -> tuple[str, str, str]:
    emotion_label = str(decision.get("emotion_label") or "").strip().lower()
    scene_type = str(decision.get("scene_type") or "").strip()
    target_type = str(decision.get("target_type") or "").strip()
    if emotion_label not in _EMOTION_LABELS:
        emotion_label = "neutral"
    if scene_type not in _SCENE_TYPES:
        scene_type = ""
    if target_type not in _TARGET_TYPES:
        target_type = ""
    return emotion_label, scene_type, target_type


def _dynamic_memory_tag(mem: dict) -> str:
    return str((mem or {}).get("tag") or "").strip()


def _dynamic_memory_days_since_last_mentioned(mem: dict, now) -> Optional[int]:
    from utils.time_aware import parse_iso_to_beijing

    last_mentioned = mem.get("last_mentioned") or mem.get("created_at") or ""
    dt = parse_iso_to_beijing(last_mentioned)
    if dt is None:
        return None
    days_since = (now - dt).days
    if days_since < 0:
        days_since = 0
    return days_since


def _is_tag_expired_dynamic_memory_for_prune(
    mem: dict,
    now,
    *,
    bedroom_days_valid: int = DYNAMIC_MEMORY_BEDROOM_DAYS_VALID,
) -> bool:
    """
    部分 tag 可以走更短落盘生命周期。
    卧室动态记忆只保留短期余味；超过卧室有效期还没被再次提到，就从动态层退场。
    """
    if _dynamic_memory_tag(mem) != "卧室":
        return False
    days_since = _dynamic_memory_days_since_last_mentioned(mem, now)
    if days_since is None:
        return False
    return days_since >= max(0, int(bedroom_days_valid))


def _is_marginal_dynamic_memory_for_prune(
    mem: dict,
    now,
    *,
    marginal_prune_enabled: bool = DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED,
    marginal_prune_max_weight: float = DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT,
    marginal_prune_min_days: int = DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS,
    tag_expired: Callable[[dict, object], bool] = _is_tag_expired_dynamic_memory_for_prune,
    memory_weight: Callable[..., float] = _memory_weight,
) -> bool:
    """
    可从动态层落盘删除的记忆（不碰 core_cache）：
    - 卧室 tag 走短有效期，超过后直接退场；
    - 其它 tag 仍沿用综合权重低且距上次提及已久的边缘化规则。
    物理淘汰是动态层召回生命周期的唯一出口。
    """
    if _dynamic_memory_tag(mem) == "图书馆":
        return False
    if tag_expired(mem, now):
        return True
    if not marginal_prune_enabled:
        return False

    days_since = _dynamic_memory_days_since_last_mentioned(mem, now)
    if days_since is None:
        return False
    if days_since < marginal_prune_min_days:
        return False
    return memory_weight(mem, now) <= marginal_prune_max_weight


def _core_protected_dynamic_memory_ids(core_pending: list) -> set[str]:
    protected_ids: set[str] = set()
    for item in core_pending or []:
        if not isinstance(item, dict):
            continue
        entry_id = str(item.get("id") or "").strip()
        source_memory_id = str(item.get("source_memory_id") or "").strip()
        if entry_id:
            protected_ids.add(entry_id)
        if source_memory_id:
            protected_ids.add(source_memory_id)
    return protected_ids


def _should_prune_dynamic_memory(
    mem: dict,
    now,
    protected_ids: set[str],
    *,
    is_marginal: Callable[[dict, object], bool] = _is_marginal_dynamic_memory_for_prune,
) -> bool:
    if isinstance((mem or {}).get("pending_merge"), dict):
        return False
    memory_id = str((mem or {}).get("id") or "").strip()
    if memory_id and memory_id in protected_ids:
        return False
    return is_marginal(mem, now)


def prune_dynamic_memories_before_recall(
    memories: list,
    core_pending: list,
    *,
    r2_store_module,
    protected_ids_for_core: Callable[[list], set[str]],
    should_prune: Callable[[dict, object, set[str]], bool],
    marginal_prune_max_weight: float,
    marginal_prune_min_days: int,
    logger_instance,
) -> list:
    """Apply the existing pre-recall dynamic-memory prune and return the latest list."""
    from utils.time_aware import _now_beijing

    now = _now_beijing()
    before_n = len(memories)
    protected_ids = protected_ids_for_core(core_pending)
    pruned = [mem for mem in memories if not should_prune(mem, now, protected_ids)]
    if len(pruned) >= before_n:
        return pruned

    removed_ids = {
        str(mem.get("id"))
        for mem in memories
        if mem.get("id") and should_prune(mem, now, protected_ids)
    }
    save_status = r2_store_module.save_dynamic_memory_list_if_unchanged(memories, pruned)
    if save_status != "saved":
        logger_instance.info("动态层边缘淘汰放弃旧快照写回 status=%s", save_status)
        return r2_store_module.get_dynamic_memory_list() or []

    provenance_deleted = 0
    try:
        from memory_vector.vector_index_store import remove_memory_ids_from_all_indices

        removed_index_records = remove_memory_ids_from_all_indices(removed_ids)
    except Exception as exc:
        removed_index_records = 0
        logger_instance.warning("动态层边缘淘汰后索引清理失败 error=%s", exc, exc_info=True)
    try:
        from services.dynamic_memory_provenance import delete_events_for_memories

        provenance_deleted = delete_events_for_memories(removed_ids)
    except Exception as exc:
        logger_instance.warning("动态层边缘淘汰后血缘表清理失败 error=%s", exc, exc_info=True)
    try:
        logger_instance.info(
            "动态层边缘淘汰：条数 %s -> %s，索引删除记录数=%s，血缘删除记录数=%s（max_weight=%s min_days=%s）",
            before_n,
            len(pruned),
            removed_index_records,
            provenance_deleted,
            marginal_prune_max_weight,
            marginal_prune_min_days,
        )
    except Exception as exc:
        logger_instance.debug("动态层边缘淘汰日志失败 error=%s", exc)
    return pruned


def _upsert_dynamic_memory_index(
    mem: dict,
    *,
    retrieval_text_builder: Callable[[dict], str] = _memory_retrieval_text,
    event_timestamp: Callable[[dict], str] = _memory_event_timestamp,
    logger_instance=logger,
) -> None:
    """把单条动态记忆增量写入向量索引。失败只记日志，不影响主流程。"""
    if not isinstance(mem, dict):
        return
    mid = str(mem.get("id") or "").strip()
    text = retrieval_text_builder(mem)
    tag = str(mem.get("tag") or "").strip() or "ALL"
    if not mid or not text:
        return
    try:
        from memory_vector.embedding_client import embed_text, content_hash, normalize_text
        from memory_vector.vector_index_store import upsert_records

        normalized = normalize_text(text)
        emb = embed_text(normalized)
        if not emb:
            logger_instance.warning("动态层索引跳过：embedding 为空 memory_id=%s tag=%s", mid, tag)
            return
        rec = {
            "memory_id": mid,
            "text": normalized,
            "embedding": emb,
            "content_hash": content_hash(normalized),
            "metadata": {
                "importance": int(mem.get("importance") or 0),
                "mention_count": int(mem.get("mention_count") or 0),
                "tag": tag,
                "emotion_label": str(mem.get("emotion_label") or "").strip(),
                "scene_type": str(mem.get("scene_type") or "").strip(),
                "target_type": str(mem.get("target_type") or "").strip(),
                "created_at": mem.get("created_at") or "",
                "updated_at": mem.get("updated_at") or "",
                "last_mentioned": mem.get("last_mentioned") or "",
                "event_at": event_timestamp(mem),
            },
        }
        ok = upsert_records(tag, [rec])
        if not ok:
            logger_instance.warning("动态层索引写入失败 memory_id=%s tag=%s", mid, tag)
    except Exception as e:
        logger_instance.warning("动态层索引增量更新失败 memory_id=%s tag=%s error=%s", mid, tag, e)


def _move_promoted_memories_out_of_dynamic(
    current_memories: list,
    promoted_ids: set[str],
    *,
    expected_snapshot: list,
    r2_store_module=r2_store,
    invalidate_recall_cache: Callable[[], None] = _invalidate_recall_cache,
    logger_instance=logger,
) -> bool:
    """核心副本确认落盘后，把对应源记忆从动态层与动态索引移走。"""
    ids = {str(x or "").strip() for x in (promoted_ids or set()) if str(x or "").strip()}
    if not ids:
        return True
    remaining = [m for m in current_memories if str((m or {}).get("id") or "").strip() not in ids]
    if len(remaining) == len(current_memories):
        return True
    save_status = r2_store_module.save_dynamic_memory_list_if_unchanged(expected_snapshot, remaining)
    saved = save_status == "saved"
    if not saved:
        logger_instance.error("核心记忆晋升后动态层移出失败 ids=%s status=%s", sorted(ids), save_status)
        return False

    current_memories[:] = remaining
    try:
        from memory_vector.vector_index_store import remove_memory_ids_from_all_indices

        removed = remove_memory_ids_from_all_indices(ids)
    except Exception as e:
        removed = 0
        logger_instance.warning("核心记忆晋升后动态索引清理失败 ids=%s error=%s", sorted(ids), e, exc_info=True)
    invalidate_recall_cache()
    logger_instance.info("核心记忆晋升完成 moved_ids=%s dynamic_index_removed=%s", sorted(ids), removed)
    return True


def _round_messages_to_raw_text(round_messages: list) -> str:
    """尽量把一轮消息转成可读原文，供动态层判断和日志摘要使用。"""
    lines = []
    for m in round_messages or []:
        role = (m.get("role") or "unknown").lower()
        content = m.get("content")
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict):
                    if c.get("type") == "text":
                        parts.append(c.get("text", ""))
                    else:
                        parts.append(f"[{c.get('type', '')}]")
                else:
                    parts.append(str(c))
            content = " ".join(parts)
        content = (content or "")
        lines.append(f"[{role}]: {str(content).strip()}")
    return "\n".join(lines).strip()


def _apply_one_decision(
    window_id: str,
    round_index: int,
    round_messages: list,
    decision: dict,
    current_memories: list,
    *,
    r2_store_module=r2_store,
    normalize_memory_labels: Callable[[dict], tuple[str, str, str]] = _normalize_memory_labels,
    build_retrieval_text: Callable[[str], str] = _build_retrieval_text,
    round_messages_to_raw_text: Callable[[list], str] = _round_messages_to_raw_text,
    move_promoted_memories: Callable[..., bool] = _move_promoted_memories_out_of_dynamic,
    upsert_dynamic_memory_index: Callable[[dict], None] = _upsert_dynamic_memory_index,
    review_all_merges: bool = DYNAMIC_MEMORY_REVIEW_ALL_MERGES,
    logger_instance=logger,
) -> Optional[dict]:
    """
    对单条 DS 决策做应用：new/merge 更新 current_memories、写 R2 并按需 promote。
    卧室内容正常进入动态层，但不提进 core cache。
    返回：若本条产生了 new/merge，返回 {"tag", "entry_id", "content", "promoted_at"}，否则 None。
    """
    from uuid import uuid4

    from utils.time_aware import now_beijing_iso

    tag = (decision.get("tag") or "").strip()
    action = (decision.get("action") or "skip").lower()
    content = (decision.get("content") or "").strip()
    fused_with_id = decision.get("fused_with_id")
    merge_reason = str(decision.get("merge_reason") or "").strip()
    importance = int(decision.get("importance") or 0)
    emotion_label, scene_type, target_type = normalize_memory_labels(decision)
    round_ts = decision.get("timestamp") or decision.get("last_mentioned")
    now_iso = round_ts if isinstance(round_ts, str) and round_ts else now_beijing_iso()
    mention_init = decision.get("mention_count")
    if mention_init is not None and isinstance(mention_init, int):
        pass
    else:
        mention_init = 0

    def _record_provenance_safe(
        *,
        memory_id: str,
        action_name: str,
        content_before: str = "",
        content_after: str = "",
        fused_id: str = "",
        mem_for_labels: dict | None = None,
    ) -> None:
        try:
            from services.dynamic_memory_provenance import record_event

            labels = mem_for_labels if isinstance(mem_for_labels, dict) else {}
            record_event(
                memory_id=memory_id,
                action=action_name,
                window_id=window_id,
                round_index=round_index,
                event_time=now_iso,
                content_before=content_before,
                content_after=content_after,
                fused_with_id=fused_id,
                tag=str(labels.get("tag") or tag or ""),
                importance=int(labels.get("importance") or importance or 0),
                emotion_label=str(labels.get("emotion_label") or emotion_label or ""),
                scene_type=str(labels.get("scene_type") or scene_type or ""),
                target_type=str(labels.get("target_type") or target_type or ""),
                source="dynamic_layer_ds",
                round_preview=round_messages_to_raw_text(round_messages),
                decision=decision,
            )
        except Exception as e:
            logger_instance.warning("动态记忆血缘记录失败 memory_id=%s action=%s error=%s", memory_id, action_name, e)

    if action in ("new", "merge") and tag not in {"客厅", "书房", "图书馆", "卧室"}:
        logger_instance.warning("动态层 %s 返回非法 tag=%s，本轮回退为 skip window_id=%s", action, tag, window_id)
        return None

    if action == "new" and content:
        new_mem = {
            "id": str(uuid4()),
            "content": content,
            "retrieval_text": build_retrieval_text(content),
            "importance": importance,
            "tag": tag,
            "emotion_label": emotion_label,
            "scene_type": scene_type,
            "target_type": target_type,
            "mention_count": mention_init if mention_init is not None else 1,
            "created_at": now_iso,
            "updated_at": now_iso,
            "last_mentioned": now_iso,
        }
        append_result = r2_store_module.append_dynamic_memory(new_mem)
        if str(append_result.get("status") or "") != "appended":
            logger_instance.warning(
                "动态层 new 放弃写入 status=%s window_id=%s memory_id=%s",
                append_result.get("status"),
                window_id,
                new_mem["id"],
            )
            return None
        current_memories[:] = list(append_result.get("memories") or [])
        latest_snapshot = copy.deepcopy(current_memories)
        promoted_ids: set[str] = set()
        if tag != "卧室":
            promoted_ids = r2_store_module.promote_to_core_cache(
                window_id,
                round_index,
                round_messages_to_raw_text(round_messages),
                current_memories,
                touched_mem_id=new_mem["id"],
            )
        if promoted_ids:
            dynamic_saved = move_promoted_memories(
                current_memories,
                promoted_ids,
                expected_snapshot=latest_snapshot,
            )
        else:
            dynamic_saved = True
        if dynamic_saved and new_mem["id"] not in promoted_ids:
            upsert_dynamic_memory_index(new_mem)
        try:
            from services.portrait_memory import sync_portrait_candidate_from_memory

            sync_portrait_candidate_from_memory(new_mem)
        except Exception as e:
            logger_instance.warning("sync_portrait_candidate_from_memory(new) 失败 error=%s", e)
        _record_provenance_safe(
            memory_id=new_mem["id"],
            action_name="new",
            content_after=content,
            mem_for_labels=new_mem,
        )
        logger_instance.debug("动态层 new window_id=%s", window_id)
        return {"tag": tag, "entry_id": new_mem["id"], "content": content, "promoted_at": new_mem["created_at"]}

    if action == "merge":
        if not fused_with_id:
            logger_instance.warning("动态层 merge 未返回 fused_with_id，本轮回退为 skip window_id=%s", window_id)
            return None
        if str(fused_with_id).startswith("core::"):
            core_entry_id = str(fused_with_id)[len("core::") :].strip()
            core_items = r2_store_module.get_core_cache_pending() or []
            core_index = next(
                (
                    i
                    for i, item in enumerate(core_items)
                    if isinstance(item, dict) and str(item.get("id") or "").strip() == core_entry_id
                ),
                None,
            )
            if core_index is None:
                logger_instance.warning(
                    "核心层 merge 未找到 fused_with_id=%s，本轮回退为 skip window_id=%s",
                    fused_with_id,
                    window_id,
                )
                return None
            current_core = core_items[core_index]
            content_before = str(current_core.get("content") or "")
            staged = r2_store_module.stage_core_memory_merge(
                core_entry_id,
                original_content=content_before,
                rewritten_content=content if content else content_before,
                proposed_at=now_iso,
                window_id=window_id,
                round_index=round_index,
                field_updates={
                    "importance": importance,
                    "mention_count": int(current_core.get("mention_count") or 0) + 1,
                    "tag": tag,
                    "emotion_label": emotion_label,
                    "scene_type": scene_type,
                    "target_type": target_type,
                    "last_mentioned": now_iso,
                },
                merge_reason=merge_reason,
            )
            if staged:
                logger_instance.info("核心层 merge 已生成待审核候选 window_id=%s fused_with_id=%s", window_id, fused_with_id)
            else:
                logger_instance.warning("核心层 merge 候选未暂存 window_id=%s fused_with_id=%s", window_id, fused_with_id)
            return None

        current_dynamic = next(
            (
                item
                for item in current_memories
                if isinstance(item, dict) and str(item.get("id") or "").strip() == str(fused_with_id).strip()
            ),
            None,
        )
        if isinstance(current_dynamic, dict) and isinstance(current_dynamic.get("pending_merge"), dict):
            logger_instance.info(
                "动态层 merge 目标已有待审核候选，本轮保持锁定并跳过 window_id=%s fused_with_id=%s",
                window_id,
                fused_with_id,
            )
            return None
        cross_day_bedroom_correction = bool(
            merge_reason == "correction"
            and decision.get("bedroom_cross_day") is True
            and isinstance(current_dynamic, dict)
            and "卧室" in {str(current_dynamic.get("tag") or "").strip(), tag}
        )
        review_required = bool(
            review_all_merges
            or merge_reason == "habit_generalization"
            or cross_day_bedroom_correction
        )
        if review_required:
            if not isinstance(current_dynamic, dict):
                logger_instance.warning(
                    "动态层待审 merge 未找到 fused_with_id=%s，本轮回退为 skip window_id=%s",
                    fused_with_id,
                    window_id,
                )
                return None
            content_before = str(current_dynamic.get("content") or "")
            staged = r2_store_module.stage_dynamic_memory_merge(
                str(fused_with_id),
                original_content=content_before,
                rewritten_content=content if content else content_before,
                proposed_at=now_iso,
                window_id=window_id,
                round_index=round_index,
                field_updates={
                    "importance": importance,
                    "mention_count": int(current_dynamic.get("mention_count") or 0) + 1,
                    "tag": tag,
                    "emotion_label": emotion_label,
                    "scene_type": scene_type,
                    "target_type": target_type,
                    "last_mentioned": now_iso,
                },
                merge_reason=merge_reason,
            )
            if staged:
                logger_instance.info(
                    "动态层待审 merge 已生成候选 window_id=%s fused_with_id=%s reason=%s gap_hours=%s",
                    window_id,
                    fused_with_id,
                    merge_reason,
                    decision.get("merge_gap_hours"),
                )
            else:
                logger_instance.warning(
                    "动态层待审 merge 候选未暂存 window_id=%s fused_with_id=%s reason=%s",
                    window_id,
                    fused_with_id,
                    merge_reason,
                )
            return None

        latest_memories = [
            dict(item)
            for item in (r2_store_module.get_dynamic_memory_list() or [])
            if isinstance(item, dict)
        ]
        latest_dynamic = next(
            (
                item
                for item in latest_memories
                if str(item.get("id") or "").strip() == str(fused_with_id).strip()
            ),
            None,
        )
        if not isinstance(latest_dynamic, dict):
            logger_instance.warning(
                "动态层 merge 最新条目未找到 fused_with_id=%s，本轮回退为 skip window_id=%s",
                fused_with_id,
                window_id,
            )
            return None
        if isinstance(latest_dynamic.get("pending_merge"), dict):
            logger_instance.info(
                "动态层 merge 最新条目已有待审核候选，本轮保持锁定并跳过 window_id=%s fused_with_id=%s",
                window_id,
                fused_with_id,
            )
            return None
        latest_snapshot = copy.deepcopy(latest_memories)
        current_memories[:] = latest_memories

        found = False
        merged_mem = None
        for mem in current_memories:
            if mem.get("id") == fused_with_id:
                content_before = str(mem.get("content") or "")
                mem["content"] = content if content else mem.get("content", "")
                mem["retrieval_text"] = build_retrieval_text(mem["content"])
                mem["importance"] = importance
                mem["tag"] = tag
                mem["emotion_label"] = emotion_label
                mem["scene_type"] = scene_type
                mem["target_type"] = target_type
                mem["updated_at"] = now_iso
                mem["last_mentioned"] = now_iso
                mem["mention_count"] = int(mem.get("mention_count") or 0) + 1
                merged_mem = mem
                found = True
                break
        if not found:
            logger_instance.warning("动态层 merge 未找到 fused_with_id=%s，本轮回退为 skip window_id=%s", fused_with_id, window_id)
            return None
        promoted_ids: set[str] = set()
        if tag != "卧室":
            promoted_ids = r2_store_module.promote_to_core_cache(
                window_id,
                round_index,
                round_messages_to_raw_text(round_messages),
                current_memories,
                touched_mem_id=fused_with_id,
            )
        if promoted_ids:
            dynamic_saved = move_promoted_memories(
                current_memories,
                promoted_ids,
                expected_snapshot=latest_snapshot,
            )
        else:
            save_status = r2_store_module.save_dynamic_memory_list_if_unchanged(
                latest_snapshot,
                current_memories,
            )
            dynamic_saved = save_status == "saved"
            if not dynamic_saved:
                logger_instance.info(
                    "动态层 merge 放弃旧快照写回 status=%s window_id=%s fused_with_id=%s",
                    save_status,
                    window_id,
                    fused_with_id,
                )
        if not dynamic_saved:
            return None
        if dynamic_saved and fused_with_id not in promoted_ids:
            upsert_dynamic_memory_index(merged_mem)
        try:
            from services.portrait_memory import sync_portrait_candidate_from_memory

            sync_portrait_candidate_from_memory(merged_mem)
        except Exception as e:
            logger_instance.warning("sync_portrait_candidate_from_memory(merge) 失败 error=%s", e)
        _record_provenance_safe(
            memory_id=fused_with_id,
            action_name="merge",
            content_before=content_before,
            content_after=str(merged_mem.get("content") or ""),
            fused_id=fused_with_id,
            mem_for_labels=merged_mem,
        )
        mem_time = merged_mem.get("created_at") or merged_mem.get("last_mentioned") or now_iso
        logger_instance.debug("动态层 merge window_id=%s fused_with_id=%s", window_id, fused_with_id)
        return {"tag": tag, "entry_id": merged_mem["id"], "content": merged_mem.get("content") or "", "promoted_at": mem_time}

    return None


def _wenyou_round_skip_dynamic(round_messages: list) -> bool:
    """文游回合带 [文游] 前缀，虚构内容不参与动态层便签。"""
    for m in round_messages or []:
        c = m.get("content")
        if isinstance(c, str) and "[文游]" in (c[:120] if c else ""):
            return True
        if isinstance(c, list):
            for p in c:
                if isinstance(p, dict) and p.get("type") == "text":
                    t = str(p.get("text") or "")
                    if "[文游]" in t[:120]:
                        return True
    return False


def _apply_dynamic_body_delta(
    decision: dict,
    *,
    window_id: str,
    round_index: int,
    logger_instance=logger,
) -> None:
    if not isinstance(decision, dict):
        return
    body_delta = decision.get("body_delta")
    if not isinstance(body_delta, dict) or not body_delta:
        return
    try:
        from services.pixel_home import apply_du_body_delta

        result = apply_du_body_delta(body_delta)
        if result.get("changed"):
            logger_instance.info(
                "动态层 BODY delta 已写入 du_body_state window_id=%s round_index=%s body_delta=%s",
                window_id,
                round_index,
                body_delta,
            )
        else:
            logger_instance.debug(
                "动态层 BODY delta 无实际变化 window_id=%s round_index=%s body_delta=%s",
                window_id,
                round_index,
                body_delta,
            )
    except Exception as e:
        logger_instance.warning(
            "动态层 BODY delta 写入 du_body_state 失败 window_id=%s round_index=%s error=%s",
            window_id,
            round_index,
            e,
        )


def _step_dynamic_layer_evolve(
    window_id: str,
    round_index: int,
    round_messages: list,
    *,
    skip_dynamic_memory_write: bool = False,
    skip_body_delta: bool = False,
    dynamic_memory_recall_candidate_ids: Optional[list[str]] = None,
    query_topic_state: Optional[dict] = None,
    r2_store_module=r2_store,
    wenyou_round_skip_dynamic: Callable[[list], bool] = _wenyou_round_skip_dynamic,
    apply_one_decision: Callable[..., Optional[dict]] = _apply_one_decision,
    apply_dynamic_body_delta: Callable[..., None] = _apply_dynamic_body_delta,
    body_delta_enabled: bool = DU_DYNAMIC_LAYER_BODY_DELTA_ENABLED,
    logger_instance=logger,
) -> Optional[dict]:
    """
    动态层演化：调用 DS 得到当前轮各独立事项的决策并逐条应用。
    返回首条应写记忆库的 archive 载荷，否则 None（实时对话忽略返回值）。
    """
    if wenyou_round_skip_dynamic(round_messages):
        logger_instance.info("动态层跳过：文游虚构回合 window_id=%s round_index=%s", window_id, round_index)
        return None
    from services.dynamic_layer_ds import call_dynamic_layer_ds

    current_memories = r2_store_module.get_dynamic_memory_list()
    if not skip_dynamic_memory_write:
        source_snapshot = copy.deepcopy(current_memories)
        current_memories, changed = r2_store_module.ensure_dynamic_memory_ids(current_memories)
        if changed:
            save_status = r2_store_module.save_dynamic_memory_list_if_unchanged(
                source_snapshot,
                current_memories,
            )
            if save_status != "saved":
                logger_instance.info(
                    "动态层补齐稳定字段放弃旧快照写回 status=%s window_id=%s round_index=%s",
                    save_status,
                    window_id,
                    round_index,
                )
                current_memories = r2_store_module.get_dynamic_memory_list()

    decisions = call_dynamic_layer_ds(
        round_messages,
        current_memories,
        window_id=window_id,
        round_index=round_index,
        candidate_memory_ids=list(dynamic_memory_recall_candidate_ids or []),
        query_topic_state=dict(query_topic_state or {}),
    )
    if isinstance(decisions, dict):
        decisions = [decisions]
    if not isinstance(decisions, list):
        decisions = []
    archive_payload = None
    if skip_dynamic_memory_write:
        logger_instance.info(
            "动态层记忆写入跳过 window_id=%s round_index=%s actions=%s",
            window_id,
            round_index,
            [item.get("action") for item in decisions if isinstance(item, dict)],
        )
    else:
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            applied = apply_one_decision(window_id, round_index, round_messages, decision, current_memories)
            if archive_payload is None and applied is not None:
                archive_payload = applied
    body_delta_decisions = [
        item for item in decisions if isinstance(item, dict) and item.get("body_delta")
    ]
    if skip_body_delta:
        logger_instance.info(
            "动态层 BODY delta 跳过 window_id=%s round_index=%s body_deltas=%s",
            window_id,
            round_index,
            [item.get("body_delta") for item in body_delta_decisions],
        )
    elif body_delta_enabled:
        for decision in body_delta_decisions:
            apply_dynamic_body_delta(decision, window_id=window_id, round_index=round_index)
    else:
        for decision in body_delta_decisions:
            logger_instance.info(
                "动态层 BODY delta 未应用：已由独立 evaluator 接管 window_id=%s round_index=%s body_delta=%s",
                window_id,
                round_index,
                decision.get("body_delta"),
            )
    return archive_payload
