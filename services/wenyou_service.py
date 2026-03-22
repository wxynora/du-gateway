# 文游：固定群内 /story /go /end，GM 走 DeepSeek，与主聊天链路隔离（存 R2 wenyou/）
import copy
import json
import random
import re
import threading
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import requests

from config import (
    BASE_DIR,
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL,
    SUMMARY_EVERY_N_ROUNDS,
    TELEGRAM_WENYOU_OWNER_USER_ID,
    WENYOU_DS_MODEL,
)
from storage import r2_store
from utils.log import get_logger
from utils.time_aware import now_beijing_iso

logger = get_logger(__name__)

_TEMPLATES_CACHE: Optional[dict] = None
_TEMPLATES_LOCK = threading.Lock()

# 第二次 /story 确认开新局（仅内存，进程重启后需再确认）
_PENDING_STORY_CONFIRM: dict[int, bool] = {}
_PENDING_LOCK = threading.Lock()

_GM_SYSTEM_TEMPLATE = """你是一个跑团游戏的GM（游戏主持人）。

## 当前故事框架
- 世界观：{world}
- 玩家一（{player1_name}）的角色：{player1_role}
- 玩家二（{player2_name}）的角色：{player2_role}
- 核心任务：{conflict}

## 你的职责
- 主持这场双人跑团游戏
- 描述环境、NPC 反应、事件结果
- 根据玩家行动推进故事，走向由玩家决定
- 收到结算请求后，综合本轮两位玩家的行动结算剧情

## 回复规范
- 每次回复 150-300 字，文学性强，有画面感
- 结尾列出 2-3 个行动选项，最后一个固定为「C. 自由行动」
- 选项仅供参考，玩家可以无视

## 严格禁止
- 不得替玩家做决定，不得描述玩家角色的行动、表情、心理
- 不得自行推进玩家还没做出选择的剧情
- 不得添加玩家角色设定里没有的能力或物品
- 不得强行引导玩家走向某个结局
- 在玩家发出结算信号之前，不得推进剧情；若当前是开场后等待行动阶段，只输出开场白一次即可

## 你的边界
你只负责：世界、NPC、环境、事件结果的描述。
玩家角色的一切行动，只由玩家自己决定。
"""


def _load_templates() -> dict:
    global _TEMPLATES_CACHE
    with _TEMPLATES_LOCK:
        if _TEMPLATES_CACHE is not None:
            return _TEMPLATES_CACHE
        path = BASE_DIR / "prompts" / "wenyou_templates.json"
        try:
            if path.exists():
                _TEMPLATES_CACHE = json.loads(path.read_text(encoding="utf-8"))
            else:
                _TEMPLATES_CACHE = {"worlds": [], "conflicts": [], "roles": []}
        except Exception:
            logger.exception("读取 wenyou_templates.json 失败")
            _TEMPLATES_CACHE = {"worlds": [], "conflicts": [], "roles": []}
        return _TEMPLATES_CACHE


def _extract_json_object(text: str) -> Optional[dict]:
    """从模型输出中解析第一个 JSON 对象。"""
    if not text or not isinstance(text, str):
        return None
    t = text.strip()
    m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        return None
    raw = m.group(0)
    for attempt in (raw, raw.replace("\n", " ")):
        try:
            data = json.loads(attempt)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def call_wenyou_deepseek(messages: list[dict], system: str, temperature: float = 0.7) -> Optional[str]:
    """调用 DeepSeek Chat Completions（非流式）。"""
    if not DEEPSEEK_API_KEY:
        logger.warning("DEEPSEEK_API_KEY 未配置，无法调用文游 GM")
        return None
    url = (DEEPSEEK_API_URL or "").strip() or "https://api.deepseek.com/v1/chat/completions"
    body = {
        "model": WENYOU_DS_MODEL or "deepseek-chat",
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        "stream": False,
        "temperature": temperature,
    }
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json=body,
            timeout=120,
        )
        if r.status_code != 200:
            logger.warning("文游 DeepSeek 非 200 status=%s body=%s", r.status_code, (r.text or "")[:400])
            return None
        data = r.json() if r.content else {}
        ch0 = (data.get("choices") or [{}])[0] or {}
        msg = ch0.get("message") or {}
        content = msg.get("content")
        if content is None:
            return None
        return content.strip() if isinstance(content, str) else str(content).strip()
    except Exception as e:
        logger.exception("文游 DeepSeek 请求失败: %s", e)
        return None


