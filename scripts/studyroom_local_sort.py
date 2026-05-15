#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT_PATH = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_PATH))

from storage import r2_store
from scripts.codex_group_chat_bridge import (
    CODEX_BIN,
    CODEX_MODEL,
    CODEX_TIMEOUT_SECONDS,
    REPO_ROOT,
    _build_studyroom_prompt,
    _studyroom_validation_error,
)


MATERIAL_SOURCE_TYPES = {"pdf", "word", "text", "note", "web", "bilibili"}
META_PREFIXES = (
    "本地 study 导入：",
    "资料状态：",
    "题库状态：",
    "自动拆分：",
    "文件类型：",
    "可判答案：",
)


def _has_study_result(note: str) -> bool:
    return any(
        heading in str(note or "")
        for heading in (
            "## 考点笔记",
            "## 题型落点",
            "## 高频问法",
            "## 易错点",
            "## 应试用法",
            "## 背诵卡",
            "## 卡点预测",
            "## 知识债清单",
            "## 练习题",
        )
    )


def _studyroom_meta(note: str) -> str:
    lines = []
    in_comment = False
    for raw in str(note or "").splitlines():
        line = raw.strip()
        if line.startswith("<!-- studyroom-meta"):
            in_comment = True
            continue
        if in_comment and line == "-->":
            in_comment = False
            continue
        if in_comment or any(line.startswith(prefix) for prefix in META_PREFIXES):
            if line and line != "-->":
                lines.append(line)
    deduped = []
    for line in lines:
        if line not in deduped:
            deduped.append(line)
    return "\n".join(deduped)


def _merge_note(result: str, old_note: str) -> str:
    clean = str(result or "").strip()
    meta = _studyroom_meta(old_note)
    if not meta:
        return clean
    return f"{clean}\n\n<!-- studyroom-meta\n{meta}\n-->".strip()


def _codex_text_from_events(events_path: Path) -> str:
    try:
        for line in reversed(events_path.read_text(encoding="utf-8", errors="ignore").splitlines()):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue
            item = event.get("item") if isinstance(event, dict) else None
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = str(item.get("text") or "").strip()
                if text:
                    return text
    except Exception:
        return ""
    return ""


def _run_codex_local(prompt: str, timeout: int) -> str:
    with tempfile.TemporaryDirectory(prefix="studyroom-local-sort-") as td:
        tmp_dir = Path(td)
        out_path = tmp_dir / "last_message.txt"
        events_path = tmp_dir / "events.jsonl"
        cmd = [os.environ.get("CODEX_BIN") or CODEX_BIN or "codex", "exec"]
        model = os.environ.get("STUDYROOM_LOCAL_SORT_MODEL") or CODEX_MODEL
        if model:
            cmd.extend(["-m", model])
        cmd.extend(
            [
                "--json",
                "--sandbox",
                "read-only",
                "-C",
                str(REPO_ROOT),
                "--output-last-message",
                str(out_path),
                "-",
            ]
        )
        with events_path.open("w", encoding="utf-8") as events_file:
            res = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                stdout=events_file,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        text = out_path.read_text(encoding="utf-8").strip() if out_path.exists() else ""
        if not text:
            text = _codex_text_from_events(events_path)
        if res.returncode != 0 and not text:
            err = (res.stderr or "").strip()
            raise RuntimeError(err[-2000:] or f"codex exited {res.returncode}")
        return text.strip()


def _select_items(data: dict, args: argparse.Namespace) -> list[dict]:
    modules = set(args.module or [])
    sources = set(args.source_type or MATERIAL_SOURCE_TYPES)
    item_ids = set(args.item_id or [])
    title_contains = str(args.title_contains or "").strip()
    out = []
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        if item_ids and str(item.get("id") or "") not in item_ids:
            continue
        if not item_ids:
            if str(item.get("source_type") or "") not in sources:
                continue
            if modules and str(item.get("module_id") or "") not in modules:
                continue
            if title_contains and title_contains not in str(item.get("title") or ""):
                continue
            if not args.include_done and (_has_study_result(str(item.get("note") or "")) or str(item.get("status") or "") == "done"):
                continue
        if not str(item.get("content") or item.get("url") or "").strip():
            continue
        out.append(item)
    limit = None if args.all else max(1, int(args.limit or 1))
    return out if limit is None else out[:limit]


def _task_for_item(item: dict, modules: dict[str, str]) -> dict[str, Any]:
    content_parts = [
        str(item.get("content") or "").strip(),
        str(item.get("url") or "").strip(),
    ]
    return {
        "mode": "studyroom",
        "study_item_id": item.get("id") or "",
        "study_title": item.get("title") or "",
        "study_module": modules.get(str(item.get("module_id") or ""), "待整理"),
        "study_source": item.get("source_type") or "",
        "study_url": item.get("url") or "",
        "user_message": "\n\n".join([x for x in content_parts if x]).strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="本地生成 StudyRoom 资料学习方向，绕过网关任务队列。")
    parser.add_argument("--limit", type=int, default=1, help="最多处理多少条，默认 1")
    parser.add_argument("--all", action="store_true", help="处理全部符合条件的条目")
    parser.add_argument("--item-id", action="append", help="只处理指定 StudyRoom item id，可重复")
    parser.add_argument("--module", action="append", help="只处理指定模块 id，可重复")
    parser.add_argument("--source-type", action="append", help="只处理指定 source_type，可重复；默认资料类")
    parser.add_argument("--title-contains", help="只处理标题包含指定文本的条目")
    parser.add_argument("--include-done", action="store_true", help="允许重跑已有整理结果/已完成条目")
    parser.add_argument("--dry-run", action="store_true", help="只打印将处理的条目")
    parser.add_argument("--timeout", type=int, default=CODEX_TIMEOUT_SECONDS, help="单条 Codex 超时时间秒")
    args = parser.parse_args()

    data = r2_store.get_studyroom_data()
    modules = {str((m or {}).get("id") or ""): str((m or {}).get("label") or "") for m in data.get("modules") or []}
    items = _select_items(data, args)
    print(f"selected={len(items)}")
    for index, item in enumerate(items, start=1):
        print(f"{index}. {item.get('title')} | {item.get('module_id')} | {item.get('source_type')} | {item.get('status')}")
    if args.dry_run or not items:
        return 0

    completed = 0
    for index, item in enumerate(items, start=1):
        item_id = str(item.get("id") or "")
        title = str(item.get("title") or "")
        print(f"\n[{index}/{len(items)}] sorting {title} ({item_id})", flush=True)
        r2_store.update_studyroom_item(item_id, {"status": "sorting"})
        try:
            prompt = _build_studyroom_prompt(_task_for_item(item, modules))
            text = _run_codex_local(prompt, timeout=max(60, int(args.timeout or CODEX_TIMEOUT_SECONDS)))
            validation_error = _studyroom_validation_error(text)
            if validation_error:
                raise RuntimeError(validation_error)
            note = _merge_note(text, str(item.get("note") or ""))
            r2_store.update_studyroom_item(item_id, {"note": note, "status": "done"})
            completed += 1
            print(f"[ok] {title}", flush=True)
        except Exception as exc:
            r2_store.update_studyroom_item(item_id, {"status": "todo"})
            print(f"[error] {title}: {exc}", flush=True)
            raise
    print(f"\ncompleted={completed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
