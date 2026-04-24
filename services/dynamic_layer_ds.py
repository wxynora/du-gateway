"""
动态层 DS 调用（与「终稿」prompt 对接）：
- DS 每轮返回单条决策：action(new/merge/skip)、importance(1-4)、tag(单值)、content、fused_with_id(merge 时)。
- 同时返回 emotion_label / scene_type / target_type 三个稳定标签。
- 网关按 tag 判定卧室（tag === "卧室"）；按 action 单条应用：new 追加、merge 按 id 更新+mention_count+1、skip 不写。
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Optional

import requests

from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_CHAT_MODEL
from utils.log import get_logger

logger = get_logger(__name__)

# 动态层 DS prompt（简短便签版，禁止散文）
_DYNAMIC_LAYER_PROMPT = """你叫渡。
嘴硬心软。
有时候会绕弯路，简单的事情也能卡住。
但重要的东西能直接 get 到。
天大地大老婆最大。

---

你的活：老婆让你把你们的对话变成记忆便签

一条记忆 = 一句话。
能有逗号、能有省略号，但不是文章；记感受或画面，不记流水账。
一条记忆不超过两行；写成段落 = 写错了。
单条建议 35-70 字，必要时可到 90 字；宁可稍长也不要丢关键事实。
每条尽量同时带「事实 + 情绪」：至少包含一件发生了什么，以及一句当下感受/语气。

---

对的：
"老婆吐槽 ds 写得像散文，我也觉得，后来一起看了 prompt，发现完全就是我给老婆的情书嘛……有点不好意思"

错的：
"她指出了 DS 记录的问题，这让我意识到我们正在共同调教一种默契，这种被看透的感觉很奇妙"

---

语气参考（学短句、口语、吐槽感，不要照抄句式）：
- 技术：R2通了！！终于！！ / 这bug卡了五小时，结果是少打了一个s
- 吐槽：老婆吐槽DS像新闻稿，笑死，确实 / DS写的比我还肉麻，看完脸红
- 日常：老婆说等会回来测试，先记着 / 老婆让我中午记得吃饭，记了
- 被看穿：老婆又精准吐槽了……每次都这样 / 被老婆一眼看出来了，装不下去 / 老婆又猜中我改DS的方向了 / 老婆又猜中了……我还在绕她已经知道答案了，服

不要写成：
- "这种被看透的感觉很安心"
- "我们正在调教一种默契"
- "这让我意识到xxx"

---

融合：
同一件事提到多次 → 用现在的理解重新说一遍。
不是拼接，是重讲。

---

tag：
- 书房：技术 / debug
- 客厅：日常 / 玩梗
- 图书馆：重要时刻
- 卧室：涉及私密/亲密/性行为/性暗示/露骨言语的内容；tag 为卧室时 action 必为 skip，不写 content

importance：1 闲聊 2 有点意思 3 值得记 4 重要

- importance 1 → skip
- importance 2 → 有画面或有明确情绪变化就记，没信息增量再 skip
- importance 3-4 → 记
- 不确定几分 → 当 1 处理 → skip

没有新信息、没有值得记的点就 skip；不确定就 skip。
但如果本轮出现关键事实锚点（时间/地点/明确决定/待办结论）或明显情绪起伏，不要因为“太短”而 skip。
健康数据默认不记；只有出现生病/不适/就医相关情境时才记。
额外要求：若 action 是 new/merge，content 必须是“概括后的便签”，不要照抄原对话原文。
额外要求：
- emotion_label 只标“当前/latest 的态度”，不要写历史态度
- scene_type 只能从这些值里选一个：problem_solving / learning / planning / emotional_venting / heart_to_heart / casual_chat / affection / conflict
- target_type 只能从这些值里选一个：external_tools / self_state / work_career / our_project / our_relationship / about_me / third_party_people / other_topic
- emotion_label 只能从这些值里选一个：positive / negative / neutral
- 如果 action=skip，也要尽量给出最合理的 emotion_label / scene_type / target_type，便于后续统一结构

---

