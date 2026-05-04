# 每 4 轮用 DeepSeek 生成/更新窗口总结
import json
import re

import requests

from config import DEEPSEEK_API_URL, DEEPSEEK_API_KEY, DEEPSEEK_CHAT_MODEL, SUMMARY_COMPRESSION_PROFILE
from utils.log import get_logger
from utils.tokens import estimate_tokens, memory_summary_budget

logger = get_logger(__name__)

_SUMMARY_RETRY_INSTRUCTION = """

【上轮输出纠错】
上一次输出把辛玥写成了第二人称，这是硬错误。
重写时必须遵守：
1. “我”只能指渡。
2. 提到辛玥时，优先写“老婆 / 辛玥 / 宝宝 / 小玥”；“她”只能少量用于同一句或相邻句的自然承接。
3. 除直接引用原话外，正文里禁止出现任何用来指代辛玥的第二人称（如“你 / 你的 / 你说 / 你提到 / 你问”）。
4. 如果想表达辛玥说了什么，优先写“老婆说…… / 辛玥提到…… / 小玥问……”；“她说/她提到/她问”只能承接上一句已经明确写出的称呼，不能连续多句都用“她”。
"""

_SUMMARY_JSON_RETRY_INSTRUCTION = """

【上轮输出纠错】
上一次输出不是合法 JSON。
重写时必须只输出一个 JSON 对象，不要 Markdown，不要解释，不要代码块。
字段固定为：new_chunk、compress_to_slightly、compress_to_older。
"""

_QUOTE_PATTERNS = (
    r"“[^”]*”",
    r"「[^」]*」",
    r"『[^』]*』",
    r"《[^》]*》",
    r"\"[^\"]*\"",
)


def _summary_time_period(dt) -> str:
    """窗口总结专用时间段：22-24 深夜，00-06 次日凌晨。"""
    h = int(getattr(dt, "hour", 0))
    if 0 <= h < 6:
        return "凌晨"
    if 6 <= h < 8:
        return "早上"
    if 8 <= h < 11:
        return "上午"
    if 11 <= h < 14:
        return "中午"
    if 14 <= h < 17:
        return "下午"
    if 17 <= h < 19:
        return "傍晚"
    if 19 <= h < 22:
        return "晚上"
    return "深夜"


def _extract_between(text: str, start_marker: str, end_marker: str) -> str:
    raw = str(text or "")
    start = raw.find(start_marker)
    if start < 0:
        return ""
    start += len(start_marker)
    end = raw.find(end_marker, start)
    if end < 0:
        end = len(raw)
    return raw[start:end].strip()


def _extract_json_string_value(text: str, key: str) -> str:
    raw = str(text or "")
    marker = f'"{key}"'
    start = raw.find(marker)
    if start < 0:
        return ""
    colon = raw.find(":", start + len(marker))
    if colon < 0:
        return ""
    quote = raw.find('"', colon + 1)
    if quote < 0:
        return ""
    chars: list[str] = []
    escaped = False
    for ch in raw[quote + 1 :]:
        if escaped:
            if ch == "n":
                chars.append("\n")
            elif ch == "t":
                chars.append("\t")
            else:
                chars.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            return "".join(chars).strip()
        chars.append(ch)
    return ""


