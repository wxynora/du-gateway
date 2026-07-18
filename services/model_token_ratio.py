"""Persist the first observed request-token/character ratio for each model."""

from __future__ import annotations

import time
from typing import Any

from storage import runtime_sqlite
from utils.log import get_logger

logger = get_logger(__name__)


def _model_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def get_model_tokens_per_char(model: str) -> float | None:
    key = _model_key(model)
    if not key:
        return None
    try:
        with runtime_sqlite.connect() as conn:
            row = conn.execute(
                "SELECT tokens_per_char FROM model_token_ratios WHERE model = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        value = float(row["tokens_per_char"] or 0)
        return value if value > 0 else None
    except Exception:
        logger.warning("model token ratio read failed model=%s", key, exc_info=True)
        return None


def learn_model_token_ratio(cache_debug: dict) -> float | None:
    """Store the first real request-token sample for a selected model and never overwrite it."""
    if not isinstance(cache_debug, dict):
        return None
    request = cache_debug.get("request") if isinstance(cache_debug.get("request"), dict) else {}
    usage = cache_debug.get("usage") if isinstance(cache_debug.get("usage"), dict) else {}
    response = cache_debug.get("response") if isinstance(cache_debug.get("response"), dict) else {}
    model = _model_key(request.get("selected_model") or request.get("model"))
    if not model or usage.get("usage_returned") is False:
        return None

    input_chars = _positive_int(request.get("request_chars"))
    if input_chars <= 0:
        input_chars = _positive_int(request.get("input_chars"))
    input_tokens = (
        _positive_int(usage.get("input_tokens"))
        + _positive_int(usage.get("cache_creation_input_tokens"))
        + _positive_int(usage.get("cache_read_input_tokens"))
    )
    if input_tokens <= 0:
        input_tokens = _positive_int(usage.get("prompt_tokens"))
    if input_chars <= 0 or input_tokens <= 0:
        return None

    ratio = input_tokens / input_chars
    actual_model = str(response.get("actual_model") or "").strip()
    try:
        with runtime_sqlite.connect() as conn:
            inserted = conn.execute(
                """
                INSERT OR IGNORE INTO model_token_ratios(
                    model, actual_model, tokens_per_char, sample_chars, sample_input_tokens, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (model, actual_model, ratio, input_chars, input_tokens, time.time()),
            ).rowcount
            row = conn.execute(
                "SELECT tokens_per_char FROM model_token_ratios WHERE model = ?",
                (model,),
            ).fetchone()
        learned = float(row["tokens_per_char"] or 0) if row is not None else 0.0
        if inserted:
            logger.info(
                "model token ratio learned model=%s actual_model=%s chars=%s input_tokens=%s tokens_per_char=%.6f",
                model,
                actual_model,
                input_chars,
                input_tokens,
                learned,
            )
        return learned if learned > 0 else None
    except Exception:
        logger.warning("model token ratio write failed model=%s", model, exc_info=True)
        return None
