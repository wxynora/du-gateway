#!/usr/bin/env node

const assert = require("assert");
const fs = require("fs");
const http = require("http");
const net = require("net");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const PROXY_PATH = path.join(__dirname, "claude_oauth_proxy.js");

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

function requestJson(port, requestPath, headers = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        host: "127.0.0.1",
        port,
        path: requestPath,
        method: "GET",
        headers,
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          try {
            resolve({ statusCode: res.statusCode || 0, body: JSON.parse(text) });
          } catch (error) {
            reject(new Error(`invalid JSON response ${res.statusCode}: ${text || error.message}`));
          }
        });
      }
    );
    req.once("error", reject);
    req.end();
  });
}

function startProxy({ port, oauthFile, snapshotFile, preloadFile }) {
  return new Promise((resolve, reject) => {
    const env = {
      ...process.env,
      HOST: "127.0.0.1",
      PORT: String(port),
      PROXY_KEY: "test-proxy-key",
      CLAUDE_OAUTH_SYNC_KEY: "test-sync-key",
      CLAUDE_OAUTH_FILE: oauthFile,
      CLAUDE_RATE_LIMIT_SNAPSHOT_FILE: snapshotFile,
    };
    if (preloadFile) {
      env.NODE_OPTIONS = `--require=${preloadFile}`;
    } else {
      delete env.NODE_OPTIONS;
    }
    const child = spawn(process.execPath, [PROXY_PATH], {
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error(`proxy start timeout stdout=${stdout} stderr=${stderr}`));
    }, 5000);
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
      if (stdout.includes("Claude OAuth Proxy running")) {
        clearTimeout(timeout);
        resolve(child);
      }
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    child.once("exit", (code, signal) => {
      clearTimeout(timeout);
      if (!stdout.includes("Claude OAuth Proxy running")) {
        reject(new Error(`proxy exited before ready code=${code} signal=${signal} stderr=${stderr}`));
      }
    });
  });
}

function stopProxy(child) {
  if (!child || child.exitCode !== null) return Promise.resolve();
  return new Promise((resolve) => {
    const timeout = setTimeout(() => child.kill("SIGKILL"), 2000);
    child.once("exit", () => {
      clearTimeout(timeout);
      resolve();
    });
    child.kill("SIGTERM");
  });
}

function waitForFile(filePath) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + 3000;
    const poll = () => {
      if (fs.existsSync(filePath)) return resolve();
      if (Date.now() >= deadline) {
        return reject(new Error(`snapshot file was not created: ${filePath}`));
      }
      setTimeout(poll, 25);
    };
    poll();
  });
}

async function main() {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "claude-rate-limit-persistence-"));
  const oauthFile = path.join(tempDir, "oauth.json");
  const snapshotFile = path.join(tempDir, "rate-limit.json");
  const preloadFile = path.join(tempDir, "mock-https.js");
  const port = await freePort();
  let child = null;
  try {
    fs.writeFileSync(
      oauthFile,
      JSON.stringify({
        claudeAiOauth: {
          accessToken: "fake-access-token",
          refreshToken: "fake-refresh-token",
          expiresAt: Date.now() + 60 * 60 * 1000,
        },
      })
    );
    fs.writeFileSync(
      preloadFile,
      `
const https = require("https");
const { EventEmitter } = require("events");
const { Readable } = require("stream");
https.request = function mockRequest(_options, callback) {
  const request = new EventEmitter();
  request.write = function write() {};
  request.end = function end() {
    process.nextTick(() => {
      const response = Readable.from([JSON.stringify({ data: [{ id: "claude-opus-5" }] })]);
      response.statusCode = 200;
      response.headers = {
        "content-type": "application/json",
        "anthropic-ratelimit-unified-status": "allowed",
        "anthropic-ratelimit-unified-reset": "1785163800",
        "anthropic-ratelimit-unified-representative-claim": "five_hour",
        "anthropic-ratelimit-unified-fallback-percentage": "0.5",
        "anthropic-ratelimit-unified-overage-status": "allowed",
        "anthropic-ratelimit-unified-5h-status": "allowed",
        "anthropic-ratelimit-unified-5h-reset": "1785163800",
        "anthropic-ratelimit-unified-5h-utilization": "0.05",
        "anthropic-ratelimit-unified-7d-status": "allowed",
        "anthropic-ratelimit-unified-7d-reset": "1785607200",
        "anthropic-ratelimit-unified-7d-utilization": "0.22",
      };
      callback(response);
    });
  };
  return request;
};
`
    );

    child = await startProxy({ port, oauthFile, snapshotFile, preloadFile });
    const models = await requestJson(port, "/v1/models", {
      Authorization: "Bearer test-proxy-key",
    });
    assert.strictEqual(models.statusCode, 200);
    await waitForFile(snapshotFile);
    const persisted = JSON.parse(fs.readFileSync(snapshotFile, "utf8"));
    assert.strictEqual(persisted.status, "allowed");
    assert.strictEqual(persisted.statusCode, 200);
    assert.strictEqual(persisted.fiveHour.utilization, 0.05);
    assert.strictEqual(persisted.sevenDay.utilization, 0.22);
    assert.strictEqual(Object.hasOwn(persisted, "route"), false);
    assert.strictEqual(Object.hasOwn(persisted, "accessToken"), false);
    assert.strictEqual(fs.statSync(snapshotFile).mode & 0o777, 0o600);
    await stopProxy(child);
    child = null;

    child = await startProxy({ port, oauthFile, snapshotFile });
    const status = await requestJson(port, "/internal/oauth-status", {
      "X-OAuth-Sync-Key": "test-sync-key",
    });
    assert.strictEqual(status.statusCode, 200);
    assert.strictEqual(status.body.rateLimitSnapshot.fiveHour.utilization, 0.05);
    assert.strictEqual(status.body.rateLimitSnapshot.sevenDay.utilization, 0.22);
    assert.strictEqual(status.body.rateLimitSnapshot.updatedAt, persisted.updatedAt);
    console.log("PASS rate-limit snapshot survives proxy restart");
  } finally {
    await stopProxy(child);
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
