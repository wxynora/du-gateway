#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TEMP_DIR = Path(tempfile.mkdtemp(prefix="watch-viewing-ticket-test-"))
os.environ["RUNTIME_STATE_DB"] = str(TEMP_DIR / "runtime.sqlite3")

from flask import Blueprint, Flask  # noqa: E402

from routes.miniapp.watch import register_routes  # noqa: E402
from storage import runtime_sqlite, watch_runtime_store  # noqa: E402


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _json(response) -> dict:
    payload = response.get_json(silent=True)
    _assert(isinstance(payload, dict), f"响应不是 JSON 对象: {response.data!r}")
    return payload


def _client():
    app = Flask(__name__)
    blueprint = Blueprint("watch_viewing_test", __name__, url_prefix="/miniapp-api")
    register_routes(blueprint)
    app.register_blueprint(blueprint)
    return app.test_client()


def _create_part(client, *, part_index: int, viewing_id: str = "") -> dict:
    payload = {
        "window_id": "sumitalk:viewing-ticket",
        "companion": {"id": "companion", "name": "陪伴者"},
        "media": {
            "id": f"bili:BV-viewing:p{part_index}",
            "source": "bilibili_embed",
            "title": "跨分 P 测试电影",
            "part_title": f"P{part_index}",
            "part_key": f"p{part_index}",
            "part_index": part_index,
            "part_count": 2,
            "work_key": "movie:test:two-parts",
            "duration_ms": 600_000 if part_index == 1 else 120_000,
            "content_end_ms": 300_000 if part_index == 1 else 100_000,
        },
        "mode": {"knowledge_mode": "known", "fear_mode": False},
    }
    if viewing_id:
        payload["viewing_id"] = viewing_id
    response = client.post("/miniapp-api/watch/sessions", json=payload)
    _assert(response.status_code == 201, f"创建 P{part_index} 失败: {response.data!r}")
    return _json(response)


def _unlock(session_id: str) -> None:
    with runtime_sqlite.connect() as conn:
        conn.execute(
            """
            UPDATE watch_sessions
               SET started_at = '2026-07-21T00:00:00Z',
                   playback_unlocked_at = '2026-07-21T00:00:00Z'
             WHERE id = ?
            """,
            (session_id,),
        )


def _snapshot(
    client,
    session_id: str,
    *,
    media_id: str,
    at: datetime,
    playhead_ms: int,
    is_playing: bool,
    playback_rate: float,
    timeline_epoch: int,
    snapshot_seq: int,
    media_ended: bool = False,
) -> dict:
    with patch.object(watch_runtime_store, "_now", return_value=at):
        response = client.put(
            f"/miniapp-api/watch/sessions/{session_id}/playback",
            json={
                "media_id": media_id,
                "playhead_ms": playhead_ms,
                "is_playing": is_playing,
                "playback_rate": playback_rate,
                "timeline_epoch": timeline_epoch,
                "snapshot_seq": snapshot_seq,
                "captured_at": at.isoformat(),
                "media_ended": media_ended,
            },
        )
    _assert(response.status_code == 200, f"播放快照失败: {response.data!r}")
    return _json(response)


