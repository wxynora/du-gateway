from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Iterable, TypeVar


T = TypeVar("T")

_TEXT_TOKEN_RE = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]+", re.IGNORECASE)
_CJK_RE = re.compile(r"^[\u4e00-\u9fff]+$")


@dataclass(frozen=True)
class BM25QueryTerm:
    text: str
    weight: float = 1.0


def tokenize_bm25(text: str) -> list[str]:
    """
    轻量 BM25 分词。
    英文/数字按词切；中文没有额外依赖，保留短完整片段并生成 2/3-gram。
    """
    raw = str(text or "").strip().lower()
    if not raw:
        return []
    tokens: list[str] = []
    for part in _TEXT_TOKEN_RE.findall(raw):
        if not part:
            continue
        if _CJK_RE.fullmatch(part):
            if len(part) == 1:
                tokens.append(part)
                continue
            if len(part) <= 12:
                tokens.append(part)
            for n in (2, 3):
                if len(part) < n:
                    continue
                for i in range(0, len(part) - n + 1):
                    tokens.append(part[i : i + n])
            continue
        if len(part) >= 2:
            tokens.append(part)
    return tokens


def _query_weights(query: str, query_terms: Iterable[BM25QueryTerm] | None = None) -> Counter[str]:
    weights: Counter[str] = Counter()
    for token in tokenize_bm25(query):
        weights[token] += 1.0
    for term in query_terms or []:
        text = str((term or BM25QueryTerm("")).text or "").strip()
        if not text:
            continue
        weight = max(0.1, float((term or BM25QueryTerm("")).weight or 1.0))
        for token in tokenize_bm25(text):
            weights[token] += weight
    return weights


def bm25_score_documents(
    query: str,
    documents: Iterable[T],
    text_getter: Callable[[T], str],
    *,
    query_terms: Iterable[BM25QueryTerm] | None = None,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[tuple[float, T]]:
    """
    对一组文档按 BM25 计算关键词相关性分数。
    返回值保留所有可取文本的文档；无命中文档分数为 0，由调用方决定是否过滤。
    """
    indexed: list[tuple[T, Counter[str], int]] = []
    doc_freq: Counter[str] = Counter()
    for doc in documents or []:
        tokens = tokenize_bm25(text_getter(doc))
        if not tokens:
            continue
        counts = Counter(tokens)
        indexed.append((doc, counts, len(tokens)))
        for token in counts:
            doc_freq[token] += 1

    if not indexed:
        return []

    q_weights = _query_weights(query, query_terms=query_terms)
    if not q_weights:
        return [(0.0, doc) for doc, _, _ in indexed]

    doc_count = len(indexed)
    avg_doc_len = sum(length for _, _, length in indexed) / max(1, doc_count)
    out: list[tuple[float, T]] = []

    for doc, counts, doc_len in indexed:
        score = 0.0
        norm = k1 * (1 - b + b * (doc_len / max(avg_doc_len, 1e-9)))
        for token, q_weight in q_weights.items():
            tf = counts.get(token, 0)
            if tf <= 0:
                continue
            df = doc_freq.get(token, 0)
            if df <= 0:
                continue
            idf = math.log(1 + (doc_count - df + 0.5) / (df + 0.5))
            tf_part = (tf * (k1 + 1)) / (tf + norm)
            score += float(q_weight) * idf * tf_part
        out.append((float(score), doc))

    return out
