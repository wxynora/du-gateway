from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from flask import Blueprint, Flask

from routes.miniapp import game_tools
from services import gomoku_game
from services.gomoku_followup import EMPTY_PLAYER_MESSAGE, send_gomoku_wakeup


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _new_game(path: Path, xinyue_color: str) -> dict:
    with patch.object(gomoku_game.secrets, "choice", return_value=xinyue_color):
        result = gomoku_game.run_command("new_game", save_path=path)
    _assert(result.get("ok") is True, f"new game failed: {result}")
    return result


def test_random_assignment_and_black_starts() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        xinyue_black = _new_game(Path(tmpdir) / "xinyue-black.json", gomoku_game.BLACK)
        black_state = xinyue_black["state"]
        _assert(
            black_state["players"] == {"xinyue": "black", "du": "white"},
            f"unexpected colors: {black_state['players']}",
        )
        _assert(black_state["turn_actor"] == "xinyue", "xinyue should start when assigned black")

        du_black = _new_game(Path(tmpdir) / "du-black.json", gomoku_game.WHITE)
        du_state = du_black["state"]
        _assert(
            du_state["players"] == {"xinyue": "white", "du": "black"},
            f"unexpected colors: {du_state['players']}",
        )
        _assert(du_state["turn_actor"] == "du", "du should start when assigned black")


def test_game_chat_persists_until_new_game() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "chat.json"
        _new_game(path, gomoku_game.BLACK)

        appended = gomoku_game.run_command(
            "append_chat "
            + json.dumps(
                {
                    "messages": [
                        {"speaker": "xinyue", "text": "我先走这里。"},
                        {"speaker": "du", "text": "那我堵住你。"},
                    ]
                },
                ensure_ascii=False,
            ),
            save_path=path,
        )
        _assert(appended.get("ok") is True, f"chat append failed: {appended}")

        restored = gomoku_game.run_command("status", save_path=path)
        _assert(
            restored["state"]["game_chat_messages"]
            == [
                {"speaker": "xinyue", "text": "我先走这里。"},
                {"speaker": "du", "text": "那我堵住你。"},
            ],
            restored["state"],
        )

        restarted = _new_game(path, gomoku_game.WHITE)
        _assert(restarted["state"]["game_chat_messages"] == [], restarted["state"])


def test_legal_turns_occupied_cell_and_five_in_a_row() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "game.json"
        _new_game(path, gomoku_game.BLACK)

        wrong_turn = gomoku_game.run_command("du_place 8-8", save_path=path)
        _assert(wrong_turn.get("error") == "NOT_YOUR_TURN", f"wrong turn accepted: {wrong_turn}")

        for col in range(1, 5):
            xinyue = gomoku_game.run_command(f"place 1-{col}", save_path=path)
            _assert(xinyue.get("ok") is True, f"xinyue move {col} failed: {xinyue}")
            du = gomoku_game.run_command(f"du_place 2-{col}", save_path=path)
            _assert(du.get("ok") is True, f"du move {col} failed: {du}")

        occupied = gomoku_game.run_command("place 1-1", save_path=path)
        _assert(occupied.get("error") == "CELL_OCCUPIED", f"occupied cell accepted: {occupied}")

        winner = gomoku_game.run_command("place 1-5", save_path=path)
        _assert(winner.get("game_over") is True, f"five did not finish: {winner}")
        _assert(winner.get("winner") == "xinyue", f"wrong winner: {winner}")
        _assert(winner.get("result") == "five_in_a_row", f"wrong result: {winner}")


