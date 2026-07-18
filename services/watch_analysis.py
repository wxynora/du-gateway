from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

import requests

from config import (
    WATCH_ANALYSIS_API_KEY,
    WATCH_ANALYSIS_API_URL,
    WATCH_ANALYSIS_MAX_OUTPUT_TOKENS,
    WATCH_ANALYSIS_MODEL,
    WATCH_ANALYSIS_PROMPT_VERSION,
    WATCH_ANALYSIS_TIMEOUT_SECONDS,
)


TIMELINE_KINDS = {
    "recap",
    "cold_open",
    "intro",
    "content",
    "credits_over_story",
    "outro",
    "preview",
    "post_credit",
    "non_story",
    "unknown",
}
RISK_TYPES = {"jumpscare", "loud_noise", "violence", "gore", "unsettling", "other"}
RISK_WARNING_LEAD_MS = {
    "jumpscare": 7000,
    "loud_noise": 4000,
    "violence": 5000,
    "gore": 5000,
    "unsettling": 4000,
    "other": 4000,
}

ANALYSIS_SYSTEM_PROMPT = "\n".join(
    [
        "你是一起看功能的视频剧情转述器，不是聊天角色，也不是影评人。",
        "你的任务是把带时间戳的画面、字幕和补充文字组织成简洁、连贯、有画面感的剧情文字，让未观看画面的人能准确理解发生了什么。不要写成逐帧罗列动作的流水账。",
        "事实是主体。写清场景、人物、动作、互动、对话结果，以及画面中能辨认的角色神情、目光、姿态和身体反应。",
        "可以依据画面中的光线、色彩、构图、环境状态、人物神情与动作，以及字幕或补充文字明确提供的声音信息，加入少量氛围和情绪渲染；润色不能改变、夸大或替代剧情事实。",
        "不得输出你自己的喜恶、审美判断、价值评价、观后感或对创作者意图的评论。不要使用‘精彩’‘高级’‘无聊’‘感人’等影评式结论。",
        "不得把猜测写成事实。人物内心、动机、关系、身份和因果只有在画面、对白、前序状态或可靠作品识别明确支持时才能写；证据不足就省略，不替角色编内心戏。",
        "只分析给出的样本，不补写未采样画面，不把作品知识当成当前片源时间点已经发生的证据。稀疏样本之间不得擅自补全动作过程。",
        "plot_chunks.description 写成自然连贯的剧情短段；visual_description 聚焦场景、动作、神情和氛围；dialogue_summary 只概括实际出现的对白信息。story_so_far 使用克制的事实摘要，不加入未来剧情。",
        "familiarity 表示能否可靠识别作品或季集，证据不足使用 partial 或 unknown。timeline_sections 只写样本支持的连续区间，preview 绝不能进入剧情摘要。",
        "risk_events 只有样本实际确认高能内容时才输出，提示语必须无剧透；普通紧张氛围不能冒充跳吓。analysis_notes 只记录证据不足、时间断层或识别不确定性，不写主观看法。",
        "所有时间均为媒体毫秒。输出必须严格符合 JSON schema，不要附加 schema 之外的说明。",
    ]
)


ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "familiarity": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["recognized", "partial", "unknown"]},
                "identity": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["status", "identity", "confidence"],
            "additionalProperties": False,
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
                "additionalProperties": False,
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
                "required": [
                    "start_ms",
                    "end_ms",
                    "description",
                    "visual_description",
                    "dialogue_summary",
                    "characters",
                    "tags",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        },
        "story_so_far": {
            "type": "object",
            "properties": {
                "through_ms": {"type": "integer", "minimum": 0},
                "summary": {"type": "string"},
                "characters": {"type": "array", "items": {"type": "string"}},
                "unresolved": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["through_ms", "summary", "characters", "unresolved"],
            "additionalProperties": False,
        },
        "story_state": {
            "type": "object",
            "properties": {
                "characters": {"type": "array", "items": {"type": "string"}},
                "locations": {"type": "array", "items": {"type": "string"}},
                "events": {"type": "array", "items": {"type": "string"}},
                "unresolved": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["characters", "locations", "events", "unresolved"],
            "additionalProperties": False,
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
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "spoiler_free_hint": {"type": "string"},
                },
                "required": [
                    "risk_type",
                    "severity",
                    "start_ms",
                    "end_ms",
                    "confidence",
                    "spoiler_free_hint",
                ],
                "additionalProperties": False,
            },
        },
        "analysis_notes": {"type": "string"},
    },
    "required": [
        "familiarity",
        "timeline_sections",
        "plot_chunks",
        "story_so_far",
        "story_state",
        "risk_events",
        "analysis_notes",
    ],
    "additionalProperties": False,
}


class WatchAnalysisProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, status_code: int = 0) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = int(status_code or 0)


def _text(value: Any, limit: int) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return default


def _strings(value: Any, *, limit: int = 20, item_limit: int = 200) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _text(item, item_limit)
        if text and text not in out:
            out.append(text)
    return out[:limit]


def _extract_json_object(content: Any) -> dict:
    if isinstance(content, dict):
        return content
    text = str(content or "").strip()
    if not text:
        raise WatchAnalysisProviderError("分析模型返回空内容", retryable=True)
    try:
        parsed = json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise WatchAnalysisProviderError("分析模型没有返回 JSON", retryable=True)
        try:
            parsed = json.loads(match.group(0))
        except Exception as exc:
            raise WatchAnalysisProviderError("分析模型 JSON 无法解析", retryable=True) from exc
    if not isinstance(parsed, dict):
        raise WatchAnalysisProviderError("分析模型 JSON 顶层不是对象", retryable=True)
    return parsed


def build_watch_analysis_prompt(session: dict, job: dict, samples: list[dict]) -> str:
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    analysis = session.get("analysis") if isinstance(session.get("analysis"), dict) else {}
    mode = session.get("mode") if isinstance(session.get("mode"), dict) else {}
    sample_manifest = [
        {
            "at_ms": int(sample.get("at_ms") or 0),
            "has_image": bool(sample.get("file_path")),
            "subtitle": _text(sample.get("subtitle"), 1000),
            "text": _text(sample.get("text_content"), 1000),
        }
        for sample in samples
    ]
    context = {
        "purpose": job.get("purpose") or "rolling",
        "media": {
            "id": media.get("id") or "",
            "source": media.get("source") or "",
            "title": media.get("title") or "",
            "part_title": media.get("part_title") or "",
            "duration_ms": int(media.get("duration_ms") or 0),
        },
        "knowledge_mode": mode.get("knowledge_mode") or "known",
        "previous_familiarity": analysis.get("familiarity") or "pending",
        "previous_identity": analysis.get("identity") or "",
        "previous_story_so_far": analysis.get("story_so_far") or {},
        "previous_story_state": analysis.get("story_state") or {},
        "samples": sample_manifest,
    }
    return "\n".join(
        [
            "请分析下面这一批样本，并结合输入中的已确认前序状态保持人物和剧情连续。",
            "purpose=identify 时重点识别作品；timeline_prepass 时重点切片头片尾/回顾/预告；rolling 时重点剧情连续性和风险。",
            "INPUT_CONTEXT=" + json.dumps(context, ensure_ascii=False, separators=(",", ":")),
        ]
    )


def build_watch_analysis_request(session: dict, job: dict, samples: list[dict]) -> dict:
    content: list[dict] = [
        {"type": "text", "text": build_watch_analysis_prompt(session, job, samples)}
    ]
    for sample in samples:
        at_ms = int(sample.get("at_ms") or 0)
        label_parts = [f"样本时间 {at_ms}ms"]
        subtitle = _text(sample.get("subtitle"), 2000)
        text_content = _text(sample.get("text_content"), 4000)
        if subtitle:
            label_parts.append("字幕：" + subtitle)
        if text_content:
            label_parts.append("补充文字：" + text_content)
        content.append({"type": "text", "text": "\n".join(label_parts)})
        file_path = Path(str(sample.get("file_path") or ""))
        if str(sample.get("file_path") or ""):
            if not file_path.exists():
                raise WatchAnalysisProviderError("分析样本文件已不存在", retryable=False)
            image_b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                }
            )
    return {
        "model": WATCH_ANALYSIS_MODEL,
        "stream": False,
        "temperature": 0,
        "max_tokens": int(WATCH_ANALYSIS_MAX_OUTPUT_TOKENS),
        "reasoning": {"effort": "none"},
        "provider": {"require_parameters": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "watch_analysis",
                "strict": True,
                "schema": ANALYSIS_SCHEMA,
            },
        },
        "messages": [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
    }


