from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import watch_context


def chunk(chunk_id: str, start_ms: int, end_ms: int) -> dict:
    return {
        "id": chunk_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "summary": chunk_id,
    }


def main() -> None:
    chunks = [
        chunk("too_old", 40_000, 64_999),
        chunk("lookback", 55_000, 80_000),
        chunk("just_seen", 80_000, 95_000),
        chunk("current", 95_000, 120_000),
        chunk("future", 100_001, 130_000),
    ]
    selected = watch_context._current_context_source(chunks, 100_000)
    assert [item["id"] for item in selected] == ["lookback", "just_seen", "current"]

    crowded = [chunk(f"part_{index}", 70_000 + index * 5_000, 110_000) for index in range(6)]
    selected = watch_context._current_context_source(crowded, 100_000)
    assert [item["id"] for item in selected] == ["part_2", "part_3", "part_4", "part_5"]


if __name__ == "__main__":
    main()
    print("watch context lookback: ok")
