from typing import Any, Optional

from services.wenyou.common import _compact_text


_WENYOU_PLAYER_IDS = ("player1", "player2")
_WENYOU_PLAYER_LABELS = {"player1": "玩家一", "player2": "玩家二"}
_WENYOU_PLAYER_CONTROLLERS = {"player1": "human", "player2": "ai"}


def _resolve_player_key(player_id: Any = "player1") -> str:
    raw = str(player_id or "player1").strip().lower()
    if raw in {"player2", "p2", "玩家二"}:
        return "player2"
    return "player1"


def _player_display_name(player_id: Any) -> str:
    return _WENYOU_PLAYER_LABELS.get(_resolve_player_key(player_id), "玩家")


def _normalize_player_display_name(value: Any, fallback: str = "") -> str:
    text = _compact_text(value, 24).replace("\n", "").replace("\r", "").strip()
    if not text:
        return fallback
    return text[:16]


def _wallet_player_display_name(wallet: Optional[dict], player_id: str, fallback: str = "") -> str:
    if not isinstance(wallet, dict):
        return fallback
    players = wallet.get("players") if isinstance(wallet.get("players"), dict) else {}
    player = players.get(player_id) if isinstance(players.get(player_id), dict) else {}
    return _normalize_player_display_name(player.get("display_name"), fallback)


def _wallet_confirmed_player_display_name(wallet: Optional[dict], player_id: str) -> str:
    if not isinstance(wallet, dict):
        return ""
    players = wallet.get("players") if isinstance(wallet.get("players"), dict) else {}
    player = players.get(player_id) if isinstance(players.get(player_id), dict) else {}
    if not player.get("display_name_set"):
        return ""
    return _normalize_player_display_name(player.get("display_name"), "")


def _session_player_display_name(session: Optional[dict], player_id: Any, fallback: str = "") -> str:
    pid = _resolve_player_key(player_id)
    default = fallback or _WENYOU_PLAYER_LABELS.get(pid, pid)
    if not isinstance(session, dict):
        return default
    st = session.get("stats") if isinstance(session.get("stats"), dict) else {}
    player = st.get(pid) if isinstance(st.get(pid), dict) else {}
    name = _normalize_player_display_name(player.get("display_name"), "")
    if name:
        return name
    fw = session.get("framework") if isinstance(session.get("framework"), dict) else {}
    name = _normalize_player_display_name(fw.get(f"{pid}_name"), "")
    return name or default


def _replace_player_aliases_for_display(text: Any, *, player1_name: str = "", player2_name: str = "") -> str:
    out = str(text or "")
    p1 = _normalize_player_display_name(player1_name, "")
    p2 = _normalize_player_display_name(player2_name, "")
    if p1 and p1 != "玩家一":
        out = out.replace("玩家一", p1)
    if p2 and p2 != "玩家二":
        out = out.replace("玩家二", p2)
    return out


def _replace_framework_player_aliases(fw: dict, text: Any) -> str:
    return _replace_player_aliases_for_display(
        text,
        player1_name=str((fw or {}).get("player1_name") or ""),
        player2_name=str((fw or {}).get("player2_name") or ""),
    )


def _replace_session_player_aliases(session: Optional[dict], text: Any) -> str:
    return _replace_player_aliases_for_display(
        text,
        player1_name=_session_player_display_name(session, "player1", "玩家一"),
        player2_name=_session_player_display_name(session, "player2", "玩家二"),
    )
