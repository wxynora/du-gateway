"""SQLite state machine and canonical projection for Together Watch preanalysis."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from config import WATCH_PREANALYSIS_INPUT_TOKENS_PER_MINUTE
from services import watch_preanalysis
from storage import runtime_sqlite


PART_LEASE = timedelta(minutes=10)
PROCESSING_POLL = timedelta(seconds=10)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def _public_cache(conn, row: Any) -> dict:
    parts = conn.execute(
        "SELECT * FROM watch_preanalysis_parts WHERE cache_key = ? ORDER BY part_index",
        (str(row["cache_key"] or ""),),
    ).fetchall()
    part_statuses = {str(part["status"] or "") for part in parts}
    upload_required = str(row["status"] or "") in {"waiting_upload", "uploading"} or (
        str(row["status"] or "") == "failed"
        and not str(row["provider_file_name"] or "")
        and not part_statuses.intersection({"failed", "needs_review"})
    )
    return {
        "cache_key": str(row["cache_key"] or ""),
        "status": str(row["status"] or ""),
        "media_identity": runtime_sqlite.json_loads(row["media_identity_json"], {}),
        "content_start_ms": int(row["content_start_ms"] or -1),
        "content_end_ms": int(row["content_end_ms"] or -1),
        "split_ms": int(row["split_ms"] or -1),
        "analysis_profile": runtime_sqlite.json_loads(row["analysis_profile_json"], {}),
        "analysis_profile_digest": str(row["analysis_profile_digest"] or ""),
        "upload": {
            "mime_type": str(row["upload_mime_type"] or ""),
            "size_bytes": int(row["upload_size_bytes"] or 0),
            "display_name": str(row["upload_display_name"] or ""),
            "provider_file_expires_at": str(row["provider_file_expires_at"] or ""),
            "required": upload_required,
        },
        "parts": [
            {
                "part_index": int(part["part_index"]),
                "clip_input_start_ms": int(part["clip_input_start_ms"]),
                "clip_input_end_ms": int(part["clip_input_end_ms"]),
                "authoritative_start_ms": int(part["authoritative_start_ms"]),
                "authoritative_end_ms": int(part["authoritative_end_ms"]),
                "status": str(part["status"] or ""),
                "available_at": str(part["available_at"] or ""),
                "input_token_count": int(part["input_token_count"] or 0),
                "usage": runtime_sqlite.json_loads(part["usage_json"], {}),
                "error": str(part["error"] or ""),
                "manual_retry_count": int(part["manual_retry_count"] or 0),
                "can_retry": str(part["status"] or "") in {"failed", "needs_review"},
            }
            for part in parts
        ],
        "usage": runtime_sqlite.json_loads(row["usage_json"], {}),
        "generation_count": int(row["generation_count"] or 0),
        "error": str(row["error"] or ""),
        "ready_at": str(row["ready_at"] or ""),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def _upload_session_display_name(cache_key: str, session_id: str) -> str:
    normalized_session = str(session_id or "").strip().lower()
    if len(normalized_session) != 32 or any(
        char not in "0123456789abcdef" for char in normalized_session
    ):
        raise ValueError("upload_session_id 无效")
    return f"watch-{str(cache_key or '').strip()[:12]}-{normalized_session}.mp4"


def _can_request_upload(conn, row: Any) -> bool:
    status = str(row["status"] or "")
    if status in {"waiting_upload", "uploading"}:
        return True
    if status != "failed" or str(row["provider_file_name"] or ""):
        return False
    retryable_part = conn.execute(
        """
        SELECT 1 FROM watch_preanalysis_parts
         WHERE cache_key = ? AND status IN ('failed', 'needs_review')
         LIMIT 1
        """,
        (str(row["cache_key"] or ""),),
    ).fetchone()
    return retryable_part is None


def create_or_get(
    *,
    owner_device_id: str,
    media: dict,
    subtitle_content_digest: str,
    subtitle_kind: str = "none",
    subtitle_format: str = "",
    subtitle_offset_ms: int = 0,
    subtitle_text: str = "",
    selected_audio_digest: str,
) -> dict:
    computed_subtitle_digest, subtitle_cues = watch_preanalysis.build_subtitle_input(
        kind=subtitle_kind,
        subtitle_format=subtitle_format,
        offset_ms=subtitle_offset_ms,
        text=subtitle_text,
    )
    if str(subtitle_content_digest or "").strip() != computed_subtitle_digest:
        raise ValueError("subtitle_content_digest 与字幕正文不一致")
    identity = watch_preanalysis.build_cache_identity(
        media,
        content_start_ms=media.get("content_start_ms"),
        content_end_ms=media.get("content_end_ms"),
        subtitle_content_digest=subtitle_content_digest,
        selected_audio_digest=selected_audio_digest,
    )
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                (identity["cache_key"],),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO watch_preanalysis_caches (
                        cache_key, owner_device_id, media_identity_json,
                        content_start_ms, content_end_ms, split_ms,
                        analysis_profile_json, analysis_profile_digest,
                        subtitle_cues_json, status,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'waiting_upload', ?, ?)
                    """,
                    (
                        identity["cache_key"],
                        str(owner_device_id or "").strip(),
                        runtime_sqlite.json_dumps(identity["media_identity"]),
                        identity["content_start_ms"],
                        identity["content_end_ms"],
                        identity["split_ms"],
                        runtime_sqlite.json_dumps(identity["analysis_profile"]),
                        identity["analysis_profile_digest"],
                        runtime_sqlite.json_dumps(subtitle_cues),
                        now_iso,
                        now_iso,
                    ),
                )
                for part in identity["parts"]:
                    conn.execute(
                        """
                        INSERT INTO watch_preanalysis_parts (
                            id, cache_key, part_index, clip_input_start_ms,
                            clip_input_end_ms, authoritative_start_ms,
                            authoritative_end_ms, status, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'blocked', ?, ?)
                        """,
                        (
                            f"watch_prepart_{uuid4().hex}",
                            identity["cache_key"],
                            part["part_index"],
                            part["clip_input_start_ms"],
                            part["clip_input_end_ms"],
                            part["authoritative_start_ms"],
                            part["authoritative_end_ms"],
                            now_iso,
                            now_iso,
                        ),
                    )
                row = conn.execute(
                    "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                    (identity["cache_key"],),
                ).fetchone()
            elif str(row["owner_device_id"] or "") != str(owner_device_id or "").strip():
                raise PermissionError("不能访问其他设备的整集缓存")
            elif str(row["status"] or "") == "cancelled":
                conn.execute(
                    """
                    UPDATE watch_preanalysis_caches
                       SET status = 'waiting_upload', upload_mime_type = '',
                           upload_size_bytes = 0, upload_display_name = '',
                           provider_file_name = '', provider_file_uri = '',
                           provider_file_expires_at = '', provider_check_after = '',
                           subtitle_cues_json = ?, error = '', updated_at = ?
                     WHERE cache_key = ? AND status = 'cancelled'
                    """,
                    (
                        runtime_sqlite.json_dumps(subtitle_cues),
                        now_iso,
                        identity["cache_key"],
                    ),
                )
                conn.execute(
                    """
                    UPDATE watch_preanalysis_parts
                       SET status = 'blocked', available_at = '', lease_token = '',
                           leased_until = '', provider_request_started_at = '',
                           input_token_count = 0, error = '', updated_at = ?,
                           finished_at = ''
                     WHERE cache_key = ? AND status != 'done'
                    """,
                    (now_iso, identity["cache_key"]),
                )
                row = conn.execute(
                    "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                    (identity["cache_key"],),
                ).fetchone()
            elif str(row["status"] or "") != "ready":
                conn.execute(
                    "UPDATE watch_preanalysis_caches SET subtitle_cues_json = ?, updated_at = ? WHERE cache_key = ?",
                    (runtime_sqlite.json_dumps(subtitle_cues), now_iso, identity["cache_key"]),
                )
                row = conn.execute(
                    "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                    (identity["cache_key"],),
                ).fetchone()
            result = _public_cache(conn, row)
            conn.execute("COMMIT")
            return result
        except Exception:
            conn.execute("ROLLBACK")
            raise


