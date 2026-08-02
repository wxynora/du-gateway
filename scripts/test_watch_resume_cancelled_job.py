#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage import runtime_sqlite, watch_analysis_store


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    with TemporaryDirectory() as directory:
        runtime_sqlite.RUNTIME_STATE_DB = Path(directory) / "runtime.sqlite3"
        runtime_sqlite._SCHEMA_READY = False
        runtime_sqlite.ensure_schema()

        now = datetime.now(timezone.utc).replace(microsecond=0)
        session_id = "watch_resume_cancelled"
        media_id = "bili:test:p1"
        with runtime_sqlite.connect() as conn:
            conn.execute(
                """
                INSERT INTO watch_sessions (
                    id, media_id, status, client_lease_expires_at,
                    created_at, updated_at, expires_at
                ) VALUES (?, ?, 'paused', ?, ?, ?, ?)
                """,
                (
                    session_id,
                    media_id,
                    _iso(now + timedelta(minutes=2)),
                    _iso(now),
                    _iso(now),
                    _iso(now + timedelta(days=1)),
                ),
            )

        session = {
            "session_id": session_id,
            "media": {"id": media_id, "duration_ms": 2_000_000},
            "playback": {"timeline_epoch": 0},
        }
        plan = {
            "purpose": "rolling",
            "target_timestamps_ms": [760_000, 780_000, 800_000],
        }

        first, created = watch_analysis_store.enqueue_source_plan(
            session=session,
            plan=plan,
        )
        assert created is True
        assert first["max_attempts"] == 3
        assert watch_analysis_store.mark_job_cancelled(
            first["job_id"],
            reason="cancel_requested",
        )

        second, created = watch_analysis_store.enqueue_source_plan(
            session=session,
            plan=plan,
        )
        assert created is True
        assert second["job_id"] != first["job_id"]
        assert second["status"] == "queued"
        assert second["max_attempts"] == 3

        repeated, created = watch_analysis_store.enqueue_source_plan(
            session=session,
            plan=plan,
        )
        assert created is False
        assert repeated["job_id"] == second["job_id"]

        runtime = watch_analysis_store.session_job_runtime(session_id)
        assert runtime["counts"] == {"cancelled": 1, "queued": 1}
        assert runtime["latest_job"]["job_id"] == second["job_id"]
        assert runtime["latest_job"]["cancel_requested"] is False

        failed_session_id = "watch_resume_failed"
        failed_media_id = "bili:failed:p1"
        with runtime_sqlite.connect() as conn:
            conn.execute(
                """
                INSERT INTO watch_sessions (
                    id, media_id, source, duration_ms, status,
                    analysis_familiarity, analysis_covered_until_ms, started_at,
                    client_lease_expires_at, created_at, updated_at, expires_at
                ) VALUES (?, ?, 'bilibili_embed', 2000000, 'paused',
                          'recognized', 760000, ?, ?, ?, ?, ?)
                """,
                (
                    failed_session_id,
                    failed_media_id,
                    _iso(now),
                    _iso(now + timedelta(minutes=2)),
                    _iso(now),
                    _iso(now),
                    _iso(now + timedelta(days=1)),
                ),
            )

        resumed_session = {
            "session_id": failed_session_id,
            "resumed_from_progress": True,
            "media": {
                "id": failed_media_id,
                "source": "bilibili_embed",
                "duration_ms": 2_000_000,
                "content_start_ms": 0,
                "content_end_ms": 2_000_000,
            },
            "mode": {"knowledge_mode": "known"},
            "playback": {"playhead_ms": 600_000, "timeline_epoch": 0},
            "analysis": {"familiarity": "recognized", "covered_until_ms": 760_000},
            "preparation": {"started_at": _iso(now)},
            "ended_at": "",
        }
        failed_plan = watch_analysis_store.build_sample_plan(resumed_session)
        assert failed_plan["purpose"] == "rolling"
        failed_first, created = watch_analysis_store.enqueue_source_plan(
            session=resumed_session,
            plan=failed_plan,
        )
        assert created is True
        with runtime_sqlite.connect() as conn:
            conn.execute(
                """
                UPDATE watch_analysis_jobs
                   SET status = 'failed', attempts = 3, error = '视频关键帧提取失败',
                       usage_json = ?, updated_at = ?, finished_at = ?
                 WHERE id = ?
                """,
                (
                    runtime_sqlite.json_dumps(
                        {
                            "provider_calls": 0,
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "total_tokens": 0,
                            "cost_usd": 0.0,
                        }
                    ),
                    _iso(now),
                    _iso(now),
                    failed_first["job_id"],
                ),
            )

        regular, created = watch_analysis_store.enqueue_source_plan(
            session=resumed_session,
            plan=failed_plan,
        )
        assert created is False
        assert regular["job_id"] == failed_first["job_id"]

        resumed = watch_analysis_store.enqueue_resumed_source_plan(resumed_session)
        assert resumed["created"] is True
        failed_retry = resumed["job"]
        assert failed_retry["job_id"] != failed_first["job_id"]
        assert failed_retry["max_attempts"] == 3
        with runtime_sqlite.connect() as conn:
            analysis_status = conn.execute(
                "SELECT analysis_status FROM watch_sessions WHERE id = ?",
                (failed_session_id,),
            ).fetchone()["analysis_status"]
        assert analysis_status == "analyzing"

        repeated_resume = watch_analysis_store.enqueue_resumed_source_plan(resumed_session)
        assert repeated_resume["created"] is False
        with runtime_sqlite.connect() as conn:
            retry_job_count = conn.execute(
                "SELECT COUNT(*) AS n FROM watch_analysis_jobs WHERE session_id = ?",
                (failed_session_id,),
            ).fetchone()["n"]
        assert retry_job_count == 2

        with runtime_sqlite.connect() as conn:
            conn.execute(
                """
                UPDATE watch_analysis_jobs
                   SET status = 'failed', attempts = 3, error = '上游返回无法解析',
                       usage_json = ?, input_tokens = 100, output_tokens = 20,
                       cost_usd = 0.01, updated_at = ?, finished_at = ?
                 WHERE id = ?
                """,
                (
                    runtime_sqlite.json_dumps(
                        {
                            "provider_calls": 1,
                            "priced_calls": 1,
                            "input_tokens": 100,
                            "output_tokens": 20,
                            "total_tokens": 120,
                            "cost_usd": 0.01,
                        }
                    ),
                    _iso(now),
                    _iso(now),
                    failed_retry["job_id"],
                ),
            )
        paid_failure = watch_analysis_store.enqueue_resumed_source_plan(resumed_session)
        assert paid_failure["created"] is False
        assert paid_failure["job"]["job_id"] == failed_retry["job_id"]

    print("watch resume cancelled job regression: ok")


if __name__ == "__main__":
    main()