def normalize_watch_analysis_result(raw: dict, *, session: dict, job: dict, samples: list[dict]) -> dict:
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    duration_ms = int(media.get("duration_ms") or 0)
    sample_times = sorted(int(sample.get("at_ms") or 0) for sample in samples)
    sample_min = sample_times[0] if sample_times else int(job.get("range_start_ms") or 0)
    sample_max = sample_times[-1] if sample_times else int(job.get("range_end_ms") or 0)
    familiarity_raw = raw.get("familiarity") if isinstance(raw.get("familiarity"), dict) else {}
    familiarity = str(familiarity_raw.get("status") or "unknown").strip().lower()
    if familiarity not in {"recognized", "partial", "unknown"}:
        familiarity = "unknown"

    sections: list[dict] = []
    for item in raw.get("timeline_sections") if isinstance(raw.get("timeline_sections"), list) else []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "unknown").strip().lower()
        start_ms = _int(item.get("start_ms"), 0)
        end_ms = _int(item.get("end_ms"), 0)
        if kind not in TIMELINE_KINDS or end_ms <= start_ms:
            continue
        if duration_ms > 0 and end_ms > duration_ms:
            end_ms = duration_ms
        if end_ms <= start_ms:
            continue
        sections.append(
            {
                "kind": kind,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "confidence": _float(item.get("confidence"), 0),
                "source": "vision_prepass",
            }
        )

    chunks: list[dict] = []
    for item in raw.get("plot_chunks") if isinstance(raw.get("plot_chunks"), list) else []:
        if not isinstance(item, dict):
            continue
        start_ms = max(sample_min, _int(item.get("start_ms"), sample_min))
        end_ms = min(sample_max, _int(item.get("end_ms"), sample_max))
        if end_ms <= start_ms:
            if sample_max == sample_min:
                start_ms = max(0, sample_min - 1000)
                end_ms = sample_min
            if end_ms <= start_ms:
                continue
        chunks.append(
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "summary": _text(item.get("description"), 3000),
                "visual_description": _text(item.get("visual_description"), 3000),
                "dialogue_summary": _text(item.get("dialogue_summary"), 3000),
                "characters": _strings(item.get("characters")),
                "tags": _strings(item.get("tags"), item_limit=80),
                "confidence": _float(item.get("confidence"), 0),
            }
        )

    story_raw = raw.get("story_so_far") if isinstance(raw.get("story_so_far"), dict) else {}
    through_ms = min(sample_max, _int(story_raw.get("through_ms"), sample_max))
    story_so_far = {
        "through_ms": through_ms,
        "summary": _text(story_raw.get("summary"), 8000),
        "characters": _strings(story_raw.get("characters"), limit=40),
        "unresolved": _strings(story_raw.get("unresolved"), limit=40),
    }
    state_raw = raw.get("story_state") if isinstance(raw.get("story_state"), dict) else {}
    story_state = {
        "characters": _strings(state_raw.get("characters"), limit=60),
        "locations": _strings(state_raw.get("locations"), limit=40),
        "events": _strings(state_raw.get("events"), limit=80),
        "unresolved": _strings(state_raw.get("unresolved"), limit=60),
    }

    risk_events: list[dict] = []
    for item in raw.get("risk_events") if isinstance(raw.get("risk_events"), list) else []:
        if not isinstance(item, dict):
            continue
        risk_type = str(item.get("risk_type") or "other").strip().lower()
        if risk_type not in RISK_TYPES:
            risk_type = "other"
        start_ms = _int(item.get("start_ms"), 0)
        end_ms = _int(item.get("end_ms"), 0)
        confidence = _float(item.get("confidence"), 0)
        if end_ms <= start_ms or start_ms < sample_min or start_ms > sample_max or confidence < 0.65:
            continue
        risk_events.append(
            {
                "risk_type": risk_type,
                "severity": str(max(1, min(3, _int(item.get("severity"), 1)))),
                "start_ms": start_ms,
                "end_ms": min(end_ms, duration_ms) if duration_ms else end_ms,
                "warn_at_ms": max(0, start_ms - RISK_WARNING_LEAD_MS[risk_type]),
                "label": _text(item.get("spoiler_free_hint"), 300),
                "companion_hint": _text(item.get("spoiler_free_hint"), 500),
                "confidence": confidence,
            }
        )
    return {
        "familiarity": familiarity,
        "identity": _text(familiarity_raw.get("identity"), 500),
        "familiarity_confidence": _float(familiarity_raw.get("confidence"), 0),
        "timeline_sections": sections,
        "plot_chunks": chunks,
        "story_so_far": story_so_far,
        "story_state": story_state,
        "risk_events": risk_events,
        "covered_from_ms": sample_min,
        "covered_until_ms": sample_max,
        "analysis_notes": _text(raw.get("analysis_notes"), 1000),
        "analysis_version": f"{WATCH_ANALYSIS_MODEL}:{WATCH_ANALYSIS_PROMPT_VERSION}",
    }


