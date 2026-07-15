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

async function normalize(realMode) {
  const body = await openaiToAnthropic(requestBody(realMode));
  processAnthropicBody(body);
  return body;
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
  console.log("claude oauth proxy Real-mode cache checks passed");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
