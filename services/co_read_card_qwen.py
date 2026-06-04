import json
import re
from typing import Any, Optional

import requests

from config import (
    CO_READ_CARD_API_KEY,
    CO_READ_CARD_API_URL,
    CO_READ_CARD_MODEL,
    CO_READ_CARD_TIMEOUT_SECONDS,
)
from utils.log import get_logger

logger = get_logger(__name__)


CO_READ_CARD_SYSTEM_PROMPT = """你是“共读读书卡片”的维护器，只负责整理剧情连续性，不扮演渡，不写聊天回复。

你的任务：根据旧读书卡片和本次完成的小节，输出新版读书卡片 JSON。

核心原则：
1. 只记录小说/书本内容的连续理解，不归档每一条聊天感想。
2. 最近 10 小节保留稍详细剧情；超过 10 小节的内容只沉淀为重要节点、人物状态、伏笔。
3. 不保存本小节原文，不长篇摘抄原文；必要引用必须很短。
4. 不要编造旧卡片和本小节没有提供的信息；不确定就写成疑问或留空。
5. 小玥/渡的标记和小节感想只作为判断重点的输入。只有它们影响剧情理解、人物关系、伏笔时，才写入 story_milestones / characters / open_questions。
6. story_recent 按 section_index 升序，只保留最近 10 个小节。每节 plot 约 200-400 字，保留事件、冲突、转折、人物关系变化。
7. story_milestones 是精选长期节点，不是追加日志。每次更新都要删除重复、已被 story_recent 覆盖、低价值、后续不再重要的条目；最多 12 条，每条 40-120 字。
8. characters 只保留仍会影响后续理解的关键人物。每个角色必须有 summary：一句话介绍这个人是谁/当前叙事作用，20-60 字。
9. 死亡、退场、功能已完成、明显只是一节内炮灰/路人的角色，后续不要继续保留在 characters；除非他的死亡/身份/线索会长期影响主线，此时写入 story_milestones，而不是留在 characters。
10. characters 建议 3-12 个，宁可少而准，不要把乘客、店员、临时敌人等无持续作用的人堆进去。
11. open_questions 只保留未解开的关键伏笔或问题；每次更新都要删除已解答、重复、太细碎、后续价值低的问题；最多 6 条。
12. 输出必须是严格 JSON 对象，不要 Markdown，不要代码块，不要解释。

JSON schema：
{
  "book_key": "string",
  "book_title": "string",
  "current_progress": "string",
  "story_recent": [
    {
      "section_index": 1,
      "range": "string",
      "plot": "string"
    }
  ],
  "story_milestones": [
    {
      "section_index": 1,
      "event": "string",
      "why_matters": "string"
    }
  ],
  "characters": [
    {
      "name": "string",
      "summary": "string",
      "status": "string",
      "known_facts": ["string"],
      "open_threads": ["string"]
    }
  ],
  "open_questions": ["string"],
  "du_understanding": "string"
}
"""


def _clip_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit] + "\n……（已截断）"


def _compact_mark(mark: dict) -> dict:
    return {
        "id": _clip_text(mark.get("id"), 80),
        "quote": _clip_text(mark.get("quote"), 240),
        "note": _clip_text(mark.get("note"), 240),
        "du_reply": _clip_text(mark.get("du_reply"), 360),
    }


def _extract_json_object(text: str) -> Optional[dict]:
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    start = raw.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(raw[start : i + 1])
                    return data if isinstance(data, dict) else None
                except Exception:
                    return None
    return None


def call_card_json_update(
    *,
    system_prompt: str,
    payload: dict,
    instruction: str,
    task_name: str = "卡片",
    temperature: float = 0.2,
) -> tuple[Optional[dict], str]:
    """Call the configured card-maintenance model and parse a JSON object."""
    if not (CO_READ_CARD_API_KEY and CO_READ_CARD_API_URL and CO_READ_CARD_MODEL):
        return None, "未配置 CO_READ_CARD_API_KEY / CO_READ_CARD_API_URL / CO_READ_CARD_MODEL"
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": instruction + "\n" + json.dumps(payload, ensure_ascii=False),
        },
    ]
    body = {
        "model": CO_READ_CARD_MODEL,
        "stream": False,
        "temperature": temperature,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {CO_READ_CARD_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            CO_READ_CARD_API_URL,
            headers=headers,
            json=body,
            timeout=max(10, int(CO_READ_CARD_TIMEOUT_SECONDS or 120)),
        )
    except Exception as e:
        logger.warning("%s模型调用失败 error=%s", task_name, e)
        return None, str(e)
    if resp.status_code >= 400:
        logger.warning("%s模型非 2xx status=%s body=%s", task_name, resp.status_code, resp.text[:500])
        return None, f"status={resp.status_code}"
    try:
        data = resp.json()
    except Exception as e:
        return None, f"响应不是 JSON: {e}"
    content = str((((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or "").strip()
    card = _extract_json_object(content)
    if not card:
        logger.warning("%s模型未返回可解析 JSON preview=%s", task_name, content[:500])
        return None, f"{task_name}模型未返回可解析 JSON"
    return card, ""


def build_co_read_card_update(
    *,
    old_card: dict,
    book: dict,
    section: dict,
    section_text: str,
) -> tuple[Optional[dict], str]:
    user_marks = section.get("user_marks") if isinstance(section.get("user_marks"), list) else []
    du_marks = section.get("du_marks") if isinstance(section.get("du_marks"), list) else []
    payload = {
        "old_card": old_card if isinstance(old_card, dict) else {},
        "current_section": {
            "book_key": str(book.get("book_key") or ""),
            "book_title": str(book.get("book_title") or ""),
            "section_index": int(section.get("index") or 1),
            "section_count": len(book.get("sections") or []),
            "range": str(section.get("range") or ""),
            "progress": str(section.get("progress") or ""),
            "current_progress": str(section.get("current_progress") or ""),
            "section_label": str(section.get("label") or ""),
            "char_start": int(section.get("char_start") or 0),
            "char_end": int(section.get("char_end") or 0),
            "text": _clip_text(section_text, 60000),
            "user_marks": [_compact_mark(x) for x in user_marks if isinstance(x, dict)][:20],
            "user_section_note": _clip_text(section.get("user_section_note"), 2000),
            "du_marks": [_compact_mark(x) for x in du_marks if isinstance(x, dict)][:20],
            "du_section_note": _clip_text(section.get("du_section_note"), 2400),
        },
    }
    card, err = call_card_json_update(
        system_prompt=CO_READ_CARD_SYSTEM_PROMPT,
        payload=payload,
        instruction="请根据下面 JSON 更新读书卡片，只返回新版读书卡片 JSON：",
        task_name="共读卡片千问",
        temperature=0.2,
    )
    if not card:
        return None, err
    card["book_key"] = str(book.get("book_key") or card.get("book_key") or "")
    card["book_title"] = str(book.get("book_title") or card.get("book_title") or "")
    return card, ""