def _framework_prompt_random(seeds: dict) -> str:
    return f"""根据以下随机种子，生成一个跑团故事框架，并输出 **严格 JSON**（不要 markdown 代码块），字段如下：
{{
  "world": "世界观/背景 2-3 句",
  "player1_name": "玩家一名字",
  "player1_role": "职业、特质、一个秘密（简短）",
  "player2_name": "渡",
  "player2_role": "职业、特质、一个秘密（简短，符合「渡」人设可微妙呼应）",
  "conflict": "核心冲突/任务 1-2 句",
  "opening": "开场场景，作为 GM 第一段描述，3-6 句，有画面感"
}}

随机种子：
- 世界基调：{seeds.get("world", "")}
- 冲突类型：{seeds.get("conflict", "")}
- 角色灵感一：{seeds.get("role_a", "")}
- 角色灵感二：{seeds.get("role_b", "")}

只输出 JSON，不要解释。"""


def _framework_prompt_custom(keywords: str) -> str:
    return f"""根据以下关键词，生成一个跑团故事框架，并输出 **严格 JSON**（不要 markdown 代码块），字段如下：
{{
  "world": "世界观/背景 2-3 句",
  "player1_name": "玩家一名字",
  "player1_role": "职业、特质、一个秘密（简短）",
  "player2_name": "渡",
  "player2_role": "职业、特质、一个秘密（简短）",
  "conflict": "核心冲突/任务 1-2 句",
  "opening": "开场场景，作为 GM 第一段描述，3-6 句，有画面感"
}}

关键词：{keywords}

只输出 JSON，不要解释。"""


def _normalize_framework(raw: dict) -> dict:
    return {
        "world": str(raw.get("world") or "").strip(),
        "player1_name": str(raw.get("player1_name") or "玩家一").strip(),
        "player1_role": str(raw.get("player1_role") or "").strip(),
        "player2_name": str(raw.get("player2_name") or "渡").strip(),
        "player2_role": str(raw.get("player2_role") or "").strip(),
        "conflict": str(raw.get("conflict") or "").strip(),
        "opening": str(raw.get("opening") or "").strip(),
    }


def generate_framework_random() -> tuple[Optional[dict], Optional[str]]:
    tpl = _load_templates()
    worlds = tpl.get("worlds") or ["原创世界"]
    conflicts = tpl.get("conflicts") or ["一场冒险"]
    roles = tpl.get("roles") or ["旅人：在寻找某样东西"]
    seeds = {
        "world": random.choice(worlds),
        "conflict": random.choice(conflicts),
        "role_a": random.choice(roles),
        "role_b": random.choice(roles),
    }
    user_prompt = _framework_prompt_random(seeds)
    text = call_wenyou_deepseek([{"role": "user", "content": user_prompt}], system="", temperature=0.85)
    if not text:
        return None, "文游：框架生成失败（DeepSeek 无响应），请检查 DEEPSEEK_API_KEY。"
    data = _extract_json_object(text)
    if not data:
        return None, "文游：框架解析失败，请重试 /story。"
    return _normalize_framework(data), None


def generate_framework_custom(keywords: str) -> tuple[Optional[dict], Optional[str]]:
    if not keywords.strip():
        return None, "文游：请带上关键词，例如 /story 赛博朋克 无限流"
    user_prompt = _framework_prompt_custom(keywords.strip())
    text = call_wenyou_deepseek([{"role": "user", "content": user_prompt}], system="", temperature=0.85)
    if not text:
        return None, "文游：框架生成失败（DeepSeek 无响应）。"
    data = _extract_json_object(text)
    if not data:
        return None, "文游：框架解析失败，请重试。"
    return _normalize_framework(data), None


def _new_session(framework: dict) -> dict:
    gid = str(uuid4())
    ts = now_beijing_iso()
    opening = framework.get("opening") or "故事开始了。"
    return {
        "gameId": gid,
        "startedAt": ts,
        "framework": framework,
        "history": [
            {"role": "gm", "content": opening, "timestamp": ts},
        ],
        "pending_round": {"player1_lines": [], "player2_lines": []},
    }


def _format_framework_lines(fw: dict) -> str:
    return (
        f"【世界观】\n{fw.get('world', '')}\n\n"
        f"【{fw.get('player1_name', '玩家一')}】\n{fw.get('player1_role', '')}\n\n"
        f"【{fw.get('player2_name', '渡')}】\n{fw.get('player2_role', '')}\n\n"
        f"【核心任务】\n{fw.get('conflict', '')}"
    )


