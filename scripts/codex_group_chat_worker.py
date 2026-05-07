#!/usr/bin/env python3
"""Backward-compatible entrypoint for the Codex group chat bridge."""

from codex_group_chat_bridge import main


if __name__ == "__main__":
    raise SystemExit(main())