def run() -> None:
    runtime_sqlite._SCHEMA_READY = False
    client = _client()
    base = datetime(2026, 7, 21, tzinfo=timezone.utc)

    first = _create_part(client, part_index=1)
    first_session = first["session"]
    first_session_id = first_session["session_id"]
    viewing_id = first_session["viewing_id"]
    _assert(viewing_id, "首个分 P 没有返回 viewing_id")
    _assert(first["viewing_summary"]["part_count"] == 2, "跨 P 总数没有保存")
    _unlock(first_session_id)

    _snapshot(
        client,
        first_session_id,
        media_id=first_session["media"]["id"],
        at=base,
        playhead_ms=0,
        is_playing=True,
        playback_rate=2.0,
        timeline_epoch=0,
        snapshot_seq=1,
    )
    paused = _snapshot(
        client,
        first_session_id,
        media_id=first_session["media"]["id"],
        at=base + timedelta(seconds=30),
        playhead_ms=60_000,
        is_playing=False,
        playback_rate=2.0,
        timeline_epoch=0,
        snapshot_seq=2,
    )
    _assert(
        paused["session"]["playback"]["played_duration_ms"] == 30_000,
        "2 倍速没有按真实观看时间累计",
    )
    paused_again = _snapshot(
        client,
        first_session_id,
        media_id=first_session["media"]["id"],
        at=base + timedelta(seconds=90),
        playhead_ms=60_000,
        is_playing=False,
        playback_rate=2.0,
        timeline_epoch=0,
        snapshot_seq=3,
    )
    _assert(
        paused_again["session"]["playback"]["played_duration_ms"] == 30_000,
        "暂停时间被计入真实观看时长",
    )
    _snapshot(
        client,
        first_session_id,
        media_id=first_session["media"]["id"],
        at=base + timedelta(seconds=100),
        playhead_ms=60_000,
        is_playing=True,
        playback_rate=1.0,
        timeline_epoch=0,
        snapshot_seq=4,
    )
    after_seek = _snapshot(
        client,
        first_session_id,
        media_id=first_session["media"]["id"],
        at=base + timedelta(seconds=110),
        playhead_ms=290_000,
        is_playing=True,
        playback_rate=1.0,
        timeline_epoch=1,
        snapshot_seq=1,
    )
    _assert(
        after_seek["session"]["playback"]["played_duration_ms"] == 30_000,
        "seek 跳过的媒体区间被计入观看时长",
    )
    first_complete = _snapshot(
        client,
        first_session_id,
        media_id=first_session["media"]["id"],
        at=base + timedelta(seconds=120),
        playhead_ms=300_000,
        is_playing=False,
        playback_rate=1.0,
        timeline_epoch=1,
        snapshot_seq=2,
        media_ended=True,
    )
    _assert(
        first_complete["session"]["playback"]["played_duration_ms"] == 40_000,
        "seek 后连续播放区间没有继续累计",
    )
    _assert(
        not first_complete["viewing_summary"]["completed"],
        "只看完 P1 就错误生成了整部票根",
    )
    _assert(first_complete["viewing_summary"]["ticket"] is None, "P1 提前生成票根")

    first_end = _json(client.delete(f"/miniapp-api/watch/sessions/{first_session_id}"))
    first_end_again = _json(client.delete(f"/miniapp-api/watch/sessions/{first_session_id}"))
    _assert(first_end["ticket"] is None, "结束 P1 冒充整部看完")
    _assert(
        first_end_again["viewing_summary"]["played_duration_ms"] == 40_000,
        "重复 DELETE 改写了累计时长",
    )

    second = _create_part(client, part_index=2, viewing_id=viewing_id)
    second_session = second["session"]
    second_session_id = second_session["session_id"]
    _assert(second_session["viewing_id"] == viewing_id, "切 P 没有复用 viewing_id")
    _unlock(second_session_id)
    _snapshot(
        client,
        second_session_id,
        media_id=second_session["media"]["id"],
        at=base + timedelta(seconds=130),
        playhead_ms=0,
        is_playing=True,
        playback_rate=4.0,
        timeline_epoch=0,
        snapshot_seq=1,
    )
    final = _snapshot(
        client,
        second_session_id,
        media_id=second_session["media"]["id"],
        at=base + timedelta(seconds=155),
        playhead_ms=100_000,
        is_playing=False,
        playback_rate=4.0,
        timeline_epoch=0,
        snapshot_seq=2,
        media_ended=True,
    )
    viewing = final["viewing_summary"]
    _assert(viewing["completed"], "最终 P 播完没有完成整次观看")
    _assert(viewing["played_duration_ms"] == 65_000, "跨 P 观看时长合计错误")
    _assert(viewing["ticket"], "完成整次观看后没有生成票根")
    ticket_id = viewing["ticket_id"]
    _assert(
        viewing["ticket"]["played_duration_ms"] == 65_000,
        "票根没有使用服务端累计时长",
    )
    after_complete = _snapshot(
        client,
        second_session_id,
        media_id=second_session["media"]["id"],
        at=base + timedelta(seconds=165),
        playhead_ms=100_000,
        is_playing=False,
        playback_rate=4.0,
        timeline_epoch=0,
        snapshot_seq=3,
        media_ended=True,
    )
    _assert(
        after_complete["viewing_summary"]["played_duration_ms"] == 65_000
        and after_complete["viewing_summary"]["ticket_id"] == ticket_id,
        "完成后的新快照改写了稳定票根",
    )

    second_end = _json(client.delete(f"/miniapp-api/watch/sessions/{second_session_id}"))
    second_end_again = _json(client.delete(f"/miniapp-api/watch/sessions/{second_session_id}"))
    _assert(second_end["analysis_cost"] is not None, "DELETE 丢失原 analysis_cost")
    _assert(second_end["ticket"]["ticket_id"] == ticket_id, "DELETE 没有返回稳定票根")
    _assert(
        second_end_again["ticket"]["ticket_id"] == ticket_id,
        "重复 DELETE 生成了不同票根",
    )
    restored = _json(client.get(f"/miniapp-api/watch/viewings/{viewing_id}"))
    _assert(restored["viewing_summary"]["ticket_id"] == ticket_id, "观看详情无法恢复票根")
    tickets = _json(client.get("/miniapp-api/watch/tickets"))["tickets"]
    _assert(
        len(tickets) == 1 and tickets[0]["ticket_id"] == ticket_id,
        "跨设备票夹查询没有返回唯一票根",
    )

    unfinished = _create_part(client, part_index=1)
    unfinished_id = unfinished["session"]["session_id"]
    unfinished_end = _json(client.delete(f"/miniapp-api/watch/sessions/{unfinished_id}"))
    _assert(
        not unfinished_end["viewing_summary"]["completed"]
        and unfinished_end["ticket"] is None,
        "DELETE 把未播放会话冒充成了看完",
    )

    with runtime_sqlite.connect() as conn:
        conn.execute("DROP INDEX IF EXISTS idx_watch_sessions_viewing")
        for column in (
            "viewing_id",
            "work_key",
            "part_key",
            "part_index",
            "part_count",
            "playback_observed_at",
            "played_duration_ms",
            "completed_at",
            "completion_event_id",
        ):
            conn.execute(f"ALTER TABLE watch_sessions DROP COLUMN {column}")
    runtime_sqlite._SCHEMA_READY = False
    runtime_sqlite.ensure_schema()
    with runtime_sqlite.connect() as conn:
        migrated_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(watch_sessions)").fetchall()
        }
        migrated_indexes = {
            str(row["name"])
            for row in conn.execute("PRAGMA index_list(watch_sessions)").fetchall()
        }
    _assert(
        {
            "viewing_id",
            "work_key",
            "part_key",
            "part_index",
            "part_count",
            "playback_observed_at",
            "played_duration_ms",
            "completed_at",
            "completion_event_id",
        }.issubset(migrated_columns),
        "老 watch_sessions 表没有补齐观看聚合字段",
    )
    _assert(
        "idx_watch_sessions_viewing" in migrated_indexes,
        "老库加列后没有创建 viewing 索引",
    )


if __name__ == "__main__":
    try:
        run()
        print("watch viewing ticket tests passed")
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