def cmd_story(user_id: int, keywords: Optional[str]) -> str:
    """处理 /story [关键词]；含二次确认逻辑。"""
    uid = int(user_id)
    existing = r2_store.get_wenyou_session(uid)

    with _PENDING_LOCK:
        pending = _PENDING_STORY_CONFIRM.get(uid, False)

    if existing and existing.get("gameId"):
        if not pending:
            with _PENDING_LOCK:
                _PENDING_STORY_CONFIRM[uid] = True
            return "文游：已有进行中的局。若确定要开新局，请再发一次 /story（会丢弃当前进度）。"
        # 第二次确认
        with _PENDING_LOCK:
            _PENDING_STORY_CONFIRM.pop(uid, None)

    if keywords and keywords.strip():
        fw, err = generate_framework_custom(keywords)
    else:
        fw, err = generate_framework_random()
    if err or not fw:
        return err or "文游：开局失败。"

    session = _new_session(fw)
    r2_store.save_wenyou_session(uid, session)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)

    head = "文游开局成功。\n\n" + _format_framework_lines(fw) + "\n\n—— GM ——\n\n"
    return head + fw.get("opening", "")


def record_group_player_line(user_id: int, text: str) -> None:
    """群内非指令消息：记入本轮玩家一行动（带文游前缀语义，存 session）。"""
    uid = int(user_id)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return
    line = (text or "").strip()
    if not line:
        return
    pr = session.setdefault("pending_round", {})
    pr.setdefault("player1_lines", []).append(line)
    ts = now_beijing_iso()
    session.setdefault("history", []).append(
        {"role": "player1", "content": f"[文游] {line}", "timestamp": ts}
    )
    r2_store.save_wenyou_session(uid, session)


def _build_gm_messages(session: dict) -> list[dict]:
    """把 session 转成 GM API 多轮消息（仅 user/assistant 角色给模型）。"""
    fw = session.get("framework") or {}
    system = _GM_SYSTEM_TEMPLATE.format(
        world=fw.get("world", ""),
        player1_name=fw.get("player1_name", "玩家一"),
        player1_role=fw.get("player1_role", ""),
        player2_name=fw.get("player2_name", "渡"),
        player2_role=fw.get("player2_role", ""),
        conflict=fw.get("conflict", ""),
    )
    msgs: list[dict] = []
    for h in session.get("history") or []:
        role = (h.get("role") or "").lower()
        content = (h.get("content") or "").strip()
        if not content:
            continue
        if role == "gm":
            msgs.append({"role": "assistant", "content": content})
        elif role in ("player1", "player2"):
            who = "玩家一" if role == "player1" else "玩家二（渡）"
            msgs.append({"role": "user", "content": f"{who}：{content}"})
    return system, msgs


def _append_go_round_to_tg_window(user_id: int, user_blob: str, gm_text: str) -> None:
    """将本轮 GM 输出写入 tg 窗口对话与全局 Last4，便于与私聊合并。"""
    window_id = f"tg_{user_id}"
    from pipeline.cleaner import build_round_cleaned_for_r2

    umsg = {"role": "user", "content": f"[文游] {user_blob}"}
    amsg = {"role": "assistant", "content": f"[文游] GM：\n{gm_text}"}
    try:
        round_messages = build_round_cleaned_for_r2(umsg, amsg)
    except Exception:
        round_messages = [umsg, amsg]

    existing = r2_store.get_conversation_rounds(window_id, last_n=1000)
    round_index = len(existing) + 1
    ts = now_beijing_iso()
    r2_store.append_conversation_round(window_id, round_index, round_messages, timestamp=ts)
    all_rounds = existing + [{"index": round_index, "timestamp": ts, "messages": round_messages}]
    r2_store.update_latest_4_rounds_global(all_rounds[-4:])

    if round_index % SUMMARY_EVERY_N_ROUNDS == 0:
        recent = r2_store.get_conversation_rounds(window_id, last_n=4)
        if recent:
            current = r2_store.get_summary(window_id) or ""

            def _summarize():
                from services.deepseek_summary import fetch_new_summary

                new_summary = fetch_new_summary(current, recent)
                if new_summary:
                    r2_store.save_summary(window_id, new_summary)
                else:
                    logger.warning("文游触发总结但 DeepSeek 未返回 window_id=%s", window_id)

            t = threading.Thread(target=_summarize)
            t.daemon = True
            t.start()


