from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 2)[0])

from services.dynamic_memory_keywords import extract_keywords_for_memories
from storage import dynamic_memory_mirror_store as mirror


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _sample_memories() -> list[dict]:
    return [
        {
            "id": "mem_1",
            "content": "辛玥想给百万计划这个文游的动态记忆补关键词，方便以后按主题召回。",
            "retrieval_text": "百万计划 文游 动态记忆 关键词 召回",
            "tag": "开发",
            "importance": 4,
            "mention_count": 2,
            "created_at": "2026-06-20T10:00:00+08:00",
            "last_mentioned": "2026-06-20T10:10:00+08:00",
            "emotion_label": "neutral",
            "scene_type": "planning",
            "target_type": "memory",
        },
        {
            "id": "mem_2",
            "content": "她希望 SQLite mirror 只能当 R2 的可搜索复印件，不能反写污染原件。",
            "retrieval_text": "SQLite mirror R2 可搜索复印件",
            "tag": "开发",
            "importance": 5,
            "mention_count": 1,
            "created_at": "2026-06-20T10:05:00+08:00",
            "last_mentioned": "2026-06-20T10:15:00+08:00",
            "emotion_label": "neutral",
            "scene_type": "planning",
            "target_type": "memory",
        },
    ]


def test_mirror_sync_is_idempotent_and_rebuildable() -> None:
    old_db = mirror.DYNAMIC_MEMORY_MIRROR_DB
    old_ready = mirror._SCHEMA_READY
    old_fts = mirror._FTS_AVAILABLE
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "dynamic_memory_mirror.sqlite3"
        mirror.DYNAMIC_MEMORY_MIRROR_DB = db
        mirror._SCHEMA_READY = False
        mirror._FTS_AVAILABLE = False
        try:
            memories = _sample_memories()
            original = copy.deepcopy(memories)
            terms = extract_keywords_for_memories(memories, max_terms=32)

            dry = mirror.sync_memories(memories, terms_by_id=terms, source="test", dry_run=True)
            _assert(dry["dry_run"] is True, "dry-run result should say dry_run")
            _assert(not db.exists(), "dry-run should not create sqlite db")

            first = mirror.sync_memories(memories, terms_by_id=terms, source="test", dry_run=False)
            _assert(first["inserted_count"] == 2, "first sync should insert two memories")
            _assert(first["keyword_count"] > 0, "first sync should write keywords")
            _assert(memories == original, "sync should not mutate source memories")

            items = mirror.list_items(limit=10)
            _assert(len(items) == 2, "mirror should list two active memories")
            _assert(any(item["keywords"] for item in items), "mirrored items should include keywords")
            _assert(mirror.find_by_keyword("百万计划"), "keyword lookup should find million-plan memory")
            shadow = mirror.shadow_candidates("百万计划 动态记忆", keywords=["百万计划", "动态记忆"], limit=5)
            _assert(shadow["ok"] is True, "shadow candidates should be ok")
            _assert(shadow["candidate_count"] >= 1, "shadow candidates should find a memory")
            _assert(
                any(item.get("memory_id") == "mem_1" for item in shadow.get("candidates") or []),
                "shadow candidates should include mem_1",
            )
            tag_only = mirror.shadow_candidates("开发", keywords=["开发"], limit=5)
            _assert(tag_only["candidate_count"] == 0, "tag-only low-signal query should not produce candidates")
            generic = mirror.shadow_candidates("拒绝", keywords=["拒绝"], limit=5)
            _assert(generic["candidate_count"] == 0, "generic stop term should not produce candidates")

            second = mirror.sync_memories(memories, terms_by_id=terms, source="test", dry_run=False)
            _assert(second["unchanged_count"] == 2, "second identical sync should be unchanged")

            changed = copy.deepcopy(memories[:1])
            changed[0]["content"] = changed[0]["content"] + " 她强调先不接聊天注入。"
            changed[0]["mention_count"] = 3
            changed_terms = extract_keywords_for_memories(changed, max_terms=32)
            third = mirror.sync_memories(changed, terms_by_id=changed_terms, source="test", dry_run=False)
            _assert(third["updated_count"] == 1, "changed memory should update")
            _assert(third["inactive_count"] == 1, "missing memory should be marked inactive")

            status = mirror.get_status()
            _assert(status["ok"] is True, "status should be ok")
            _assert(status["active_count"] == 1, "one active memory should remain")
            _assert(status["inactive_count"] == 1, "one inactive memory should remain")

            cleared = mirror.clear_all()
            _assert(cleared >= 5, "clear_all should clear mirror tables")
            _assert(mirror.get_status()["active_count"] == 0, "clear_all should remove active rows")
        finally:
            mirror.DYNAMIC_MEMORY_MIRROR_DB = old_db
            mirror._SCHEMA_READY = old_ready
            mirror._FTS_AVAILABLE = old_fts


if __name__ == "__main__":
    test_mirror_sync_is_idempotent_and_rebuildable()
    print("ok")
