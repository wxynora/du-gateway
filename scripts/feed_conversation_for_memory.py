#!/usr/bin/env python3
"""
【已弃用】归档已完成，本脚本不再使用。保留代码仅供查阅。

---
预喂对话：只做动态层记忆，不经过聊天接口、不写窗口存档、不做窗口总结。
把已有 N 轮对话按轮过一遍动态层 DS，只更新 dynamic_memory/current.json（及可能的 core_cache/卧室 Notion）。

省 API 方式：
- 本地预筛：明显空轮（极短/纯嗯啊哦）不调 DS，直接跳过。
- 批处理：--batch-size N（默认 8），每 N 轮打成一个请求，用 archive_ds_prompt 一次返回 N 条决策，再逐条应用。

用法：python scripts/feed_conversation_for_memory.py [--window-id ""] [--batch-size 8] <input.json>
输入 JSON 三种形式任选其一：
  - 标准：{"window_id":"","rounds":[{"user":"...","assistant":"..."}, ...]}
  - RikkaHub 导出（数组，每项含 node_index、messages 字符串）：自动切轮，且可初筛：设 ARCHIVE_ALLOWED_MODEL_IDS=渡的modelId（逗号分隔）只保留该助手
  - 整段消息 / 根即数组：[{"role":"user","content":"..."}, ...]，按 user→assistant 自动切轮（无 modelId 无法初筛）

一键停止：运行 python scripts/stop_feed_archive.py 或在本目录创建 feed_archive.stop 文件，
脚本每批/每轮前会检查，发现即退出，不再调 DS。

断点续跑：出错或手动停掉后，下次用同一命令（同一 input_json、同一 batch_size）再跑会从断点继续；
续跑时仍使用每轮 JSON 里的 timestamp/createdAt 等，不会变成「实时时间」。强制从头用 --from-start。
"""
import argparse
import atexit
import json
import os
import re
import sys
from pathlib import Path

# 项目根
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 停止信号：存在则下一批/下一轮后退出
STOP_FILE = Path(__file__).resolve().parent / "feed_archive.stop"
# 断点续跑：记录已完成的批次数，重跑时跳过已完成的批次，不重复花 API 钱
CHECKPOINT_FILE = Path(__file__).resolve().parent / "feed_archive_checkpoint.json"
# 单实例锁：同一时间只允许一个归档脚本在跑，避免重复写入
LOCK_FILE = Path(__file__).resolve().parent / "feed_archive.lock"


def _process_exists(pid: int) -> bool:
    """当前平台下进程是否仍在运行。"""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return True


def _take_lock() -> None:
    """启动时占锁；若已有同脚本在跑则退出并提示先停掉。"""
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            pid = None
        if pid is not None and _process_exists(pid):
            print(
                "已有归档脚本在运行 (PID=%s)，请先执行 python scripts/stop_feed_archive.py 或等其结束后再跑，避免重复写入。"
                " 若确认没有其它归档在跑，可删除 scripts/feed_archive.lock 后重试。" % pid,
                file=sys.stderr,
            )
            sys.exit(1)
        LOCK_FILE.unlink(missing_ok=True)
    try:
        LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass


def _release_lock() -> None:
    """退出时释放锁。"""
    if LOCK_FILE.exists():
        try:
            LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass


def _should_stop() -> bool:
    return STOP_FILE.exists()


def _load_checkpoint(
    input_path: Path,
    input_mtime: float,
    batch_size: int,
    total_non_empty: int,
) -> int:
    """返回已完成的批次数（0 表示从头跑）。仅当输入文件、batch_size、非空轮数一致时才续跑。"""
    if not CHECKPOINT_FILE.exists():
        return 0
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            ck = json.load(f)
        if ck.get("input_path") != str(input_path.resolve()):
            return 0
        if ck.get("input_mtime") != input_mtime:
            return 0
        if ck.get("batch_size") != batch_size or ck.get("total_non_empty") != total_non_empty:
            return 0
        return max(0, int(ck.get("batches_done", 0)))
    except Exception:
        return 0


