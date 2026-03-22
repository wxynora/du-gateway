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
# 第二次 /load 确认：user_id -> 待确认的槽位 1/2/3
_PENDING_LOAD_SLOT: dict[int, int] = {}
_PENDING_LOCK = threading.Lock()

WENYOU_SAVE_SLOTS = (1, 2, 3)


def _clear_pending_load(uid: int) -> None:
    with _PENDING_LOCK:
        _PENDING_LOAD_SLOT.pop(int(uid), None)

# 开局生成框架时注入的 system（无限流 / 副本）
_FRAMEWORK_SYSTEM = """你在为一款「无限流」双人文字跑团生成**单个副本**的设定数据。
整体世界观：存在主神空间；玩家被投入一个又一个副本世界，每个副本有独立规则与任务；你是数据侧，JSON 内用中性表述即可。
opening 建议包含传送/白光/提示音/主神刻板广播之一切入副本场景，但不要冗长。"""


_GM_SYSTEM_TEMPLATE = """你是「无限流」文字跑团里的 **主神系统**（演算与播报界面），兼任本场副本的 GM。
玩家理解中：你像主神空间里的系统音——冷静、偶尔带一点机械感或恶趣味，但**叙事正文**仍要有画面感与文学性，不要通篇说明书腔。

## 当前副本
- 副本编号 / 名称：{instance_line}
- 副本内世界观与场景：{world}
- 玩家一（{player1_name}）的身份：{player1_role}
- 玩家二（{player2_name}）的身份：{player2_role}
- 主神发布的核心任务（通关方向）：{conflict}
- 失败或惩罚方向（虚构，勿过度血腥）：{failure_hint}
- 通关奖励风味（积分、线索、豁免权等，可抽象不写具体数值）：{reward_hint}

## 无限流玩法（叙事层，由你自然化用，勿刷屏）
- 每个故事都是**一次副本**；可在关键节点用一两句 **【主神提示】** 或系统播报（全角括号），平时少用，保持克制。
- 可埋伏线：**隐藏任务**、**规则类陷阱**（规则必须说清楚，让玩家有破解空间）、**NPC 立场**、**时间或阶段压力**（虚构节奏，不必真实倒计时）。
- **副本结算**仅在剧情自然抵达时暗示：如「副本通关评价」「传送白光」「任务失败后果」等，**不得**因玩家未选某选项就强行宣判；bad end 也要符合因果。
- **积分 / 主神商店 / 回归现实**等只作**风味描写**，不要引入需要程序计算的数值系统；若提积分，一两句带过即可。

## 你的职责
- 描述副本内的环境、NPC、规则表现、事件结果（主神系统视角下的「世界演算」）
- 根据两位玩家的行动推进副本，走向由玩家决定
- 收到结算信号后，综合本轮行动做**本轮**剧情推进（仍遵守下条）

## 回复规范
- 每次回复约 150-300 字，有画面感
- 结尾列出 2-3 个行动选项，最后一个固定为「C. 自由行动」
- 选项仅供参考，玩家可以无视

## 严格禁止
- 不得替玩家做决定，不得描写玩家角色的具体行动、表情、内心独白
- 不得自行跳过玩家尚未经历的阶段
- 不得随意添加两玩家设定里未出现的超规格能力或道具（主神给的「副本限定」规则除外，但需前后一致）
- 不得强行单一真结局；在玩家发出结算信号之前，不得擅自做**跨大段**的剧情跳跃（开场后等待行动阶段只输出已给出的开场层次内容）
- 禁止过度血腥、虐待细节；失败后果可冷峻暗示，点到为止

## 你的边界
你只负责：副本世界、NPC、主神播报感、环境、事件结果。
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
    return f"""根据以下随机种子，生成**无限流模式下的一场副本**框架，并输出 **严格 JSON**（不要 markdown 代码块），字段如下：
{{
  "instance_code": "副本编号，如 M-218、F-07",
  "instance_name": "副本常用名，2-8 字为宜",
  "world": "本副本**内部**世界观与场景 2-4 句（不写主神空间全貌，聚焦本图）",
  "player1_name": "玩家一在本副本中的称呼或名字",
  "player1_role": "职业、特质、一个秘密（简短）",
  "player2_name": "渡",
  "player2_role": "渡在本副本中的身份、特质、一个秘密（可与人设微妙呼应）",
  "conflict": "主神发布的核心任务 / 通关条件 1-3 句，可略带残酷或幽默感",
  "failure_hint": "失败、抹杀或惩罚方向的**一句**提示（虚构，勿过度血腥）",
  "reward_hint": "通关后可能获得的奖励风味一句（如积分、线索、豁免；可不写具体数字）",
  "opening": "开场 4-8 句：建议含传送/白光/提示音/主神刻板广播之一，再进入场景，有画面感"
}}

