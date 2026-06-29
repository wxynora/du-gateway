from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


_NEXT_HIDDEN_MARKER_RE = re.compile(
    r"<<<\s*(?:END_)?[A-Z][A-Z0-9_]*\s*>{2,3}"
    r"|[\[［【]\s*(?:du\s*[:：]\s*[a-z_]+|pending\s*[:：]|pcmd\s*[:：])",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class HiddenBlockParser:
    """
    Tolerant parser for assistant-only hidden blocks such as <<<DU_THOUGHT>>>.

    It accepts the two common malformed shapes we have seen from models:
    - marker names with extra whitespace: <<< DU_THOUGHT >>>
    - one missing closing >: <<<DU_THOUGHT>>
    - optional one-line short tags when configured: [du:thought ...]
    - unclosed tail markers by hiding the tail and returning it as fallback content
    """

    marker_name: str
    marker_start: str
    marker_end: str
    start_re: re.Pattern
    end_re: re.Pattern
    block_re: re.Pattern
    short_aliases: tuple[str, ...]
    short_alias_keys: tuple[str, ...]
    short_tag_re: Optional[re.Pattern]
    short_start_re: Optional[re.Pattern]
    max_partial_chars: int

    @classmethod
    def for_markers(
        cls,
        marker_name: str,
        marker_start: str,
        marker_end: str,
        short_markers: tuple[str, ...] | list[str] | None = None,
    ) -> "HiddenBlockParser":
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
        aliases = tuple(str(x or "").strip() for x in (short_markers or ()) if str(x or "").strip())
        alias_pattern = cls._short_alias_pattern(aliases)
        short_tag_re = (
            re.compile(
                r"[\[［【]\s*(?:"
                + alias_pattern
                + r")\b\s*(?:[:：]\s*)?(.*?)\s*[\]］】]",
                flags=re.DOTALL | re.IGNORECASE,
            )
            if alias_pattern
            else None
        )
        short_start_re = (
            re.compile(
                r"[\[［【]\s*(?:"
                + alias_pattern
                + r")\b\s*(?:[:：]\s*)?",
                flags=re.IGNORECASE,
            )
            if alias_pattern
            else None
        )
        short_alias_keys = tuple(cls._compact_short_alias(x) for x in aliases)
        max_short_chars = max((len(x) for x in aliases), default=0) + 12
        max_partial_chars = max(len(marker_start), len(marker_end), len(name) + 16, max_short_chars)
        return cls(
            marker_name=name,
            marker_start=marker_start,
            marker_end=marker_end,
            start_re=start_re,
            end_re=end_re,
            block_re=block_re,
            short_aliases=aliases,
            short_alias_keys=short_alias_keys,
            short_tag_re=short_tag_re,
            short_start_re=short_start_re,
            max_partial_chars=max_partial_chars,
        )

    def split(self, full_text: str) -> tuple[str, Optional[str]]:
        """Return visible text and hidden block content. Unclosed tail blocks are hidden and recovered."""
        if not full_text or not isinstance(full_text, str):
            return full_text or "", None
        marker = self._find_next_marker(full_text)
        if not marker:
            return full_text, None
        start_i, end_i, content = marker
        visible = full_text[:start_i] + full_text[end_i:]
        return visible.strip(), content if content else None

    def split_all(self, full_text: str) -> tuple[str, list[str]]:
        """Return visible text and all hidden block contents. Unclosed tail blocks are hidden and recovered."""
        if not full_text or not isinstance(full_text, str):
            return full_text or "", []
        visible = full_text
        contents: list[str] = []
        while True:
            next_visible, content = self.split(visible)
            if next_visible == visible:
                return visible.strip(), contents
            if content:
                contents.append(content)
            visible = next_visible

    def compute_visible_streaming(self, acc: str) -> str:
        """
        Current visible text while streaming. If a start marker has begun but not closed,
        only text before the marker is visible.
        """
        if not acc:
            return ""
        visible, _contents = self.split_all(acc)
        visible = self.strip_partial_start_marker_suffix(visible)
        visible = self.strip_partial_short_marker_suffix(visible)
        return visible

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

    def strip_partial_short_marker_suffix(self, text: str) -> str:
        if not text or not self.short_alias_keys:
            return text or ""
        max_len = min(len(text), self.max_partial_chars)
        for size in range(max_len, 0, -1):
            suffix = text[-size:]
            if self._is_potential_short_marker_prefix(suffix):
                return text[:-size].rstrip()
        return text

    def _find_next_marker(self, text: str) -> Optional[tuple[int, int, str]]:
        long_start = self.start_re.search(text)
        short_start = self.short_start_re.search(text) if self.short_start_re else None
        if not long_start and not short_start:
            return None

        use_short = bool(short_start and (not long_start or short_start.start() < long_start.start()))
        if use_short and short_start:
            match = self.short_tag_re.search(text, short_start.start()) if self.short_tag_re else None
            if match and match.start() == short_start.start():
                content_start = short_start.end()
                next_marker = _NEXT_HIDDEN_MARKER_RE.search(text, content_start, match.end())
                if not next_marker:
                    return match.start(), match.end(), (match.group(1) or "").strip()
            tail_end = self._next_hidden_marker_start(text, short_start.end())
            return short_start.start(), tail_end, text[short_start.end() : tail_end].strip()

        if not long_start:
            return None
        match = self.block_re.search(text, long_start.start())
        if match and match.start() == long_start.start():
            return match.start(), match.end(), (match.group(1) or "").strip()
        tail_end = self._next_hidden_marker_start(text, long_start.end())
        return long_start.start(), tail_end, text[long_start.end() : tail_end].strip()

    @staticmethod
    def _next_hidden_marker_start(text: str, start: int) -> int:
        match = _NEXT_HIDDEN_MARKER_RE.search(text, max(0, int(start or 0)))
        return match.start() if match else len(text)

    def _is_potential_short_marker_prefix(self, candidate: str) -> bool:
        if not candidate or not self.short_alias_keys:
            return False
        s = str(candidate)
        if s[0] not in "[［【":
            return False
        rest = s[1:]
        if not rest.strip():
            return True
        compact = self._compact_short_alias(rest)
        if not compact:
            return True
        for alias in self.short_alias_keys:
            if alias.startswith(compact) or compact.startswith(alias):
                return True
        return False

    @staticmethod
    def _compact_short_alias(value: str) -> str:
        return re.sub(r"\s+", "", str(value or "").strip().lower()).replace("：", ":")

    @classmethod
    def _short_alias_pattern(cls, aliases: tuple[str, ...]) -> str:
        parts: list[str] = []
        for alias in aliases:
            normalized = str(alias or "").strip()
            if not normalized:
                continue
            split = re.split(r"[:：]", normalized, maxsplit=1)
            if len(split) == 2:
                left, right = split
                if left.strip() and right.strip():
                    parts.append(re.escape(left.strip()) + r"\s*[:：]\s*" + re.escape(right.strip()))
                    continue
            parts.append(re.escape(normalized).replace(r"\ ", r"\s+"))
        return "|".join(parts)
