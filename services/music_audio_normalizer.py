from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass


TARGET_AUDIO_FORMAT = "mp3"
TARGET_AUDIO_MIME_TYPE = "audio/mpeg"
TARGET_AUDIO_FILENAME = "music-analysis.mp3"
TARGET_AUDIO_BITRATE = "192k"
TARGET_AUDIO_SAMPLE_RATE = "44100"


class MusicAudioNormalizationError(Exception):
    pass


@dataclass(frozen=True)
class PreparedMusicAudio:
    audio_bytes: bytes
    audio_format: str
    filename: str
    mime_type: str
    converted: bool
    source_codec: str
    source_container: str


def _tool_path(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise MusicAudioNormalizationError(f"缺少 {name}，无法识别或转换音频格式")
    return path


def _probe_audio(path: str, ffprobe: str) -> tuple[str, str]:
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name,codec_type:format=format_name",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise MusicAudioNormalizationError("识别音频格式超时") from e
    except Exception as e:
        raise MusicAudioNormalizationError(f"识别音频格式失败: {e}") from e

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[:300]
        raise MusicAudioNormalizationError(f"无法识别音频格式{': ' + detail if detail else ''}")
    try:
        data = json.loads(proc.stdout or "{}")
    except Exception as e:
        raise MusicAudioNormalizationError("ffprobe 返回了无效结果") from e

    streams = data.get("streams") if isinstance(data, dict) else None
    stream = streams[0] if isinstance(streams, list) and streams and isinstance(streams[0], dict) else {}
    codec = str(stream.get("codec_name") or "").strip().lower()
    codec_type = str(stream.get("codec_type") or "").strip().lower()
    container = str(((data.get("format") or {}) if isinstance(data, dict) else {}).get("format_name") or "").strip().lower()
    if codec_type != "audio" or not codec:
        raise MusicAudioNormalizationError("文件中没有可分析的音频流")
    return codec, container


def _is_mp3(codec: str, container: str) -> bool:
    containers = {item.strip() for item in str(container or "").split(",") if item.strip()}
    return codec == "mp3" and "mp3" in containers


def prepare_music_audio(
    audio_bytes: bytes,
    *,
    max_source_bytes: int,
    max_output_bytes: int,
) -> PreparedMusicAudio:
    """Inspect real bytes and normalize non-MP3 audio before model analysis."""
    if not audio_bytes:
        raise MusicAudioNormalizationError("音频文件为空")
    if len(audio_bytes) > max_source_bytes:
        raise MusicAudioNormalizationError(f"源音频过大，最大 {max_source_bytes // 1024 // 1024}MB")
    if audio_bytes.startswith(b"CTENFDAM"):
        raise MusicAudioNormalizationError(
            "网易云 .ncm 是加密缓存文件，不能直接转码；请使用网易云曲目分析入口获取真实音频流"
        )

    ffprobe = _tool_path("ffprobe")
    with tempfile.TemporaryDirectory(prefix="du_music_analysis_") as tmp:
        src = os.path.join(tmp, "source.audio")
        dst = os.path.join(tmp, TARGET_AUDIO_FILENAME)
        with open(src, "wb") as f:
            f.write(audio_bytes)

        source_codec, source_container = _probe_audio(src, ffprobe)
        if _is_mp3(source_codec, source_container) and len(audio_bytes) <= max_output_bytes:
            return PreparedMusicAudio(
                audio_bytes=audio_bytes,
                audio_format=TARGET_AUDIO_FORMAT,
                filename=TARGET_AUDIO_FILENAME,
                mime_type=TARGET_AUDIO_MIME_TYPE,
                converted=False,
                source_codec=source_codec,
                source_container=source_container,
            )

        ffmpeg = _tool_path("ffmpeg")
        try:
            proc = subprocess.run(
                [
                    ffmpeg,
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    src,
                    "-map",
                    "0:a:0",
                    "-vn",
                    "-map_metadata",
                    "-1",
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    TARGET_AUDIO_BITRATE,
                    "-ar",
                    TARGET_AUDIO_SAMPLE_RATE,
                    "-ac",
                    "2",
                    dst,
                ],
                capture_output=True,
                timeout=180,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise MusicAudioNormalizationError("音频格式转换超时") from e
        except Exception as e:
            raise MusicAudioNormalizationError(f"音频格式转换失败: {e}") from e

        if proc.returncode != 0:
            detail = (proc.stderr or b"").decode("utf-8", errors="ignore").strip()[:300]
            raise MusicAudioNormalizationError(f"音频格式转换失败{': ' + detail if detail else ''}")
        try:
            with open(dst, "rb") as f:
                converted = f.read()
        except Exception as e:
            raise MusicAudioNormalizationError(f"读取转换结果失败: {e}") from e
        if not converted:
            raise MusicAudioNormalizationError("音频格式转换结果为空")
        if len(converted) > max_output_bytes:
            raise MusicAudioNormalizationError(f"转换后的音频过大，最大 {max_output_bytes // 1024 // 1024}MB")

        output_codec, output_container = _probe_audio(dst, ffprobe)
        if not _is_mp3(output_codec, output_container):
            raise MusicAudioNormalizationError("音频转换结果不是有效 MP3")
        return PreparedMusicAudio(
            audio_bytes=converted,
            audio_format=TARGET_AUDIO_FORMAT,
            filename=TARGET_AUDIO_FILENAME,
            mime_type=TARGET_AUDIO_MIME_TYPE,
            converted=True,
            source_codec=source_codec,
            source_container=source_container,
        )
