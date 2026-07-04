from __future__ import annotations

import json
import os
import random
import re
import shlex
import secrets
import threading
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except Exception:  # pragma: no cover - fcntl is available on the target Linux/macOS hosts.
    fcntl = None

from config import DATA_DIR
from services.pixel_home import (
    PRIVATE_DRAW_DU_LEADS_THEMES,
    PRIVATE_DRAW_KEEP_LIMIT_PATTERNS,
    PRIVATE_DRAW_SLOTS,
    PRIVATE_DRAW_XINYUE_CONTROL_LIMIT_PATTERNS,
    PRIVATE_DRAW_XINYUE_CONTROL_TASK_PATTERNS,
)
from utils.time_aware import now_beijing_iso


GAME_ID = "private_board"
DEFAULT_SAVE_PATH = DATA_DIR / GAME_ID / "default.json"
DEFAULT_BOARD_SIZE = 36
ACTORS = ("xinyue", "du")
SCHEMA_VERSION = 1

DU_VIEW_NAMES = {"xinyue": "小玥", "du": "我"}
PLAYER_VIEW_NAMES = {"xinyue": "我", "du": "渡"}

COMMAND_HINT = "可用命令：打开 / status / roll / roll 3 / new_game / end_game"
_PROCESS_LOCKS: dict[str, threading.Lock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()
THEME_DIRECTION_DU_LEADS = set(PRIVATE_DRAW_DU_LEADS_THEMES) - {"吸血鬼人类play"}
THEME_DIRECTION_XINYUE_LEADS = {"大小姐管家play", "吸血鬼人类play"}
DU_CONTROL_TASK_PATTERNS = (
    "给小玥舔",
    "用手把小玥",
    "用玩具让小玥",
    "只准用嘴取悦小玥",
    "先让小玥高潮",
    "把小玥亲到",
    "让小玥半穿衣",
    "给蒙眼的小玥",
    "把小玥伺候",
    "让小玥高潮后",
    "哄到小玥自己说",
    "收尾必须先把小玥",
    "结束前必须把小玥",
    "用夸奖把小玥",
    "用冰块和吻把小玥",
    "隔着衣服磨到小玥",
    "让小玥坐在你脸上",
    "把小玥抱到腿上",
    "用三种速度把小玥",
    "用电话指令让小玥",
    "让小玥在半公开",
    "只用手指和舌头把小玥",
    "把小玥全身反应",
    "给小玥戴上蒙眼",
    "让小玥在易感期",
    "在小玥后颈",
    "用强占有欲把小玥",
    "和小玥交配",
)
DU_CONTROL_LIMIT_PATTERNS = (
    "小玥第一次高潮前",
    "小玥没高潮前",
    "不准让小玥自己动手",
    "不准在小玥脸红前停手",
    "不准在小玥说可以前收尾",
    "不准在小玥害羞躲开时立刻放过她",
    "小玥每次发抖都要被你说出来",
    "不准在小玥声音软下来前结束",
    "不准只顾动作不哄她",
    "不准在她主动靠近前假装正经",
    "临时标记前必须先把小玥哄软",
)
DEFAULT_CELL_LABELS = {
    "theme": "本局玩法",
    "lock": "道具停步",
    "place": "地点追加",
    "limit": "限制追加",
    "task": "任务追加",
    "pose": "姿势锁定",
    "clear": "解除状态",
    "extend": "状态延长",
    "swap": "位置交换",
    "back": "限制拖回",
    "forward": "奖励前进",
    "replace": "替换状态",
}
DIRECTION_CELL_STYLES = {
    "du_leads": {
        "cell_names": {
            "lock": "主导停步",
            "limit": "规矩追加",
            "task": "命令任务",
            "pose": "姿势指定",
            "clear": "短暂放行",
            "extend": "加码延长",
            "swap": "主动权调换",
            "back": "规矩压回",
            "forward": "奖励前进",
            "replace": "改换条件",
        }
    },
    "xinyue_leads": {
        "cell_names": {
            "lock": "小玥扣留",
            "limit": "小玥规矩",
            "task": "小玥发令",
            "pose": "小玥验收",
            "clear": "小玥放行",
            "extend": "小玥加时",
            "swap": "主动权反转",
            "back": "重新听令",
            "forward": "准许前进",
            "replace": "小玥改令",
        }
    },
}
THEME_CELL_STYLES = {
    "成人师生play": {
        "cell_names": {
            "lock": "课堂罚停",
            "place": "留堂地点",
            "limit": "课堂规矩",
            "task": "课后任务",
            "pose": "检查姿势",
            "clear": "下课整理",
            "extend": "加罚延长",
            "back": "留堂退回",
            "forward": "表现奖励",
            "replace": "换个教室",
        },
        "preferred": {
            "place": ("教室", "图书馆", "讲台"),
            "prop": ("戒尺", "领带", "眼罩", "白衬衫", "制服"),
            "limit": ("不准", "允许", "申请", "报备"),
            "task": ("报备", "检查", "命令", "羞耻", "台词"),
        },
    },
    "上司下属play": {
        "cell_names": {
            "lock": "加班扣留",
            "place": "办公地点",
            "limit": "职场规矩",
            "task": "上司指令",
            "pose": "汇报姿势",
            "clear": "临时批准",
            "extend": "加班延长",
            "back": "退回重做",
            "forward": "批准前进",
            "replace": "改派任务",
        },
        "preferred": {
            "place": ("办公", "会议", "深夜便利店仓库"),
            "prop": ("领带", "白衬衫", "制服外套", "皮带"),
            "limit": ("不准", "申请", "报备", "允许"),
            "task": ("报备", "命令", "检查", "验收", "台词"),
        },
    },
    "女仆主人play": {
        "cell_names": {
            "lock": "女仆停步",
            "place": "侍奉地点",
            "limit": "主人规矩",
            "task": "侍奉任务",
            "pose": "服从姿势",
            "clear": "主人放行",
            "extend": "侍奉加时",
            "back": "重新侍奉",
            "forward": "奖励前进",
            "replace": "更换命令",
        },
        "preferred": {
            "place": ("厨房", "沙发", "床尾", "门后", "化妆台"),
            "prop": ("围巾", "项圈", "铃铛项圈", "白衬衫", "吊袜带"),
            "limit": ("不准", "命令", "验收", "允许"),
            "task": ("伺候", "命令", "验收", "夸乖", "围裙"),
        },
    },
    "大小姐管家play": {
        "cell_names": {
            "lock": "大小姐扣留",
            "place": "宅邸地点",
            "limit": "礼仪规矩",
            "task": "管家侍奉",
            "pose": "礼仪验收",
            "clear": "大小姐放行",
            "extend": "侍奉加时",
            "back": "退回听令",
            "forward": "准许前进",
            "replace": "改换吩咐",
        },
        "preferred": {
            "place": ("沙发", "玄关", "厨房", "化妆台", "衣帽间", "床尾"),
            "prop": ("项圈", "铃铛项圈", "领带", "白衬衫", "制服外套"),
            "limit": ("小玥", "不准", "命令", "验收", "允许"),
            "task": ("小玥", "伺候", "命令", "验收", "夸乖", "围裙"),
        },
    },
    "医生检查play": {
        "cell_names": {
            "lock": "检查暂停",
            "place": "检查地点",
            "limit": "检查规矩",
            "task": "检查项目",
            "pose": "检查姿势",
            "clear": "检查结束",
            "extend": "复查延长",
            "back": "退回复查",
            "forward": "检查通过",
            "replace": "更换项目",
        },
        "preferred": {
            "place": ("按摩床", "洗手台", "浴室", "床尾"),
            "prop": ("手套", "眼罩", "润滑液", "束缚带", "皮革手套"),
            "limit": ("不准", "检查", "允许", "报备"),
            "task": ("检查", "报备", "命令", "验收"),
        },
    },
    "秘书老板play": {
        "cell_names": {
            "lock": "老板扣留",
            "place": "办公室地点",
            "limit": "老板规矩",
            "task": "秘书任务",
            "pose": "汇报姿势",
            "clear": "老板批准",
            "extend": "加班延长",
            "back": "退回重做",
            "forward": "批准前进",
            "replace": "改派任务",
        },
        "preferred": {
            "place": ("办公", "会议", "落地窗", "KTV", "车后座"),
            "prop": ("领带", "白衬衫", "制服外套", "口红", "丝袜"),
            "limit": ("不准", "申请", "报备", "允许"),
            "task": ("报备", "命令", "检查", "验收", "台词"),
        },
    },
    "成人补课play": {
        "cell_names": {
            "lock": "补课罚停",
            "place": "补课地点",
            "limit": "补课规矩",
            "task": "课后作业",
            "pose": "验收姿势",
            "clear": "下课放行",
            "extend": "补课加时",
            "back": "退回重讲",
            "forward": "答对前进",
            "replace": "改换题目",
        },
        "preferred": {
            "place": ("教室", "图书馆", "沙发", "床尾"),
            "prop": ("戒尺", "眼罩", "领带", "白衬衫", "制服"),
            "limit": ("不准", "允许", "申请", "报备"),
            "task": ("报备", "检查", "命令", "羞耻", "台词"),
        },
    },
    "骑士公主play": {
        "cell_names": {
            "lock": "骑士扣留",
            "place": "城堡地点",
            "limit": "骑士誓约",
            "task": "守护命令",
            "pose": "宣誓姿势",
            "clear": "公主放行",
            "extend": "誓约加时",
            "back": "退回宣誓",
            "forward": "准许前进",
            "replace": "改换誓约",
        },
        "preferred": {
            "place": ("小木屋", "壁炉", "床尾", "阳台", "落地窗"),
            "prop": ("项圈", "牵引绳", "领带", "皮带", "丝带"),
            "limit": ("不准", "允许", "申请", "报备"),
            "task": ("命令", "报备", "检查", "验收", "标记"),
        },
    },
    "吸血鬼人类play": {
        "cell_names": {
            "lock": "夜色扣留",
            "place": "夜间地点",
            "limit": "眷属规矩",
            "task": "吸血鬼发令",
            "pose": "标记验收",
            "clear": "暂时放行",
            "extend": "夜色加时",
            "back": "退回听令",
            "forward": "准许前进",
            "replace": "改换标记",
        },
        "preferred": {
            "place": ("落地窗", "浴室", "床尾", "门后", "小木屋", "天台"),
            "prop": ("项圈", "牵引绳", "眼罩", "丝带", "口红"),
            "limit": ("小玥", "不准", "命令", "验收", "允许"),
            "task": ("小玥", "命令", "验收", "标记", "伺候"),
        },
    },
}

CELL_EVENTS: dict[int, dict[str, Any]] = {
    1: {"kind": "state", "slot": "theme", "duration": "until_finish", "name": "本局玩法"},
    3: {"kind": "lock", "slot": "prop", "actions": 1, "name": "道具锁定"},
    4: {"kind": "state", "slot": "place", "duration": "minutes", "minutes": 10, "name": "地点追加"},
    6: {"kind": "back", "slot": "limit", "steps": 2, "duration": "until_clear", "name": "限制拖回"},
    8: {"kind": "clear", "steps": 1, "name": "解除状态"},
    9: {"kind": "lock", "slot": "prop", "actions": 2, "name": "行动权锁定"},
    11: {"kind": "state", "slot": "task", "duration": "minutes", "minutes": 15, "name": "任务追加"},
    12: {"kind": "forward", "steps": 2, "name": "奖励前进"},
    14: {"kind": "extend", "name": "状态延长"},
    15: {"kind": "swap", "slot": "place", "duration": "until_finish", "name": "位置交换"},
    17: {"kind": "lock", "slot": "prop", "actions": 3, "name": "强制停步"},
    18: {"kind": "replace", "slot": "place", "duration": "minutes", "minutes": 12, "name": "地点替换"},
    20: {"kind": "state", "slot": "limit", "duration": "until_clear", "name": "限制追加"},
    21: {"kind": "back", "slot": "task", "steps": 3, "duration": "until_clear", "name": "任务压回"},
    23: {"kind": "clear", "steps": 2, "name": "解除加速"},
    24: {"kind": "state", "slot": "pose", "duration": "until_finish", "name": "姿势锁定"},
    26: {"kind": "lock", "slot": "prop", "actions": 2, "name": "道具压制"},
    27: {"kind": "replace", "slot": "prop", "duration": "minutes", "minutes": 10, "name": "道具替换"},
    29: {"kind": "extend", "name": "状态加时"},
    30: {"kind": "swap", "slot": "limit", "duration": "until_clear", "name": "位置反转"},
    31: {"kind": "back", "slot": "limit", "steps": 2, "duration": "until_clear", "name": "规则拖回"},
    33: {"kind": "state", "slot": "task", "duration": "until_finish", "name": "终局任务"},
    34: {"kind": "lock", "slot": "prop", "actions": 1, "name": "终点前停步"},
    35: {"kind": "clear", "steps": 0, "name": "最终整理"},
}


def _cell_event_key(event: dict[str, Any]) -> str:
    kind = str(event.get("kind") or "").strip()
    slot = str(event.get("slot") or "").strip()
    if kind == "state" and slot in {"theme", "place", "prop", "task", "limit", "pose"}:
        return slot
    if kind in {"lock", "clear", "extend", "swap", "back", "forward", "replace"}:
        return kind
    if slot in DEFAULT_CELL_LABELS:
        return slot
    return kind or slot


def _cell_event_name(state: dict[str, Any], cell: int, event: dict[str, Any]) -> str:
    key = _cell_event_key(event)
    if key == "theme":
        return DEFAULT_CELL_LABELS["theme"]

    profile = state.get("theme_profile") if isinstance(state.get("theme_profile"), dict) else {}
    theme = str(profile.get("theme") or "").strip()
    theme_style = THEME_CELL_STYLES.get(theme) or {}
    theme_names = theme_style.get("cell_names") if isinstance(theme_style.get("cell_names"), dict) else {}
    if key in theme_names:
        return str(theme_names[key])

    direction = str(profile.get("direction") or "").strip()
    direction_style = DIRECTION_CELL_STYLES.get(direction) or {}
    direction_names = direction_style.get("cell_names") if isinstance(direction_style.get("cell_names"), dict) else {}
    if key in direction_names:
        return str(direction_names[key])

    return DEFAULT_CELL_LABELS.get(key) or str(event.get("name") or f"第 {cell} 格")


def _public_cell_events(state: dict[str, Any]) -> list[dict[str, Any]]:
    board_size = int(state.get("board_size") or DEFAULT_BOARD_SIZE)
    events: list[dict[str, Any]] = []
    for position, event in sorted(CELL_EVENTS.items()):
        if position <= 0 or position >= board_size:
            continue
        events.append(
            {
                "position": position,
                "kind": str(event.get("kind") or ""),
                "slot": str(event.get("slot") or ""),
                "name": _cell_event_name(state, position, event),
                "effect": _cell_effect_text(event),
            }
        )
    return events


def _cell_effect_text(event: dict[str, Any]) -> str:
    kind = str(event.get("kind") or "").strip()
    slot_label = _slot_label(str(event.get("slot") or "").strip())
    if kind == "state":
        duration = _event_duration_text(event)
        return f"追加{slot_label}" + (f"（{duration}）" if duration else "")
    if kind == "lock":
        actions = max(1, int(event.get("actions") or 1))
        return f"追加{slot_label}，失去 {actions} 次行动权"
    if kind == "back":
        steps = max(1, int(event.get("steps") or 1))
        return f"追加{slot_label}，后退 {steps} 格"
    if kind == "forward":
        steps = max(1, int(event.get("steps") or 1))
        return f"前进 {steps} 格"
    if kind == "clear":
        steps = int(event.get("steps") or 0)
        return "解除一个状态" + (f"，前进 {steps} 格" if steps else "")
    if kind == "extend":
        return "延长最近状态"
    if kind == "replace":
        return f"替换或追加{slot_label}"
    if kind == "swap":
        return f"追加{slot_label}，交换位置"
    return str(event.get("name") or "事件")


def _event_duration_text(event: dict[str, Any]) -> str:
    duration = str(event.get("duration") or "").strip()
    if duration == "minutes":
        minutes = max(1, int(event.get("minutes") or 10))
        return f"{minutes} 分钟"
    if duration == "until_finish":
        return "直到终点"
    if duration == "until_clear":
        return "直到解除"
    return ""


def _slot_label(key: str) -> str:
    if not key:
        return "状态"
    return str(_slot_by_key(key).get("label") or key or "状态").strip()


def cmd(command: str = "", save_path: str | Path | None = None) -> str:
    """Run one private board command and return the Du-facing text."""
    result = run_command(command, save_path=save_path)
    return str(result.get("du_text") or result.get("text") or "")


def run_command(command: str = "", save_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(save_path) if save_path is not None else DEFAULT_SAVE_PATH
    action, args = _parse_command(command)
    with _locked_save(path):
        if action == "new_game":
            state = _new_state(seed=args.get("seed"), board_size=args.get("board_size"))
            _save_state(path, state)
            return _result(state, ["新局已开始。"], command=command or "new_game")

        if action == "end_game":
            state = _load_or_new(path)
            state["game_over"] = True
            state["result"] = "ended_by_player"
            state["ended_at"] = now_beijing_iso()
            _append_log(state, "本局已手动结束。")
            _save_state(path, state)
            return _result(state, ["本局已结束。"], command=command or "end_game")

        state = _load_or_new(path)
        _cleanup_expired_statuses(state)
        if action in {"open", "status"}:
            _save_state(path, state)
            return _result(state, ["当前局面如下。"], command=command or "打开")

        if action == "roll":
            lines = _roll(state, dice=args.get("dice"))
            _cleanup_expired_statuses(state)
            _save_state(path, state)
            return _result(state, lines, command=command or "roll")

        _save_state(path, state)
        return _result(state, [f"没看懂命令：{command or ''}".strip(), COMMAND_HINT], command=command or "")


def _process_lock_for(path: Path) -> threading.Lock:
    key = str(path.expanduser().resolve())
    with _PROCESS_LOCKS_GUARD:
        lock = _PROCESS_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PROCESS_LOCKS[key] = lock
        return lock


@contextmanager
def _locked_save(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    process_lock = _process_lock_for(path)
    with process_lock:
        lock_path = path.with_name(f"{path.name}.lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _parse_command(command: str) -> tuple[str, dict[str, Any]]:
    raw = str(command or "").strip()
    if not raw:
        return "open", {}
    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = raw.split()
    first = (parts[0] if parts else raw).strip().lower()
    aliases = {
        "打开": "open",
        "继续": "open",
        "look": "status",
        "状态": "status",
        "status": "status",
        "new": "new_game",
        "new_game": "new_game",
        "重开": "new_game",
        "开局": "new_game",
        "roll": "roll",
        "掷骰": "roll",
        "扔骰子": "roll",
        "骰子": "roll",
        "结束": "end_game",
        "结束本局": "end_game",
        "end": "end_game",
        "end_game": "end_game",
    }
    action = aliases.get(first, "roll" if re.fullmatch(r"[1-6]", first) else "")
    args: dict[str, Any] = {}
    seed_match = re.search(r"\bseed=([^\s]+)", raw)
    if seed_match:
        args["seed"] = seed_match.group(1).strip()
    board_match = re.search(r"\b(?:size|board_size)=(\d+)", raw)
    if board_match:
        args["board_size"] = max(12, min(80, int(board_match.group(1))))
    dice = _parse_dice(raw, parts)
    if dice:
        args["dice"] = dice
    return action or "unknown", args


def _parse_dice(raw: str, parts: list[str]) -> int | None:
    for pattern in (r"\bdice=([1-6])\b", r"\b点数=([1-6])\b"):
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    for part in parts[1:] if parts else []:
        if re.fullmatch(r"[1-6]", part):
            return int(part)
    if parts and re.fullmatch(r"[1-6]", parts[0]):
        return int(parts[0])
    return None


def _new_state(seed: str | None = None, board_size: int | None = None) -> dict[str, Any]:
    resolved_seed = str(seed or "").strip() or secrets.token_hex(4)
    size = int(board_size or DEFAULT_BOARD_SIZE)
    return {
        "schema_version": SCHEMA_VERSION,
        "game_id": GAME_ID,
        "seed": resolved_seed,
        "board_size": max(12, min(80, size)),
        "created_at": now_beijing_iso(),
        "updated_at": now_beijing_iso(),
        "turn_index": 0,
        "positions": {"xinyue": 0, "du": 0},
        "turn_actor": "xinyue",
        "statuses": {"xinyue": [], "du": []},
        "theme_profile": {},
        "game_over": False,
        "winner": "",
        "result": "",
        "event_log": [],
    }


def _load_or_new(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _new_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _new_state()
    state = data if isinstance(data, dict) else _new_state()
    if state.get("schema_version") != SCHEMA_VERSION:
        return _new_state()
    _normalize_state(state)
    return state


def _normalize_state(state: dict[str, Any]) -> None:
    state.setdefault("game_id", GAME_ID)
    state.setdefault("seed", secrets.token_hex(4))
    state["board_size"] = max(12, min(80, int(state.get("board_size") or DEFAULT_BOARD_SIZE)))
    positions = state.get("positions") if isinstance(state.get("positions"), dict) else {}
    state["positions"] = {actor: max(0, int(positions.get(actor) or 0)) for actor in ACTORS}
    statuses = state.get("statuses") if isinstance(state.get("statuses"), dict) else {}
    state["statuses"] = {
        actor: [item for item in statuses.get(actor, []) if isinstance(item, dict)]
        for actor in ACTORS
    }
    if state.get("turn_actor") not in ACTORS:
        state["turn_actor"] = "xinyue"
    state.setdefault("turn_index", 0)
    state.setdefault("event_log", [])
    profile = state.get("theme_profile") if isinstance(state.get("theme_profile"), dict) else {}
    state["theme_profile"] = _normalize_theme_profile(profile)
    if not state["theme_profile"]:
        _sync_theme_profile(state)
    state.setdefault("game_over", False)
    state.setdefault("winner", "")
    state.setdefault("result", "")


def _save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_beijing_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _roll(state: dict[str, Any], dice: int | None = None) -> list[str]:
    if state.get("game_over"):
        return ["本局已经结束。"]
    actor = str(state.get("turn_actor") or "xinyue")
    if actor not in ACTORS:
        actor = "xinyue"
    if _actor_blocked(state, actor):
        consumed = _consume_block_action(state, actor)
        other = _other_actor(actor)
        state["turn_actor"] = other if not _actor_blocked(state, actor) else other
        return [f"{_name(actor, DU_VIEW_NAMES)}当前没有行动权，消耗 1 次限制。{consumed}".strip()]

    rolled = dice if dice in {1, 2, 3, 4, 5, 6} else random.Random(_rng_seed(state, actor, "dice")).randint(1, 6)
    old_pos = int(state["positions"].get(actor) or 0)
    new_pos = min(int(state["board_size"]), old_pos + int(rolled))
    state["positions"][actor] = new_pos
    state["turn_index"] = int(state.get("turn_index") or 0) + 1
    lines = [f"{_name(actor, DU_VIEW_NAMES)}掷出 {rolled}，从 {old_pos} 走到 {new_pos}。"]

    if new_pos >= int(state["board_size"]):
        _finish_game(state, actor)
        lines.append(_finish_line(actor, DU_VIEW_NAMES))
        _append_log(state, " / ".join(lines))
        return lines

    event_lines = _apply_cell_event(state, actor, new_pos)
    lines.extend(event_lines)

    if int(state["positions"].get(actor) or 0) >= int(state["board_size"]):
        _finish_game(state, actor)
        lines.append(_finish_line(actor, DU_VIEW_NAMES))
        _append_log(state, " / ".join(lines))
        return lines

    turn_line = _advance_turn(state, actor)
    if turn_line:
        lines.append(turn_line)
    _append_log(state, " / ".join(lines))
    return lines


def _apply_cell_event(state: dict[str, Any], actor: str, cell: int) -> list[str]:
    event = CELL_EVENTS.get(cell)
    if not event:
        return [f"第 {cell} 格没有追加状态。"]
    kind = str(event.get("kind") or "")
    name = _cell_event_name(state, cell, event)
    if kind == "state":
        status = _add_status_from_event(state, actor, event)
        return [f"第 {cell} 格：{name}，追加 {status['label']}：{status['value']}（{_duration_text(status)}）。"]
    if kind == "lock":
        status = _add_status_from_event(state, actor, event, blocks_action=True)
        return [f"第 {cell} 格：{name}，追加 {status['label']}：{status['value']}，失去 {status.get('remaining_actions')} 次行动权。"]
    if kind == "back":
        status = _add_status_from_event(state, actor, event)
        steps = int(event.get("steps") or 1)
        state["positions"][actor] = max(0, int(state["positions"].get(actor) or 0) - steps)
        return [f"第 {cell} 格：{name}，追加 {status['label']}：{status['value']}，后退 {steps} 格。"]
    if kind == "forward":
        steps = int(event.get("steps") or 1)
        state["positions"][actor] = min(int(state["board_size"]), int(state["positions"].get(actor) or 0) + steps)
        return [f"第 {cell} 格：{name}，前进 {steps} 格。"]
    if kind == "clear":
        removed = _remove_latest_status(state, actor)
        steps = int(event.get("steps") or 0)
        if steps:
            state["positions"][actor] = min(int(state["board_size"]), int(state["positions"].get(actor) or 0) + steps)
        tail = f"，前进 {steps} 格" if steps else ""
        return [f"第 {cell} 格：{name}，解除 {removed or '无可解除状态'}{tail}。"]
    if kind == "extend":
        extended = _extend_latest_status(state, actor)
        return [f"第 {cell} 格：{name}，{extended}。"]
    if kind == "replace":
        removed = _remove_latest_status_by_slot(state, actor, str(event.get("slot") or ""))
        status = _add_status_from_event(state, actor, event)
        prefix = f"替换 {removed}，" if removed else ""
        return [f"第 {cell} 格：{name}，{prefix}追加 {status['label']}：{status['value']}（{_duration_text(status)}）。"]
    if kind == "swap":
        status = _add_status_from_event(state, actor, event)
        other = _other_actor(actor)
        state["positions"][actor], state["positions"][other] = state["positions"][other], state["positions"][actor]
        return [f"第 {cell} 格：{name}，追加 {status['label']}：{status['value']}，双方交换位置。"]
    return [f"第 {cell} 格：事件未生效。"]


def _add_status_from_event(
    state: dict[str, Any],
    actor: str,
    event: dict[str, Any],
    *,
    blocks_action: bool = False,
) -> dict[str, Any]:
    slot_key = str(event.get("slot") or "").strip()
    slot = _slot_by_key(slot_key)
    label = str(slot.get("label") or slot_key or "状态").strip()
    value = _pick_slot_value(state, actor, int(state["positions"].get(actor) or 0), slot_key)
    status = {
        "id": secrets.token_hex(4),
        "slot": slot_key,
        "label": label,
        "value": value,
        "created_at": now_beijing_iso(),
        "blocks_action": bool(blocks_action),
    }
    duration = str(event.get("duration") or "").strip()
    if blocks_action:
        status["duration_type"] = "actions"
        status["remaining_actions"] = max(1, int(event.get("actions") or 1))
    elif duration == "minutes":
        minutes = max(1, int(event.get("minutes") or 10))
        status["duration_type"] = "minutes"
        status["minutes"] = minutes
        status["expires_at"] = _iso_from_now(minutes)
    elif duration == "until_finish":
        status["duration_type"] = "until_finish"
    else:
        status["duration_type"] = "until_clear"
    state["statuses"][actor].append(status)
    if slot_key == "theme":
        state["theme_profile"] = _theme_profile_for(value)
    return status


def _slot_by_key(key: str) -> dict[str, Any]:
    for slot in PRIVATE_DRAW_SLOTS:
        if str(slot.get("key") or "").strip() == key:
            return slot
    return {"key": key, "label": key or "状态", "options": [key or "状态"]}


def _pick_slot_value(state: dict[str, Any], actor: str, cell: int, slot_key: str) -> str:
    slot = _slot_by_key(slot_key)
    options = [str(item).strip() for item in slot.get("options", []) if str(item).strip()]
    options = _filter_options_for_theme(state, slot_key, options)
    if not options:
        return str(slot.get("label") or slot_key or "状态").strip()
    rng = random.Random(_rng_seed(state, actor, slot_key, str(cell), str(len(state["statuses"].get(actor, [])))))
    return options[rng.randrange(len(options))]


def _filter_options_for_theme(state: dict[str, Any], slot_key: str, options: list[str]) -> list[str]:
    if slot_key not in {"task", "limit"}:
        return _prefer_options_for_theme(state, slot_key, options)
    direction = str((state.get("theme_profile") or {}).get("direction") or "").strip()
    if direction == "du_leads":
        return _prefer_options_for_theme(state, slot_key, _filter_du_leads_options(slot_key, options))
    if direction == "xinyue_leads":
        return _prefer_options_for_theme(state, slot_key, _filter_xinyue_leads_options(slot_key, options))
    return _prefer_options_for_theme(state, slot_key, options)


def _prefer_options_for_theme(state: dict[str, Any], slot_key: str, options: list[str]) -> list[str]:
    profile = state.get("theme_profile") if isinstance(state.get("theme_profile"), dict) else {}
    theme = str(profile.get("theme") or "").strip()
    style = THEME_CELL_STYLES.get(theme) or {}
    preferred = (style.get("preferred") or {}).get(slot_key) if isinstance(style.get("preferred"), dict) else None
    patterns = tuple(str(item).strip() for item in (preferred or ()) if str(item).strip())
    if not patterns:
        return options
    filtered = [item for item in options if _contains_any(item, patterns)]
    return filtered or options


def _filter_du_leads_options(slot_key: str, options: list[str]) -> list[str]:
    if slot_key == "task":
        filtered = [
            item
            for item in options
            if not _contains_any(item, PRIVATE_DRAW_XINYUE_CONTROL_TASK_PATTERNS)
        ]
        return filtered or options
    filtered = []
    for item in options:
        if _contains_any(item, PRIVATE_DRAW_KEEP_LIMIT_PATTERNS):
            filtered.append(item)
            continue
        if _contains_any(item, PRIVATE_DRAW_XINYUE_CONTROL_LIMIT_PATTERNS):
            continue
        filtered.append(item)
    return filtered or options


def _filter_xinyue_leads_options(slot_key: str, options: list[str]) -> list[str]:
    if slot_key == "task":
        preferred = [
            item
            for item in options
            if _contains_any(item, PRIVATE_DRAW_XINYUE_CONTROL_TASK_PATTERNS)
            or _contains_any(item, ("伺候小玥", "给小玥看", "交给小玥", "听小玥", "小玥决定", "小玥命令"))
        ]
        pool = preferred or options
        filtered = [item for item in pool if not _contains_any(item, DU_CONTROL_TASK_PATTERNS)]
        return filtered or pool or options
    preferred = [
        item
        for item in options
        if _contains_any(item, PRIVATE_DRAW_XINYUE_CONTROL_LIMIT_PATTERNS)
        or _contains_any(item, PRIVATE_DRAW_KEEP_LIMIT_PATTERNS)
    ]
    pool = preferred or options
    filtered = [item for item in pool if not _contains_any(item, DU_CONTROL_LIMIT_PATTERNS)]
    return filtered or pool or options


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern and pattern in text for pattern in patterns)


def _theme_profile_for(theme: str) -> dict[str, str]:
    label = str(theme or "").strip()
    if not label:
        return {}
    if label in THEME_DIRECTION_XINYUE_LEADS:
        return {"theme": label, "direction": "xinyue_leads", "direction_label": "小玥主导"}
    if label in THEME_DIRECTION_DU_LEADS:
        return {"theme": label, "direction": "du_leads", "direction_label": "渡主导"}
    return {"theme": label, "direction": "open", "direction_label": "开放方向"}


def _normalize_theme_profile(profile: dict[str, Any]) -> dict[str, str]:
    theme = str(profile.get("theme") or "").strip()
    if not theme:
        return {}
    return _theme_profile_for(theme)


def _rng_seed(state: dict[str, Any], *parts: str) -> str:
    base = [str(state.get("seed") or ""), str(state.get("turn_index") or 0)]
    base.extend(str(part) for part in parts)
    return ":".join(base)


def _remove_latest_status(state: dict[str, Any], actor: str) -> str:
    statuses = state["statuses"].get(actor) or []
    if not statuses:
        return ""
    item = statuses.pop()
    if str(item.get("slot") or "") == "theme":
        _sync_theme_profile(state)
    return _status_brief(item)


def _remove_latest_status_by_slot(state: dict[str, Any], actor: str, slot: str) -> str:
    statuses = state["statuses"].get(actor) or []
    for idx in range(len(statuses) - 1, -1, -1):
        item = statuses[idx]
        if str(item.get("slot") or "") == slot:
            statuses.pop(idx)
            if slot == "theme":
                _sync_theme_profile(state)
            return _status_brief(item)
    return ""


def _sync_theme_profile(state: dict[str, Any]) -> None:
    for actor in reversed(ACTORS):
        for status in reversed(state["statuses"].get(actor) or []):
            if str(status.get("slot") or "") == "theme":
                state["theme_profile"] = _theme_profile_for(str(status.get("value") or ""))
                return
    state["theme_profile"] = {}


def _extend_latest_status(state: dict[str, Any], actor: str) -> str:
    statuses = state["statuses"].get(actor) or []
    if not statuses:
        return "没有可延长状态"
    item = statuses[-1]
    if item.get("duration_type") == "actions":
        item["remaining_actions"] = max(0, int(item.get("remaining_actions") or 0)) + 1
        return f"{_status_brief(item)} 延长 1 次行动"
    if item.get("duration_type") == "minutes":
        item["minutes"] = max(1, int(item.get("minutes") or 0)) + 5
        item["expires_at"] = _iso_from_now(5, base_iso=str(item.get("expires_at") or ""))
        return f"{_status_brief(item)} 延长 5 分钟"
    item["duration_type"] = "until_finish"
    return f"{_status_brief(item)} 锁定到终点"


def _actor_blocked(state: dict[str, Any], actor: str) -> bool:
    for status in state["statuses"].get(actor) or []:
        if status.get("blocks_action") and int(status.get("remaining_actions") or 0) > 0:
            return True
    return False


def _consume_block_action(state: dict[str, Any], actor: str) -> str:
    statuses = state["statuses"].get(actor) or []
    for status in list(statuses):
        if not status.get("blocks_action") or int(status.get("remaining_actions") or 0) <= 0:
            continue
        status["remaining_actions"] = int(status.get("remaining_actions") or 0) - 1
        if int(status.get("remaining_actions") or 0) <= 0:
            statuses.remove(status)
            return f"{_status_brief(status)} 已解除。"
        return f"{_status_brief(status)} 还剩 {status.get('remaining_actions')} 次。"
    return ""


def _advance_turn(state: dict[str, Any], actor: str) -> str:
    next_actor = _other_actor(actor)
    if _actor_blocked(state, next_actor):
        consumed = _consume_block_action(state, next_actor)
        if _actor_blocked(state, next_actor):
            state["turn_actor"] = actor
            return f"{_name(next_actor, DU_VIEW_NAMES)}没有行动权，{_name(actor, DU_VIEW_NAMES)}继续行动。{consumed}".strip()
        state["turn_actor"] = next_actor
        return f"{_name(next_actor, DU_VIEW_NAMES)}的行动权恢复。{consumed}".strip()
    state["turn_actor"] = next_actor
    return f"下一次行动：{_name(next_actor, DU_VIEW_NAMES)}。"


def _finish_game(state: dict[str, Any], actor: str) -> None:
    state["positions"][actor] = int(state["board_size"])
    state["game_over"] = True
    state["winner"] = actor
    state["result"] = "winner_control"
    state["ended_at"] = now_beijing_iso()


def _finish_line(actor: str, names: dict[str, str]) -> str:
    return f"{_name(actor, names)}到达终点，获得最终状态栏决定权。"


def _cleanup_expired_statuses(state: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    for actor in ACTORS:
        kept = []
        for status in state["statuses"].get(actor) or []:
            if status.get("duration_type") != "minutes":
                kept.append(status)
                continue
            expires_at = _parse_iso(str(status.get("expires_at") or ""))
            if expires_at and expires_at <= now:
                continue
            kept.append(status)
        state["statuses"][actor] = kept


def _iso_from_now(minutes: int, base_iso: str = "") -> str:
    base = _parse_iso(base_iso) or datetime.now(timezone.utc)
    return (base + timedelta(minutes=minutes)).isoformat()


def _parse_iso(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _result(state: dict[str, Any], lines: list[str], *, command: str) -> dict[str, Any]:
    public_state = _public_state(state)
    du_text = _render_text(state, lines, DU_VIEW_NAMES)
    player_text = _render_text(state, lines, PLAYER_VIEW_NAMES)
    return {
        "ok": True,
        "game_id": GAME_ID,
        "command": command,
        "text": du_text,
        "du_text": du_text,
        "player_text": player_text,
        "board": {
            "du": _render_board(state, DU_VIEW_NAMES),
            "player": _render_board(state, PLAYER_VIEW_NAMES),
        },
        "state": public_state,
        "game_over": bool(state.get("game_over")),
        "winner": str(state.get("winner") or ""),
        "result": str(state.get("result") or ""),
        "commands": ["打开", "status", "roll", "roll 3", "new_game", "end_game"],
    }


def _public_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "board_size": int(state.get("board_size") or DEFAULT_BOARD_SIZE),
        "positions": deepcopy(state.get("positions") or {}),
        "turn_actor": str(state.get("turn_actor") or "xinyue"),
        "statuses": deepcopy(state.get("statuses") or {}),
        "theme_profile": deepcopy(state.get("theme_profile") or {}),
        "cell_events": _public_cell_events(state),
        "game_over": bool(state.get("game_over")),
        "winner": str(state.get("winner") or ""),
        "result": str(state.get("result") or ""),
        "updated_at": str(state.get("updated_at") or ""),
    }


def _render_text(state: dict[str, Any], lines: list[str], names: dict[str, str]) -> str:
    translated = [_translate_line(line, names) for line in lines if str(line or "").strip()]
    out = ["【涩涩走格棋】", *translated]
    out.append("")
    out.append(f"跑道：{_render_board(state, names)}")
    theme_line = _render_theme_profile(state)
    if theme_line:
        out.append(theme_line)
    out.append(f"当前行动：{_name(str(state.get('turn_actor') or 'xinyue'), names)}")
    out.append("状态栏：")
    for actor in ACTORS:
        out.append(f"- {_name(actor, names)}：{_render_statuses(state, actor, names)}")
    if state.get("game_over") and state.get("winner"):
        out.append(_finish_line(str(state.get("winner") or ""), names))
    out.append(COMMAND_HINT)
    return "\n".join(out).strip()


def _translate_line(line: str, names: dict[str, str]) -> str:
    if names is DU_VIEW_NAMES:
        return line
    text = line.replace("小玥", "\u0000")
    text = re.sub(
        r"(^|[：，。；、\s-])我(?=(掷出|当前没有行动权|没有行动权|继续行动|的行动权恢复|到达终点|：))",
        r"\1渡",
        text,
    )
    return text.replace("\u0000", "我")


def _render_board(state: dict[str, Any], names: dict[str, str]) -> str:
    positions = state.get("positions") if isinstance(state.get("positions"), dict) else {}
    board_size = int(state.get("board_size") or DEFAULT_BOARD_SIZE)
    tokens: list[str] = []
    start_markers = _markers_at(positions, 0, names)
    tokens.append("起点" + (f"({start_markers})" if start_markers else ""))
    for pos in range(1, board_size):
        markers = _markers_at(positions, pos, names)
        tokens.append(markers or "□")
    finish_markers = _markers_at(positions, board_size, names, finish=True)
    tokens.append((finish_markers + "/终点") if finish_markers else "终点")
    return " ".join(tokens)


def _render_theme_profile(state: dict[str, Any]) -> str:
    profile = state.get("theme_profile") if isinstance(state.get("theme_profile"), dict) else {}
    theme = str(profile.get("theme") or "").strip()
    if not theme:
        return ""
    direction = str(profile.get("direction_label") or "").strip()
    return f"本局主题：{theme}" + (f"（{direction}）" if direction else "")


def _markers_at(positions: dict[str, Any], pos: int, names: dict[str, str], *, finish: bool = False) -> str:
    markers = []
    for actor in ACTORS:
        actor_pos = int(positions.get(actor) or 0)
        if actor_pos == pos or (finish and actor_pos >= pos):
            markers.append(_name(actor, names))
    return "/".join(markers)


def _render_statuses(state: dict[str, Any], actor: str, names: dict[str, str]) -> str:
    statuses = state["statuses"].get(actor) or []
    if not statuses:
        return "无"
    return "；".join(_translate_line(_status_brief(status), names) for status in statuses[-6:])


def _status_brief(status: dict[str, Any]) -> str:
    label = str(status.get("label") or status.get("slot") or "状态").strip()
    value = str(status.get("value") or "").strip()
    return f"{label}：{value}（{_duration_text(status)}）"


def _duration_text(status: dict[str, Any]) -> str:
    duration_type = str(status.get("duration_type") or "").strip()
    if duration_type == "actions":
        return f"剩余 {max(0, int(status.get('remaining_actions') or 0))} 次行动"
    if duration_type == "minutes":
        minutes = int(status.get("minutes") or 0)
        return f"{minutes} 分钟"
    if duration_type == "until_finish":
        return "直到终点"
    return "直到解除"


def _append_log(state: dict[str, Any], text: str) -> None:
    log = state.get("event_log") if isinstance(state.get("event_log"), list) else []
    log.append({"at": now_beijing_iso(), "text": str(text or "").strip()})
    state["event_log"] = log[-40:]


def _name(actor: str, names: dict[str, str]) -> str:
    return names.get(actor, actor)


def _other_actor(actor: str) -> str:
    return "du" if actor == "xinyue" else "xinyue"