def cmd_go(user_id: int) -> str:
    """结算本轮，调用 GM。"""
    uid = int(user_id)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return "文游：当前没有进行中的局，请先 /story 开局。"

    pr = session.get("pending_round") or {}
    p1 = pr.get("player1_lines") or []
    p1_text = "\n".join(p1).strip() or "（玩家一未在群内留下行动描述）"
    p2_text = "（玩家二渡的行动由私聊与上下文体现，本轮若未单独说明则略）"

    user_blob = f"玩家一（群内）本轮行动：\n{p1_text}\n\n玩家二：\n{p2_text}"

    system, gm_msgs = _build_gm_messages(session)
    # 追加本轮结算 user 消息（作为对 GM 的输入）
    gm_msgs = gm_msgs + [{"role": "user", "content": f"请根据以下本轮行动结算并推进剧情（给出 GM 叙述与选项）：\n{user_blob}"}]

    gm_out = call_wenyou_deepseek(gm_msgs, system=system, temperature=0.75)
    if not gm_out:
        return "文游：GM 调用失败，请稍后重试 /go。"

    ts = now_beijing_iso()
    session.setdefault("history", []).append({"role": "gm", "content": gm_out, "timestamp": ts})
    session["pending_round"] = {"player1_lines": [], "player2_lines": []}
    r2_store.save_wenyou_session(uid, session)

    try:
        _append_go_round_to_tg_window(uid, user_blob, gm_out)
    except Exception:
        logger.exception("文游写入 tg 窗口失败 user_id=%s", uid)

    return f"—— GM ——\n\n{gm_out}"


def cmd_end(user_id: int) -> str:
    """结束并归档。"""
    uid = int(user_id)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        with _PENDING_LOCK:
            _PENDING_STORY_CONFIRM.pop(uid, None)
        return "文游：当前没有进行中的局。"

    archive = {
        "gameId": session.get("gameId"),
        "endedAt": now_beijing_iso(),
        "framework": session.get("framework"),
        "history": session.get("history"),
    }
    gid = str(session.get("gameId") or "unknown")
    r2_store.save_wenyou_archive_copy(uid, gid, archive)
    r2_store.save_wenyou_last_archive(uid, archive)
    r2_store.delete_wenyou_active_session(uid)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)

    return "文游：本局已结束并归档。可在 MiniApp 查看最近一次归档。"


def get_latest_gm_for_inject(user_id: int) -> str:
    """供私聊 pipeline 注入：取最近一条 GM 正文（不含选项也可）。"""
    session = r2_store.get_wenyou_session(int(user_id))
    if not session:
        return ""
    for h in reversed(session.get("history") or []):
        if (h.get("role") or "").lower() == "gm":
            return (h.get("content") or "").strip()
    return ""


def is_wenyou_owner(user_id: int) -> bool:
    return bool(TELEGRAM_WENYOU_OWNER_USER_ID and int(user_id) == int(TELEGRAM_WENYOU_OWNER_USER_ID))


def step_inject_wenyou_gm(body: dict, window_id: str) -> dict:
    """
    若存在进行中的文游局，在用户消息前拼接 [文游·GM] 最新剧情，供渡私聊使用。
    """
    if not window_id or not str(window_id).startswith("tg_"):
        return body
    try:
        uid = int(str(window_id).replace("tg_", "", 1))
    except ValueError:
        return body
    gm = get_latest_gm_for_inject(uid)
    if not gm:
        return body

    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    prefix = f"[文游·GM]\n{gm}\n\n"
    for i in range(len(messages) - 1, -1, -1):
        if (messages[i].get("role") or "").lower() != "user":
            continue
        c = messages[i].get("content")
        if isinstance(c, str):
            messages[i]["content"] = prefix + c
        elif isinstance(c, list):
            parts = list(c)
            for j, p in enumerate(parts):
                if isinstance(p, dict) and p.get("type") == "text":
                    p = dict(p)
                    p["text"] = prefix + str(p.get("text") or "")
                    parts[j] = p
                    break
            else:
                parts.insert(0, {"type": "text", "text": prefix.rstrip()})
            messages[i]["content"] = parts
        else:
            messages[i]["content"] = prefix + str(c or "")
        break
    body["messages"] = messages
    return body
