from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DynamicMemoryItem:
    id: str
    content: str
    importance: int = 0
    mention_count: int = 0
    tag: str = ""
    created_at: str = ""
    last_mentioned: str = ""


@dataclass
class DynamicMemoryEmbeddingRecord:
    memory_id: str
    text: str
    embedding: list[float]
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DynamicMemoryEmbeddingIndex:
    schema_version: int = 1
    tag: str = ""
    embedding_model: str = ""
    updated_at: str = ""
    records: list[DynamicMemoryEmbeddingRecord] = field(default_factory=list)


@dataclass
class RetrievedCandidate:
    memory_id: str
    cosine_sim: float
    weight: float
    memory: Optional[dict] = None

