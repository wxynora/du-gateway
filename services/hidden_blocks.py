from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class HiddenBlockParser:
    """
    Tolerant parser for assistant-only hidden blocks such as <<<DU_THOUGHT>>>.

    It accepts the two common malformed shapes we have seen from models:
    - marker names with extra whitespace: <<< DU_THOUGHT >>>
    - one missing closing >: <<<DU_THOUGHT>>
    """

    marker_name: str
    marker_start: str
    marker_end: str
    start_re: re.Pattern
    end_re: re.Pattern
    block_re: re.Pattern
    max_partial_chars: int

    @classmethod
    def for_markers(cls, marker_name: str, marker_start: str, marker_end: str) -> "HiddenBlockParser":
        name = str(marker_name or "").strip()
        if not name:
            raise ValueError("marker_name is required")
        escaped = re.escape(name)
        end_name = f"END_{name}"
        escaped_end = re.escape(end_name)
        start_re = re.compile(r"<<<\s*" + escaped + r"\s*>{2,3}", flags=re.IGNORECASE)
        end_re = re.compile(r"<<<\s*" + escaped_end + r"\s*>{2,3}", flags=re.IGNORECASE)
        block_re = re.compile(
            r"<<<\s*" + escaped + r"\s*>{2,3}\s*(.*?)\s*<<<\s*" + escaped_end + r"\s*>{2,3}",
            flags=re.DOTALL | re.IGNORECASE,
        )
        max_partial_chars = max(len(marker_start), len(marker_end), len(name) + 16)
        return cls(
            marker_name=name,
            marker_start=marker_start,
            marker_end=marker_end,
            start_re=start_re,
            end_re=end_re,
            block_re=block_re,
            max_partial_chars=max_partial_chars,
        )

    def split(self, full_text: str) -> tuple[str, Optional[str]]:
        """Return visible text and hidden block content. Unclosed blocks are dropped from the start marker."""
        if not full_text or not isinstance(full_text, str):
            return full_text or "", None
        start = self.start_re.search(full_text)
        if not start:
            return full_text, None
        match = self.block_re.search(full_text)
        if not match:
            return full_text[: start.start()].rstrip(), None
        content = (match.group(1) or "").strip()
        visible = full_text[: match.start()] + full_text[match.end() :]
        return visible.strip(), content if content else None

    def split_all(self, full_text: str) -> tuple[str, list[str]]:
        """Return visible text and all complete hidden block contents. Unclosed tail blocks are dropped."""
        if not full_text or not isinstance(full_text, str):
            return full_text or "", []
        visible = full_text
        contents: list[str] = []
        while True:
            start = self.start_re.search(visible)
            if not start:
                return visible.strip(), contents
            match = self.block_re.search(visible)
            if not match:
                return visible[: start.start()].rstrip(), contents
            content = (match.group(1) or "").strip()
            if content:
                contents.append(content)
            visible = visible[: match.start()] + visible[match.end() :]

    def compute_visible_streaming(self, acc: str) -> str:
        """
        Current visible text while streaming. If a start marker has begun but not closed,
        only text before the marker is visible.
        """
        if not acc:
            return ""
        visible = acc
        while True:
            start = self.start_re.search(visible)
            if not start:
                return self.strip_partial_start_marker_suffix(visible)
            end = self.end_re.search(visible, start.end())
            if not end:
                return visible[: start.start()].rstrip()
            before_raw = visible[: start.start()]
            after_raw = visible[end.end() :]
            before = before_raw.rstrip()
            after = after_raw.lstrip()
            if before and after:
                visible = before + " " + after
            else:
                visible = before or after

    def strip_partial_start_marker_suffix(self, text: str) -> str:
        if not text:
            return ""
        max_len = min(len(text), self.max_partial_chars)
        for size in range(max_len, 0, -1):
            suffix = text[-size:]
            if self._is_potential_start_marker_prefix(suffix):
                return text[:-size].rstrip()
        return text

    def _is_potential_start_marker_prefix(self, candidate: str) -> bool:
        if not candidate:
            return False
        s = str(candidate)
        idx = 0
        while idx < len(s) and idx < 3:
            if s[idx] != "<":
                return False
            idx += 1
        if idx < 3:
            return idx == len(s)
        while idx < len(s) and s[idx].isspace():
            idx += 1
        if idx >= len(s):
            return True

        name = self.marker_name.lower()
        remaining = s[idx:].lower()
        name_prefix_len = min(len(remaining), len(name))
        if remaining[:name_prefix_len] != name[:name_prefix_len]:
            return False
        if len(remaining) <= len(name):
            return True
        idx += len(name)

        while idx < len(s) and s[idx].isspace():
            idx += 1
        if idx >= len(s):
            return True

        closing = s[idx:]
        return 1 <= len(closing) <= 3 and all(ch == ">" for ch in closing)
