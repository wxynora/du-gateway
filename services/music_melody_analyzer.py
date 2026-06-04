from __future__ import annotations

import base64
import json
import mimetypes
import re
from typing import Any, Optional

import requests

from config import (
    MUSIC_ANALYSIS_API_KEY,
    MUSIC_ANALYSIS_API_URL,
    MUSIC_ANALYSIS_FALLBACK_MODEL,
    MUSIC_ANALYSIS_MAX_AUDIO_BYTES,
    MUSIC_ANALYSIS_MODEL,
    MUSIC_ANALYSIS_PROVIDER,
    MUSIC_ANALYSIS_TIMEOUT_SECONDS,
    MUSIC_PROMPT_VERSION,
)
from storage.music_melody_store import get_music_melody_entry, save_music_melody_entry
from services.music_lyrics import parse_lyrics_text
from utils.log import get_logger

logger = get_logger(__name__)

SUPPORTED_AUDIO_FORMATS = {"mp3", "m4a", "wav", "flac", "aac", "ogg", "aiff"}


class MusicMelodyError(Exception):
    pass


def _clean_text(value: Any, limit: int = 200) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _audio_format(filename: str = "", mime_type: str = "") -> str:
    mt = (mime_type or "").split(";")[0].strip().lower()
    by_mime = {
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/mp4": "m4a",
        "audio/x-m4a": "m4a",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/flac": "flac",
        "audio/aac": "aac",
        "audio/ogg": "ogg",
        "audio/aiff": "aiff",
        "audio/x-aiff": "aiff",
    }
    if mt in by_mime:
        return by_mime[mt]
    guessed, _ = mimetypes.guess_type(filename or "")
    if guessed and guessed.lower() in by_mime:
        return by_mime[guessed.lower()]
    suffix = (filename or "").rsplit(".", 1)[-1].strip().lower() if "." in (filename or "") else ""
    if suffix == "mpeg":
        return "mp3"
    if suffix in SUPPORTED_AUDIO_FORMATS:
        return suffix
    return ""


