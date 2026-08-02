#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const proxyPath = path.join(ROOT, "scripts", "claude_oauth_proxy.js");
const source = fs.readFileSync(proxyPath, "utf8");
const reducerStart = source.indexOf("function reduceAnthropicTextContent");
const streamConverterStart = source.indexOf("function createOpenaiStreamConverter", reducerStart);
if (reducerStart < 0 || streamConverterStart < 0) {
  throw new Error("proxy final/snapshot reducer is missing");
}

const sandbox = {
  convertUsage: () => ({}),
  createOpenaiStreamConverter: () => {
    throw new Error("stream converter must not run in non-stream test");
  },
};
vm.createContext(sandbox);
vm.runInContext(
  `${source.slice(reducerStart, streamConverterStart)}
   globalThis.__anthropicToOpenai = anthropicToOpenai;`,
  sandbox,
  { filename: proxyPath }
);

const convert = sandbox.__anthropicToOpenai;

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: expected=${JSON.stringify(expected)} actual=${JSON.stringify(actual)}`);
  }
}

function convertedText(content) {
  const response = convert(
    {
      id: "msg_snapshot_test",
      model: "claude-opus-5",
      content,
      stop_reason: "end_turn",
      usage: {},
    },
    "claude-opus-5",
    false
  );
  return response.choices[0].message.content;
}

assertEqual(
  convertedText([
    { type: "text", mode: "delta", text: "初稿第一段。" },
    { type: "text", mode: "delta", text: "初稿第二段。" },
    { type: "text", mode: "final", text: "终稿只有这一版。" },
  ]),
  "终稿只有这一版。",
  "final must replace accumulated deltas"
);

assertEqual(
  convertedText([
    { type: "text", mode: "delta", text: "我先写了一个版本，句尾是冷的。" },
    { type: "text", mode: "snapshot", text: "我后来改成终稿，句尾是暖的。" },
  ]),
  "我后来改成终稿，句尾是暖的。",
  "snapshot with small rewrites must replace the draft"
);

assertEqual(
  convertedText([
    { type: "text", text: "普通主动消息第一块。" },
    { type: "text", text: "普通主动消息第二块。" },
  ]),
  "普通主动消息第一块。普通主动消息第二块。",
  "unmarked standard Anthropic text blocks must keep their original concatenation"
);

assertEqual(
  convertedText([
    { type: "text", mode: "delta", text: "旧内容。" },
    { type: "text", mode: "final", text: "完整终稿。" },
    { type: "text", mode: "delta", text: "终稿后的协议增量。" },
  ]),
  "完整终稿。终稿后的协议增量。",
  "deltas after a final snapshot must append to the current final text"
);

console.log("Claude OAuth final snapshot aggregation checks passed");
