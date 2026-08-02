#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(
  process.env.QQ_TEST_REPO_ROOT || path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
);

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

async function testAllOutboundMessagesShareOneRandomIntervalQueue() {
  const sendStartedAt = [];
  const onebot = http.createServer((request, response) => {
    let raw = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => {
      raw += chunk;
    });
    request.on("end", () => {
      if (request.url === "/send_private_msg") {
        JSON.parse(raw || "{}");
        sendStartedAt.push(Date.now());
        response.writeHead(200, { "Content-Type": "application/json" });
        response.end(JSON.stringify({ status: "ok", retcode: 0 }));
        return;
      }
      response.writeHead(404);
      response.end();
    });
  });
  const onebotPort = await listen(onebot);
  const connectorPort = await freePort();
  const child = spawn(process.execPath, ["connectors/qq_onebot/src/main.js"], {
    cwd: ROOT,
    env: {
      ...process.env,
      QQ_ONEBOT_API_BASE: `http://127.0.0.1:${onebotPort}`,
      QQ_ONEBOT_PORT: String(connectorPort),
      QQ_BOT_USER_ID: "3195570280",
      QQ_PROACTIVE_TARGET_USER_ID: "1336091712",
      QQ_OUTPUT_SEND_DELAY_MS: "0",
      QQ_OUTPUT_SEND_DELAY_MIN_MS: "40",
      QQ_OUTPUT_SEND_DELAY_MAX_MS: "80",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  try {
    await waitForOutput(child, `[qq-onebot] listening on :${connectorPort}`);
    const requests = Array.from({ length: 4 }, (_, index) =>
      fetch(`http://127.0.0.1:${connectorPort}/push`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: `并发消息 ${index + 1}`, single_message: true }),
      })
    );
    const responses = await Promise.all(requests);
    assert.deepEqual(responses.map((response) => response.status), [200, 200, 200, 200]);
    assert.equal(sendStartedAt.length, 4);

    const gaps = sendStartedAt.slice(1).map((time, index) => time - sendStartedAt[index]);
    for (const gap of gaps) {
      assert.ok(gap >= 35, `outbound calls must not overlap; observed gap=${gap}ms`);
      assert.ok(gap <= 160, `test interval should remain near the configured 40-80ms; observed gap=${gap}ms`);
    }
  } finally {
    child.kill("SIGTERM");
    await close(onebot);
  }
}

await testAllOutboundMessagesShareOneRandomIntervalQueue();
console.log("qq outbound random interval queue checks passed");