def _format_duration(seconds: float) -> str:
    if seconds <= 0:
        return ""
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def _format_timestamp(value: Any) -> str:
    try:
        seconds = max(0, int(round(float(value or 0))))
    except (TypeError, ValueError):
        seconds = 0
    minutes, secs = divmod(seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def _clean_lyrics_text(value: Any, limit: int = 4000) -> str:
    raw = str(value or "").replace("\u00a0", " ")
    lines: list[str] = []
    for line in raw.splitlines():
        item = line.strip()
        if not item:
            continue
        if item.startswith("{"):
            tx_parts = re.findall(r'"tx"\s*:\s*"([^"]*)"', item)
            item = "".join(tx_parts).strip()
            if not item or item in {"作词:", "作曲:", "编曲:"}:
                continue
        item = re.sub(r"^\[\d{2}:\d{2}(?:\.\d+)?\]", "", item).strip()
        if item:
            lines.append(item)
    return "\n".join(lines)[:limit]


def _max_segment_end_seconds(structured: dict) -> float:
    segments = structured.get("segments") if isinstance(structured, dict) else None
    if not isinstance(segments, list):
        return 0
    max_end = 0.0
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        try:
            max_end = max(max_end, float(segment.get("end") or 0))
        except (TypeError, ValueError):
            continue
    return max_end


def _display_text_from_segments(data: dict) -> str:
    segments = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(segments, list):
        return ""
    lines: list[str] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        plain = str(segment.get("plain") or "").strip()
        if not plain:
            continue
        start = _format_timestamp(segment.get("start"))
        end = _format_timestamp(segment.get("end"))
        section = _clean_text(segment.get("section") or "段落", 30)
        lines.append(f"{start}-{end} {section}：{plain}")
    trend = str(data.get("overall_trend") or "").strip()
    if lines and trend:
        lines.append(f"整体趋势：{trend}")
    return "\n".join(lines)


def build_music_melody_prompt(
    title: str,
    artist: str,
    duration_seconds: float = 0,
    lyrics_text: str = "",
) -> str:
    song_name = _clean_text(title, 160)
    artist_name = _clean_text(artist, 160)
    duration = float(duration_seconds or 0)
    duration_line = ""
    if duration > 0:
        duration_line = (
            f"\n音频总时长：{duration:.1f} 秒（约 {_format_duration(duration)}）。"
            "所有 start/end 都必须落在这个范围内，不能超过歌曲总时长；最后一段的 end 必须等于这个总时长。"
        )
    lyrics = _clean_lyrics_text(lyrics_text)
    lyrics_block = f"\n\n歌词/文本线索（可能不是逐字逐秒对齐，只作为理解意象参考）：\n{lyrics}" if lyrics else ""
    identity = f"歌名：{song_name}\n歌手：{artist_name or '未知'}{duration_line}"
    return (
        "你在为“和渡一起听”的功能分析歌曲。请先听完整音频，再把它转成渡可以拿来陪小玥一起聊歌的听感素材。\n"
        f"{identity}"
        f"{lyrics_block}\n\n"
        "要求：\n"
        "1. 不要按固定秒数平均切分。先判断歌曲结构，再按结构段落输出。\n"
        "2. 优先识别：前奏、主歌、预副歌、副歌、副歌后段、间奏、桥段、breakdown、最后副歌、尾奏。听不准就写“过渡段/情绪抬升段/收束段”，不要硬编专业名词。\n"
        "3. 每段可以 10-70 秒不等，切点要跟着人声进入、鼓点/低音加入、旋律重复、能量抬升或回落、编曲抽空这些真实变化走；必须覆盖整首歌。\n"
        "4. display_text 是给渡看的自然听感素材：不要对渡说话，不要写“渡，你听”；不要像音乐赏析模板，也不要把 Valence/Arousal 写进正文。\n"
        "5. 每段 plain 写 1-2 句，避免反复复读“人声清晰、鼓点压进来”。重复副歌也要指出这次和上一次有什么不同，或者说明“几乎复现上一轮”。\n"
        "6. 每段重点写听见的变化：人声远近和质感、混响/空间、鼓点和低音什么时候压进来、主旋律怎么抬起/回落、歌词意象怎样被编曲托住。听不准时要保守。\n"
        "7. segments 里的 start/end 是秒数数字，不是 mm:ss；例如 110 秒要写成 110，不要写成 70 或 01:10。\n"
        "8. 输出前自查：第一段 start 必须是 0；后一段 start 应该等于前一段 end；最后一段 end 必须等于音频总时长；任何 start/end 都不能超过总时长。不要根据歌词行数或想象补出音频里不存在的后半段。\n"
        "9. segments 里保留 valence（-5 到 +5）和 arousal（1 到 5）给后台用；正文里不用出现这些数字。\n"
        "10. 只返回一个 JSON 对象，不要 Markdown，不要代码块，不要把 JSON 包成字符串。\n\n"
        "JSON 格式：\n"
        "{\n"
        '  "display_text": "00:00-00:18 前奏：空间先慢慢铺开，人声还在远处，鼓点很克制。\\n00:18-00:52 主歌：...\\n整体趋势：...",\n'
        '  "overall_trend": "从克制的前奏，到副歌被鼓点和人声抬起来，最后慢慢收回。",\n'
        '  "segments": [\n'
        '    {"start":0,"end":18,"section":"前奏","plain":"空间先慢慢铺开，人声还在远处，鼓点很克制。","melody_motion":"缓慢展开","sonic_detail":"人声有距离感，混响明显","intensity":"偏轻","valence":-1,"arousal":2}\n'
        "  ]\n"
        "}"
    )


def _extract_json_object(text: str) -> Optional[dict]:
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


def _display_text_from_structured(data: Optional[dict], fallback: str) -> tuple[str, str]:
    if isinstance(data, dict):
        trend = str(data.get("overall_trend") or "").strip()
        display = _display_text_from_segments(data)
        if display:
            return display, trend
        display = str(data.get("display_text") or "").strip()
        if display:
            return display, trend
    return str(fallback or "").strip(), ""


def parse_music_melody_model_text(text: str) -> tuple[dict, str, str]:
    structured = _extract_json_object(text) or {}
    melody_text, overall_trend = _display_text_from_structured(structured, text)
    return structured, melody_text, overall_trend


def _openrouter_payload(
    model: str,
    title: str,
    artist: str,
    audio_bytes: bytes,
    audio_format: str,
    duration_seconds: float = 0,
    lyrics_text: str = "",
) -> dict:
    return {
        "model": model,
        "stream": False,
        "temperature": 0.2,
        "max_tokens": 2600,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": build_music_melody_prompt(
                            title,
                            artist,
                            duration_seconds=duration_seconds,
                            lyrics_text=lyrics_text,
                        ),
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": base64.b64encode(audio_bytes).decode("ascii"),
                            "format": audio_format,
                        },
                    },
                ],
            }
        ],
    }