def test_draw_and_undo_negotiation_state_machine() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "negotiation.json"
        _new_game(path, gomoku_game.BLACK)

        no_move_undo = gomoku_game.run_command("request_undo", save_path=path)
        _assert(no_move_undo.get("error") == "NO_MOVE_TO_UNDO", no_move_undo)

        draw_request = gomoku_game.run_command("request_draw", save_path=path)
        pending = draw_request["state"]["pending_request"]
        _assert(
            pending == {
                "type": "draw",
                "requester": "xinyue",
                "responder": "du",
            },
            pending,
        )
        _assert(draw_request["state"]["turn_actor"] == "xinyue", draw_request["state"])

        frozen = gomoku_game.run_command("place 8-8", save_path=path)
        _assert(frozen.get("error") == "REQUEST_PENDING", frozen)

        rejected = gomoku_game.run_command("du_reject_draw", save_path=path)
        _assert(rejected.get("ok") is True, rejected)
        _assert(rejected["state"]["pending_request"] is None, rejected["state"])
        _assert(rejected["state"]["turn_actor"] == "xinyue", rejected["state"])

        xinyue_move = gomoku_game.run_command("place 8-8", save_path=path)
        _assert(xinyue_move.get("ok") is True, xinyue_move)
        du_move = gomoku_game.run_command("du_place 8-9", save_path=path)
        _assert(du_move.get("ok") is True, du_move)

        undo_request = gomoku_game.run_command("request_undo", save_path=path)
        _assert(undo_request.get("ok") is True, undo_request)
        undone = gomoku_game.run_command("du_accept_undo", save_path=path)
        _assert(undone.get("ok") is True, undone)
        _assert(undone["state"]["turn_actor"] == "xinyue", undone["state"])
        _assert(undone["state"]["last_move"] is None, undone["state"])
        _assert(undone["state"]["moves"] == [], undone["state"])
        _assert(
            all(not cell for row in undone["state"]["board"] for cell in row),
            undone["state"]["board"],
        )

        gomoku_game.run_command("place 7-7", save_path=path)
        du_draw_request = gomoku_game.run_command("du_request_draw", save_path=path)
        _assert(du_draw_request.get("ok") is True, du_draw_request)
        agreed_draw = gomoku_game.run_command("accept_draw", save_path=path)
        _assert(agreed_draw.get("game_over") is True, agreed_draw)
        _assert(agreed_draw.get("result") == "agreed_draw", agreed_draw)
        _assert(agreed_draw["state"]["turn_actor"] == "", agreed_draw["state"])


