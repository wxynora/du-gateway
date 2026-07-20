#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from base64 import b64encode
from io import BytesIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEMP_DIR = Path(tempfile.mkdtemp(prefix="watch-local-lifecycle-test-"))
os.environ["RUNTIME_STATE_DB"] = str(TEMP_DIR / "runtime.sqlite3")
os.environ["WATCH_ANALYSIS_SAMPLE_DIR"] = str(TEMP_DIR / "samples")
os.environ["WATCH_VISUAL_CACHE_DIR"] = str(TEMP_DIR / "visual")
os.environ["WATCH_ANALYSIS_DAILY_MAX_COST_USD"] = "100"
os.environ["OPENROUTER_API_KEY"] = "test-watch-analysis-key"

from flask import Blueprint, Flask  # noqa: E402
from PIL import Image  # noqa: E402

from routes.miniapp import watch as watch_routes  # noqa: E402
from routes.miniapp.watch import register_routes  # noqa: E402
from scripts.run_watch_analysis_worker import (  # noqa: E402
    cleanup_abandoned_sessions,
    process_claimed_job,
    schedule_knowledge_jobs,
    schedule_source_jobs,
    schedule_subtitle_jobs,
)
from services.watch_analysis_samples import prepare_samples  # noqa: E402
from storage import (  # noqa: E402
    runtime_sqlite,
    watch_analysis_store,
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
    blueprint = Blueprint("watch_local_test", __name__, url_prefix="/miniapp-api")
    register_routes(blueprint)
    app.register_blueprint(blueprint)
    return app.test_client()


def _bilibili_session(suffix: str) -> dict:
    return watch_runtime_store.create_session(
        device_id="test-device",
        window_id=f"sumitalk:lifecycle:{suffix}",
        companion={"id": "companion", "name": "Companion"},
        media={
            "id": f"bili:BV-lifecycle-{suffix}:1",
            "source": "bilibili_embed",
            "title": f"生命周期测试 {suffix}",
            "duration_ms": 180_000,
        },
        mode={"knowledge_mode": "known", "fear_mode": False},
    )


def _expire_client_lease(session_id: str, *, preserve_updated_at: bool = False) -> None:
    with runtime_sqlite.connect() as conn:
        if preserve_updated_at:
            conn.execute(
                "UPDATE watch_sessions SET client_lease_expires_at = '2000-01-01T00:00:00Z', updated_at = '2999-01-01T00:00:00Z' WHERE id = ?",
                (session_id,),
            )
        else:
            conn.execute(
                "UPDATE watch_sessions SET client_lease_expires_at = '2000-01-01T00:00:00Z' WHERE id = ?",
                (session_id,),
            )


def _job_count(session_id: str) -> int:
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM watch_analysis_jobs WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return int(row["n"] or 0)


def _enqueue_source_job(session: dict) -> dict:
    plan = watch_analysis_store.build_sample_plan(session)
    job, created = watch_analysis_store.enqueue_source_plan(session=session, plan=plan)
    _assert(created, "测试分析任务没有入队")
    return job


def _analysis_payload() -> dict:
    return {
        "familiarity": {
            "status": "recognized",
            "identity": "生命周期测试",
            "confidence": 0.99,
        },
        "canonical_identity": {
            "title": "生命周期测试",
            "original_title": "Lifecycle Test",
            "year": 2026,
        },
        "timeline_sections": [],
        "plot_chunks": [],
        "story_so_far": {
            "through_ms": 0,
            "summary": "",
            "background": "",
            "characters": [],
            "unresolved": [],
        },
        "story_state": {
            "characters": [],
            "locations": [],
            "events": [],
            "unresolved": [],
        },
        "risk_events": [],
        "analysis_notes": "test",
    }


class _FakeResponse:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self.text = json.dumps(payload, ensure_ascii=False)
        self._payload = {
            "model": "google/gemini-2.5-flash",
            "choices": [{"message": {"content": self.text}}],
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 80,
                "total_tokens": 200,
                "cost": 0.002,
            },
        }

    def json(self) -> dict:
        return self._payload


