from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 2)[0])

import services.dynamic_memory_provenance as provenance


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_provenance_events_are_queryable() -> None:
    old_db = provenance.DYNAMIC_MEMORY_PROVENANCE_DB
    old_ready = provenance._SCHEMA_READY
    with tempfile.TemporaryDirectory() as tmp:
        provenance.DYNAMIC_MEMORY_PROVENANCE_DB = Path(tmp) / "provenance.sqlite3"
        provenance._SCHEMA_READY = False
        try:
            ok = provenance.record_event(
                memory_id="mem_1",
                action="new",
                window_id="tg_1",
                round_index=7,
                event_time="2026-06-08T12:00:00+08:00",
                content_after="她说要把动态记忆血缘做成 SQL 表，方便以后按 id 追查来源。",
                tag="开发",
                importance=3,
                decision={"action": "new"},
            )
            _assert(ok, "new provenance event should be recorded")

            ok = provenance.record_event(
                memory_id="mem_1",
                action="merge",
                window_id="tg_1",
                round_index=9,
                event_time="2026-06-08T12:05:00+08:00",
                content_before="她想追查动态记忆来源。",
                content_after="她希望动态记忆用 SQL 血缘表记录 new/merge 来源，方便按 memory_id 重写。",
                fused_with_id="mem_1",
                related_memory_ids=["old_2"],
                tag="开发",
                importance=4,
                decision={"action": "merge", "fused_with_id": "mem_1"},
            )
            _assert(ok, "merge provenance event should be recorded")

            events = provenance.list_events_for_memory("mem_1")
            _assert(len(events) == 2, "memory_id query should return both events")
            _assert([e["action"] for e in events] == ["new", "merge"], "events should keep chronological order")
            _assert(events[1]["related_memory_ids"] == ["old_2"], "related memory ids should round-trip")

            round_events = provenance.list_events_for_round("tg_1", 9)
            _assert(len(round_events) == 1, "round query should return the merge event")
            _assert(round_events[0]["memory_id"] == "mem_1", "round query should include memory id")

            ok = provenance.record_event(
                memory_id="old_2",
                action="new",
                window_id="tg_1",
                round_index=6,
                event_time="2026-06-08T11:58:00+08:00",
                content_after="一条后来被淘汰的旧记忆。",
            )
            _assert(ok, "old memory event should be recorded before delete")
            deleted = provenance.delete_events_for_memories({"old_2", ""})
            _assert(deleted == 1, "delete should remove provenance rows for pruned memories")
            _assert(provenance.list_events_for_memory("old_2") == [], "deleted memory should have no provenance events")
            _assert(len(provenance.list_events_for_memory("mem_1")) == 2, "deleting another memory should not touch current memory")
        finally:
            provenance.DYNAMIC_MEMORY_PROVENANCE_DB = old_db
            provenance._SCHEMA_READY = old_ready


if __name__ == "__main__":
    test_provenance_events_are_queryable()
    print("dynamic memory provenance checks passed")
