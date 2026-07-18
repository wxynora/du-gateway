from __future__ import annotations

import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

import requests

from config import (
    WATCH_ANALYSIS_BILIBILI_COOKIE,
    WATCH_ANALYSIS_FFMPEG_BIN,
    WATCH_ANALYSIS_SOURCE_CACHE_SECONDS,
    WATCH_ANALYSIS_SOURCE_ENABLED,
    WATCH_ANALYSIS_SOURCE_MAX_HEIGHT,
    WATCH_ANALYSIS_SOURCE_MAX_WORKERS,
    WATCH_ANALYSIS_SOURCE_PROVIDER,
    WATCH_ANALYSIS_SOURCE_TIMEOUT_SECONDS,
    WATCH_ANALYSIS_SOURCE_USER_AGENT,
)


BVID_RE = re.compile(r"(?i)BV[0-9A-Za-z]{10}")
MEDIA_ID_RE = re.compile(r"(?i)^bili:(BV[0-9A-Za-z]{10}):p([1-9][0-9]*)$")
BILIBILI_VIEW_API = "https://api.bilibili.com/x/web-interface/view"
BILIBILI_PLAYURL_API = "https://api.bilibili.com/x/player/playurl"
BILIBILI_PLAYER_API = "https://api.bilibili.com/x/player/v2"


class WatchAnalysisSourceError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = bool(retryable)


def canonical_bilibili_url(media: dict) -> tuple[str, str, int]:
    media_id = str(media.get("id") or "").strip()
    match = MEDIA_ID_RE.fullmatch(media_id)
    if match:
        bvid = "BV" + match.group(1)[2:]
        page = max(1, int(match.group(2)))
        return f"https://www.bilibili.com/video/{bvid}?p={page}", bvid, page

    raw_url = str(media.get("url") or "").strip()
    parsed = urlparse(raw_url)
    host = str(parsed.hostname or "").lower()
    if host != "player.bilibili.com" and host != "www.bilibili.com":
        raise WatchAnalysisSourceError("当前分析源只支持 Bilibili 公开分享视频", retryable=False)
    bvid_match = BVID_RE.search(raw_url)
    if not bvid_match:
        raise WatchAnalysisSourceError("Bilibili 媒体缺少可解析的 BVID", retryable=False)
    bvid = "BV" + bvid_match.group(0)[2:]
    page_match = re.search(r"(?:[?&]|\b)(?:p|page)=([1-9][0-9]*)", raw_url, flags=re.I)
    page = int(page_match.group(1)) if page_match else 1
    return f"https://www.bilibili.com/video/{bvid}?p={page}", bvid, page


def _clean_header(value: Any, limit: int = 1000) -> str:
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()[:limit]


def _timestamp_seconds(value: str) -> float | None:
    normalized = str(value or "").strip().replace(",", ".")
    parts = normalized.split(":")
    if len(parts) not in {2, 3}:
        return None
    try:
        seconds = float(parts[-1])
        minutes = int(parts[-2])
        hours = int(parts[-3]) if len(parts) == 3 else 0
    except (TypeError, ValueError):
        return None
    return max(0.0, hours * 3600 + minutes * 60 + seconds)


def _subtitle_cues_from_text(text: str) -> list[dict]:
    lines = str(text or "").replace("\r\n", "\n").split("\n")
    cues: list[dict] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if "-->" not in line:
            index += 1
            continue
        left, right = (part.strip().split(" ", 1)[0] for part in line.split("-->", 1))
        start = _timestamp_seconds(left)
        end = _timestamp_seconds(right)
        index += 1
        content: list[str] = []
        while index < len(lines) and lines[index].strip():
            cleaned = re.sub(r"<[^>]+>", "", lines[index]).strip()
            if cleaned:
                content.append(cleaned)
            index += 1
        if start is not None and end is not None and end > start and content:
            cues.append({"start": start, "end": end, "text": " ".join(content)[:1000]})
        index += 1
    return cues


def _subtitle_cues(response: Any) -> list[dict]:
    try:
        payload = response.json()
    except Exception:
        return _subtitle_cues_from_text(str(getattr(response, "text", "") or ""))
    if not isinstance(payload, dict):
        return []
    body = payload.get("body")
    if not isinstance(body, list) and isinstance(payload.get("data"), dict):
        body = payload["data"].get("body")
    if not isinstance(body, list):
        return []
    cues: list[dict] = []
    for item in body:
        if not isinstance(item, dict):
            continue
        try:
            start = max(0.0, float(item.get("from") or item.get("start") or 0))
            end = max(0.0, float(item.get("to") or item.get("end") or 0))
        except (TypeError, ValueError):
            continue
        content = str(item.get("content") or item.get("text") or "").strip()[:1000]
        if content and end > start:
            cues.append({"start": start, "end": end, "text": content})
    return cues