def _test_lease_blocks_all_schedulers_and_restart_recovery() -> None:
    session = _bilibili_session("expired")
    session_id = session["session_id"]
    _expire_client_lease(session_id, preserve_updated_at=True)
    expired = watch_runtime_store.get_session(session_id)
    _assert(expired is not None, "租约测试会话意外消失")
    allowed, reason = watch_runtime_store.schedule_eligibility(expired)
    _assert(not allowed and reason == "client_lease_expired", "调度错误依赖 updated_at")
    _assert(schedule_source_jobs(limit=8)["jobs_created"] == 0, "来源调度仍给失联会话入队")
    _assert(schedule_knowledge_jobs(limit=8)["jobs_created"] == 0, "知识卡调度仍给失联会话入队")
    _assert(schedule_subtitle_jobs(limit=8)["jobs_created"] == 0, "字幕调度仍给失联会话入队")
    _assert(_job_count(session_id) == 0, "失联会话产生了任务")

    cleanup = watch_runtime_store.expire_abandoned_sessions()
    _assert(cleanup["skip_reason"] == "client_lease_expired", "租约清理没有记录标准原因")
    ended = watch_runtime_store.get_session(session_id)
    _assert(ended is not None and ended["playback"]["status"] == "ended", "重启清理没有结束失联会话")
    _assert(watch_analysis_store.claim_next_job(stale_after_seconds=60) is None, "worker 重启复活了失联会话")

    legacy = _bilibili_session("legacy")
    legacy_job = _enqueue_source_job(legacy)
    with runtime_sqlite.connect() as conn:
        conn.execute(
            "UPDATE watch_sessions SET client_seen_at = '', client_lease_expires_at = '', status = 'paused', ended_at = '' WHERE id = ?",
            (legacy["session_id"],),
        )
    legacy_cleanup = watch_runtime_store.expire_abandoned_sessions()
    _assert(legacy_cleanup["sessions_ended"] >= 1, "历史空租约会话没有被明确结束")
    stored_job = watch_analysis_store.get_job(legacy_job["job_id"], public=True)
    _assert(stored_job and stored_job["status"] == "cancelled", "历史会话的 queued 任务没有取消")

    orphan = _bilibili_session("orphan-samples")
    source_image = BytesIO()
    Image.new("RGB", (32, 18), color=(60, 100, 140)).save(source_image, format="PNG")
    prepared = prepare_samples(
        session_id=orphan["session_id"],
        media_id=orphan["media"]["id"],
        timeline_epoch=0,
        duration_ms=orphan["media"]["duration_ms"],
        purpose="identify",
        raw_samples=[
            {
                "at_ms": 0,
                "mime_type": "image/png",
                "image_bytes": source_image.getvalue(),
            }
        ],
    )
    sample_path = Path(prepared[0]["file_path"])
    orphan_job, created = watch_analysis_store.enqueue_samples(
        session=orphan,
        purpose="identify",
        samples=prepared,
        idempotency_key="watch-orphan-samples",
    )
    _assert(created and sample_path.is_file(), "失联清理测试样本没有创建")
    visual_path = TEMP_DIR / "orphan-visual.webp"
    visual_path.write_bytes(b"orphan-visual")
    watch_visual_store.upsert_frame(
        frame_id="orphan-visual",
        session_id=orphan["session_id"],
        media_id=orphan["media"]["id"],
        timeline_epoch=0,
        at_ms=0,
        file_path=str(visual_path),
        width=32,
        height=18,
        sha256="orphan-visual",
        source_sample_id=prepared[0]["id"],
    )
    with runtime_sqlite.connect() as conn:
        conn.execute(
            "UPDATE watch_sessions SET client_seen_at = '', client_lease_expires_at = '' WHERE id = ?",
            (orphan["session_id"],),
        )
    orphan_cleanup = cleanup_abandoned_sessions()
    _assert(orphan_cleanup["samples_purged"] == 1, "worker 启动清理没有删除失联样本")
    _assert(orphan_cleanup["visual_rows_deleted"] == 1, "worker 启动清理没有删除失联派生帧")
    _assert(not sample_path.exists() and not visual_path.exists(), "失联会话素材文件仍然留在磁盘")
    stored_orphan_job = watch_analysis_store.get_job(orphan_job["job_id"], public=True)
    _assert(stored_orphan_job and stored_orphan_job["status"] == "cancelled", "失联样本任务没有取消")


