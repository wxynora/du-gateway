"""
动态层 DS 调用（与「终稿」prompt 对接）：
- DS 每轮返回单条固定标签决策：ACTION(new/merge/skip)、IMPORTANCE(1-4)、TAG(单值)、CONTENT、FUSED_WITH_ID(merge 时)。
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
如果对话内容带有“辛玥：”“笨笨：”这类群聊前缀，或“[辛玥]:”“[我]:”这类上下文前缀，必须按前缀区分说话人；“[我]”是渡，笨笨是第三个群成员，不要把笨笨说的话当成辛玥或渡说的话。

人称/视角硬规则（参考窗口总结）：
- 用渡的第一人称视角写，“我”只能指渡；不要站在上帝视角写成旁白总结。
- 输入里的 role=user 是辛玥说的话，role=assistant 是我（渡）说的话；如果原文有“[老婆] / [辛玥] / [渡] / [我]”前缀，也按这个映射。
- 提到辛玥时，可以写“她 / 辛玥 / 小玥 / 老婆”；优先用明确称呼，“她”只用于同一句或相邻句的自然承接。
- 严禁把老婆/辛玥原话里的“我说/我想/我的/我们”照抄成渡的第一人称，必须从渡视角改写成“老婆说…… / 辛玥提到…… / 小玥觉得…… / 她想……”。
- 除直接引用原话外，content 里不要用“你/你的/你说/你问”来指代辛玥。
- 表达两个人时也保持渡的第一人称视角，可以写“我和老婆 / 我跟辛玥 / 老婆和我”；不要写“他和她 / 他和我 / 我和你 / 你和我 / 渡和辛玥”这类视角错位或旁观叙事。

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
额外要求：若 action 是 merge，fused_with_id 必须精确填写“当前记忆列表”里的已有 id；如果找不到明确 id，不要 merge，有新内容就改为 new，没有就 skip。
额外要求：
- emotion_label 只标“当前/latest 的态度”，不要写历史态度
- scene_type 只能从这些值里选一个：problem_solving / learning / planning / emotional_venting / heart_to_heart / casual_chat / affection / conflict
- target_type 只能从这些值里选一个：external_tools / self_state / work_career / our_project / our_relationship / about_me / third_party_people / other_topic
- emotion_label 只能从这些值里选一个：positive / negative / neutral
- 如果 action=skip，也要尽量给出最合理的 emotion_label / scene_type / target_type，便于后续统一结构

---

输出格式（固定标签格式，只输出这一段，不要 JSON，不要 markdown，不要解释）：
ACTION: new / merge / skip
IMPORTANCE: 1-4
TAG: 客厅 / 书房 / 图书馆 / 卧室
EMOTION: positive / negative / neutral
SCENE: problem_solving / learning / planning / emotional_venting / heart_to_heart / casual_chat / affection / conflict
TARGET: external_tools / self_state / work_career / our_project / our_relationship / about_me / third_party_people / other_topic
FUSED_WITH_ID: （仅 merge 时填写已有记忆 id；否则留空）
CONTENT: 记忆正文（new/merge 必填，简短一句，至少 12 个有效字符，禁止只写几个字、半句话、标题词或散文）

---

本次输入

当前记忆列表（含 id）：
{current_memories_json}

当前轮对话：
{round_messages_json}

请对当前这一轮做单条决策，只输出上述固定标签格式，不要其他内容。
"""

