#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PROXY_HARNESS = r"""
const fs = require("fs");
const Module = require("module");
const path = require("path");

const proxyPath = path.join(process.cwd(), "scripts", "claude_oauth_proxy.js");
const source = fs.readFileSync(proxyPath, "utf8");
const listenIdx = source.lastIndexOf("server.listen(PORT, HOST");
if (listenIdx <= 0) throw new Error("proxy server entrypoint not found");

const testModule = new Module(proxyPath, module);
testModule.filename = proxyPath;
testModule.paths = Module._nodeModulePaths(path.dirname(proxyPath));
testModule._compile(
  `${source.slice(0, listenIdx)}\nmodule.exports = { openaiToAnthropic, processAnthropicBody };\n`,
  proxyPath
);

const { openaiToAnthropic, processAnthropicBody } = testModule.exports;
const input = JSON.parse(fs.readFileSync(0, "utf8"));

(async () => {
  const body = await openaiToAnthropic(input);
  processAnthropicBody(body);
  process.stdout.write(JSON.stringify(body));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""

RECENT_PREFIX = "\n\n【近期记忆（最近）】\n【最近】\n"
RECENT_CLOSING = "\n【以上为最近记忆】"


def _recent_summary(chunks: list[str]) -> str:
    rendered_chunks = [
        f"（2026-07-29 晚上）\n{chunk}"
        for chunk in chunks
    ]
    return RECENT_PREFIX + "\n\n".join(rendered_chunks) + RECENT_CLOSING


def _request_body(chunks: list[str]) -> dict:
    return {
        "model": "claude-opus-4-6",
        "messages": [
            {"role": "system", "content": "STATIC"},
            {
                "role": "system",
                "content": "TOOL-SUMMARY",
                "__tool_result_cache__": True,
            },
            {"role": "system", "content": "ENTRY", "__entry_style__": True},
            {"role": "system", "content": "REAL", "__sumitalk_real_mode__": True},
            {"role": "system", "content": "STABLE", "__summary_cache__": True},
            {
                "role": "system",
                "content": _recent_summary(chunks),
                "__summary_recent__": True,
            },
            {"role": "system", "content": "DYNAMIC", "__dynamic__": True},
            {"role": "user", "content": "hello"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "noop",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    }


def _anthropic_body(chunks: list[str]) -> dict:
    result = subprocess.run(
        ["node", "-e", PROXY_HARNESS],
        cwd=ROOT,
        input=json.dumps(_request_body(chunks), ensure_ascii=False),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def _recent_blocks(body: dict) -> list[dict]:
    system = body["system"]
    start = next(
        index
        for index, block in enumerate(system)
        if str(block.get("text") or "").startswith(RECENT_PREFIX)
    )
    end = next(
        index
        for index in range(start, len(system))
        if str(system[index].get("text") or "") == RECENT_CLOSING
    )
    return system[start : end + 1]


def _signature(block: dict) -> tuple[str, str]:
    return str(block.get("type") or ""), str(block.get("text") or "")


def test_recent_summary_tail_rewrite_keeps_previous_written_prefix() -> None:
    seed_chunks = ["稳定小段 A"]
    added_chunks = [*seed_chunks, "当前小段 B 初稿"]
    changed_chunks = [*seed_chunks, "当前小段 B 改写稿"]
    seed = _anthropic_body(seed_chunks)
    added = _anthropic_body(added_chunks)
    changed = _anthropic_body(changed_chunks)

    seed_blocks = _recent_blocks(seed)
    added_blocks = _recent_blocks(added)
    changed_blocks = _recent_blocks(changed)
    seed_body = seed_blocks[:-1]
    added_body = added_blocks[:-1]
    changed_body = changed_blocks[:-1]

    assert [_signature(block) for block in added_body[: len(seed_body)]] == [
        _signature(block) for block in seed_body
    ]
    assert [_signature(block) for block in changed_body[: len(seed_body)]] == [
        _signature(block) for block in seed_body
    ]
    assert len(added_body) == len(seed_body) + 1
    assert len(changed_body) == len(seed_body) + 1
    assert _signature(added_body[-1]) != _signature(changed_body[-1])

    assert "".join(block["text"] for block in seed_blocks) == _recent_summary(seed_chunks)
    assert "".join(block["text"] for block in added_blocks) == _recent_summary(added_chunks)
    assert "".join(block["text"] for block in changed_blocks) == _recent_summary(changed_chunks)

    assert not seed_blocks[-1].get("cache_control")
    assert not added_blocks[-1].get("cache_control")
    assert not changed_blocks[-1].get("cache_control")
    assert seed_body[-1].get("cache_control")
    assert added_body[-1].get("cache_control")
    assert changed_body[-1].get("cache_control")
    assert not added_body[-2].get("cache_control")
    assert not changed_body[-2].get("cache_control")

    assert sum(bool(block.get("cache_control")) for block in seed["system"]) == 3
    assert sum(bool(block.get("cache_control")) for block in added["system"]) == 3
    assert sum(bool(block.get("cache_control")) for block in changed["system"]) == 3
    assert seed["tools"][-1].get("cache_control")
    assert added["tools"][-1].get("cache_control")
    assert changed["tools"][-1].get("cache_control")

    internal_markers = {
        "__dynamic__",
        "__summary_cache__",
        "__summary_recent__",
        "__tool_result_cache__",
        "__entry_style__",
        "__sumitalk_real_mode__",
        "__play_note__",
    }
    assert not any(internal_markers.intersection(block) for block in changed["system"])


if __name__ == "__main__":
    test_recent_summary_tail_rewrite_keeps_previous_written_prefix()
    print("prompt cache recent-summary block preservation checks passed")
