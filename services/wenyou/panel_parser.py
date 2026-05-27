import re
from typing import Optional

from services.wenyou.runtime_state import _normalize_core_ability, _parse_abilities_line


def _parse_player_panel_block(block: str, label: str) -> dict:
    """解析【主神面板】中某一玩家的字段（可部分出现）。"""
    out = {}
    m = re.search(rf"{label}\s*HP\s*(\d+)\s*/\s*(\d+)\s*精神\s*(\d+)\s*/\s*(\d+)", block)
    if m:
        out["hp"] = int(m.group(1))
        out["hp_max"] = int(m.group(2))
        out["san"] = int(m.group(3))
        out["san_max"] = int(m.group(4))
    m = re.search(rf"{label}等级[：:]\s*(\d+)", block)
    if m:
        out["level"] = int(m.group(1))
    m = re.search(rf"{label}经验[：:]\s*(\d+)", block)
    if m:
        out["exp"] = int(m.group(1))
    m = re.search(rf"{label}阶位[：:]\s*([DCSBA])", block)
    if m:
        out["rank"] = m.group(1).upper()
    m = re.search(rf"{label}体力[：:]\s*(\d+)", block)
    if m:
        out["vit"] = int(m.group(1))
    m = re.search(rf"{label}智慧[：:]\s*(\d+)", block)
    if m:
        out["wis"] = int(m.group(1))
    m = re.search(rf"{label}核心能力[：:]\s*(.+?)(?:\n|$)", block)
    if m:
        parsed = _parse_abilities_line(m.group(1))
        out["core_ability"] = _normalize_core_ability(parsed[0]) if parsed else None
    return out


def _parse_main_god_panel(gm_text: str) -> Optional[dict]:
    """解析 GM 输出的【主神面板】，失败返回 None。"""
    if "【主神面板】" not in gm_text:
        return None
    block = gm_text.split("【主神面板】", 1)[-1]
    out: dict = {}
    loc_m = re.search(r"场地[：:]\s*(\S+)", block)
    if loc_m:
        v = loc_m.group(1).strip()
        out["phase"] = "hub" if ("主神" in v or "空间" in v) else "instance_running"
    pts_m = re.search(r"积分[：:]\s*(\d+)", block)
    if pts_m:
        out["points"] = int(pts_m.group(1))
    p1 = _parse_player_panel_block(block, "玩家一")
    p2 = _parse_player_panel_block(block, "玩家二")
    if p1:
        out["player1"] = p1
    if p2:
        out["player2"] = p2
    inv_m = re.search(r"道具[：:]\s*(.+?)(?:\n|$)", block)
    if inv_m:
        raw_inv = inv_m.group(1).strip()
        if raw_inv in ("无", "无。", "-", "——"):
            out["inventory"] = []
        else:
            out["inventory"] = [x.strip() for x in re.split(r"[、，,]", raw_inv) if x.strip()][:20]
    if not out:
        return None
    return out
