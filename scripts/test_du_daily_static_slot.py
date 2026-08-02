#!/usr/bin/env python3
"""Focused contract for the Du Daily static prompt slot."""

from __future__ import annotations

import ast
import copy
import sys
import types
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_PATH = ROOT / "pipeline" / "pipeline.py"


def _load_prompt_order_namespace() -> dict:
    constant_names = {
        "_DYNAMIC_SYSTEM_MARKER",
        "_TEMPORARY_DYNAMIC_SYSTEM_MARKER",
        "_LAST4_SYSTEM_MARKER",
        "_SUMMARY_CACHE_SYSTEM_MARKER",
        "_SUMMARY_RECENT_SYSTEM_MARKER",
        "_TOOL_RESULT_CACHE_SYSTEM_MARKER",
        "_THINKING_RULES_SYSTEM_MARKER",
        "_ENTRY_STYLE_SYSTEM_MARKER",
        "_SUMITALK_REAL_MODE_SYSTEM_MARKER",
        "_DU_DAILY_SYSTEM_MARKER",
        "_PLAY_NOTE_SYSTEM_MARKER",
        "_SYSTEM_PROMPT_REGION_ORDER",
        "_SYSTEM_PROMPT_CACHE_GROUPS",
        "SUMITALK_REAL_MODE_PROMPT",
        "SUMITALK_APP_PROMPT",
    }
    function_names = {
        "_is_persistent_dynamic_system",
        "_ensure_dynamic_region",
        "_ensure_dynamic_system",
        "_append_to_dynamic_system",
        "_system_prompt_region",
        "_merge_system_region",
        "step_inject_tool_result_cache",
        "step_inject_sumitalk_real_mode",
        "step_inject_du_daily",
    }
    tree = ast.parse(PIPELINE_PATH.read_text(encoding="utf-8"), filename=str(PIPELINE_PATH))
    selected = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            assigned = {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            if assigned & constant_names:
                selected.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in function_names:
            selected.append(node)
    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            *selected,
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    namespace = {"copy": copy}
    exec(compile(module, str(PIPELINE_PATH), "exec"), namespace)
    return namespace


def test_du_daily_is_static_between_sumitalk_mode_and_recent_memory() -> None:
    pipeline = _load_prompt_order_namespace()
    services = types.ModuleType("services")
    services.__path__ = []
    du_daily = types.ModuleType("services.du_daily")
    du_daily.get_prepared_state = lambda: ({"version": 1}, False)
    du_daily.format_inject_block = lambda state, trigger, maintenance_mode: "DAILY"
    tool_result_cache = types.ModuleType("services.tool_result_cache")
    tool_result_cache.prompt_system_contents = lambda: []
    services.du_daily = du_daily
    services.tool_result_cache = tool_result_cache

    with patch.dict(
        sys.modules,
        {
            "services": services,
            "services.du_daily": du_daily,
            "services.tool_result_cache": tool_result_cache,
        },
    ):
        for enabled, app_request, expected_mode in (
            (True, False, pipeline["SUMITALK_REAL_MODE_PROMPT"]),
            (False, True, pipeline["SUMITALK_APP_PROMPT"]),
        ):
            body = {
                "messages": [
                    {"role": "system", "content": "CORE"},
                    {"role": "system", "content": "STABLE", "__summary_cache__": True},
                    {"role": "system", "content": "RECENT", "__summary_recent__": True},
                    {"role": "system", "content": "DYNAMIC", "__dynamic__": True},
                    {"role": "user", "content": "hello"},
                ]
            }
            body = pipeline["step_inject_sumitalk_real_mode"](
                body,
                enabled=enabled,
                app_request=app_request,
            )
            injected = pipeline["step_inject_du_daily"](body, "tg_test")
            daily = next(msg for msg in injected["messages"] if msg.get("content") == "\n\nDAILY")
            assert daily.get("__du_daily__") is True
            assert not daily.get("__dynamic__")
            result = pipeline["step_inject_tool_result_cache"](injected)

            assert [msg["content"] for msg in result["messages"]] == [
                "CORE",
                f"{expected_mode}\n\n\n\nDAILY\n\nSTABLE\n\nRECENT",
                "DYNAMIC",
                "hello",
            ]
            assert result["messages"][1].get("__summary_recent__") is True
            assert not result["messages"][1].get("__dynamic__")
            assert result["messages"][2].get("__dynamic__") is True


if __name__ == "__main__":
    test_du_daily_is_static_between_sumitalk_mode_and_recent_memory()
    print("PASS test_du_daily_is_static_between_sumitalk_mode_and_recent_memory")
