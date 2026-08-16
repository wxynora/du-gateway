"""Shared request metadata for prompt-pipeline assembly."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PipelineRequestContext:
    window_id: str
    model: str
    reply_channel: str
    prompt_reply_channel: str
    reply_target: str
    wakeup_kind: str
    anthropic_messages: bool


__all__ = ("PipelineRequestContext",)
