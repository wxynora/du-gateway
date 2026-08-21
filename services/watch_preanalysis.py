"""Canonical whole-episode preanalysis for Together Watch.

This module owns the Google Files/generateContent contract and deterministic
canonicalization only. Persistence and retries live in watch_preanalysis_store.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable
from urllib.parse import quote

import requests

from config import (
    WATCH_PREANALYSIS_API_BASE,
    WATCH_PREANALYSIS_API_KEY,
    WATCH_PREANALYSIS_MODEL,
    WATCH_PREANALYSIS_PROMPT_VERSION,
    WATCH_PREANALYSIS_TIMEOUT_SECONDS,
)
from services.watch_analysis import ANALYSIS_SYSTEM_PROMPT, RISK_TYPES, TIMELINE_KINDS
from services.watch_subtitles import parse_subtitle_cues


SCHEMA_VERSION = "watch-preanalysis-v1"
MEDIA_RESOLUTION = "MEDIA_RESOLUTION_LOW"
CLIPPING_POLICY_VERSION = "manual-bounds-two-equal-parts-v1"
SEAM_POLICY_VERSION = "no-overlap-v1"
TIMESTAMP_NORMALIZER_VERSION = "clip-relative-to-media-v1"
PREANALYSIS_SYSTEM_SUFFIX = (
    "\n预解析使用当前裁剪片段的连续音画，不是稀疏 rolling 样本；"
    "输出必须遵守独立 story_checkpoints 协议。"
)
PREANALYSIS_PART_RULES = (
    "你正在预解析一集视频中的一个连续片段。视频输入已经由 Files API 裁剪。",
    "所有输出时间都必须是相对当前裁剪片段开头的毫秒；后端会确定性换算为绝对媒体时间。",
    "plot_chunks 要覆盖真实剧情单元；story_checkpoints 必须至少两条并严格递增，每条只能包含截至该时刻已经揭示的信息。",
    "不得预告后续身份、关系、反转、结局或未来事件。风险提示不得剧透。",
)
PREANALYSIS_SUBTITLE_RULE = (
    "以下字幕 cues 已按当前片段裁剪，时间为相对当前片段开头的毫秒；"
    "它们只能作为当前片段连续音画的辅助证据。"
)


class WatchPreanalysisError(RuntimeError):
    def __init__(self, message: str, *, uncertain: bool = False, status_code: int = 0) -> None:
        super().__init__(message)
        self.uncertain = bool(uncertain)
        self.status_code = int(status_code or 0)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _required_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} 必须是整数")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是整数") from exc
    if parsed < 0:
        raise ValueError(f"{field} 不能为负数")
    return parsed


def _number(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是数字") from exc
    if parsed < 0 or parsed > 1:
        raise ValueError(f"{field} 必须在 0 到 1 之间")
    return parsed


def analysis_profile() -> dict:
    prompt_digest = _digest(
        {
            "system_instruction": ANALYSIS_SYSTEM_PROMPT + PREANALYSIS_SYSTEM_SUFFIX,
            "part_rules": PREANALYSIS_PART_RULES,
            "subtitle_rule": PREANALYSIS_SUBTITLE_RULE,
        }
    )
    return {
        "provider": "google_ai_studio",
        "model": WATCH_PREANALYSIS_MODEL,
        "prompt_version": WATCH_PREANALYSIS_PROMPT_VERSION,
        "prompt_digest": prompt_digest,
        "schema_version": SCHEMA_VERSION,
        "knowledge_context_digest": "no_knowledge_context",
        "media_resolution": MEDIA_RESOLUTION,
        "fps": 1,
        "clipping_policy_version": CLIPPING_POLICY_VERSION,
        "seam_policy_version": SEAM_POLICY_VERSION,
        "timestamp_normalizer_version": TIMESTAMP_NORMALIZER_VERSION,
    }


def analysis_profile_digest() -> str:
    return _digest(analysis_profile())


def build_media_identity(
    media: dict,
    *,
    subtitle_content_digest: str,
    selected_audio_digest: str = "",
) -> dict:
    local_media = media.get("local_media") if isinstance(media.get("local_media"), dict) else {}
    selected_audio = (
        local_media.get("selected_audio")
        if isinstance(local_media.get("selected_audio"), dict)
        else {}
    )
    audio_digest = _clean_text(selected_audio_digest) or _digest(selected_audio)
    subtitle_digest = _clean_text(subtitle_content_digest)
    if not subtitle_digest:
        raise ValueError("subtitle_content_digest 不能为空；无字幕时请使用 no_subtitle")
    identity = {
        "source": _clean_text(media.get("source")),
        "media_id": _clean_text(media.get("id")),
        "local_asset_id": _clean_text(local_media.get("local_asset_id")),
        "media_revision": _clean_text(local_media.get("media_revision")),
        "duration_ms": _required_int(media.get("duration_ms"), "media.duration_ms"),
        "selected_audio_digest": audio_digest,
        "subtitle_content_digest": subtitle_digest,
    }
    if not identity["source"] or not identity["media_id"]:
        raise ValueError("media.source 和 media.id 不能为空")
    if identity["source"] == "local_file" and (
        not identity["local_asset_id"] or not identity["media_revision"]
    ):
        raise ValueError("本地媒体缺少 local_asset_id 或 media_revision")
    identity["media_identity_digest"] = _digest(identity)
    return identity


def build_subtitle_input(
    *,
    kind: Any,
    subtitle_format: Any,
    offset_ms: Any,
    text: Any,
) -> tuple[str, list[dict]]:
    normalized_kind = _clean_text(kind).lower() or "none"
    if normalized_kind == "none":
        return "no_subtitle", []
    if normalized_kind not in {"external", "embedded"}:
        raise ValueError("subtitle.kind 只能是 none、external 或 embedded")
    normalized_format = _clean_text(subtitle_format).lower()
    if normalized_format not in {"srt", "vtt"}:
        raise ValueError("subtitle.format 只支持 srt 或 vtt")
    try:
        normalized_offset = int(offset_ms or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("subtitle.offset_ms 必须是整数") from exc
    normalized_text = "\n".join(
        line.rstrip()
        for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ).strip()
    if not normalized_text:
        raise ValueError("subtitle.text 不能为空")
    parsed = parse_subtitle_cues(normalized_text, offset_ms=normalized_offset)
    cues = [
        {
            "start_ms": max(0, int(round(float(cue.get("start") or 0) * 1000))),
            "end_ms": max(0, int(round(float(cue.get("end") or 0) * 1000))),
            "text": _clean_text(cue.get("text")),
        }
        for cue in parsed
        if isinstance(cue, dict) and _clean_text(cue.get("text"))
    ]
    cues = [cue for cue in cues if cue["end_ms"] > cue["start_ms"]]
    if not cues:
        raise ValueError("subtitle.text 没有解析出可用字幕 cues")
    digest_fields = [normalized_kind, normalized_format, str(normalized_offset)]
    for cue in cues:
        digest_fields.extend(
            (
                str(cue["start_ms"]),
                str(cue["end_ms"]),
                str(cue["text"]).replace("\x00", ""),
            )
        )
    digest = hashlib.sha256("\x00".join(digest_fields).encode("utf-8")).hexdigest()
    return digest, cues


def split_bounds(content_start_ms: Any, content_end_ms: Any) -> tuple[int, int, int]:
    start_ms = _required_int(content_start_ms, "content_start_ms")
    end_ms = _required_int(content_end_ms, "content_end_ms")
    if end_ms <= start_ms:
        raise ValueError("content_end_ms 必须晚于 content_start_ms")
    split_ms = start_ms + (end_ms - start_ms) // 2
    if split_ms <= start_ms or split_ms >= end_ms:
        raise ValueError("正片范围太短，无法切成两段")
    return start_ms, end_ms, split_ms


def build_cache_identity(
    media: dict,
    *,
    content_start_ms: Any,
    content_end_ms: Any,
    subtitle_content_digest: str,
    selected_audio_digest: str = "",
) -> dict:
    start_ms, end_ms, split_ms = split_bounds(content_start_ms, content_end_ms)
    media_identity = build_media_identity(
        media,
        subtitle_content_digest=subtitle_content_digest,
        selected_audio_digest=selected_audio_digest,
    )
    profile = analysis_profile()
    profile_digest = _digest(profile)
    cache_key = _digest(
        {
            "media_identity_digest": media_identity["media_identity_digest"],
            "content_start_ms": start_ms,
            "content_end_ms": end_ms,
            "analysis_profile_digest": profile_digest,
        }
    )
    return {
        "cache_key": cache_key,
        "media_identity": media_identity,
        "content_start_ms": start_ms,
        "content_end_ms": end_ms,
        "split_ms": split_ms,
        "analysis_profile": profile,
        "analysis_profile_digest": profile_digest,
        "parts": [
            {
                "part_index": 1,
                "clip_input_start_ms": start_ms,
                "clip_input_end_ms": split_ms,
                "authoritative_start_ms": start_ms,
                "authoritative_end_ms": split_ms,
            },
            {
                "part_index": 2,
                "clip_input_start_ms": split_ms,
                "clip_input_end_ms": end_ms,
                "authoritative_start_ms": split_ms,
                "authoritative_end_ms": end_ms,
            },
        ],
    }


PREANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "enum": [SCHEMA_VERSION]},
        "segment": {
            "type": "object",
            "properties": {
                "part_index": {"type": "integer", "enum": [1, 2]},
                "authoritative_start_ms": {"type": "integer", "minimum": 0},
                "authoritative_end_ms": {"type": "integer", "minimum": 0},
            },
            "required": ["part_index", "authoritative_start_ms", "authoritative_end_ms"],
        },
        "familiarity": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["recognized", "partial", "unknown"]},
                "identity": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["status", "identity", "confidence"],
        },
        "canonical_identity": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "original_title": {"type": "string"},
                "year": {"type": "integer", "minimum": 0},
            },
            "required": ["title", "original_title", "year"],
        },
        "timeline_sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": sorted(TIMELINE_KINDS)},
                    "start_ms": {"type": "integer", "minimum": 0},
                    "end_ms": {"type": "integer", "minimum": 0},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["kind", "start_ms", "end_ms", "confidence"],
            },
        },
        "plot_chunks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_ms": {"type": "integer", "minimum": 0},
                    "end_ms": {"type": "integer", "minimum": 0},
                    "description": {"type": "string"},
                    "visual_description": {"type": "string"},
                    "dialogue_summary": {"type": "string"},
                    "characters": {"type": "array", "items": {"type": "string"}},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["start_ms", "end_ms", "description", "visual_description", "dialogue_summary", "characters", "tags", "confidence"],
            },
        },
        "story_checkpoints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "through_ms": {"type": "integer", "minimum": 0},
                    "background": {"type": "string"},
                    "characters": {"type": "array", "items": {"type": "string"}},
                    "story_state": {"type": "object"},
                },
                "required": ["through_ms", "background", "characters", "story_state"],
            },
        },
        "risk_events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "risk_type": {"type": "string", "enum": sorted(RISK_TYPES)},
                    "severity": {"type": "integer", "minimum": 1, "maximum": 3},
                    "start_ms": {"type": "integer", "minimum": 0},
                    "end_ms": {"type": "integer", "minimum": 0},
                    "warn_at_ms": {"type": "integer", "minimum": 0},
                    "label": {"type": "string"},
                    "companion_hint": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["risk_type", "severity", "start_ms", "end_ms", "warn_at_ms", "label", "companion_hint", "confidence"],
            },
        },
        "analysis_notes": {"type": "string"},
    },
    "required": ["schema_version", "segment", "familiarity", "canonical_identity", "timeline_sections", "plot_chunks", "story_checkpoints", "risk_events", "analysis_notes"],
}


def _offset(ms: int) -> str:
    seconds = ms / 1000
    return f"{seconds:g}s"


def _video_part(file_uri: str, mime_type: str, start_ms: int, end_ms: int) -> dict:
    return {
        "fileData": {"fileUri": file_uri, "mimeType": mime_type},
        "videoMetadata": {"startOffset": _offset(start_ms), "endOffset": _offset(end_ms)},
        "mediaResolution": {"level": MEDIA_RESOLUTION},
    }


def _subtitle_cues_for_part(part: dict, subtitle_cues: list[dict] | None) -> list[dict]:
    start_ms = int(part["clip_input_start_ms"])
    end_ms = int(part["clip_input_end_ms"])
    result: list[dict] = []
    for cue in subtitle_cues or []:
        if not isinstance(cue, dict):
            continue
        cue_start = int(cue.get("start_ms") or 0)
        cue_end = int(cue.get("end_ms") or 0)
        text = _clean_text(cue.get("text"))
        if not text or cue_end <= start_ms or cue_start >= end_ms:
            continue
        result.append(
            {
                "start_ms": max(start_ms, cue_start) - start_ms,
                "end_ms": min(end_ms, cue_end) - start_ms,
                "text": text,
            }
        )
    return result


def _part_prompt(
    part: dict,
    previous_context: dict | None = None,
    subtitle_cues: list[dict] | None = None,
) -> str:
    duration_ms = int(part["clip_input_end_ms"]) - int(part["clip_input_start_ms"])
    lines = [
        PREANALYSIS_PART_RULES[0],
        PREANALYSIS_PART_RULES[1],
        f"这是第 {part['part_index']} 段，当前片段相对时间范围是 0 到 {duration_ms} 毫秒。",
        PREANALYSIS_PART_RULES[2],
        PREANALYSIS_PART_RULES[3],
    ]
    if previous_context:
        lines.extend(
            [
                "以下是上一段末尾已确认的前序状态，仅用于接续，不得复述上一段正文：",
                _canonical_json(previous_context),
            ]
        )
    current_subtitles = _subtitle_cues_for_part(part, subtitle_cues)
    if current_subtitles:
        lines.extend((PREANALYSIS_SUBTITLE_RULE, _canonical_json(current_subtitles)))
    return "\n".join(lines)


def _generate_request_body(
    *,
    file_uri: str,
    mime_type: str,
    part: dict,
    previous_context: dict | None = None,
    subtitle_cues: list[dict] | None = None,
) -> dict:
    return {
        "systemInstruction": {
            "parts": [{"text": ANALYSIS_SYSTEM_PROMPT + PREANALYSIS_SYSTEM_SUFFIX}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    _video_part(
                        file_uri,
                        mime_type,
                        int(part["clip_input_start_ms"]),
                        int(part["clip_input_end_ms"]),
                    ),
                    {"text": _part_prompt(part, previous_context, subtitle_cues)},
                ],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": PREANALYSIS_SCHEMA,
        },
    }


def _response_json(response: Any) -> dict:
    try:
        payload = response.json()
    except Exception as exc:
        raise WatchPreanalysisError("AI Studio 返回了无法解析的响应") from exc
    return payload if isinstance(payload, dict) else {}


def _raise_http(response: Any, operation: str) -> None:
    status_code = int(getattr(response, "status_code", 0) or 0)
    if 200 <= status_code < 300:
        return
    payload = _response_json(response)
    message = _clean_text((payload.get("error") or {}).get("message")) if isinstance(payload.get("error"), dict) else ""
    raise WatchPreanalysisError(
        message or f"AI Studio {operation} 失败（HTTP {status_code}）",
        uncertain=False,
        status_code=status_code,
    )


class WatchPreanalysisProvider:
    def __init__(self, *, request: Callable[..., Any] | None = None) -> None:
        self.request = request or requests.request

    def _call(self, method: str, url: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}) or {})
        if WATCH_PREANALYSIS_API_KEY:
            headers["x-goog-api-key"] = WATCH_PREANALYSIS_API_KEY
        try:
            return self.request(
                method,
                url,
                timeout=int(WATCH_PREANALYSIS_TIMEOUT_SECONDS),
                headers=headers,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise WatchPreanalysisError(
                "AI Studio 请求结果不确定：网络连接失败或响应未完成",
                uncertain=True,
            ) from exc

    def create_upload_session(self, *, display_name: str, mime_type: str, size_bytes: int) -> str:
        if not WATCH_PREANALYSIS_API_KEY:
            raise WatchPreanalysisError("整集预解析未配置 AI Studio API key")
        response = self._call(
            "POST",
            f"{WATCH_PREANALYSIS_API_BASE}/upload/v1beta/files",
            headers={
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(int(size_bytes)),
                "X-Goog-Upload-Header-Content-Type": mime_type,
                "Content-Type": "application/json",
            },
            json={"file": {"display_name": display_name}},
        )
        _raise_http(response, "创建上传会话")
        upload_url = _clean_text(getattr(response, "headers", {}).get("X-Goog-Upload-URL"))
        if not upload_url:
            raise WatchPreanalysisError("AI Studio 没有返回上传地址")
        return upload_url

    def get_file(self, file_name: str) -> dict:
        response = self._call(
            "GET",
            f"{WATCH_PREANALYSIS_API_BASE}/v1beta/{file_name.lstrip('/')}",
        )
        _raise_http(response, "读取文件状态")
        return _response_json(response)

    def delete_file(self, file_name: str) -> None:
        if not file_name:
            return
        response = self._call(
            "DELETE",
            f"{WATCH_PREANALYSIS_API_BASE}/v1beta/{file_name.lstrip('/')}",
        )
        if int(getattr(response, "status_code", 0) or 0) not in {200, 204, 404}:
            _raise_http(response, "删除文件")

    def count_tokens(
        self,
        *,
        file_uri: str,
        mime_type: str,
        part: dict,
        previous_context: dict | None = None,
        subtitle_cues: list[dict] | None = None,
    ) -> int:
        generation_request = _generate_request_body(
            file_uri=file_uri,
            mime_type=mime_type,
            part=part,
            previous_context=previous_context,
            subtitle_cues=subtitle_cues,
        )
        payload = {
            "generateContentRequest": {
                "model": f"models/{WATCH_PREANALYSIS_MODEL}",
                **generation_request,
            }
        }
        response = self._call(
            "POST",
            f"{WATCH_PREANALYSIS_API_BASE}/v1beta/models/{quote(WATCH_PREANALYSIS_MODEL, safe='')}:countTokens",
            headers={"Content-Type": "application/json"},
            json=payload,
        )
        _raise_http(response, "统计输入 token")
        count = _response_json(response).get("totalTokens")
        return _required_int(count, "totalTokens")

    def generate_part(
        self,
        *,
        file_uri: str,
        mime_type: str,
        part: dict,
        previous_context: dict | None = None,
        subtitle_cues: list[dict] | None = None,
    ) -> tuple[dict, dict]:
        request_body = _generate_request_body(
            file_uri=file_uri,
            mime_type=mime_type,
            part=part,
            previous_context=previous_context,
            subtitle_cues=subtitle_cues,
        )
        response = self._call(
            "POST",
            f"{WATCH_PREANALYSIS_API_BASE}/v1beta/models/{quote(WATCH_PREANALYSIS_MODEL, safe='')}:generateContent",
            headers={"Content-Type": "application/json"},
            json=request_body,
        )
        _raise_http(response, "生成预解析")
        payload = _response_json(response)
        candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
        parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
        text = "".join(
            str(item.get("text") or "") for item in parts if isinstance(item, dict)
        ).strip()
        if not text:
            raise WatchPreanalysisError("AI Studio 没有返回预解析正文")
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WatchPreanalysisError("AI Studio 返回的预解析 JSON 无效") from exc
        if not isinstance(raw, dict):
            raise WatchPreanalysisError("AI Studio 返回的预解析不是对象")
        usage = payload.get("usageMetadata") if isinstance(payload.get("usageMetadata"), dict) else {}
        return normalize_part_result(raw, part), usage


def _normalize_interval(
    item: dict,
    *,
    part: dict,
    label: str,
    start_field: str = "start_ms",
    end_field: str = "end_ms",
) -> tuple[int, int]:
    relative_start = _required_int(item.get(start_field), f"{label}.{start_field}")
    relative_end = _required_int(item.get(end_field), f"{label}.{end_field}")
    if relative_end <= relative_start:
        raise ValueError(f"{label} 时间范围无效")
    clip_start = int(part["clip_input_start_ms"])
    absolute_start = clip_start + relative_start
    absolute_end = clip_start + relative_end
    if (
        absolute_start < int(part["authoritative_start_ms"])
        or absolute_end > int(part["authoritative_end_ms"])
    ):
        raise ValueError(f"{label} 超出当前 part 权威范围")
    return absolute_start, absolute_end


def normalize_part_result(raw: dict, part: dict) -> dict:
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("预解析 schema_version 不匹配")
    segment = raw.get("segment") if isinstance(raw.get("segment"), dict) else {}
    if int(segment.get("part_index") or 0) != int(part["part_index"]):
        raise ValueError("预解析 part_index 不匹配")

    timeline_sections: list[dict] = []
    previous_start = -1
    for index, item in enumerate(raw.get("timeline_sections") or []):
        if not isinstance(item, dict):
            raise ValueError("timeline_sections 项必须是对象")
        start_ms, end_ms = _normalize_interval(item, part=part, label=f"timeline_sections[{index}]")
        if start_ms < previous_start:
            raise ValueError("timeline_sections 时间倒退")
        previous_start = start_ms
        kind = _clean_text(item.get("kind"))
        if kind not in TIMELINE_KINDS:
            raise ValueError("timeline_sections.kind 无效")
        timeline_sections.append(
            {"kind": kind, "start_ms": start_ms, "end_ms": end_ms, "confidence": _number(item.get("confidence"), "timeline_sections.confidence"), "source": "preanalysis"}
        )

    plot_chunks: list[dict] = []
    previous_start = -1
    for index, item in enumerate(raw.get("plot_chunks") or []):
        if not isinstance(item, dict):
            raise ValueError("plot_chunks 项必须是对象")
        start_ms, end_ms = _normalize_interval(item, part=part, label=f"plot_chunks[{index}]")
        if start_ms < previous_start:
            raise ValueError("plot_chunks 时间倒退")
        previous_start = start_ms
        plot_chunks.append(
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "summary": _clean_text(item.get("description")),
                "visual_description": _clean_text(item.get("visual_description")),
                "dialogue_summary": _clean_text(item.get("dialogue_summary")),
                "characters": [_clean_text(value) for value in item.get("characters") or [] if _clean_text(value)],
                "tags": [_clean_text(value) for value in item.get("tags") or [] if _clean_text(value)],
                "confidence": _number(item.get("confidence"), "plot_chunks.confidence"),
            }
        )

    checkpoints: list[dict] = []
    previous_through = -1
    for index, item in enumerate(raw.get("story_checkpoints") or []):
        if not isinstance(item, dict):
            raise ValueError("story_checkpoints 项必须是对象")
        relative_through = _required_int(item.get("through_ms"), f"story_checkpoints[{index}].through_ms")
        through_ms = int(part["clip_input_start_ms"]) + relative_through
        if through_ms <= previous_through:
            raise ValueError("story_checkpoints 时间必须严格递增")
        if through_ms < int(part["authoritative_start_ms"]) or through_ms > int(part["authoritative_end_ms"]):
            raise ValueError("story_checkpoints 超出当前 part 权威范围")
        previous_through = through_ms
        story_state = item.get("story_state")
        if not isinstance(story_state, dict):
            raise ValueError("story_checkpoints.story_state 必须是对象")
        checkpoints.append(
            {
                "through_ms": through_ms,
                "background": _clean_text(item.get("background")),
                "characters": [_clean_text(value) for value in item.get("characters") or [] if _clean_text(value)],
                "story_state": story_state,
            }
        )
    if len(checkpoints) < 2:
        raise ValueError("每个半段必须返回至少两条渐进 story_checkpoints")

    risk_events: list[dict] = []
    previous_start = -1
    for index, item in enumerate(raw.get("risk_events") or []):
        if not isinstance(item, dict):
            raise ValueError("risk_events 项必须是对象")
        start_ms, end_ms = _normalize_interval(item, part=part, label=f"risk_events[{index}]")
        if start_ms < previous_start:
            raise ValueError("risk_events 时间倒退")
        previous_start = start_ms
        relative_warn = _required_int(item.get("warn_at_ms"), f"risk_events[{index}].warn_at_ms")
        warn_at_ms = int(part["clip_input_start_ms"]) + relative_warn
        if warn_at_ms < int(part["authoritative_start_ms"]) or warn_at_ms > start_ms:
            raise ValueError("risk_events.warn_at_ms 超出有效范围")
        risk_type = _clean_text(item.get("risk_type"))
        if risk_type not in RISK_TYPES:
            raise ValueError("risk_events.risk_type 无效")
        severity = _required_int(item.get("severity"), "risk_events.severity")
        if severity not in {1, 2, 3}:
            raise ValueError("risk_events.severity 无效")
        risk_events.append(
            {
                "risk_type": risk_type,
                "severity": severity,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "warn_at_ms": warn_at_ms,
                "label": _clean_text(item.get("label")),
                "companion_hint": _clean_text(item.get("companion_hint")),
                "confidence": _number(item.get("confidence"), "risk_events.confidence"),
            }
        )

    familiarity = raw.get("familiarity") if isinstance(raw.get("familiarity"), dict) else {}
    canonical_identity = raw.get("canonical_identity") if isinstance(raw.get("canonical_identity"), dict) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "part_index": int(part["part_index"]),
        "authoritative_start_ms": int(part["authoritative_start_ms"]),
        "authoritative_end_ms": int(part["authoritative_end_ms"]),
        "familiarity": {
            "status": _clean_text(familiarity.get("status")) or "unknown",
            "identity": _clean_text(familiarity.get("identity")),
            "confidence": _number(familiarity.get("confidence", 0), "familiarity.confidence"),
        },
        "canonical_identity": {
            "title": _clean_text(canonical_identity.get("title")),
            "original_title": _clean_text(canonical_identity.get("original_title")),
            "year": _required_int(canonical_identity.get("year", 0), "canonical_identity.year"),
        },
        "timeline_sections": timeline_sections,
        "plot_chunks": plot_chunks,
        "story_checkpoints": checkpoints,
        "risk_events": risk_events,
        "analysis_notes": _clean_text(raw.get("analysis_notes")),
    }


def previous_part_context(part_result: dict) -> dict:
    checkpoints = part_result.get("story_checkpoints") or []
    plots = part_result.get("plot_chunks") or []
    return {
        "last_story_checkpoint": checkpoints[-1] if checkpoints else {},
        "last_plot_chunk": plots[-1] if plots else {},
    }


def merge_canonical_results(first: dict, second: dict, *, cache_key: str) -> dict:
    if int(first.get("part_index") or 0) != 1 or int(second.get("part_index") or 0) != 2:
        raise ValueError("canonical merge 需要 part 1 和 part 2")
    if int(first.get("authoritative_end_ms") or 0) != int(second.get("authoritative_start_ms") or 0):
        raise ValueError("canonical merge 的两段权威范围不连续")
    checkpoints = list(first.get("story_checkpoints") or []) + list(second.get("story_checkpoints") or [])
    if any(
        int(checkpoints[index]["through_ms"]) <= int(checkpoints[index - 1]["through_ms"])
        for index in range(1, len(checkpoints))
    ):
        raise ValueError("canonical story_checkpoints 时间不递增")
    identity = second.get("canonical_identity") or first.get("canonical_identity") or {}
    familiarity = second.get("familiarity") or first.get("familiarity") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "cache_key": cache_key,
        "analysis_version": f"{WATCH_PREANALYSIS_PROMPT_VERSION}:{analysis_profile_digest()}",
        "familiarity": familiarity,
        "canonical_identity": identity,
        "timeline_sections": list(first.get("timeline_sections") or []) + list(second.get("timeline_sections") or []),
        "plot_chunks": list(first.get("plot_chunks") or []) + list(second.get("plot_chunks") or []),
        "story_checkpoints": checkpoints,
        "risk_events": list(first.get("risk_events") or []) + list(second.get("risk_events") or []),
    }
