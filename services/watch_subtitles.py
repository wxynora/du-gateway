from __future__ import annotations

import io
import logging
import re
import time
import zipfile
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import requests

from config import (
    WATCH_SUBDL_API_URL,
    WATCH_SUBTITLE_LOOKUP_TIMEOUT_SECONDS,
    WATCH_SUBTITLE_REQUEST_TIMEOUT_SECONDS,
    WATCH_TMDB_API_URL,
)


SUBDL_DOWNLOAD_BASE_URL = "https://dl.subdl.com"
SUPPORTED_TEXT_EXTENSIONS = (".srt", ".vtt")
SUBDL_CANDIDATE_MISS_MESSAGES = (
    "can't find movie or tv",
    "cannot find movie or tv",
    "film name contains potentially unsafe characters",
)
logger = logging.getLogger(__name__)


class SubtitleLookupError(RuntimeError):
    pass


def _response_bytes(response: Any) -> bytes:
    content = bytes(getattr(response, "content", b"") or b"")
    if content:
        return content
    return str(getattr(response, "text", "") or "").encode("utf-8")


def _decode_subtitle(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "gb18030", "cp1252"):
        try:
            return payload.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return payload.decode("utf-8", errors="replace")


def decode_subtitle_bytes(payload: bytes) -> str:
    return _decode_subtitle(bytes(payload or b""))


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


def parse_subtitle_cues(text: str, *, offset_ms: int = 0) -> list[dict]:
    lines = str(text or "").replace("\r\n", "\n").split("\n")
    offset_seconds = int(offset_ms) / 1000.0
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
        if start is not None and end is not None:
            shifted_start = max(0.0, start + offset_seconds)
            shifted_end = max(0.0, end + offset_seconds)
            if shifted_end > shifted_start and content:
                cues.append(
                    {
                        "start": shifted_start,
                        "end": shifted_end,
                        "text": " ".join(content),
                    }
                )
        index += 1
    return cues


def _subtitle_text_from_download(payload: bytes, *, name: str) -> str:
    if not payload:
        return ""
    if not zipfile.is_zipfile(io.BytesIO(payload)):
        return _decode_subtitle(payload)
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            candidates = [
                item
                for item in archive.infolist()
                if not item.is_dir()
                and item.filename.lower().endswith(SUPPORTED_TEXT_EXTENSIONS)
                and item.file_size > 0
            ]
            if not candidates:
                return ""
            preferred_name = str(name or "").lower()
            candidates.sort(
                key=lambda item: (
                    0 if preferred_name and preferred_name in item.filename.lower() else 1,
                    -item.file_size,
                )
            )
            return _decode_subtitle(archive.read(candidates[0]))
    except (OSError, RuntimeError, zipfile.BadZipFile):
        return ""


def _safe_download_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    url = urljoin(SUBDL_DOWNLOAD_BASE_URL + "/", raw)
    if (urlsplit(url).hostname or "").lower() != "dl.subdl.com":
        return ""
    return url


def _candidate_downloads(data: dict) -> list[dict]:
    candidates: list[dict] = []
    seen_urls: set[str] = set()

    def append_candidate(candidate: dict) -> None:
        url = str(candidate.get("url") or "")
        if not url or url in seen_urls:
            return
        seen_urls.add(url)
        candidates.append(candidate)

    for subtitle in data.get("subtitles") if isinstance(data.get("subtitles"), list) else []:
        if not isinstance(subtitle, dict):
            continue
        release_name = str(subtitle.get("release_name") or subtitle.get("name") or "").strip()
        unpack_files = subtitle.get("unpack_files") if isinstance(subtitle.get("unpack_files"), list) else []
        for item in unpack_files:
            if not isinstance(item, dict):
                continue
            extension = "." + str(item.get("format") or "").strip().lower().lstrip(".")
            if extension not in SUPPORTED_TEXT_EXTENSIONS:
                continue
            url = _safe_download_url(item.get("url"))
            if url:
                append_candidate(
                    {
                        "url": url,
                        "name": str(item.get("name") or release_name).strip(),
                        "release_name": release_name,
                        "format": extension.lstrip("."),
                        "language": str(
                            item.get("language")
                            or subtitle.get("language")
                            or subtitle.get("language_code")
                            or ""
                        ).strip(),
                    }
                )
        url = _safe_download_url(subtitle.get("url"))
        if url:
            append_candidate(
                {
                    "url": url,
                    "name": release_name,
                    "release_name": release_name,
                    "format": "zip",
                    "language": str(
                        subtitle.get("language") or subtitle.get("language_code") or ""
                    ).strip(),
                }
            )
    return candidates


