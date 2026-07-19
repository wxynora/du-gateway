from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image, ImageOps

from config import (
    WATCH_ANALYSIS_MAX_AUDIO_BYTES,
    WATCH_ANALYSIS_MAX_FRAMES_PER_JOB,
    WATCH_ANALYSIS_MAX_LONG_EDGE,
    WATCH_ANALYSIS_MAX_REQUEST_BYTES,
    WATCH_ANALYSIS_MAX_SAMPLE_BYTES,
    WATCH_ANALYSIS_SAMPLE_DIR,
)


ALLOWED_PURPOSES = {"identify", "timeline_prepass", "rolling"}
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
ALLOWED_AUDIO_MIME_TYPES = {"audio/mpeg", "audio/mp3"}


class WatchAnalysisSampleError(ValueError):
    pass


def normalize_purpose(value: Any) -> str:
    purpose = str(value or "rolling").strip().lower() or "rolling"
    if purpose not in ALLOWED_PURPOSES:
        raise WatchAnalysisSampleError("purpose 只能是 identify/timeline_prepass/rolling")
    return purpose


def _int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def _text(value: Any, limit: int) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def decode_base64_image(value: Any) -> bytes:
    raw = str(value or "").strip()
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        return base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise WatchAnalysisSampleError("image_base64 无效") from exc


