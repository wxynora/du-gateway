#!/usr/bin/env python3
"""SumiTalk must reject a bare successful-looking stream terminator."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.sumitalk_chat_queue import _consume_sumitalk_chat_stream


class _BareDoneResponse:
    status_code = 200
    headers: dict[str, str] = {}

    def __init__(self) -> None:
        self.response = [b"data: [DONE]\n\n"]
        self.closed = False

    def close(self) -> None:
        self.closed = True


def main() -> None:
    response = _BareDoneResponse()
    status, payload = _consume_sumitalk_chat_stream(response, "job-empty-stream-test")

    assert response.closed is True
    assert status == 502
    assert payload == {"error": "流式响应正常结束但未返回正文或结束原因"}
    print("SumiTalk bare empty stream rejection passed")


if __name__ == "__main__":
    main()
