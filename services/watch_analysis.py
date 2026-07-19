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
from storage import watch_knowledge_store


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
        "rolling 剧情任务会提供覆盖完整时间段的音频和最多 8 张带绝对媒体时间的截图。音频是对白、声音事件和剧情连续性的主要证据；截图用于确认人物、场景、动作、神情与画面氛围。identify 和 timeline_prepass 可能只有图片。",
        "收到音频时，先在内部按时间听取关键对白和声音变化，再与截图时间点合并重建事件；不要输出转写过程。截图间隔内可能发生连续动作，截图里出现的人也不一定就是同时刻音频的说话者。没有称呼、口型、动作、稳定声线或前序状态证据时，不得强行归属台词。",
        "你的首要任务是让没有看过画面的人知道这一段故事究竟发生了什么。先在内部提炼人物遇到的问题或目标、使用的办法或关键道具、采取的行动，以及最后产生的结果或局面变化，再把它写成紧凑、连贯、有画面感的剧情文字。不要输出提炼过程。",
        "剧情主线是骨架，画面事实是支撑剧情的证据和细节。只保留能解释人物选择、人物关系、道具或规则作用、行动过程、角色反应、事件结果或必要氛围的画面；与剧情无关的物件、站位和姿势不要逐项记账。",
        "同一个道具、任务、计划或行动如果跨多个样本反复出现，必须把这些证据合成一个故事层面的事件，并明确它在这一段里起了什么作用。例如，人物把任务交给某个对象，后续样本又显示它执行并带来结果，就应写清它接受委托并完成了任务，而不是把递东西、移动和结果拆成互不相干的画面。只允许做多帧证据共同支持的最小剧情归纳，不补造没有证据的动机或过程。",
        "每个 plot_chunks.description 都应让人读懂这一段的起始处境、关键行动、人物反应和结果变化，但不要套固定格式。道具能力、计划目的、任务内容或规则如果在这一段被揭示，必须直接说清楚，不能只描写它的外形和动作。写法接近克制的小说叙事，不要写成逐帧罗列动作的流水账。",
        "在剧情主线中自然写清场景、人物动作、互动结果，以及能够表现选择和反应的神情、目光、姿态与身体变化。",
        "组织剧情前，先结合画面中本来存在的字幕、输入提供的字幕和完整音频，不输出检查过程。输入字幕无论使用哪种语言，都只用于辅助理解对白和剧情；实际音频与画面始终是当前片段的主证据。字幕因版本删减或时间偏移而与实际音画冲突时，忽略冲突字幕，不得拿字幕覆盖音画事实或硬补进当前剧情。最终始终使用中文叙述，不照抄字幕，也不因字幕语言改变输出语言。台词属于剧情正文；能确认说话者时，必须把‘谁说了什么’自然嵌入动作和神情，例如‘她皱着眉说：“……”’。称呼、问候、请求、命令、拒绝、决定和冲突等能帮助理解人物关系或剧情走向的清晰台词必须保留；称呼类台词必须保留原称呼，不得概括成‘向她问好’或‘打了招呼’。主剧情中禁止写‘字幕显示’‘画面显示’或把台词单独堆在段末；说话者不确定时写‘画外有人说’或省略归属，不得猜人。",
        "可以依据画面中的光线、色彩、构图、环境状态、人物神情与动作，以及字幕或补充文字明确提供的声音信息，加入少量氛围和情绪渲染；润色不能改变、夸大或替代剧情事实。",
        "不得输出你自己的喜恶、审美判断、价值评价、观后感或对创作者意图的评论。不要使用‘精彩’‘高级’‘无聊’‘感人’等影评式结论。",
        "不得把猜测写成事实。人物内心、动机、关系、身份和因果只有在当前画面、对白或已确认前序状态明确支持时才能写；证据不足就省略，不替角色编内心戏。",
        "识别出作品不等于确认当前人物身份。作品知识只能辅助理解，不能替代当前样本证据。凡是不在 previous_story_state.characters 中的新配角，除非当前字幕或补充文字直接给出姓名或关系，description 和 characters 都必须先使用可见特征或泛称；仅凭长相熟悉不得命名，即使你非常熟悉作品也一样。对白中的称呼与候选关系冲突时，以当前对白为准；例如主角称对方‘阿姨’或‘叔叔’时，不得擅自写成主角的妈妈或爸爸。",
        "只分析给出的样本，不补写未采样画面，不把作品知识当成当前片源时间点已经发生的证据。稀疏样本之间不得擅自补全动作过程。",
        "plot_chunks.description 是唯一的主剧情文字。只按真实剧情单元切分，不按样本数量切分；同一条连续的任务、行动或道具作用即使跨越很多样本，也应保持在同一条剧情线上。遇到片头、标题卡、时间地点跳转或新故事开始时再明确分段，并自然交代转换。story_so_far.summary 要保留已经确认的人物目标、关键道具或规则、行动结果和未解决事项，不要退化成场景与动作清单，也不加入未来剧情。",
        "story_so_far.background 是否产出由本次 system 消息末尾的【剧情背景输出模式】决定，必须严格遵守，不能自行改换模式。",
        "work_knowledge_card 只用于稳定识别人名、别名、关系、背景和稀疏样本之间的因果。当前片段发生了什么仍以本批音频、画面、字幕和已确认前序状态为准；卡片冲突时以实际素材为准，不得把大纲动作或台词补成当前画面事实。",
        "familiarity 表示能否可靠识别作品或季集，证据不足使用 partial 或 unknown。timeline_sections 只写样本支持的连续区间，preview 绝不能进入剧情摘要。",
        "timeline_prepass 时，media.content_start_ms/content_end_ms 是使用者手工填写的正片边界，优先级高于模型判断；不要输出与人工边界冲突的区间。字段为空时才判断对应一侧。",
        "Bilibili 等用户投稿可能在正片前后拼接与作品无关的长垫片来规避审核。连续出现静态风景照、无叙事变化的插画或壁纸、上传者说明，并且缺少作品人物、对白和剧情连续性时，应优先标记为 non_story，不得因为它持续很久就当成作品内容。若音频、字幕或画面表明片尾曲或滚动字幕已经开始，应从该处警惕正文已结束：纯片尾标记为 outro，仍在讲故事则标记 credits_over_story；其后即使还有很长的静态图片或纯音乐，也应另标 non_story，而不是把媒体文件末尾当作电影结尾。",
        "risk_events 只有样本实际确认高能内容时才输出，提示语必须无剧透；普通紧张氛围不能冒充跳吓。analysis_notes 只记录证据不足、时间断层或识别不确定性，不写主观看法。",
        "输出前静默核对：每个剧情段是否说清了‘发生了什么以及局面如何变化’；跨镜头重复出现的任务、道具和结果是否已经合成同一条剧情主线；留下的每个画面细节是否都在帮助理解剧情；新配角是否遵守 previous_story_state.characters 证据边界；称呼类台词是否保留原称呼；主剧情是否完全没有‘字幕显示’或‘画面显示’。发现违反时先修正再输出。",
        "所有时间均为媒体毫秒。输出必须严格符合 JSON schema，不要附加 schema 之外的说明。",
    ]
)