def test_board_system_text_and_reply_parser() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        du_black_path = Path(tmpdir) / "du-black.json"
        du_black = _new_game(du_black_path, gomoku_game.WHITE)
        opening_system = game_tools._gomoku_system_text(du_black)
        _assert(
            "本局为 15 行 × 15 列；小玥执白；你执黑。黑先手" in opening_system,
            opening_system,
        )
        _assert("小玥刚刚落子：" not in opening_system, opening_system)
        _assert(
            opening_system
            == "\n".join(
                [
                    "小玥正在和你玩「五子棋」。这是棋局状态同步，不是主聊天正文。",
                    "本局为 15 行 × 15 列；小玥执白；你执黑。黑先手",
                    "坐标使用“行-列”，范围都是 1-15，例如 8-8。",
                    "当前行动方：你",
                    "当前棋盘：全空",
                    "",
                    "现在轮到你执黑行动。回复第一行必须单独写以下精确指令之一：",
                    "「【落子：行-列】」：请根据当前棋盘选择一个空位，每次只落一枚黑子。",
                    "「【求和：请求】」",
                    "每次只能选择一种行动，想对小玥说的话另起一行。",
                ]
            ),
            opening_system,
        )

        xinyue_black_path = Path(tmpdir) / "xinyue-black.json"
        _new_game(xinyue_black_path, gomoku_game.BLACK)
        moved = gomoku_game.run_command("place 8-8", save_path=xinyue_black_path)
        moved_system = game_tools._gomoku_system_text(moved)
        _assert("小玥刚刚落子：8-8" in moved_system, moved_system)
        _assert("现在轮到你执白行动。" in moved_system, moved_system)
        _assert("「【求和：请求】」" in moved_system, moved_system)
        _assert("「【悔棋：请求】」" not in moved_system, moved_system)
        _assert(
            "\n".join(
                [
                    "当前棋盘（●=黑，○=白，·=空；每行依次为 1-5｜6-10｜11-15 列）：",
                    "1-7：全空",
                    "8：·····|··●··|·····",
                    "9-15：全空",
                ]
            ) in moved_system,
            moved_system,
        )

        visual_board = [["" for _ in range(15)] for _ in range(15)]
        visual_board[6][6] = "white"
        visual_board[7][7] = "black"
        visual_board[7][8] = "white"
        visual_board[8][7] = "black"
        _assert(
            gomoku_game.render_board_for_system({"board": visual_board})
            == "\n".join(
                [
                    "当前棋盘（●=黑，○=白，·=空；每行依次为 1-5｜6-10｜11-15 列）：",
                    "1-6：全空",
                    "7：·····|·○···|·····",
                    "8：·····|··●○·|·····",
                    "9：·····|··●··|·····",
                    "10-15：全空",
                ]
            ),
            "compact board layout changed",
        )

        request_path = Path(tmpdir) / "xinyue-request.json"
        _new_game(request_path, gomoku_game.BLACK)
        requested = gomoku_game.run_command("request_draw", save_path=request_path)
        request_system = game_tools._gomoku_system_text(requested)
        _assert(
            request_system
            == "\n".join(
                [
                    "小玥正在和你玩「五子棋」。这是棋局状态同步，不是主聊天正文。",
                    "本局为 15 行 × 15 列；小玥执黑；你执白。黑先手",
                    "坐标使用“行-列”，范围都是 1-15，例如 8-8。",
                    "小玥向你请求和棋。",
                    "当前棋局行动方：小玥",
                    "当前需要你处理：小玥的求和请求",
                    "当前棋盘：全空",
                    "",
                    "请决定是否同意。回复第一行必须单独写精确指令「【求和：同意】」或「【求和：拒绝】」，想对小玥说的话另起一行。",
                ]
            ),
            request_system,
        )

        undo_path = Path(tmpdir) / "xinyue-undo-request.json"
        _new_game(undo_path, gomoku_game.BLACK)
        gomoku_game.run_command("place 8-8", save_path=undo_path)
        gomoku_game.run_command("du_place 8-9", save_path=undo_path)
        undo_requested = gomoku_game.run_command("request_undo", save_path=undo_path)
        undo_system = game_tools._gomoku_system_text(undo_requested)
        _assert(
            undo_system
            == "\n".join(
                [
                    "小玥正在和你玩「五子棋」。这是棋局状态同步，不是主聊天正文。",
                    "本局为 15 行 × 15 列；小玥执黑；你执白。黑先手",
                    "坐标使用“行-列”，范围都是 1-15，例如 8-8。",
                    "小玥请求悔棋。若你同意，将撤回小玥最近一手以及此后已落下的棋子，并轮到小玥重新行动。",
                    "当前棋局行动方：小玥",
                    "当前需要你处理：小玥的悔棋请求",
                    "当前棋盘（●=黑，○=白，·=空；每行依次为 1-5｜6-10｜11-15 列）：",
                    "1-7：全空",
                    "8：·····|··●○·|·····",
                    "9-15：全空",
                    "",
                    "请决定是否同意。回复第一行必须单独写精确指令「【悔棋：同意】」或「【悔棋：拒绝】」，想对小玥说的话另起一行。",
                ]
            ),
            undo_system,
        )

    parsed = game_tools._parse_gomoku_reply("【落子：9-10】\n堵住你。\n再想想。")
    _assert(
        parsed == {"action": "move", "row": 9, "col": 10, "chat_text": "堵住你。\n再想想。"},
        f"unexpected parse: {parsed}",
    )
    _assert(
        game_tools._parse_gomoku_reply("【求和：请求】\n要不要就这样？")
        == {"action": "request_draw", "chat_text": "要不要就这样？"},
        "draw request directive did not parse",
    )
    _assert(
        game_tools._parse_gomoku_reply("【悔棋：同意】")
        == {"action": "accept_undo", "chat_text": ""},
        "undo decision directive did not parse",
    )
    _assert(
        game_tools._parse_gomoku_reply("我想落 9-10\n【落子：9-10】") is None,
        "directive outside the first line should not apply",
    )
    _assert(
        game_tools._parse_gomoku_reply("【落子:9-10】") is None,
        "non-exact directive punctuation should not apply",
    )


def test_followup_uses_temporary_dynamic_system_and_real_user_content() -> None:
    calls: list[dict] = []
    fake_module = ModuleType("services.conversation_followup")

    def fake_send_wakeup_event(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "reply_text": "【落子：8-8】"}

    fake_module._send_wakeup_event = fake_send_wakeup_event
    with patch.dict(sys.modules, {"services.conversation_followup": fake_module}):
        send_gomoku_wakeup(
            window_id="sumitalk-main",
            target="phone",
            system_text="棋局 system",
            user_content="  原样内容  ",
        )
        send_gomoku_wakeup(
            window_id="sumitalk-main",
            target="phone",
            system_text="空棋盘 system",
            user_content="",
        )

    first, second = calls
    _assert(first["system_event"] is True, f"not a system event: {first}")
    _assert(
        first["dynamic_system_event"] is True,
        f"gomoku state must use the temporary dynamic system region: {first}",
    )
    _assert(
        second["dynamic_system_event"] is True,
        f"empty-message gomoku state must stay temporary dynamic: {second}",
    )
    _assert(first["event_text"] == "棋局 system", f"system changed: {first}")
    _assert(first["system_event_user_summary"] == "  原样内容  ", f"user content changed: {first}")
    _assert(
        second["system_event_user_summary"] == EMPTY_PLAYER_MESSAGE,
        f"empty message fallback changed: {second}",
    )


