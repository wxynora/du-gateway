from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path
from typing import Any, Protocol

from PIL import Image, ImageDraw, ImageOps

from config import (
    WATCH_VISUAL_CACHE_DIR,
    WATCH_VISUAL_CONTEXT_ENABLED,
    WATCH_VISUAL_FRAME_LONG_EDGE,
    WATCH_VISUAL_SHEET_QUALITY,
)
from storage import watch_visual_store


SHEET_SIZE = (1536, 864)
CELL_SIZE = (768, 432)


class WatchVisualContextAdapter(Protocol):
    def cache_frames(self, session: dict, samples: list[dict]) -> list[dict]: ...

    def build_sheet(
        self,
        *,
        session_id: str,
        timeline_epoch: int,
        playhead_ms: int,
        reply_until_ms: int,
        current_chunks: list[dict],
        related_chunks: list[dict],
        reply_arrival_chunks: list[dict],
    ) -> dict: ...


class LocalWatchVisualContextAdapter:
    def cache_frames(self, session: dict, samples: list[dict]) -> list[dict]:
        return cache_analysis_frames(session, samples)

    def build_sheet(
        self,
        *,
        session_id: str,
        timeline_epoch: int,
        playhead_ms: int,
        reply_until_ms: int,
        current_chunks: list[dict],
        related_chunks: list[dict],
        reply_arrival_chunks: list[dict],
    ) -> dict:
        return build_contact_sheet(
            session_id=session_id,
            timeline_epoch=timeline_epoch,
            playhead_ms=playhead_ms,
            reply_until_ms=reply_until_ms,
            current_chunks=current_chunks,
            related_chunks=related_chunks,
            reply_arrival_chunks=reply_arrival_chunks,
        )


def _clock(ms: int) -> str:
    total = max(0, int(ms)) // 1000
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def cache_analysis_frames(session: dict, samples: list[dict]) -> list[dict]:
    if not WATCH_VISUAL_CONTEXT_ENABLED:
        return []
    session_id = str(session.get("session_id") or "").strip()
    media_id = str((session.get("media") or {}).get("id") or "").strip()
    timeline_epoch = int((session.get("playback") or {}).get("timeline_epoch") or 0)
    if not session_id or not media_id:
        return []
    output_dir = Path(WATCH_VISUAL_CACHE_DIR) / session_id / str(timeline_epoch)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[dict] = []
    for sample in samples:
        mime_type = str(sample.get("mime_type") or "").strip().lower()
        source_path = Path(str(sample.get("file_path") or ""))
        if not mime_type.startswith("image/") or not source_path.is_file():
            continue
        at_ms = max(0, int(sample.get("at_ms") or 0))
        try:
            with Image.open(source_path) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                image.thumbnail(
                    (int(WATCH_VISUAL_FRAME_LONG_EDGE), int(WATCH_VISUAL_FRAME_LONG_EDGE)),
                    Image.Resampling.LANCZOS,
                )
                buffer = io.BytesIO()
                image.save(
                    buffer,
                    format="WEBP",
                    quality=int(WATCH_VISUAL_SHEET_QUALITY),
                    method=4,
                )
                data = buffer.getvalue()
                digest = hashlib.sha256(data).hexdigest()
                frame_id = f"watch_frame_{hashlib.sha256(f'{session_id}:{timeline_epoch}:{at_ms}:{digest}'.encode()).hexdigest()[:24]}"
                target_path = output_dir / f"{at_ms}_{digest[:16]}.webp"
                target_path.write_bytes(data)
                saved.append(
                    watch_visual_store.upsert_frame(
                        frame_id=frame_id,
                        session_id=session_id,
                        media_id=media_id,
                        timeline_epoch=timeline_epoch,
                        at_ms=at_ms,
                        file_path=str(target_path),
                        width=image.width,
                        height=image.height,
                        sha256=digest,
                        source_sample_id=str(sample.get("id") or ""),
                    )
                )
        except Exception:
            continue
    return saved


def _nearest_frame(
    frames: list[dict],
    target_ms: int,
    *,
    used_ids: set[str],
    max_distance_ms: int | None,
) -> dict | None:
    candidates = [item for item in frames if str(item.get("id") or "") not in used_ids]
    if not candidates:
        return None
    selected = min(
        candidates,
        key=lambda item: (abs(int(item.get("at_ms") or 0) - int(target_ms)), int(item.get("at_ms") or 0)),
    )
    if max_distance_ms is not None and abs(int(selected.get("at_ms") or 0) - int(target_ms)) > max_distance_ms:
        return None
    return selected