def _call_music_model(
    model: str,
    title: str,
    artist: str,
    audio_bytes: bytes,
    audio_format: str,
    duration_seconds: float = 0,
    lyrics_text: str = "",
) -> tuple[str, dict]:
    if not MUSIC_ANALYSIS_API_KEY:
        raise MusicMelodyError("MUSIC_ANALYSIS_API_KEY/OPENROUTER_API_KEY 未配置")
    headers = {
        "Authorization": f"Bearer {MUSIC_ANALYSIS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = _openrouter_payload(
        model,
        title,
        artist,
        audio_bytes,
        audio_format,
        duration_seconds=duration_seconds,
        lyrics_text=lyrics_text,
    )
    try:
        resp = requests.post(
            MUSIC_ANALYSIS_API_URL,
            headers=headers,
            json=payload,
            timeout=max(20, int(MUSIC_ANALYSIS_TIMEOUT_SECONDS or 180)),
        )
    except Exception as e:
        raise MusicMelodyError(f"音乐分析请求失败: {e}") from e
    if resp.status_code >= 400:
        body = (resp.text or "")[:600]
        raise MusicMelodyError(f"音乐分析非 2xx status={resp.status_code} body={body}")
    try:
        data = resp.json()
    except Exception as e:
        raise MusicMelodyError(f"音乐分析响应不是 JSON: {e}") from e
    content = str((((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or "").strip()
    if not content:
        raise MusicMelodyError("音乐分析返回空内容")
    return content, data


def analyze_music_melody(
    title: str,
    artist: str = "",
    audio_bytes: bytes = b"",
    filename: str = "",
    mime_type: str = "",
    force: bool = False,
    model: str = "",
    prompt_version: str = "",
    duration_seconds: float = 0,
    lyrics_text: str = "",
) -> dict:
    clean_title = _clean_text(title, 200)
    clean_artist = _clean_text(artist, 200)
    if not clean_title:
        raise MusicMelodyError("缺少歌名 title")

    use_model = _clean_text(model, 120) or MUSIC_ANALYSIS_MODEL
    use_prompt_version = _clean_text(prompt_version, 40) or MUSIC_PROMPT_VERSION
    provider = MUSIC_ANALYSIS_PROVIDER or "openrouter"

    if not force:
        cached = get_music_melody_entry(clean_title, clean_artist, provider, use_model, use_prompt_version)
        if cached:
            return {"ok": True, "cached": True, "entry": cached}

    if not audio_bytes:
        raise MusicMelodyError("未命中缓存，且缺少可分析音频")
    if len(audio_bytes) > MUSIC_ANALYSIS_MAX_AUDIO_BYTES:
        raise MusicMelodyError(f"音频过大，最大 {MUSIC_ANALYSIS_MAX_AUDIO_BYTES // 1024 // 1024}MB")
    fmt = _audio_format(filename, mime_type)
    if not fmt:
        raise MusicMelodyError("不支持的音频格式，请上传 mp3/m4a/wav/flac/aac/ogg/aiff")

    models = [use_model]
    fallback = _clean_text(MUSIC_ANALYSIS_FALLBACK_MODEL, 120)
    if fallback and fallback not in models:
        models.append(fallback)

    last_error = ""
    for idx, candidate_model in enumerate(models):
        try:
            raw_content, raw_response = _call_music_model(
                candidate_model,
                clean_title,
                clean_artist,
                audio_bytes,
                fmt,
                duration_seconds=duration_seconds,
                lyrics_text=lyrics_text,
            )
            structured, melody_text, overall_trend = parse_music_melody_model_text(raw_content)
            max_end = _max_segment_end_seconds(structured)
            if duration_seconds and max_end > float(duration_seconds) + 2:
                raise MusicMelodyError(f"音乐分析时间段超出音频时长 end={max_end:g}s duration={float(duration_seconds):g}s")
            entry = save_music_melody_entry(
                clean_title,
                clean_artist,
                provider,
                candidate_model,
                use_prompt_version,
                melody_text,
                overall_trend=overall_trend,
                structured=structured,
                lyrics=parse_lyrics_text(lyrics_text, duration_seconds=duration_seconds) if lyrics_text else None,
            )
            if not entry:
                raise MusicMelodyError("音乐分析结果保存失败")
            return {
                "ok": True,
                "cached": False,
                "entry": entry,
                "model": candidate_model,
                "fallback_used": idx > 0,
                "usage": raw_response.get("usage") if isinstance(raw_response, dict) else None,
            }
        except MusicMelodyError as e:
            last_error = str(e)
            logger.warning("音乐分析模型失败 model=%s error=%s", candidate_model, last_error)
            continue
    raise MusicMelodyError(last_error or "音乐分析失败")
