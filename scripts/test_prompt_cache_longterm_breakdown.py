#!/usr/bin/env python3
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.prompt_cache_debug import _static_system_breakdown_parts


class PromptCacheLongtermBreakdownTest(unittest.TestCase):
    def test_longterm_memory_is_reported_as_its_own_static_block(self):
        content = "\n\n".join(
            [
                "【渡的记事本】\n- 固定事项\n【以上为固定记事本】",
                "【人称指代提醒】记忆中的“她”均指辛玥。",
                "【长期记忆（截至 2026-07-15）】\n长期摘要正文\n【以上为长期记忆】",
                "【最近一段时间（2026-07-16 至 2026-07-29）】\n中期摘要正文\n【以上为最近一段时间】",
            ]
        )

        parts = _static_system_breakdown_parts(
            {"role": "system", "content": content},
            0,
        )

        labels = [part["label"] for part in parts]
        self.assertEqual(labels, ["渡的记事本", "长期记忆", "中期记忆"])
        self.assertEqual(sum(part["chars"] for part in parts), len(content))


if __name__ == "__main__":
    unittest.main()