def _usage_from_response(data: dict, *, elapsed_ms: int) -> dict:
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    cost_usd = _float(usage.get("cost") or usage.get("cost_usd"), 0)
    return {
        "input_tokens": _int(usage.get("prompt_tokens") or usage.get("input_tokens"), 0),
        "output_tokens": _int(usage.get("completion_tokens") or usage.get("output_tokens"), 0),
        "total_tokens": _int(usage.get("total_tokens"), 0),
        "cost_usd": max(0.0, cost_usd),
        "elapsed_ms": max(0, int(elapsed_ms)),
        "model": _text(data.get("model") or WATCH_ANALYSIS_MODEL, 160),
    }


def analyze_watch_samples(
    session: dict,
    job: dict,
    samples: list[dict],
    *,
    post: Callable[..., Any] = requests.post,
) -> tuple[dict, dict]:
    if not WATCH_ANALYSIS_API_KEY:
        raise WatchAnalysisProviderError("WATCH_ANALYSIS_API_KEY/OPENROUTER_API_KEY 未配置", retryable=False)
    if not samples:
        raise WatchAnalysisProviderError("分析任务没有可用样本", retryable=False)
    payload = build_watch_analysis_request(session, job, samples)
    started = time.perf_counter()
    try:
        response = post(
            WATCH_ANALYSIS_API_URL,
            headers={
                "Authorization": f"Bearer {WATCH_ANALYSIS_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=max(20, int(WATCH_ANALYSIS_TIMEOUT_SECONDS)),
        )
    except Exception as exc:
        raise WatchAnalysisProviderError(f"分析请求失败: {exc}", retryable=True) from exc
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code >= 400:
        body = _text(getattr(response, "text", ""), 600)
        retryable = status_code in {408, 409, 425, 429} or status_code >= 500
        raise WatchAnalysisProviderError(
            f"分析上游 HTTP {status_code}: {body}",
            retryable=retryable,
            status_code=status_code,
        )
    try:
        data = response.json()
    except Exception as exc:
        raise WatchAnalysisProviderError("分析上游响应不是 JSON", retryable=True) from exc
    message = (((data.get("choices") or [{}])[0] or {}).get("message") or {})
    raw = _extract_json_object(message.get("content"))
    result = normalize_watch_analysis_result(raw, session=session, job=job, samples=samples)
    return result, _usage_from_response(data, elapsed_ms=elapsed_ms)
