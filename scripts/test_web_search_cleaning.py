from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.web_search_tools import _decode_response_text, _post_clean_text


def test_mojibake_line_is_removed_but_image_desc_stays() -> None:
    mojibake = "测试中文内容".encode("utf-8").decode("latin1")
    raw = f"[图片：一张证件照风格的男性正面头像。]\n\n{mojibake} {mojibake} Fable 5 Mythos {mojibake}"
    cleaned = _post_clean_text(raw)
    assert "证件照风格" in cleaned
    assert "æ" not in cleaned
    assert "Ã" not in cleaned


def test_normal_chinese_and_ascii_are_kept() -> None:
    raw = "Fable 5 和 Mythos 5 是 Anthropic 相关传闻，需要继续核验。"
    assert _post_clean_text(raw) == raw


def test_decode_response_prefers_readable_utf8_over_wrong_header() -> None:
    text = "这是一段正常中文网页正文，包含 Fable 5。"
    resp = SimpleNamespace(content=text.encode("utf-8"), encoding="latin1", apparent_encoding="utf-8", text="")
    decoded = _decode_response_text(resp)
    assert "正常中文" in decoded
    assert "æ" not in decoded


if __name__ == "__main__":
    test_mojibake_line_is_removed_but_image_desc_stays()
    test_normal_chinese_and_ascii_are_kept()
    test_decode_response_prefers_readable_utf8_over_wrong_header()
    print("ok")
