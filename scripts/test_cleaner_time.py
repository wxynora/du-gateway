#!/usr/bin/env python3
"""自测：RikkaHub 时间 strip / tool 结果 normalize。"""
import sys
sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 2)[0])

from pipeline.cleaner import (
    _strip_rikkahub_time_artifacts,
    _normalize_rikkahub_time_tool_result,
    clean_message_content_for_forward,
)

def main():
    # 1) strip: time_reminder 整块删
    t1 = 'hello <time_reminder>Current time: 11:56</time_reminder> world'
    r1 = _strip_rikkahub_time_artifacts(t1)
    assert "<time_reminder>" not in r1, r1

    # 2) strip: {"year":...} JSON 整段删
    t2 = 'pre {"year":2026,"month":3,"day":13,"weekday":"星期五","time":"10:45:05"} post'
    r2 = _strip_rikkahub_time_artifacts(t2)
    assert "year" not in r2 and "10:45" not in r2, r2

    # 3) normalize: tool 结果只保留 HH:mm
    t3 = '{"year":2026,"month":3,"day":13,"weekday":"星期五","time":"10:45:05"}'
    r3 = _normalize_rikkahub_time_tool_result(t3)
    assert r3 == "10:45", repr(r3)

    # 4) role=tool 时 content 被 normalize 成 10:45
    msg_tool = {"role": "tool", "content": t3}
    out = clean_message_content_for_forward(t3, msg_tool)
    assert out == "10:45", repr(out)

    # 5) role=user 时整段 JSON 被 strip，不会保留
    msg_user = {"role": "user", "content": "现在几点？ " + t2}
    out_user = clean_message_content_for_forward("现在几点？ " + t2, msg_user)
    assert "year" not in out_user and "10:45:05" not in out_user

    print("cleaner time self-check OK")

if __name__ == "__main__":
    main()
