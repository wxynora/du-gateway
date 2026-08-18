"""Usage extraction and price accounting for background model responses."""

from __future__ import annotations

import logging
import os
from typing import Any

from storage import worker_usage_store


logger = logging.getLogger(__name__)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any) -> int:
    return max(0, int(_number(value, 0.0)))


def _env_price(name: str, default: float) -> float:
    return max(0.0, _number(os.environ.get(name), default))


def _bucket_for(provider: str, model: str) -> str:
    normalized_provider = str(provider or "").strip().lower()
    normalized_model = str(model or "").strip().lower()
    if normalized_provider == "google_ai_studio" or "gemini-3.5-flash-lite" in normalized_model:
        return "google_ai_studio"
    if "deepseek-v4-flash" in normalized_model:
        return "deepseek_v4_flash"
    if "gemini-3.7-flash" in normalized_model:
        return "gemini_3_7_flash"
    if "qwen3-reranker-8b" in normalized_model:
        return "qwen3_reranker_8b"
    return ""


def _usage_from_response(data: dict[str, Any]) -> tuple[int, int, int, dict[str, Any]]:
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    if not usage:
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        usage = meta.get("billed_units") if isinstance(meta.get("billed_units"), dict) else {}
        if not usage:
            usage = meta.get("tokens") if isinstance(meta.get("tokens"), dict) else {}
    input_tokens = _int(usage.get("prompt_tokens") or usage.get("input_tokens"))
    output_tokens = _int(usage.get("completion_tokens") or usage.get("output_tokens"))
    input_details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details")
    if not isinstance(input_details, dict):
        input_details = {}
    cached_input_tokens = min(input_tokens, _int(input_details.get("cached_tokens")))
    return input_tokens, output_tokens, cached_input_tokens, usage


def _price(
    *,
    bucket_key: str,
    provider: str,
    usage: dict[str, Any],
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int,
) -> tuple[float, str]:
    normalized_provider = str(provider or "").strip().lower()
    if normalized_provider == "openrouter" and ("cost" in usage or "cost_usd" in usage):
        raw = usage.get("cost") if "cost" in usage else usage.get("cost_usd")
        return max(0.0, _number(raw)), "USD"

    uncached_input_tokens = max(0, input_tokens - cached_input_tokens)
    if bucket_key == "deepseek_v4_flash":
        input_rate = _env_price("WORKER_USAGE_DEEPSEEK_V4_INPUT_CNY_PER_MILLION", 1.0)
        output_rate = _env_price("WORKER_USAGE_DEEPSEEK_V4_OUTPUT_CNY_PER_MILLION", 2.0)
        cached_rate = _env_price("WORKER_USAGE_DEEPSEEK_V4_CACHED_INPUT_CNY_PER_MILLION", 0.02)
        value = (
            uncached_input_tokens * input_rate
            + cached_input_tokens * cached_rate
            + output_tokens * output_rate
        ) / 1_000_000
        return value, "CNY"

    if bucket_key == "qwen3_reranker_8b":
        input_rate = _env_price("WORKER_USAGE_QWEN3_RERANKER_8B_INPUT_CNY_PER_MILLION", 0.28)
        value = input_tokens * input_rate / 1_000_000
        return value, "CNY"

    if bucket_key == "gemini_3_7_flash":
        input_rate = _env_price("WORKER_USAGE_GEMINI_3_7_INPUT_USD_PER_MILLION", 0.375)
        output_rate = _env_price("WORKER_USAGE_GEMINI_3_7_OUTPUT_USD_PER_MILLION", 1.875)
        value = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
        return value, "USD"

    return 0.0, ""


def record_response_usage(
    *,
    role: str,
    provider: str,
    model: str,
    data: dict[str, Any],
) -> None:
    bucket_key = _bucket_for(provider, model)
    if not bucket_key:
        return
    input_tokens, output_tokens, cached_input_tokens, usage = _usage_from_response(data)
    cost_value, currency = _price(
        bucket_key=bucket_key,
        provider=provider,
        usage=usage,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
    )
    try:
        worker_usage_store.record_usage(
            bucket_key=bucket_key,
            role=role,
            provider=provider,
            model=str(data.get("model") or model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            cost_value=cost_value,
            currency=currency,
        )
    except Exception as exc:
        logger.warning(
            "worker usage record failed role=%s provider=%s model=%s error=%s",
            role,
            provider,
            model,
            exc,
        )


def dashboard_snapshot() -> dict[str, Any]:
    return worker_usage_store.dashboard_snapshot()