def _current_target(current_chunks: list[dict], playhead_ms: int) -> int:
    if current_chunks:
        item = current_chunks[-1]
        start_ms = int(item.get("start_ms") or 0)
        end_ms = int(item.get("end_ms") or start_ms)
        return max(0, min(int(playhead_ms), (start_ms + end_ms) // 2))
    return max(0, playhead_ms)


def _related_target(related_chunks: list[dict], playhead_ms: int) -> int:
    if related_chunks:
        item = min(
            related_chunks,
            key=lambda chunk: int(chunk.get("recall_rank") or 0),
        )
        start_ms = int(item.get("start_ms") or 0)
        end_ms = int(item.get("end_ms") or start_ms)
        return max(0, (start_ms + end_ms) // 2)
    return max(0, playhead_ms - 15_000)


def _reply_arrival_target(reply_arrival_chunks: list[dict], reply_until_ms: int) -> int:
    if reply_arrival_chunks:
        item = reply_arrival_chunks[-1]
        start_ms = int(item.get("start_ms") or 0)
        end_ms = int(item.get("end_ms") or start_ms)
        return max(0, min(int(reply_until_ms), (start_ms + end_ms) // 2))
    return max(0, reply_until_ms)


def _select_frames(
    frames: list[dict],
    *,
    playhead_ms: int,
    reply_until_ms: int,
    current_chunks: list[dict] | None = None,
    related_chunks: list[dict] | None = None,
    reply_arrival_chunks: list[dict] | None = None,
) -> list[dict]:
    current_chunks = current_chunks or []
    related_chunks = related_chunks or []
    reply_arrival_chunks = reply_arrival_chunks or []
    targets = [
        ("A", "当前剧情", _current_target(current_chunks, playhead_ms), 35_000),
        ("B", "相关已观看片段", _related_target(related_chunks, playhead_ms), None),
        (
            "C",
            "预计抵达剧情",
            _reply_arrival_target(reply_arrival_chunks, reply_until_ms),
            35_000,
        ),
        ("D", "预计回复抵达", reply_until_ms, 35_000),
    ]
    selected: list[dict] = []
    used_ids: set[str] = set()
    for role, purpose, target_ms, max_distance in targets:
        frame = _nearest_frame(
            frames,
            target_ms,
            used_ids=used_ids,
            max_distance_ms=max_distance,
        )
        if frame is None:
            continue
        frame_id = str(frame.get("id") or "")
        used_ids.add(frame_id)
        selected.append({**frame, "role": role, "purpose": purpose})
    selected.sort(key=lambda item: "ABCD".index(str(item.get("role") or "D")))
    return selected[:4]


def _fit_into_cell(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    fitted = ImageOps.contain(image.convert("RGB"), size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, (13, 15, 18))
    x = (size[0] - fitted.width) // 2
    y = (size[1] - fitted.height) // 2
    canvas.paste(fitted, (x, y))
    return canvas


def build_contact_sheet(
    *,
    session_id: str,
    timeline_epoch: int,
    playhead_ms: int,
    reply_until_ms: int,
    current_chunks: list[dict] | None = None,
    related_chunks: list[dict] | None = None,
    reply_arrival_chunks: list[dict] | None = None,
) -> dict:
    if not WATCH_VISUAL_CONTEXT_ENABLED:
        return {}
    frames = watch_visual_store.list_frames(
        session_id,
        timeline_epoch=timeline_epoch,
        through_ms=reply_until_ms,
        from_ms=0,
    )
    selected = _select_frames(
        frames,
        playhead_ms=playhead_ms,
        reply_until_ms=reply_until_ms,
        current_chunks=current_chunks,
        related_chunks=related_chunks,
        reply_arrival_chunks=reply_arrival_chunks,
    )
    if len(selected) < 2:
        return {}
    sheet = Image.new("RGB", SHEET_SIZE, (13, 15, 18))
    draw = ImageDraw.Draw(sheet)
    metadata: list[dict] = []
    positions = [(0, 0), (CELL_SIZE[0], 0), (0, CELL_SIZE[1]), CELL_SIZE]
    for item, (x, y) in zip(selected, positions):
        try:
            with Image.open(Path(str(item.get("file_path") or ""))) as opened:
                cell = _fit_into_cell(ImageOps.exif_transpose(opened), CELL_SIZE)
        except Exception:
            continue
        sheet.paste(cell, (x, y))
        role = str(item.get("role") or "")
        at_ms = int(item.get("at_ms") or 0)
        label = f"{role}  {_clock(at_ms)}"
        draw.rectangle((x + 14, y + 14, x + 178, y + 48), fill=(0, 0, 0))
        draw.text((x + 24, y + 23), label, fill=(255, 255, 255))
        metadata.append(
            {
                "role": role,
                "at_ms": at_ms,
                "purpose": str(item.get("purpose") or ""),
                "frame_id": str(item.get("id") or ""),
            }
        )
    if len(metadata) < 2:
        return {}
    buffer = io.BytesIO()
    sheet.save(
        buffer,
        format="WEBP",
        quality=int(WATCH_VISUAL_SHEET_QUALITY),
        method=4,
    )
    data = buffer.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    return {
        "image_url": "data:image/webp;base64," + base64.b64encode(data).decode("ascii"),
        "sha256": digest,
        "mime_type": "image/webp",
        "width": SHEET_SIZE[0],
        "height": SHEET_SIZE[1],
        "panels": metadata,
    }
