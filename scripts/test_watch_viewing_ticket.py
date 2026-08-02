#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TEMP_DIR = Path(tempfile.mkdtemp(prefix="watch-viewing-ticket-test-"))
os.environ["RUNTIME_STATE_DB"] = str(TEMP_DIR / "runtime.sqlite3")
os.environ["WATCH_VISUAL_CACHE_DIR"] = str(TEMP_DIR / "visual-cache")

from flask import Blueprint, Flask  # noqa: E402

from routes.miniapp.watch import register_routes  # noqa: E402
from storage import (  # noqa: E402
    runtime_sqlite,
    stay_with_du_store,
    watch_runtime_store,
    watch_visual_store,
)


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
            "cover_url": "https://example.test/watch-cover.jpg",
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
    _assert(
        response.status_code in {200, 201},
        f"创建 P{part_index} 失败: {response.data!r}",
    )
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
    base = datetime.now(timezone.utc).replace(microsecond=0)

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
        is_playing=True,
        playback_rate=4.0,
        timeline_epoch=0,
        snapshot_seq=2,
        media_ended=True,
    )
    viewing = final["viewing_summary"]
    _assert(
        not viewing["completed"] and viewing["playback_completed"],
        "自然播到终点没有保留为待确认的播放完成状态",
    )
    _assert(viewing["played_duration_ms"] == 65_000, "跨 P 观看时长合计错误")
    _assert(viewing["ticket"] is None, "正片完成状态提前生成了票根")

    after_complete = _snapshot(
        client,
        second_session_id,
        media_id=second_session["media"]["id"],
        at=base + timedelta(seconds=160),
        playhead_ms=120_000,
        is_playing=False,
        playback_rate=4.0,
        timeline_epoch=0,
        snapshot_seq=3,
        media_ended=True,
    )
    _assert(
        after_complete["viewing_summary"]["played_duration_ms"] == 70_000,
        "达到正片终点后继续播放的真实时间没有累计",
    )
    plain_second_end = _json(
        client.delete(f"/miniapp-api/watch/sessions/{second_session_id}")
    )
    _assert(
        not plain_second_end["viewing_summary"]["completed"]
        and plain_second_end["ticket"] is None,
        "普通 session 收尾冒充已看完或生成了票根",
    )
    second_end = _json(
        client.delete(
            f"/miniapp-api/watch/sessions/{second_session_id}?viewing_action=complete"
        )
    )
    second_end_again = _json(
        client.delete(
            f"/miniapp-api/watch/sessions/{second_session_id}?viewing_action=complete"
        )
    )
    _assert(second_end["analysis_cost"] is not None, "DELETE 丢失原 analysis_cost")
    ticket_id = second_end["ticket"]["ticket_id"]
    _assert(
        second_end["ticket"]["played_duration_ms"] == 70_000,
        "显式结束生成的票根没有使用完整可信累计时长",
    )
    _assert(
        second_end_again["ticket"]["ticket_id"] == ticket_id,
        "重复显式结束生成了不同票根",
    )
    with patch.object(stay_with_du_store, "archive_watch_ticket") as archive_mock:
        title_only = client.put(
            f"/miniapp-api/watch/tickets/{ticket_id}",
            json={"title": "编辑后但不归档的片名"},
        )
    _assert(title_only.status_code == 200, f"只保存票根标题失败: {title_only.data!r}")
    title_only_payload = _json(title_only)
    _assert(
        title_only_payload["ticket"]["title"] == "编辑后但不归档的片名",
        "编辑后的作品名没有保存到服务端票根",
    )
    _assert(
        title_only_payload["archived_to_stay_with_du"] is False
        and title_only_payload["stay_with_du_entry"] is None,
        "未选择归档却写入了 Stay with Du",
    )
    archive_mock.assert_not_called()

    remote_payload = {
        "data": {
            "timeline": [],
            "moviesTodo": [
                {
                    "id": "wanted-movie-1",
                    "title": "最终确认片名",
                    "note": "原来的想看备注",
                }
            ],
            "moviesDone": [],
            "booksTodo": [],
            "booksDone": [],
        }
    }

    def fake_read_json(_client, _key):
        return deepcopy(remote_payload)

    def fake_write_json(_client, _key, payload):
        remote_payload.clear()
        remote_payload.update(deepcopy(payload))

    with (
        patch.object(stay_with_du_store, "_s3_client", return_value=object()),
        patch.object(stay_with_du_store, "_read_json", side_effect=fake_read_json),
        patch.object(stay_with_du_store, "_write_json", side_effect=fake_write_json),
    ):
        archived = client.put(
            f"/miniapp-api/watch/tickets/{ticket_id}",
            json={
                "title": "最终确认片名",
                "archive_to_stay_with_du": True,
            },
        )
        _assert(archived.status_code == 200, f"票根归档失败: {archived.data!r}")
        archived_payload = _json(archived)
        _assert(
            archived_payload["archived_to_stay_with_du"] is True,
            "后端没有返回明确的归档结果",
        )
        _assert(
            archived_payload["stay_with_du_entry"]["id"] == "wanted-movie-1"
            and archived_payload["stay_with_du_entry"]["title"] == "最终确认片名",
            "已有想看记录没有保留 id 并使用编辑后的作品名",
        )
        _assert(
            remote_payload["data"]["moviesTodo"] == []
            and len(remote_payload["data"]["moviesDone"]) == 1,
            "想看记录没有原子迁移到已看",
        )
        archived_again = client.put(
            f"/miniapp-api/watch/tickets/{ticket_id}",
            json={
                "title": "最终确认片名",
                "archive_to_stay_with_du": True,
            },
        )
    _assert(archived_again.status_code == 200, "重复保存归档失败")
    _assert(
        len(remote_payload["data"]["moviesDone"]) == 1,
        "重复保存同一张票根生成了重复已看记录",
    )
    _assert(
        _json(archived_again)["ticket"]["stay_with_du"]["entry_id"]
        == "wanted-movie-1",
        "票根没有持久化 Stay with Du 关联",
    )
    restored = _json(client.get(f"/miniapp-api/watch/viewings/{viewing_id}"))
    _assert(restored["viewing_summary"]["ticket_id"] == ticket_id, "观看详情无法恢复票根")
    tickets = _json(client.get("/miniapp-api/watch/tickets"))["tickets"]
    _assert(
        len(tickets) == 1 and tickets[0]["ticket_id"] == ticket_id,
        "跨设备票夹查询没有返回唯一票根",
    )

    unfinished = _create_part(client, part_index=1)
    unfinished_session = unfinished["session"]
    unfinished_id = unfinished_session["session_id"]
    unfinished_viewing_id = unfinished_session["viewing_id"]
    _unlock(unfinished_id)
    _snapshot(
        client,
        unfinished_id,
        media_id=unfinished_session["media"]["id"],
        at=base + timedelta(seconds=200),
        playhead_ms=201_000,
        is_playing=False,
        playback_rate=1.0,
        timeline_epoch=0,
        snapshot_seq=1,
    )
    frame_path = TEMP_DIR / "ticket-frame.webp"
    frame_path.write_bytes(b"ticket-frame")
    frame = watch_visual_store.upsert_frame(
        frame_id="watch_frame_ticket_test",
        session_id=unfinished_id,
        media_id=unfinished_session["media"]["id"],
        timeline_epoch=0,
        at_ms=180_000,
        file_path=str(frame_path),
        width=768,
        height=432,
        sha256="ticket-frame-test",
        source_sample_id="sample-ticket-test",
    )
    selected = client.put(
        f"/miniapp-api/watch/viewings/{unfinished_viewing_id}/ticket-frame",
        json={"session_id": unfinished_id, "frame_id": frame["id"]},
    )
    _assert(selected.status_code == 200, f"选择票根画面失败: {selected.data!r}")
    unfinished_end = _json(
        client.delete(
            f"/miniapp-api/watch/sessions/{unfinished_id}?viewing_action=save_progress"
        )
    )
    _assert(
        not unfinished_end["viewing_summary"]["completed"]
        and unfinished_end["ticket"] is None
        and unfinished_end["viewing_summary"]["status_text"] == "已看67%"
        and unfinished_end["viewing_summary"]["ticket_back_frame"] is not None,
        "保存进度没有保留百分比、票根画面或错误生成了票根",
    )
    recent = _json(client.get("/miniapp-api/watch/viewings?status=recent"))["viewings"]
    saved_recent = next(
        item for item in recent if item["viewing_id"] == unfinished_viewing_id
    )
    _assert(
        saved_recent["cover_url"] == "https://example.test/watch-cover.jpg"
        and saved_recent["can_resume"]
        and saved_recent["status_text"] == "已看67%",
        "最近观看没有返回续播封面和百分比",
    )
    resumed = _create_part(client, part_index=1, viewing_id=unfinished_viewing_id)
    _assert(
        resumed["session"]["session_id"] == unfinished_id
        and resumed["session"]["resumed_from_progress"]
        and resumed["session"]["playback"]["playhead_ms"] == 201_000,
        "最近观看没有恢复同一 viewing 的播放位置和剧情 session",
    )
    completed = _json(
        client.delete(
            f"/miniapp-api/watch/sessions/{unfinished_id}?viewing_action=complete"
        )
    )
    _assert(
        completed["viewing_summary"]["completed"]
        and completed["viewing_summary"]["status_text"] == "已看完"
        and completed["ticket"]["back_frame"] is not None,
        "选择已看完没有生成带所选画面的稳定票根",
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
            "retained_for_resume",
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
            "retained_for_resume",
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
