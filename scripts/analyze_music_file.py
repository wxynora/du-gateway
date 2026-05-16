#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config import (  # noqa: E402
    MAIN_GATEWAY_BASE_URL,
    MAIN_GATEWAY_BEARER_TOKEN,
    MUSIC_ANALYSIS_API_KEY,
    MUSIC_ANALYSIS_API_URL,
    MUSIC_ANALYSIS_MAX_AUDIO_BYTES,
    MUSIC_ANALYSIS_MODEL,
    MUSIC_ANALYSIS_PROVIDER,
    MUSIC_ANALYSIS_TIMEOUT_SECONDS,
    MUSIC_PROMPT_VERSION,
)
from services.music_melody_analyzer import (  # noqa: E402
    SUPPORTED_AUDIO_FORMATS,
    build_music_melody_prompt,
    parse_music_melody_model_text,
)


def _audio_format(path: Path, mime_type: str = "") -> str:
    mt = (mime_type or "").split(";", 1)[0].strip().lower()
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
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed and guessed.lower() in by_mime:
        return by_mime[guessed.lower()]
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "mpeg":
        return "mp3"
    return suffix if suffix in SUPPORTED_AUDIO_FORMATS else ""


def _post_json(url: str, payload: dict, token: str = "", timeout: int = 60) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"POST {url} failed status={resp.status_code} body={(resp.text or '')[:600]}")
    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"POST {url} did not return JSON: {e}") from e
    if not data.get("ok"):
        raise RuntimeError(str(data.get("error") or data))
    return data


def _get_json(url: str, token: str = "", timeout: int = 30) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, headers=headers, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"GET {url} failed status={resp.status_code} body={(resp.text or '')[:600]}")
    return resp.json()


def _analyze_with_openrouter(
    audio_path: Path,
    title: str,
    artist: str,
    model: str,
    api_url: str,
    api_key: str,
    mime_type: str = "",
) -> tuple[dict, dict]:
    if not api_key:
        raise RuntimeError("MUSIC_ANALYSIS_API_KEY 或 OPENROUTER_API_KEY 未配置")
    audio_format = _audio_format(audio_path, mime_type)
    if not audio_format:
        raise RuntimeError("不支持的音频格式，请使用 mp3/m4a/wav/flac/aac/ogg/aiff")
    audio_bytes = audio_path.read_bytes()
    if not audio_bytes:
        raise RuntimeError("音频文件为空")
    if len(audio_bytes) > MUSIC_ANALYSIS_MAX_AUDIO_BYTES:
        mb = MUSIC_ANALYSIS_MAX_AUDIO_BYTES // 1024 // 1024
        raise RuntimeError(f"音频过大，最大 {mb}MB")

    payload = {
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
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=max(20, int(MUSIC_ANALYSIS_TIMEOUT_SECONDS or 180)),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"music model failed status={resp.status_code} body={(resp.text or '')[:600]}")
    data = resp.json()
    content = str((((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or "").strip()
    if not content:
        raise RuntimeError("music model returned empty content")
    structured, melody_text, overall_trend = parse_music_melody_model_text(content)
    if not melody_text:
        raise RuntimeError("music model result has no display text")
    result = {
        "title": title,
        "artist": artist,
        "provider": MUSIC_ANALYSIS_PROVIDER or "openrouter",
        "model": model,
        "prompt_version": MUSIC_PROMPT_VERSION,
        "melody_text": melody_text,
        "overall_trend": overall_trend,
        "structured": structured,
    }
    return result, data


def _write_output(path: Optional[Path], data: dict) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="本地分析音乐文件，并把旋律文字结果写入网关缓存")
    parser.add_argument("audio", type=Path, help="本地音频文件，支持 mp3/m4a/wav/flac/aac/ogg/aiff")
    parser.add_argument("--title", required=True, help="歌名")
    parser.add_argument("--artist", default="", help="歌手")
    parser.add_argument("--model", default=MUSIC_ANALYSIS_MODEL, help="OpenRouter 模型")
    parser.add_argument("--api-url", default=MUSIC_ANALYSIS_API_URL, help="OpenRouter chat completions URL")
    parser.add_argument("--api-key", default=MUSIC_ANALYSIS_API_KEY, help="OpenRouter API key")
    parser.add_argument("--mime-type", default="", help="手动指定音频 MIME type")
    parser.add_argument("--gateway-url", default=MAIN_GATEWAY_BASE_URL, help="网关 base URL")
    parser.add_argument("--gateway-token", default=MAIN_GATEWAY_BEARER_TOKEN, help="网关 Bearer token，可空")
    parser.add_argument("--provider", default=MUSIC_ANALYSIS_PROVIDER, help="缓存 provider 字段")
    parser.add_argument("--prompt-version", default=MUSIC_PROMPT_VERSION, help="缓存 prompt_version 字段")
    parser.add_argument("--out", type=Path, default=None, help="把分析结果另存为 JSON")
    parser.add_argument("--no-upload", action="store_true", help="只输出本地结果，不写入网关")
    parser.add_argument("--force", action="store_true", help="跳过网关缓存命中检查，强制重新分析")
    args = parser.parse_args()

    audio_path = args.audio.expanduser().resolve()
    if not audio_path.exists():
        raise SystemExit(f"音频文件不存在: {audio_path}")
    gateway_base = str(args.gateway_url or "").strip().rstrip("/")
    gateway_token = str(args.gateway_token or "").strip()
    title = str(args.title or "").strip()
    artist = str(args.artist or "").strip()
    model = str(args.model or MUSIC_ANALYSIS_MODEL).strip()
    provider = str(args.provider or MUSIC_ANALYSIS_PROVIDER or "openrouter").strip()
    prompt_version = str(args.prompt_version or MUSIC_PROMPT_VERSION).strip()

    if gateway_base and not args.no_upload and not args.force:
        from urllib.parse import urlencode

        query = urlencode(
            {
                "title": title,
                "artist": artist,
                "provider": provider,
                "model": model,
                "prompt_version": prompt_version,
            }
        )
        cache = _get_json(f"{gateway_base}/api/music/listen/cache?{query}", token=gateway_token)
        if cache.get("hit") and cache.get("entry"):
            print(json.dumps({"ok": True, "cached": True, "entry": cache["entry"]}, ensure_ascii=False, indent=2))
            return 0

    result, raw_response = _analyze_with_openrouter(
        audio_path=audio_path,
        title=title,
        artist=artist,
        model=model,
        api_url=str(args.api_url or MUSIC_ANALYSIS_API_URL).strip(),
        api_key=str(args.api_key or "").strip(),
        mime_type=str(args.mime_type or "").strip(),
    )
    result["provider"] = provider
    result["prompt_version"] = prompt_version
    payload: dict[str, Any] = {"ok": True, "cached": False, "result": result, "usage": raw_response.get("usage")}

    if not args.no_upload:
        if not gateway_base:
            raise SystemExit("未配置 gateway URL；可传 --gateway-url 或加 --no-upload")
        uploaded = _post_json(f"{gateway_base}/api/music/listen/result", result, token=gateway_token)
        payload["uploaded"] = True
        payload["entry"] = uploaded.get("entry")
    else:
        payload["uploaded"] = False

    _write_output(args.out, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
