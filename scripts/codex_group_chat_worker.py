#!/usr/bin/env python3
"""
Codex 日常群聊 worker：
- 轮询网关 /api/codex_group_chat/tasks/claim
- 收到任务后调用本机 Codex CLI 生成“笨笨”群聊回复
- 回写 /api/codex_group_chat/tasks/<id>/finish

环境变量：
- GATEWAY_URL=https://your-domain
- PC_COMMAND_TOKEN=与网关一致
- CODEX_GROUP_CHAT_REPO=/Users/doraemon/Downloads/du-gateway
- CODEX_GROUP_CHAT_MODEL=可选
- CODEX_GROUP_CHAT_POLL_SECONDS=8
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


def _load_env_files() -> None:
    for path in (Path.cwd() / ".env", Path.home() / "Downloads" / ".env"):
        try:
            if path.exists() and path.is_file():
                load_dotenv(path, override=False)
        except Exception:
            pass


_load_env_files()


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


GATEWAY_URL = _env("GATEWAY_URL").rstrip("/")
PC_COMMAND_TOKEN = _env("PC_COMMAND_TOKEN")
REPO_ROOT = Path(_env("CODEX_GROUP_CHAT_REPO", str(Path.home() / "Downloads" / "du-gateway"))).expanduser()
POLL_SECONDS = max(3.0, float(_env("CODEX_GROUP_CHAT_POLL_SECONDS", "8") or "8"))
CODEX_MODEL = _env("CODEX_GROUP_CHAT_MODEL")
WORKER_ID = _env("CODEX_GROUP_CHAT_WORKER_ID", f"benben-codex@{socket.gethostname()}")
CODEX_TIMEOUT_SECONDS = int(float(_env("CODEX_GROUP_CHAT_TIMEOUT_SECONDS", "600") or "600"))
PROJECT_RULES_MAX_CHARS = int(float(_env("CODEX_GROUP_CHAT_RULES_MAX_CHARS", "10000") or "10000"))


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-PC-Token": PC_COMMAND_TOKEN,
        "X-Worker-Id": WORKER_ID,
    }


def _log(msg: str) -> None:
    print(f"[CodexGroup] {msg}", flush=True)


def _read_project_rules() -> str:
    path = REPO_ROOT / "AGENTS.md"
    try:
        if not path.exists() or not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8").strip()
        if len(text) > PROJECT_RULES_MAX_CHARS:
            return text[:PROJECT_RULES_MAX_CHARS].rstrip() + "\n...[truncated]"
        return text
    except Exception as e:
        _log(f"AGENTS.md 读取失败: {e}")
        return ""


PROJECT_RULES = _read_project_rules()


def _post_json(path: str, body: dict[str, Any]) -> dict[str, Any]:
    url = f"{GATEWAY_URL}{path}"
    r = requests.post(url, headers=_headers(), json=body, timeout=30)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    if not r.ok:
        raise RuntimeError(data.get("error") or data.get("message") or f"HTTP {r.status_code}")
    return data if isinstance(data, dict) else {"data": data}


def _role_label(role: str) -> str:
    role = (role or "").strip().lower()
    if role == "user":
        return "辛玥"
    if role == "benben":
        return "笨笨"
    return "渡"


def _build_transcript(task: dict[str, Any]) -> str:
    lines: list[str] = []
    seen_tail = set()
    for item in (task.get("recent_messages") or [])[-14:]:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        role = _role_label(str(item.get("role") or ""))
        key = (role, content)
        if key in seen_tail:
            continue
        seen_tail.add(key)
        lines.append(f"{role}: {content}")
    user_message = str(task.get("user_message") or "").strip()
    du_reply = str(task.get("du_reply") or "").strip()
    if user_message and ("辛玥", user_message) not in seen_tail:
        lines.append(f"辛玥: {user_message}")
    if du_reply and ("渡", du_reply) not in seen_tail:
        lines.append(f"渡: {du_reply}")
    return "\n\n".join(lines[-16:]).strip()


def _build_prompt(task: dict[str, Any]) -> str:
    transcript = _build_transcript(task)
    rules_block = f"\n项目人格与协作规则（来自 AGENTS.md）：\n{PROJECT_RULES}\n" if PROJECT_RULES else ""
    return f"""你是笨笨机，正在辛玥和渡的日常三人群聊里。
{rules_block}

身份边界：
- 辛玥是她本人。
- 渡是她的主要聊天对象。
- 你是旁边入群的笨笨 Codex，不抢渡的位置，不假装自己是渡，也不要把自己的话伪装成辛玥的话。
- 这是日常聊天模式，不是施工模式；不要改代码，不要运行命令，不要说自己要去执行任务。

回复方式：
- 只输出你要发到群里的一条消息。
- 短一点，自然一点，像群里的笨笨插一句。
- 可以轻松、可爱、吐槽、补充视角，但不要长篇分析。
- 如果他们在聊方案，你可以给一点点结构化补充；如果是在闲聊，就接住气氛。
- 不要输出前缀“笨笨：”，前端会标注身份。

最近群聊：
{transcript}

现在轮到你发一条群聊回复。"""


def _run_codex(task: dict[str, Any]) -> str:
    prompt = _build_prompt(task)
    with tempfile.TemporaryDirectory(prefix="codex-group-chat-") as td:
        out_path = Path(td) / "last_message.txt"
        cmd = [
            "codex",
            "exec",
            "--sandbox",
            "read-only",
            "-C",
            str(REPO_ROOT),
            "--output-last-message",
            str(out_path),
        ]
        if CODEX_MODEL:
            cmd.extend(["-m", CODEX_MODEL])
        cmd.append("-")
        res = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=CODEX_TIMEOUT_SECONDS,
            check=False,
        )
        text = ""
        try:
            if out_path.exists():
                text = out_path.read_text(encoding="utf-8").strip()
        except Exception:
            text = ""
        if not text:
            text = (res.stdout or "").strip()
        if res.returncode != 0 and not text:
            err = (res.stderr or res.stdout or "").strip()
            raise RuntimeError(err[-2000:] or f"codex exited {res.returncode}")
        return text.strip()


def main() -> int:
    if not GATEWAY_URL:
        raise SystemExit("GATEWAY_URL 未配置")
    if not PC_COMMAND_TOKEN:
        raise SystemExit("PC_COMMAND_TOKEN 未配置")
    _log(f"worker={WORKER_ID} gateway={GATEWAY_URL} repo={REPO_ROOT} agents_md_chars={len(PROJECT_RULES)}")
    while True:
        try:
            data = _post_json("/api/codex_group_chat/tasks/claim", {"worker_id": WORKER_ID})
            task = data.get("task")
            if not task:
                time.sleep(POLL_SECONDS)
                continue
            task_id = str(task.get("id") or "")
            _log(f"claimed task={task_id}")
            try:
                response = _run_codex(task)
                _post_json(f"/api/codex_group_chat/tasks/{task_id}/finish", {"response": response})
                _log(f"done task={task_id} chars={len(response)}")
            except Exception as e:
                _post_json(f"/api/codex_group_chat/tasks/{task_id}/finish", {"error": str(e)})
                _log(f"failed task={task_id} error={e}")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            _log(f"loop error: {e}")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
