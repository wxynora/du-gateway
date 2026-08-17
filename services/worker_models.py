"""Central model assignments for background worker roles."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from config import (
    DEEPGRAM_API_KEY,
    DEEPGRAM_STT_MODEL,
    DEEPGRAM_STT_URL,
    DYNAMIC_MEMORY_RERANK_API_URL,
    DYNAMIC_MEMORY_RERANK_MODEL,
    DYNAMIC_MEMORY_RERANK_PROVIDER,
    SILICONFLOW_BASE_HOST,
    VOICE_STT_OPENROUTER_API_KEY,
    VOICE_STT_OPENROUTER_API_URL,
    VOICE_STT_OPENROUTER_FALLBACK_MODEL,
    VOICE_STT_OPENROUTER_MODEL,
    VOICE_STT_FALLBACK_PROVIDER,
    VOICE_STT_PROVIDER,
    WEBSEARCH_COMPRESS_API_URL,
    WEBSEARCH_COMPRESS_MODEL,
    resolve_siliconflow_api_key,
)


WORKER_ROLES = frozenset({"translate", "structured", "ocr", "asr", "rerank"})


@dataclass(frozen=True)
class WorkerModelSpec:
    role: str
    provider: str
    protocol: str
    api_url: str
    model: str
    api_key: str = field(default="", repr=False)
    fallback_models: tuple[str, ...] = ()
    fallback_providers: tuple[str, ...] = ()


def _env(name: str, fallback: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        return str(fallback or "").strip()
    return str(value or "").strip()


def _env_or(name: str, fallback: str = "") -> str:
    return _env(name) or str(fallback or "").strip()


def _siliconflow_chat_url() -> str:
    host = str(SILICONFLOW_BASE_HOST or "").strip()
    return f"https://{host}/v1/chat/completions" if host else ""


def _siliconflow_key(env_name: str) -> str:
    return _env(env_name) or str(resolve_siliconflow_api_key() or "").strip()


def get_worker_model(role: str, *, provider: str | None = None) -> WorkerModelSpec:
    normalized_role = str(role or "").strip().lower()
    if normalized_role not in WORKER_ROLES:
        raise ValueError(f"unknown worker model role: {role}")

    if normalized_role == "translate":
        return WorkerModelSpec(
            role="translate",
            provider=_env_or("WORKER_TRANSLATE_PROVIDER", "siliconflow").lower(),
            protocol="openai_chat",
            api_url=_env_or("WORKER_TRANSLATE_API_URL", _siliconflow_chat_url()),
            api_key=_siliconflow_key("WORKER_TRANSLATE_API_KEY"),
            model=_env_or("WORKER_TRANSLATE_MODEL", "tencent/Hunyuan-MT-7B"),
        )

    if normalized_role == "structured":
        return WorkerModelSpec(
            role="structured",
            provider=_env_or("WORKER_STRUCTURED_PROVIDER", "siliconflow").lower(),
            protocol="openai_chat",
            api_url=_env_or("WORKER_STRUCTURED_API_URL", WEBSEARCH_COMPRESS_API_URL),
            api_key=_siliconflow_key("WORKER_STRUCTURED_API_KEY"),
            model=_env_or("WORKER_STRUCTURED_MODEL", WEBSEARCH_COMPRESS_MODEL),
        )

    if normalized_role == "ocr":
        return WorkerModelSpec(
            role="ocr",
            provider=_env_or("WORKER_OCR_PROVIDER", "google_ai_studio").lower(),
            protocol="openai_chat_vision",
            api_url=_env_or(
                "WORKER_OCR_API_URL",
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            ),
            api_key=_env("WORKER_OCR_API_KEY"),
            model=_env_or("WORKER_OCR_MODEL", "gemini-3.5-flash-lite"),
        )

    if normalized_role == "asr":
        selected_provider = str(provider or _env_or("WORKER_ASR_PROVIDER", VOICE_STT_PROVIDER)).strip().lower()
        fallback_provider = ""
        if provider is None:
            fallback_provider = _env_or("WORKER_ASR_FALLBACK_PROVIDER", VOICE_STT_FALLBACK_PROVIDER).lower()
            if fallback_provider in {"gemini", "google", "gemini-openrouter"}:
                fallback_provider = "openrouter"
            if fallback_provider == selected_provider:
                fallback_provider = ""
        fallback_providers = (fallback_provider,) if fallback_provider else ()
        if selected_provider == "deepgram":
            return WorkerModelSpec(
                role="asr",
                provider="deepgram",
                protocol="deepgram_transcription",
                api_url=_env_or("WORKER_ASR_DEEPGRAM_API_URL", DEEPGRAM_STT_URL),
                api_key=_env_or("WORKER_ASR_DEEPGRAM_API_KEY", DEEPGRAM_API_KEY),
                model=_env_or("WORKER_ASR_DEEPGRAM_MODEL", DEEPGRAM_STT_MODEL),
                fallback_providers=fallback_providers,
            )
        if selected_provider in {"openrouter", "gemini", "google", "gemini-openrouter"}:
            fallback = _env("WORKER_ASR_OPENROUTER_FALLBACK_MODEL", VOICE_STT_OPENROUTER_FALLBACK_MODEL)
            return WorkerModelSpec(
                role="asr",
                provider="openrouter",
                protocol="openrouter_chat_audio",
                api_url=_env_or("WORKER_ASR_OPENROUTER_API_URL", VOICE_STT_OPENROUTER_API_URL),
                api_key=_env_or("WORKER_ASR_OPENROUTER_API_KEY", VOICE_STT_OPENROUTER_API_KEY),
                model=_env_or("WORKER_ASR_OPENROUTER_MODEL", VOICE_STT_OPENROUTER_MODEL),
                fallback_models=(fallback,) if fallback else (),
                fallback_providers=fallback_providers,
            )
        raise ValueError(f"unknown asr worker provider: {selected_provider}")

    return WorkerModelSpec(
        role="rerank",
        provider=_env_or("WORKER_RERANK_PROVIDER", DYNAMIC_MEMORY_RERANK_PROVIDER).lower(),
        protocol="rerank",
        api_url=_env_or("WORKER_RERANK_API_URL", DYNAMIC_MEMORY_RERANK_API_URL),
        api_key=_siliconflow_key("WORKER_RERANK_API_KEY"),
        model=_env_or("WORKER_RERANK_MODEL", DYNAMIC_MEMORY_RERANK_MODEL),
    )