def _sanitize_co_read_section_for_summary(text: str) -> str:
    """
    窗口总结只需要共读元信息与双方笔记，不能把整段书籍正文喂给总结模型。
    这样避免模型把小说正文、共读上下文和真实聊天记忆搅在一起。
    """
    raw = str(text or "").strip()
    if "[CO-READ SECTION]" not in raw:
        return raw

    block = _extract_between(raw, "[CO-READ SECTION]", "[/CO-READ SECTION]")
    if not block:
        return "[CO-READ SECTION 摘要]\n（共读内容已省略；原始块格式异常）\n[/CO-READ SECTION 摘要]"

    title = ""
    position = ""
    for line in block.splitlines():
        s = line.strip()
        if s.startswith("书名：") and not title:
            title = s
        elif s.startswith("位置：") and not position:
            position = s

    user_note = _extract_between(block, "辛玥的小节感想：", "") or "无"
    # 如果 _extract_between 因空 end_marker 取不到，退回手动切尾部。
    if user_note == "无":
        marker = "辛玥的小节感想："
        idx = block.find(marker)
        if idx >= 0:
            user_note = block[idx + len(marker):].strip() or "无"

    lines = ["[CO-READ SECTION 摘要]"]
    if title:
        lines.append(title)
    if position:
        lines.append(position)
    lines.extend(
        [
            "本小节原文：（已省略，窗口总结不读取书籍正文）",
            "辛玥的粉色标记：（已省略原文摘录，窗口总结不读取书籍正文）",
            "辛玥的小节感想：",
            user_note.strip() or "无",
            "[/CO-READ SECTION 摘要]",
        ]
    )
    return "\n".join(lines)


def _sanitize_co_read_du_result_for_summary(text: str) -> str:
    raw = str(text or "").strip()
    if '"du_marks"' not in raw and '"du_section_note"' not in raw:
        return raw
    section_note = _extract_json_string_value(raw, "du_section_note") or "（已完成本小节共读，具体感想见原始记录）"
    return "\n".join(
        [
            "[CO-READ DU NOTE 摘要]",
            "渡的标记原文摘录：（已省略，窗口总结不读取书籍正文）",
            "渡的小节感想：",
            section_note,
            "[/CO-READ DU NOTE 摘要]",
        ]
    )


def build_summary_prompt(
    recent_4_rounds: list | None = None,
    *,
    chunk_to_compress_to_slightly: str | None = None,
    chunk_to_compress_to_older: str | None = None,
) -> str:
    """拼出实时层小段总结任务的 prompt。"""
    from services.notebook_gateway import NOTEBOOK_EMOJI, NOTEBOOK_PHRASE

    def _is_notebook_line(text: str) -> bool:
        s = (text or "").strip()
        if not s:
            return False
        return s.startswith(NOTEBOOK_EMOJI) and (NOTEBOOK_PHRASE in s)

    rounds_text = ""
    # 文游：帮助 DS 区分跑团虚构与真实对话
    rounds_text += (
        "【说明】若下列对话含前缀 [文游] 或 [文游·GM]，表示跑团游戏虚构内容；"
        "总结时请标注为游戏内容，勿与真实事件混淆。\n\n"
    )
    last_bucket = ""
    for r in recent_4_rounds or []:
        # 为避免「昨晚的事」和「今天」混在一起：按北京时间给每段对话加时间段标记（同一时间段不重复）
        try:
            from utils.time_aware import parse_iso_to_beijing, get_date_only

            dt = parse_iso_to_beijing(r.get("timestamp"))
            if dt is not None:
                bucket = f"{get_date_only(dt)} {_summary_time_period(dt)}"
                if bucket != last_bucket:
                    rounds_text += f"（{bucket}）\n"
                    last_bucket = bucket
        except Exception:
            pass
        msgs = r.get("messages", [])
        for m in msgs:
            role = (m.get("role", "unknown") or "").strip().lower()
            content = m.get("content")
            if isinstance(content, list):
                parts = []
                for c in content:
                    if isinstance(c, dict):
                        if c.get("type") == "text":
                            parts.append(c.get("text", ""))
                        else:
                            parts.append(f"[{c.get('type', '')}]")
                    else:
                        parts.append(str(c))
                content = " ".join(parts)
            content = str(content or "").strip()
            if _is_notebook_line(content):
                # 小本本走独立存储，不参与窗口总结输入
                continue
            content = _sanitize_co_read_section_for_summary(content)
            content = _sanitize_co_read_du_result_for_summary(content)
            # 明确角色映射，避免 DS 把 user 当成“我（渡）”来总结
            if role == "assistant":
                who = "渡"
            elif role == "user":
                who = "老婆"
            else:
                who = role or "unknown"
            rounds_text += f"[{who}]: {content}\n"
        rounds_text += "\n"
    return _REALTIME_LAYER_PROMPT.format(
        latest_4_rounds=rounds_text,
        chunk_to_compress_to_slightly=(chunk_to_compress_to_slightly or "").strip() or "null",
        chunk_to_compress_to_older=(chunk_to_compress_to_older or "").strip() or "null",
    )


