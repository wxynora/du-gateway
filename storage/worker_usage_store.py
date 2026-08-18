"""Persistent accounting for background model calls used by the App dashboard."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from storage.runtime_sqlite import connect


_UTC = timezone.utc
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_PACIFIC = ZoneInfo("America/Los_Angeles")

_BUCKETS = (
    ("deepseek_v4_flash", "DeepSeek V4 Flash", "siliconflow", "CNY"),
    ("gemini_3_7_flash", "Gemini 3.7 Flash", "openrouter", "USD"),
    ("qwen3_reranker_8b", "Qwen3-Reranker-8B", "siliconflow", "CNY"),
    ("google_ai_studio", "Google AI Studio", "google_ai_studio", ""),
    ("gemini_3_5_flash_lite", "Gemini 3.5 Flash Lite", "google_ai_studio", ""),
)

_AI_STUDIO_BUCKET = "google_ai_studio"
_OCR_BUCKET = "gemini_3_5_flash_lite"
_OCR_MODEL_FRAGMENT = "gemini-3.5-flash-lite"


def _quota(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _as_utc(value: datetime | None) -> datetime:
    current = value or datetime.now(_UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=_UTC)
    return current.astimezone(_UTC)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="milliseconds")


def record_usage(
    *,
    bucket_key: str,
    role: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int,
    cost_value: float,
    currency: str,
    success: bool = True,
    occurred_at: datetime | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO worker_model_usage (
                occurred_at, bucket_key, role, provider, model, request_count,
                input_tokens, output_tokens, cached_input_tokens,
                cost_value, currency, success
            ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
            """,
            (
                _iso(_as_utc(occurred_at)),
                str(bucket_key or "").strip(),
                str(role or "").strip(),
                str(provider or "").strip(),
                str(model or "").strip(),
                max(0, int(input_tokens or 0)),
                max(0, int(output_tokens or 0)),
                max(0, int(cached_input_tokens or 0)),
                max(0.0, float(cost_value or 0.0)),
                str(currency or "").strip().upper(),
                1 if success else 0,
            ),
        )


def _aggregate(bucket_key: str, since: datetime) -> dict[str, Any]:
    with connect() as conn:
        select_sql = """
        SELECT
            COALESCE(SUM(request_count), 0) AS request_count,
            COALESCE(SUM(input_tokens), 0) AS input_tokens,
            COALESCE(SUM(output_tokens), 0) AS output_tokens,
            COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens,
            COALESCE(SUM(cost_value), 0) AS cost_value,
            COALESCE(MAX(currency), '') AS currency
        FROM worker_model_usage
        """
        if bucket_key == _OCR_BUCKET:
            row = conn.execute(
                select_sql
                + """
                WHERE occurred_at >= ?
                  AND (
                      bucket_key = ?
                      OR (bucket_key = ? AND LOWER(model) LIKE ?)
                  )
                """,
                (
                    _iso(since),
                    _OCR_BUCKET,
                    _AI_STUDIO_BUCKET,
                    f"%{_OCR_MODEL_FRAGMENT}%",
                ),
            ).fetchone()
        elif bucket_key == _AI_STUDIO_BUCKET:
            row = conn.execute(
                select_sql
                + """
                WHERE occurred_at >= ?
                  AND bucket_key = ?
                  AND LOWER(model) NOT LIKE ?
                """,
                (_iso(since), _AI_STUDIO_BUCKET, f"%{_OCR_MODEL_FRAGMENT}%"),
            ).fetchone()
        else:
            row = conn.execute(
                select_sql + "WHERE bucket_key = ? AND occurred_at >= ?",
                (bucket_key, _iso(since)),
            ).fetchone()
    return dict(row or {})


def dashboard_snapshot(*, now: datetime | None = None) -> dict[str, Any]:
    now_utc = _as_utc(now)
    shanghai_now = now_utc.astimezone(_SHANGHAI)
    paid_day_start = shanghai_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(_UTC)

    pacific_now = now_utc.astimezone(_PACIFIC)
    quota_day_start = pacific_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(_UTC)
    minute_start = now_utc - timedelta(seconds=60)

    models: list[dict[str, Any]] = []
    for bucket_key, name, default_provider, default_currency in _BUCKETS:
        since = quota_day_start if bucket_key in {_AI_STUDIO_BUCKET, _OCR_BUCKET} else paid_day_start
        usage = _aggregate(bucket_key, since)
        currency = str(usage.get("currency") or default_currency)
        item = {
            "key": bucket_key,
            "name": name,
            "provider": default_provider,
            "request_count": int(usage.get("request_count") or 0),
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "cached_input_tokens": int(usage.get("cached_input_tokens") or 0),
            "cost": {
                "value": round(float(usage.get("cost_value") or 0.0), 8),
                "currency": currency,
            },
        }
        if bucket_key == _AI_STUDIO_BUCKET:
            minute_usage = _aggregate(bucket_key, minute_start)
            rpm_limit = _quota("WORKER_USAGE_AI_STUDIO_RPM", 5)
            tpm_limit = _quota("WORKER_USAGE_AI_STUDIO_TPM", 250_000)
            rpd_limit = _quota("WORKER_USAGE_AI_STUDIO_RPD", 20)
            rpm_used = int(minute_usage.get("request_count") or 0)
            tpm_used = int(minute_usage.get("input_tokens") or 0)
            rpd_used = int(usage.get("request_count") or 0)
            item["quota"] = {
                "rpm": {"limit": rpm_limit, "used": rpm_used, "remaining": max(0, rpm_limit - rpm_used)},
                "tpm": {"limit": tpm_limit, "used": tpm_used, "remaining": max(0, tpm_limit - tpm_used)},
                "rpd": {"limit": rpd_limit, "used": rpd_used, "remaining": max(0, rpd_limit - rpd_used)},
                "resets_at": (
                    pacific_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                ).astimezone(_UTC).isoformat(timespec="seconds"),
            }
        elif bucket_key == _OCR_BUCKET:
            minute_usage = _aggregate(bucket_key, minute_start)
            rpm_limit = _quota("WORKER_USAGE_AI_STUDIO_OCR_RPM", 15)
            tpm_limit = _quota("WORKER_USAGE_AI_STUDIO_OCR_TPM", 250_000)
            rpd_limit = _quota("WORKER_USAGE_AI_STUDIO_OCR_RPD", 500)
            rpm_used = int(minute_usage.get("request_count") or 0)
            tpm_used = int(minute_usage.get("input_tokens") or 0)
            rpd_used = int(usage.get("request_count") or 0)
            item["quota"] = {
                "rpm": {
                    "limit": rpm_limit,
                    "used": rpm_used,
                    "remaining": max(0, rpm_limit - rpm_used),
                },
                "tpm": {
                    "limit": tpm_limit,
                    "used": tpm_used,
                    "remaining": max(0, tpm_limit - tpm_used),
                },
                "rpd": {
                    "limit": rpd_limit,
                    "used": rpd_used,
                    "remaining": max(0, rpd_limit - rpd_used),
                },
                "resets_at": (
                    pacific_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                ).astimezone(_UTC).isoformat(timespec="seconds"),
            }
        models.append(item)

    return {
        "period": "today",
        "cost_day_timezone": "Asia/Shanghai",
        "quota_day_timezone": "America/Los_Angeles",
        "generated_at": now_utc.isoformat(timespec="seconds"),
        "models": models,
    }
