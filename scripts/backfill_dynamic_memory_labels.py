"""
给现有动态层记忆回填 emotion_label / scene_type / target_type。

只改三个标签字段，不改：
- id
- content
- retrieval_text
- importance
- mention_count
- created_at
- last_mentioned

用法：
  .venv/bin/python scripts/backfill_dynamic_memory_labels.py --dry-run
  .venv/bin/python scripts/backfill_dynamic_memory_labels.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL
from storage import r2_store
from utils.log import get_logger

logger = get_logger(__name__)

_PROMPT = """你在给“动态记忆”补三个稳定标签。

只看这条记忆正文本身，不要脑补额外上下文。

标签定义：
1. emotion_label：只标这条记忆里“当前/latest”的态度
- positive
- negative
- neutral

2. scene_type：这条记忆主要在做什么，只能选一个
- problem_solving
- learning
- planning
- emotional_venting
- heart_to_heart
- casual_chat
- affection
- conflict

3. target_type：这条记忆主要在说谁/什么，只能选一个
- external_tools
- self_state
- work_career
- our_project
- our_relationship
- about_me
- third_party_people
- other_topic

规则：
- 只返回 JSON，不要解释
- 不要改写记忆正文
- 如果拿不准，emotion_label 选 neutral，scene_type / target_type 选最贴近主线的一个

输入是一组记忆，每条有 id 和 content。

请对每条都输出标签，不要漏项，不要改 id。

输入：
{items_json}

输出格式：
[
  {{
    "id": "原样返回",
    "emotion_label": "positive / negative / neutral",
    "scene_type": "problem_solving / learning / planning / emotional_venting / heart_to_heart / casual_chat / affection / conflict",
    "target_type": "external_tools / self_state / work_career / our_project / our_relationship / about_me / third_party_people / other_topic"
  }}
]
"""

_EMOTION = {"positive", "negative", "neutral"}
_SCENE = {
    "problem_solving",
    "learning",
    "planning",
    "emotional_venting",
    "heart_to_heart",
    "casual_chat",
    "affection",
    "conflict",
}
_TARGET = {
    "external_tools",
    "self_state",
    "work_career",
    "our_project",
    "our_relationship",
    "about_me",
    "third_party_people",
    "other_topic",
}


def _extract_json(text: str) -> Optional[dict]:
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    if "```" in s:
        for start in ("```json", "```"):
            if start in s:
                idx = s.find(start) + len(start)
                s = s[idx:].lstrip()
            if "```" in s:
                s = s[: s.find("```")].strip()
            break
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    end = -1
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None
    try:
        return json.loads(s[start : end + 1])
    except Exception:
        return None


def _extract_json_array(text: str) -> Optional[list]:
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    if "```" in s:
        for start in ("```json", "```"):
            if start in s:
                idx = s.find(start) + len(start)
                s = s[idx:].lstrip()
            if "```" in s:
                s = s[: s.find("```")].strip()
            break
    start = s.find("[")
    if start < 0:
        return None
    depth = 0
    end = -1
    for i in range(start, len(s)):
        if s[i] in ("[", "{"):
            depth += 1
        elif s[i] in ("]", "}"):
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None
    try:
        return json.loads(s[start : end + 1])
    except Exception:
        return None


def _call_ds_labels(batch: list[dict]) -> dict[str, dict]:
    if not DEEPSEEK_API_KEY or not DEEPSEEK_API_URL:
        return {}
    items = [{"id": str(it.get("id") or ""), "content": str(it.get("content") or "").strip()} for it in batch if str(it.get("id") or "").strip() and str(it.get("content") or "").strip()]
    if not items:
        return {}
    prompt = _PROMPT.format(items_json=json.dumps(items, ensure_ascii=False))
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": min(1200, max(300, 110 * len(items))),
    }
    for attempt in range(2):
        try:
            r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            content_text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            arr = _extract_json_array(str(content_text))
            out: dict[str, dict] = {}
            for obj in arr or []:
                if not isinstance(obj, dict):
                    continue
                mid = str(obj.get("id") or "").strip()
                emotion = str(obj.get("emotion_label") or "").strip().lower()
                scene = str(obj.get("scene_type") or "").strip()
                target = str(obj.get("target_type") or "").strip()
                if emotion in _EMOTION and scene in _SCENE and target in _TARGET:
                    out[mid] = {
                        "emotion_label": emotion,
                        "scene_type": scene,
                        "target_type": target,
                    }
            if out:
                return out
        except Exception as e:
            logger.warning("backfill labels failed attempt=%s error=%s", attempt + 1, e)
            time.sleep(0.8)
    return {}


def _needs_backfill(mem: dict) -> bool:
    if not isinstance(mem, dict):
        return False
    if not str(mem.get("content") or "").strip():
        return False
    emotion = str(mem.get("emotion_label") or "").strip()
    scene = str(mem.get("scene_type") or "").strip()
    target = str(mem.get("target_type") or "").strip()
    return not (emotion and scene and target)


def main() -> int:
    parser = argparse.ArgumentParser(description="回填动态层旧记忆的三个标签")
    parser.add_argument("--dry-run", action="store_true", help="只统计和预览，不写回")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少条，0 表示全部")
    parser.add_argument("--sleep", type=float, default=0.25, help="每条之间休眠秒数")
    parser.add_argument("--save-every", type=int, default=20, help="正式写回时每处理多少条落盘一次")
    parser.add_argument("--batch-size", type=int, default=10, help="每次请求 DS 处理多少条")
    args = parser.parse_args()

    memories = r2_store.get_dynamic_memory_list() or []
    targets = [m for m in memories if _needs_backfill(m)]
    if args.limit and args.limit > 0:
        targets = targets[: args.limit]

    changed = 0
    failed = 0
    processed = 0
    preview: list[dict] = []
    failed_ids: list[str] = []
    mem_by_id = {str((m or {}).get("id") or ""): m for m in memories if isinstance(m, dict)}

    batch_size = max(1, int(args.batch_size or 10))
    for start in range(0, len(targets), batch_size):
        batch = targets[start : start + batch_size]
        result_map = _call_ds_labels(batch)
        processed += len(batch)
        for mem in batch:
            mid = str(mem.get("id") or "").strip()
            content = str(mem.get("content") or "").strip()
            result = result_map.get(mid)
            if not result:
                failed += 1
                if mid:
                    failed_ids.append(mid)
                continue
            target = mem_by_id.get(mid)
            if not target:
                failed += 1
                if mid:
                    failed_ids.append(mid)
                continue
            target["emotion_label"] = result["emotion_label"]
            target["scene_type"] = result["scene_type"]
            target["target_type"] = result["target_type"]
            changed += 1
            if len(preview) < 10:
                preview.append({
                    "id": mid,
                    "emotion_label": result["emotion_label"],
                    "scene_type": result["scene_type"],
                    "target_type": result["target_type"],
                    "content": content[:80],
                })
        if (not args.dry_run) and args.save_every > 0 and processed % int(args.save_every) == 0:
            r2_store.save_dynamic_memory_list(memories)
        if args.sleep > 0:
            time.sleep(float(args.sleep))
        if processed % 20 == 0:
            logger.info("backfill labels progress=%s/%s changed=%s failed=%s", processed, len(targets), changed, failed)

    out = {
        "total_memories": len(memories),
        "targets": len(targets),
        "processed": processed,
        "changed": changed,
        "failed": failed,
        "preview": preview,
        "failed_ids": failed_ids[:30],
        "saved": False,
    }

    if not args.dry_run and changed > 0:
        out["saved"] = bool(r2_store.save_dynamic_memory_list(memories))

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
