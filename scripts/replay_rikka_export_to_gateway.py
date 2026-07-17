"""
一次性脚本：把 RikkaHub 导出的对话记录（tsv/txt，含 messages JSON）按轮喂给网关的实时管道。

目标：
- 不重新调用上游模型；
- 直接用现有 pipeline 的归档逻辑：
  - 清洗一轮 user+assistant → R2 对话存档；
  - 每 4 轮触发 DeepSeek 总结（实时层「渡的回忆」）；
  - 每轮调用动态层 DS，更新 dynamic_memory / core_cache。

用法示例（在项目根目录）：
  python -m scripts.replay_rikka_export_to_gateway ^
    --file "C:\\Users\\doraemon\\Desktop\\渡.txt" ^
    --window-id "rikka_main" ^
    --conversation-id "4380ebe1-d47e-471d-aa4f-53066e6dd1da"

说明：
- --file：RikkaHub 导出的 txt/tsv 文件路径（首行是表头，至少包含 id / conversation_id / node_index / messages）。
- --window-id：在网关/R2 里使用的 window_id（可自定义，如 rikka_main / tg_xxx）。
- --conversation-id：可选；不填则使用文件中第一行的 conversation_id。
"""

from __future__ import annotations

import argparse
import csv
import json
from typing import Any, Dict, List, Optional, Tuple

from pipeline.pipeline import step_archive_and_maybe_summary
from utils.log import get_logger

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="重放 RikkaHub 导出的对话到网关实时管道")
    p.add_argument("--file", required=True, help="RikkaHub 导出的 txt/tsv 文件路径")
    p.add_argument("--window-id", required=True, help="在网关/R2 中使用的 window_id（如 rikka_main）")
    p.add_argument(
        "--conversation-id",
        required=False,
        help="只重放指定 conversation_id；不填则使用文件中第一行的 conversation_id",
    )
    p.add_argument(
        "--max-rounds",
        type=int,
        default=0,
        help="最多重放的轮数（0 表示全部）",
    )
    return p.parse_args()


def _load_rows(
    path: str, target_conv_id: Optional[str] = None
) -> Tuple[str, List[Tuple[int, Dict[str, Any]]]]:
    """
    读取 tsv 文件，按 node_index 升序返回指定 conversation_id 的 messages。
    返回：(实际使用的 conversation_id, [(node_index, message_obj), ...])。
    """
    rows: List[Tuple[int, Dict[str, Any]]] = []
    conv_id_used: Optional[str] = None
    # 尝试多种常见编码，兼容 Windows 上导出的文件（如 ANSI / GBK）
    last_err: Optional[Exception] = None
    for enc in ("utf-8", "utf-8-sig", "gbk", "mbcs"):
        try:
            f = open(path, "r", encoding=enc, errors="strict")
        except LookupError:
            continue
        try:
            with f:
                reader = csv.DictReader(f, delimiter="\t")
                # 访问一次 fieldnames 触发首行解析
                _ = reader.fieldnames
                for row in reader:
                    conv_id = (row.get("conversation_id") or "").strip()
                    if not conv_id:
                        continue
                    if target_conv_id:
                        if conv_id != target_conv_id:
                            continue
                    else:
                        # 若未指定 conversation_id，则取第一行的
                        if conv_id_used is None:
                            conv_id_used = conv_id
                        if conv_id != conv_id_used:
                            continue
                    try:
                        idx = int(row.get("node_index") or 0)
                    except ValueError:
                        continue
                    raw = row.get("messages") or ""
                    try:
                        arr = json.loads(raw)
                    except Exception as e:
                        last_err = e
                        logger.warning("解析 messages 失败 node_index=%s raw 截断=%s", idx, raw[:200])
                        continue
                    if not isinstance(arr, list) or not arr:
                        continue
                    msg = arr[0]
                    if not isinstance(msg, dict):
                        continue
                    rows.append((idx, msg))
        except Exception as e:
            last_err = e
            rows = []
            conv_id_used = None
            continue
        if rows:
            break
    if not rows:
        if last_err:
            raise SystemExit(f"未从文件中读到任何消息，最后一个解码错误: {last_err}")
        raise SystemExit("未从文件中读到任何消息，请检查路径/格式/会话 ID。")
    rows.sort(key=lambda x: x[0])
    if not target_conv_id and conv_id_used is None:
        conv_id_used = ""
    return conv_id_used or target_conv_id or "", rows


def _build_rounds(rows: List[Tuple[int, Dict[str, Any]]]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """
    根据导出的单条消息列表，组装成 [ (user_msg, assistant_msg) ... ] 轮次。
    简单假设：按时间顺序 user / assistant 交替出现。
    """
    rounds: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    pending_user: Optional[Dict[str, Any]] = None
    for idx, msg in rows:
        role = (msg.get("role") or "").lower()
        if role == "user":
            # 若前一个 user 没配到 assistant，就丢弃（或可视需求合并）
            pending_user = msg
        elif role == "assistant":
            if pending_user:
                rounds.append((pending_user, msg))
                pending_user = None
        else:
            continue
    return rounds


def main() -> None:
    args = _parse_args()
    conv_id, rows = _load_rows(args.file, args.conversation_id)
    logger.info("重放文件=%s conversation_id=%s 行数=%s", args.file, conv_id, len(rows))
    rounds = _build_rounds(rows)
    if not rounds:
        raise SystemExit("未能从导出中组装出任何 user+assistant 轮次。")
    max_rounds = int(args.max_rounds or 0)
    total = len(rounds) if max_rounds <= 0 else min(len(rounds), max_rounds)
    logger.info("共检测到轮次=%s，将重放前 %s 轮", len(rounds), total)

    for i, (user_msg, asst_msg) in enumerate(rounds[:total], start=1):
        # step_archive_and_maybe_summary 只关心「请求里的最后一个 user」和 assistant_message
        request_messages: List[Dict[str, Any]] = [user_msg]
        assistant_message: Dict[str, Any] = asst_msg
        try:
            step_archive_and_maybe_summary(args.window_id, request_messages, assistant_message)
        except Exception as e:
            logger.error("重放第 %s 轮失败 error=%s", i, e, exc_info=True)
            # 避免一条失败导致整体中断，可按需选择 continue / break
            continue
        if i % 50 == 0 or i == total:
            logger.info("已重放轮次 %s/%s", i, total)


if __name__ == "__main__":
    main()