def get_owned(cache_key: str, *, owner_device_id: str) -> dict | None:
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
            (str(cache_key or "").strip(),),
        ).fetchone()
        if row is None:
            return None
        owner = str(row["owner_device_id"] or "")
        if owner and owner_device_id and owner != str(owner_device_id).strip():
            raise PermissionError("不能访问其他设备的整集缓存")
        return _public_cache(conn, row)


def upload_request_data(
    cache_key: str,
    *,
    owner_device_id: str,
    mime_type: str,
    size_bytes: int,
    display_name: str,
) -> dict:
    normalized_mime = str(mime_type or "").strip().lower()
    normalized_size = int(size_bytes or 0)
    if normalized_mime != "video/mp4":
        raise ValueError("整集提前解析上传只接受重封装后的 video/mp4")
    if normalized_size <= 0:
        raise ValueError("upload_size_bytes 必须大于 0")
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
            (str(cache_key or "").strip(),),
        ).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            raise KeyError("watch_preanalysis_not_found")
        if str(row["owner_device_id"] or "") != str(owner_device_id or "").strip():
            conn.execute("ROLLBACK")
            raise PermissionError("不能访问其他设备的整集缓存")
        if not _can_request_upload(conn, row):
            conn.execute("ROLLBACK")
            raise ValueError("当前预解析状态不允许重新上传")
        session_id = uuid4().hex
        resolved_name = _upload_session_display_name(cache_key, session_id)
        conn.execute(
            """
             UPDATE watch_preanalysis_caches
                SET upload_mime_type = ?, upload_size_bytes = ?,
                    upload_display_name = ?, updated_at = ?
              WHERE cache_key = ?
            """,
            (normalized_mime, normalized_size, resolved_name, _iso(_now()), cache_key),
        )
        conn.execute("COMMIT")
        return {
            "display_name": resolved_name,
            "mime_type": normalized_mime,
            "size_bytes": normalized_size,
            "session_id": session_id,
        }


