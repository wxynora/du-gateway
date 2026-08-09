"""Anthropic model feature gates derived from the public Messages API contract."""

import re


_CLAUDE_FAMILY_VERSION_RE = re.compile(
    r"claude-(?P<family>opus|fable|mythos)-(?P<major>\d+)(?:[-.](?P<minor>\d+))?",
    re.IGNORECASE,
)


def supports_mid_conversation_system(model: str) -> bool:
    """Return whether the model accepts role=system inside messages.

    Anthropic currently documents this for Fable 5+, Mythos 5+, Opus 4.8+
    and Opus 5+. Sonnet 5 is explicitly excluded by the same contract.
    """
    match = _CLAUDE_FAMILY_VERSION_RE.search(str(model or "").strip())
    if not match:
        return False
    family = match.group("family").lower()
    major = int(match.group("major"))
    minor = int(match.group("minor") or 0)
    if family == "opus":
        return major > 4 or (major == 4 and minor >= 8)
    return major >= 5
