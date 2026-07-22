from __future__ import annotations

import re
from collections import Counter
from math import log
from typing import Any

from config import WATCH_CONTEXT_REPLY_LEAD_MS
from services.watch_visual_context import build_contact_sheet
from storage import watch_analysis_store, watch_runtime_store
from storage import watch_visual_store


WATCH_SESSION_BODY_KEY = "watch_session_id"
WATCH_SNAPSHOT_BODY_KEY = "watch_snapshot"
FUTURE_WINDOW_MS = 2 * 60_000
CURRENT_LOOKBACK_MS = 30_000
RELATED_CHUNK_LIMIT = 4
_RECALL_MESSAGE_WEIGHTS = (0.2, 0.45, 1.0)
_BM25_K1 = 1.2
_BM25_B = 0.75
_LATIN_OR_NUMBER_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u3400-\u9fff]+")
_QUERY_STOPWORDS = {
    "一个",
    "不是",
    "什么",
    "他们",
    "你们",
    "我们",
    "怎么",
    "这个",
    "这里",
    "那个",
    "那里",
    "还是",
    "就是",
    "然后",
    "现在",
    "刚才",
    "有点",
}


def _int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def _compact_text(value: Any, limit: int = 900) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return text[:limit]


def _normalize_snapshot(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {}
    required = {
        "media_id",
        "playhead_ms",
        "is_playing",
        "playback_rate",
        "timeline_epoch",
        "snapshot_seq",
        "captured_at",
    }
    if any(key not in raw for key in required):
        return {}
    media_id = _compact_text(raw.get("media_id"), 240)
    captured_at = _compact_text(raw.get("captured_at"), 80)
    if not media_id or not captured_at:
        return {}
    try:
        playback_rate = min(4.0, max(0.25, float(raw.get("playback_rate") or 1.0)))
    except (TypeError, ValueError):
        playback_rate = 1.0
    return {
        "media_id": media_id,
        "playhead_ms": _int(raw.get("playhead_ms"), 0),
        "is_playing": raw.get("is_playing") is True,
        "playback_rate": playback_rate,
        "timeline_epoch": _int(raw.get("timeline_epoch"), 0),
        "snapshot_seq": _int(raw.get("snapshot_seq"), 0),
        "captured_at": captured_at,
    }


def _chunk_view(chunk: dict) -> dict:
    return {
        "start_ms": _int(chunk.get("start_ms"), 0),
        "end_ms": _int(chunk.get("end_ms"), 0),
        "summary": _compact_text(chunk.get("summary")),
        "characters": chunk.get("characters") if isinstance(chunk.get("characters"), list) else [],
    }


def _clock(milliseconds: int) -> str:
    total_seconds = max(0, int(milliseconds or 0) // 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _format_chunks(chunks: list[dict]) -> list[str]:
    lines: list[str] = []
    for chunk in chunks:
        summary = _compact_text(chunk.get("summary"), 900)
        if not summary:
            continue
        lines.append(
            f"[{_clock(_int(chunk.get('start_ms'), 0))}-{_clock(_int(chunk.get('end_ms'), 0))}] {summary}"
        )
    return lines


def _work_name(media: dict, analysis: dict) -> str:
    title = _compact_text(media.get("title") or analysis.get("identity"), 160) or "当前影片"
    part_title = _compact_text(media.get("part_title"), 120)
    return f"《{title}》" + (f"的{part_title}" if part_title else "")


def _message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return _compact_text(content, 1200)
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and str(item.get("type") or "") in {"text", "input_text"}:
            parts.append(str(item.get("text") or item.get("content") or ""))
    return _compact_text(" ".join(parts), 1200)


def _watch_recall_queries(messages: list[dict]) -> list[str]:
    user_texts = [
        _message_text(message)
        for message in messages
        if isinstance(message, dict) and str(message.get("role") or "") == "user"
    ]
    return [text for text in user_texts[-3:] if text]


def _recall_terms(text: str) -> Counter[str]:
    normalized = str(text or "").lower()
    terms: list[str] = _LATIN_OR_NUMBER_RE.findall(normalized)
    for run in _CJK_RE.findall(normalized):
        if len(run) <= 8 and run not in _QUERY_STOPWORDS:
            terms.append(run)
        for size in (2, 3):
            for index in range(max(0, len(run) - size + 1)):
                token = run[index : index + size]
                if token not in _QUERY_STOPWORDS:
                    terms.append(token)
    return Counter(term for term in terms if term and term not in _QUERY_STOPWORDS)


def _weighted_query_terms(query: str | list[str]) -> dict[str, float]:
    texts = [query] if isinstance(query, str) else [str(item or "") for item in query]
    texts = [text for text in texts[-3:] if text.strip()]
    weights = _RECALL_MESSAGE_WEIGHTS[-len(texts) :]
    weighted: dict[str, float] = {}
    for text, weight in zip(texts, weights):
        for term, count in _recall_terms(text).items():
            weighted[term] = weighted.get(term, 0.0) + weight * min(3, count)
    return weighted


def _chunk_field_terms(chunk: dict) -> tuple[Counter[str], Counter[str], Counter[str]]:
    body = " ".join(
        [
            str(chunk.get("summary") or ""),
            str(chunk.get("dialogue_summary") or ""),
        ]
    )
    tags = chunk.get("tags") if isinstance(chunk.get("tags"), list) else []
    characters = chunk.get("characters") if isinstance(chunk.get("characters"), list) else []
    return (
        _recall_terms(body),
        _recall_terms(" ".join(str(item) for item in tags)),
        _recall_terms(" ".join(str(item) for item in characters)),
    )


def _bm25_tf(term_frequency: int, document_length: int, average_length: float) -> float:
    if term_frequency <= 0:
        return 0.0
    length_ratio = document_length / max(1.0, average_length)
    denominator = term_frequency + _BM25_K1 * (1.0 - _BM25_B + _BM25_B * length_ratio)
    return term_frequency * (_BM25_K1 + 1.0) / denominator


def _recall_related_chunks(
    query: str | list[str],
    chunks: list[dict],
    *,
    excluded_ids: set[str],
) -> list[dict]:
    query_terms = _weighted_query_terms(query)
    if not query_terms:
        return []

    documents: list[tuple[dict, Counter[str], Counter[str], Counter[str]]] = []
    document_frequency: Counter[str] = Counter()
    character_terms: set[str] = set()
    for chunk in chunks:
        if str(chunk.get("id") or "") in excluded_ids:
            continue
        body_terms, tag_terms, chunk_character_terms = _chunk_field_terms(chunk)
        all_terms = set(body_terms) | set(tag_terms) | set(chunk_character_terms)
        if not all_terms:
            continue
        document_frequency.update(all_terms)
        character_terms.update(chunk_character_terms)
        documents.append((chunk, body_terms, tag_terms, chunk_character_terms))
    if not documents:
        return []

    average_body_length = sum(sum(body.values()) for _, body, _, _ in documents) / len(documents)
    document_count = len(documents)
    scored: list[tuple[float, int, bool, dict]] = []
    for chunk, body_terms, tag_terms, chunk_character_terms in documents:
        score = 0.0
        has_content_anchor = False
        body_length = sum(body_terms.values())
        for term, query_weight in query_terms.items():
            body_tf = body_terms.get(term, 0)
            tag_tf = tag_terms.get(term, 0)
            character_tf = chunk_character_terms.get(term, 0)
            if not (body_tf or tag_tf or character_tf):
                continue
            frequency = document_frequency.get(term, 0)
            inverse_frequency = log(
                1.0 + (document_count - frequency + 0.5) / (frequency + 0.5)
            )
            field_score = (
                _bm25_tf(body_tf, body_length, average_body_length)
                + 0.55 * min(1, tag_tf)
                + 0.12 * min(1, character_tf)
            )
            score += query_weight * inverse_frequency * field_score
            if term not in character_terms and (body_tf or tag_tf):
                has_content_anchor = True
        if score <= 0:
            continue
        if not has_content_anchor:
            score *= 0.2
        scored.append(
            (score, _int(chunk.get("end_ms"), 0), has_content_anchor, chunk)
        )
    if not scored:
        return []

    anchored = [item for item in scored if item[2]]
    candidates = anchored if anchored else scored
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if anchored:
        minimum_score = candidates[0][0] * 0.35
        candidates = [item for item in candidates if item[0] >= minimum_score]
        limit = RELATED_CHUNK_LIMIT
    else:
        limit = 1
    selected = [
        item[3]
        for item in candidates[:limit]
    ]
    selected.sort(key=lambda item: (_int(item.get("start_ms"), 0), _int(item.get("end_ms"), 0)))
    return [_chunk_view(item) for item in selected]


def _eligible_story_summary(
    session: dict,
    *,
    session_id: str,
    timeline_epoch: int,
    playhead_ms: int,
) -> dict:
    if str((session.get("mode") or {}).get("knowledge_mode") or "") != "needs_summary":
        return {}
    checkpoint = watch_analysis_store.get_story_checkpoint(
        session_id,
        timeline_epoch=timeline_epoch,
        through_ms=playhead_ms,
    )
    if checkpoint:
        return checkpoint
    summary = (session.get("analysis") or {}).get("story_so_far")
    if not isinstance(summary, dict) or not summary:
        return {}
    try:
        through_ms = int(float(summary["through_ms"]))
    except (KeyError, TypeError, ValueError):
        return {}
    if through_ms < 0 or through_ms > playhead_ms:
        return {}
    return summary


def build_watch_context(
    *,
    session_id: str,
    snapshot: dict,
    window_id: str,
    recall_query: str = "",
) -> tuple[str, dict] | None:
    session = watch_runtime_store.get_session(session_id)
    if not session or session.get("ended_at"):
        return None
    preparation = session.get("preparation") if isinstance(session.get("preparation"), dict) else {}
    if not str(preparation.get("started_at") or "").strip():
        return None
    session_window_id = str(session.get("window_id") or "").strip()
    if session_window_id and window_id and session_window_id != window_id:
        return None
    media = session.get("media") if isinstance(session.get("media"), dict) else {}
    if snapshot.get("media_id") != media.get("id"):
        return None

    playhead_ms = _int(snapshot.get("playhead_ms"), 0)
    timeline_epoch = _int(snapshot.get("timeline_epoch"), 0)
    chunks = watch_runtime_store.get_plot_chunks(
        session_id,
        timeline_epoch=timeline_epoch,
        start_before_ms=playhead_ms + FUTURE_WINDOW_MS,
        end_after_ms=max(0, playhead_ms - CURRENT_LOOKBACK_MS),
        limit=24,
    )
    current_source = [
        item
        for item in chunks
        if _int(item.get("start_ms")) <= playhead_ms < _int(item.get("end_ms"))
    ]
    if not current_source:
        current_source = [
            item
            for item in chunks
            if _int(item.get("end_ms")) <= playhead_ms
            and _int(item.get("end_ms")) >= max(0, playhead_ms - CURRENT_LOOKBACK_MS)
        ][-2:]
    current = [_chunk_view(item) for item in current_source][-4:]
    completed_chunks = watch_runtime_store.get_completed_plot_chunks(
        session_id,
        timeline_epoch=timeline_epoch,
        through_ms=playhead_ms,
    )
    related = _recall_related_chunks(
        recall_query,
        completed_chunks,
        excluded_ids={str(item.get("id") or "") for item in current_source},
    )
    future = [
        _chunk_view(item)
        for item in chunks
        if playhead_ms < _int(item.get("start_ms")) <= playhead_ms + FUTURE_WINDOW_MS
    ][:8]
    reply_lead_ms = 0
    if bool(snapshot.get("is_playing")):
        session_reply_lead_ms = _int(
            (session.get("mode") or {}).get("reply_lead_ms"),
            WATCH_CONTEXT_REPLY_LEAD_MS,
        )
        reply_lead_ms = min(
            FUTURE_WINDOW_MS,
            max(
                0,
                int(
                    round(
                        session_reply_lead_ms
                        * float(snapshot.get("playback_rate") or 1.0)
                    )
                ),
            ),
        )
    reply_until_ms = playhead_ms + reply_lead_ms
    reply_arrival = [
        item for item in future if _int(item.get("start_ms"), 0) <= reply_until_ms
    ]
    danmaku_future = [
        item for item in future if _int(item.get("end_ms"), 0) > reply_until_ms
    ]
    story_summary = _eligible_story_summary(
        session,
        session_id=session_id,
        timeline_epoch=timeline_epoch,
        playhead_ms=playhead_ms,
    )
    analysis = session.get("analysis") if isinstance(session.get("analysis"), dict) else {}
    mode = session.get("mode") if isinstance(session.get("mode"), dict) else {}

    action_context = {
        "session_id": session_id,
        "media_id": str(media.get("id") or ""),
        "snapshot": snapshot,
        "reply_until_ms": reply_until_ms,
        "future_until_ms": playhead_ms + FUTURE_WINDOW_MS,
        "visual": {
            "timeline_epoch": timeline_epoch,
            "playhead_ms": playhead_ms,
            "reply_until_ms": reply_until_ms,
            "related_chunks": related,
        },
    }

    current_lines = _format_chunks(current)
    story_text = _compact_text(story_summary.get("background"), 1800)
    if not current_lines:
        current_lines.append("这一小段暂时没有可靠的剧情描述。")

    lines = [
        "【一起看】",
        f"你正在和小玥一起看{_work_name(media, analysis)}。",
        "",
        "视频不会停下来等你回复，所以本轮另外提供了预计回复抵达前会播放到的少量内容。",
        "小玥正在和你看同一段，不需要和她照搬复述你看到的剧情内容以及逐项描述剧情画面。",
    ]
    story_characters = [
        _compact_text(item, 120)
        for item in story_summary.get("characters", [])
        if _compact_text(item, 120)
    ]
    if story_text or story_characters:
        lines.extend(["", "剧情背景："])
        if story_text:
            lines.append(story_text)
        if story_characters:
            lines.append("相关人物：" + "、".join(story_characters[:12]))
    lines.extend(["", "当前剧情：", *current_lines])
    related_lines = _format_chunks(related)
    if related_lines:
        lines.extend(["", "与小玥说的相关的剧情：", *related_lines])
    reply_lines = _format_chunks(reply_arrival)
    if reply_lines:
        lines.extend(
            [
                "",
                "后续的剧情（这部分用于同步你与小玥观看时的延迟进度）：",
                *reply_lines,
            ]
        )
    if str(analysis.get("status") or "pending") != "ready":
        lines.extend(["", "没有可靠描述的部分不要自行补写。"])
    if bool(mode.get("danmaku_enabled")) and danmaku_future:
        first_action_chunk = danmaku_future[0]
        example_target_ms = max(
            reply_until_ms,
            _int(first_action_chunk.get("start_ms"), reply_until_ms),
        )
        lines.extend(
            [
                "",
                "【定时观看反应】",
                f"预计当前可见回复抵达时，视频约播放到 {_clock(reply_until_ms)}。",
                "下面是抵达位置之后仍会发生、只可用于定时弹幕的剧情：",
                *_format_chunks(danmaku_future),
                "这些内容不能写进当前可见回复，也不能提前暗示给小玥。",
                "如果你想发送弹幕，可以在回复末尾追加一行短隐藏标记：[du:danmaku 媒体时间 弹幕内容]。",
                "媒体时间是希望弹幕实际出现在画面上的时间，不是小玥发消息或你写回复时的时间。",
                f"优先选择不早于 {_clock(reply_until_ms)}、且落在上面可靠剧情片段内的时间；片段允许时再留 5 到 10 秒抵达余量。例如：[du:danmaku {_clock(example_target_ms)} 这里先别盯太紧]。没有想发的就不要写。",
            ]
        )
    else:
        lines.append("本轮没有可用的未来动作片段，不要发送定时弹幕。")
    return "\n".join(lines), action_context


def inject_watch_context(
    body: dict,
    *,
    window_id: str,
    reply_channel: str,
) -> tuple[dict, dict]:
    if not isinstance(body, dict):
        return body, {}
    next_body = dict(body)
    session_id = str(next_body.pop(WATCH_SESSION_BODY_KEY, "") or "").strip()
    snapshot = _normalize_snapshot(next_body.pop(WATCH_SNAPSHOT_BODY_KEY, None))
    if str(reply_channel or "").strip().lower() != "sumitalk" or not session_id or not snapshot:
        return next_body, {}
    messages = next_body.get("messages") if isinstance(next_body.get("messages"), list) else []
    built = build_watch_context(
        session_id=session_id,
        snapshot=snapshot,
        window_id=window_id,
        recall_query=_watch_recall_queries(messages),
    )
    if built is None:
        return next_body, {}
    prompt, action_context = built
    output_messages = [
        {
            "role": "system",
            "content": prompt,
            "__dynamic__": True,
            "__temporary_dynamic__": True,
        },
        *list(messages),
    ]
    session = watch_runtime_store.get_session(session_id)
    mode = session.get("mode") if isinstance((session or {}).get("mode"), dict) else {}
    visual = action_context.get("visual") if isinstance(action_context.get("visual"), dict) else {}
    if str(mode.get("visual_context_mode") or "") == "text_plus_contact_sheet" and visual:
        sheet = build_contact_sheet(
            session_id=session_id,
            timeline_epoch=_int(visual.get("timeline_epoch"), 0),
            playhead_ms=_int(visual.get("playhead_ms"), 0),
            reply_until_ms=_int(visual.get("reply_until_ms"), 0),
            related_chunks=visual.get("related_chunks") if isinstance(visual.get("related_chunks"), list) else [],
        )
        if sheet and watch_visual_store.claim_visual_delivery(
            session_id,
            timeline_epoch=_int(visual.get("timeline_epoch"), 0),
            sheet_hash=str(sheet.get("sha256") or ""),
        ):
            visual_message = {
                "role": "user",
                "content": [
                    {"type": "text", "text": "【剧情画面】"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": str(sheet.get("image_url") or ""),
                            "detail": "low",
                        },
                    },
                ],
                "__dynamic__": True,
            }
            insert_at = len(output_messages)
            for index in range(len(output_messages) - 1, -1, -1):
                item = output_messages[index]
                if isinstance(item, dict) and str(item.get("role") or "").lower() == "user":
                    insert_at = index
                    break
            output_messages.insert(insert_at, visual_message)
            action_context["visual_panels"] = sheet.get("panels") or []
    next_body["messages"] = output_messages
    return next_body, action_context