def _save_checkpoint(
    input_path: Path,
    input_mtime: float,
    batch_size: int,
    total_non_empty: int,
    batches_done: int,
) -> None:
    try:
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "input_path": str(input_path.resolve()),
                    "input_mtime": input_mtime,
                    "batch_size": batch_size,
                    "total_non_empty": total_non_empty,
                    "batches_done": batches_done,
                },
                f,
                ensure_ascii=False,
            )
    except Exception:
        pass


def _clear_checkpoint() -> None:
    if CHECKPOINT_FILE.exists():
        try:
            CHECKPOINT_FILE.unlink(missing_ok=True)
        except Exception:
            pass


from config import ARCHIVE_ALLOWED_MODEL_IDS
from pipeline.cleaner import build_round_cleaned_for_r2
from pipeline.pipeline import _apply_one_decision
from services.archive_notion import write_archive_entry
from utils.time_aware import parse_iso_to_beijing

def _parse_from_date(s: str):
    """--from-date 解析为 date，格式 YYYY-MM-DD。"""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            from datetime import date
            return date(int(s[:4]), int(s[5:7]), int(s[8:10]))
        except ValueError:
            pass
    return None
from services.dynamic_layer_ds import call_archive_batch_ds
from storage import r2_store

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
try:
    from rikkahub_export_to_feed import parse_rikkahub_export
except ImportError:
    parse_rikkahub_export = None


def _round_timestamp(round_item) -> str | None:
    """从一轮的原始数据里取时间（供小本本/归档用「每轮对话自己的时间」）。无则返回 None，归档不会把实时时间写进 Notion。"""
    if isinstance(round_item, dict):
        return (
            (round_item.get("timestamp") or round_item.get("createdAt")
            or round_item.get("created_at") or round_item.get("time") or round_item.get("date"))
            or None
        )
    if isinstance(round_item, list) and len(round_item) > 0:
        # 小本本在 assistant 里，用最后一条（assistant）的 createdAt
        last = round_item[-1] if len(round_item) > 1 else round_item[0]
        if isinstance(last, dict):
            return last.get("createdAt") or last.get("created_at") or last.get("timestamp") or last.get("date") or None
    return None


def _extract_content_from_message(m: dict) -> str:
    """从单条消息里取出正文。支持顶层 content/text，或 RikkaHub 风格 parts（只取 type=text 的 text）。"""
    if not m or not isinstance(m, dict):
        return ""
    if "content" in m and m["content"]:
        return (m["content"] or "").strip()
    if "text" in m and m["text"]:
        return (m["text"] or "").strip()
    parts = m.get("parts") or []
    if not isinstance(parts, list):
        return ""
    texts = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        if p.get("type") == "text" and "text" in p:
            texts.append((p.get("text") or "").strip())
    return "\n".join(texts).strip()


def _round_to_messages(round_item: dict | list) -> list:
    """把一轮转成 [user_msg, assistant_msg]，均为 {role, content}。"""
    if isinstance(round_item, list):
        return [{"role": m.get("role", "user"), "content": _extract_content_from_message(m) if isinstance(m, dict) else ""} for m in round_item]
    u = (round_item.get("user") or "").strip()
    a = (round_item.get("assistant") or "").strip()
    return [
        {"role": "user", "content": u},
        {"role": "assistant", "content": a},
    ]