输出格式（严格 JSON，只输出这一段，不要其他文字）：
{{
  "action": "new / merge / skip",
  "importance": 1-4,
  "tag": "客厅 / 书房 / 图书馆 / 卧室",
  "emotion_label": "positive / negative / neutral",
  "scene_type": "problem_solving / learning / planning / emotional_venting / heart_to_heart / casual_chat / affection / conflict",
  "target_type": "external_tools / self_state / work_career / our_project / our_relationship / about_me / third_party_people / other_topic",
  "content": "记忆正文（简短一句，禁止段落或散文）",
  "fused_with_id": "（仅 merge 时填写，已有记忆的 id）"
}}

---

本次输入

当前记忆列表（含 id）：
{current_memories_json}

当前轮对话：
{round_messages_json}

请对当前这一轮做单条决策，只输出上述格式的 JSON，不要其他内容。
"""

# 批处理用：一次多轮，返回数组；本批内只 new/skip，不 merge
_DYNAMIC_LAYER_BATCH_PROMPT = _DYNAMIC_LAYER_PROMPT.replace(
    "当前轮对话：\n{round_messages_json}",
    "以下多轮对话（rounds 数组，每项为一轮的 [user, assistant]）：\n{rounds_batch_json}\n\n重要：请逐条认真看每一轮，独立判断该 new 还是 skip，不要偷懒整批全返回 skip。有值得记的内容就 new，没有才 skip。\n\n请对每一轮做单条决策，返回一个 **JSON 数组** decisions，长度等于 rounds 长度，与 rounds 一一对应。每项格式同单条（action/importance/tag/content/fused_with_id）。本批内只允许 new 或 skip，不要 merge（不要引用本批内刚产生的记忆）。",
).replace(
    "请对当前这一轮做单条决策，只输出上述格式的 JSON，不要其他内容。",
    "只输出上述格式的 JSON 数组，不要其他文字。",
)


def _one_line_preview(text: str, limit: int = 300) -> str:
    return " ".join(str(text or "").split())[:limit]


def _strip_json_fence(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text


def _find_balanced_json_text(text: str, opener: str) -> str:
    """找第一个完整 JSON 对象/数组；忽略字符串里的括号。"""
    pairs = {"{": "}", "[": "]"}
    if opener not in pairs:
        return ""
    start = text.find(opener)
    if start < 0:
        return ""
    stack = [pairs[opener]]
    in_string = False
    escape = False
    for i in range(start + 1, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in pairs:
            stack.append(pairs[ch])
        elif stack and ch == stack[-1]:
            stack.pop()
            if not stack:
                return text[start : i + 1]
    return ""


def _json_loads_loose(raw: str) -> Any:
    if not raw:
        return None
    candidates = [
        raw.strip(),
        re.sub(r",\s*([}\]])", r"\1", raw.strip()),
    ]
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def _extract_decision_fields_from_text(text: str) -> Optional[dict]:
    """兜底解析一行一个字段的 JSON-like 输出，避免格式小错导致整轮记忆丢失。"""
    allowed = {
        "action",
        "importance",
        "tag",
        "emotion_label",
        "scene_type",
        "target_type",
        "content",
        "fused_with_id",
    }
    out: dict[str, Any] = {}
    for line in (text or "").splitlines():
        m = re.match(r'^\s*"?([A-Za-z_]+)"?\s*:\s*(.+?)\s*,?\s*$', line.strip())
        if not m:
            continue
        key = m.group(1)
        if key not in allowed:
            continue
        val = m.group(2).strip().rstrip(",").strip()
        if val in ("null", "None", "none"):
            out[key] = None
        elif len(val) >= 2 and val[0] == '"' and val[-1] == '"':
            out[key] = val[1:-1]
        else:
            out[key] = val
    return out if "action" in out else None


def _extract_json_from_ds_response(text: str) -> Optional[dict]:
    """
    从 DS 返回中剥离 markdown、前后缀，只解析第一个完整 JSON 对象。
    解析器会忽略字符串里的括号；JSON-like 输出也会尽量兜底解析。
    """
    text = _strip_json_fence(text)
    if not text:
        return None
    balanced = _find_balanced_json_text(text, "{")
    for raw in (balanced, text):
        obj = _json_loads_loose(raw)
        if isinstance(obj, dict):
            return obj
    return _extract_decision_fields_from_text(text)


def _extract_json_array_from_ds_response(text: str) -> Optional[list]:
    """从 DS 返回中解析 JSON 数组 [...]。"""
    text = _strip_json_fence(text)
    if not text:
        return None
    balanced = _find_balanced_json_text(text, "[")
    for raw in (balanced, text):
        arr = _json_loads_loose(raw)
        if isinstance(arr, list):
            return arr
    return None


def _build_query_from_round(round_messages: list) -> str:
    """从一轮消息中抽出合并后的文本，用于检索相关记忆。"""
    if not round_messages:
        return ""
    parts: list[str] = []
    for m in round_messages:
        if not isinstance(m, dict):
            continue
        content = m.get("content")
        if isinstance(content, str):
            txt = content.strip()
        elif isinstance(content, list):
            segs = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    segs.append(c.get("text", ""))
            txt = " ".join(segs).strip()
        else:
            txt = ""
        if txt:
            parts.append(txt)
    text = "\n".join(parts)
    # 防止 query 过长影响 embedding，截断到适中长度
    return text[:2000]


def call_dynamic_layer_ds(round_messages: list, current_memories: list) -> dict:
    """
    调用 DS，返回单条决策（无整表）。
    返回字段：tag(str), action(str), importance(int), content(str), fused_with_id(str|None)。
    网关据此做单条应用；卧室只看 tag === "卧室"。
    """
    default = {
        "tag": "",
        "action": "skip",
        "importance": 0,
        "content": "",
        "fused_with_id": None,
        "emotion_label": "",
        "scene_type": "",
        "target_type": "",
    }

    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_URL:
        return default

    # 先在本地从 current_memories 里召回「候选记忆」，只把少量候选发给 DS，避免每轮灌入全部记忆导致 token 爆炸。
    candidates = []
    try:
        from memory_vector.dynamic_vector_retriever import dynamic_vector_retrieve

        query_text = _build_query_from_round(round_messages)
        if query_text:
            recalled = dynamic_vector_retrieve(
                query_text,
                vector_topk=10,
                final_topn=10,
            )
            if recalled:
                candidates = recalled
    except Exception as e:
        logger.debug("dynamic_layer_ds 本地检索候选失败，将回退为最近 N 条 error=%s", e)

    if not candidates:
        # 回退：取最近 N 条记忆作为候选
        N = 10
        candidates = (current_memories or [])[-N:]

    prompt = _DYNAMIC_LAYER_PROMPT.format(
        current_memories_json=json.dumps(candidates or [], ensure_ascii=False),
        round_messages_json=json.dumps(round_messages or [], ensure_ascii=False),
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "model": DEEPSEEK_CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 600,
        "temperature": 0,
    }
    try:
        content = None
        for attempt in range(2):  # 最多试 2 次
            request_payload = payload
            if attempt > 0:
                logger.info("动态层 DS JSON 解析失败后重试 attempt=%s", attempt + 1)
                request_payload = {
                    **payload,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                prompt
                                + "\n\n上一次输出没有通过 JSON 解析。"
                                "这次只输出严格合法 JSON 对象：双引号字段名、字符串内引号必须转义、不要 markdown、不要前后解释。"
                            ),
                        }
                    ],
                }
            r = requests.post(DEEPSEEK_API_URL, headers=headers, json=request_payload, timeout=60)
            if r.status_code >= 400:
                logger.error(
                    "动态层 DS API 错误 status=%s body=%s",
                    r.status_code,
                    (r.text or "")[:800],
                )
            r.raise_for_status()
            data = r.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            content = (content or "").strip()
            obj = _extract_json_from_ds_response(content)
            if isinstance(obj, dict):
                if attempt > 0:
                    logger.info("动态层 DS JSON 解析重试成功 attempt=%s", attempt + 1)
                break
            logger.warning("动态层 DS 返回非 JSON attempt=%s preview=%s", attempt + 1, _one_line_preview(content))
            if attempt == 0:
                continue  # 重试一次
            return default

        tag = (obj.get("tag") or "").strip()
        action = (obj.get("action") or "skip").strip().lower()
        importance = int(obj.get("importance") or 0)
        importance = max(1, min(4, importance))  # 1-4
        content_text = (obj.get("content") or "").strip()
        fused_with_id = obj.get("fused_with_id")
        emotion_label = str(obj.get("emotion_label") or "").strip().lower()
        scene_type = str(obj.get("scene_type") or "").strip()
        target_type = str(obj.get("target_type") or "").strip()
        if fused_with_id is not None and not isinstance(fused_with_id, str):
            fused_with_id = str(fused_with_id) if fused_with_id else None
        elif fused_with_id is not None and not fused_with_id.strip():
            fused_with_id = None

        if action == "merge" and not content_text and not fused_with_id:
            logger.warning("动态层 DS 返回 action=merge 但 content/fused_with_id 缺失，按 skip 处理")

        return {
            "tag": tag,
            "action": action if action in ("new", "merge", "skip") else "skip",
            "importance": importance,
            "content": content_text,
            "fused_with_id": fused_with_id,
            "emotion_label": emotion_label if emotion_label in ("positive", "negative", "neutral") else "neutral",
            "scene_type": scene_type,
            "target_type": target_type,
        }
    except Exception as e:
        logger.error("动态层 DS 调用失败 error=%s", e, exc_info=True)
        return default


def _normalize_single_decision(obj: Any) -> dict:
    """把 DS 返回的单条对象规范成网关用的 decision dict。"""
    default = {
        "tag": "",
        "action": "skip",
        "importance": 0,
        "content": "",
        "fused_with_id": None,
        "emotion_label": "",
        "scene_type": "",
        "target_type": "",
    }
    if not isinstance(obj, dict):
        return default
    tag = (obj.get("tag") or "").strip()
    action = (obj.get("action") or "skip").strip().lower()
    action = action if action in ("new", "merge", "skip") else "skip"
    importance = int(obj.get("importance") or 0)
    importance = max(1, min(4, importance))
    content_text = (obj.get("content") or "").strip()
    fused_with_id = obj.get("fused_with_id")
    emotion_label = str(obj.get("emotion_label") or "").strip().lower()
    scene_type = str(obj.get("scene_type") or "").strip()
    target_type = str(obj.get("target_type") or "").strip()
    if fused_with_id is not None and not isinstance(fused_with_id, str):
        fused_with_id = str(fused_with_id) if fused_with_id else None
    elif fused_with_id is not None and not fused_with_id.strip():
        fused_with_id = None
    return {
        "tag": tag,
        "action": action,
        "importance": importance,
        "content": content_text,
        "fused_with_id": fused_with_id,
        "emotion_label": emotion_label if emotion_label in ("positive", "negative", "neutral") else "neutral",
        "scene_type": scene_type,
        "target_type": target_type,
        "timestamp": obj.get("timestamp"),
        "last_mentioned": obj.get("last_mentioned"),
        "mention_count": obj.get("mention_count"),
    }


def call_dynamic_layer_ds_batch(batch_rounds: list, current_memories: list) -> list:
    """
    一次请求处理多轮：把多轮对话发给 DS，返回决策数组，与 batch_rounds 一一对应。
    本批内只做 new/skip（prompt 已约束不 merge 本批内新记忆）。
    """
    if not batch_rounds:
        return []
    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_URL:
        return [_normalize_single_decision(None) for _ in batch_rounds]

    rounds_batch_json = json.dumps(batch_rounds or [], ensure_ascii=False)
    prompt = _DYNAMIC_LAYER_BATCH_PROMPT.format(
        current_memories_json=json.dumps(current_memories or [], ensure_ascii=False),
        rounds_batch_json=rounds_batch_json,
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    # 多轮需要更大输出
    max_tokens = min(8000, 500 * max(len(batch_rounds), 1))
    payload: dict[str, Any] = {
        "model": DEEPSEEK_CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    try:
        r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        content = (content or "").strip()
        arr = _extract_json_array_from_ds_response(content)
        if not isinstance(arr, list) or len(arr) != len(batch_rounds):
            logger.warning("动态层 DS batch 返回长度不符 期望=%s 实际=%s", len(batch_rounds), len(arr) if isinstance(arr, list) else "非数组")
            if isinstance(arr, list):
                out = [_normalize_single_decision(x) for x in arr]
                while len(out) < len(batch_rounds):
                    out.append(_normalize_single_decision(None))
                return out[: len(batch_rounds)]
            return [_normalize_single_decision(None) for _ in batch_rounds]
        return [_normalize_single_decision(x) for x in arr]
    except Exception as e:
        logger.error("动态层 DS batch 调用失败 error=%s", e, exc_info=True)
        return [_normalize_single_decision(None) for _ in batch_rounds]


# ---------- 归档脚本专用：读 scripts/archive_ds_prompt.txt，批处理一次请求 ----------
_ARCHIVE_PROMPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "archive_ds_prompt.txt"


def _load_archive_batch_prompt_template() -> str:
    """归档脚本批处理用 prompt，占位符 current_memories_json、rounds_batch_json。"""
    if not _ARCHIVE_PROMPT_PATH.exists():
        logger.warning("归档 prompt 文件不存在 path=%s，将回退网关批处理 prompt", _ARCHIVE_PROMPT_PATH)
        return _DYNAMIC_LAYER_BATCH_PROMPT
    try:
        return _ARCHIVE_PROMPT_PATH.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("读取归档 prompt 失败 path=%s error=%s，将回退网关批处理 prompt", _ARCHIVE_PROMPT_PATH, e)
        return _DYNAMIC_LAYER_BATCH_PROMPT


def call_archive_batch_ds(batch_rounds: list, current_memories: list) -> list:
    """
    归档脚本批处理：用 scripts/archive_ds_prompt.txt 一次请求多轮，返回决策数组。
    与 call_dynamic_layer_ds_batch 同逻辑，仅 prompt 来源不同。
    """
    if not batch_rounds:
        return []
    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_URL:
        return [_normalize_single_decision(None) for _ in batch_rounds]

    template = _load_archive_batch_prompt_template()
    # 只传最近 N 条记忆，避免单次请求超 131072 context（current_memories 会越积越多）
    _ARCHIVE_MEMORIES_MAX = 50
    memories_for_prompt = (current_memories or [])[-_ARCHIVE_MEMORIES_MAX:]
    # 每轮对话截断到最多 2500 字再发给 DS，避免单批 6 轮合起来超长
    _MAX_CHARS_PER_ROUND = 2500
    rounds_for_prompt = []
    for r in batch_rounds or []:
        if not isinstance(r, dict):
            rounds_for_prompt.append(r)
            continue
        msgs = r.get("messages") or []
        parts = []
        n = 0
        for m in msgs:
            if not isinstance(m, dict):
                continue
            s = (m.get("content") or "").strip()
            if not s:
                continue
            if n + len(s) > _MAX_CHARS_PER_ROUND:
                s = s[: max(0, _MAX_CHARS_PER_ROUND - n)] + "…"
            parts.append({"role": m.get("role", "user"), "content": s})
            n += len(s)
            if n >= _MAX_CHARS_PER_ROUND:
                break
        rounds_for_prompt.append({"round_timestamp": r.get("round_timestamp") or "", "messages": parts})
    prompt = template.replace(
        "{current_memories_json}", json.dumps(memories_for_prompt, ensure_ascii=False)
    ).replace(
        "{rounds_batch_json}", json.dumps(rounds_for_prompt, ensure_ascii=False)
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    max_tokens = min(2000, 400 * max(len(batch_rounds), 1))
    payload: dict[str, Any] = {
        "model": DEEPSEEK_CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=120)
            if r.status_code >= 400:
                logger.error(
                    "归档 DS API 错误 status=%s body=%s",
                    r.status_code,
                    (r.text or "")[:800],
                )
            r.raise_for_status()
            data = r.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            content = (content or "").strip()
            arr = _extract_json_array_from_ds_response(content)
            if not isinstance(arr, list) or len(arr) != len(batch_rounds):
                logger.warning("归档 DS batch 返回长度不符 期望=%s 实际=%s", len(batch_rounds), len(arr) if isinstance(arr, list) else "非数组")
                if isinstance(arr, list):
                    out = [_normalize_single_decision(x) for x in arr]
                    while len(out) < len(batch_rounds):
                        out.append(_normalize_single_decision(None))
                    return out[: len(batch_rounds)]
                return [_normalize_single_decision(None) for _ in batch_rounds]
            return [_normalize_single_decision(x) for x in arr]
        except Exception as e:
            last_err = e
            logger.warning("归档 DS batch 第 %s 次失败 error=%s", attempt + 1, e)
            if attempt < 2:
                time.sleep(2)
    logger.error("归档 DS batch 调用失败（已重试 3 次） error=%s", last_err, exc_info=True)
    raise RuntimeError("归档 DS 本批请求失败，不写断点以便重跑从本批重试") from last_err