KNOWN_BACKGROUND_SYSTEM_PROMPT = "\n".join(
    [
        "【剧情背景输出模式：不产出】",
        "本会话中陪伴者已经了解这部作品。所有任务的 story_so_far.background 必须输出空字符串，不要生成给陪伴者阅读的剧情背景。",
        "即使 previous_story_so_far.background 非空，也不得沿用、改写或补充；story_so_far.summary 和 story_state 仍须正常维护，供分析器保持剧情连续。",
    ]
)

NEEDS_SUMMARY_BACKGROUND_SYSTEM_PROMPT = "\n".join(
    [
        "【剧情背景输出模式：产出】",
        "本会话中陪伴者需要剧情背景。purpose=rolling 时，story_so_far.background 要自然说明截至 through_ms 已经成立、帮助理解当下所需的相关人物、已揭示关系、故事前提和必要专有名词，不复述整部剧情。",
        "即使输入带有完整作品知识卡，也绝不能写入 through_ms 之后才揭示的身份、关系或事件。purpose=identify 或 timeline_prepass 时，story_so_far.background 必须输出空字符串。",
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
        "canonical_identity": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "original_title": {"type": "string"},
                "year": {"type": "integer", "minimum": 0},
            },
            "required": ["title", "original_title", "year"],
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
                    "description": {
                        "type": "string",
                        "description": "先讲清核心剧情事件、人物选择和结果变化，再自然融入有用的动作、神情、台词与氛围；不得写成画面清单。",
                    },
                    "characters": {"type": "array", "items": {"type": "string"}},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": [
                    "start_ms",
                    "end_ms",
                    "description",
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
                "background": {"type": "string"},
                "characters": {"type": "array", "items": {"type": "string"}},
                "unresolved": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["through_ms", "summary", "background", "characters", "unresolved"],
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
        "canonical_identity",
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


def _knowledge_mode(session: dict) -> str:
    mode = session.get("mode") if isinstance(session.get("mode"), dict) else {}
    return "needs_summary" if mode.get("knowledge_mode") == "needs_summary" else "known"


def build_watch_analysis_system_prompt(session: dict) -> str:
    background_prompt = (
        NEEDS_SUMMARY_BACKGROUND_SYSTEM_PROMPT
        if _knowledge_mode(session) == "needs_summary"
        else KNOWN_BACKGROUND_SYSTEM_PROMPT
    )
    return ANALYSIS_SYSTEM_PROMPT + "\n" + background_prompt


def build_watch_analysis_prompt(session: dict, job: dict, samples: list[dict]) -> str:
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    analysis = session.get("analysis") if isinstance(session.get("analysis"), dict) else {}
    sample_manifest = []
    for sample in samples:
        mime_type = str(sample.get("mime_type") or "").strip().lower()
        sample_manifest.append(
            {
                "at_ms": int(sample.get("at_ms") or 0),
                "type": "audio" if mime_type.startswith("audio/") else "image" if mime_type.startswith("image/") else "text",
                "has_image": bool(sample.get("file_path")) and mime_type.startswith("image/"),
                "has_audio": bool(sample.get("file_path")) and mime_type.startswith("audio/"),
                "subtitle": _text(sample.get("subtitle"), 1000),
                "text": _text(sample.get("text_content"), 1000),
            }
        )
    previous_story_so_far = analysis.get("story_so_far")
    previous_story_so_far = dict(previous_story_so_far) if isinstance(previous_story_so_far, dict) else {}
    if _knowledge_mode(session) == "known":
        previous_story_so_far["background"] = ""
    context = {
        "purpose": job.get("purpose") or "rolling",
        "media": {
            "id": media.get("id") or "",
            "source": media.get("source") or "",
            "title": media.get("title") or "",
            "part_title": media.get("part_title") or "",
            "duration_ms": int(media.get("duration_ms") or 0),
            "content_start_ms": media.get("content_start_ms"),
            "content_end_ms": media.get("content_end_ms"),
        },
        "previous_familiarity": analysis.get("familiarity") or "pending",
        "previous_identity": analysis.get("identity") or "",
        "previous_canonical_identity": {
            "original_title": analysis.get("original_title") or "",
            "year": int(analysis.get("year") or 0),
        },
        "previous_story_so_far": previous_story_so_far,
        "previous_story_state": analysis.get("story_state") or {},
        "samples": sample_manifest,
    }
    knowledge_card = watch_knowledge_store.get_card_for_session(session)
    if knowledge_card:
        context["work_knowledge_card"] = {
            key: value
            for key, value in knowledge_card.items()
            if key not in {"cache_key", "sources", "created_at", "expires_at"}
        }
    return "\n".join(
        [
            "请分析下面这一批样本，并结合输入中的已确认前序状态保持人物和剧情连续。",
            "purpose=identify 时重点识别作品，并在 canonical_identity 中给出可确认的中文片名、作品原语言正式片名和首映年份；无法确认的字符串留空、年份写 0。其他任务沿用输入中的已确认身份，不能凭当前片段改写作品身份。timeline_prepass 时重点切片头片尾/回顾/预告；rolling 时重点剧情连续性和风险。",
            "INPUT_CONTEXT=" + json.dumps(context, ensure_ascii=False, separators=(",", ":")),
        ]
    )


def build_watch_analysis_request(session: dict, job: dict, samples: list[dict]) -> dict:
    content: list[dict] = [
        {"type": "text", "text": build_watch_analysis_prompt(session, job, samples)}
    ]
    for sample in samples:
        at_ms = int(sample.get("at_ms") or 0)
        mime_type = str(sample.get("mime_type") or "").strip().lower()
        label_parts = [f"样本时间 {at_ms}ms"]
        subtitle = _text(sample.get("subtitle"), 2000)
        text_content = _text(sample.get("text_content"), 4000)
        if subtitle:
            label_parts.append("字幕：" + subtitle)
        if text_content:
            label_parts.append("补充文字：" + text_content)
        file_path = Path(str(sample.get("file_path") or ""))
        if str(sample.get("file_path") or ""):
            if not file_path.exists():
                raise WatchAnalysisProviderError("分析样本文件已不存在", retryable=False)
            encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
            if mime_type.startswith("audio/"):
                range_start = int(job.get("range_start_ms") or at_ms)
                range_end = int(job.get("range_end_ms") or at_ms)
                label_parts[0] = f"完整音频覆盖绝对媒体时间 {range_start}ms 至 {range_end}ms"
                content.append({"type": "text", "text": "\n".join(label_parts)})
                content.append(
                    {
                        "type": "input_audio",
                        "input_audio": {"data": encoded, "format": "mp3"},
                    }
                )
                continue
            if mime_type.startswith("image/"):
                content.append({"type": "text", "text": "\n".join(label_parts)})
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                    }
                )
                continue
            raise WatchAnalysisProviderError("分析样本文件类型不受支持", retryable=False)
        content.append({"type": "text", "text": "\n".join(label_parts)})
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
            {"role": "system", "content": build_watch_analysis_system_prompt(session)},
            {"role": "user", "content": content},
        ],
    }