def _subtitle_at(cues: list[dict], at_ms: int) -> str:
    at_seconds = max(0.0, int(at_ms) / 1000.0)
    texts = [
        str(cue.get("text") or "").strip()
        for cue in cues
        if float(cue.get("start") or 0) - 0.2 <= at_seconds <= float(cue.get("end") or 0) + 0.2
    ]
    return " ".join(dict.fromkeys(text for text in texts if text))[:2000]


class BilibiliApiAnalysisSource:
    def __init__(
        self,
        *,
        command_runner: Callable[..., Any] = subprocess.run,
        http_get: Callable[..., Any] | None = None,
        ffmpeg_bin: str = "",
        max_workers: int | None = None,
        cookie: str | None = None,
    ) -> None:
        self._command_runner = command_runner
        self._http_session = requests.Session() if http_get is None else None
        self._http_get = http_get or self._http_session.get
        self._ffmpeg_bin = ffmpeg_bin
        self._max_workers = max(1, min(4, int(max_workers or WATCH_ANALYSIS_SOURCE_MAX_WORKERS)))
        self._cookie = _clean_header(
            WATCH_ANALYSIS_BILIBILI_COOKIE if cookie is None else cookie,
            4096,
        )
        self._cache: dict[str, tuple[float, dict]] = {}

    def _api_data(self, url: str, *, params: dict, headers: dict, label: str) -> dict:
        try:
            response = self._http_get(
                url,
                params=params,
                headers=headers,
                timeout=int(WATCH_ANALYSIS_SOURCE_TIMEOUT_SECONDS),
            )
        except Exception as exc:
            raise WatchAnalysisSourceError(f"Bilibili {label}请求失败", retryable=True) from exc
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code >= 400:
            raise WatchAnalysisSourceError(
                f"Bilibili {label}请求失败: HTTP {status_code}",
                retryable=status_code not in {400, 404},
            )
        try:
            payload = response.json()
        except Exception as exc:
            raise WatchAnalysisSourceError(f"Bilibili {label}返回格式错误", retryable=True) from exc
        if not isinstance(payload, dict):
            raise WatchAnalysisSourceError(f"Bilibili {label}返回格式错误", retryable=True)
        code = int(payload.get("code") or 0)
        if code != 0:
            message = _clean_header(payload.get("message") or payload.get("msg"), 160)
            suffix = f": {message}" if message else f": code={code}"
            raise WatchAnalysisSourceError(
                f"Bilibili {label}失败{suffix}",
                retryable=code not in {-400, -403, -404, 62002, 62004},
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise WatchAnalysisSourceError(f"Bilibili {label}缺少数据", retryable=True)
        return data

    def _api_data_with_auth_fallback(
        self,
        url: str,
        *,
        params: dict,
        headers: dict,
        label: str,
    ) -> tuple[dict, dict]:
        try:
            return self._api_data(url, params=params, headers=headers, label=label), headers
        except WatchAnalysisSourceError:
            if not self._cookie or headers.get("Cookie"):
                raise
        authenticated_headers = {**headers, "Cookie": self._cookie}
        return (
            self._api_data(
                url,
                params=params,
                headers=authenticated_headers,
                label=label,
            ),
            authenticated_headers,
        )

    def _ffmpeg(self) -> str:
        candidate = self._ffmpeg_bin or WATCH_ANALYSIS_FFMPEG_BIN or shutil.which("ffmpeg") or ""
        if not candidate:
            raise WatchAnalysisSourceError("后端未安装 ffmpeg", retryable=False)
        return candidate

    @staticmethod
    def _page_info(view_data: dict, page: int) -> dict:
        pages = view_data.get("pages")
        if not isinstance(pages, list):
            pages = []
        for item in pages:
            if isinstance(item, dict) and int(item.get("page") or 0) == page:
                return item
        if page == 1 and not pages and int(view_data.get("cid") or 0) > 0:
            return {
                "cid": view_data["cid"],
                "page": 1,
                "duration": view_data.get("duration"),
                "part": view_data.get("title"),
            }
        raise WatchAnalysisSourceError("Bilibili 视频不存在这个分 P", retryable=False)

    @staticmethod
    def _stream_urls(item: dict) -> list[str]:
        values: list[Any] = [
            item.get("baseUrl"),
            item.get("base_url"),
            item.get("url"),
        ]
        for key in ("backupUrl", "backup_url"):
            backup = item.get(key)
            if isinstance(backup, list):
                values.extend(backup)
            elif backup:
                values.append(backup)
        urls: list[str] = []
        for value in values:
            url = str(value or "").strip()
            if url.startswith(("https://", "http://")) and url not in urls:
                urls.append(url)
        return urls

    @staticmethod
    def _pick_stream_urls(play_data: dict) -> list[str]:
        dash = play_data.get("dash")
        videos = dash.get("video") if isinstance(dash, dict) else None
        candidates = [item for item in videos or [] if isinstance(item, dict)]
        if candidates:
            max_edge = int(WATCH_ANALYSIS_SOURCE_MAX_HEIGHT)

            def score(item: dict) -> tuple[int, int, int, float]:
                width = max(0, int(item.get("width") or 0))
                height = max(0, int(item.get("height") or 0))
                short_edge = min(value for value in (width, height) if value > 0) if width or height else 0
                fits = bool(short_edge and short_edge <= max_edge)
                codec = str(item.get("codecs") or item.get("codecid") or "").lower()
                is_avc = "avc" in codec or codec in {"7", ""}
                resolution_score = short_edge if fits else -short_edge
                return int(fits), int(is_avc), resolution_score, -float(item.get("bandwidth") or 0)

            urls = BilibiliApiAnalysisSource._stream_urls(max(candidates, key=score))
            if urls:
                return urls

        durl = [item for item in play_data.get("durl") or [] if isinstance(item, dict)]
        if len(durl) == 1:
            urls = BilibiliApiAnalysisSource._stream_urls(durl[0])
            if urls:
                return urls
        raise WatchAnalysisSourceError("Bilibili 没有返回可读取的视频流", retryable=True)

    def _load_subtitles(self, *, bvid: str, cid: int, headers: dict) -> list[dict]:
        try:
            player_data, subtitle_headers = self._api_data_with_auth_fallback(
                BILIBILI_PLAYER_API,
                params={"bvid": bvid, "cid": cid},
                headers=headers,
                label="字幕信息",
            )
        except WatchAnalysisSourceError:
            return []
        subtitle = player_data.get("subtitle")
        tracks = subtitle.get("subtitles") if isinstance(subtitle, dict) else None
        tracks = [item for item in tracks or [] if isinstance(item, dict)]
        if not tracks and self._cookie and not subtitle_headers.get("Cookie"):
            subtitle_headers = {**headers, "Cookie": self._cookie}
            try:
                player_data = self._api_data(
                    BILIBILI_PLAYER_API,
                    params={"bvid": bvid, "cid": cid},
                    headers=subtitle_headers,
                    label="字幕信息",
                )
            except WatchAnalysisSourceError:
                return []
            subtitle = player_data.get("subtitle")
            tracks = subtitle.get("subtitles") if isinstance(subtitle, dict) else None
            tracks = [item for item in tracks or [] if isinstance(item, dict)]
        if not tracks:
            return []
        tracks.sort(
            key=lambda item: (
                0
                if re.search(
                    r"zh|cn|hans|chs",
                    str(item.get("lan") or item.get("lan_doc") or ""),
                    flags=re.I,
                )
                else 1,
                1 if int(item.get("type") or 0) else 0,
            )
        )
        subtitle_url = str(tracks[0].get("subtitle_url") or tracks[0].get("url") or "").strip()
        if subtitle_url.startswith("//"):
            subtitle_url = "https:" + subtitle_url
        if not subtitle_url.startswith(("https://", "http://")):
            return []
        try:
            response = self._http_get(
                subtitle_url,
                headers=subtitle_headers,
                timeout=int(WATCH_ANALYSIS_SOURCE_TIMEOUT_SECONDS),
            )
            if int(getattr(response, "status_code", 0) or 0) >= 400:
                return []
            return _subtitle_cues(response)
        except Exception:
            return []

    def _resolve(self, media: dict) -> dict:
        canonical_url, bvid, page = canonical_bilibili_url(media)
        cache_key = f"{bvid}:p{page}"
        cached = self._cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        headers = {
            "User-Agent": _clean_header(WATCH_ANALYSIS_SOURCE_USER_AGENT),
            "Referer": canonical_url,
            "Origin": "https://www.bilibili.com",
        }
        view_data, request_headers = self._api_data_with_auth_fallback(
            BILIBILI_VIEW_API,
            params={"bvid": bvid},
            headers=headers,
            label="视频信息",
        )
        page_info = self._page_info(view_data, page)
        cid = int(page_info.get("cid") or 0)
        if cid <= 0:
            raise WatchAnalysisSourceError("Bilibili 分 P 缺少 CID", retryable=True)
        play_data, request_headers = self._api_data_with_auth_fallback(
            BILIBILI_PLAYURL_API,
            params={
                "bvid": bvid,
                "cid": cid,
                "qn": 64,
                "fnval": 16,
                "fnver": 0,
                "fourk": 0,
            },
            headers=request_headers,
            label="播放地址",
        )
        resolved = {
            "stream_urls": self._pick_stream_urls(play_data),
            "headers": request_headers,
            "subtitles": self._load_subtitles(bvid=bvid, cid=cid, headers=request_headers),
            "canonical_url": canonical_url,
            "cid": cid,
        }
        self._cache[cache_key] = (
            time.monotonic() + int(WATCH_ANALYSIS_SOURCE_CACHE_SECONDS),
            resolved,
        )
        return resolved

    def _extract_frame(self, resolved: dict, at_ms: int) -> bytes:
        headers = resolved.get("headers") if isinstance(resolved.get("headers"), dict) else {}
        header_lines = [
            f"{_clean_header(name, 80)}: {_clean_header(value)}"
            for name, value in headers.items()
            if _clean_header(name, 80) and _clean_header(value)
        ]
        header_blob = "\r\n".join(header_lines) + "\r\n\r\n" if header_lines else ""
        stream_urls = [
            str(value).strip()
            for value in resolved.get("stream_urls") or []
            if str(value).strip().startswith(("https://", "http://"))
        ]
        if not stream_urls:
            raise WatchAnalysisSourceError("Bilibili 没有可用于取帧的视频流", retryable=True)
        for stream_url in stream_urls:
            command = [
                self._ffmpeg(),
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{max(0, int(at_ms)) / 1000.0:.3f}",
            ]
            if header_blob:
                command.extend(["-headers", header_blob])
            command.extend(
                [
                    "-i",
                    stream_url,
                    "-map",
                    "0:v:0",
                    "-frames:v",
                    "1",
                    "-vf",
                    f"scale={int(WATCH_ANALYSIS_SOURCE_MAX_HEIGHT)}:-2:force_original_aspect_ratio=decrease",
                    "-f",
                    "image2pipe",
                    "-vcodec",
                    "mjpeg",
                    "pipe:1",
                ]
            )
            try:
                completed = self._command_runner(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=int(WATCH_ANALYSIS_SOURCE_TIMEOUT_SECONDS),
                    check=False,
                )
            except Exception:
                continue
            output = bytes(getattr(completed, "stdout", b"") or b"")
            if int(getattr(completed, "returncode", 1) or 0) == 0 and output:
                return output
        raise WatchAnalysisSourceError("视频关键帧提取失败", retryable=True)

    def acquire(self, session: dict, *, purpose: str, timestamps_ms: list[int]) -> list[dict]:
        media = session.get("media") if isinstance(session.get("media"), dict) else {}
        if str(media.get("source") or "") != "bilibili_embed":
            raise WatchAnalysisSourceError("当前分析源不支持这个播放来源", retryable=False)
        duration_ms = max(0, int(media.get("duration_ms") or 0))
        targets = sorted(
            {
                min(duration_ms, max(0, int(value))) if duration_ms else max(0, int(value))
                for value in timestamps_ms
            }
        )
        if not targets:
            raise WatchAnalysisSourceError("后端分析计划没有目标时间", retryable=False)
        resolved = self._resolve(media)
        captured_at = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            with ThreadPoolExecutor(max_workers=min(self._max_workers, len(targets))) as executor:
                frames = list(executor.map(lambda at_ms: self._extract_frame(resolved, at_ms), targets))
        except WatchAnalysisSourceError:
            _canonical_url, bvid, page = canonical_bilibili_url(media)
            self._cache.pop(f"{bvid}:p{page}", None)
            raise
        return [
            {
                "at_ms": at_ms,
                "mime_type": "image/jpeg",
                "image_bytes": frame,
                "subtitle": _subtitle_at(resolved.get("subtitles") or [], at_ms),
                "captured_at": captured_at,
            }
            for at_ms, frame in zip(targets, frames)
        ]


_SOURCE: BilibiliApiAnalysisSource | None = None


def get_watch_analysis_source() -> BilibiliApiAnalysisSource:
    global _SOURCE
    if str(WATCH_ANALYSIS_SOURCE_PROVIDER or "").lower() != "bilibili_api":
        raise WatchAnalysisSourceError(
            f"不支持的分析源 provider: {WATCH_ANALYSIS_SOURCE_PROVIDER}",
            retryable=False,
        )
    if _SOURCE is None:
        _SOURCE = BilibiliApiAnalysisSource()
    return _SOURCE


def watch_analysis_source_health() -> dict:
    ffmpeg = WATCH_ANALYSIS_FFMPEG_BIN or shutil.which("ffmpeg") or ""
    return {
        "enabled": bool(WATCH_ANALYSIS_SOURCE_ENABLED),
        "provider": str(WATCH_ANALYSIS_SOURCE_PROVIDER or ""),
        "public_api": True,
        "authenticated_fallback_configured": bool(WATCH_ANALYSIS_BILIBILI_COOKIE),
        "ffmpeg_available": bool(ffmpeg),
        "ready": bool(
            WATCH_ANALYSIS_SOURCE_ENABLED
            and str(WATCH_ANALYSIS_SOURCE_PROVIDER or "").lower() == "bilibili_api"
            and ffmpeg
        ),
    }
