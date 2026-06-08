import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.chat_tool_helpers import append_tool_results_and_continue


def _fake_tool(name: str, args: dict) -> str:
    return f"result:{name}:{args.get('round')}"


def test_tool_rounds_keep_thinking_block_signatures() -> None:
    body = {
        "messages": [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "please use tools"},
        ]
    }

    for round_no in range(1, 6):
        assistant_message = {
            "content": None,
            "tool_calls": [
                {
                    "id": f"toolu_{round_no}",
                    "type": "function",
                    "function": {
                        "name": "demo_tool",
                        "arguments": f'{{"round": {round_no}}}',
                    },
                }
            ],
            "thinking_blocks": [
                {
                    "type": "thinking",
                    "thinking": f"thinking round {round_no}",
                    "signature": f"sig-{round_no}",
                }
            ],
        }
        body = append_tool_results_and_continue(body, assistant_message, assistant_message["tool_calls"], _fake_tool)

    assistant_traces = [m for m in body["messages"] if m.get("role") == "assistant"]
    assert len(assistant_traces) == 5
    assert [m["thinking_blocks"][0]["signature"] for m in assistant_traces] == [
        "sig-1",
        "sig-2",
        "sig-3",
        "sig-4",
        "sig-5",
    ]
    assert [m["thinking_blocks"][0]["thinking"] for m in assistant_traces] == [
        "thinking round 1",
        "thinking round 2",
        "thinking round 3",
        "thinking round 4",
        "thinking round 5",
    ]


if __name__ == "__main__":
    test_tool_rounds_keep_thinking_block_signatures()
    print("ok")