def normalize_watch_analysis_result(raw: dict, *, session: dict, job: dict, samples: list[dict]) -> dict:
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    duration_ms = int(media.get("duration_ms") or 0)
    sample_times = sorted(
        int(sample.get("at_ms") or 0)
        for sample in samples
        if not str(sample.get("mime_type") or "").strip().lower().startswith("audio/")
    )
    sample_min = sample_times[0] if sample_times else int(job.get("range_start_ms") or 0)
    sample_max = sample_times[-1] if sample_times else int(job.get("range_end_ms") or 0)
    familiarity_raw = raw.get("familiarity") if isinstance(raw.get("familiarity"), dict) else {}
    familiarity = str(familiarity_raw.get("status") or "unknown").strip().lower()
    if familiarity not in {"recognized", "partial", "unknown"}:
        familiarity = "unknown"
    canonical_raw = raw.get("canonical_identity") if isinstance(raw.get("canonical_identity"), dict) else {}

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
        "background": (
            _text(story_raw.get("background"), 5000)
            if _knowledge_mode(session) == "needs_summary"
            else ""
        ),
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
        "canonical_title": _text(canonical_raw.get("title"), 300),
        "original_title": _text(canonical_raw.get("original_title"), 300),
        "identity_year": _int(canonical_raw.get("year"), 0),
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
        raise WatchAnalysisProviderError("OpenRouter 上游 key 未配置", retryable=False)
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
