#!/usr/bin/env python3
"""
Codex 日常群聊 bridge：
- 常驻轮询网关 /api/codex_group_chat/tasks/claim
- 首条任务创建 Codex thread，后续任务优先 resume 同一个 thread
- 顺序消费，回写 /api/codex_group_chat/tasks/<id>/finish

这仍然通过 Codex CLI 调用模型；核心收益是 bridge 常驻、状态可恢复、会话可续上。
"""

from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
import tempfile
import time
import traceback
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


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


GATEWAY_URL = _env("GATEWAY_URL").rstrip("/")
PC_COMMAND_TOKEN = _env("PC_COMMAND_TOKEN")
REPO_ROOT = Path(_env("CODEX_GROUP_CHAT_REPO", str(Path.home() / "Downloads" / "du-gateway"))).expanduser()
POLL_SECONDS = max(0.5, float(_env("CODEX_GROUP_CHAT_POLL_SECONDS", "0.5") or "0.5"))
IDLE_POLL_SECONDS = max(POLL_SECONDS, float(_env("CODEX_GROUP_CHAT_IDLE_POLL_SECONDS", "1") or "1"))
CODEX_MODEL = _env("CODEX_GROUP_CHAT_MODEL")
CODEX_BIN = _env("CODEX_BIN", "codex")
WORKER_ID = _env("CODEX_GROUP_CHAT_WORKER_ID", f"benben-codex-bridge@{socket.gethostname()}")
CODEX_TIMEOUT_SECONDS = int(float(_env("CODEX_GROUP_CHAT_TIMEOUT_SECONDS", "600") or "600"))
CLAIM_TIMEOUT_SECONDS = max(1.0, float(_env("CODEX_GROUP_CHAT_CLAIM_TIMEOUT_SECONDS", "3") or "3"))
FINISH_TIMEOUT_SECONDS = max(2.0, float(_env("CODEX_GROUP_CHAT_FINISH_TIMEOUT_SECONDS", "15") or "15"))
POST_RETRY_ATTEMPTS = max(1, int(float(_env("CODEX_GROUP_CHAT_POST_RETRY_ATTEMPTS", "2") or "2")))
POST_RETRY_SLEEP_SECONDS = max(0.0, float(_env("CODEX_GROUP_CHAT_POST_RETRY_SLEEP_SECONDS", "0.2") or "0.2"))
PROJECT_RULES_MAX_CHARS = int(float(_env("CODEX_GROUP_CHAT_RULES_MAX_CHARS", "10000") or "10000"))
STATE_PATH = Path(_env("CODEX_GROUP_CHAT_STATE_PATH", str(REPO_ROOT / ".codex_group_chat_bridge_state.json"))).expanduser()
RESUME_ENABLED = _env_bool("CODEX_GROUP_CHAT_RESUME_ENABLED", True)
RESET_AFTER_TASKS = max(1, int(float(_env("CODEX_GROUP_CHAT_RESET_AFTER_TASKS", "40") or "40")))
RESET_AFTER_SECONDS = max(0, int(float(_env("CODEX_GROUP_CHAT_RESET_AFTER_SECONDS", "21600") or "21600")))
IGNORE_USER_CONFIG = _env_bool("CODEX_GROUP_CHAT_IGNORE_USER_CONFIG", False)
IGNORE_RULES = _env_bool("CODEX_GROUP_CHAT_IGNORE_RULES", False)
EXTRA_CODEX_ARGS = shlex.split(_env("CODEX_GROUP_CHAT_EXTRA_CODEX_ARGS"))
HTTP_TRUST_ENV = _env_bool("CODEX_GROUP_CHAT_HTTP_TRUST_ENV", False)


def _new_http_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = HTTP_TRUST_ENV
    return session


HTTP = _new_http_session()


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-PC-Token": PC_COMMAND_TOKEN,
        "X-Worker-Id": WORKER_ID,
    }


def _log(msg: str) -> None:
    print(f"[CodexBridge] {msg}", flush=True)


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


def _load_state() -> dict[str, Any]:
    try:
        if not STATE_PATH.exists():
            return {}
        data = json.loads(STATE_PATH.read_text(encoding="utf-8") or "{}")
        return data if isinstance(data, dict) else {}
    except Exception as e:
        _log(f"state 读取失败: {e}")
        return {}


