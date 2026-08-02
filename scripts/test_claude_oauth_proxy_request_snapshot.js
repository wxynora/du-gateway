#!/usr/bin/env node

const assert = require("assert");
const fs = require("fs");
const Module = require("module");
const os = require("os");
const path = require("path");
const { EventEmitter } = require("events");
const { PassThrough } = require("stream");

const snapshotDir = fs.mkdtempSync(path.join(os.tmpdir(), "claude-request-snapshots-"));
process.env.CLAUDE_REQUEST_SNAPSHOT_DIR = snapshotDir;

const proxyPath = path.join(__dirname, "claude_oauth_proxy.js");
const source = fs.readFileSync(proxyPath, "utf8");
const listenIdx = source.lastIndexOf("server.listen(PORT, HOST");
assert(listenIdx > 0, "proxy server entrypoint not found");

const https = require("https");
const originalRequest = https.request;
const sentBodies = [];
https.request = (_options, callback) => {
  const request = new EventEmitter();
  request.write = (data) => sentBodies.push(String(data));
  request.end = () => {
    const response = new PassThrough();
    response.statusCode = 200;
    response.headers = {};
    callback(response);
    response.end();
  };
  return request;
};

const testModule = new Module(proxyPath, module);
testModule.filename = proxyPath;
testModule.paths = Module._nodeModulePaths(path.dirname(proxyPath));
testModule._compile(
  `${source.slice(0, listenIdx)}\nmodule.exports = { proxyToAnthropic };\n`,
  proxyPath
);

const { proxyToAnthropic } = testModule.exports;

(async () => {
  const payloads = [];
  for (let index = 0; index < 12; index += 1) {
    const payload = {
      model: "claude-opus-5",
      max_tokens: 128000,
      system: [
        {
          type: "text",
          text: `核心原文-${index}`,
          cache_control: { type: "ephemeral", ttl: "1h" },
        },
        {
          type: "text",
          text: `较稳定记忆-${index}`,
        },
        {
          type: "text",
          text: `最近记忆-${index}`,
          cache_control: { type: "ephemeral", ttl: "1h" },
        },
      ],
      messages: [
        {
          role: "user",
          content: [
            { type: "text", text: `完整用户正文-${index}` },
            {
              type: "image",
              source: {
                type: "base64",
                media_type: "image/png",
                data: `base64-${index}`,
              },
            },
          ],
        },
      ],
      tools: [
        {
          name: "完整工具",
          description: `完整工具说明-${index}`,
          input_schema: {
            type: "object",
            properties: {
              content: { type: "string" },
            },
          },
        },
      ],
    };
    payloads.push(payload);
    await proxyToAnthropic("oauth-secret-must-not-be-saved", "/v1/messages", payload);
  }

  const snapshotFiles = fs.readdirSync(snapshotDir).sort();
  assert.strictEqual(snapshotFiles.length, 10);
  for (const filename of snapshotFiles) {
    assert(filename.endsWith(".json"), filename);
    const mode = fs.statSync(path.join(snapshotDir, filename)).mode & 0o777;
    assert.strictEqual(mode, 0o600);
  }

  const savedBodies = snapshotFiles.map((filename) =>
    fs.readFileSync(path.join(snapshotDir, filename), "utf8")
  );
  assert.deepStrictEqual(savedBodies, sentBodies.slice(-10));
  assert.deepStrictEqual(
    savedBodies.map((body) => JSON.parse(body)),
    payloads.slice(-10)
  );
  assert(!savedBodies.join("\n").includes("oauth-secret-must-not-be-saved"));
  assert(!savedBodies.some((body) => body.endsWith("\n")));

  console.log("claude oauth proxy exact request snapshot checks passed");
})()
  .finally(() => {
    https.request = originalRequest;
    fs.rmSync(snapshotDir, { recursive: true, force: true });
  })
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