def _year_from_media(media: dict) -> int | None:
    try:
        explicit = int(media.get("subtitle_year") or 0)
    except (TypeError, ValueError):
        explicit = 0
    if explicit > 0:
        return explicit
    blob = " ".join(str(media.get(key) or "") for key in ("title", "part_title"))
    match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", blob)
    return int(match.group(1)) if match else None


def _title_candidates(media: dict) -> list[str]:
    configured = media.get("subtitle_titles")
    if isinstance(configured, list):
        values: list[Any] = configured
    else:
        values = [media.get("title")]
    candidates: list[str] = []
    seen: set[str] = set()
    for value in values:
        title = str(value or "").strip()
        key = title.casefold()
        if title and key not in seen:
            seen.add(key)
            candidates.append(title)
    return candidates


def _provider_error_message(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    return str(data.get("error") or data.get("status_message") or data.get("message") or "").strip()


def _is_subdl_candidate_miss(message: str) -> bool:
    normalized = str(message or "").strip().casefold()
    return any(fragment in normalized for fragment in SUBDL_CANDIDATE_MISS_MESSAGES)


def _title_token(value: Any) -> str:
    return "".join(character for character in str(value or "").casefold() if character.isalnum())


def _tmdb_media_types(media: dict) -> tuple[str, ...]:
    configured = str(media.get("subtitle_media_type") or media.get("media_type") or "").strip().casefold()
    if configured in {"movie", "film"}:
        return ("movie",)
    if configured in {"tv", "series", "episode", "show"}:
        return ("tv",)
    if media.get("season") or media.get("episode"):
        return ("tv",)
    return ("movie", "tv")


def resolve_tmdb_identity(
    media: dict,
    *,
    read_access_token: str,
    http_get: Callable[..., Any] = requests.get,
) -> dict:
    token = str(read_access_token or "").strip()
    titles = _title_candidates(media)
    if not token or not titles:
        return {}
    year = _year_from_media(media)
    started_at = time.monotonic()
    deadline = started_at + float(WATCH_SUBTITLE_LOOKUP_TIMEOUT_SECONDS)
    exact_matches: dict[int, dict] = {}
    unique_matches: dict[int, dict] = {}

    def request_timeout() -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SubtitleLookupError("TMDB 作品识别超时")
        return min(float(WATCH_SUBTITLE_REQUEST_TIMEOUT_SECONDS), remaining)

    for title in titles:
        query_token = _title_token(title)
        for media_type in _tmdb_media_types(media):
            params: dict[str, Any] = {
                "query": title,
                "include_adult": "false",
                "language": "zh-CN",
            }
            if year:
                params["primary_release_year" if media_type == "movie" else "first_air_date_year"] = year
            try:
                response = http_get(
                    f"{WATCH_TMDB_API_URL}/search/{media_type}",
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    timeout=request_timeout(),
                )
            except SubtitleLookupError:
                raise
            except Exception as exc:
                raise SubtitleLookupError("TMDB 作品识别请求失败") from exc
            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code in {401, 403}:
                raise SubtitleLookupError("TMDB 鉴权失败")
            if status_code == 429:
                raise SubtitleLookupError("TMDB 请求额度受限")
            if status_code >= 500:
                raise SubtitleLookupError("TMDB 服务暂时不可用")
            if status_code >= 400:
                raise SubtitleLookupError(f"TMDB 作品识别失败: HTTP {status_code}")
            try:
                data = response.json()
            except Exception as exc:
                raise SubtitleLookupError("TMDB 作品识别返回格式错误") from exc
            if not isinstance(data, dict):
                raise SubtitleLookupError("TMDB 作品识别返回格式错误")
            if data.get("success") is False:
                message = _provider_error_message(data)
                raise SubtitleLookupError(f"TMDB 作品识别失败: {message}" if message else "TMDB 作品识别失败")
            results = data.get("results") if isinstance(data.get("results"), list) else []
            valid_results: list[dict] = []
            exact_results: list[dict] = []
            for item in results:
                if not isinstance(item, dict):
                    continue
                try:
                    tmdb_id = int(item.get("id") or 0)
                except (TypeError, ValueError):
                    tmdb_id = 0
                if tmdb_id <= 0:
                    continue
                date_value = str(
                    item.get("release_date") if media_type == "movie" else item.get("first_air_date")
                    or ""
                ).strip()
                if year and (not date_value or not date_value.startswith(f"{year:04d}-")):
                    continue
                normalized = {
                    _title_token(item.get("title")),
                    _title_token(item.get("name")),
                    _title_token(item.get("original_title")),
                    _title_token(item.get("original_name")),
                }
                normalized.discard("")
                match = {
                    "tmdb_id": tmdb_id,
                    "media_type": media_type,
                    "query_title": title,
                    "canonical_title": str(item.get("title") or item.get("name") or "").strip(),
                }
                valid_results.append(match)
                if query_token and query_token in normalized:
                    exact_results.append(match)
            for match in exact_results:
                exact_matches[int(match["tmdb_id"])] = match
            exact_for_query = {int(match["tmdb_id"]): match for match in exact_results}
            if len(exact_for_query) == 1:
                result = next(iter(exact_for_query.values()))
                logger.info(
                    "TMDB 作品识别完成 tmdb_id=%s media_type=%s year=%s elapsed_ms=%s",
                    result["tmdb_id"],
                    result["media_type"],
                    year or 0,
                    round((time.monotonic() - started_at) * 1000),
                )
                return result
            if len(valid_results) == 1:
                match = valid_results[0]
                unique_matches[int(match["tmdb_id"])] = match

    selected = exact_matches if exact_matches else unique_matches
    if len(selected) != 1:
        logger.info(
            "TMDB 作品未唯一命中 titles=%s year=%s matches=%s elapsed_ms=%s",
            len(titles),
            year or 0,
            len(selected),
            round((time.monotonic() - started_at) * 1000),
        )
        return {}
    result = next(iter(selected.values()))
    logger.info(
        "TMDB 作品识别完成 tmdb_id=%s media_type=%s year=%s elapsed_ms=%s",
        result["tmdb_id"],
        result["media_type"],
        year or 0,
        round((time.monotonic() - started_at) * 1000),
    )
    return result


def fetch_subdl_subtitle(
    media: dict,
    *,
    api_key: str,
    http_get: Callable[..., Any] = requests.get,
) -> dict:
    key = str(api_key or "").strip()
    titles = _title_candidates(media)
    try:
        tmdb_id = int(media.get("subtitle_tmdb_id") or 0)
    except (TypeError, ValueError):
        tmdb_id = 0
    if not key or (tmdb_id <= 0 and not titles):
        return {}
    year = _year_from_media(media)
    saw_valid_response = False
    download_failed = False
    started_at = time.monotonic()
    deadline = started_at + float(WATCH_SUBTITLE_LOOKUP_TIMEOUT_SECONDS)

    def request_timeout() -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SubtitleLookupError("SubDL 字幕准备超时")
        return min(float(WATCH_SUBTITLE_REQUEST_TIMEOUT_SECONDS), remaining)

    if tmdb_id > 0:
        query_specs = [
            {
                "params": {"tmdb_id": tmdb_id},
                "query_title": str(media.get("subtitle_query_title") or (titles[0] if titles else "")).strip(),
            }
        ]
    else:
        query_specs = [
            {"params": {"film_name": title}, "query_title": title}
            for title in titles
        ]

    for query in query_specs:
        title = str(query.get("query_title") or "").strip()
        params: dict[str, Any] = {
            "api_key": key,
            "unpack": 1,
            "client": "custom_integration",
            **(query.get("params") if isinstance(query.get("params"), dict) else {}),
        }
        media_type = str(media.get("subtitle_media_type") or "").strip().casefold()
        if tmdb_id > 0 and media_type in {"movie", "tv"}:
            params["type"] = media_type
        if year and "film_name" in params:
            params["year"] = year
        try:
            response = http_get(
                WATCH_SUBDL_API_URL,
                params=params,
                headers={"Accept": "application/json"},
                timeout=request_timeout(),
            )
        except SubtitleLookupError:
            raise
        except Exception as exc:
            raise SubtitleLookupError("SubDL 查询请求失败") from exc
        status_code = int(getattr(response, "status_code", 0) or 0)
        try:
            data = response.json()
        except Exception as exc:
            if status_code >= 400:
                raise SubtitleLookupError(f"SubDL 查询失败: HTTP {status_code}") from exc
            raise SubtitleLookupError("SubDL 查询返回格式错误") from exc
        error_message = _provider_error_message(data)
        if _is_subdl_candidate_miss(error_message):
            logger.info(
                "SubDL 字幕候选未命中 title=%r tmdb_id=%s status=%s elapsed_ms=%s",
                title,
                tmdb_id,
                status_code,
                round((time.monotonic() - started_at) * 1000),
            )
            continue
        if status_code in {401, 403}:
            raise SubtitleLookupError("SubDL 鉴权失败")
        if status_code == 429:
            raise SubtitleLookupError("SubDL 请求额度受限")
        if status_code >= 500:
            raise SubtitleLookupError("SubDL 服务暂时不可用")
        if status_code >= 400:
            raise SubtitleLookupError(f"SubDL 查询失败: HTTP {status_code}")
        if not isinstance(data, dict):
            raise SubtitleLookupError("SubDL 查询返回格式错误")
        if data.get("status") is not True:
            lowered_error = error_message.casefold()
            if any(fragment in lowered_error for fragment in ("api key", "unauthorized", "authentication")):
                raise SubtitleLookupError("SubDL 鉴权失败")
            if any(fragment in lowered_error for fragment in ("quota", "rate limit", "too many requests")):
                raise SubtitleLookupError("SubDL 请求额度受限")
            raise SubtitleLookupError(
                f"SubDL 查询返回失败状态: {error_message}"
                if error_message
                else "SubDL 查询返回失败状态"
            )
        saw_valid_response = True
        candidates = _candidate_downloads(data)
        logger.info(
            "SubDL 字幕搜索完成 title=%r tmdb_id=%s year=%s candidates=%s elapsed_ms=%s",
            title,
            tmdb_id,
            year or 0,
            len(candidates),
            round((time.monotonic() - started_at) * 1000),
        )
        for attempt, candidate in enumerate(candidates, start=1):
            try:
                response = http_get(
                    candidate["url"],
                    headers={"Accept": "application/octet-stream"},
                    timeout=request_timeout(),
                )
            except SubtitleLookupError:
                raise
            except Exception:
                download_failed = True
                logger.warning(
                    "SubDL 字幕候选下载失败 title=%r attempt=%s elapsed_ms=%s",
                    title,
                    attempt,
                    round((time.monotonic() - started_at) * 1000),
                )
                continue
            if int(getattr(response, "status_code", 0) or 0) >= 400:
                download_failed = True
                logger.warning(
                    "SubDL 字幕候选返回失败 title=%r attempt=%s status=%s elapsed_ms=%s",
                    title,
                    attempt,
                    int(getattr(response, "status_code", 0) or 0),
                    round((time.monotonic() - started_at) * 1000),
                )
                continue
            text = _subtitle_text_from_download(
                _response_bytes(response),
                name=str(candidate.get("name") or ""),
            )
            if "-->" in text:
                logger.info(
                    "SubDL 字幕准备完成 title=%r attempt=%s elapsed_ms=%s",
                    title,
                    attempt,
                    round((time.monotonic() - started_at) * 1000),
                )
                return {
                    "text": text,
                    "query_title": title,
                    "release_name": str(candidate.get("release_name") or ""),
                    "format": str(candidate.get("format") or ""),
                    "language": str(candidate.get("language") or ""),
                }
    if saw_valid_response and download_failed:
        raise SubtitleLookupError("SubDL 找到字幕但下载或解析失败")
    logger.info(
        "SubDL 字幕未命中 titles=%s tmdb_id=%s year=%s elapsed_ms=%s",
        len(titles),
        tmdb_id,
        year or 0,
        round((time.monotonic() - started_at) * 1000),
    )
    return {}


def fetch_subdl_subtitle_text(
    media: dict,
    *,
    api_key: str,
    http_get: Callable[..., Any] = requests.get,
) -> str:
    return str(
        fetch_subdl_subtitle(media, api_key=api_key, http_get=http_get).get("text") or ""
    )
