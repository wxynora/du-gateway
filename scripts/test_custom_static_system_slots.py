import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import pipeline
from services import prompt_manager


class CustomStaticSystemSlotsTest(unittest.TestCase):
    def test_five_optional_sections_are_registered_at_catalog_end(self) -> None:
        section_ids = [section.id for section in prompt_manager.PROMPT_SECTIONS]
        custom_sections = [
            prompt_manager.PROMPT_SECTION_MAP[section_id]
            for section_id in prompt_manager.CUSTOM_STATIC_SYSTEM_SECTION_IDS
        ]
        with patch.object(
            prompt_manager.r2_store,
            "get_prompt_manager_config",
            return_value={},
        ):
            catalog_rows = prompt_manager.list_prompt_sections()

        self.assertEqual(
            [
                "custom_static_system_1",
                "custom_static_system_2",
                "custom_static_system_3",
                "custom_static_system_4",
                "custom_static_system_5",
            ],
            list(prompt_manager.CUSTOM_STATIC_SYSTEM_SECTION_IDS),
        )
        self.assertEqual(
            list(prompt_manager.CUSTOM_STATIC_SYSTEM_SECTION_IDS),
            section_ids[-5:],
        )
        self.assertTrue(all(section.allow_empty for section in custom_sections))
        self.assertEqual(
            list(prompt_manager.CUSTOM_STATIC_SYSTEM_SECTION_IDS),
            [row["id"] for row in catalog_rows[-5:]],
        )
        self.assertTrue(all(row["allow_empty"] for row in catalog_rows[-5:]))

    def test_empty_slots_are_skipped_and_nonempty_slots_keep_order_and_text(self) -> None:
        values = {
            "custom_static_system_1": "槽位一\n保留原文",
            "custom_static_system_2": "",
            "custom_static_system_3": "  槽位三带空白  ",
            "custom_static_system_4": " \n ",
            "custom_static_system_5": "槽位五",
        }

        with patch.object(
            prompt_manager,
            "get_managed_prompt_text",
            side_effect=lambda section_id, fallback="": values.get(section_id, fallback),
        ):
            self.assertEqual(
                ["槽位一\n保留原文", "  槽位三带空白  ", "槽位五"],
                prompt_manager.get_custom_static_system_texts(),
            )

    def test_nonempty_slots_land_at_static_tail_before_tool_cache(self) -> None:
        body = {
            "messages": [
                {"role": "system", "content": "核心 Prompt"},
                {"role": "system", "content": "其他固定静态规则"},
                {
                    "role": "system",
                    "content": "Thinking 规范",
                    pipeline._THINKING_RULES_SYSTEM_MARKER: True,
                },
                {
                    "role": "system",
                    "content": "入口风格",
                    pipeline._ENTRY_STYLE_SYSTEM_MARKER: True,
                },
                {
                    "role": "system",
                    "content": "常驻动态",
                    pipeline._DYNAMIC_SYSTEM_MARKER: True,
                },
                {"role": "user", "content": "你好"},
            ]
        }

        with (
            patch(
                "services.prompt_manager.get_custom_static_system_texts",
                return_value=["自定义一", "自定义三", "自定义五"],
            ),
            patch(
                "services.tool_result_cache.prompt_system_contents",
                return_value=["工具缓存"],
            ),
        ):
            body = pipeline.step_inject_custom_static_systems(body)
            body = pipeline.step_inject_tool_result_cache(body)

        self.assertEqual(
            [message["content"] for message in body["messages"]],
            [
                "核心 Prompt\n\n其他固定静态规则\n\n自定义一\n\n自定义三\n\n自定义五",
                "工具缓存",
                "Thinking 规范",
                "入口风格",
                "常驻动态",
                "你好",
            ],
        )

    def test_main_chat_route_injects_custom_slots_before_cache_assembly(self) -> None:
        route_path = Path(__file__).resolve().parents[1] / "routes" / "chat.py"
        module = ast.parse(route_path.read_text(encoding="utf-8"))
        chat_completions = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "chat_completions"
        )
        call_lines = {
            node.func.id: node.lineno
            for node in ast.walk(chat_completions)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in {
                "step_inject_custom_static_systems",
                "step_inject_tool_result_cache",
            }
        }

        self.assertEqual(
            {
                "step_inject_custom_static_systems",
                "step_inject_tool_result_cache",
            },
            set(call_lines),
        )
        self.assertLess(
            call_lines["step_inject_custom_static_systems"],
            call_lines["step_inject_tool_result_cache"],
        )


if __name__ == "__main__":
    unittest.main()