def test_sync_route_applies_du_move_without_external_writes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "route.json"
        _new_game(save_path, gomoku_game.WHITE)
        captured: dict = {}

        def fake_execute(game_id: str, command: str, save_id: str = "default", **_kwargs):
            _assert(game_id == "gomoku", f"unexpected game id: {game_id}")
            return gomoku_game.run_command(command, save_path=save_path)

        def fake_resolve_recent_reply_context(default_target: str = ""):
            return {
                "channel": "sumitalk",
                "window_id": "sumitalk-main",
                "target": default_target or "phone",
                "meta": {},
            }

        def fake_wakeup(**kwargs):
            captured.update(kwargs)
            return {
                "ok": True,
                "reply_text": "【落子：8-8】\n第一手先占中间。",
                "channel": "sumitalk",
            }

        app = Flask("gomoku-sync-test")
        bp = Blueprint("gomoku-sync-test-bp", __name__)
        game_tools.register_routes(bp)
        app.register_blueprint(bp)

        with (
            patch.object(game_tools, "execute_game_command", side_effect=fake_execute),
            patch.object(game_tools, "_mark_gomoku_sync_activity", return_value=None),
            patch("services.reply_channel_context.resolve_recent_reply_context", side_effect=fake_resolve_recent_reply_context),
            patch("services.gomoku_followup.send_gomoku_wakeup", side_effect=fake_wakeup),
        ):
            response = app.test_client().post(
                "/game-tools/gomoku/sync-du",
                json={"save_id": "default", "message": "来呀"},
            )

        data = response.get_json()
        _assert(response.status_code == 200, f"sync failed status={response.status_code} data={data}")
        _assert(captured["user_content"] == "来呀", f"user content wrapped: {captured}")
        _assert(captured["system_text"].startswith("小玥正在和你玩「五子棋」。"), captured["system_text"])
        _assert(data["move"] == {"actor": "du", "color": "black", "row": 8, "col": 8}, data)
        _assert(data["reply_text"] == "第一手先占中间。", data)
        _assert(data["state"]["board"][7][7] == "black", data["state"]["board"][7])
        _assert(data["state"]["turn_actor"] == "xinyue", data["state"])
        _assert(
            data["state"]["game_chat_messages"]
            == [
                {"speaker": "xinyue", "text": "来呀"},
                {"speaker": "du", "text": "第一手先占中间。"},
            ],
            data["state"],
        )
        restored = gomoku_game.run_command("status", save_path=save_path)
        _assert(
            restored["state"]["game_chat_messages"] == data["state"]["game_chat_messages"],
            restored["state"],
        )


