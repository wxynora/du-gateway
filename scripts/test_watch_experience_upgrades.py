from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from storage import (
    runtime_sqlite,
    stay_with_du_store,
    watch_analysis_store,
    watch_runtime_store,
    watch_subtitle_store,
    watch_viewing_store,
    watch_visual_store,
)


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _insert_session(session_id: str, *, now_iso: str) -> None:
    with runtime_sqlite.connect() as conn:
        conn.execute(
            """
            INSERT INTO watch_sessions (
                id, media_id, timeline_epoch, created_at, updated_at, expires_at
            ) VALUES (?, 'media-1', 0, ?, ?, ?)
            """,
            (session_id, now_iso, now_iso, "2099-01-01T00:00:00Z"),
        )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runtime_sqlite.RUNTIME_STATE_DB = str(Path(tmp) / "runtime.sqlite3")
        runtime_sqlite._SCHEMA_READY = False
        runtime_sqlite.ensure_schema()
        now = datetime.now(timezone.utc).replace(microsecond=0)
        now_iso = _iso(now)

        _insert_session("visual-session", now_iso=now_iso)
        frame_path = Path(tmp) / "frame.webp"
        frame_path.write_bytes(b"frame")
        watch_visual_store.upsert_frame(
            frame_id="frame-1",
            session_id="visual-session",
            media_id="media-1",
            timeline_epoch=0,
            at_ms=1000,
            file_path=str(frame_path),
            width=1,
            height=1,
            sha256="abc",
            source_sample_id="sample-1",
        )
        second_frame_path = Path(tmp) / "frame-2.webp"
        second_frame_path.write_bytes(b"frame-2")
        watch_visual_store.upsert_frame(
            frame_id="frame-2",
            session_id="visual-session",
            media_id="media-1",
            timeline_epoch=0,
            at_ms=2000,
            file_path=str(second_frame_path),
            width=1,
            height=1,
            sha256="def",
            source_sample_id="sample-2",
        )
        watch_visual_store.delete_session_frames("visual-session")
        visual_status = watch_visual_store.frame_cache_status(
            "visual-session", timeline_epoch=0
        )
        assert visual_status["count"] == 0
        assert visual_status["generation_status"] == "ready"
        assert visual_status["generation_ready_at"]

        _insert_session("latency-session", now_iso=now_iso)
        with runtime_sqlite.connect() as conn:
            conn.executemany(
                """
                INSERT INTO watch_reply_latency_samples (
                    job_id, session_id, request_created_ts, visible_ts,
                    latency_ms, source, updated_at
                ) VALUES (?, 'latency-session', 0, 0, ?, ?, ?)
                """,
                [
                    (
                        "old-gateway",
                        120000,
                        "gateway_first_visible",
                        _iso(now - timedelta(hours=2)),
                    ),
                    ("recent-client", 30000, "client_displayed", now_iso),
                ],
            )
        latency = watch_runtime_store.get_reply_latency_profile("latency-session")
        assert latency["sample_count"] == 2
        assert latency["average_latency_ms"] < 40000
        assert latency["latest_source"] == "client_displayed"

        original_get_asset = watch_subtitle_store.get_asset_for_session
        watch_subtitle_store.get_asset_for_session = lambda _session: {
            "cues": [
                {"start": 10.5, "end": 11.5, "text": "第一句"},
                {"start": 20.5, "end": 21.5, "text": "第二句"},
            ]
        }
        try:
            aligned = watch_analysis_store._subtitle_aligned_targets(
                {"session_id": "subtitle-session"},
                [0, 10000, 20000, 30000],
            )
        finally:
            watch_subtitle_store.get_asset_for_session = original_get_asset
        assert aligned == [0, 11000, 21000, 30000]

        with runtime_sqlite.connect() as conn:
            conn.execute(
                """
                INSERT INTO watch_viewings (
                    id, status, ticket_id, ticket_json, created_at, updated_at
                ) VALUES ('viewing-1', 'completed', 'ticket-1', ?, ?, ?)
                """,
                (
                    runtime_sqlite.json_dumps(
                        {"ticket_id": "ticket-1", "title": "测试电影"}
                    ),
                    now_iso,
                    now_iso,
                ),
            )
        viewing = watch_viewing_store.update_viewing_reflection(
            "viewing-1",
            viewer_review="挺喜欢。",
            favorite=True,
            rating=5,
            now_iso=now_iso,
        )
        assert viewing is not None
        assert viewing["viewer_review"] == "挺喜欢。"
        assert viewing["favorite"] is True
        assert viewing["rating"] == 5
        assert viewing["ticket"]["viewer_review"] == "挺喜欢。"

        normalized = stay_with_du_store.normalize_stay_with_du_data(
            {
                "moviesDone": [
                    {
                        "id": "movie-1",
                        "title": "测试电影",
                        "favorite": True,
                        "rating": 5,
                        "viewer_review": "挺喜欢。",
                    }
                ]
            }
        )
        assert normalized["moviesDone"][0]["favorite"] is True
        assert normalized["moviesDone"][0]["rating"] == 5
        assert normalized["moviesDone"][0]["viewer_review"] == "挺喜欢。"

    print("watch experience upgrades tests ok")


if __name__ == "__main__":
    main()
