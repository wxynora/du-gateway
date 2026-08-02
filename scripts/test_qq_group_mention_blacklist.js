#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  DEFAULT_QQ_GROUP_MENTION_BLACKLIST,
  parseQqGroupMentionBlacklist,
  shouldIgnoreQqGroupMention,
} from "../connectors/qq_onebot/src/group_mention_blacklist.js";

const configured = parseQqGroupMentionBlacklist("");
assert.deepEqual(
  [...configured].sort(),
  [...DEFAULT_QQ_GROUP_MENTION_BLACKLIST].sort(),
  "empty configuration must use the requested default QQ blacklist"
);

for (const userId of ["3299553137", "190689686"]) {
  assert.equal(
    shouldIgnoreQqGroupMention({ user_id: userId }, true, configured),
    true,
    `blacklisted QQ ${userId} mentioning Du must be ignored`
  );
  assert.equal(
    shouldIgnoreQqGroupMention({ sender: { user_id: userId } }, true, configured),
    true,
    `sender.user_id fallback must enforce QQ ${userId}`
  );
  assert.equal(
    shouldIgnoreQqGroupMention({ user_id: userId }, false, configured),
    false,
    `ordinary non-mention group messages from QQ ${userId} must keep existing behavior`
  );
}

assert.equal(
  shouldIgnoreQqGroupMention({ user_id: "123456789" }, true, configured),
  false,
  "other members mentioning Du must keep existing behavior"
);

assert.deepEqual(
  [...parseQqGroupMentionBlacklist(" 111,222  333\ninvalid ")],
  ["111", "222", "333"],
  "optional environment override must accept comma or whitespace separated QQ IDs"
);

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BOT_ID = 3195570280;

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => resolve(server.address().port));
  });
}

function close(server) {
  return new Promise((resolve) => server.close(resolve));
}

async function freePort() {
  const server = http.createServer();
  const port = await listen(server);
  await close(server);
  return port;
}

function waitForOutput(child, needle) {
  return new Promise((resolve, reject) => {
    let output = "";
    const timeout = setTimeout(() => reject(new Error(`connector start timeout: ${output}`)), 5000);
    const onData = (chunk) => {
      output += String(chunk || "");
      if (!output.includes(needle)) return;
      clearTimeout(timeout);
      child.stdout.off("data", onData);
      child.stderr.off("data", onData);
      resolve();
    };
    child.stdout.on("data", onData);
    child.stderr.on("data", onData);
    child.once("exit", (code) => {
      clearTimeout(timeout);
      reject(new Error(`connector exited before ready code=${code}: ${output}`));
    });
  });
}

async function waitUntil(predicate) {
  const deadline = Date.now() + 3000;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error("timed out waiting for connector side effect");
}

function groupMentionEvent(userId, messageId) {
  return {
    post_type: "message",
    message_type: "group",
    group_id: 778899,
    user_id: Number(userId),
    self_id: BOT_ID,
    message_id: messageId,
    message: [
      { type: "at", data: { qq: String(BOT_ID) } },
      { type: "text", data: { text: "在吗" } },
    ],
    raw_message: `[CQ:at,qq=${BOT_ID}] 在吗`,
  };
}

async function postEvent(port, event) {
  const response = await fetch(`http://127.0.0.1:${port}/onebot/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(event),
  });
  assert.equal(response.status, 200);
}

async function testRealInboundBoundary() {
  let gatewayCalls = 0;
  let groupSendCalls = 0;
  const fakeUpstreams = http.createServer((request, response) => {
    if (request.url === "/v1/chat/completions") {
      gatewayCalls += 1;
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ choices: [{ message: { content: "收到" } }] }));
      return;
    }
    if (request.url === "/send_group_msg") {
      groupSendCalls += 1;
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ status: "ok", retcode: 0 }));
      return;
    }
    if (request.url === "/miniapp-api/stickers/tags-public") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ tags: [] }));
      return;
    }
    response.writeHead(404);
    response.end();
  });
  const upstreamPort = await listen(fakeUpstreams);
  const connectorPort = await freePort();
  const child = spawn(process.execPath, ["connectors/qq_onebot/src/main.js"], {
    cwd: ROOT,
    env: {
      ...process.env,
      GATEWAY_BASE_URL: `http://127.0.0.1:${upstreamPort}`,
      QQ_ONEBOT_API_BASE: `http://127.0.0.1:${upstreamPort}`,
      QQ_ONEBOT_PORT: String(connectorPort),
      QQ_BOT_USER_ID: String(BOT_ID),
      QQ_GROUP_MENTION_BLACKLIST: "3299553137,190689686",
      QQ_GROUP_ACTIVITY_REPORT_ENABLED: "0",
      QQ_GROUP_EVENT_LOG: "0",
      QQ_INBOUND_EVENT_LOG: "0",
      TELEGRAM_PROACTIVE_TARGET_USER_ID: "8260066512",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  try {
    await waitForOutput(child, `[qq-onebot] listening on :${connectorPort}`);
    await postEvent(connectorPort, groupMentionEvent("3299553137", "blocked-1"));
    await new Promise((resolve) => setTimeout(resolve, 100));
    assert.equal(gatewayCalls, 0, "blacklisted @ must return before the gateway/model");
    assert.equal(groupSendCalls, 0, "blacklisted @ must not send a group reply");

    await postEvent(connectorPort, groupMentionEvent("123456789", "allowed-1"));
    await waitUntil(() => gatewayCalls === 1 && groupSendCalls === 1);
  } finally {
    child.kill("SIGTERM");
    await close(fakeUpstreams);
  }
}

await testRealInboundBoundary();

console.log("qq group mention blacklist checks passed");
