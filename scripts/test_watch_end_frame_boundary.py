from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storage import watch_analysis_store


def main() -> None:
    duration_ms = 6_422_950
    planned = watch_analysis_store._source_plan_timestamps(
        [6_360_000, duration_ms],
        duration_ms=duration_ms,
        purpose="rolling",
    )
    assert planned == [6_360_000, 6_421_950]
    assert max(planned) < duration_ms

    content_end_ms = 582_000
    planned = watch_analysis_store._source_plan_timestamps(
        [440_000, content_end_ms],
        duration_ms=859_627,
        content_end_ms=content_end_ms,
        purpose="rolling",
    )
    assert planned == [440_000, 581_000]
    assert max(planned) < content_end_ms

    assert watch_analysis_store._advance_terminal_coverage(
        6_421_950,
        job_range_end_ms=6_421_950,
        duration_ms=duration_ms,
    ) == duration_ms
    assert watch_analysis_store._advance_terminal_coverage(
        580_000,
        job_range_end_ms=581_000,
        duration_ms=859_627,
        content_end_ms=content_end_ms,
    ) == 580_000
    assert watch_analysis_store._advance_terminal_coverage(
        581_000,
        job_range_end_ms=581_000,
        duration_ms=859_627,
        content_end_ms=content_end_ms,
    ) == content_end_ms


if __name__ == "__main__":
    main()
    print("watch end frame boundary: ok")