def _dhash(image: Image.Image) -> str:
    grayscale = ImageOps.grayscale(image).resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(grayscale.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | int(pixels[row * 9 + col] > pixels[row * 9 + col + 1])
    return f"{bits:016x}"


def _prepare_image(image_bytes: bytes, mime_type: str) -> tuple[bytes, int, int, str]:
    if not image_bytes:
        raise WatchAnalysisSampleError("图片内容为空")
    if len(image_bytes) > int(WATCH_ANALYSIS_MAX_SAMPLE_BYTES):
        raise WatchAnalysisSampleError("单张图片超过大小限制")
    normalized_mime = str(mime_type or "image/jpeg").strip().lower()
    if normalized_mime not in ALLOWED_IMAGE_MIME_TYPES:
        raise WatchAnalysisSampleError("只接受 JPEG/PNG/WebP 图片")
    try:
        with Image.open(io.BytesIO(image_bytes)) as opened:
            opened.verify()
        with Image.open(io.BytesIO(image_bytes)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.thumbnail(
                (int(WATCH_ANALYSIS_MAX_LONG_EDGE), int(WATCH_ANALYSIS_MAX_LONG_EDGE)),
                Image.Resampling.LANCZOS,
            )
            width, height = image.size
            perceptual_hash = _dhash(image)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=78, optimize=True)
            prepared = output.getvalue()
    except WatchAnalysisSampleError:
        raise
    except Exception as exc:
        raise WatchAnalysisSampleError("图片无法解码") from exc
    if not prepared or len(prepared) > int(WATCH_ANALYSIS_MAX_SAMPLE_BYTES):
        raise WatchAnalysisSampleError("缩图后仍超过大小限制")
    return prepared, width, height, perceptual_hash


def _prepare_audio(audio_bytes: bytes, mime_type: str) -> bytes:
    if not audio_bytes:
        raise WatchAnalysisSampleError("音频内容为空")
    if len(audio_bytes) > int(WATCH_ANALYSIS_MAX_AUDIO_BYTES):
        raise WatchAnalysisSampleError("单段音频超过大小限制")
    normalized_mime = str(mime_type or "audio/mpeg").strip().lower()
    if normalized_mime not in ALLOWED_AUDIO_MIME_TYPES:
        raise WatchAnalysisSampleError("只接受 MP3 音频")
    return bytes(audio_bytes)


def prepare_samples(
    *,
    session_id: str,
    media_id: str,
    timeline_epoch: int,
    duration_ms: int,
    purpose: str,
    raw_samples: list[dict],
) -> list[dict]:
    normalized_purpose = normalize_purpose(purpose)
    if not isinstance(raw_samples, list) or not raw_samples:
        raise WatchAnalysisSampleError("samples 不能为空")
    image_count = sum(
        1
        for item in raw_samples
        if isinstance(item, dict)
        and (item.get("image_bytes") is not None or item.get("image_base64"))
    )
    audio_count = sum(
        1
        for item in raw_samples
        if isinstance(item, dict) and item.get("audio_bytes") is not None
    )
    if image_count > int(WATCH_ANALYSIS_MAX_FRAMES_PER_JOB):
        raise WatchAnalysisSampleError("单次图片数量超过限制")
    if audio_count > 1:
        raise WatchAnalysisSampleError("单次滚动分析只接受一段音频")
    if audio_count and normalized_purpose != "rolling":
        raise WatchAnalysisSampleError("音频只用于 rolling 剧情分析")
    sample_dir = Path(WATCH_ANALYSIS_SAMPLE_DIR) / session_id / str(int(timeline_epoch))
    prepared_items: list[dict] = []
    total_bytes = 0
    try:
        for raw in raw_samples:
            if not isinstance(raw, dict):
                raise WatchAnalysisSampleError("sample 必须是对象")
            at_ms = _int(raw.get("at_ms"), 0)
            if duration_ms > 0 and at_ms > duration_ms:
                raise WatchAnalysisSampleError("sample.at_ms 超过媒体时长")
            subtitle = _text(raw.get("subtitle"), 2000)
            text_content = _text(raw.get("text") or raw.get("text_content"), 4000)
            captured_at = _text(raw.get("captured_at"), 80)
            image_bytes = raw.get("image_bytes")
            if image_bytes is None and raw.get("image_base64"):
                image_bytes = decode_base64_image(raw.get("image_base64"))
            if image_bytes is not None and not isinstance(image_bytes, bytes):
                raise WatchAnalysisSampleError("图片内容类型无效")
            audio_bytes = raw.get("audio_bytes")
            if audio_bytes is not None and not isinstance(audio_bytes, bytes):
                raise WatchAnalysisSampleError("音频内容类型无效")
            if image_bytes is not None and audio_bytes is not None:
                raise WatchAnalysisSampleError("同一个 sample 不能同时包含图片和音频")

            sample_id = f"watch_sample_{uuid4().hex}"
            file_path = ""
            sha256 = ""
            perceptual_hash = ""
            width = 0
            height = 0
            byte_size = 0
            mime_type = ""
            if image_bytes:
                prepared, width, height, perceptual_hash = _prepare_image(
                    image_bytes,
                    str(raw.get("mime_type") or "image/jpeg"),
                )
                byte_size = len(prepared)
                total_bytes += byte_size
                if total_bytes > int(WATCH_ANALYSIS_MAX_REQUEST_BYTES):
                    raise WatchAnalysisSampleError("单次上传图片总量超过限制")
                sample_dir.mkdir(parents=True, exist_ok=True)
                path = sample_dir / f"{sample_id}.jpg"
                path.write_bytes(prepared)
                file_path = str(path)
                mime_type = "image/jpeg"
                sha256 = hashlib.sha256(prepared).hexdigest()
            elif audio_bytes:
                prepared = _prepare_audio(
                    audio_bytes,
                    str(raw.get("mime_type") or "audio/mpeg"),
                )
                byte_size = len(prepared)
                total_bytes += byte_size
                if total_bytes > int(WATCH_ANALYSIS_MAX_REQUEST_BYTES):
                    raise WatchAnalysisSampleError("单次分析素材总量超过限制")
                sample_dir.mkdir(parents=True, exist_ok=True)
                path = sample_dir / f"{sample_id}.mp3"
                path.write_bytes(prepared)
                file_path = str(path)
                mime_type = "audio/mpeg"
                sha256 = hashlib.sha256(prepared).hexdigest()
            if not file_path and not subtitle and not text_content:
                raise WatchAnalysisSampleError("每个 sample 至少需要图片、音频、字幕或文字之一")
            prepared_items.append(
                {
                    "id": sample_id,
                    "session_id": session_id,
                    "media_id": media_id,
                    "timeline_epoch": int(timeline_epoch),
                    "purpose": normalized_purpose,
                    "at_ms": at_ms,
                    "mime_type": mime_type,
                    "file_path": file_path,
                    "text_content": text_content,
                    "subtitle": subtitle,
                    "sha256": sha256,
                    "perceptual_hash": perceptual_hash,
                    "width": width,
                    "height": height,
                    "byte_size": byte_size,
                    "captured_at": captured_at,
                }
            )
    except Exception:
        purge_prepared_samples(prepared_items)
        raise
    return prepared_items


def purge_prepared_samples(samples: list[dict]) -> None:
    for item in samples or []:
        raw_path = str((item or {}).get("file_path") or "").strip()
        if not raw_path:
            continue
        path = Path(raw_path)
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
