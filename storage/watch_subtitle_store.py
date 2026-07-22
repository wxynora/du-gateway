from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from config import WATCH_SUBTITLE_JOB_MAX_ATTEMPTS
from services.watch_subtitles import parse_subtitle_cues
from storage import runtime_sqlite, watch_analysis_store, watch_knowledge_store


ASSET_TTL = timedelta(hours=24)
TERMINAL_STATUSES = {
    "found",
    "not_found",
    "not_configured",
    "original_title_unavailable",
    "failed",
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(value: Any, limit: int = 500) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _has_cjk(value: str) -> bool:
    return any("\u3400" <= character <= "\u9fff" for character in value)


def _has_ascii_letters(value: str) -> bool:
    return any(character.isascii() and character.isalpha() for character in value)


def _subtitle_search_identity(session: dict) -> dict:
    card = watch_knowledge_store.get_card_for_session(session)
    canonical = card.get("canonical_identity") if isinstance(card.get("canonical_identity"), dict) else {}
    analysis = session.get("analysis") if isinstance(session.get("analysis"), dict) else {}
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    aliases = canonical.get("aliases") if isinstance(canonical.get("aliases"), list) else []
    configured = media.get("subtitle_titles") if isinstance(media.get("subtitle_titles"), list) else []
    originals = [canonical.get("original_title"), analysis.get("original_title")]
    localized = [canonical.get("title"), analysis.get("canonical_title"), media.get("title")]
    alternatives = [*aliases, *configured]
    titles: list[str] = []
    seen: set[str] = set()

    def append(value: Any) -> None:
        title = _text(value, 300)
        key = title.casefold()
        if title and key not in seen:
            seen.add(key)
            titles.append(title)

    for value in originals:
        append(value)
    for value in [*localized, *alternatives]:
        title = _text(value, 300)
        if _has_cjk(title):
            append(title)
    for value in [*localized, *alternatives]:
        title = _text(value, 300)
        if _has_ascii_letters(title) and not _has_cjk(title):
            append(title)
    for value in [*localized, *alternatives]:
        append(value)

    original_title = next((_text(value, 300) for value in originals if _text(value, 300)), "")
    try:
        year = max(
            0,
            int(
                canonical.get("year")
                or analysis.get("year")
                or analysis.get("identity_year")
                or 0
            ),
        )
    except (TypeError, ValueError):
        year = 0
    work_type = _text(
        canonical.get("work_type")
        or media.get("work_type")
        or media.get("media_type"),
        40,
    ).casefold()
    if work_type in {"movie", "film"}:
        media_type = "movie"
    elif work_type in {"tv", "series", "episode", "show"} or canonical.get("season") or canonical.get("episode"):
        media_type = "tv"
    else:
        media_type = ""
    return {
        "original_title": original_title,
        "year": year,
        "title_candidates": titles,
        "media_type": media_type,
    }


def _identity(session: dict) -> tuple[str, int]:
    identity = _subtitle_search_identity(session)
    return str(identity.get("original_title") or ""), int(identity.get("year") or 0)


def _lookup(session: dict) -> dict:
    preparation = session.get("preparation") if isinstance(session.get("preparation"), dict) else {}
    lookup = preparation.get("subtitle_lookup")
    return lookup if isinstance(lookup, dict) else {}


def _active_job(session_id: str) -> dict:
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT id FROM watch_analysis_jobs
             WHERE session_id = ? AND purpose = 'subtitle_lookup'
               AND status IN ('queued', 'running')
             ORDER BY created_at DESC LIMIT 1
            """,
            (_text(session_id, 160),),
        ).fetchone()
    if row is None:
        return {}
    return watch_analysis_store.get_job(str(row["id"] or ""), public=True) or {}


def ensure_lookup_job(session: dict, *, force: bool = False) -> tuple[dict, bool]:
    session_id = _text(session.get("session_id"), 160)
    if not session_id:
        raise ValueError("session_id 不能为空")
    preparation = session.get("preparation") if isinstance(session.get("preparation"), dict) else {}
    if str(preparation.get("started_at") or "").strip():
        raise ValueError("字幕只能在正式开始前准备")
    card_status = str(preparation.get("knowledge_card_status") or "pending")
    if card_status not in {"ready", "not_required", "failed"}:
        raise ValueError("作品资料尚未准备完成，不能开始查找字幕")
    current = _lookup(session)
    current_status = str(current.get("status") or "pending")
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    if str(media.get("source") or "") == "local_file":
        if current_status in TERMINAL_STATUSES:
            from storage import watch_runtime_store

            watch_runtime_store.update_preparation_state(
                session_id,
                status="ready_to_confirm",
            )
        return {}, False
    if current_status == "searching" and not force:
        existing = _active_job(session_id)
        return existing or {}, False
    if current_status in TERMINAL_STATUSES and not force:
        return {}, False

    search_identity = _subtitle_search_identity(session)
    original_title = str(search_identity.get("original_title") or "")
    title_candidates = search_identity.get("title_candidates") or []
    query_title = original_title or (str(title_candidates[0]) if title_candidates else "")
    year = int(search_identity.get("year") or 0)
    search_strategy = "tmdb_then_subdl" if force else "subdl_titles"
    lookup_id = f"watch_subtitle_lookup_{uuid4().hex}"
    job_id = f"watch_job_{uuid4().hex}"
    retry_suffix = uuid4().hex if force else "initial"
    idempotency_key = (
        f"subtitle:{session_id}:{media.get('id') or ''}:{original_title.casefold()}:{year}:{retry_suffix}"
    )
    now = _now()
    now_iso = _iso(now)
    public_lookup = {
        "lookup_id": lookup_id,
        "status": "searching",
        "provider": "",
        "query_title": query_title,
        "search_strategy": search_strategy,
        "language_codes": [],
        "release_name": "",
        "format": "",
        "cue_count": 0,
        "coverage_start_ms": 0,
        "coverage_end_ms": 0,
        "message": "正在查找字幕",
        "error": "",
        "can_retry": False,
        "_job_id": job_id,
    }
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT status, started_at, media_id, client_lease_expires_at FROM watch_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError("watch_session_not_found")
            if str(row["status"] or "") == "ended" or str(row["started_at"] or ""):
                raise ValueError("字幕只能在正式开始前准备")
            if (
                not str(row["client_lease_expires_at"] or "")
                or str(row["client_lease_expires_at"] or "") <= now_iso
            ):
                raise ValueError("客户端租约已过期，不能新建字幕任务")
            conn.execute(
                """
                INSERT INTO watch_analysis_jobs (
                    id, idempotency_key, session_id, media_id, timeline_epoch,
                    purpose, input_origin, planned_timestamps_json, range_start_ms,
                    range_end_ms, status, priority, attempts, max_attempts,
                    available_at, sample_ids_json, analysis_version,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, 'subtitle_lookup', 'subtitle_provider', '[]',
                          0, 0, 'queued', 24, 0, ?, ?, '[]', 'subtitle-lookup-v1', ?, ?)
                """,
                (
                    job_id,
                    idempotency_key,
                    session_id,
                    _text(row["media_id"], 240),
                    int(WATCH_SUBTITLE_JOB_MAX_ATTEMPTS),
                    now_iso,
                    now_iso,
                    now_iso,
                ),
            )
            conn.execute(
                """
                UPDATE watch_sessions
                   SET preparation_status = 'searching_subtitles',
                       subtitle_lookup_json = ?, subtitle_asset_id = '',
                       subtitle_confirmed_at = '', updated_at = ?, expires_at = ?
                 WHERE id = ?
                """,
                (
                    runtime_sqlite.json_dumps(public_lookup),
                    now_iso,
                    _iso(now + ASSET_TTL),
                    session_id,
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return watch_analysis_store.get_job(job_id, public=True) or {}, True


def commit_lookup_result(job: dict, result: dict) -> dict:
    job_id = _text(job.get("job_id"), 160)
    lease_token = _text(job.get("lease_token"), 200)
    session_id = _text(job.get("session_id"), 160)
    status = _text(result.get("status"), 40)
    if status not in TERMINAL_STATUSES - {"failed"}:
        raise ValueError("字幕准备结果状态无效")
    cues = result.get("cues") if isinstance(result.get("cues"), list) else []
    if status == "found" and not cues:
        raise ValueError("字幕命中结果缺少可用正文")
    now = _now()
    now_iso = _iso(now)
    expires_at = _iso(now + ASSET_TTL)
    asset_id = f"watch_subtitle_asset_{uuid4().hex}" if status == "found" and cues else ""
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            running = conn.execute(
                "SELECT cancel_requested FROM watch_analysis_jobs WHERE id = ? AND status = 'running' AND lease_token = ?",
                (job_id, lease_token),
            ).fetchone()
            row = conn.execute(
                "SELECT * FROM watch_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if running is None:
                conn.execute("ROLLBACK")
                return {"applied": False, "reason": "lease_lost"}
            if bool(running["cancel_requested"]):
                rejection_reason = "cancel_requested"
            elif row is None or str(row["status"] or "") == "ended":
                rejection_reason = "session_ended"
            elif (
                not str(row["client_lease_expires_at"] or "")
                or str(row["client_lease_expires_at"] or "") <= now_iso
            ):
                rejection_reason = "client_lease_expired"
            else:
                rejection_reason = ""
            if rejection_reason:
                conn.execute(
                    "UPDATE watch_analysis_jobs SET status = 'cancelled', cancel_requested = 1, cancel_requested_at = CASE WHEN cancel_requested_at = '' THEN ? ELSE cancel_requested_at END, cancel_reason = ?, error = ?, finished_at = ?, updated_at = ?, lease_token = '', leased_until = '' WHERE id = ?",
                    (now_iso, rejection_reason, rejection_reason, now_iso, now_iso, job_id),
                )
                conn.execute("COMMIT")
                return {"applied": False, "reason": rejection_reason}
            current = runtime_sqlite.json_loads(row["subtitle_lookup_json"], {})
            lookup_id = _text(current.get("lookup_id"), 160)
            if not lookup_id or _text(current.get("_job_id"), 160) != job_id:
                conn.execute("ROLLBACK")
                return {"applied": False, "reason": "lookup_replaced"}
            if asset_id:
                conn.execute(
                    """
                    INSERT INTO watch_subtitle_assets (
                        id, session_id, media_id, provider, query_title, year,
                        language_codes_json, release_name, format, cues_json,
                        cue_count, coverage_start_ms, coverage_end_ms, created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset_id,
                        session_id,
                        _text(row["media_id"], 240),
                        _text(result.get("provider"), 40),
                        _text(result.get("query_title"), 300),
                        max(0, int(result.get("year") or 0)),
                        runtime_sqlite.json_dumps(result.get("language_codes") or []),
                        _text(result.get("release_name"), 500),
                        _text(result.get("format"), 40),
                        runtime_sqlite.json_dumps(cues),
                        len(cues),
                        max(0, int(result.get("coverage_start_ms") or 0)),
                        max(0, int(result.get("coverage_end_ms") or 0)),
                        now_iso,
                        expires_at,
                    ),
                )
            public_lookup = {
                "lookup_id": lookup_id,
                "status": status,
                "provider": _text(result.get("provider"), 40),
                "query_title": _text(result.get("query_title"), 300),
                "search_strategy": _text(current.get("search_strategy"), 40) or "subdl_titles",
                "language_codes": result.get("language_codes") or [],
                "release_name": _text(result.get("release_name"), 500),
                "format": _text(result.get("format"), 40),
                "cue_count": len(cues),
                "coverage_start_ms": max(0, int(result.get("coverage_start_ms") or 0)),
                "coverage_end_ms": max(0, int(result.get("coverage_end_ms") or 0)),
                "message": _text(result.get("message"), 500),
                "error": "",
                "can_retry": status in {"not_found", "original_title_unavailable"},
            }
            card_status = str(row["knowledge_card_status"] or "pending")
            preparation_status = (
                "ready_to_confirm"
                if card_status in {"ready", "not_required", "failed"}
                else str(row["preparation_status"] or "identifying")
            )
            conn.execute(
                """
                UPDATE watch_sessions
                   SET preparation_status = ?, subtitle_lookup_json = ?,
                       subtitle_asset_id = ?, updated_at = ?, expires_at = ?
                 WHERE id = ?
                """,
                (
                    preparation_status,
                    runtime_sqlite.json_dumps(public_lookup),
                    asset_id,
                    now_iso,
                    expires_at,
                    session_id,
                ),
            )
            conn.execute(
                """
                UPDATE watch_analysis_jobs
                   SET status = 'done', leased_until = '', lease_token = '',
                       finished_at = ?, updated_at = ?, error = '', result_json = ?
                 WHERE id = ?
                """,
                (now_iso, now_iso, runtime_sqlite.json_dumps(public_lookup), job_id),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return {"applied": True, "lookup": public_lookup}


def fail_lookup_job(job: dict, error: str, *, retryable: bool) -> str:
    job_id = _text(job.get("job_id"), 160)
    lease_token = _text(job.get("lease_token"), 200)
    session_id = _text(job.get("session_id"), 160)
    now = _now()
    now_iso = _iso(now)
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT attempts, max_attempts, cancel_requested FROM watch_analysis_jobs WHERE id = ? AND status = 'running' AND lease_token = ?",
                (job_id, lease_token),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                return "cancelled"
            session_state = conn.execute(
                "SELECT status, client_lease_expires_at FROM watch_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if bool(row["cancel_requested"]):
                cancellation_reason = "cancel_requested"
            elif session_state is None or str(session_state["status"] or "") == "ended":
                cancellation_reason = "session_ended"
            elif (
                not str(session_state["client_lease_expires_at"] or "")
                or str(session_state["client_lease_expires_at"] or "") <= now_iso
            ):
                cancellation_reason = "client_lease_expired"
            else:
                cancellation_reason = ""
            if cancellation_reason:
                conn.execute(
                    "UPDATE watch_analysis_jobs SET status = 'cancelled', cancel_requested = 1, cancel_requested_at = CASE WHEN cancel_requested_at = '' THEN ? ELSE cancel_requested_at END, cancel_reason = ?, error = ?, finished_at = ?, updated_at = ?, leased_until = '', lease_token = '' WHERE id = ?",
                    (
                        now_iso,
                        cancellation_reason,
                        cancellation_reason,
                        now_iso,
                        now_iso,
                        job_id,
                    ),
                )
                conn.execute("COMMIT")
                return "cancelled"
            should_retry = retryable and int(row["attempts"] or 0) < int(row["max_attempts"] or 1)
            if should_retry:
                conn.execute(
                    "UPDATE watch_analysis_jobs SET status = 'queued', available_at = ?, leased_until = '', lease_token = '', error = ?, updated_at = ? WHERE id = ?",
                    (now_iso, _text(error, 1000), now_iso, job_id),
                )
                conn.execute("COMMIT")
                return "queued"
            session_row = conn.execute(
                "SELECT subtitle_lookup_json, knowledge_card_status, preparation_status FROM watch_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            current = runtime_sqlite.json_loads(session_row["subtitle_lookup_json"], {}) if session_row else {}
            public_lookup = {
                **current,
                "status": "failed",
                "message": "字幕查询失败",
                "error": _text(error, 500),
                "can_retry": True,
            }
            card_status = str(session_row["knowledge_card_status"] or "pending") if session_row else "pending"
            preparation_status = (
                "ready_to_confirm"
                if card_status in {"ready", "not_required", "failed"}
                else str(session_row["preparation_status"] or "knowledge_failed")
            ) if session_row else "knowledge_failed"
            conn.execute(
                "UPDATE watch_analysis_jobs SET status = 'failed', finished_at = ?, updated_at = ?, leased_until = '', lease_token = '', error = ? WHERE id = ?",
                (now_iso, now_iso, _text(error, 1000), job_id),
            )
            if session_row:
                conn.execute(
                    "UPDATE watch_sessions SET preparation_status = ?, subtitle_lookup_json = ?, subtitle_asset_id = '', updated_at = ? WHERE id = ?",
                    (preparation_status, runtime_sqlite.json_dumps(public_lookup), now_iso, session_id),
                )
            conn.execute("COMMIT")
            return "failed"
        except Exception:
            conn.execute("ROLLBACK")
            raise


def reset_lookup(session_id: str) -> dict:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            session_row = conn.execute(
                "SELECT status, started_at, client_lease_expires_at FROM watch_sessions WHERE id = ?",
                (_text(session_id, 160),),
            ).fetchone()
            if session_row is None or str(session_row["status"] or "") == "ended":
                raise ValueError("观看会话已经结束")
            if str(session_row["started_at"] or ""):
                raise ValueError("字幕只能在正式开始前重新查找")
            if (
                not str(session_row["client_lease_expires_at"] or "")
                or str(session_row["client_lease_expires_at"] or "") <= now_iso
            ):
                raise ValueError("客户端租约已过期，不能重建字幕任务")
            conn.execute(
                "UPDATE watch_analysis_jobs SET status = 'cancelled', cancel_requested = 1, cancel_requested_at = CASE WHEN cancel_requested_at = '' THEN ? ELSE cancel_requested_at END, cancel_reason = 'subtitle_lookup_reset', error = 'subtitle_lookup_reset', finished_at = ?, updated_at = ?, leased_until = '', lease_token = '' WHERE session_id = ? AND purpose = 'subtitle_lookup' AND status IN ('queued', 'running')",
                (now_iso, now_iso, now_iso, _text(session_id, 160)),
            )
            conn.execute("DELETE FROM watch_subtitle_assets WHERE session_id = ?", (_text(session_id, 160),))
            conn.execute(
                "UPDATE watch_sessions SET subtitle_lookup_json = '{}', subtitle_asset_id = '', subtitle_confirmed_at = '', updated_at = ? WHERE id = ? AND status != 'ended' AND started_at = ''",
                (now_iso, _text(session_id, 160)),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    from storage import watch_runtime_store

    return watch_runtime_store.get_session(session_id) or {}


def retry_lookup(session: dict) -> tuple[dict, bool]:
    reset = reset_lookup(str(session.get("session_id") or ""))
    return ensure_lookup_job(reset, force=True)


def commit_local_subtitle(
    session: dict,
    *,
    media_revision: str,
    subtitle_text: str,
    subtitle_format: str,
    track_id: str,
) -> dict:
    session_id = _text(session.get("session_id"), 160)
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    local_media = media.get("local_media") if isinstance(media.get("local_media"), dict) else {}
    selected = local_media.get("selected_subtitle") if isinstance(local_media.get("selected_subtitle"), dict) else {}
    if str(media.get("source") or "") != "local_file":
        raise ValueError("本地字幕接口只适用于 local_file 会话")
    if str((session.get("preparation") or {}).get("started_at") or ""):
        raise ValueError("本地字幕只能在正式开始前提交")
    if str(media_revision or "") != str(local_media.get("media_revision") or ""):
        raise ValueError("本地文件版本已经变化，请重新选择文件")
    kind = str(selected.get("kind") or "none")
    if kind not in {"embedded", "external"}:
        raise ValueError("当前会话没有选择需要提交的本地字幕")
    expected_format = str(selected.get("format") or "").lower()
    if str(subtitle_format or "").lower() != expected_format:
        raise ValueError("提交的字幕格式与当前选择不一致")
    expected_track_id = str(selected.get("track_id") or "")
    if expected_track_id and str(track_id or "") != expected_track_id:
        raise ValueError("提交的字幕轨与当前播放器选择不一致")
    cues = parse_subtitle_cues(
        subtitle_text,
        offset_ms=int(selected.get("offset_ms") or 0),
    )
    if not cues:
        raise ValueError("本地字幕没有解析出可用时间轴")
    now = _now()
    now_iso = _iso(now)
    expires_at = _iso(now + ASSET_TTL)
    asset_id = f"watch_subtitle_asset_{uuid4().hex}"
    lookup = _lookup(session)
    lookup_id = _text(lookup.get("lookup_id"), 160) or f"watch_subtitle_lookup_{uuid4().hex}"
    coverage_start_ms = max(0, int(float(cues[0].get("start") or 0) * 1000))
    coverage_end_ms = max(
        coverage_start_ms,
        int(float(cues[-1].get("end") or 0) * 1000),
    )
    public_lookup = {
        "lookup_id": lookup_id,
        "status": "found",
        "provider": f"local_{kind}",
        "query_title": "",
        "language_codes": [selected.get("language")] if selected.get("language") else [],
        "release_name": str(selected.get("label") or ""),
        "format": expected_format,
        "cue_count": len(cues),
        "coverage_start_ms": coverage_start_ms,
        "coverage_end_ms": coverage_end_ms,
        "message": "已载入所选本地字幕",
        "error": "",
        "can_retry": False,
    }
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT status, started_at, media_id, knowledge_card_status FROM watch_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None or str(row["status"] or "") == "ended":
                raise KeyError("watch_session_not_found")
            if str(row["started_at"] or ""):
                raise ValueError("本地字幕只能在正式开始前提交")
            conn.execute("DELETE FROM watch_subtitle_assets WHERE session_id = ?", (session_id,))
            conn.execute(
                """
                INSERT INTO watch_subtitle_assets (
                    id, session_id, media_id, provider, query_title, year,
                    language_codes_json, release_name, format, cues_json,
                    cue_count, coverage_start_ms, coverage_end_ms, created_at, expires_at
                ) VALUES (?, ?, ?, ?, '', 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    session_id,
                    str(row["media_id"] or ""),
                    f"local_{kind}",
                    runtime_sqlite.json_dumps(public_lookup["language_codes"]),
                    public_lookup["release_name"],
                    expected_format,
                    runtime_sqlite.json_dumps(cues),
                    len(cues),
                    coverage_start_ms,
                    coverage_end_ms,
                    now_iso,
                    expires_at,
                ),
            )
            preparation_status = (
                "ready_to_confirm"
                if str(row["knowledge_card_status"] or "") in {"ready", "not_required", "failed"}
                else "searching_subtitles"
            )
            conn.execute(
                """
                UPDATE watch_sessions
                   SET preparation_status = ?, subtitle_lookup_json = ?,
                       subtitle_asset_id = ?, subtitle_confirmed_at = '',
                       updated_at = ?, expires_at = ?
                 WHERE id = ?
                """,
                (
                    preparation_status,
                    runtime_sqlite.json_dumps(public_lookup),
                    asset_id,
                    now_iso,
                    expires_at,
                    session_id,
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return public_lookup


def enrich_samples_with_subtitles(session: dict, job: dict, samples: list[dict]) -> list[dict]:
    asset = get_asset_for_session(session)
    cues = asset.get("cues") if isinstance(asset.get("cues"), list) else []
    if not cues:
        return samples
    timestamps = sorted({int(item.get("at_ms") or 0) for item in samples})
    range_end_ms = int(job.get("range_end_ms") or (timestamps[-1] if timestamps else 0))
    out: list[dict] = []
    for item in samples:
        if str(item.get("subtitle") or "").strip():
            out.append(item)
            continue
        start_ms = int(item.get("at_ms") or 0)
        later = [value for value in timestamps if value > start_ms]
        end_ms = min(later) if later else max(start_ms + 1000, range_end_ms)
        start_seconds = start_ms / 1000.0
        end_seconds = end_ms / 1000.0
        texts = [
            str(cue.get("text") or "").strip()
            for cue in cues
            if float(cue.get("end") or 0) >= start_seconds - 0.2
            and float(cue.get("start") or 0) < end_seconds
        ]
        out.append(
            {
                **item,
                "subtitle": " ".join(dict.fromkeys(text for text in texts if text)),
            }
        )
    return out


def get_asset_for_session(session: dict) -> dict:
    preparation = session.get("preparation") if isinstance(session.get("preparation"), dict) else {}
    lookup = preparation.get("subtitle_lookup") if isinstance(preparation.get("subtitle_lookup"), dict) else {}
    if str(lookup.get("status") or "") != "found":
        return {}
    session_id = _text(session.get("session_id"), 160)
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT a.* FROM watch_subtitle_assets a
            JOIN watch_sessions s ON s.subtitle_asset_id = a.id
            WHERE s.id = ? AND a.expires_at > ?
            """,
            (session_id, _iso(_now())),
        ).fetchone()
    if row is None:
        return {}
    return {
        "asset_id": str(row["id"] or ""),
        "provider": str(row["provider"] or ""),
        "cues": runtime_sqlite.json_loads(row["cues_json"], []),
    }


def identity_for_session(session: dict) -> tuple[str, int]:
    return _identity(session)


def search_identity_for_session(session: dict) -> dict:
    return _subtitle_search_identity(session)


def cleanup_expired_assets() -> int:
    with runtime_sqlite.connect() as conn:
        cursor = conn.execute(
            "DELETE FROM watch_subtitle_assets WHERE expires_at <= ?",
            (_iso(_now()),),
        )
    return max(0, int(cursor.rowcount or 0))
