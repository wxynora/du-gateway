"""
把 RikkaHub 导出的 txt/tsv（含 messages JSON）转成统一 JSON 轮次文件，不调 DS、不写 R2。

用法（在项目根目录）：
  python -m scripts.convert_rikka_export_to_json ^
    --file "C:\\Users\\doraemon\\Desktop\\渡.txt" ^
    --conversation-id "4380ebe1-d47e-471d-aa4f-53066e6dd1da" ^
    --out "data/rikka_main_rounds.json"

输出格式：
[
  {
    "index": 1,
    "messages": [ { ...user... }, { ...assistant... } ]
  },
  ...
]
"""

from __future__ import annotations

import argparse
import csv
import json
from typing import Any, Dict, List, Optional, Tuple


def _parse_args() -> argparse.Namespace:
  p = argparse.ArgumentParser(description="Rikka 导出 → JSON 轮次文件（仅转换，不写 R2）")
  p.add_argument("--file", required=True, help="RikkaHub 导出的 txt/tsv 文件路径")
  p.add_argument("--conversation-id", required=False, help="只转换指定 conversation_id")
  p.add_argument("--out", required=True, help="输出 JSON 文件路径")
  return p.parse_args()


def _load_rows(
  path: str, target_conv_id: Optional[str] = None
) -> Tuple[str, List[Tuple[int, Dict[str, Any]]]]:
  rows: List[Tuple[int, Dict[str, Any]]] = []
  conv_id_used: Optional[str] = None
  last_err: Optional[Exception] = None
  for enc in ("utf-8", "utf-8-sig", "gbk", "mbcs"):
    try:
      f = open(path, "r", encoding=enc, errors="strict")
    except LookupError:
      continue
    try:
      with f:
        reader = csv.DictReader(f, delimiter="\t")
        _ = reader.fieldnames
        for row in reader:
          conv_id = (row.get("conversation_id") or "").strip()
          if not conv_id:
            continue
          if target_conv_id:
            if conv_id != target_conv_id:
              continue
          else:
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


def _build_rounds(
  rows: List[Tuple[int, Dict[str, Any]]]
) -> List[Dict[str, Any]]:
  out: List[Dict[str, Any]] = []
  pending_user: Optional[Dict[str, Any]] = None
  idx_round = 0
  for _, msg in rows:
    role = (msg.get("role") or "").lower()
    if role == "user":
      pending_user = msg
    elif role == "assistant":
      if pending_user:
        idx_round += 1
        out.append({"index": idx_round, "messages": [pending_user, msg]})
        pending_user = None
  return out


def main() -> None:
  args = _parse_args()
  conv_id, rows = _load_rows(args.file, args.conversation_id)
  rounds = _build_rounds(rows)
  with open(args.out, "w", encoding="utf-8") as f:
    json.dump(
      {"conversation_id": conv_id, "rounds": rounds},
      f,
      ensure_ascii=False,
      indent=2,
    )
  print(f"已写出 {len(rounds)} 轮到 {args.out}（conversation_id={conv_id}）")


if __name__ == "__main__":
  main()

