#!/usr/bin/env python3
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.watch_analysis_source import (
    BilibiliApiAnalysisSource,
    WatchAnalysisSourceError,
)


class BilibiliStreamFallbackTest(unittest.TestCase):
    def test_working_backup_is_promoted_for_later_frames(self) -> None:
        attempted_urls: list[str] = []

        def run(command: list[str], **_kwargs):
            stream_url = command[command.index("-i") + 1]
            attempted_urls.append(stream_url)
            if stream_url.endswith("primary"):
                return subprocess.CompletedProcess(command, 1, b"", b"HTTP 403")
            return subprocess.CompletedProcess(command, 0, b"jpeg", b"")

        source = BilibiliApiAnalysisSource(command_runner=run)
        resolved = {
            "headers": {},
            "stream_urls": [
                "https://cdn.example/primary",
                "https://cdn.example/backup",
            ],
        }

        self.assertEqual(source._extract_frame(resolved, 1_000), b"jpeg")
        self.assertEqual(source._extract_frame(resolved, 2_000), b"jpeg")
        self.assertEqual(
            attempted_urls,
            [
                "https://cdn.example/primary",
                "https://cdn.example/backup",
                "https://cdn.example/backup",
            ],
        )

    def test_refreshes_and_retries_only_the_failed_current_frame(self) -> None:
        source = BilibiliApiAnalysisSource()
        old_resolution = {"name": "old", "subtitles": []}
        fresh_resolution = {"name": "fresh", "subtitles": []}
        resolutions = iter([old_resolution, fresh_resolution])
        refresh_calls: list[str] = []
        frame_calls: list[tuple[str, int]] = []

        def refresh(_media: dict) -> dict:
            refresh_calls.append("refresh")
            return next(resolutions)

        def extract(resolved: dict, at_ms: int) -> bytes:
            name = str(resolved["name"])
            frame_calls.append((name, at_ms))
            if name == "old" and at_ms == 2_000:
                raise WatchAnalysisSourceError("expired", retryable=True)
            return f"{name}:{at_ms}".encode()

        source._refresh_resolution = refresh
        source._extract_frame = extract

        samples = source.acquire(
            {
                "media": {
                    "source": "bilibili_embed",
                    "duration_ms": 10_000,
                }
            },
            purpose="identify",
            timestamps_ms=[1_000, 2_000, 3_000],
        )

        self.assertEqual(len(refresh_calls), 2)
        self.assertEqual(
            frame_calls,
            [
                ("old", 1_000),
                ("old", 2_000),
                ("fresh", 2_000),
                ("fresh", 3_000),
            ],
        )
        self.assertEqual(
            [sample["image_bytes"] for sample in samples],
            [b"old:1000", b"fresh:2000", b"fresh:3000"],
        )


if __name__ == "__main__":
    unittest.main()