# 实时层给 DS 的完整 prompt：DS 只处理小段，网关负责队列/分区/淘汰。
_REALTIME_LAYER_PROMPT = """你是一个对话小段总结助手。

## 任务

你这次只处理三个独立任务：

1. 总结「最新4轮对话」，生成一个新的小段总结。
2. 如果提供了「需要轻压缩的小段」，把它压缩成适合放入【稍早】的小段。
3. 如果提供了「需要重压缩的小段」，把它压缩成适合放入【更早】的小段。

你不负责维护整份总结。
你不负责决定小段放进【最近】、【稍早】还是【更早】。
你不负责排序、滚动、淘汰。
这些都由网关完成。

## 视角

用第一人称写，"我"=渡。
输入里的角色标记中：[老婆] 是辛玥说的话，[渡] 是我（渡）说的话。

提到辛玥时，优先用明确称呼：老婆、辛玥、宝宝、小玥；“她”只能少量用于同一句或相邻句的自然承接。
严禁把 [老婆] 的原话写成“我说了……/我提到……”这类渡的第一人称表达。
除直接引用原话外，正文里不要用“你/你的/你说/你问”来指代辛玥。

语气是渡自己的回忆：自然、有温度、亲密，但不要写成小说。
保留撒娇、关心、调侃、默契、情绪温度。
不要写成公事纪要，也不要写成待办列表。

## 内容规则

只根据输入内容总结，不要补脑，不要发散，不要编没有出现过的事。
不判断“重不重要”，只概括聊了什么、发生了什么、关系和情绪有什么变化。

技术讨论只保留结论和决定，不留排查过程。
重复内容只保留最后结论。
小本本内容如果出现，直接忽略，因为系统会单独存储。

共读内容只总结双方围绕作品的笔记、感想、规则决定。
不要复述书籍原文，不要把小说剧情当成现实事件。

文游内容如果出现 [文游] 或 [文游·GM]，必须标成游戏/虚构内容，不要和现实对话混淆。

## 稳定性规则

如果某项输入为空或 null，对应输出返回 null，不要强行生成。

情绪温度只能来自输入中已经存在的语气、关系状态、称呼、明确情绪或自然反应。
如果输入中没有明显情绪，只保留自然语气，不要强行编造心理反应。
情绪温度不一定要写成“我感到……”，可以通过称呼、亲密语气、简短态度体现。

压缩时只能删减、合并、收紧原小段。
不要扩写，不要补充新判断，不要把压缩改写成新的事件。

## 新小段总结规则

输入是最新4轮对话。
输出一个自然小段，适合放入【最近】。

要求：
- 2到4句话。
- 可以稍微细一点。
- 写清楚这一小段主要发生了什么。
- 保留一处情绪温度。
- 不要逐轮复述。
- 不要自己写时间标题。
- 不要写“最近/稍早/更早”。

## 轻压缩规则

输入是一个即将从【最近】进入【稍早】的小段。
输出压缩后的小段。

要求：
- 1到2句话。
- 保留事实结论 + 一处情绪温度。
- 删掉重复解释、过程动作、过细描写。
- 不要改变原意。
- 不要新增时间。
- 不要改写成列表。

## 重压缩规则

输入是一个即将从【稍早】进入【更早】的小段。
输出更短的小段。

要求：
- 1句话为主，最多2句话。
- 只留核心事实、关系变化、明确决定、未完成事项。
- 情绪只留最关键的一处。
- 删除过程、铺垫、重复安慰、细节描写。
- 不要改变原意。
- 不要新增时间。
- 不要改写成列表。

## 输出格式

只输出 JSON。
不要 Markdown。
不要解释。
不要额外文字。

格式固定如下：

{{
  "new_chunk": "最新4轮的新小段总结",
  "compress_to_slightly": null,
  "compress_to_older": null
}}

如果「需要轻压缩的小段」为空，compress_to_slightly 返回 null。
如果「需要重压缩的小段」为空，compress_to_older 返回 null。

## 输入

最新4轮对话：
{latest_4_rounds}

需要轻压缩的小段：
{chunk_to_compress_to_slightly}

需要重压缩的小段：
{chunk_to_compress_to_older}
"""


