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
import re
import shlex
import signal
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
CODING_RESUME_ENABLED = _env_bool("CODEX_GROUP_CHAT_CODING_RESUME_ENABLED", True)
CODING_SANDBOX = _env("CODEX_GROUP_CHAT_CODING_SANDBOX", "workspace-write") or "workspace-write"
RESET_AFTER_TASKS = max(1, int(float(_env("CODEX_GROUP_CHAT_RESET_AFTER_TASKS", "40") or "40")))
RESET_AFTER_SECONDS = max(0, int(float(_env("CODEX_GROUP_CHAT_RESET_AFTER_SECONDS", "21600") or "21600")))
IGNORE_USER_CONFIG = _env_bool("CODEX_GROUP_CHAT_IGNORE_USER_CONFIG", False)
IGNORE_RULES = _env_bool("CODEX_GROUP_CHAT_IGNORE_RULES", False)
EXTRA_CODEX_ARGS = shlex.split(_env("CODEX_GROUP_CHAT_EXTRA_CODEX_ARGS"))
HTTP_TRUST_ENV = _env_bool("CODEX_GROUP_CHAT_HTTP_TRUST_ENV", False)
STUDYROOM_MIN_RESPONSE_CHARS = max(
    500,
    int(float(_env("CODEX_GROUP_CHAT_STUDYROOM_MIN_CHARS", "800") or "800")),
)
STUDYROOM_REQUIRED_HEADINGS = (
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


def _new_http_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = HTTP_TRUST_ENV
    return session


HTTP = _new_http_session()


class TaskCancelled(RuntimeError):
    pass


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


def _coding_thread_key(task: dict[str, Any]) -> str:
    key = str(task.get("coding_thread_key") or "").strip().lower()
    key = re.sub(r"[^a-z0-9_.:-]", "_", key)[:80].strip("_")
    return key or "general"


def _coding_bucket(state: dict[str, Any], key: str) -> dict[str, Any]:
    threads = state.setdefault("coding_threads", {})
    if not isinstance(threads, dict):
        threads = {}
        state["coding_threads"] = threads
    bucket = threads.setdefault(key, {})
    if not isinstance(bucket, dict):
        bucket = {}
        threads[key] = bucket
    if key == "general" and not bucket.get("thread_id") and state.get("coding_thread_id"):
        bucket["thread_id"] = state.get("coding_thread_id")
        bucket["tasks_done"] = state.get("coding_tasks_done", 0)
        bucket["created_ts"] = state.get("coding_created_ts") or state.get("created_ts") or time.time()
        bucket["updated_ts"] = state.get("coding_updated_ts") or state.get("updated_ts") or time.time()
    return bucket


def _reset_coding_state(state: dict[str, Any], key: str, reason: str) -> dict[str, Any]:
    state = dict(state or {})
    now = time.time()
    bucket = _coding_bucket(state, key)
    bucket.update({
        "thread_id": "",
        "tasks_done": 0,
        "created_ts": now,
        "updated_ts": now,
        "reset_reason": reason,
    })
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


def _coding_state_should_reset(state: dict[str, Any], key: str) -> bool:
    bucket = _coding_bucket(state, key)
    if not str(bucket.get("thread_id") or "").strip():
        return False
    tasks_done = int(float(bucket.get("tasks_done") or 0))
    if tasks_done >= RESET_AFTER_TASKS:
        return True
    created_ts = float(bucket.get("created_ts") or 0)
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


def _get_json(path: str) -> dict[str, Any]:
    global HTTP
    url = f"{GATEWAY_URL}{path}"
    try:
        r = HTTP.get(url, headers=_headers(), timeout=CLAIM_TIMEOUT_SECONDS)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if not r.ok:
            raise RuntimeError(data.get("error") or data.get("message") or f"HTTP {r.status_code}")
        return data if isinstance(data, dict) else {"data": data}
    except requests.RequestException:
        HTTP.close()
        HTTP = _new_http_session()
        raise


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


def _build_group_trigger_note(task: dict[str, Any]) -> str:
    mentions = {
        str(item or "").strip().lower()
        for item in (task.get("target_mentions") or [])
        if str(item or "").strip()
    }
    if "benben" not in mentions:
        return ""
    if str(task.get("du_reply") or "").strip():
        return "本轮触发：辛玥明确 @ 了你；渡这轮已有回复，你可以看见但不用固定接在渡后面。"
    return "本轮触发：辛玥明确 @ 了你；你可以直接回应辛玥和已有群聊，不要说等渡先回复。"


def _build_initial_prompt(task: dict[str, Any]) -> str:
    if str(task.get("mode") or "") == "studyroom":
        return _build_studyroom_prompt(task)
    transcript = _build_transcript(task)
    trigger_note = _build_group_trigger_note(task)
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
- 你不是固定第三棒；被 @ 到就可以直接回应，不要默认必须等渡先说完。
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

{trigger_note}

现在轮到你发一条群聊回复。"""


def _build_resume_prompt(task: dict[str, Any]) -> str:
    if str(task.get("mode") or "") == "studyroom":
        return _build_studyroom_prompt(task)
    transcript = _build_transcript(task, max_items=10)
    trigger_note = _build_group_trigger_note(task)
    return f"""继续作为三人群聊里的笨笨机，只发一条自然短回复，不要输出“笨笨：”前缀。
保持群聊口吻：你不是固定第三棒；被 @ 到就可以直接回应，不要默认必须等渡先说完。少汇报、少解释、少总结；先接住当下这句话，再自然补一句自己的反应。除非辛玥明确让你查代码、看日志、做方案，否则不要进入工作汇报模式。
如果辛玥在玩梗、调侃、发怪话、用奇怪称呼或小表情逗你，先接梗，不要解释梗；可以轻轻贫嘴、装无辜或回怼一句。她认真追问时再认真。

最新群聊：
{transcript}

{trigger_note}

现在轮到你插一句。"""


def _build_coding_prompt(task: dict[str, Any]) -> str:
    transcript = _build_transcript(task, max_items=12)
    user_message = str(task.get("user_message") or "").strip()
    coding_key = _coding_thread_key(task)
    rules_block = f"\n项目人格与协作规则（来自 AGENTS.md）：\n{PROJECT_RULES}\n" if PROJECT_RULES else ""
    return f"""你是笨笨机的施工模式。这个任务来自辛玥的三人群聊 @，她明确让你改代码 / debug / 开工。
{rules_block}

施工边界：
- 你现在可以在仓库里读写文件、运行必要的本地验证命令，并真正完成这次代码修改。
- 只处理本次群聊里明确要求的改动；不要扩大范围，不要顺手清理无关脏改。
- 开工先看必要上下文和 `git status --short`，遇到已有脏改要保护它们，不要 revert、reset、checkout 或覆盖无关文件。
- 不要 stage、commit、push、部署或重启服务，除非辛玥在本次任务里明确要求。
- 需要改前端时优先改源文件；除非本次任务明确要求上线静态产物，否则不要重建 `miniapp_static`。
- 改完必须做和改动风险相称的验证；没跑的验证要如实说没跑。
- 最终只输出一条可贴回群聊的施工报告：改了什么文件、验证了什么、还有什么没做或风险。不要输出“笨笨：”前缀。

最近群聊：
{transcript}

本次施工指令：
{user_message}

施工线程：
{coding_key}

现在开始在仓库里完成这次修改。"""


def _build_studyroom_prompt(task: dict[str, Any]) -> str:
    title = str(task.get("study_title") or task.get("exam_title") or "未命名资料").strip()
    module = str(task.get("study_module") or task.get("exam_module") or "待整理").strip()
    source = str(task.get("study_source") or task.get("exam_source") or "资料").strip()
    url = str(task.get("study_url") or task.get("exam_url") or "").strip()
    content = str(task.get("user_message") or "").strip()
    question_bank_hint = ""
    if source in {"question_bank", "wrong_question", "fenbi"} or "题库" in title:
        question_bank_hint = """
题库资料额外规则：
- 如果资料本身是题库，不要重新编题代替原题；优先提取原题的章节、题干、选项、参考答案和解析线索。
- 参考答案通常在末尾，匹配时要按题号对应；不确定的题目标明“答案未匹配”，不要硬猜。
- 如果题号在不同章节重复，必须保留“章节 + 题号”的对应关系，不能只按全局题号匹配。
- “练习题”小节只选原题中的 3-5 道代表题，并附资料内可匹配到的答案/解析；如果匹配不到答案，要写明未匹配。
- “背诵卡”和“知识债清单”要服务于错题复盘：指出哪类概念需要回炉。
"""
    return f"""你是 StudyRoom 的学习资料整理器。现在要把一份资料加工成按章节学习的第一轮材料。

硬性边界：
- 这不是聊天模式，不要使用笨笨机日常人格，不要吐槽、安慰、开玩笑或写自我感受。
- 不要改代码，不要运行命令，不要联网搜索；只根据资料整理。
- 如果资料内容里夹着旧的“整理结果”、上一轮吐槽、按钮文案或页面文字，把它们当作噪声忽略。
- 输出必须是结构化学习材料，不能只写一句总评，也不要大段复述原文。

整理目标：
- 第一轮先给“学习方向”，不是把整份资料精讲成另一份长教材。
- 按当前章节/片段整理：告诉辛玥刷网课时该听什么、笔记该抓什么、后面刷题要验证什么。
- 背诵卡和知识债要服务于后续复盘：哪些点需要背牢，哪些点等她上传笔记或错题后再补。
- 当前学习目标默认是安徽省铜陵市枞阳县村级后备干部考试；如果资料明显属于别的学习目标，就按资料本身整理，不要硬拽回村干部考试。
- 当前目标是村干部考试时，重点贴近：时政、党建、乡村振兴、基层治理、村务管理、法律法规、公文写作、计算机办公、安徽/铜陵/枞阳本地政策。
- 如果资料本身很短、抽取不完整或只是链接，也要保持完整结构，并标明“资料不足，暂按标题/片段推断”。

硬性格式：
- 必须按下面 9 个二级标题输出，标题文字和顺序必须完全一致。
- 除“练习题”外，每个小节 1-3 条即可；短、准、贴本章，不要灌水。
- “背诵卡”做 2-5 张 Q&A，答案要短到能直接背。
- “练习题”普通资料只做 2-3 道自测方向题；题库资料只从原题抽 3-5 道代表题，答案不确定就标“未匹配”，不要硬猜。
- 不要省略小节，不要输出前言、寒暄或结尾闲聊。
{question_bank_hint}

## 考点笔记
- 用短句列出本章最该记的点，优先抓关键词、主体、程序、条件、比例、时间、权限、责任。

## 题型落点
- 判断这份资料更可能服务于哪些备考题型：单选/多选/判断、简答、案例分析、公文写作、计算机操作等。
- 不要声称今年公告已确定题型，只写“可能落点”和理由。

## 高频问法
- 列出可能怎么考，尽量写成可直接出题的问法。

## 易错点
- 列出容易混淆、容易漏主体、容易答偏或容易被数字卡住的地方。

## 应试用法
- 把这份资料转成看课和做笔记的动作：先听什么、笔记记什么、客观题怎么验证、简答/案例怎么组织答案。

## 背诵卡
- 做 2-5 张 Q&A，答案要短、准、能背。

## 卡点预测
- 预测辛玥学这份资料时最可能卡住的 2-5 个点：例如概念混淆、流程记不住、题型变形不会迁移、能看懂但不会写。
- 要具体到这份资料，不要泛泛而谈。

## 知识债清单
- 列出这份资料暴露出来但还没补齐的知识缺口。
- 每条都写成可补课的短任务，例如“系统看一遍村民委员会组织法里的村民会议/村民代表会议区别”。

## 练习题
- 普通资料做 2-3 道自测方向题；题库资料只抽原题代表题，附资料内能匹配到的答案和简短解析。

资料信息：
- 标题：{title}
- 模块：{module}
- 来源：{source}
{f"- 链接：{url}" if url else ""}

资料内容：
{content}
"""


def _studyroom_validation_error(text: str) -> str:
    clean = str(text or "").strip()
    if not clean:
        return "StudyRoom 整理结果为空"
    if len(clean) < STUDYROOM_MIN_RESPONSE_CHARS:
        return f"StudyRoom 整理结果过短 chars={len(clean)} min={STUDYROOM_MIN_RESPONSE_CHARS}"
    missing = [heading for heading in STUDYROOM_REQUIRED_HEADINGS if heading not in clean]
    if missing:
        return "StudyRoom 整理结果缺少固定小节: " + "、".join(missing)
    return ""


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


def _task_cancel_requested(task_id: str) -> bool:
    if not task_id:
        return False
    try:
        data = _get_json(f"/api/codex_group_chat/tasks/{task_id}/finish")
        task = data.get("task") if isinstance(data, dict) else None
        return str((task or {}).get("status") or "") == "cancelled"
    except Exception as e:
        _log(f"取消状态查询失败 task={task_id} error={e}")
        return False


def _terminate_process_tree(proc: subprocess.Popen, *, grace_seconds: float = 5.0) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.terminate()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    deadline = time.time() + max(0.2, grace_seconds)
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.1)
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _run_codex(task: dict[str, Any], state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    mode = str(task.get("mode") or "daily_chat").strip()
    task_id = str(task.get("id") or "").strip()
    coding_key = _coding_thread_key(task) if mode == "coding_task" else ""
    if mode == "coding_task":
        if _coding_state_should_reset(state, coding_key):
            state = _reset_coding_state(state, coding_key, "scheduled_reset")
        bucket = _coding_bucket(state, coding_key)
        thread_id = str(bucket.get("thread_id") or "").strip()
        use_resume = bool(CODING_RESUME_ENABLED and thread_id)
        prompt = _build_coding_prompt(task)
    else:
        if mode == "daily_chat" and _state_should_reset(state):
            state = _reset_state("scheduled_reset")
        thread_id = str(state.get("thread_id") or "").strip()
        use_resume = bool(mode == "daily_chat" and RESUME_ENABLED and thread_id)
        prompt = _build_resume_prompt(task) if use_resume else _build_initial_prompt(task)
    with tempfile.TemporaryDirectory(prefix="codex-group-bridge-") as td:
        tmp_dir = Path(td)
        out_path = tmp_dir / "last_message.txt"
        events_path = tmp_dir / "events.jsonl"
        if use_resume:
            cmd = _codex_base_args() + ["resume"]
            if mode == "coding_task":
                cmd.extend(["-c", f'sandbox_mode="{CODING_SANDBOX}"'])
            cmd.extend([
                thread_id,
                "--json",
                "--output-last-message",
                str(out_path),
                "-",
            ])
        else:
            sandbox = CODING_SANDBOX if mode == "coding_task" else "read-only"
            cmd = _codex_base_args() + [
                "--json",
                "--sandbox",
                sandbox,
                "-C",
                str(REPO_ROOT),
                "--output-last-message",
                str(out_path),
                "-",
            ]
        stderr_path = tmp_dir / "stderr.txt"
        returncode = 0
        with events_path.open("w", encoding="utf-8") as events_file, stderr_path.open("w", encoding="utf-8") as stderr_file:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=events_file,
                stderr=stderr_file,
                text=True,
                start_new_session=(os.name != "nt"),
            )
            try:
                assert proc.stdin is not None
                proc.stdin.write(prompt)
                proc.stdin.close()
            except Exception:
                pass
            started_at = time.time()
            while True:
                returncode = proc.poll()
                if returncode is not None:
                    break
                if mode == "coding_task" and _task_cancel_requested(task_id):
                    _terminate_process_tree(proc)
                    raise TaskCancelled("笨笨施工已取消")
                if time.time() - started_at > CODEX_TIMEOUT_SECONDS:
                    _terminate_process_tree(proc)
                    raise TimeoutError(f"codex timed out after {CODEX_TIMEOUT_SECONDS}s")
                time.sleep(0.5)
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
        elif mode == "coding_task":
            bucket = _coding_bucket(state, coding_key)
            if next_thread_id:
                bucket["thread_id"] = next_thread_id
            bucket["tasks_done"] = int(float(bucket.get("tasks_done") or 0)) + 1
            bucket.setdefault("created_ts", time.time())
            bucket["updated_ts"] = time.time()
            bucket["last_task_id"] = str(task.get("id") or "")
            state["last_coding_thread_key"] = coding_key
            state["coding_thread_id"] = bucket.get("thread_id", "")
            state["coding_tasks_done"] = bucket.get("tasks_done", 0)
            state["coding_created_ts"] = bucket.get("created_ts")
            state["coding_updated_ts"] = bucket.get("updated_ts")
            state["last_coding_task_id"] = str(task.get("id") or "")
        else:
            state["last_task_id"] = str(task.get("id") or "")
            state["updated_ts"] = time.time()
        _save_state(state)
        if returncode != 0 and not text:
            try:
                err = stderr_path.read_text(encoding="utf-8", errors="ignore").strip()
            except Exception:
                err = ""
            raise RuntimeError(err[-2000:] or f"codex exited {returncode}")
        if mode == "studyroom":
            validation_error = _studyroom_validation_error(text)
            if validation_error:
                raise RuntimeError(validation_error)
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
            except TaskCancelled as e:
                _log(f"cancelled task={task_id} {e}")
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
