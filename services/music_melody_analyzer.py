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


def build_music_melody_prompt(title: str, artist: str) -> str:
    song_name = _clean_text(title, 160)
    artist_name = _clean_text(artist, 160)
    identity = f"歌名：{song_name}\n歌手：{artist_name or '未知'}"
    return (
        "你在为一个“和渡一起听”的功能分析歌曲。请听完整音频，把它转成 LLM 和普通人都能理解的旋律/情绪描述。\n"
        f"{identity}\n\n"
        "要求：\n"
        "1. 按 10-25 秒左右切段；如果歌曲结构明显变化，可以自然调整切点。\n"
        "2. 每段用中文人话描述听感，不要堆乐理术语；可以写“慢慢铺开”“被提起来”“回落”“更亮”“更闷”。\n"
        "3. 每段都给 Valence（-5 到 +5，负数偏低落，正数偏明亮）和 Arousal（1 到 5，越高越激动）。\n"
        "4. 重点描述主旋律/人声旋律的走势、力度变化和情绪变化；听不准时要保守，不要装作精确扒谱。\n"
        "5. 只返回一个 JSON 对象，不要 Markdown，不要代码块。\n\n"
        "JSON 格式：\n"
        "{\n"
        '  "display_text": "0-18s：像是在慢慢铺开，情绪偏安静，力度轻，Valence:-1，Arousal:2\\n...\\n整体趋势：...",\n'
        '  "overall_trend": "从平静铺垫到情绪上扬，再慢慢回落。",\n'
        '  "segments": [\n'
        '    {"start":0,"end":18,"plain":"像是在慢慢铺开，情绪偏安静，力度轻。","melody_motion":"平稳","intensity":"偏轻","valence":-1,"arousal":2}\n'
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
        display = str(data.get("display_text") or "").strip()
        trend = str(data.get("overall_trend") or "").strip()
        if display:
            return display, trend
    return str(fallback or "").strip(), ""


def parse_music_melody_model_text(text: str) -> tuple[dict, str, str]:
    structured = _extract_json_object(text) or {}
    melody_text, overall_trend = _display_text_from_structured(structured, text)
    return structured, melody_text, overall_trend


def _openrouter_payload(model: str, title: str, artist: str, audio_bytes: bytes, audio_format: str) -> dict:
    return {
        "model": model,
        "stream": False,
        "temperature": 0.2,
        "max_tokens": 1800,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": build_music_melody_prompt(title, artist)},
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


def _call_music_model(model: str, title: str, artist: str, audio_bytes: bytes, audio_format: str) -> tuple[str, dict]:
    if not MUSIC_ANALYSIS_API_KEY:
        raise MusicMelodyError("MUSIC_ANALYSIS_API_KEY/OPENROUTER_API_KEY 未配置")
    headers = {
        "Authorization": f"Bearer {MUSIC_ANALYSIS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = _openrouter_payload(model, title, artist, audio_bytes, audio_format)
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
            raw_content, raw_response = _call_music_model(candidate_model, clean_title, clean_artist, audio_bytes, fmt)
            structured, melody_text, overall_trend = parse_music_melody_model_text(raw_content)
            entry = save_music_melody_entry(
                clean_title,
                clean_artist,
                provider,
                candidate_model,
                use_prompt_version,
                melody_text,
                overall_trend=overall_trend,
                structured=structured,
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
