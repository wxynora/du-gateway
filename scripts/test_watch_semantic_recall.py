from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import watch_context
from storage import runtime_sqlite, watch_runtime_store


def _chunk(index: int) -> dict:
    return {
        "id": f"chunk_{index}",
        "start_ms": index * 10_000,
        "end_ms": (index + 1) * 10_000,
        "summary": f"人物围绕钥匙争执，随后发生事件 {index}",
        "dialogue_summary": "他仍然没有解释自己的决定。",
        "characters": ["甲", "乙"],
        "tags": ["争执"],
    }


def main() -> None:
    original_embed = watch_context.embed_texts_with_cloudflare_model
    original_save = watch_context.watch_runtime_store.save_plot_chunk_recall_embeddings
    saved: list[dict] = []

    def fake_embed(texts: list[str], *, model: str) -> list[list[float]]:
        assert model == "@cf/qwen/qwen3-embedding-0.6b"
        vectors = [[1.0, 0.0]]
        for text in texts[1:]:
            vectors.append([1.0, 0.0] if "事件 0" in text else [0.0, 1.0])
        return vectors

    def fake_save(session_id: str, *, model: str, embeddings: list[dict]) -> int:
        assert session_id == "watch_test"
        assert model == "@cf/qwen/qwen3-embedding-0.6b"
        saved.extend(embeddings)
        return len(embeddings)

    watch_context.embed_texts_with_cloudflare_model = fake_embed
    watch_context.watch_runtime_store.save_plot_chunk_recall_embeddings = fake_save
    try:
        chunks = [_chunk(index) for index in range(5)]
        selected = watch_context._recall_related_chunks(
            "钥匙",
            chunks,
            session_id="watch_test",
            excluded_ids=set(),
        )
        selected_ids = {item["summary"].rsplit(" ", 1)[-1] for item in selected}
        assert "0" in selected_ids
        assert len(selected) == 4
        assert len(saved) == 5

        cached_chunks = [_chunk(0)]
        cached_text = watch_context._chunk_semantic_text(cached_chunks[0])
        cached_chunks[0].update(
            {
                "recall_embedding": [1.0, 0.0],
                "recall_embedding_model": "@cf/qwen/qwen3-embedding-0.6b",
                "recall_embedding_hash": watch_context._semantic_content_hash(cached_text),
            }
        )
        calls: list[list[str]] = []

        def query_only_embed(texts: list[str], *, model: str) -> list[list[float]]:
            calls.append(texts)
            return [[1.0, 0.0]]

        watch_context.embed_texts_with_cloudflare_model = query_only_embed
        saved.clear()
        scores = watch_context._semantic_scores_for_chunks(
            "钥匙",
            cached_chunks,
            session_id="watch_test",
        )
        assert scores == {"chunk_0": 1.0}
        assert len(calls) == 1 and len(calls[0]) == 1
        assert saved == []

        def failed_embed(texts: list[str], *, model: str) -> list[list[float]]:
            raise RuntimeError("temporary unavailable")

        watch_context.embed_texts_with_cloudflare_model = failed_embed
        fallback = watch_context._recall_related_chunks(
            "钥匙",
            [_chunk(index) for index in range(5)],
            session_id="watch_test",
            excluded_ids=set(),
        )
        assert len(fallback) == 4
    finally:
        watch_context.embed_texts_with_cloudflare_model = original_embed
        watch_context.watch_runtime_store.save_plot_chunk_recall_embeddings = original_save

    original_db_path = runtime_sqlite.RUNTIME_STATE_DB
    original_schema_ready = runtime_sqlite._SCHEMA_READY
    try:
        with TemporaryDirectory() as directory:
            runtime_sqlite.RUNTIME_STATE_DB = str(Path(directory) / "runtime.sqlite3")
            runtime_sqlite._SCHEMA_READY = False
            with runtime_sqlite.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO watch_plot_chunks (
                        id, session_id, start_ms, end_ms, created_at, updated_at
                    ) VALUES ('persisted', 'watch_test', 0, 10000, 'now', 'now')
                    """
                )
            count = watch_runtime_store.save_plot_chunk_recall_embeddings(
                "watch_test",
                model="@cf/qwen/qwen3-embedding-0.6b",
                embeddings=[
                    {
                        "id": "persisted",
                        "content_hash": "sha256:test",
                        "embedding": [0.25, 0.75],
                    }
                ],
            )
            assert count == 1
            stored = watch_runtime_store.get_completed_plot_chunks(
                "watch_test",
                timeline_epoch=0,
                through_ms=10000,
            )
            assert stored[0]["recall_embedding"] == [0.25, 0.75]
            assert stored[0]["recall_embedding_model"] == "@cf/qwen/qwen3-embedding-0.6b"
            assert stored[0]["recall_embedding_hash"] == "sha256:test"
    finally:
        runtime_sqlite.RUNTIME_STATE_DB = original_db_path
        runtime_sqlite._SCHEMA_READY = original_schema_ready


if __name__ == "__main__":
    main()
    print("watch semantic recall: ok")