def _messages_to_rounds(messages: list) -> list[dict]:
    """
    把「整段消息列表」自动切分成轮次。
    规则：按顺序，每遇到 user 就开一轮；紧跟的 assistant 作为该轮回复；没有跟 assistant 则 assistant 为空。
    孤立的 assistant（前面没有 user）当作一轮，user 为空。
    每条消息可为 { "role", "content" } 或 { "role", "parts": [{ "type": "text", "text": "..." }] }（RikkaHub 风格），
    时间取该轮最后一条的 createdAt/timestamp。
    """
    if not messages or not isinstance(messages, list):
        return []
    rounds = []
    i = 0
    while i < len(messages):
        m = messages[i] if isinstance(messages[i], dict) else {}
        role = (m.get("role") or "user").strip().lower()
        content = _extract_content_from_message(m)
        ts = m.get("createdAt") or m.get("created_at") or m.get("timestamp")

        if role == "user":
            user_content = content
            i += 1
            if i < len(messages):
                next_m = messages[i] if isinstance(messages[i], dict) else {}
                next_role = (next_m.get("role") or "").strip().lower()
                if next_role == "assistant":
                    ast_content = _extract_content_from_message(next_m)
                    round_item = {"user": user_content, "assistant": ast_content}
                    if next_m.get("createdAt") or next_m.get("created_at") or next_m.get("timestamp"):
                        round_item["timestamp"] = next_m.get("createdAt") or next_m.get("created_at") or next_m.get("timestamp")
                    rounds.append(round_item)
                    i += 1
                    continue
            rounds.append({"user": user_content, "assistant": ""})
        elif role == "assistant":
            round_item = {"user": "", "assistant": content}
            if ts is not None:
                round_item["timestamp"] = ts
            rounds.append(round_item)
            i += 1
        else:
            i += 1
    return rounds


# 明显无信息：总字数过少或几乎全是语气词（嗯啊哦好呃唉呀哈、标点、空格）
_EMPTY_PATTERN = re.compile(r"^[\s\u3000\u3002\u002e\u2026\u55ef\u54c8\u597d\u5440\u5443\u5509\u54c8\u0021\uff01\u563f\u5b83]*$", re.I)

# 写入 Notion 记忆库前过滤：过短或纯废话不写，避免随便什么废话都存
_NOTION_ARCHIVE_MIN_LEN = 6


def _is_junk_archive_content(content: str) -> bool:
    """True 表示这条是废话/过短，不要写入 Notion 记忆库。"""
    s = (content or "").strip()
    if len(s) < _NOTION_ARCHIVE_MIN_LEN:
        return True
    s_compact = re.sub(r"\s+", "", s)
    if len(s_compact) < _NOTION_ARCHIVE_MIN_LEN:
        return True
    if len(s_compact) <= 20 and _EMPTY_PATTERN.match(s_compact):
        return True
    return False


def _is_likely_empty_round(messages: list) -> bool:
    """True 表示本轮极可能无信息，可本地跳过不调 DS。"""
    if not messages or len(messages) < 2:
        return True
    text = " ".join((m.get("content") or "").strip() for m in messages if isinstance(m, dict))
    text = re.sub(r"\s+", "", text)
    if len(text) < 8:
        return True
    if len(text) <= 20 and _EMPTY_PATTERN.match(text):
        return True
    return False