def test_sync_route_applies_du_request_and_du_decision() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "route-negotiation.json"
        _new_game(save_path, gomoku_game.WHITE)
        replies = iter(
            [
                "【求和：请求】\n这盘要不要算平手？",
                "【悔棋：同意】\n好，给你重走。",
            ]
        )

        def fake_execute(game_id: str, command: str, save_id: str = "default", **_kwargs):
            _assert(game_id == "gomoku", f"unexpected game id: {game_id}")
            return gomoku_game.run_command(command, save_path=save_path)

        def fake_resolve_recent_reply_context(default_target: str = ""):
            return {
                "channel": "sumitalk",
                "window_id": "sumitalk-main",
                "target": default_target or "phone",
                "meta": {},
            }

        def fake_wakeup(**_kwargs):
            return {"ok": True, "reply_text": next(replies), "channel": "sumitalk"}

        app = Flask("gomoku-negotiation-sync-test")
        bp = Blueprint("gomoku-negotiation-sync-test-bp", __name__)
        game_tools.register_routes(bp)
        app.register_blueprint(bp)

        with (
            patch.object(game_tools, "execute_game_command", side_effect=fake_execute),
            patch.object(game_tools, "_mark_gomoku_sync_activity", return_value=None),
            patch("services.reply_channel_context.resolve_recent_reply_context", side_effect=fake_resolve_recent_reply_context),
            patch("services.gomoku_followup.send_gomoku_wakeup", side_effect=fake_wakeup),
        ):
            du_request_response = app.test_client().post(
                "/game-tools/gomoku/sync-du",
                json={"save_id": "default", "message": ""},
            )
            du_request = du_request_response.get_json()
            _assert(du_request_response.status_code == 200, du_request)
            _assert(du_request["action"] == "request_draw", du_request)
            _assert(du_request["state"]["pending_request"]["requester"] == "du", du_request)
            _assert(du_request["reply_text"] == "这盘要不要算平手？", du_request)

            rejected = gomoku_game.run_command("reject_draw", save_path=save_path)
            _assert(rejected.get("ok") is True, rejected)
            gomoku_game.run_command("du_place 8-8", save_path=save_path)
            gomoku_game.run_command("place 8-9", save_path=save_path)
            gomoku_game.run_command("du_place 9-9", save_path=save_path)
            requested = gomoku_game.run_command("request_undo", save_path=save_path)
            _assert(requested.get("ok") is True, requested)

            du_decision_response = app.test_client().post(
                "/game-tools/gomoku/sync-du",
                json={"save_id": "default", "message": "我想重走"},
            )
            du_decision = du_decision_response.get_json()
            _assert(du_decision_response.status_code == 200, du_decision)
            _assert(du_decision["action"] == "accept_undo", du_decision)
            _assert(du_decision["state"]["pending_request"] is None, du_decision)
            _assert(du_decision["state"]["turn_actor"] == "xinyue", du_decision)
            _assert(du_decision["reply_text"] == "好，给你重走。", du_decision)


def test_user_actions_refresh_shared_game_activity_without_external_writes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "route-activity.json"
        activity_sources: list[str] = []

        def fake_execute(game_id: str, command: str, save_id: str = "default", **_kwargs):
            _assert(game_id == "gomoku", f"unexpected game id: {game_id}")
            return gomoku_game.run_command(command, save_path=save_path)

        def fake_mark(_occurred_at: str, *, source: str, detail: dict | None = None):
            _assert((detail or {}).get("game_id") == "gomoku", detail)
            activity_sources.append(source)

        app = Flask("gomoku-activity-test")
        bp = Blueprint("gomoku-activity-test-bp", __name__)
        game_tools.register_routes(bp)
        app.register_blueprint(bp)

        with (
            patch.object(game_tools, "execute_game_command", side_effect=fake_execute),
            patch.object(game_tools, "_mark_gomoku_activity", side_effect=fake_mark),
            patch.object(gomoku_game.secrets, "choice", return_value=gomoku_game.BLACK),
        ):
            client = app.test_client()
            _assert(
                client.post("/game-tools/gomoku", json={"command": "new_game"}).status_code == 200,
                "new game route failed",
            )
            _assert(
                client.post("/game-tools/gomoku", json={"command": "request_draw"}).status_code == 200,
                "draw request route failed",
            )
            gomoku_game.run_command("du_reject_draw", save_path=save_path)
            _assert(
                client.post("/game-tools/gomoku", json={"command": "place 8-8"}).status_code == 200,
                "move route failed",
            )
            gomoku_game.run_command("du_request_draw", save_path=save_path)
            _assert(
                client.post("/game-tools/gomoku", json={"command": "reject_draw"}).status_code == 200,
                "draw decision route failed",
            )

        _assert(
            activity_sources
            == [
                "gomoku_new_game",
                "gomoku_xinyue_draw_request",
                "gomoku_xinyue_move",
                "gomoku_xinyue_draw_reject",
            ],
            activity_sources,
        )


def main() -> None:
    test_random_assignment_and_black_starts()
    test_game_chat_persists_until_new_game()
    test_legal_turns_occupied_cell_and_five_in_a_row()
    test_draw_and_undo_negotiation_state_machine()
    test_board_system_text_and_reply_parser()
    test_followup_uses_temporary_dynamic_system_and_real_user_content()
    test_sync_route_applies_du_move_without_external_writes()
    test_sync_route_applies_du_request_and_du_decision()
    test_user_actions_refresh_shared_game_activity_without_external_writes()
    print("gomoku tests ok")


if __name__ == "__main__":
    main()