def mark_upload_session_created(cache_key: str, *, upload_session_id: str) -> None:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                (str(cache_key or "").strip(),),
            ).fetchone()
            if row is None:
                raise KeyError("watch_preanalysis_not_found")
            expected_name = _upload_session_display_name(cache_key, upload_session_id)
            if str(row["upload_display_name"] or "") != expected_name:
                raise ValueError("上传会话已经失效")
            if not _can_request_upload(conn, row):
                raise ValueError("当前预解析状态不允许上传")
            conn.execute(
                """
                UPDATE watch_preanalysis_caches
                   SET status = 'uploading', error = '', updated_at = ?
                 WHERE cache_key = ?
                """,
                (now_iso, str(cache_key or "").strip()),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def bind_uploaded_file(
    cache_key: str,
    *,
    owner_device_id: str,
    file_payload: dict,
    upload_session_id: str = "",
) -> dict:
    name = str(file_payload.get("name") or "").strip()
    uri = str(file_payload.get("uri") or "").strip()
    state_value = file_payload.get("state")
    state = (
        str(state_value.get("name") or "").strip().upper()
        if isinstance(state_value, dict)
        else str(state_value or "").strip().upper()
    )
    if not name or not name.startswith("files/") or not uri:
        raise ValueError("AI Studio 文件信息不完整")
    if state not in {"ACTIVE", "PROCESSING", "FAILED"}:
        raise ValueError("AI Studio 文件状态无效")
    now = _now()
    now_iso = _iso(now)
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                (str(cache_key or "").strip(),),
            ).fetchone()
            if row is None:
                raise KeyError("watch_preanalysis_not_found")
            if str(row["owner_device_id"] or "") != str(owner_device_id or "").strip():
                raise PermissionError("不能访问其他设备的整集缓存")
            expected_display_name = str(row["upload_display_name"] or "")
            if upload_session_id and expected_display_name != _upload_session_display_name(
                cache_key,
                upload_session_id,
            ):
                raise ValueError("上传会话与预解析任务不一致")
            if not upload_session_id and not expected_display_name:
                raise ValueError("预解析任务缺少上传会话")
            if str(file_payload.get("displayName") or "").strip() != expected_display_name:
                raise ValueError("AI Studio 文件与本次上传会话不一致")
            if str(file_payload.get("mimeType") or "").strip().lower() != str(row["upload_mime_type"] or "").strip().lower():
                raise ValueError("AI Studio 文件 MIME 与预解析任务不一致")
            if int(file_payload.get("sizeBytes") or 0) != int(row["upload_size_bytes"] or 0):
                raise ValueError("AI Studio 文件大小与预解析任务不一致")
            if str(row["status"] or "") == "cancelled":
                result = _public_cache(conn, row)
                result["provider_state"] = "CANCELLED"
                conn.execute("COMMIT")
                return result
            status = "provider_processing" if state == "PROCESSING" else "failed" if state == "FAILED" else "provider_processing"
            error = "AI Studio 文件处理失败" if state == "FAILED" else ""
            conn.execute(
                """
                UPDATE watch_preanalysis_caches
                   SET provider_file_name = ?, provider_file_uri = ?,
                       provider_file_expires_at = ?, status = ?, error = ?,
                       subtitle_cues_json = CASE WHEN ? = 'failed' THEN '[]' ELSE subtitle_cues_json END,
                       provider_check_after = ?, updated_at = ?
                 WHERE cache_key = ?
                """,
                (
                    name,
                    uri,
                    str(file_payload.get("expirationTime") or "").strip(),
                    status,
                    error,
                    status,
                    now_iso if state == "ACTIVE" else _iso(now + PROCESSING_POLL),
                    now_iso,
                    str(cache_key or "").strip(),
                ),
            )
            updated = conn.execute(
                "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                (str(cache_key or "").strip(),),
            ).fetchone()
            result = _public_cache(conn, updated)
            result["provider_state"] = state
            conn.execute("COMMIT")
            return result
        except Exception:
            conn.execute("ROLLBACK")
            raise


def next_processing_cache() -> dict | None:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM watch_preanalysis_caches
             WHERE status = 'provider_processing' AND provider_check_after <= ?
               AND provider_file_name != ''
             ORDER BY updated_at, cache_key LIMIT 1
            """,
            (now_iso,),
        ).fetchone()
        return dict(row) if row is not None else None


def defer_processing_check(cache_key: str, *, expected_provider_file_name: str) -> None:
    now = _now()
    with runtime_sqlite.connect() as conn:
        conn.execute(
            """
            UPDATE watch_preanalysis_caches
               SET provider_check_after = ?, updated_at = ?
             WHERE cache_key = ? AND provider_file_name = ?
               AND status IN ('provider_processing', 'analyzing')
            """,
            (
                _iso(now + PROCESSING_POLL),
                _iso(now),
                str(cache_key or "").strip(),
                str(expected_provider_file_name or "").strip(),
            ),
        )


def mark_file_failed(
    cache_key: str,
    error: str,
    *,
    expected_provider_file_name: str,
) -> None:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        conn.execute(
            """
            UPDATE watch_preanalysis_caches
               SET status = 'failed', subtitle_cues_json = '[]',
                   error = ?, updated_at = ?
             WHERE cache_key = ? AND provider_file_name = ?
               AND status NOT IN ('cancelled', 'ready')
            """,
            (
                str(error or "").strip(),
                now_iso,
                str(cache_key or "").strip(),
                str(expected_provider_file_name or "").strip(),
            ),
        )


def activate_file(cache_key: str, *, provider: watch_preanalysis.WatchPreanalysisProvider) -> dict:
    with runtime_sqlite.connect() as conn:
        cache = conn.execute(
            "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
            (str(cache_key or "").strip(),),
        ).fetchone()
        if cache is None:
            raise KeyError("watch_preanalysis_not_found")
        parts = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM watch_preanalysis_parts WHERE cache_key = ? ORDER BY part_index",
                (str(cache_key or "").strip(),),
            ).fetchall()
        ]
    counts = [
        provider.count_tokens(
            file_uri=str(cache["provider_file_uri"] or ""),
            mime_type=str(cache["upload_mime_type"] or ""),
            part=part,
            previous_context=None,
            subtitle_cues=runtime_sqlite.json_loads(cache["subtitle_cues_json"], []),
        )
        for part in parts
    ]
    now_iso = _iso(_now())
    quota = int(WATCH_PREANALYSIS_INPUT_TOKENS_PER_MINUTE)
    too_large = any(
        count > quota
        for part, count in zip(parts, counts)
        if str(part.get("status") or "") != "done"
    )
    first_part_done = bool(parts and str(parts[0].get("status") or "") == "done")
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            current_cache = conn.execute(
                "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                (str(cache_key or "").strip(),),
            ).fetchone()
            if current_cache is None:
                raise KeyError("watch_preanalysis_not_found")
            if (
                str(current_cache["status"] or "") != "provider_processing"
                or str(current_cache["provider_file_name"] or "")
                != str(cache["provider_file_name"] or "")
            ):
                result = _public_cache(conn, current_cache)
                conn.execute("COMMIT")
                return result
            for part, count in zip(parts, counts):
                conn.execute(
                    "UPDATE watch_preanalysis_parts SET input_token_count = ?, updated_at = ? WHERE id = ?",
                    (count, now_iso, part["id"]),
                )
            if too_large:
                conn.execute(
                    """
                    UPDATE watch_preanalysis_caches
                       SET status = 'needs_user_action',
                           subtitle_cues_json = '[]',
                           error = '单个半段输入 token 超过当前 AI Studio TPM', updated_at = ?
                     WHERE cache_key = ?
                    """,
                    (now_iso, str(cache_key or "").strip()),
                )
            else:
                if first_part_done:
                    conn.execute(
                        """
                        UPDATE watch_preanalysis_parts
                           SET status = 'queued', available_at = ?, error = '', updated_at = ?
                         WHERE cache_key = ? AND part_index = 2 AND status != 'done'
                        """,
                        (now_iso, now_iso, str(cache_key or "").strip()),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE watch_preanalysis_parts
                           SET status = CASE WHEN part_index = 1 THEN 'queued' ELSE 'blocked' END,
                               available_at = CASE WHEN part_index = 1 THEN ? ELSE '' END,
                               error = '', updated_at = ?
                         WHERE cache_key = ? AND status != 'done'
                        """,
                        (now_iso, now_iso, str(cache_key or "").strip()),
                    )
                conn.execute(
                    "UPDATE watch_preanalysis_caches SET status = 'analyzing', error = '', updated_at = ? WHERE cache_key = ?",
                    (now_iso, str(cache_key or "").strip()),
                )
            row = conn.execute(
                "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                (str(cache_key or "").strip(),),
            ).fetchone()
            result = _public_cache(conn, row)
            conn.execute("COMMIT")
            return result
        except Exception:
            conn.execute("ROLLBACK")
            raise