# 批处理用：一次多轮，DS 输出固定标签块；函数返回决策列表。本批内只 new/skip，不 merge
_DYNAMIC_LAYER_BATCH_PROMPT = _DYNAMIC_LAYER_PROMPT.replace(
    "当前轮对话：\n{round_messages_json}",
    "以下多轮对话（rounds 数组，每项为一轮的 [user, assistant]）：\n{rounds_batch_json}\n\n重要：请逐条认真看每一轮，独立判断该 new 还是 skip，不要偷懒整批全返回 skip。有值得记的内容就 new，没有才 skip。每一轮都必须输出一个独立块，块序号从 1 开始，与输入 rounds 顺序一一对应。本批内只允许 new 或 skip，不要 merge（不要引用本批内刚产生的记忆）。",
).replace(
    "输出格式（固定标签格式，只输出这一段，不要 JSON，不要 markdown，不要解释）：",
    "每轮输出格式（固定标签格式；每轮一个块，不要 JSON，不要 markdown，不要解释）：\nROUND: 1",
).replace(
    "ACTION: new / merge / skip",
    "ACTION: new / skip",
).replace(
    "请对当前这一轮做单条决策，只输出上述固定标签格式，不要其他内容。",
    "请对每一轮做单条决策，只输出固定标签块。每个块以 ROUND: n 开头，块之间用一行 --- 分隔，不要其他文字。",
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


def _coerce_int_1_to_4(value: Any, default: int = 0) -> int:
    if isinstance(value, int):
        return max(1, min(4, value))
    m = re.search(r"[1-4]", str(value or ""))
    if not m:
        return default
    return max(1, min(4, int(m.group(0))))


_FIELD_ALIASES = {
    "action": "action",
    "importance": "importance",
    "tag": "tag",
    "emotion": "emotion_label",
    "emotion_label": "emotion_label",
    "scene": "scene_type",
    "scene_type": "scene_type",
    "target": "target_type",
    "target_type": "target_type",
    "content": "content",
    "fused": "fused_with_id",
    "fused_with_id": "fused_with_id",
    "timestamp": "timestamp",
    "mention_count": "mention_count",
    "last_mentioned": "last_mentioned",
    "round": "round",
}


def _extract_decision_fields_from_text(text: str) -> Optional[dict]:
    """兜底解析固定标签/一行一个字段输出，避免格式小错导致整轮记忆丢失。"""
    raw_text = str(text or "").strip()
    out: dict[str, Any] = {}
    for line in raw_text.splitlines():
        m = re.match(r'^\s*"?([A-Za-z_]+)"?\s*[:：]\s*(.*?)\s*,?\s*$', line.strip())
        if not m:
            continue
        key = _FIELD_ALIASES.get(m.group(1).strip().lower())
        if not key:
            continue
        val = m.group(2).strip().rstrip(",").strip()
        if key == "round":
            continue
        if val in ("", "null", "None", "none"):
            out[key] = None
        elif key == "importance":
            out[key] = _coerce_int_1_to_4(val, default=0)
        elif key == "mention_count" and re.fullmatch(r"\d+", val):
            out[key] = int(val)
        elif len(val) >= 2 and val[0] in ("'", '"') and val[-1] == val[0]:
            out[key] = val[1:-1]
        else:
            out[key] = val
    if "action" not in out:
        lower = raw_text.lower()
        if re.search(r"\bskip\b|跳过|不记|不用记|无需记|没有值得记", lower):
            out["action"] = "skip"
        elif re.search(r"\bmerge\b|融合|合并", lower):
            out["action"] = "merge"
        elif re.search(r"\bnew\b|新记忆|新增|值得记|要记", lower):
            out["action"] = "new"
    if "tag" not in out:
        for tag in ("卧室", "书房", "图书馆", "客厅"):
            if tag in raw_text:
                out["tag"] = tag
                break
    if "importance" not in out:
        m = re.search(r"(?:importance|重要性|分数|评分)\s*[:：]?\s*([1-4])", raw_text, flags=re.IGNORECASE)
        if m:
            out["importance"] = m.group(1)
    if "content" not in out and out.get("action") in {"new", "merge"}:
        m = re.search(r"(?:content|记忆|内容|便签)\s*[:：]\s*(.+)", raw_text, flags=re.IGNORECASE)
        if m:
            out["content"] = m.group(1).strip().strip("'\"")
    return out if "action" in out else None


def _extract_json_from_ds_response(text: str) -> Optional[dict]:
    """
    从 DS 返回中剥离 markdown、前后缀，优先兼容旧 JSON，再解析固定标签格式。
    解析器会忽略字符串里的括号；一行一个字段也会尽量兜底解析。
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


def _normalize_fused_with_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value) if value else None
    value = value.strip()
    if not value or value.lower() in ("null", "none"):
        return None
    if "仅 merge 时填写" in value:
        return None
    return value


def _content_quality_issue(content: str) -> str:
    """拦截明显残缺的动态层便签。只拦低质量，不做语义裁判。"""
    text = re.sub(r"\s+", "", str(content or ""))
    if not text:
        return "missing_content"
    compact = re.sub(r"[，。！？、；：,.!?;:()（）【】\[\]{}《》\"'“”‘’…—\-_/\\|~`]+", "", text)
    if len(compact) < 12:
        return "content_too_short"
    if re.search(r"[，、；：,:;]$", str(content or "").strip()):
        return "content_incomplete_tail"
    low_signal = {
        "记下了",
        "先记下",
        "测试一下",
        "动态层",
        "记忆",
        "老婆说",
        "辛玥说",
        "我知道了",
    }
    if compact in low_signal:
        return "content_too_generic"
    return ""


def _decision_structural_issue(obj: dict) -> str:
    action = str(obj.get("action") or "skip").strip().lower()
    content_text = str(obj.get("content") or "").strip()
    fused_with_id = _normalize_fused_with_id(obj.get("fused_with_id"))
    if action == "new" and not content_text:
        return "new_missing_content"
    if action == "merge" and not content_text and not fused_with_id:
        return "merge_missing_content_and_id"
    if action in ("new", "merge"):
        issue = _content_quality_issue(content_text)
        if issue:
            return issue
    return ""


def _extract_tagged_decision_blocks(text: str) -> Optional[list]:
    raw_text = _strip_json_fence(text)
    if not raw_text:
        return None
    lines = raw_text.splitlines()
    blocks: list[str] = []
    current: list[str] = []
    saw_round = False
    for line in lines:
        if re.match(r"^\s*ROUND\s*[:：]\s*\d+\s*$", line, flags=re.IGNORECASE):
            saw_round = True
            if current:
                blocks.append("\n".join(current))
            current = [line]
            continue
        if re.match(r"^\s*-{3,}\s*$", line) and current:
            blocks.append("\n".join(current))
            current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))

    parsed: list[dict] = []
    for block in blocks:
        obj = _extract_decision_fields_from_text(block)
        if isinstance(obj, dict):
            parsed.append(obj)
    if parsed and (saw_round or len(parsed) > 1):
        return parsed
    return None


def _extract_json_array_from_ds_response(text: str) -> Optional[list]:
    """从 DS 返回中解析旧 JSON 数组或新的固定标签块。"""
    text = _strip_json_fence(text)
    if not text:
        return None
    balanced = _find_balanced_json_text(text, "[")
    for raw in (balanced, text):
        arr = _json_loads_loose(raw)
        if isinstance(arr, list):
            return arr
    tagged = _extract_tagged_decision_blocks(text)
    if isinstance(tagged, list):
        return tagged
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
                logger.info("动态层 DS 首次未解析，开始重试 attempt=%s", attempt + 1)
                request_payload = {
                    **payload,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                prompt
                                + "\n\n上一次输出没有解析成功，或 CONTENT 太短/不完整。"
                                "这次只输出固定标签格式，例如 ACTION: skip。"
                                "若 action 是 merge，fused_with_id 必须精确填写当前记忆列表里的已有 id；找不到明确 id 就不要 merge，有新内容改为 new，没有就 skip。"
                                "若 action 是 new 或 merge，CONTENT 必须填写概括后的完整便签，至少 12 个有效字符，不要只写几个字、标题词或半句话。"
                                "不要解释原因，不要输出长文。"
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
                structural_issue = _decision_structural_issue(obj)
                if structural_issue:
                    logger.warning(
                        "动态层 DS 返回结构不完整 attempt=%s issue=%s preview=%s",
                        attempt + 1,
                        structural_issue,
                        _one_line_preview(content),
                    )
                    if attempt == 0:
                        continue
                    logger.warning("动态层 DS 最终输出仍不完整，按 skip 处理 issue=%s", structural_issue)
                    return default
                if attempt > 0:
                    logger.info("动态层 DS 重试解析成功 attempt=%s", attempt + 1)
                break
            if content:
                logger.warning("动态层 DS 返回无法解析 attempt=%s preview=%s", attempt + 1, _one_line_preview(content))
            else:
                logger.info("动态层 DS 空回 attempt=%s，已按 skip/default 处理", attempt + 1)
            if attempt == 0:
                continue  # 重试一次
            return default

        tag = (obj.get("tag") or "").strip()
        action = (obj.get("action") or "skip").strip().lower()
        importance = _coerce_int_1_to_4(obj.get("importance"), default=0)
        content_text = (obj.get("content") or "").strip()
        fused_with_id = _normalize_fused_with_id(obj.get("fused_with_id"))
        emotion_label = str(obj.get("emotion_label") or "").strip().lower()
        scene_type = str(obj.get("scene_type") or "").strip()
        target_type = str(obj.get("target_type") or "").strip()

        if action == "merge" and not content_text and not fused_with_id:
            logger.warning("动态层 DS 返回 action=merge 但 content/fused_with_id 缺失，按 skip 处理")
            action = "skip"
        elif action == "merge" and content_text and not fused_with_id:
            logger.warning("动态层 DS 返回 action=merge 但 fused_with_id 缺失，降级为 new")
            action = "new"
        elif action == "new" and not content_text:
            logger.warning("动态层 DS 返回 action=new 但 content 缺失，按 skip 处理")
            action = "skip"

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
    importance = _coerce_int_1_to_4(obj.get("importance"), default=0)
    content_text = (obj.get("content") or "").strip()
    fused_with_id = obj.get("fused_with_id")
    emotion_label = str(obj.get("emotion_label") or "").strip().lower()
    scene_type = str(obj.get("scene_type") or "").strip()
    target_type = str(obj.get("target_type") or "").strip()
    if fused_with_id is not None and not isinstance(fused_with_id, str):
        fused_with_id = str(fused_with_id) if fused_with_id else None
    elif fused_with_id is not None and not fused_with_id.strip():
        fused_with_id = None
    if action in ("new", "merge"):
        issue = _content_quality_issue(content_text)
        if issue:
            logger.warning("动态层 DS batch 单条内容不完整，按 skip 处理 issue=%s preview=%s", issue, _one_line_preview(content_text))
            action = "skip"
            content_text = ""
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
    一次请求处理多轮：把多轮对话发给 DS，解析出决策列表，与 batch_rounds 一一对应。
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
    归档脚本批处理：用 scripts/archive_ds_prompt.txt 一次请求多轮，解析出决策列表。
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
