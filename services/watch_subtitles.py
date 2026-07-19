from __future__ import annotations

import io
import re
import zipfile
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import requests

from config import WATCH_ANALYSIS_SOURCE_TIMEOUT_SECONDS, WATCH_SUBDL_API_URL


SUBDL_DOWNLOAD_BASE_URL = "https://dl.subdl.com"
SUPPORTED_TEXT_EXTENSIONS = (".srt", ".vtt")


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
                candidates.append(
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
            candidates.append(
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


def fetch_subdl_subtitle(
    media: dict,
    *,
    api_key: str,
    http_get: Callable[..., Any] = requests.get,
) -> dict:
    key = str(api_key or "").strip()
    titles = _title_candidates(media)
    if not key or not titles:
        return {}
    year = _year_from_media(media)
    saw_valid_response = False
    download_failed = False
    for title in titles:
        params: dict[str, Any] = {
            "api_key": key,
            "film_name": title,
            "unpack": 1,
            "client": "custom_integration",
        }
        if year:
            params["year"] = year
        try:
            response = http_get(
                WATCH_SUBDL_API_URL,
                params=params,
                headers={"Accept": "application/json"},
                timeout=int(WATCH_ANALYSIS_SOURCE_TIMEOUT_SECONDS),
            )
        except Exception as exc:
            raise SubtitleLookupError("SubDL 查询请求失败") from exc
        if int(getattr(response, "status_code", 0) or 0) >= 400:
            raise SubtitleLookupError(
                f"SubDL 查询失败: HTTP {int(getattr(response, 'status_code', 0) or 0)}"
            )
        try:
            data = response.json()
        except Exception as exc:
            raise SubtitleLookupError("SubDL 查询返回格式错误") from exc
        if not isinstance(data, dict) or data.get("status") is not True:
            raise SubtitleLookupError("SubDL 查询返回失败状态")
        saw_valid_response = True
        for candidate in _candidate_downloads(data):
            try:
                response = http_get(
                    candidate["url"],
                    headers={"Accept": "application/octet-stream"},
                    timeout=int(WATCH_ANALYSIS_SOURCE_TIMEOUT_SECONDS),
                )
            except Exception:
                download_failed = True
                continue
            if int(getattr(response, "status_code", 0) or 0) >= 400:
                download_failed = True
                continue
            text = _subtitle_text_from_download(
                _response_bytes(response),
                name=str(candidate.get("name") or ""),
            )
            if "-->" in text:
                return {
                    "text": text,
                    "query_title": title,
                    "release_name": str(candidate.get("release_name") or ""),
                    "format": str(candidate.get("format") or ""),
                    "language": str(candidate.get("language") or ""),
                }
    if saw_valid_response and download_failed:
        raise SubtitleLookupError("SubDL 找到字幕但下载或解析失败")
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