def main():
    print("本脚本已弃用（归档已完成），不再执行。", file=sys.stderr)
    sys.exit(0)

    parser = argparse.ArgumentParser(description="预喂对话，只过动态层 DS，不写窗口存档、不做总结")
    parser.add_argument("input_json", type=Path, help="JSON 文件：含 window_id 与 rounds（如 渡1.json）")
    parser.add_argument("--window-id", default="", help="覆盖 JSON 里的 window_id")
    parser.add_argument("--batch-size", type=int, default=6, help="每几轮打成一个 DS 请求（归档 prompt），默认 6")
    parser.add_argument("--from-start", action="store_true", help="强制从头开始：忽略并删除断点，从第 1 批开始跑（需先清空 R2 时配合使用）")
    parser.add_argument("--from-date", type=str, default="", help="只处理该日期及之后的轮次，格式 YYYY-MM-DD（如 2026-03-13）；无时间的轮次会被跳过")
    args = parser.parse_args()

    _take_lock()
    atexit.register(_release_lock)

    if not args.input_json.exists():
        print(f"文件不存在: {args.input_json}", file=sys.stderr)
        sys.exit(1)
    input_mtime = os.path.getmtime(args.input_json)

    with open(args.input_json, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        print("输入 JSON 文件为空", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"输入 JSON 解析失败: {e}", file=sys.stderr)
        sys.exit(1)
    if data is None:
        data = {}
    if not isinstance(data, dict) and not isinstance(data, list):
        print("输入 JSON 根节点需为对象或数组", file=sys.stderr)
        sys.exit(1)

    # 支持三种输入：① 标准 { window_id, rounds }  ② { window_id?, messages } 自动切轮  ③ 根节点即消息数组
    if isinstance(data, list):
        data = {"messages": data}
    window_id = args.window_id or (data.get("window_id") or "")
    rounds_raw = data.get("rounds")
    if rounds_raw is None or (isinstance(rounds_raw, list) and len(rounds_raw) == 0):
        messages = data.get("messages") or []
        if not isinstance(messages, list):
            messages = []
        # RikkaHub 导出格式：每项含 node_index、messages（字符串化 JSON）
        if messages and parse_rikkahub_export:
            first = messages[0] if isinstance(messages[0], dict) else {}
            if "node_index" in first and "messages" in first and isinstance(first.get("messages"), str):
                rounds_raw = parse_rikkahub_export(messages, allowed_model_ids=ARCHIVE_ALLOWED_MODEL_IDS)
                if rounds_raw:
                    msg = f"已按 RikkaHub 导出解析出 {len(rounds_raw)} 轮（共 {len(messages)} 条节点）"
                    if ARCHIVE_ALLOWED_MODEL_IDS:
                        msg += f"，初筛仅保留 modelId∈{ARCHIVE_ALLOWED_MODEL_IDS}"
                    print(msg, file=sys.stderr)
        if not rounds_raw:
            rounds_raw = _messages_to_rounds(messages)
            if rounds_raw:
                print(f"已从 messages（共 {len(messages)} 条）自动切分为 {len(rounds_raw)} 轮", file=sys.stderr)
    if rounds_raw is not None and not isinstance(rounds_raw, list):
        print("rounds 字段需为数组，已忽略", file=sys.stderr)
        rounds_raw = None
    if not rounds_raw:
        print("rounds 为空且无法从 messages 切出轮次（需提供 rounds 或 messages 数组）", file=sys.stderr)
        sys.exit(1)

    batch_size = max(1, args.batch_size)
    # 启动时删掉上次的停止信号，避免误拦
    if STOP_FILE.exists():
        STOP_FILE.unlink(missing_ok=True)
    print(f"window_id={repr(window_id)}, 共 {len(rounds_raw)} 轮, batch_size={batch_size}")
    print(f"  一键停止：运行 python scripts/stop_feed_archive.py 或创建 scripts/feed_archive.stop")

    # 批处理：只对「非空轮」打包，用 archive_ds_prompt 一批多轮请求
    from_date = _parse_from_date(getattr(args, "from_date", "") or "")
    non_empty: list[tuple[int, list, dict]] = []
    skipped_by_date = 0
    for i, item in enumerate(rounds_raw):
        round_index = i + 1
        if from_date is not None:
            round_ts = _round_timestamp(item)
            if not round_ts:
                skipped_by_date += 1
                continue
            dt = parse_iso_to_beijing(round_ts)
            if dt is None or dt.date() < from_date:
                skipped_by_date += 1
                continue
        try:
            messages = _round_to_messages(item)
        except Exception:
            continue
        if len(messages) < 2:
            continue
        user_msg, assistant_msg = messages[0], messages[1]
        try:
            round_cleaned = build_round_cleaned_for_r2(user_msg, assistant_msg)
        except Exception:
            continue
        if _is_likely_empty_round(round_cleaned):
            continue
        non_empty.append((round_index, round_cleaned, item if isinstance(item, dict) else {}))

    if from_date is not None and skipped_by_date > 0:
        print(f"已按 --from-date {args.from_date} 筛掉 {skipped_by_date} 轮（早于该日或无时间）", file=sys.stderr)
    total_batches = (len(non_empty) + batch_size - 1) // batch_size
    if getattr(args, "from_start", False):
        _clear_checkpoint()
        batches_done = 0
        print("已强制从头开始（--from-start）：断点已清除，从第 1 批开始")
    else:
        batches_done = _load_checkpoint(args.input_json, input_mtime, batch_size, len(non_empty))
    if batches_done > 0:
        print(f"断点续跑：跳过前 {batches_done} 批（已写入 {CHECKPOINT_FILE.name}），剩余 {total_batches - batches_done} 批")
    else:
        print(f"非空轮 {len(non_empty)}，预计 API 调用 {total_batches} 次（若逐轮需 {len(non_empty)} 次）")

    start_index = batches_done * batch_size
    for b in range(start_index, len(non_empty), batch_size):
        if _should_stop():
            print("检测到停止信号（feed_archive.stop），已退出")
            sys.exit(0)
        chunk = non_empty[b : b + batch_size]
        indices = [t[0] for t in chunk]
        rounds_batch = [t[1] for t in chunk]
        raw_items = [t[2] for t in chunk]
        # 小本本已齐全，归档脚本不再写小本本，只做对话归档（动态层 + Notion 记忆库）
        try:
            current_memories = r2_store.get_dynamic_memory_list()
            current_memories, changed = r2_store.ensure_dynamic_memory_ids(current_memories)
            if changed:
                r2_store.save_dynamic_memory_list(current_memories)
        except Exception as e:
            print(f"  本批 R2 读写失败（动态层），已退出: {e}", file=sys.stderr)
            sys.exit(1)
        # 给 DS 的每轮带上 round_timestamp（archive_ds_prompt 要求原样填到输出）
        rounds_for_ds = [
            {"round_timestamp": _round_timestamp(raw_item) or "", "messages": rc}
            for raw_item, rc in zip(raw_items, rounds_batch)
        ]
        try:
            decisions = call_archive_batch_ds(rounds_for_ds, current_memories)
        except Exception as e:
            print(f"  本批 DS 失败，未写断点，下次将从本批重试: {e}", file=sys.stderr)
            sys.exit(1)
        # DS 理论上返回与 rounds_for_ds 等长，为防异常只处理对齐部分
        n_apply = min(len(indices), len(rounds_batch), len(decisions), len(rounds_for_ds))
        if n_apply < len(indices):
            print(f"  警告：本批 DS 返回长度={len(decisions)}，仅处理前 {n_apply} 条", file=sys.stderr)
        for i in range(n_apply):
            round_index, round_cleaned, decision = indices[i], rounds_batch[i], decisions[i]
            try:
                # 强制用本轮对话的原始时间，不用 DS 返回的也不用手头“当前时间”
                round_ts = rounds_for_ds[i].get("round_timestamp") or ""
                if round_ts:
                    decision = {**decision, "timestamp": round_ts, "last_mentioned": round_ts}
                payload = _apply_one_decision(
                    window_id, round_index, round_cleaned, decision, current_memories
                )
                if payload:
                    # 废话、过短不写 Notion，避免随便什么都被存进去
                    if _is_junk_archive_content(payload.get("content") or ""):
                        pass
                    else:
                        # 没有本轮原始时间时不要写实时时间进 Notion，否则会显示成「当前时间」
                        promoted_at = payload.get("promoted_at") if round_ts else None
                        # 按时间判定唯一：同一时间+同一分类只保留一行，重跑或重复数据会覆盖而非新增
                        tag = payload["tag"]
                        if promoted_at:
                            dt = parse_iso_to_beijing(promoted_at)
                            canonical_time = dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else promoted_at
                            entry_id = f"{tag}_{canonical_time}"
                        else:
                            entry_id = payload["entry_id"]
                        try:
                            write_archive_entry(
                                tag,
                                entry_id=entry_id,
                                content=payload["content"],
                                promoted_at=promoted_at,
                            )
                        except Exception:
                            pass
            except Exception as e:
                print(f"  轮 {round_index} 应用决策失败: {e}", file=sys.stderr)
        current_batch_one_based = b // batch_size + 1
        print(f"  批 {current_batch_one_based}/{total_batches} 已过（轮 {indices[0]}..{indices[-1]}）")
        # 只有本批 DS 成功并跑完才写断点，失败则上面已 exit(1)，不写断点，下次从本批重试
        _save_checkpoint(
            args.input_json,
            input_mtime,
            batch_size,
            len(non_empty),
            batches_done=current_batch_one_based,
        )

    if STOP_FILE.exists():
        STOP_FILE.unlink(missing_ok=True)
    _clear_checkpoint()
    print("完成")


if __name__ == "__main__":
    main()
