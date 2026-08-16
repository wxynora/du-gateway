"""Shared request metadata for prompt-pipeline assembly."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class PipelineRequestContext:
    window_id: str
    model: str
    reply_channel: str
    prompt_reply_channel: str
    reply_target: str
    wakeup_kind: str
    headers: Mapping[str, str]
    upstream_url: str
    anthropic_messages: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers or {})))


__all__ = ("PipelineRequestContext",)