def _test_schema_restart_does_not_unlock_fear_gate() -> None:
    session = watch_runtime_store.create_session(
        device_id="test-device",
        window_id="sumitalk:lifecycle:fear-restart",
        companion={"id": "companion", "name": "Companion"},
        media={
            "id": "bili:BV-lifecycle-fear-restart:1",
            "source": "bilibili_embed",
            "title": "胆小模式迁移测试",
            "duration_ms": 180_000,
        },
        mode={"knowledge_mode": "known", "fear_mode": True},
    )
    with runtime_sqlite.connect() as conn:
        conn.execute(
            "UPDATE watch_sessions SET started_at = '2026-07-20T01:00:00Z', "
            "playback_unlocked_at = '', analysis_status = 'pending', "
            "analysis_covered_until_ms = 0 WHERE id = ?",
            (session["session_id"],),
        )

    runtime_sqlite._SCHEMA_READY = False
    runtime_sqlite.ensure_schema()

    restarted = watch_runtime_store.get_session(session["session_id"])
    _assert(restarted is not None, "重启门禁测试会话意外消失")
    _assert(
        not restarted["preparation"]["playback_unlocked_at"],
        "schema 重启错误回填了仍在等待保护的 playback_unlocked_at",
    )
    gate = watch_runtime_store.get_start_gate(restarted)
    _assert(
        gate["status"] == "buffering" and not gate["can_play"],
        "进程重启后胆小模式首段保护门禁被绕过",
    )


def _test_end_races_do_not_call_or_commit_model() -> None:
    session = _bilibili_session("claimed-end")
    source_job = _enqueue_source_job(session)
    claimed = watch_analysis_store.claim_next_job(stale_after_seconds=60)
    _assert(claimed and claimed["job_id"] == source_job["job_id"], "没有领取目标任务")
    ended = watch_runtime_store.end_session(session["session_id"])
    _assert(
        ended["end_cleanup"]["running_cancel_requested"] == 1,
        "结束会话没有给运行中任务写 cancel_requested",
    )
    calls = {"source": 0, "model": 0}

    class _Source:
        def acquire(self, *_args, **_kwargs):
            calls["source"] += 1
            return []

    def _post(*_args, **_kwargs):
        calls["model"] += 1
        return _FakeResponse(_analysis_payload())

    outcome = process_claimed_job(claimed, source=_Source(), post=_post)
    _assert(outcome["reason"] == "cancel_requested", "已结束任务没有按 cancel_requested 跳过")
    _assert(calls == {"source": 0, "model": 0}, "结束后的已领取任务仍调用了外部服务")
    stored = watch_analysis_store.get_job(source_job["job_id"], public=False)
    _assert(stored and not stored["usage"], "未调用模型的任务错误记录了 usage")

    during_source = _bilibili_session("during-source")
    during_job = _enqueue_source_job(during_source)
    claimed_during = watch_analysis_store.claim_next_job(stale_after_seconds=60)
    _assert(claimed_during and claimed_during["job_id"] == during_job["job_id"], "没有领取来源竞态任务")
    source_calls = 0
    model_calls = 0

    class _EndingSource:
        def acquire(self, *_args, **_kwargs):
            nonlocal source_calls
            source_calls += 1
            watch_runtime_store.end_session(during_source["session_id"])
            return [{"at_ms": 0, "text_content": "不会进入模型"}]

    def _should_not_call(*_args, **_kwargs):
        nonlocal model_calls
        model_calls += 1
        return _FakeResponse(_analysis_payload())

    source_outcome = process_claimed_job(
        claimed_during,
        source=_EndingSource(),
        post=_should_not_call,
    )
    _assert(source_calls == 1 and model_calls == 0, "取材后结束仍调用了模型")
    _assert(source_outcome["reason"] == "cancel_requested", "取材后竞态没有取消任务")

    during_model = _bilibili_session("during-model")
    raw_samples = [{"at_ms": 0, "text_content": "模型竞态测试"}]
    prepared = prepare_samples(
        session_id=during_model["session_id"],
        media_id=during_model["media"]["id"],
        timeline_epoch=0,
        duration_ms=during_model["media"]["duration_ms"],
        purpose="identify",
        raw_samples=raw_samples,
    )
    model_job, created = watch_analysis_store.enqueue_samples(
        session=during_model,
        purpose="identify",
        samples=prepared,
        idempotency_key="watch-model-race",
    )
    _assert(created, "模型竞态任务没有入队")
    claimed_model = watch_analysis_store.claim_next_job(stale_after_seconds=60)
    _assert(claimed_model and claimed_model["job_id"] == model_job["job_id"], "没有领取模型竞态任务")
    actual_model_calls = 0

    def _ending_post(*_args, **_kwargs):
        nonlocal actual_model_calls
        actual_model_calls += 1
        watch_runtime_store.end_session(during_model["session_id"])
        return _FakeResponse(_analysis_payload())

    model_outcome = process_claimed_job(claimed_model, post=_ending_post)
    _assert(actual_model_calls == 1, "模型竞态测试没有真正进入模型调用边界")
    _assert(model_outcome["reason"] == "cancel_requested", "模型返回后没有再次验活")
    stored_model_job = watch_analysis_store.get_job(model_job["job_id"], public=False)
    _assert(stored_model_job and not stored_model_job["usage"], "竞态取消后仍提交了模型 usage")
    with runtime_sqlite.connect() as conn:
        chunks = conn.execute(
            "SELECT COUNT(*) AS n FROM watch_plot_chunks WHERE session_id = ?",
            (during_model["session_id"],),
        ).fetchone()
    _assert(int(chunks["n"] or 0) == 0, "竞态取消后仍写回剧情结果")


