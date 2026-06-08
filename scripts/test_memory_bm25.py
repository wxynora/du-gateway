#!/usr/bin/env python3
"""Local checks for BM25 keyword memory retrieval; no network/API call."""

import sys

sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 2)[0])

from services.memory_bm25 import BM25QueryTerm, bm25_score_documents, tokenize_bm25  # noqa: E402
from pipeline.pipeline import _bm25_recall_scores, _merge_vector_and_bm25_recall  # noqa: E402


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_chinese_ngram_tokenizer() -> None:
    tokens = tokenize_bm25("那你亲亲我 Claude proxy")
    _assert("亲亲" in tokens, "Chinese bigram should be available for matching")
    _assert("claude" in tokens and "proxy" in tokens, "ASCII words should be tokenized")


def test_bm25_ranks_relevant_memory_first() -> None:
    memories = [
        {"id": "a", "content": "老婆叫哥哥要亲亲，我嘴上说没办法，但还是亲了。"},
        {"id": "b", "content": "今天把 Claude proxy 的 token 刷新脚本检查了一遍。"},
        {"id": "c", "content": "晚上一起看电影，顺便点了奶茶。"},
    ]
    ranked = bm25_score_documents(
        "那你亲亲我",
        memories,
        lambda mem: str(mem.get("content") or ""),
        query_terms=[BM25QueryTerm("亲亲", weight=2.0)],
    )
    ranked.sort(key=lambda item: -item[0])
    _assert(ranked[0][1]["id"] == "a", "亲亲 memory should rank first")
    _assert(ranked[0][0] > ranked[1][0], "top memory should have a stronger BM25 score")


def test_unrelated_memory_scores_zero() -> None:
    ranked = bm25_score_documents(
        "查一下 token",
        [{"id": "x", "content": "晚上吃了炒饭。"}],
        lambda mem: str(mem.get("content") or ""),
    )
    _assert(ranked and ranked[0][0] == 0.0, "unrelated memory should have zero BM25 score")


def test_vector_and_bm25_are_merged_before_final_sort() -> None:
    keyword_mem = {
        "id": "keyword",
        "content": "老婆叫哥哥要亲亲，我嘴上说没办法，但还是亲了。",
        "importance": 3,
        "mention_count": 0,
    }
    vector_mem = {
        "id": "vector",
        "content": "晚上一起看电影，顺便点了奶茶。",
        "importance": 1,
        "mention_count": 0,
        "_recall_score": {"total": 0.7, "sem_user": 0.6, "sem_ctx": 0.6},
    }
    bm25_scores = _bm25_recall_scores("那你亲亲我", [], [keyword_mem, vector_mem])
    merged = _merge_vector_and_bm25_recall([vector_mem], bm25_scores)
    ids = [str(mem.get("id") or "") for mem in merged]
    _assert("keyword" in ids and "vector" in ids, "BM25 and vector candidates should share one pool")
    _assert(ids[0] == "keyword", "strong BM25 hit should be able to outrank vector-only hit")


if __name__ == "__main__":
    test_chinese_ngram_tokenizer()
    test_bm25_ranks_relevant_memory_first()
    test_unrelated_memory_scores_zero()
    test_vector_and_bm25_are_merged_before_final_sort()
    print("memory BM25 checks passed")
