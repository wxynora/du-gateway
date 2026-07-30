#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const { EventEmitter } = require("events");
const { StringDecoder } = require("string_decoder");

const ROOT = path.resolve(__dirname, "..");
const proxyPath = path.join(ROOT, "scripts", "claude_oauth_proxy.js");
const source = fs.readFileSync(proxyPath, "utf8");
const converterStart = source.indexOf("function createOpenaiStreamConverter");
const nativeHandlerStart = source.indexOf("// Anthropic 原生请求处理", converterStart);
assert(converterStart >= 0 && nativeHandlerStart > converterStart, "stream converter helpers are missing");

const logs = [];
const sandbox = {
  StringDecoder,
  convertUsage: () => ({}),
  log: (message) => logs.push(String(message)),
};
vm.createContext(sandbox);
vm.runInContext(
  `${source.slice(converterStart, nativeHandlerStart)}
   globalThis.__pipe = pipeAnthropicStreamToOpenAI;`,
  sandbox,
  { filename: proxyPath }
);

function fakeResponse() {
  const writes = [];
  return {
    writes,
    ended: false,
    write(chunk) {
      writes.push(String(chunk));
    },
    end() {
      this.ended = true;
    },
  };
}

const upstream = new EventEmitter();
const downstream = fakeResponse();
sandbox.__pipe(upstream, downstream, "claude-opus-5");
upstream.emit(
  "data",
  Buffer.from(
    'event: error\ndata: {"type":"error","error":{"type":"overloaded_error","message":"Overloaded"},"request_id":"req_test"}\n\n'
  )
);
upstream.emit("end");

assert.strictEqual(downstream.ended, true);
assert.strictEqual(downstream.writes.some((chunk) => chunk.includes('"error"')), true);
assert.strictEqual(downstream.writes.some((chunk) => chunk.includes("overloaded_error")), true);
assert.strictEqual(downstream.writes.some((chunk) => chunk.includes("req_test")), true);
assert.strictEqual(downstream.writes.some((chunk) => chunk.includes("[DONE]")), false);
assert.strictEqual(logs.some((line) => line.includes("overloaded_error") && line.includes("req_test")), true);

const successUpstream = new EventEmitter();
const successDownstream = fakeResponse();
sandbox.__pipe(successUpstream, successDownstream, "claude-opus-5");
successUpstream.emit(
  "data",
  Buffer.from(
    'data: {"type":"message_start","message":{"id":"msg_test","model":"claude-opus-5","usage":{}}}\n\n'
  )
);
successUpstream.emit(
  "data",
  Buffer.from(
    'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"正常回复"}}\n\n'
  )
);
successUpstream.emit("end");

assert.strictEqual(successDownstream.ended, true);
assert.strictEqual(successDownstream.writes.some((chunk) => chunk.includes("正常回复")), true);
assert.strictEqual(successDownstream.writes.some((chunk) => chunk.includes("[DONE]")), true);

console.log("Claude OAuth proxy stream error propagation checks passed");
