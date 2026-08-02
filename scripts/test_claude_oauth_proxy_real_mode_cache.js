#!/usr/bin/env node

const assert = require("assert");
const fs = require("fs");
const Module = require("module");
const path = require("path");

const proxyPath = path.join(__dirname, "claude_oauth_proxy.js");
const source = fs.readFileSync(proxyPath, "utf8");
const listenIdx = source.lastIndexOf("server.listen(PORT, HOST");
assert(listenIdx > 0, "proxy server entrypoint not found");

const testModule = new Module(proxyPath, module);
testModule.filename = proxyPath;
testModule.paths = Module._nodeModulePaths(path.dirname(proxyPath));
testModule._compile(
  `${source.slice(0, listenIdx)}\nmodule.exports = { openaiToAnthropic, processAnthropicBody };\n`,
  proxyPath
);

const { openaiToAnthropic, processAnthropicBody } = testModule.exports;
const REAL_PROMPT = "REAL MODE PROMPT";

function requestBody(realMode) {
  return {
    model: "claude-opus-4-6",
    messages: [
      { role: "system", content: "STATIC" },
      { role: "system", content: "【近期记忆】\nSTABLE", __summary_cache__: true },
      { role: "system", content: "【近期记忆（最近）】\nRECENT", __summary_recent__: true },
      ...(realMode
        ? [{ role: "system", content: REAL_PROMPT, __sumitalk_real_mode__: true }]
        : []),
      { role: "system", content: "DYNAMIC", __dynamic__: true },
      { role: "user", content: "hello" },
    ],
    tools: [{ type: "function", function: { name: "noop", parameters: { type: "object" } } }],
  };
}

function requestBodyWithToolCache(realMode = false) {
  return {
    model: "claude-opus-5",
    messages: [
      { role: "system", content: "STATIC" },
      {
        role: "system",
        content: "【最近24小时工具使用摘要】\nTOOL CACHE",
        __tool_result_cache__: true,
      },
      { role: "system", content: "ENTRY STYLE", __entry_style__: true },
      ...(realMode
        ? [{ role: "system", content: REAL_PROMPT, __sumitalk_real_mode__: true }]
        : []),
      { role: "system", content: "DAILY" },
      { role: "system", content: "【近期记忆】\nSTABLE", __summary_cache__: true },
      { role: "system", content: "【近期记忆（最近）】\nRECENT", __summary_recent__: true },
      { role: "system", content: "DYNAMIC", __dynamic__: true },
      { role: "user", content: "hello" },
    ],
    tools: [{ type: "function", function: { name: "noop", parameters: { type: "object" } } }],
  };
}

async function normalize(realMode) {
  const body = await openaiToAnthropic(requestBody(realMode));
  processAnthropicBody(body);
  return body;
}

async function normalizeWithToolCache(realMode = false) {
  const body = await openaiToAnthropic(requestBodyWithToolCache(realMode));
  processAnthropicBody(body);
  return body;
}

async function opus5Thinking(reasoningEffort) {
  return openaiToAnthropic({
    model: "claude-opus-5",
    messages: [{ role: "user", content: "hello" }],
    ...(reasoningEffort ? { reasoning_effort: reasoningEffort } : {}),
  });
}

function systemBlock(body, text) {
  return body.system.find((item) => item && item.text === text);
}

(async () => {
  const normal = await normalize(false);
  assert(systemBlock(normal, "【近期记忆（最近）】\nRECENT").cache_control);

  const real = await normalize(true);
  assert(!systemBlock(real, "【近期记忆（最近）】\nRECENT").cache_control);
  assert.deepStrictEqual(systemBlock(real, REAL_PROMPT).cache_control, {
    type: "ephemeral",
    ttl: "1h",
  });
  assert.strictEqual(systemBlock(real, REAL_PROMPT).__sumitalk_real_mode__, undefined);

  const systemBreakpoints = real.system.filter((item) => item && item.cache_control).length;
  assert.strictEqual(systemBreakpoints, 3);
  assert(real.tools[real.tools.length - 1].cache_control);

  const withToolCache = await normalizeWithToolCache();
  assert.deepStrictEqual(systemBlock(withToolCache, "STATIC").cache_control, {
    type: "ephemeral",
    ttl: "1h",
  });
  assert.deepStrictEqual(
    systemBlock(withToolCache, "【最近24小时工具使用摘要】\nTOOL CACHE").cache_control,
    {
      type: "ephemeral",
      ttl: "1h",
    }
  );
  assert.strictEqual(systemBlock(withToolCache, "DAILY").cache_control, undefined);
  assert.strictEqual(
    systemBlock(withToolCache, "【近期记忆】\nSTABLE").cache_control,
    undefined
  );
  assert.deepStrictEqual(systemBlock(withToolCache, "【近期记忆（最近）】\nRECENT").cache_control, {
    type: "ephemeral",
    ttl: "1h",
  });
  assert.strictEqual(
    withToolCache.system.filter((item) => item && item.cache_control).length,
    3
  );
  assert(withToolCache.tools[withToolCache.tools.length - 1].cache_control);

  const withToolCacheReal = await normalizeWithToolCache(true);
  assert.strictEqual(systemBlock(withToolCacheReal, REAL_PROMPT).cache_control, undefined);
  assert.deepStrictEqual(
    systemBlock(withToolCacheReal, "【近期记忆（最近）】\nRECENT").cache_control,
    {
      type: "ephemeral",
      ttl: "1h",
    }
  );

  const opus5Default = await opus5Thinking();
  assert.deepStrictEqual(opus5Default.thinking, {
    type: "adaptive",
    display: "summarized",
  });
  assert.deepStrictEqual(opus5Default.output_config, { effort: "high" });

  const opus5Max = await opus5Thinking("max");
  assert.deepStrictEqual(opus5Max.output_config, { effort: "max" });

  console.log("claude oauth proxy Real-mode cache checks passed");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
