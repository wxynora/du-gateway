from typing import Any


_WENYOU_PHASES = frozenset({"hub", "candidate_selection", "instance_running", "settlement", "archived"})


def _normalize_phase(value: Any, default: str = "instance_running") -> str:
    """Normalize old local phase names to the rules-doc state machine."""
    raw = str(value or "").strip().lower()
    if raw in _WENYOU_PHASES:
        return raw
    if raw in ("instance", "running", "game", "副本", "副本中", "进行中"):
        return "instance_running"
    if raw in ("main_god", "space", "主神", "主神空间", "系统空间"):
        return "hub"
    if raw in ("settle", "结算", "结算中"):
        return "settlement"
    if raw in ("archive", "归档", "已归档"):
        return "archived"
    if raw in ("selection", "candidate", "候选池", "副本选择"):
        return "candidate_selection"
    return default if default in _WENYOU_PHASES else "instance_running"


def _phase_label(phase: Any) -> str:
    return {
        "hub": "主神空间",
        "candidate_selection": "候选池",
        "instance_running": "副本中",
        "settlement": "结算中",
        "archived": "已归档",
    }.get(_normalize_phase(phase), "副本中")


def _session_phase(session: dict) -> str:
    if isinstance(session, dict) and session.get("phase"):
        return _normalize_phase(session.get("phase"))
    st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    return _normalize_phase(st.get("phase"))


def _shop_open_for_phase(phase: Any) -> bool:
    return _normalize_phase(phase) in {"hub", "settlement"}