def next_second_part_token_check() -> dict | None:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT p.*, c.provider_file_uri, c.provider_file_name, c.upload_mime_type,
                   c.subtitle_cues_json
              FROM watch_preanalysis_parts p
              JOIN watch_preanalysis_caches c ON c.cache_key = p.cache_key
             WHERE p.part_index = 2 AND p.status = 'blocked'
               AND c.status = 'analyzing'
               AND (c.provider_check_after = '' OR c.provider_check_after <= ?)
               AND EXISTS (
                    SELECT 1 FROM watch_preanalysis_parts first
                     WHERE first.cache_key = p.cache_key
                       AND first.part_index = 1 AND first.status = 'done'
               )
             ORDER BY p.updated_at, p.created_at LIMIT 1
            """,
            (now_iso,),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        first = conn.execute(
            "SELECT result_json FROM watch_preanalysis_parts WHERE cache_key = ? AND part_index = 1 AND status = 'done'",
            (result["cache_key"],),
        ).fetchone()
        if first is None:
            return None
        result["previous_context"] = watch_preanalysis.previous_part_context(
            runtime_sqlite.json_loads(first["result_json"], {})
        )
        result["subtitle_cues"] = runtime_sqlite.json_loads(result["subtitle_cues_json"], [])
        return result


def finish_second_part_token_check(cache_key: str, *, input_token_count: int) -> dict:
    count = int(input_token_count)
    if count < 0:
        raise ValueError("input_token_count 不能为负数")
    now = _now()
    now_iso = _iso(now)
    quota = int(WATCH_PREANALYSIS_INPUT_TOKENS_PER_MINUTE)
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            part = conn.execute(
                "SELECT * FROM watch_preanalysis_parts WHERE cache_key = ? AND part_index = 2",
                (str(cache_key or "").strip(),),
            ).fetchone()
            cache = conn.execute(
                "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                (str(cache_key or "").strip(),),
            ).fetchone()
            if part is None or cache is None:
                raise KeyError("watch_preanalysis_not_found")
            if str(cache["status"] or "") != "analyzing" or str(part["status"] or "") != "blocked":
                result = _public_cache(conn, cache)
                conn.execute("COMMIT")
                return result
            if count > quota:
                conn.execute(
                    """
                    UPDATE watch_preanalysis_parts
                       SET input_token_count = ?, error = ?, updated_at = ?
                     WHERE id = ? AND status = 'blocked'
                    """,
                    (count, "单个半段输入 token 超过当前 AI Studio TPM", now_iso, part["id"]),
                )
                conn.execute(
                    """
                    UPDATE watch_preanalysis_caches
                       SET status = 'needs_user_action', subtitle_cues_json = '[]',
                           error = ?, updated_at = ?
                     WHERE cache_key = ? AND status = 'analyzing'
                    """,
                    (
                        "part 2 加入前序状态后的输入 token 超过当前 AI Studio TPM",
                        now_iso,
                        str(cache_key or "").strip(),
                    ),
                )
            else:
                first = conn.execute(
                    "SELECT input_token_count FROM watch_preanalysis_parts WHERE cache_key = ? AND part_index = 1",
                    (str(cache_key or "").strip(),),
                ).fetchone()
                total_tokens = int((first or {})["input_token_count"] or 0) + count
                available_at = now_iso
                if total_tokens > quota:
                    available_at = _iso(now.replace(second=0) + timedelta(minutes=1))
                conn.execute(
                    """
                    UPDATE watch_preanalysis_parts
                       SET status = 'queued', input_token_count = ?, available_at = ?,
                           error = '', updated_at = ?
                     WHERE id = ? AND status = 'blocked'
                    """,
                    (count, available_at, now_iso, part["id"]),
                )
            updated = conn.execute(
                "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                (str(cache_key or "").strip(),),
            ).fetchone()
            result = _public_cache(conn, updated)
            conn.execute("COMMIT")
            return result
        except Exception:
            conn.execute("ROLLBACK")
            raise


def claim_next_part() -> dict | None:
    now = _now()
    now_iso = _iso(now)
    lease_token = uuid4().hex
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """
                UPDATE watch_preanalysis_parts
                   SET status = 'needs_review', error = 'worker_lease_expired',
                       leased_until = '', lease_token = '', updated_at = ?
                 WHERE status = 'running' AND leased_until != '' AND leased_until <= ?
                """,
                (now_iso, now_iso),
            )
            conn.execute(
                """
                UPDATE watch_preanalysis_caches
                   SET status = 'failed', subtitle_cues_json = '[]',
                       error = 'worker_lease_expired', updated_at = ?
                 WHERE status = 'analyzing' AND EXISTS (
                    SELECT 1 FROM watch_preanalysis_parts p
                     WHERE p.cache_key = watch_preanalysis_caches.cache_key
                       AND p.status = 'needs_review'
                 )
                """,
                (now_iso,),
            )
            row = conn.execute(
                """
                SELECT p.* FROM watch_preanalysis_parts p
                JOIN watch_preanalysis_caches c ON c.cache_key = p.cache_key
                 WHERE p.status = 'queued' AND p.available_at <= ?
                   AND c.status = 'analyzing'
                 ORDER BY p.available_at, p.part_index, p.created_at
                 LIMIT 1
                """,
                (now_iso,),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            result = conn.execute(
                """
                UPDATE watch_preanalysis_parts
                   SET status = 'running', lease_token = ?, leased_until = ?,
                       provider_request_started_at = ?, updated_at = ?
                 WHERE id = ? AND status = 'queued'
                """,
                (lease_token, _iso(now + PART_LEASE), now_iso, now_iso, row["id"]),
            )
            if not result.rowcount:
                conn.execute("COMMIT")
                return None
            conn.execute(
                "UPDATE watch_preanalysis_caches SET generation_count = generation_count + 1, updated_at = ? WHERE cache_key = ?",
                (now_iso, row["cache_key"]),
            )
            claimed = dict(row)
            claimed["lease_token"] = lease_token
            cache = conn.execute(
                "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                (row["cache_key"],),
            ).fetchone()
            claimed["provider_file_uri"] = str(cache["provider_file_uri"] or "")
            claimed["provider_file_name"] = str(cache["provider_file_name"] or "")
            claimed["upload_mime_type"] = str(cache["upload_mime_type"] or "")
            claimed["subtitle_cues"] = runtime_sqlite.json_loads(cache["subtitle_cues_json"], [])
            if int(row["part_index"]) == 2:
                first = conn.execute(
                    "SELECT result_json FROM watch_preanalysis_parts WHERE cache_key = ? AND part_index = 1 AND status = 'done'",
                    (row["cache_key"],),
                ).fetchone()
                if first is None:
                    raise RuntimeError("part 2 缺少已完成的 part 1")
                claimed["previous_context"] = watch_preanalysis.previous_part_context(
                    runtime_sqlite.json_loads(first["result_json"], {})
                )
            conn.execute("COMMIT")
            return claimed
        except Exception:
            conn.execute("ROLLBACK")
            raise


def commit_part(job: dict, *, result: dict, usage: dict) -> dict:
    now = _now()
    now_iso = _iso(now)
    cache_key = str(job.get("cache_key") or "")
    part_index = int(job.get("part_index") or 0)
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            changed = conn.execute(
                """
                UPDATE watch_preanalysis_parts
                   SET status = 'done', result_json = ?, usage_json = ?, error = '',
                       finished_at = ?, updated_at = ?, leased_until = '', lease_token = ''
                 WHERE id = ? AND status = 'running' AND lease_token = ?
                """,
                (
                    runtime_sqlite.json_dumps(result),
                    runtime_sqlite.json_dumps(usage),
                    now_iso,
                    now_iso,
                    job["id"],
                    job["lease_token"],
                ),
            )
            if not changed.rowcount:
                conn.execute("ROLLBACK")
                return {"applied": False, "reason": "lease_lost"}
            usage_rows = conn.execute(
                "SELECT usage_json FROM watch_preanalysis_parts WHERE cache_key = ? AND status = 'done' ORDER BY part_index",
                (cache_key,),
            ).fetchall()
            aggregate_usage = [runtime_sqlite.json_loads(row["usage_json"], {}) for row in usage_rows]
            if part_index == 1:
                conn.execute(
                    "UPDATE watch_preanalysis_caches SET usage_json = ?, updated_at = ? WHERE cache_key = ?",
                    (runtime_sqlite.json_dumps(aggregate_usage), now_iso, cache_key),
                )
                conn.execute("COMMIT")
                return {"applied": True, "ready": False, "part_two_token_check": True}

            rows = conn.execute(
                "SELECT part_index, result_json FROM watch_preanalysis_parts WHERE cache_key = ? AND status = 'done' ORDER BY part_index",
                (cache_key,),
            ).fetchall()
            if len(rows) != 2:
                raise RuntimeError("两段尚未全部完成，不能生成 canonical cache")
            canonical = watch_preanalysis.merge_canonical_results(
                runtime_sqlite.json_loads(rows[0]["result_json"], {}),
                runtime_sqlite.json_loads(rows[1]["result_json"], {}),
                cache_key=cache_key,
            )
            conn.execute(
                """
                UPDATE watch_preanalysis_caches
                   SET status = 'ready', canonical_result_json = ?, usage_json = ?,
                       subtitle_cues_json = '[]', error = '', ready_at = ?, updated_at = ?
                 WHERE cache_key = ?
                """,
                (
                    runtime_sqlite.json_dumps(canonical),
                    runtime_sqlite.json_dumps(aggregate_usage),
                    now_iso,
                    now_iso,
                    cache_key,
                ),
            )
            conn.execute("COMMIT")
            return {"applied": True, "ready": True, "canonical": canonical}
        except Exception:
            conn.execute("ROLLBACK")
            raise


def fail_part(job: dict, *, error: str, uncertain: bool) -> str:
    status = "needs_review" if uncertain else "failed"
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            changed = conn.execute(
                """
                UPDATE watch_preanalysis_parts
                   SET status = ?, error = ?, finished_at = ?, updated_at = ?,
                       leased_until = '', lease_token = ''
                 WHERE id = ? AND status = 'running' AND lease_token = ?
                """,
                (status, str(error or "").strip(), now_iso, now_iso, job["id"], job["lease_token"]),
            )
            if changed.rowcount:
                conn.execute(
                    "UPDATE watch_preanalysis_caches SET status = 'failed', subtitle_cues_json = '[]', error = ?, updated_at = ? WHERE cache_key = ? AND status = 'analyzing'",
                    (str(error or "").strip(), now_iso, job["cache_key"]),
                )
            conn.execute("COMMIT")
            return status if changed.rowcount else "ignored"
        except Exception:
            conn.execute("ROLLBACK")
            raise


def retry_part(
    cache_key: str,
    *,
    owner_device_id: str,
    part_index: int,
    subtitle_content_digest: str,
    subtitle_kind: str,
    subtitle_format: str,
    subtitle_offset_ms: int,
    subtitle_text: str,
) -> dict:
    if part_index not in {1, 2}:
        raise ValueError("part_index 必须是 1 或 2")
    computed_subtitle_digest, subtitle_cues = watch_preanalysis.build_subtitle_input(
        kind=subtitle_kind,
        subtitle_format=subtitle_format,
        offset_ms=subtitle_offset_ms,
        text=subtitle_text,
    )
    if str(subtitle_content_digest or "").strip() != computed_subtitle_digest:
        raise ValueError("subtitle_content_digest 与字幕正文不一致")
    now = _now()
    now_iso = _iso(now)
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            cache = conn.execute(
                "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                (str(cache_key or "").strip(),),
            ).fetchone()
            if cache is None:
                raise KeyError("watch_preanalysis_not_found")
            if str(cache["owner_device_id"] or "") != str(owner_device_id or "").strip():
                raise PermissionError("不能访问其他设备的整集缓存")
            media_identity = runtime_sqlite.json_loads(cache["media_identity_json"], {})
            if str(media_identity.get("subtitle_content_digest") or "") != computed_subtitle_digest:
                raise ValueError("字幕正文与原预解析缓存身份不一致")
            part = conn.execute(
                "SELECT * FROM watch_preanalysis_parts WHERE cache_key = ? AND part_index = ?",
                (str(cache_key or "").strip(), part_index),
            ).fetchone()
            if part is None or str(part["status"] or "") not in {"failed", "needs_review"}:
                raise ValueError("只能人工重试 failed 或 needs_review 的 part")
            if part_index == 2:
                first = conn.execute(
                    "SELECT status FROM watch_preanalysis_parts WHERE cache_key = ? AND part_index = 1",
                    (str(cache_key or "").strip(),),
                ).fetchone()
                if first is None or str(first["status"] or "") != "done":
                    raise ValueError("part 1 未完成，不能重试 part 2")
            expires_at = _parse_iso(cache["provider_file_expires_at"])
            upload_required = not str(cache["provider_file_name"] or "") or (
                expires_at is not None and expires_at <= now
            )
            conn.execute(
                "UPDATE watch_preanalysis_caches SET subtitle_cues_json = ?, updated_at = ? WHERE cache_key = ?",
                (
                    runtime_sqlite.json_dumps(subtitle_cues),
                    now_iso,
                    str(cache_key or "").strip(),
                ),
            )
            if upload_required:
                conn.execute(
                    """
                    UPDATE watch_preanalysis_caches
                       SET status = 'waiting_upload', provider_file_name = '',
                           provider_file_uri = '', provider_file_expires_at = '',
                           error = '', updated_at = ? WHERE cache_key = ?
                    """,
                    (now_iso, str(cache_key or "").strip()),
                )
                conn.execute(
                    "UPDATE watch_preanalysis_parts SET status = 'blocked', error = '', manual_retry_count = manual_retry_count + 1, updated_at = ? WHERE id = ?",
                    (now_iso, part["id"]),
                )
            else:
                if part_index == 1:
                    conn.execute(
                        "UPDATE watch_preanalysis_parts SET status = 'blocked', available_at = '', error = '', updated_at = ? WHERE cache_key = ? AND part_index = 2 AND status != 'done'",
                        (now_iso, str(cache_key or "").strip()),
                    )
                conn.execute(
                    """
                    UPDATE watch_preanalysis_parts
                       SET status = 'queued', available_at = ?, error = '', finished_at = '',
                           manual_retry_count = manual_retry_count + 1, updated_at = ?
                     WHERE id = ?
                    """,
                    (now_iso, now_iso, part["id"]),
                )
                conn.execute(
                    "UPDATE watch_preanalysis_caches SET status = 'analyzing', error = '', updated_at = ? WHERE cache_key = ?",
                    (now_iso, str(cache_key or "").strip()),
                )
            updated = conn.execute(
                "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                (str(cache_key or "").strip(),),
            ).fetchone()
            result = _public_cache(conn, updated)
            conn.execute("COMMIT")
            return result
        except Exception:
            conn.execute("ROLLBACK")
            raise


def cancel(cache_key: str, *, owner_device_id: str) -> str:
    now_iso = _iso(_now())
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ?",
                (str(cache_key or "").strip(),),
            ).fetchone()
            if row is None:
                raise KeyError("watch_preanalysis_not_found")
            if str(row["owner_device_id"] or "") != str(owner_device_id or "").strip():
                raise PermissionError("不能访问其他设备的整集缓存")
            conn.execute(
                "UPDATE watch_preanalysis_parts SET status = 'cancelled', updated_at = ?, leased_until = '', lease_token = '' WHERE cache_key = ? AND status NOT IN ('done', 'cancelled')",
                (now_iso, str(cache_key or "").strip()),
            )
            conn.execute(
                "UPDATE watch_preanalysis_caches SET status = 'cancelled', subtitle_cues_json = '[]', error = '', updated_at = ? WHERE cache_key = ?",
                (now_iso, str(cache_key or "").strip()),
            )
            conn.execute("COMMIT")
            return str(row["provider_file_name"] or "")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def provider_file_name(cache_key: str) -> str:
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT provider_file_name FROM watch_preanalysis_caches WHERE cache_key = ?",
            (str(cache_key or "").strip(),),
        ).fetchone()
        return str(row["provider_file_name"] or "") if row is not None else ""


def clear_provider_file(cache_key: str, *, expected_provider_file_name: str = "") -> None:
    with runtime_sqlite.connect() as conn:
        expected = str(expected_provider_file_name or "").strip()
        if expected:
            conn.execute(
                """
                UPDATE watch_preanalysis_caches
                   SET provider_file_name = '', provider_file_uri = '',
                       provider_file_expires_at = '', provider_check_after = '', updated_at = ?
                 WHERE cache_key = ? AND provider_file_name = ?
                """,
                (_iso(_now()), str(cache_key or "").strip(), expected),
            )
        else:
            conn.execute(
                """
                UPDATE watch_preanalysis_caches
                   SET provider_file_name = '', provider_file_uri = '',
                       provider_file_expires_at = '', provider_check_after = '', updated_at = ?
                 WHERE cache_key = ?
                """,
                (_iso(_now()), str(cache_key or "").strip()),
            )


def clear_hydrated_cache(
    conn,
    *,
    cache_key: str,
    session_id: str,
    timeline_epoch: int,
    now_iso: str,
) -> None:
    row = conn.execute(
        "SELECT canonical_result_json FROM watch_preanalysis_caches WHERE cache_key = ?",
        (str(cache_key or "").strip(),),
    ).fetchone()
    canonical = runtime_sqlite.json_loads(row["canonical_result_json"], {}) if row is not None else {}
    analysis_version = str((canonical or {}).get("analysis_version") or "")
    conn.execute(
        "DELETE FROM watch_timeline_sections WHERE session_id = ? AND timeline_epoch = ? AND source = 'preanalysis'",
        (session_id, int(timeline_epoch)),
    )
    if analysis_version:
        for table in ("watch_plot_chunks", "watch_risk_events", "watch_story_checkpoints"):
            conn.execute(
                f"DELETE FROM {table} WHERE session_id = ? AND timeline_epoch = ? AND analysis_version = ?",
                (session_id, int(timeline_epoch), analysis_version),
            )
    conn.execute(
        """
        UPDATE watch_sessions
           SET preanalysis_cache_key = '', preanalysis_subtitle_digest = '',
               preanalysis_audio_digest = '', preanalysis_profile_digest = '',
               analysis_status = 'pending', analysis_covered_from_ms = 0,
               analysis_covered_until_ms = 0, analysis_error = '',
               story_so_far_json = '{}', analysis_story_state_json = '{}',
               updated_at = ?
         WHERE id = ? AND timeline_epoch = ? AND status != 'ended'
        """,
        (now_iso, session_id, int(timeline_epoch)),
    )


def _expected_identity_from_session_media(media: dict) -> tuple[str, str, str]:
    return (
        str(media.get("preanalysis_cache_key") or "").strip(),
        str(media.get("subtitle_content_digest") or "").strip(),
        str(media.get("selected_audio_digest") or "").strip(),
    )


def validate_ready_binding(
    conn,
    *,
    cache_key: str,
    owner_device_id: str,
    media: dict,
) -> Any:
    row = conn.execute(
        "SELECT * FROM watch_preanalysis_caches WHERE cache_key = ? AND status = 'ready'",
        (str(cache_key or "").strip(),),
    ).fetchone()
    if row is None:
        raise ValueError("preanalysis_cache_key 不是 ready cache")
    if str(row["owner_device_id"] or "") != str(owner_device_id or "").strip():
        raise PermissionError("不能绑定其他设备的整集缓存")
    _provided_key, subtitle_digest, audio_digest = _expected_identity_from_session_media(media)
    provided_profile_digest = str(media.get("analysis_profile_digest") or "").strip()
    if provided_profile_digest != str(row["analysis_profile_digest"] or ""):
        raise ValueError("preanalysis analysis_profile_digest 与 ready cache 不一致")
    expected = watch_preanalysis.build_cache_identity(
        media,
        content_start_ms=media.get("content_start_ms"),
        content_end_ms=media.get("content_end_ms"),
        subtitle_content_digest=subtitle_digest,
        selected_audio_digest=audio_digest,
    )
    if expected["cache_key"] != str(row["cache_key"] or ""):
        raise ValueError("preanalysis cache 与当前媒体、边界、字幕或分析 profile 不一致")
    return row


def hydrate_ready_cache(
    conn,
    *,
    cache_key: str,
    owner_device_id: str,
    media: dict,
    session_id: str,
    media_id: str,
    timeline_epoch: int,
    now_iso: str,
) -> bool:
    if not cache_key:
        return False
    row = validate_ready_binding(
        conn,
        cache_key=cache_key,
        owner_device_id=owner_device_id,
        media=media,
    )
    canonical = runtime_sqlite.json_loads(row["canonical_result_json"], {})
    if not isinstance(canonical, dict) or not canonical:
        raise ValueError("ready cache 缺少 canonical_result_json")
    analysis_version = str(canonical.get("analysis_version") or "")
    if not analysis_version:
        raise ValueError("ready cache 缺少 analysis_version")

    conn.execute(
        "DELETE FROM watch_timeline_sections WHERE session_id = ? AND timeline_epoch = ? AND source != 'manual'",
        (session_id, int(timeline_epoch)),
    )
    conn.execute(
        "DELETE FROM watch_plot_chunks WHERE session_id = ? AND timeline_epoch = ?",
        (session_id, int(timeline_epoch)),
    )
    conn.execute(
        "DELETE FROM watch_risk_events WHERE session_id = ? AND timeline_epoch = ?",
        (session_id, int(timeline_epoch)),
    )
    conn.execute(
        "DELETE FROM watch_story_checkpoints WHERE session_id = ? AND timeline_epoch = ?",
        (session_id, int(timeline_epoch)),
    )
    for section in canonical.get("timeline_sections") or []:
        digest = hashlib.sha256(
            f"{session_id}:{timeline_epoch}:section:{section.get('kind')}:{section.get('start_ms')}:{section.get('end_ms')}:{analysis_version}".encode()
        ).hexdigest()[:20]
        conn.execute(
            """
            INSERT OR REPLACE INTO watch_timeline_sections (
                id, session_id, timeline_epoch, kind, start_ms, end_ms,
                source, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'preanalysis', ?, ?, ?)
            """,
            (
                f"watch_section_{digest}", session_id, int(timeline_epoch),
                section.get("kind") or "unknown", int(section.get("start_ms") or 0),
                int(section.get("end_ms") or 0), float(section.get("confidence") or 0),
                now_iso, now_iso,
            ),
        )

    for chunk in canonical.get("plot_chunks") or []:
        digest = hashlib.sha256(
            f"{session_id}:{timeline_epoch}:plot:{chunk.get('start_ms')}:{chunk.get('end_ms')}:{analysis_version}".encode()
        ).hexdigest()[:20]
        conn.execute(
            """
            INSERT OR REPLACE INTO watch_plot_chunks (
                id, session_id, media_id, timeline_epoch, start_ms, end_ms,
                summary, visual_description, dialogue_summary, characters_json,
                tags_json, confidence, analysis_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"watch_plot_{digest}", session_id, media_id, int(timeline_epoch),
                int(chunk.get("start_ms") or 0), int(chunk.get("end_ms") or 0),
                str(chunk.get("summary") or ""), str(chunk.get("visual_description") or ""),
                str(chunk.get("dialogue_summary") or ""),
                runtime_sqlite.json_dumps(chunk.get("characters") or []),
                runtime_sqlite.json_dumps(chunk.get("tags") or []),
                float(chunk.get("confidence") or 0), analysis_version, now_iso, now_iso,
            ),
        )

    for event in canonical.get("risk_events") or []:
        digest = hashlib.sha256(
            f"{session_id}:{timeline_epoch}:risk:{event.get('risk_type')}:{event.get('start_ms')}:{event.get('end_ms')}:{analysis_version}".encode()
        ).hexdigest()[:20]
        conn.execute(
            """
            INSERT OR REPLACE INTO watch_risk_events (
                id, session_id, media_id, timeline_epoch, risk_type, severity,
                start_ms, end_ms, warn_at_ms, label, companion_hint, confidence,
                status, analysis_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', ?, ?, ?)
            """,
            (
                f"watch_risk_{digest}", session_id, media_id, int(timeline_epoch),
                event.get("risk_type") or "other", str(event.get("severity") or "1"),
                int(event.get("start_ms") or 0), int(event.get("end_ms") or 0),
                int(event.get("warn_at_ms") or event.get("start_ms") or 0),
                str(event.get("label") or ""), str(event.get("companion_hint") or ""),
                float(event.get("confidence") or 0), analysis_version, now_iso, now_iso,
            ),
        )

    for checkpoint in canonical.get("story_checkpoints") or []:
        through_ms = int(checkpoint.get("through_ms") or 0)
        digest = hashlib.sha256(
            f"{session_id}:{timeline_epoch}:story:{through_ms}:{analysis_version}".encode()
        ).hexdigest()[:20]
        conn.execute(
            """
            INSERT OR REPLACE INTO watch_story_checkpoints (
                id, session_id, media_id, timeline_epoch, through_ms,
                summary_json, story_state_json, analysis_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"watch_story_{digest}", session_id, media_id, int(timeline_epoch), through_ms,
                runtime_sqlite.json_dumps(
                    {
                        "through_ms": through_ms,
                        "background": str(checkpoint.get("background") or ""),
                        "characters": checkpoint.get("characters") or [],
                    }
                ),
                runtime_sqlite.json_dumps(checkpoint.get("story_state") or {}),
                analysis_version,
                now_iso,
            ),
        )

    familiarity = canonical.get("familiarity") if isinstance(canonical.get("familiarity"), dict) else {}
    identity = canonical.get("canonical_identity") if isinstance(canonical.get("canonical_identity"), dict) else {}
    conn.execute(
        """
        UPDATE watch_sessions
           SET preanalysis_cache_key = ?, analysis_status = 'ready',
               analysis_covered_from_ms = ?, analysis_covered_until_ms = ?,
               analysis_error = '', analysis_familiarity = ?, analysis_identity = ?,
               analysis_original_title = ?, analysis_year = ?,
               story_so_far_json = ?, analysis_story_state_json = ?, updated_at = ?
         WHERE id = ? AND timeline_epoch = ? AND status != 'ended'
        """,
        (
            cache_key,
            int(row["content_start_ms"]),
            int(row["content_end_ms"]),
            str(familiarity.get("status") or "unknown"),
            str(familiarity.get("identity") or identity.get("title") or ""),
            str(identity.get("original_title") or ""),
            int(identity.get("year") or 0),
            "{}",
            "{}",
            now_iso,
            session_id,
            int(timeline_epoch),
        ),
    )
    return True
