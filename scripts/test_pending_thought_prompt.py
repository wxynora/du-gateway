import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.pending_thoughts import format_inject_block


def run() -> None:
    prompt = format_inject_block(
        [
            {
                "id": "pending-test-1",
                "text": "晚点问她吃饭没",
                "status": "pending",
            }
        ]
    )
    expected = "继续留着（不需要输出标记）"
    assert expected in prompt, f"待续念头保留规则缺少明确的无标记合同: {prompt!r}"
    assert "继续留着，或用隐藏标记" not in prompt, f"仍保留会诱导 keep 的旧文案: {prompt!r}"
    print("pending thought prompt wording test passed")


if __name__ == "__main__":
    run()