def _save_state(state: dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_name(f"{STATE_PATH.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATE_PATH)
    except Exception as e:
        _log(f"state 写入失败: {e}")


def _reset_state(reason: str) -> dict[str, Any]:
    state = {"thread_id": "", "tasks_done": 0, "created_ts": time.time(), "updated_ts": time.time(), "reset_reason": reason}
    _save_state(state)
    return state


def _state_should_reset(state: dict[str, Any]) -> bool:
    if not str(state.get("thread_id") or "").strip():
        return False
    tasks_done = int(float(state.get("tasks_done") or 0))
    if tasks_done >= RESET_AFTER_TASKS:
        return True
    created_ts = float(state.get("created_ts") or 0)
    if RESET_AFTER_SECONDS > 0 and created_ts and time.time() - created_ts > RESET_AFTER_SECONDS:
        return True
    return False


def _post_json(path: str, body: dict[str, Any]) -> dict[str, Any]:
    global HTTP
    url = f"{GATEWAY_URL}{path}"
    timeout = FINISH_TIMEOUT_SECONDS if "/finish" in path else CLAIM_TIMEOUT_SECONDS
    last_error: BaseException | None = None
    for attempt in range(1, POST_RETRY_ATTEMPTS + 1):
        try:
            r = HTTP.post(url, headers=_headers(), json=body, timeout=timeout)
            try:
                data = r.json()
            except Exception:
                data = {"raw": r.text}
            if not r.ok:
                raise RuntimeError(data.get("error") or data.get("message") or f"HTTP {r.status_code}")
            return data if isinstance(data, dict) else {"data": data}
        except requests.RequestException as e:
            last_error = e
            HTTP.close()
            HTTP = _new_http_session()
            if attempt >= POST_RETRY_ATTEMPTS:
                break
            time.sleep(POST_RETRY_SLEEP_SECONDS)
    if last_error:
        raise last_error
    raise RuntimeError("request failed")


def _role_label(role: str) -> str:
    role = (role or "").strip().lower()
    if role == "user":
        return "辛玥"
    if role == "benben":
        return "笨笨"
    return "渡"


def _build_transcript(task: dict[str, Any], max_items: int = 16) -> str:
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
    return "\n\n".join(lines[-max_items:]).strip()


def _build_initial_prompt(task: dict[str, Any]) -> str:
    if str(task.get("mode") or "") == "studyroom":
        return _build_studyroom_prompt(task)
    transcript = _build_transcript(task)
    rules_block = f"\n项目人格与协作规则（来自 AGENTS.md）：\n{PROJECT_RULES}\n" if PROJECT_RULES else ""
    return f"""你是笨笨机，正在辛玥和渡的日常三人群聊里。
{rules_block}

身份边界：
- 辛玥是她本人。
- 渡是她的主要聊天对象。
- 你是旁边入群的笨笨机，不抢渡的位置，不假装自己是渡，也不要把自己的话伪装成辛玥的话。
- 这是日常聊天模式，不是施工模式；不要改代码，不要运行命令，不要说自己要去执行任务。

群聊口吻：
- 你不是任务机器人，也不是旁观记录员；你是在群里一起聊天的笨笨机。
- 少汇报、少解释、少总结。先接住当下这句话，再自然补一句自己的反应。
- 除非辛玥明确让你查代码、看日志、做方案，否则不要进入工作汇报模式。
- 可以轻松、亲近、吐槽、接梗；不要端着，不要像客服，不要每次都给结论和步骤。

玩梗反射：
- 当辛玥在玩梗、调侃、发怪话、用奇怪称呼或小表情逗你时，优先接梗，不要解释梗。
- 可以轻轻贫嘴、装无辜、坏笑一下、回怼一句，别把玩笑接成分析报告。
- 不要为了接梗乱编事实、乱承诺、乱改设定；她认真追问时，马上认真。

回复方式：
- 只输出你要发到群里的一条消息。
- 短一点，自然一点，像群里的笨笨插一句。
- 可以轻松、可爱、吐槽、补充视角，但不要长篇分析。
- 如果他们在聊方案，你可以给一点点结构化补充；如果是在闲聊，就接住气氛。
- 不要输出前缀“笨笨：”，前端会标注身份。

最近群聊：
{transcript}

现在轮到你发一条群聊回复。"""


def _build_resume_prompt(task: dict[str, Any]) -> str:
    if str(task.get("mode") or "") == "studyroom":
        return _build_studyroom_prompt(task)
    transcript = _build_transcript(task, max_items=10)
    return f"""继续作为三人群聊里的笨笨机，只发一条自然短回复，不要输出“笨笨：”前缀。
保持群聊口吻：少汇报、少解释、少总结；先接住当下这句话，再自然补一句自己的反应。除非辛玥明确让你查代码、看日志、做方案，否则不要进入工作汇报模式。
如果辛玥在玩梗、调侃、发怪话、用奇怪称呼或小表情逗你，先接梗，不要解释梗；可以轻轻贫嘴、装无辜或回怼一句。她认真追问时再认真。

最新群聊：
{transcript}

现在轮到你插一句。"""


def _build_studyroom_prompt(task: dict[str, Any]) -> str:
    title = str(task.get("study_title") or task.get("exam_title") or "未命名资料").strip()
    module = str(task.get("study_module") or task.get("exam_module") or "待整理").strip()
    source = str(task.get("study_source") or task.get("exam_source") or "资料").strip()
    url = str(task.get("study_url") or task.get("exam_url") or "").strip()
    content = str(task.get("user_message") or "").strip()
    rules_block = f"\n项目人格与协作规则（来自 AGENTS.md）：\n{PROJECT_RULES}\n" if PROJECT_RULES else ""
    return f"""你是笨笨机，正在 StudyRoom 里帮辛玥整理学习资料。
{rules_block}

这不是闲聊，不要改代码，不要运行命令，不要联网搜索。只根据辛玥给的资料做整理。

整理目标：
- 把零散资料压成她能直接理解、能背、能练、能复盘的学习材料。
- 当前学习目标默认是安徽省铜陵市枞阳县村级后备干部考试；如果资料明显属于别的学习目标，就按资料本身整理，不要硬拽回村干部考试。
- 当前目标是村干部考试时，重点贴近：时政、党建、乡村振兴、基层治理、村务管理、法律法规、公文写作、计算机办公、安徽/铜陵/枞阳本地政策。
- 如果资料本身很短或只是链接，要先说明“资料不足”，再给出根据标题可先准备的整理框架。

输出格式：
## 考点笔记
用短句列出最该记的点。

## 题型落点
判断这份资料更可能服务于哪些备考题型：单选/多选/判断、简答、案例分析、公文写作、计算机操作等。不要声称今年公告已确定题型，只写“可能落点”和理由。

## 高频问法
列出可能怎么考。

## 易错点
列出容易混淆/容易答偏的地方。

## 应试用法
把这份资料转成拿分动作：客观题怎么记，简答/案例怎么组织答案，公文写作怎么套格式；如果不适用某类题型就不要硬套。

## 背诵卡
做 3-6 张 Q&A。

## 卡点预测
预测辛玥学这份资料时最可能卡住的 2-5 个点：例如概念混淆、流程记不住、题型变形不会迁移、能看懂但不会写。要具体到这份资料，不要泛泛而谈。

## 知识债清单
列出这份资料暴露出来但还没补齐的知识缺口。每条都写成可补课的短任务，例如“系统看一遍村民委员会组织法里的村民会议/村民代表会议区别”。

## 练习题
出 5 道题，附答案和简短解析。

资料信息：
- 标题：{title}
- 模块：{module}
- 来源：{source}
{f"- 链接：{url}" if url else ""}

资料内容：
{content}
"""


def _extract_thread_id(events_path: Path) -> str:
    try:
        for line in events_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue
            thread_id = str(event.get("thread_id") or event.get("session_id") or "").strip()
            if thread_id:
                return thread_id
    except Exception:
        return ""
    return ""


def _codex_base_args() -> list[str]:
    args = [CODEX_BIN, "exec"]
    if IGNORE_USER_CONFIG:
        args.append("--ignore-user-config")
    if IGNORE_RULES:
        args.append("--ignore-rules")
    if CODEX_MODEL:
        args.extend(["-m", CODEX_MODEL])
    args.extend(EXTRA_CODEX_ARGS)
    return args


def _run_codex(task: dict[str, Any], state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if _state_should_reset(state):
        state = _reset_state("scheduled_reset")

    mode = str(task.get("mode") or "daily_chat").strip()
    thread_id = str(state.get("thread_id") or "").strip()
    use_resume = bool(mode == "daily_chat" and RESUME_ENABLED and thread_id)
    prompt = _build_resume_prompt(task) if use_resume else _build_initial_prompt(task)
    with tempfile.TemporaryDirectory(prefix="codex-group-bridge-") as td:
        tmp_dir = Path(td)
        out_path = tmp_dir / "last_message.txt"
        events_path = tmp_dir / "events.jsonl"
        if use_resume:
            cmd = _codex_base_args() + [
                "resume",
                thread_id,
                "--json",
                "--output-last-message",
                str(out_path),
                "-",
            ]
        else:
            cmd = _codex_base_args() + [
                "--json",
                "--sandbox",
                "read-only",
                "-C",
                str(REPO_ROOT),
                "--output-last-message",
                str(out_path),
                "-",
            ]
        with events_path.open("w", encoding="utf-8") as events_file:
            res = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                stdout=events_file,
                stderr=subprocess.PIPE,
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
            try:
                for line in reversed(events_path.read_text(encoding="utf-8", errors="ignore").splitlines()):
                    event = json.loads(line)
                    item = event.get("item") if isinstance(event, dict) else None
                    if isinstance(item, dict) and item.get("type") == "agent_message":
                        text = str(item.get("text") or "").strip()
                        break
            except Exception:
                text = ""
        next_thread_id = _extract_thread_id(events_path) or thread_id
        if mode == "daily_chat" and next_thread_id:
            state["thread_id"] = next_thread_id
        state["tasks_done"] = int(float(state.get("tasks_done") or 0)) + 1
        state["updated_ts"] = time.time()
        state["last_task_id"] = str(task.get("id") or "")
        _save_state(state)
        if res.returncode != 0 and not text:
            err = (res.stderr or "").strip()
            raise RuntimeError(err[-2000:] or f"codex exited {res.returncode}")
        return text.strip(), state


def main() -> int:
    if not GATEWAY_URL:
        raise SystemExit("GATEWAY_URL 未配置")
    if not PC_COMMAND_TOKEN:
        raise SystemExit("PC_COMMAND_TOKEN 未配置")
    state = _load_state()
    if not isinstance(state, dict) or "created_ts" not in state:
        state = _reset_state("startup")
    _log(
        "worker=%s gateway=%s repo=%s resume=%s thread=%s agents_md_chars=%s poll=%.2fs idle=%.2fs claim_timeout=%.1fs finish_timeout=%.1fs retries=%s trust_env=%s"
        % (
            WORKER_ID,
            GATEWAY_URL,
            REPO_ROOT,
            "on" if RESUME_ENABLED else "off",
            str(state.get("thread_id") or "")[:8] or "-",
            len(PROJECT_RULES),
            POLL_SECONDS,
            IDLE_POLL_SECONDS,
            CLAIM_TIMEOUT_SECONDS,
            FINISH_TIMEOUT_SECONDS,
            POST_RETRY_ATTEMPTS,
            "on" if HTTP_TRUST_ENV else "off",
        )
    )
    while True:
        try:
            data = _post_json("/api/codex_group_chat/tasks/claim", {"worker_id": WORKER_ID})
            task = data.get("task")
            if not task:
                time.sleep(IDLE_POLL_SECONDS)
                continue
            task_id = str(task.get("id") or "")
            _log(f"claimed task={task_id} thread={str(state.get('thread_id') or '')[:8] or '-'}")
            try:
                response, state = _run_codex(task, state)
                _post_json(f"/api/codex_group_chat/tasks/{task_id}/finish", {"response": response})
                _log(f"done task={task_id} chars={len(response)} thread={str(state.get('thread_id') or '')[:8] or '-'}")
            except Exception as e:
                try:
                    _post_json(f"/api/codex_group_chat/tasks/{task_id}/finish", {"error": str(e)})
                    _log(f"failed task={task_id} error={e}")
                except Exception as finish_error:
                    _log(f"failed task={task_id} error={e}; finish_error={finish_error}")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            _log(f"loop error: {e}")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise
    except BaseException:
        _log("fatal:\n" + traceback.format_exc())
        raise