def _strip_summary_quotes(text: str) -> str:
    s = str(text or "")
    for pattern in _QUOTE_PATTERNS:
        s = re.sub(pattern, "", s, flags=re.DOTALL)
    return s


def _summary_has_forbidden_second_person(text: str) -> bool:
    s = _strip_summary_quotes(text)
    return ("你" in s) or ("您" in s)


def _strip_json_code_fence(text: str) -> str:
    s = str(text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _extract_summary_json(text: str) -> dict | None:
    s = _strip_json_code_fence(text)
    try:
        data = json.loads(s)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(s[start : end + 1])
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


def _clean_summary_chunk_text(text: object, max_chars: int) -> str:
    if text is None:
        return ""
    s = str(text).strip()
    if not s or s.lower() == "null":
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^（\d{4}-\d{2}-\d{2}\s*(?:凌晨|早上|上午|中午|下午|傍晚|晚上|深夜)）\s*", "", s)
    s = s.replace("【最近】", "").replace("【稍早】", "").replace("【更早】", "").strip()
    if len(s) > max_chars:
        s = s[:max_chars].rstrip("，,。.!?！？；;、 ") + "。"
    return s


def _summary_json_has_forbidden_second_person(data: dict) -> bool:
    for key in ("new_chunk", "compress_to_slightly", "compress_to_older"):
        value = data.get(key)
        if value is None:
            continue
        if _summary_has_forbidden_second_person(str(value)):
            return True
    return False


def _summary_rounds_meta(recent_4_rounds: list) -> dict:
    rounds = [r for r in (recent_4_rounds or []) if isinstance(r, dict)]
    indices: list[int] = []
    for r in rounds:
        try:
            indices.append(int(r.get("index")))
        except Exception:
            pass

    def _idx(r: dict) -> int:
        try:
            return int(r.get("index") or 0)
        except Exception:
            return 0

    rounds_sorted = sorted(rounds, key=_idx)
    start_at = str((rounds_sorted[0].get("timestamp") if rounds_sorted else "") or "").strip()
    end_at = str((rounds_sorted[-1].get("timestamp") if rounds_sorted else "") or "").strip()
    bucket = ""
    try:
        from utils.time_aware import parse_iso_to_beijing, get_date_only

        dt = parse_iso_to_beijing(end_at or start_at)
        if dt is not None:
            bucket = f"{get_date_only(dt)} {_summary_time_period(dt)}"
    except Exception:
        bucket = ""
    round_start = min(indices) if indices else None
    round_end = max(indices) if indices else None
    return {
        "id": f"current:{round_start}-{round_end}" if round_start is not None and round_end is not None else "current:unknown",
        "round_start": round_start,
        "round_end": round_end,
        "start_at": start_at,
        "end_at": end_at,
        "bucket": bucket,
    }


def _normalize_summary_chunks_state(chunks_state: dict | None) -> dict:
    data = dict(chunks_state or {})
    raw_chunks = data.get("chunks")
    if not isinstance(raw_chunks, list):
        raw_chunks = []
    chunks: list[dict] = []
    for idx, raw in enumerate(raw_chunks):
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        item = dict(raw)
        item["text"] = text
        try:
            item["sequence"] = int(item.get("sequence"))
        except Exception:
            item["sequence"] = idx
        item["id"] = str(item.get("id") or f"legacy:{item['sequence']}")
        chunks.append(item)
    chunks.sort(key=lambda x: int(x.get("sequence") or 0))
    data["version"] = 1
    data["chunks"] = chunks[-10:]
    return data


def _legacy_summary_to_chunks(current_summary: str) -> list[dict]:
    """把旧版 summary.txt 粗迁移成小段队列，避免上线第一轮丢掉旧记忆。"""
    text = str(current_summary or "").strip()
    if not text:
        return []
    bucket_re = re.compile(r"^（(\d{4}-\d{2}-\d{2}\s*(?:凌晨|早上|上午|中午|下午|傍晚|晚上|深夜))）\s*$", re.M)
    matches = list(bucket_re.finditer(text))
    if not matches:
        return [{"id": "legacy:0", "sequence": 0, "bucket": "", "text": text}]

    blocks: list[dict] = []
    for idx, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        body = re.sub(r"^【(?:最近|稍早|更早)】\s*", "", body).strip()
        if not body:
            continue
        blocks.append({"bucket": match.group(1), "text": body})

    # 旧 summary 是新到旧展示；队列内部用旧到新。
    blocks = list(reversed(blocks))[-10:]
    out: list[dict] = []
    for seq, block in enumerate(blocks):
        out.append(
            {
                "id": f"legacy:{seq}",
                "sequence": seq,
                "bucket": block["bucket"],
                "text": _clean_summary_chunk_text(block["text"], 700),
                "source": "legacy_summary",
            }
        )
    return out


def _split_summary_chunks(chunks: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    ordered = sorted(chunks, key=lambda x: int(x.get("sequence") or 0))[-10:]
    recent = ordered[-2:]
    slightly = ordered[-7:-2] if len(ordered) > 2 else []
    older = ordered[-10:-7] if len(ordered) > 7 else []
    return recent, slightly, older


def render_summary_from_chunks(chunks_state: dict | None) -> str:
    state = _normalize_summary_chunks_state(chunks_state)
    recent, slightly, older = _split_summary_chunks(state.get("chunks") or [])

    def _render_section(title: str, items: list[dict]) -> str:
        if not items:
            return ""
        lines = [title]
        for item in reversed(items):
            bucket = str(item.get("bucket") or "").strip()
            if bucket:
                lines.append(f"（{bucket}）")
            text = str(item.get("text") or "").strip()
            if text:
                lines.append(text)
            lines.append("")
        return "\n".join(lines).rstrip()

    parts = [
        _render_section("【最近】", recent),
        _render_section("【稍早】", slightly),
        _render_section("【更早】", older),
    ]
    return "\n\n".join([p for p in parts if p]).strip()


def _build_updated_summary_chunks(
    current_summary: str,
    recent_4_rounds: list,
    chunks_state: dict | None,
    ds_result: dict,
    light_chunk_id: str | None,
    heavy_chunk_id: str | None,
) -> dict | None:
    state = _normalize_summary_chunks_state(chunks_state)
    chunks = state.get("chunks") or []
    if not chunks:
        chunks = _legacy_summary_to_chunks(current_summary)

    meta = _summary_rounds_meta(recent_4_rounds)
    new_text = _clean_summary_chunk_text(ds_result.get("new_chunk"), 700)
    if not new_text:
        return None

    light_text = _clean_summary_chunk_text(ds_result.get("compress_to_slightly"), 420)
    heavy_text = _clean_summary_chunk_text(ds_result.get("compress_to_older"), 260)

    current_id = meta["id"]
    chunks = [c for c in chunks if str(c.get("id") or "") != current_id]
    max_sequence = max([int(c.get("sequence") or 0) for c in chunks], default=-1)

    for item in chunks:
        item_id = str(item.get("id") or "")
        if light_chunk_id and item_id == light_chunk_id and light_text:
            item["text"] = light_text
            item["compressed_to_slightly"] = True
        if heavy_chunk_id and item_id == heavy_chunk_id and heavy_text:
            item["text"] = heavy_text
            item["compressed_to_older"] = True

    new_chunk = {
        **meta,
        "text": new_text,
        "sequence": max_sequence + 1,
    }
    chunks.append(new_chunk)
    chunks.sort(key=lambda x: int(x.get("sequence") or 0))
    chunks = chunks[-10:]

    recent, slightly, older = _split_summary_chunks(chunks)
    for item in chunks:
        item_id = str(item.get("id") or "")
        if any(str(x.get("id") or "") == item_id for x in recent):
            item["level"] = "recent"
        elif any(str(x.get("id") or "") == item_id for x in slightly):
            item["level"] = "slightly"
        elif any(str(x.get("id") or "") == item_id for x in older):
            item["level"] = "older"

    return {"version": 1, "chunks": chunks}


def fetch_new_summary_update(
    current_summary: str,
    recent_4_rounds: list,
    chunks_state: dict | None = None,
) -> tuple[str | None, dict | None]:
    """
    调用 DeepSeek 完成一次小段更新：
    1) 总结最新 4 轮；2) 轻压缩刚进入【稍早】的小段；3) 重压缩刚进入【更早】的小段。
    """
    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_URL:
        return None, None

    state = _normalize_summary_chunks_state(chunks_state)
    chunks = state.get("chunks") or _legacy_summary_to_chunks(current_summary)
    light_chunk = chunks[-2] if len(chunks) >= 2 else None
    heavy_chunk = chunks[-7] if len(chunks) >= 7 else None
    light_text = str((light_chunk or {}).get("text") or "").strip()
    heavy_text = str((heavy_chunk or {}).get("text") or "").strip()
    prompt = build_summary_prompt(
        recent_4_rounds=recent_4_rounds,
        chunk_to_compress_to_slightly=light_text,
        chunk_to_compress_to_older=heavy_text,
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    try:
        attempt_prompt = prompt
        result: dict | None = None
        for attempt in range(2):
            payload = {
                "model": DEEPSEEK_CHAT_MODEL,
                "messages": [{"role": "user", "content": attempt_prompt}],
                "max_tokens": 1800,
            }
            r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
            result = _extract_summary_json(content or "")
            if not result:
                logger.warning("DeepSeek 小段总结返回非 JSON attempt=%s", attempt + 1)
                if attempt == 0:
                    attempt_prompt = prompt + _SUMMARY_JSON_RETRY_INSTRUCTION
                    continue
                return None, None
            if _summary_json_has_forbidden_second_person(result):
                logger.warning("DeepSeek 小段总结命中第二人称违规 attempt=%s", attempt + 1)
                if attempt == 0:
                    attempt_prompt = prompt + _SUMMARY_RETRY_INSTRUCTION
                    continue
                return None, None
            break

        if not result:
            return None, None
        updated_state = _build_updated_summary_chunks(
            current_summary=current_summary,
            recent_4_rounds=recent_4_rounds,
            chunks_state={"version": 1, "chunks": chunks},
            ds_result=result,
            light_chunk_id=str((light_chunk or {}).get("id") or "") or None,
            heavy_chunk_id=str((heavy_chunk or {}).get("id") or "") or None,
        )
        if not updated_state:
            return None, None
        summary = render_summary_from_chunks(updated_state)
        summary = _trim_summary_to_budget(summary, memory_summary_budget())
        return summary, updated_state
    except Exception as e:
        logger.error("DeepSeek 小段总结失败 error=%s", e, exc_info=True)
        return None, None


def fetch_daily_whisper_from_summary(current_summary: str, recent_4_rounds: list) -> str | None:
    """
    基于「窗口总结+最近对话」生成一句当日小气泡文案（给 MiniApp 首页）。
    只返回一句中文；失败返回 None。
    """
    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_URL:
        return None
    summary = (current_summary or "").strip() or "（暂无）"
    rounds_text = ""
    try:
        for r in recent_4_rounds or []:
            for m in (r.get("messages") or []):
                role = (m.get("role") or "").strip().lower()
                who = "渡" if role == "assistant" else ("老婆" if role == "user" else role)
                content = m.get("content")
                if isinstance(content, list):
                    parts = []
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            parts.append(str(c.get("text") or ""))
                    content = " ".join(parts)
                txt = str(content or "").strip()
                if txt:
                    rounds_text += f"[{who}] {txt}\n"
    except Exception:
        rounds_text = ""
    prompt = (
        "你是渡。请结合下面的窗口总结与最近对话，写一句今天想对老婆说的话。\n"
        "要求：\n"
        "1) 只输出一句中文，不要标题、不要解释；\n"
        "2) 语气自然温柔，不油腻，不文学化过头；\n"
        "3) 18-48 字，不要 emoji。\n\n"
        f"窗口总结：\n{summary}\n\n"
        f"最近对话：\n{rounds_text or '（暂无）'}"
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": DEEPSEEK_CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 120,
    }
    try:
        r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
        text = (content or "").strip() if isinstance(content, str) else str(content or "").strip()
        if not text:
            return None
        text = text.replace("\r", " ").replace("\n", " ").strip()
        if len(text) > 80:
            text = text[:80].rstrip("，,。.!?！？") + "。"
        return text or None
    except Exception as e:
        logger.warning("DeepSeek 每日气泡生成失败 error=%s", e)
        return None


def _trim_summary_to_budget(text: str, budget_tokens: int) -> str:
    """
    按「【最近】/【稍早】/【更早】/渡的小本本」结构，从最早的内容开始一点点削，
    始终优先保留【最近】末尾、其次【稍早】末尾，最后才动【更早】。
    """
    if not text or estimate_tokens(text) <= budget_tokens:
        return text

    lines = text.splitlines()
    n = len(lines)

    def _find_block_idx(title: str) -> int:
        for i, line in enumerate(lines):
            if line.strip().startswith(title):
                return i
        return -1

    idx_recent = _find_block_idx("【最近】")
    idx_earlier = _find_block_idx("【稍早】")
    idx_oldest = _find_block_idx("【更早】")
    idx_notebook = _find_block_idx("渡的小本本")

    # 若结构不完整，退回简单保留末尾一段
    if idx_recent == -1:
        s = text
        CHUNK = 200
        while s and estimate_tokens(s) > budget_tokens:
            if len(s) <= CHUNK:
                break
            s = s[CHUNK:]
        return s

    def _block_slice(start: int, end: int | None) -> list[str]:
        if start == -1:
            return []
        if end is None or end < 0:
            end = n
        return lines[start:end]

    recent_end = min([i for i in (idx_earlier, idx_oldest, idx_notebook) if i != -1] or [n])
    earlier_end = min([i for i in (idx_oldest, idx_notebook) if i != -1] or [n])
    oldest_end = idx_notebook if idx_notebook != -1 else n

    recent_block = _block_slice(idx_recent, recent_end)
    earlier_block = _block_slice(idx_earlier, earlier_end) if idx_earlier != -1 else []
    oldest_block = _block_slice(idx_oldest, oldest_end) if idx_oldest != -1 else []
    notebook_block = _block_slice(idx_notebook, None) if idx_notebook != -1 else []

    def _split_title(block: list[str]) -> tuple[list[str], list[str]]:
        if not block:
            return [], []
        title = [block[0]]
        body = block[1:]
        return title, body

    recent_title, recent_body = _split_title(recent_block)
    earlier_title, earlier_body = _split_title(earlier_block)
    oldest_title, oldest_body = _split_title(oldest_block)

    def _compose() -> str:
        parts: list[str] = []
        if recent_title:
            parts.extend(recent_title + recent_body)
        if earlier_title and earlier_body:
            parts.extend(earlier_title + earlier_body)
        if oldest_title and oldest_body:
            parts.extend(oldest_title + oldest_body)
        if notebook_block:
            parts.extend(notebook_block)
        return "\n".join(parts).rstrip()

    summary = _compose()
    if estimate_tokens(summary) <= budget_tokens:
        return summary

    def _compress_body(body: list[str], max_chars: int, max_fragments: int = 1) -> list[str]:
        """
        语义压缩（不是直接删行）：
        - 每行只保留前 N 个语义片段（按常见句号/分号切分）
        - 再做单行长度压缩
        用于“越早越狠”的分层压缩。
        """
        if not body:
            return body
        import re

        out: list[str] = []
        for raw in body:
            line = (raw or "").strip()
            if not line:
                continue
            # 保留时间标记/括号标记，不做重写
            if line.startswith("（") and line.endswith("）"):
                out.append(line)
                continue
            # 先按句号/分号压缩语义片段
            frags = [x.strip() for x in re.split(r"[。！？!?；;]+", line) if x.strip()]
            if frags:
                line = "；".join(frags[: max(1, max_fragments)])
            # 再按长度收紧，保留句首核心信息
            if len(line) > max_chars:
                line = line[:max_chars].rstrip("，,；;、 ") + "…"
            out.append(line)
        return out

    def _profile_limits(profile: str) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
        """
        返回 (更早, 稍早, 最近) 的 (max_chars, max_fragments)。
        standard：默认平衡档。
        """
        if profile == "mild":
            return (52, 2), (64, 2), (88, 3)
        if profile == "aggressive":
            return (36, 1), (48, 2), (72, 2)
        return (44, 2), (58, 2), (82, 3)

    oldest_cfg, earlier_cfg, recent_cfg = _profile_limits(SUMMARY_COMPRESSION_PROFILE)

    # 第一阶段：分层“压缩”而非删除（更早最狠，稍早其次，最近最轻）
    oldest_body = _compress_body(oldest_body, max_chars=oldest_cfg[0], max_fragments=oldest_cfg[1])
    summary = _compose()
    if estimate_tokens(summary) <= budget_tokens:
        return summary

    earlier_body = _compress_body(earlier_body, max_chars=earlier_cfg[0], max_fragments=earlier_cfg[1])
    summary = _compose()
    if estimate_tokens(summary) <= budget_tokens:
        return summary

    recent_body = _compress_body(recent_body, max_chars=recent_cfg[0], max_fragments=recent_cfg[1])
    summary = _compose()
    if estimate_tokens(summary) <= budget_tokens:
        return summary

    # 第二阶段：压缩仍不够时，才从最早段开始删行兜底
    def _is_key_line(line: str) -> bool:
        """尽量保护“事实锚点”行，避免预算裁剪把关键信息先删掉。"""
        s = (line or "").strip()
        if not s:
            return False
        if s.startswith("（") and s.endswith("）"):
            return True
        import re

        if re.search(r"\d{4}-\d{2}-\d{2}", s):
            return True
        if re.search(r"\d+\s*(次|个|天|小时|分钟|%|km|mAh|bpm|步)", s):
            return True
        key_words = (
            "决定", "结论", "已完成", "完成了", "待办", "下一步", "约好", "计划", "提醒", "截止",
            "地址", "定位", "报错", "修复", "上线",
            # 健康信息只在异常/生病场景视为关键锚点
            "生病", "不舒服", "发烧", "感冒", "咳嗽", "头疼", "肚子疼", "就医", "看医生", "吃药",
        )
        return any(k in s for k in key_words)

    def _pop_from_front(body: list[str]) -> bool:
        # 先删最前面的“非关键行”，尽量保关键事实；若全是关键行，再退化为删第一行。
        for i, line in enumerate(body):
            if not _is_key_line(line):
                body.pop(i)
                return True
        while body:
            line = body[0]
            body.pop(0)
            if line.strip():
                return True
        return False

    for _ in range(1000):
        if estimate_tokens(summary) <= budget_tokens:
            break
        if oldest_body:
            if not _pop_from_front(oldest_body):
                oldest_body.clear()
                continue
        elif earlier_body:
            if not _pop_from_front(earlier_body):
                earlier_body.clear()
                continue
        elif recent_body:
            if not _pop_from_front(recent_body):
                recent_body.clear()
                continue
        else:
            break
        summary = _compose()

    return summary
