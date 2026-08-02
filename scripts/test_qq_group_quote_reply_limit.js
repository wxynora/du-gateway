#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BOT_ID = 3195570280;
const GROUP_ID = 778899;

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

async function waitUntil(predicate) {
  const deadline = Date.now() + 3000;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  throw new Error("timed out waiting for connector side effect");
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

function groupEvent({ messageId, mentionsSelf }) {
  const message = mentionsSelf
    ? [
        { type: "at", data: { qq: String(BOT_ID) } },
        { type: "text", data: { text: `第 ${messageId} 条` } },
      ]
    : [{ type: "text", data: { text: "普通群消息，重置连续计数" } }];
  return {
    post_type: "message",
    message_type: "group",
    group_id: GROUP_ID,
    user_id: 123456789,
    self_id: BOT_ID,
    message_id: messageId,
    message,
    raw_message: mentionsSelf
      ? `[CQ:at,qq=${BOT_ID}] 第 ${messageId} 条`
      : "普通群消息，重置连续计数",
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

function replySegmentIds(message) {
  if (!Array.isArray(message)) return [];
  return message
    .filter((part) => part?.type === "reply")
    .map((part) => String(part?.data?.id || ""));
}

async function testGroupQuoteAndMentionLimit() {
  let gatewayCalls = 0;
  const gatewayBodies = [];
  const groupSends = [];
  const fakeUpstreams = http.createServer((request, response) => {
    let raw = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => {
      raw += chunk;
    });
    request.on("end", () => {
      if (request.url === "/v1/chat/completions") {
        gatewayCalls += 1;
        gatewayBodies.push(JSON.parse(raw || "{}"));
        const replies = {
          1: "[QQ_REPLY:Q1]第一段\n第二段",
          2: "[QQ_REPLY:Q1]引用第一条",
          3: "[QQ_REPLY:Q999]无效编号应退化为普通回复",
          4: "[QQ_REPLY:Q2]引用第二条",
          5: "[QQ_REPLY:Q5]引用当前第五条",
        };
        const content = replies[gatewayCalls] || `收到 ${gatewayCalls}`;
        response.writeHead(200, { "Content-Type": "application/json" });
        response.end(JSON.stringify({ choices: [{ message: { content } }] }));
        return;
      }
      if (request.url === "/send_group_msg") {
        groupSends.push(JSON.parse(raw || "{}"));
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
      QQ_GROUP_ACTIVITY_REPORT_ENABLED: "0",
      QQ_GROUP_EVENT_LOG: "0",
      QQ_INBOUND_EVENT_LOG: "0",
      QQ_OUTPUT_SEND_DELAY_MS: "0",
      QQ_GROUP_MAX_CONSECUTIVE_MENTION_REPLIES: "5",
      TELEGRAM_PROACTIVE_TARGET_USER_ID: "8260066512",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  try {
    await waitForOutput(child, `[qq-onebot] listening on :${connectorPort}`);

    for (let messageId = 1001; messageId <= 1005; messageId += 1) {
      await postEvent(connectorPort, groupEvent({ messageId, mentionsSelf: true }));
      const expectedCalls = messageId - 1000;
      const expectedSends = expectedCalls + 1;
      await waitUntil(() => gatewayCalls >= expectedCalls && groupSends.length >= expectedSends);
    }
    await postEvent(connectorPort, groupEvent({ messageId: 1006, mentionsSelf: true }));
    await new Promise((resolve) => setTimeout(resolve, 100));
    assert.equal(gatewayCalls, 5, "the sixth consecutive @ must stop before the gateway/model");
    assert.equal(groupSends.length, 6, "five replies include two chunks for the first reply");

    const firstPrompt = String(gatewayBodies[0]?.messages?.[0]?.content || "");
    const fifthPrompt = String(gatewayBodies[4]?.messages?.[0]?.content || "");
    assert.match(firstPrompt, /\[Q1\].*第 1001 条/s, "the current message must receive a selectable quote ref");
    assert.match(
      fifthPrompt,
      /\[Q1\].*第 1001 条.*\[Q5\].*第 1005 条/s,
      "the model must receive stable refs for any visible message in this group turn"
    );
    assert.match(
      fifthPrompt,
      /\[QQ_REPLY:Q编号\]/,
      "the prompt must explain the model-controlled reply marker"
    );

    assert.deepEqual(replySegmentIds(groupSends[0].message), ["1001"]);
    assert.deepEqual(
      replySegmentIds(groupSends[1].message),
      [],
      "only the first chunk of one reply may quote the triggering message"
    );
    assert.deepEqual(replySegmentIds(groupSends[2].message), ["1001"], "Du may quote an earlier visible message");
    assert.deepEqual(replySegmentIds(groupSends[3].message), [], "an unknown ref must not quote any message");
    assert.doesNotMatch(
      String(groupSends[3].message),
      /QQ_REPLY/,
      "an invalid control marker must not leak into visible QQ text"
    );
    assert.deepEqual(replySegmentIds(groupSends[4].message), ["1002"], "Q2 must resolve to the second visible message");
    assert.deepEqual(replySegmentIds(groupSends[5].message), ["1005"], "Du may choose the current fifth message");

    await postEvent(connectorPort, groupEvent({ messageId: 2000, mentionsSelf: false }));
    await postEvent(connectorPort, groupEvent({ messageId: 2001, mentionsSelf: true }));
    await waitUntil(() => gatewayCalls >= 6);
    assert.equal(gatewayCalls, 6, "an ordinary non-@ group message must reset the consecutive limit");
    assert.deepEqual(
      replySegmentIds(groupSends.at(-1).message),
      [],
      "after reset, a model reply without a marker must remain an ordinary non-quoted reply"
    );

    await postEvent(connectorPort, groupEvent({ messageId: 2001, mentionsSelf: true }));
    await new Promise((resolve) => setTimeout(resolve, 100));
    assert.equal(gatewayCalls, 6, "duplicate webhook delivery must not consume another reply slot");
  } finally {
    child.kill("SIGTERM");
    await close(fakeUpstreams);
  }
}

await testGroupQuoteAndMentionLimit();
console.log("qq group quote reply and consecutive mention limit checks passed");