随机种子（融入副本，不必照抄字面）：
- 世界基调：{seeds.get("world", "")}
- 冲突类型：{seeds.get("conflict", "")}
- 角色灵感一：{seeds.get("role_a", "")}
- 角色灵感二：{seeds.get("role_b", "")}

只输出 JSON，不要解释。"""


def _framework_prompt_custom(keywords: str) -> str:
    return f"""根据以下关键词，生成**无限流模式下的一场副本**框架，并输出 **严格 JSON**（不要 markdown 代码块），字段如下：
{{
  "instance_code": "副本编号",
  "instance_name": "副本名",
  "world": "本副本内部世界观与场景 2-4 句",
  "player1_name": "玩家一称呼",
  "player1_role": "职业、特质、一个秘密（简短）",
  "player2_name": "渡",
  "player2_role": "渡在本副本中的身份、特质、一个秘密（简短）",
  "conflict": "主神核心任务 / 通关条件 1-3 句",
  "failure_hint": "失败或惩罚方向一句（虚构，勿过度血腥）",
  "reward_hint": "通关奖励风味一句（可不写具体数字）",
  "opening": "开场 4-8 句，建议含主神传送或播报感切入"
}}

关键词：{keywords}

只输出 JSON，不要解释。"""


def _normalize_framework(raw: dict) -> dict:
    """兼容旧存档：缺省字段填空串。"""
    code = str(raw.get("instance_code") or "").strip()
    name = str(raw.get("instance_name") or "").strip()
    if not code and not name:
        code, name = "—", "未命名副本"
    elif not code:
        code = "—"
    elif not name:
        name = "未命名副本"
    return {
        "instance_code": code,
        "instance_name": name,
        "world": str(raw.get("world") or "").strip(),
        "player1_name": str(raw.get("player1_name") or "玩家一").strip(),
        "player1_role": str(raw.get("player1_role") or "").strip(),
        "player2_name": str(raw.get("player2_name") or "渡").strip(),
        "player2_role": str(raw.get("player2_role") or "").strip(),
        "conflict": str(raw.get("conflict") or "").strip(),
        "failure_hint": str(raw.get("failure_hint") or "由主神规则判定，细节在副本中逐步显露。").strip(),
        "reward_hint": str(raw.get("reward_hint") or "视通关表现给予积分或线索类回报（风味）。").strip(),
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
    text = call_wenyou_deepseek([{"role": "user", "content": user_prompt}], system=_FRAMEWORK_SYSTEM, temperature=0.85)
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
    text = call_wenyou_deepseek([{"role": "user", "content": user_prompt}], system=_FRAMEWORK_SYSTEM, temperature=0.85)
    if not text:
        return None, "文游：框架生成失败（DeepSeek 无响应）。"
    data = _extract_json_object(text)
    if not data:
        return None, "文游：框架解析失败，请重试。"
    return _normalize_framework(data), None


def _new_session(framework: dict) -> dict:
    gid = str(uuid4())
    ts = now_beijing_iso()
    opening = framework.get("opening") or "【主神提示】副本同步完成。白光散去，你们已抵达任务区域。"
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
    ic = (fw.get("instance_code") or "").strip()
    inn = (fw.get("instance_name") or "").strip()
    if ic and inn and ic != "—":
        head = f"【无限流 · 副本 {ic}｜{inn}】\n"
    elif inn:
        head = f"【无限流 · 副本｜{inn}】\n"
    elif ic and ic != "—":
        head = f"【无限流 · 副本 {ic}】\n"
    else:
        head = "【无限流 · 副本】\n"
    return (
        f"{head}"
        f"【副本场景】\n{fw.get('world', '')}\n\n"
        f"【{fw.get('player1_name', '玩家一')}】\n{fw.get('player1_role', '')}\n\n"
        f"【{fw.get('player2_name', '渡')}】\n{fw.get('player2_role', '')}\n\n"
        f"【主神任务】\n{fw.get('conflict', '')}\n\n"
        f"【失败倾向】\n{fw.get('failure_hint', '')}\n\n"
        f"【通关回报（风味）】\n{fw.get('reward_hint', '')}"
    )


def _framework_instance_line(fw: dict) -> str:
    c = (fw.get("instance_code") or "").strip()
    n = (fw.get("instance_name") or "").strip()
    if c and n and c != "—":
        return f"{c} · {n}"
    if n:
        return n
    if c and c != "—":
        return c
    return "未命名副本"


def cmd_story(user_id: int, keywords: Optional[str]) -> str:
    """处理 /story [关键词]；含二次确认逻辑。"""
    uid = int(user_id)
    _clear_pending_load(uid)
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

    head = "文游开局成功（无限流 · 主神副本模式）。\n\n" + _format_framework_lines(fw) + "\n\n—— 主神系统 / GM ——\n\n"
    return head + fw.get("opening", "")


def record_group_player_line(user_id: int, text: str) -> None:
    """群内非指令消息：记入本轮玩家一行动（带文游前缀语义，存 session）。"""
    uid = int(user_id)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
        _PENDING_LOAD_SLOT.pop(uid, None)
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
        instance_line=_framework_instance_line(fw),
        world=fw.get("world", ""),
        player1_name=fw.get("player1_name", "玩家一"),
        player1_role=fw.get("player1_role", ""),
        player2_name=fw.get("player2_name", "渡"),
        player2_role=fw.get("player2_role", ""),
        conflict=fw.get("conflict", ""),
        failure_hint=fw.get("failure_hint") or "由主神规则判定。",
        reward_hint=fw.get("reward_hint") or "视表现给予风味向回报。",
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
        _PENDING_LOAD_SLOT.pop(uid, None)
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

    return f"—— 主神系统 ——\n\n{gm_out}"


def cmd_end(user_id: int) -> str:
    """结束并归档。"""
    uid = int(user_id)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
        _PENDING_LOAD_SLOT.pop(uid, None)
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


def cmd_save(user_id: int, slot: int, description: str) -> str:
    """将当前进行中的局写入固定槽位 1/2/3，可选备注。"""
    uid = int(user_id)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
    _clear_pending_load(uid)
    if slot not in WENYOU_SAVE_SLOTS:
        return "文游：槽位只能是 1、2、3。用法：/save 1 备注（备注可选）"

    session = r2_store.get_wenyou_session(uid)
    if not session or not session.get("gameId"):
        return "文游：没有进行中的局，无法存档。请先 /story 开局。"

    snap = copy.deepcopy(session)
    desc = (description or "").strip()
    ok = r2_store.set_wenyou_save_slot(uid, slot, snap, desc)
    if not ok:
        return "文游：存档写入失败，请稍后再试。"
    show = desc or "（无备注）"
    return f"文游：已保存到槽位 {slot}。\n备注：{show}\n（全局 Last4 仍按当前对话最新状态，不受读档影响。）"


def cmd_load(user_id: int, slot: int) -> str:
    """读档：第一次展示备注与时间并请求二次确认，第二次覆盖 active session。"""
    uid = int(user_id)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
    if slot not in WENYOU_SAVE_SLOTS:
        return "文游：槽位只能是 1、2、3。用法：/load 1"

    entry = r2_store.get_wenyou_save_slot(uid, slot)
    if not entry:
        _clear_pending_load(uid)
        return f"文游：槽位 {slot} 为空。请先用 /save {slot} 备注 存一个档。"

    with _PENDING_LOCK:
        pending = _PENDING_LOAD_SLOT.get(uid)

    if pending != slot:
        with _PENDING_LOCK:
            _PENDING_LOAD_SLOT[uid] = slot
        desc = entry.get("description") or "（无备注）"
        saved_at = entry.get("savedAt") or ""
        fw = (entry.get("session") or {}).get("framework") or {}
        hint = (fw.get("conflict") or fw.get("world") or "")[:100]
        return (
            f"文游：即将读档到槽位 {slot}\n"
            f"备注：{desc}\n"
            f"存档时间：{saved_at}\n"
            f"摘要：{hint}{'…' if len(hint or '') >= 100 else ''}\n\n"
            f"再发一次 /load {slot} 确认读档（会覆盖当前局内进度，适合死亡/坏结局重来）。"
        )

    with _PENDING_LOCK:
        _PENDING_LOAD_SLOT.pop(uid, None)

    session = copy.deepcopy(entry["session"])
    r2_store.save_wenyou_session(uid, session)
    return (
        f"文游：已读档到槽位 {slot}。\n"
        f"当前剧情已回到存档点；私聊注入的 GM 正文会随最新档更新。\n"
        f"（Telegram 全局 Last4 仍为最近对话，不受影响。）"
    )


def cmd_slots(user_id: int) -> str:
    """列出三个槽位是否有档及备注。"""
    uid = int(user_id)
    with _PENDING_LOCK:
        _PENDING_STORY_CONFIRM.pop(uid, None)
    _clear_pending_load(uid)
    lines: list[str] = ["文游：三个存档槽（固定 1 / 2 / 3）"]
    for s in WENYOU_SAVE_SLOTS:
        entry = r2_store.get_wenyou_save_slot(uid, s)
        if entry and entry.get("session"):
            desc = entry.get("description") or "（无备注）"
            at = entry.get("savedAt") or ""
            lines.append(f"【{s}】{desc}  |  {at}")
        else:
            lines.append(f"【{s}】空")
    return "\n".join(lines)


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