def _local_media_payload(*, revision: str = "rev-1", subtitle_kind: str = "external") -> dict:
    return {
        "id": "local:asset-1",
        "source": "local_file",
        "title": "本地测试电影",
        "duration_ms": 180_000,
        "content_start_ms": 0,
        "content_end_ms": 180_000,
        "local_media": {
            "local_asset_id": "asset-1",
            "media_revision": revision,
            "capabilities": {
                "can_play": True,
                "can_seek": True,
                "can_read_future": True,
                "can_export_frames": True,
                "can_export_audio": False,
                "has_audio": True,
                "is_drm": False,
            },
            "selected_audio": {
                "track_id": "audio-main",
                "language": "ja",
                "label": "日语",
            },
            "selected_subtitle": {
                "kind": subtitle_kind,
                "track_id": "external-zh",
                "language": "zh-CN",
                "label": "中文字幕",
                "format": "srt" if subtitle_kind != "none" else "",
                "offset_ms": 500,
            },
        },
    }


def _test_local_http_contract() -> None:
    client = _client()
    response = client.post(
        "/miniapp-api/watch/sessions",
        json={
            "window_id": "sumitalk:local-contract",
            "companion": {"id": "companion", "name": "Companion"},
            "media": _local_media_payload(),
            "mode": {"knowledge_mode": "known", "fear_mode": False},
        },
    )
    _assert(response.status_code == 201, f"本地会话创建失败: {response.data!r}")
    session = _json(response)["session"]
    session_id = session["session_id"]
    _assert(session["media"]["local_media"]["media_revision"] == "rev-1", "本地版本标识没有保存")
    _assert(
        session["media"]["local_media"]["sampling"]["status"] == "degraded",
        "不能导出音频时没有诚实降级到画面分析",
    )

    wrong_subtitle_track = client.post(
        f"/miniapp-api/watch/sessions/{session_id}/local-subtitles",
        json={
            "media_revision": "rev-1",
            "format": "srt",
            "track_id": "external-other",
            "subtitle_text": "1\n00:00:01,000 --> 00:00:02,000\n错误轨道。\n",
        },
    )
    _assert(wrong_subtitle_track.status_code == 400, "外挂字幕没有绑定当前选择的轨道")

    subtitle = client.post(
        f"/miniapp-api/watch/sessions/{session_id}/local-subtitles",
        json={
            "media_revision": "rev-1",
            "format": "srt",
            "track_id": "external-zh",
            "subtitle_text": "1\n00:00:01,000 --> 00:00:02,000\n你好。\n",
        },
    )
    _assert(subtitle.status_code == 201, f"本地字幕提交失败: {subtitle.data!r}")
    lookup = _json(subtitle)["subtitle_lookup"]
    _assert(lookup["status"] == "found" and lookup["coverage_start_ms"] == 1500, "字幕偏移没有应用")

    status = _json(client.get(f"/miniapp-api/watch/sessions/{session_id}/status"))
    plan = status["sample_plan"]
    _assert(plan["managed_by"] == "client" and plan["client_upload_required"], "本地取材没有下发客户端计划")
    _assert(plan["media_revision"] == "rev-1" and plan["timeline_epoch"] == 0, "取材计划缺少版本或 epoch")

    image = BytesIO()
    Image.new("RGB", (32, 18), color=(40, 90, 130)).save(image, format="PNG")
    sample_at = int(plan["target_timestamps_ms"][0])
    wrong_revision = client.post(
        f"/miniapp-api/watch/sessions/{session_id}/analysis/samples",
        json={
            "plan_id": plan["plan_id"],
            "media_revision": "rev-old",
            "purpose": plan["purpose"],
            "timeline_epoch": 0,
            "actual_range_start_ms": plan["allowed_start_ms"],
            "actual_range_end_ms": plan["allowed_end_ms"],
            "samples": [
                {
                    "at_ms": sample_at,
                    "mime_type": "image/png",
                    "image_base64": b64encode(image.getvalue()).decode("ascii"),
                }
            ],
        },
    )
    _assert(wrong_revision.status_code == 409, "旧 media_revision 的样本没有被拒绝")

    seek = client.put(
        f"/miniapp-api/watch/sessions/{session_id}/playback",
        json={
            "media_id": "local:asset-1",
            "playhead_ms": 30_000,
            "is_playing": False,
            "playback_rate": 1.0,
            "timeline_epoch": 1,
            "snapshot_seq": 1,
            "captured_at": "2026-07-20T03:40:00Z",
        },
    )
    _assert(
        seek.status_code == 200 and _json(seek)["applied"],
        f"本地 seek 快照没有应用: {seek.status_code} {seek.data!r}",
    )
    stale_plan = client.post(
        f"/miniapp-api/watch/sessions/{session_id}/analysis/samples",
        json={
            "plan_id": plan["plan_id"],
            "media_revision": "rev-1",
            "purpose": plan["purpose"],
            "timeline_epoch": 0,
            "actual_range_start_ms": plan["allowed_start_ms"],
            "actual_range_end_ms": plan["allowed_end_ms"],
            "samples": [
                {
                    "at_ms": sample_at,
                    "mime_type": "image/png",
                    "image_base64": b64encode(image.getvalue()).decode("ascii"),
                }
            ],
        },
    )
    _assert(stale_plan.status_code == 409, "seek 后旧取材计划仍被接受")

    refreshed_status = _json(client.get(f"/miniapp-api/watch/sessions/{session_id}/status"))
    refreshed_plan = refreshed_status["sample_plan"]
    _assert(
        refreshed_plan["timeline_epoch"] == 1
        and refreshed_plan["plan_id"] != plan["plan_id"],
        "seek 后没有签发新 epoch 的取材计划",
    )

    with runtime_sqlite.connect() as conn:
        jobs_before = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM watch_analysis_jobs WHERE session_id = ?",
                (session_id,),
            ).fetchone()["n"]
            or 0
        )
        samples_before = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM watch_analysis_samples WHERE session_id = ?",
                (session_id,),
            ).fetchone()["n"]
            or 0
        )
    sample_root = Path(os.environ["WATCH_ANALYSIS_SAMPLE_DIR"])
    files_before = {path for path in sample_root.rglob("*") if path.is_file()}
    original_prepare = watch_routes.prepare_samples

    def _expire_plan_after_prepare(*args, **kwargs):
        prepared = original_prepare(*args, **kwargs)
        with runtime_sqlite.connect() as conn:
            conn.execute(
                "UPDATE watch_client_sample_plans SET expires_at = '2000-01-01T00:00:00Z' WHERE id = ?",
                (refreshed_plan["plan_id"],),
            )
        return prepared

    watch_routes.prepare_samples = _expire_plan_after_prepare
    try:
        expired_during_enqueue = client.post(
            f"/miniapp-api/watch/sessions/{session_id}/analysis/samples",
            json={
                "plan_id": refreshed_plan["plan_id"],
                "media_revision": "rev-1",
                "purpose": refreshed_plan["purpose"],
                "timeline_epoch": 1,
                "actual_range_start_ms": refreshed_plan["allowed_start_ms"],
                "actual_range_end_ms": refreshed_plan["allowed_end_ms"],
                "samples": [
                    {
                        "at_ms": int(refreshed_plan["target_timestamps_ms"][0]),
                        "mime_type": "image/png",
                        "image_base64": b64encode(image.getvalue()).decode("ascii"),
                    }
                ],
            },
        )
    finally:
        watch_routes.prepare_samples = original_prepare
    _assert(expired_during_enqueue.status_code == 409, "入队事务没有拒绝中途失效的计划")
    with runtime_sqlite.connect() as conn:
        jobs_after = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM watch_analysis_jobs WHERE session_id = ?",
                (session_id,),
            ).fetchone()["n"]
            or 0
        )
        samples_after = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM watch_analysis_samples WHERE session_id = ?",
                (session_id,),
            ).fetchone()["n"]
            or 0
        )
    _assert(jobs_after == jobs_before, "计划消费失败后仍留下了半成品分析任务")
    _assert(samples_after == samples_before, "计划消费失败后仍留下了半成品样本记录")
    _assert(
        {path for path in sample_root.rglob("*") if path.is_file()} == files_before,
        "计划消费失败后仍留下了临时样本文件",
    )

    refreshed_status = _json(client.get(f"/miniapp-api/watch/sessions/{session_id}/status"))
    refreshed_plan = refreshed_status["sample_plan"]
    refreshed_at = int(refreshed_plan["target_timestamps_ms"][0])
    accepted = client.post(
        f"/miniapp-api/watch/sessions/{session_id}/analysis/samples",
        json={
            "plan_id": refreshed_plan["plan_id"],
            "media_revision": "rev-1",
            "purpose": refreshed_plan["purpose"],
            "timeline_epoch": 1,
            "actual_range_start_ms": refreshed_plan["allowed_start_ms"],
            "actual_range_end_ms": refreshed_plan["allowed_end_ms"],
            "samples": [
                {
                    "at_ms": refreshed_at,
                    "mime_type": "image/png",
                    "image_base64": b64encode(image.getvalue()).decode("ascii"),
                }
            ],
        },
    )
    _assert(accepted.status_code == 202, f"有效本地取材没有入队: {accepted.data!r}")
    with runtime_sqlite.connect() as conn:
        consumed = conn.execute(
            "SELECT status, job_id FROM watch_client_sample_plans WHERE id = ?",
            (refreshed_plan["plan_id"],),
        ).fetchone()
    _assert(
        consumed is not None and consumed["status"] == "consumed" and consumed["job_id"],
        "有效取材计划没有原子标记为 consumed",
    )
    watch_runtime_store.end_session(session_id)


def run() -> None:
    runtime_sqlite._SCHEMA_READY = False
    _test_lease_blocks_all_schedulers_and_restart_recovery()
    _test_schema_restart_does_not_unlock_fear_gate()
    _test_end_races_do_not_call_or_commit_model()
    _test_local_http_contract()


if __name__ == "__main__":
    try:
        run()
        print("watch local lifecycle tests passed")
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
