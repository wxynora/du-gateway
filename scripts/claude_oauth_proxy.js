#!/usr/bin/env node

const http = require("http");
const https = require("https");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { StringDecoder } = require("string_decoder");
const { execFileSync, spawn } = require("child_process");
const { Readable } = require("stream");

const PORT = parseInt(process.env.PORT || "8082");
const HOST = process.env.HOST || "127.0.0.1";
const PROXY_KEY = process.env.PROXY_KEY;
const OAUTH_SYNC_KEY = process.env.CLAUDE_OAUTH_SYNC_KEY || PROXY_KEY;
const DEFAULT_MAX_TOKENS = parseInt(process.env.CLAUDE_MAX_TOKENS || "33000", 10);
const THINKING_BUDGET_TOKENS = parseInt(
  process.env.CLAUDE_THINKING_BUDGET_TOKENS || "32000",
  10
);
const CLAUDE_ADAPTIVE_THINKING_EFFORT = String(
  process.env.CLAUDE_ADAPTIVE_THINKING_EFFORT || "high"
).trim().toLowerCase();
const CLAUDE_ADAPTIVE_THINKING_EFFORTS = new Set(["low", "medium", "high", "xhigh", "max"]);
const CLAUDE_OAUTH_FILE = process.env.CLAUDE_OAUTH_FILE || "";
const CLAUDE_OAUTH_JSON = process.env.CLAUDE_OAUTH_JSON || "";
const CLAUDE_OAUTH_KEYCHAIN_SERVICE =
  process.env.CLAUDE_OAUTH_KEYCHAIN_SERVICE || "Claude Code-credentials";
const CLAUDE_OAUTH_TOKEN_URL =
  process.env.CLAUDE_OAUTH_TOKEN_URL || "https://platform.claude.com/v1/oauth/token";
const CLAUDE_OAUTH_CLIENT_ID =
  process.env.CLAUDE_OAUTH_CLIENT_ID || "9d1c250a-e61b-44d9-88ed-5944d1962f5e";
const CLAUDE_OAUTH_REFRESH_PYTHON =
  process.env.CLAUDE_OAUTH_REFRESH_PYTHON || selectPythonWithRequests();
const CLAUDE_OAUTH_REFRESH_TIMEOUT_SECONDS = Math.max(
  1,
  parseInt(process.env.CLAUDE_OAUTH_REFRESH_TIMEOUT_SECONDS || "10", 10)
);
const CLAUDE_OAUTH_REFRESH_MAX_ATTEMPTS = Math.max(
  1,
  parseInt(process.env.CLAUDE_OAUTH_REFRESH_MAX_ATTEMPTS || "3", 10)
);
const CLAUDE_OAUTH_REFRESH_PROCESS_TIMEOUT_MS = Math.max(
  5000,
  parseInt(process.env.CLAUDE_OAUTH_REFRESH_PROCESS_TIMEOUT_MS || "45000", 10)
);
const REFRESH_SKEW_MS = Math.max(
  60,
  parseInt(process.env.CLAUDE_REFRESH_SKEW_SECONDS || "60", 10)
) * 1000;
const CLAUDE_PROMPT_CACHE_TTL = String(process.env.CLAUDE_PROMPT_CACHE_TTL || "1h").trim();
const TARGET_HOST = "api.anthropic.com";
const ANTHROPIC_VERSION = "2023-06-01";
const CLAUDE_CODE_VERSION = String(process.env.CLAUDE_CODE_VERSION || "2.1.195").trim();
const CLAUDE_CODE_BILLING_SALT = String(
  process.env.CLAUDE_CODE_BILLING_SALT || "59cf53e54c78"
).trim();
const CLAUDE_CODE_ENTRYPOINT = String(process.env.CLAUDE_CODE_ENTRYPOINT || "cli").trim();
const CLAUDE_CODE_CCH = String(process.env.CLAUDE_CODE_CCH || "00000").trim();
const BILLING_HEADER_PREFIX = "x-anthropic-billing-header:";
const BETA_HEADER = [
  "oauth-2025-04-20",
  "claude-code-20250219",
  "interleaved-thinking-2025-05-14",
  "prompt-caching-scope-2026-01-05",
  "context-management-2025-06-27",
].join(",");
const DYNAMIC_SYSTEM_MARKER = "__dynamic__";
const SUMMARY_CACHE_SYSTEM_MARKER = "__summary_cache__";
const SUMMARY_RECENT_SYSTEM_MARKER = "__summary_recent__";
const SUMITALK_REAL_MODE_SYSTEM_MARKER = "__sumitalk_real_mode__";
const GATEWAY_DYNAMIC_SYSTEM_HINTS = [
  "【渡的心事",
  "【渡的日常",
  "今日：",
  "听了老婆的话，我想起来",
  "【指代提醒】",
  "老婆当前状态",
  "【当前是在 RikkaHub 和渡聊天】",
  "【Notion 相关】",
];

const MODEL_MAP = {
  "gpt-4o": "claude-sonnet-4-6",
  "gpt-4o-mini": "claude-haiku-4-5-20251001",
  "gpt-4-turbo": "claude-sonnet-4-6",
  "gpt-4": "claude-sonnet-4-6",
  "gpt-3.5-turbo": "claude-haiku-4-5-20251001",
};
const IMAGE_DOWNLOAD_MAX_BYTES = parseInt(process.env.CLAUDE_IMAGE_MAX_BYTES || "10485760", 10);
const SUPPORTED_IMAGE_MIME_TYPES = new Set(["image/jpeg", "image/png", "image/gif", "image/webp"]);

let cachedOAuth = null;
let cachedOAuthRaw = null;
let cachedOAuthSource = "";
let lastUnauthorizedAt = 0;
let lastUnauthorizedRoute = "";
let lastRateLimitSnapshot = null;
let refreshInFlight = null;

function log(msg) {
  console.log(`[${new Date().toLocaleTimeString()}] ${msg}`);
}

function pythonHasRequests(candidate) {
  try {
    execFileSync(candidate, ["-c", "import requests"], { stdio: "ignore", timeout: 3000 });
    return true;
  } catch {
    return false;
  }
}

function selectPythonWithRequests() {
  const candidates = [
    process.env.VIRTUAL_ENV ? path.join(process.env.VIRTUAL_ENV, "bin/python") : "",
    path.join(process.cwd(), ".venv/bin/python"),
    path.join(__dirname, "..", ".venv", "bin", "python"),
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "/usr/bin/python3",
    "python3",
  ];
  const seen = new Set();
  for (const candidate of candidates) {
    if (!candidate || seen.has(candidate)) continue;
    seen.add(candidate);
    if (candidate.includes("/") && !fs.existsSync(candidate)) continue;
    if (pythonHasRequests(candidate)) return candidate;
  }
  return "python3";
}

function readKeychainOAuth() {
  const raw = execFileSync(
    "security",
    ["find-generic-password", "-s", CLAUDE_OAUTH_KEYCHAIN_SERVICE, "-w"],
    { encoding: "utf8" }
  ).trim();
  return JSON.parse(raw);
}

function parseExpiresAt(value) {
  if (!value) return 0;
  if (typeof value === "number") return value < 1e12 ? value * 1000 : value;
  if (/^\d+$/.test(String(value))) {
    const n = Number(value);
    return n < 1e12 ? n * 1000 : n;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? Date.now() + 30 * 60 * 1000 : parsed;
}

function normalizeOAuth(raw) {
  const obj = typeof raw === "string" ? JSON.parse(raw) : raw;
  const src =
    obj.claudeAiOauth ||
    obj.oauth ||
    obj.metadata ||
    obj.tokens ||
    obj;
  const accessToken = src.accessToken || src.access_token || src.access || "";
  const refreshToken = src.refreshToken || src.refresh_token || src.refresh || "";
  if (!accessToken && !refreshToken) {
    throw new Error("OAuth credentials must include accessToken/access_token or refreshToken/refresh_token");
  }
  return {
    accessToken,
    refreshToken,
    expiresAt: parseExpiresAt(src.expiresAt || src.expires_at || src.expiry || src.expires || src.expired),
  };
}

function cloneJson(value) {
  if (!value || typeof value !== "object") return {};
  return JSON.parse(JSON.stringify(value));
}

function oauthCredentialContainer(raw) {
  const root = raw && typeof raw === "object" ? raw : {};
  for (const key of ["claudeAiOauth", "oauth", "metadata", "tokens"]) {
    if (root[key] && typeof root[key] === "object" && !Array.isArray(root[key])) {
      return root[key];
    }
  }
  return root;
}

function buildRefreshedOAuthRaw(refreshed) {
  const root = cloneJson(cachedOAuthRaw);
  const target = oauthCredentialContainer(root);
  const expiresAtMs = refreshed.expiresAt;
  target.accessToken = refreshed.accessToken;
  target.refreshToken = refreshed.refreshToken;
  target.expiresAt = expiresAtMs;
  if ("access_token" in target) target.access_token = refreshed.accessToken;
  if ("refresh_token" in target) target.refresh_token = refreshed.refreshToken;
  if ("access" in target) target.access = refreshed.accessToken;
  if ("refresh" in target) target.refresh = refreshed.refreshToken;
  if ("expires_at" in target) target.expires_at = Math.floor(expiresAtMs / 1000);
  if ("expiry" in target) target.expiry = expiresAtMs;
  if ("expires" in target) target.expires = expiresAtMs;
  return root && Object.keys(root).length ? root : {
    accessToken: refreshed.accessToken,
    refreshToken: refreshed.refreshToken,
    expiresAt: expiresAtMs,
  };
}

function loadOAuthCredentials(reason) {
  cachedOAuth = readOAuthCredentials();
  log(
    `Token ${reason || "loaded"} from ${cachedOAuthSource || "unknown"} (expires ${new Date(
      cachedOAuth.expiresAt
    ).toLocaleString()})`
  );
  return cachedOAuth;
}

function readOAuthCredentials() {
  if (CLAUDE_OAUTH_JSON) {
    cachedOAuthSource = "env";
    cachedOAuthRaw = JSON.parse(CLAUDE_OAUTH_JSON);
    return normalizeOAuth(cachedOAuthRaw);
  }
  if (CLAUDE_OAUTH_FILE) {
    cachedOAuthSource = "file";
    cachedOAuthRaw = JSON.parse(fs.readFileSync(CLAUDE_OAUTH_FILE, "utf8"));
    return normalizeOAuth(cachedOAuthRaw);
  }
  cachedOAuthSource = "keychain";
  cachedOAuthRaw = readKeychainOAuth();
  return normalizeOAuth(cachedOAuthRaw);
}

function writeSyncedOAuthCredentials(raw) {
  if (!CLAUDE_OAUTH_FILE) {
    throw new Error("CLAUDE_OAUTH_FILE is required for OAuth sync");
  }
  const normalized = normalizeOAuth(raw);
  if (!normalized.refreshToken && (!normalized.expiresAt || normalized.expiresAt <= Date.now())) {
    throw new Error("Synced OAuth token is already expired");
  }
  fs.mkdirSync(path.dirname(CLAUDE_OAUTH_FILE), { recursive: true, mode: 0o700 });
  const tmp = `${CLAUDE_OAUTH_FILE}.tmp-${process.pid}-${Date.now()}`;
  fs.writeFileSync(tmp, JSON.stringify(raw, null, 2) + "\n", { mode: 0o600 });
  fs.renameSync(tmp, CLAUDE_OAUTH_FILE);
  cachedOAuthRaw = raw;
  cachedOAuth = normalized;
  cachedOAuthSource = "file";
  return normalized;
}

function refreshOAuthWithPython(refreshToken) {
  return new Promise((resolve, reject) => {
    const script = `
import json
import sys
import time

try:
    import requests
except Exception as exc:
    print(json.dumps({"error": "missing_requests", "message": str(exc)}), file=sys.stderr)
    sys.exit(21)

payload = json.loads(sys.stdin.read() or "{}")
token_url = payload["token_url"]
client_id = payload["client_id"]
refresh_token = payload["refresh_token"]
timeout_s = int(payload.get("timeout_s") or 10)
max_attempts = int(payload.get("max_attempts") or 3)

last_error = None
for attempt in range(max_attempts):
    if attempt > 0:
        time.sleep(2 ** (attempt - 1))
    try:
        resp = requests.post(
            token_url,
            json={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=timeout_s,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(json.dumps({
                "accessToken": data["access_token"],
                "refreshToken": data["refresh_token"],
                "expiresAt": int((time.time() + int(data["expires_in"]) - 300) * 1000),
            }))
            sys.exit(0)
        if 500 <= resp.status_code < 600:
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            continue
        print(json.dumps({
            "error": "permanent_refresh_failure",
            "status": resp.status_code,
            "body": resp.text[:500],
        }), file=sys.stderr)
        sys.exit(20)
    except (requests.Timeout, requests.ConnectionError) as exc:
        last_error = f"{type(exc).__name__}: {exc}"
        continue
    except Exception as exc:
        print(json.dumps({"error": "unexpected_refresh_error", "message": str(exc)}), file=sys.stderr)
        sys.exit(21)

print(json.dumps({"error": "refresh_gave_up", "last": last_error}), file=sys.stderr)
sys.exit(22)
`.trim();

    const child = spawn(CLAUDE_OAUTH_REFRESH_PYTHON, ["-c", script], {
      stdio: ["pipe", "pipe", "pipe"],
      env: process.env,
    });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error("OAuth refresh helper timed out"));
    }, CLAUDE_OAUTH_REFRESH_PROCESS_TIMEOUT_MS);
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        const details = stderr.trim() || stdout.trim() || `exit ${code}`;
        reject(new Error(`OAuth refresh failed: ${details.slice(0, 700)}`));
        return;
      }
      try {
        const parsed = JSON.parse(stdout.trim());
        if (!parsed.accessToken || !parsed.refreshToken || !parsed.expiresAt) {
          throw new Error("refresh response missing token fields");
        }
        resolve(parsed);
      } catch (e) {
        reject(new Error(`OAuth refresh helper returned invalid JSON: ${e.message}`));
      }
    });
    child.stdin.end(
      JSON.stringify({
        token_url: CLAUDE_OAUTH_TOKEN_URL,
        client_id: CLAUDE_OAUTH_CLIENT_ID,
        refresh_token: refreshToken,
        timeout_s: CLAUDE_OAUTH_REFRESH_TIMEOUT_SECONDS,
        max_attempts: CLAUDE_OAUTH_REFRESH_MAX_ATTEMPTS,
      })
    );
  });
}

async function refreshOAuthCredentials(reason) {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    if (!cachedOAuth) {
      loadOAuthCredentials();
    }
    const refreshToken = cachedOAuth.refreshToken;
    if (!refreshToken) {
      throw new Error("Claude OAuth refresh token is missing");
    }
    log(`Refreshing Claude OAuth token via gist-compatible requests client (${reason || "token refresh"})`);
    const refreshed = await refreshOAuthWithPython(refreshToken);
    const raw = buildRefreshedOAuthRaw(refreshed);
    if (CLAUDE_OAUTH_FILE) {
      writeSyncedOAuthCredentials(raw);
    } else {
      cachedOAuthRaw = raw;
      cachedOAuth = normalizeOAuth(raw);
      cachedOAuthSource = cachedOAuthSource || "memory";
    }
    log(`OAuth refreshed by proxy (expires ${new Date(cachedOAuth.expiresAt).toLocaleString()})`);
    return cachedOAuth;
  })().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

function oauthExpiresInSeconds() {
  if (!cachedOAuth?.expiresAt) return 0;
  return Math.floor((cachedOAuth.expiresAt - Date.now()) / 1000);
}

async function getAccessToken(routeLabel = "forwarded request") {
  if (!cachedOAuth) {
    loadOAuthCredentials();
  }
  const expiresInSeconds = oauthExpiresInSeconds();
  if (expiresInSeconds <= Math.ceil(REFRESH_SKEW_MS / 1000)) {
    log(
      `Holding ${routeLabel} until OAuth refresh completes (expires in ${expiresInSeconds}s)`
    );
    await refreshOAuthCredentials(`${routeLabel} near expiry`);
  }
  return cachedOAuth.accessToken;
}

function readBody(req) {
  return new Promise((resolve) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks)));
  });
}

function requestSecret(req) {
  const auth = String(req.headers.authorization || "").trim();
  const bearer = auth.toLowerCase().startsWith("bearer ") ? auth.slice(7).trim() : "";
  return String(req.headers["x-oauth-sync-key"] || req.headers["x-sync-key"] || req.headers["x-api-key"] || bearer || "");
}

function secretMatches(actual, expected) {
  if (!actual || !expected) return false;
  const a = Buffer.from(String(actual));
  const b = Buffer.from(String(expected));
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

async function readStreamText(stream) {
  const chunks = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString("utf8");
}

function stripTtlFromCacheControl(obj) {
  if (!obj || typeof obj !== "object") return;
  const process = (arr) => {
    if (!Array.isArray(arr)) return;
    for (const item of arr) {
      if (item?.cache_control?.ttl !== undefined) delete item.cache_control.ttl;
    }
  };
  if (Array.isArray(obj.system)) process(obj.system);
  if (Array.isArray(obj.messages)) {
    for (const msg of obj.messages) {
      if (Array.isArray(msg.content)) process(msg.content);
    }
  }
}

function sampledJsUtf16(text, indices) {
  const value = String(text || "");
  return indices.map((idx) => (idx < value.length ? value.charAt(idx) : "0")).join("");
}

function billingHash(firstText) {
  const sampled = sampledJsUtf16(String(firstText || "").slice(0, 50), [4, 7, 20]);
  return crypto
    .createHash("sha256")
    .update(`${CLAUDE_CODE_BILLING_SALT}${sampled}${CLAUDE_CODE_VERSION}`)
    .digest("hex")
    .slice(0, 3);
}

function claudeBillingSystemBlock(firstText) {
  const sampleText = firstText || "";
  const h = billingHash(sampleText);
  return {
    type: "text",
    text: `${BILLING_HEADER_PREFIX} cc_version=${CLAUDE_CODE_VERSION}.${h}; cc_entrypoint=${CLAUDE_CODE_ENTRYPOINT}; cch=${CLAUDE_CODE_CCH};`,
  };
}

function isClaudeBillingSystemBlock(item) {
  return String(item?.text || "").trimStart().startsWith(BILLING_HEADER_PREFIX);
}

function safeJsonParse(value, fallback = {}) {
  if (value && typeof value === "object") return value;
  if (typeof value !== "string" || value.trim() === "") return fallback;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function contentToText(content) {
  if (content === null || content === undefined) return "";
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part;
        if (part?.type === "text" || part?.type === "input_text") return part.text || "";
        return "";
      })
      .filter(Boolean)
      .join("\n");
  }
  return String(content);
}

function inferImageMimeType(url, contentType) {
  const cleanType = String(contentType || "").split(";")[0].trim().toLowerCase();
  if (SUPPORTED_IMAGE_MIME_TYPES.has(cleanType)) return cleanType;
  const path = (() => {
    try {
      return new URL(url).pathname.toLowerCase();
    } catch {
      return String(url || "").toLowerCase();
    }
  })();
  if (path.endsWith(".jpg") || path.endsWith(".jpeg")) return "image/jpeg";
  if (path.endsWith(".png")) return "image/png";
  if (path.endsWith(".gif")) return "image/gif";
  if (path.endsWith(".webp")) return "image/webp";
  return "";
}

function downloadImageUrl(rawUrl, redirectCount = 0) {
  return new Promise((resolve, reject) => {
    if (redirectCount > 5) {
      reject(new Error("too many redirects"));
      return;
    }

    let url;
    try {
      url = new URL(rawUrl);
    } catch {
      reject(new Error("invalid image URL"));
      return;
    }
    if (!["http:", "https:"].includes(url.protocol)) {
      reject(new Error(`unsupported image URL protocol: ${url.protocol}`));
      return;
    }

    const client = url.protocol === "http:" ? http : https;
    const req = client.request(
      {
        hostname: url.hostname,
        port: url.port || (url.protocol === "http:" ? 80 : 443),
        path: `${url.pathname}${url.search}`,
        method: "GET",
        headers: {
          Accept: "image/*,*/*;q=0.8",
          "User-Agent": "claude-oauth-proxy/1.0",
        },
      },
      (res) => {
        const status = res.statusCode || 0;
        if (status >= 300 && status < 400 && res.headers.location) {
          res.resume();
          const nextUrl = new URL(res.headers.location, url).toString();
          downloadImageUrl(nextUrl, redirectCount + 1).then(resolve, reject);
          return;
        }
        if (status < 200 || status >= 300) {
          res.resume();
          reject(new Error(`image download HTTP ${status}`));
          return;
        }

        const mediaType = inferImageMimeType(url.toString(), res.headers["content-type"]);
        if (!mediaType) {
          res.resume();
          reject(new Error(`unsupported image content-type: ${res.headers["content-type"] || "unknown"}`));
          return;
        }

        const chunks = [];
        let size = 0;
        res.on("data", (chunk) => {
          size += chunk.length;
          if (size > IMAGE_DOWNLOAD_MAX_BYTES) {
            req.destroy(new Error(`image too large: ${size} bytes`));
            return;
          }
          chunks.push(chunk);
        });
        res.on("end", () => {
          resolve({
            media_type: mediaType,
            data: Buffer.concat(chunks).toString("base64"),
          });
        });
      }
    );
    req.setTimeout(30000, () => req.destroy(new Error("image download timeout")));
    req.on("error", reject);
    req.end();
  });
}

async function openaiContentToAnthropic(content) {
  if (content === null || content === undefined) return [];
  if (typeof content === "string") {
    return content ? [{ type: "text", text: content }] : [];
  }
  if (!Array.isArray(content)) {
    return [{ type: "text", text: String(content) }];
  }

  const out = [];
  for (const part of content) {
    if (typeof part === "string") {
      if (part) out.push({ type: "text", text: part });
      continue;
    }
    if (part?.type === "text" || part?.type === "input_text") {
      if (part.text) out.push({ type: "text", text: part.text });
      continue;
    }
    if (part?.type === "image_url") {
      const url = part.image_url?.url || part.url || "";
      const match = url.match(/^data:(image\/[^;]+);base64,(.+)$/);
      if (match) {
        out.push({
          type: "image",
          source: { type: "base64", media_type: match[1], data: match[2] },
        });
      } else if (url) {
        const image = await downloadImageUrl(url);
        out.push({
          type: "image",
          source: { type: "base64", media_type: image.media_type, data: image.data },
        });
      }
    }
  }
  return out;
}

function convertOpenaiTools(tools) {
  if (!Array.isArray(tools)) return undefined;
  const out = [];
  for (const tool of tools) {
    if (tool?.type === "function" && tool.function) {
      out.push({
        name: tool.function.name,
        description: tool.function.description || "",
        input_schema: tool.function.parameters || { type: "object", properties: {} },
      });
    } else if (tool?.name && tool?.input_schema) {
      out.push(tool);
    }
  }
  return out.length ? out : undefined;
}

function convertToolChoice(choice) {
  if (!choice || choice === "auto") return undefined;
  if (choice === "none") return { type: "none" };
  return { type: "auto" };
}

function addToolResult(pending, msg) {
  const toolUseId = msg.tool_call_id || msg.id || msg.name;
  if (!toolUseId) return;
  pending.push({
    type: "tool_result",
    tool_use_id: toolUseId,
    content: contentToText(msg.content),
  });
}

// ──────────────────────────────────────
// OpenAI -> Anthropic 格式转换
// ──────────────────────────────────────

async function openaiToAnthropic(oai) {
  const model = MODEL_MAP[oai.model] || oai.model;
  const messages = [];
  const systemBlocks = [];
  let pendingToolResults = [];

  const flushToolResults = () => {
    if (pendingToolResults.length) {
      messages.push({ role: "user", content: pendingToolResults });
      pendingToolResults = [];
    }
  };

  for (const msg of oai.messages || []) {
    if (msg.role === "system") {
      const text = contentToText(msg.content);
      if (text) {
        const block = { type: "text", text };
        if (msg[DYNAMIC_SYSTEM_MARKER]) block[DYNAMIC_SYSTEM_MARKER] = true;
        if (msg[SUMMARY_CACHE_SYSTEM_MARKER]) block[SUMMARY_CACHE_SYSTEM_MARKER] = true;
        if (msg[SUMMARY_RECENT_SYSTEM_MARKER]) block[SUMMARY_RECENT_SYSTEM_MARKER] = true;
        if (msg[SUMITALK_REAL_MODE_SYSTEM_MARKER]) block[SUMITALK_REAL_MODE_SYSTEM_MARKER] = true;
        systemBlocks.push(block);
      }
    } else if (msg.role === "tool" || msg.role === "function") {
      addToolResult(pendingToolResults, msg);
    } else if (msg.role === "user") {
      flushToolResults();
      const content = await openaiContentToAnthropic(msg.content);
      messages.push({ role: "user", content: content.length ? content : [{ type: "text", text: "" }] });
    } else if (msg.role === "assistant") {
      flushToolResults();
      const content = await openaiContentToAnthropic(msg.content);
      if (Array.isArray(msg.thinking_blocks)) {
        content.unshift(...msg.thinking_blocks);
      }
      for (const call of msg.tool_calls || []) {
        if (call?.type !== "function" || !call.function?.name) continue;
        content.push({
          type: "tool_use",
          id: call.id,
          name: call.function.name,
          input: safeJsonParse(call.function.arguments, {}),
        });
      }
      if (content.length) {
        messages.push({ role: "assistant", content });
      }
    }
  }
  flushToolResults();

  const body = {
    model,
    max_tokens: oai.max_tokens || oai.max_completion_tokens || DEFAULT_MAX_TOKENS,
    messages,
  };

  if (systemBlocks.length) body.system = systemBlocks;
  if (oai.thinking && typeof oai.thinking === "object" && !Array.isArray(oai.thinking)) {
    body.thinking = { ...oai.thinking };
  }
  if (oai.output_config && typeof oai.output_config === "object" && !Array.isArray(oai.output_config)) {
    body.output_config = { ...oai.output_config };
  }
  if (oai.reasoning_effort && !body.output_config) {
    body.output_config = { effort: oai.reasoning_effort };
  }
  if (oai.temperature !== undefined) body.temperature = oai.temperature;
  if (oai.top_p !== undefined) body.top_p = oai.top_p;
  if (oai.stream) body.stream = true;
  if (oai.stop) body.stop_sequences = Array.isArray(oai.stop) ? oai.stop : [oai.stop];
  const tools = convertOpenaiTools(oai.tools);
  if (tools) body.tools = tools;
  const toolChoice = convertToolChoice(oai.tool_choice);
  if (toolChoice) body.tool_choice = toolChoice;
  if (oai.parallel_tool_calls === false) body.disable_parallel_tool_use = true;

  applyDefaultThinking(body);
  return body;
}

function applyDefaultThinking(body) {
  if (!body || typeof body !== "object") return body;
  if (!modelSupportsThinking(body.model)) return body;

  if (modelSupportsAdaptiveThinking(body.model)) {
    const outputConfig = body.output_config && typeof body.output_config === "object" ? { ...body.output_config } : {};
    outputConfig.effort = normalizeAdaptiveThinkingEffort(outputConfig.effort || body.reasoning_effort, body.model);
    body.thinking = { type: "adaptive", display: "summarized" };
    body.output_config = outputConfig;
    delete body.reasoning_effort;
    delete body.temperature;
    delete body.top_k;
    return body;
  }

  if (body.thinking) return body;

  const maxTokens = Number(body.max_tokens) || DEFAULT_MAX_TOKENS;
  const budget = Math.min(THINKING_BUDGET_TOKENS, maxTokens - 1);
  if (budget < 1024) return body;

  body.max_tokens = Math.max(maxTokens, budget + 1);
  body.thinking = { type: "enabled", budget_tokens: budget };

  delete body.temperature;
  delete body.top_k;
  return body;
}

function normalizeAdaptiveThinkingEffort(effort, model) {
  const value = String(effort || CLAUDE_ADAPTIVE_THINKING_EFFORT || "high").trim().toLowerCase();
  if (value === "xhigh" && modelIsClaudeOpus46(model)) return "high";
  return CLAUDE_ADAPTIVE_THINKING_EFFORTS.has(value) ? value : "high";
}

function modelSupportsAdaptiveThinking(model) {
  return /claude-(opus-4-(6|7|8)|fable-5)(\b|-|$)/.test(String(model || ""));
}

function modelIsClaudeOpus46(model) {
  return /claude-opus-4-6(\b|-|$)/.test(String(model || ""));
}

function modelSupportsThinking(model) {
  return /claude-(opus|sonnet)-4|claude-3-7-sonnet|claude-fable/.test(String(model || ""));
}

function convertUsage(usage = {}) {
  const inputTokens = usage.input_tokens || 0;
  const outputTokens = usage.output_tokens || 0;
  const cacheCreationInputTokens = usage.cache_creation_input_tokens || 0;
  const cacheReadInputTokens = usage.cache_read_input_tokens || 0;
  const out = {
    prompt_tokens: inputTokens,
    completion_tokens: outputTokens,
    total_tokens: inputTokens + outputTokens,
    cache_creation_input_tokens: cacheCreationInputTokens,
    cache_read_input_tokens: cacheReadInputTokens,
    anthropic_created: cacheCreationInputTokens,
    anthropic_read: cacheReadInputTokens,
    prompt_tokens_details: {
      cached_tokens: cacheReadInputTokens,
    },
  };
  if (usage.output_tokens_details && typeof usage.output_tokens_details === "object") {
    out.output_tokens_details = usage.output_tokens_details;
  }
  if (Array.isArray(usage.iterations)) {
    out.iterations = usage.iterations;
    out.anthropic_iterations = usage.iterations;
  }
  return out;
}

function anthropicToOpenai(ant, model, isStream) {
  if (isStream) return createOpenaiStreamConverter(model)(ant);

  const actualModel = String(ant.model || "").trim() || model;
  const textParts = [];
  const reasoningParts = [];
  const thinkingBlocks = [];
  const fallbackBlocks = [];
  const toolCalls = [];
  for (const part of ant.content || []) {
    if (part.type === "text") {
      textParts.push(part.text || "");
    } else if (part.type === "thinking") {
      thinkingBlocks.push(part);
      const thinkingText = part.thinking || part.text || "";
      if (thinkingText) reasoningParts.push(thinkingText);
    } else if (part.type === "redacted_thinking") {
      thinkingBlocks.push(part);
    } else if (part.type === "fallback") {
      fallbackBlocks.push(part);
    } else if (part.type === "tool_use") {
      toolCalls.push({
        id: part.id,
        type: "function",
        function: {
          name: part.name,
          arguments: JSON.stringify(part.input || {}),
        },
      });
    }
  }

  const message = {
    role: "assistant",
    content: textParts.join("") || (toolCalls.length ? null : ""),
  };
  if (reasoningParts.length) message.reasoning_content = reasoningParts.join("\n\n");
  if (thinkingBlocks.length) message.thinking_blocks = thinkingBlocks;
  if (fallbackBlocks.length) message.anthropic_fallback_blocks = fallbackBlocks;
  if (toolCalls.length) message.tool_calls = toolCalls;

  const resp = {
    id: "chatcmpl-" + ant.id,
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model: actualModel,
    choices: [
      {
        index: 0,
        message,
        finish_reason:
          ant.stop_reason === "tool_use"
            ? "tool_calls"
            : ant.stop_reason === "max_tokens"
              ? "length"
              : "stop",
      },
    ],
    usage: convertUsage(ant.usage),
  };
  if (actualModel !== model) resp.requested_model = model;
  resp.anthropic_model = actualModel;
  if (fallbackBlocks.length) resp.anthropic_fallback_blocks = fallbackBlocks;
  return resp;
}

function createOpenaiStreamConverter(model) {
  let messageId = "stream";
  let created = Math.floor(Date.now() / 1000);
  let servingModel = model;
  let nextToolIndex = 0;
  let inputTokens = 0;
  let outputTokens = 0;
  let cacheCreationInputTokens = 0;
  let cacheReadInputTokens = 0;
  let outputTokensDetails = null;
  let usageIterations = null;
  const blocks = new Map();
  const thinkingBlocks = [];
  const fallbackBlocks = [];

  const chunk = (delta, finish_reason = null, extra = {}) => {
    const out = {
      id: "chatcmpl-" + messageId,
      object: "chat.completion.chunk",
      created,
      model: servingModel,
      choices: [{ index: 0, delta, finish_reason }],
      ...extra,
    };
    if (servingModel !== model) out.requested_model = model;
    out.anthropic_model = servingModel;
    return out;
  };

  return (event) => {
    if (event.type === "message_start") {
      messageId = event.message?.id || messageId;
      servingModel = String(event.message?.model || "").trim() || servingModel;
      inputTokens = event.message?.usage?.input_tokens || 0;
      outputTokens = event.message?.usage?.output_tokens || 0;
      cacheCreationInputTokens = event.message?.usage?.cache_creation_input_tokens || 0;
      cacheReadInputTokens = event.message?.usage?.cache_read_input_tokens || 0;
      outputTokensDetails = event.message?.usage?.output_tokens_details || outputTokensDetails;
      usageIterations = Array.isArray(event.message?.usage?.iterations) ? event.message.usage.iterations : usageIterations;
      return chunk({ role: "assistant", content: "" });
    }

    if (event.type === "content_block_start") {
      const index = event.index ?? 0;
      const block = event.content_block || {};
      if (block.type === "fallback") {
        fallbackBlocks.push(block);
        servingModel = String(block.to?.model || "").trim() || servingModel;
        return null;
      }
      const state = { type: block.type, block: { ...block } };
      if (block.type === "tool_use") {
        state.toolIndex = nextToolIndex++;
        blocks.set(index, state);
        return chunk({
          tool_calls: [
            {
              index: state.toolIndex,
              id: block.id,
              type: "function",
              function: { name: block.name, arguments: "" },
            },
          ],
        });
      }
      blocks.set(index, state);
      if (block.type === "thinking") {
        state.block.thinking = state.block.thinking || "";
        return chunk({ reasoning_content: "" });
      }
      if (block.type === "redacted_thinking") {
        thinkingBlocks.push(state.block);
      }
      return null;
    }

    if (event.type === "content_block_delta") {
      const state = blocks.get(event.index ?? 0) || {};
      if (event.delta?.type === "text_delta") {
        return chunk({ content: event.delta.text || "" });
      }
      if (event.delta?.type === "thinking_delta") {
        const text = event.delta.thinking || event.delta.text || "";
        if (state.block) state.block.thinking = (state.block.thinking || "") + text;
        return chunk({ reasoning_content: text });
      }
      if (event.delta?.type === "signature_delta") {
        if (state.block) state.block.signature = (state.block.signature || "") + (event.delta.signature || "");
        return null;
      }
      if (event.delta?.type === "input_json_delta" && state.toolIndex !== undefined) {
        return chunk({
          tool_calls: [
            {
              index: state.toolIndex,
              function: { arguments: event.delta.partial_json || "" },
            },
          ],
        });
      }
    }

    if (event.type === "message_delta") {
      const stopReason = event.delta?.stop_reason;
      outputTokens = event.usage?.output_tokens || outputTokens;
      cacheCreationInputTokens = event.usage?.cache_creation_input_tokens || cacheCreationInputTokens;
      cacheReadInputTokens = event.usage?.cache_read_input_tokens || cacheReadInputTokens;
      outputTokensDetails = event.usage?.output_tokens_details || outputTokensDetails;
      usageIterations = Array.isArray(event.usage?.iterations) ? event.usage.iterations : usageIterations;
      const fullThinkingBlocks = [
        ...thinkingBlocks,
        ...Array.from(blocks.values())
          .filter((state) => state.type === "thinking" && state.block?.thinking)
          .map((state) => state.block),
      ];
      return chunk(
        fullThinkingBlocks.length ? { thinking_blocks: fullThinkingBlocks } : {},
        stopReason === "tool_use" ? "tool_calls" : stopReason === "max_tokens" ? "length" : "stop",
        {
          usage: convertUsage({
            input_tokens: inputTokens,
            output_tokens: outputTokens,
            cache_creation_input_tokens: cacheCreationInputTokens,
            cache_read_input_tokens: cacheReadInputTokens,
            output_tokens_details: outputTokensDetails,
            iterations: usageIterations,
          }),
          ...(fallbackBlocks.length ? { anthropic_fallback_blocks: fallbackBlocks } : {}),
        }
      );
    }

    return null;
  };
}

// ──────────────────────────────────────
// Anthropic 原生请求处理
// ──────────────────────────────────────

function processAnthropicBody(body) {
  const existingSystem = (() => {
    if (!body.system) return [];
    if (Array.isArray(body.system)) return body.system.filter((item) => !isClaudeBillingSystemBlock(item));
    return [{ type: "text", text: body.system }];
  })();

  const billingSeed = existingSystem.find((item) => String(item?.text || "").trim())?.text || "";
  body.system = [
    claudeBillingSystemBlock(billingSeed),
    ...existingSystem,
  ];
  stripTtlFromCacheControl(body);
  applyPromptCache(body);
  return body;
}

function applyPromptCache(body) {
  const cacheControl = CLAUDE_PROMPT_CACHE_TTL
    ? { type: "ephemeral", ttl: CLAUDE_PROMPT_CACHE_TTL }
    : { type: "ephemeral" };
      const setCacheControl = (item) => {
    if (item && typeof item === "object") item.cache_control = { ...cacheControl };
  };

  if (Array.isArray(body.tools) && body.tools.length > 0) {
    const lastTool = body.tools[body.tools.length - 1];
    setCacheControl(lastTool);
  }

  if (Array.isArray(body.system) && body.system.length > 0) {
    splitGatewaySummaryBlocks(body.system);

    const summaryIdx = body.system.findIndex(
      (item, idx) => idx > 0 && (item?.[SUMMARY_CACHE_SYSTEM_MARKER] || looksLikeGatewaySummaryCacheBlock(item))
    );

    if (summaryIdx > 0) {
      setCacheControl(findCacheableSystemBefore(body.system, summaryIdx));
      setCacheControl(body.system[summaryIdx]);
      const recentIdx = body.system.findIndex(
        (item, idx) =>
          idx > summaryIdx &&
          (item?.[SUMMARY_RECENT_SYSTEM_MARKER] || looksLikeGatewayRecentSummaryBlock(item))
      );
      const realModeIdx = body.system.findIndex(
        (item, idx) => idx > summaryIdx && item?.[SUMITALK_REAL_MODE_SYSTEM_MARKER]
      );
      if (realModeIdx > summaryIdx) {
        setCacheControl(body.system[realModeIdx]);
      } else if (recentIdx > summaryIdx) {
        setCacheControl(body.system[recentIdx]);
      }
    } else {
      let staticSystem = null;
      for (let i = 1; i < body.system.length; i += 1) {
        const item = body.system[i];
        if (
          item?.[DYNAMIC_SYSTEM_MARKER] ||
          item?.[SUMMARY_RECENT_SYSTEM_MARKER] ||
          looksLikeGatewayDynamicSystemBlock(item) ||
          looksLikeGatewayRecentSummaryBlock(item)
        ) break;
        if (item && typeof item === "object") staticSystem = item;
      }
      setCacheControl(staticSystem);
    }

    for (const item of body.system) {
      if (item && typeof item === "object") {
        delete item[DYNAMIC_SYSTEM_MARKER];
        delete item[SUMMARY_CACHE_SYSTEM_MARKER];
        delete item[SUMMARY_RECENT_SYSTEM_MARKER];
        delete item[SUMITALK_REAL_MODE_SYSTEM_MARKER];
      }
    }
  }
}

function splitGatewaySummaryBlocks(systemBlocks) {
  if (!Array.isArray(systemBlocks)) return;
  for (let i = 1; i < systemBlocks.length; i += 1) {
    const item = systemBlocks[i];
    if (!(item?.[SUMMARY_CACHE_SYSTEM_MARKER] || looksLikeGatewaySummaryCacheBlock(item))) continue;
    if (systemBlocks[i + 1]?.[SUMMARY_RECENT_SYSTEM_MARKER] || looksLikeGatewayRecentSummaryBlock(systemBlocks[i + 1])) return;

    const split = splitGatewaySummaryText(item.text);
    if (!split.recentText) return;
    item.text = split.stableText;
    item[SUMMARY_CACHE_SYSTEM_MARKER] = true;
    systemBlocks.splice(i + 1, 0, {
      type: "text",
      text: split.recentText,
      [SUMMARY_RECENT_SYSTEM_MARKER]: true,
    });
    return;
  }
}

function splitGatewaySummaryText(value) {
  let text = String(value || "").trim();
  if (!text) return { stableText: "", recentText: "" };
  text = text.replace(/【以上为近期记忆】\s*$/u, "").trim();
  const recentIdx = text.indexOf("【最近】");
  if (recentIdx < 0) return { stableText: String(value || ""), recentText: "" };

  const stableRaw = text.slice(0, recentIdx).trim();
  const recentRaw = text.slice(recentIdx).trim();
  if (!recentRaw) return { stableText: String(value || ""), recentText: "" };
  return {
    stableText: stableRaw
      ? `${stableRaw}\n【以上为较稳定的近期记忆】`
      : "",
    recentText: `\n\n【近期记忆（最近）】\n${recentRaw}\n【以上为最近记忆】`,
  };
}

function findCacheableSystemBefore(systemBlocks, endIdx) {
  for (let i = endIdx - 1; i > 0; i -= 1) {
    const item = systemBlocks[i];
    if (
      item &&
      typeof item === "object" &&
      !item?.[DYNAMIC_SYSTEM_MARKER] &&
      !item?.[SUMMARY_RECENT_SYSTEM_MARKER] &&
      !looksLikeGatewayRecentSummaryBlock(item)
    ) {
      return item;
    }
  }
  return null;
}

function looksLikeGatewaySummaryCacheBlock(item) {
  const text = String(item?.text || "").trimStart();
  return text.startsWith("【近期记忆】");
}

function looksLikeGatewayRecentSummaryBlock(item) {
  const text = String(item?.text || "").trimStart();
  return text.startsWith("【近期记忆（最近）】");
}

function looksLikeGatewayDynamicSystemBlock(item) {
  const text = String(item?.text || "").trimStart();
  if (!text) return false;
  return GATEWAY_DYNAMIC_SYSTEM_HINTS.some((hint) => text.startsWith(hint));
}

function sendError(res, status, msg) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: { type: "proxy_error", message: msg } }));
}

function sendOpenaiError(res, status, msg) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: { message: msg, type: "proxy_error", code: status } }));
}

function proxyExceptionStatus(err) {
  const msg = String(err?.message || err || "");
  if (/oauth token|oauth credentials|local token sync|synced credentials/i.test(msg)) {
    return 503;
  }
  return 500;
}

function sendJson(res, status, payload) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(payload));
}

function oauthStatusPayload() {
  if (!cachedOAuth) {
    cachedOAuth = readOAuthCredentials();
    log(
      `Token loaded from ${cachedOAuthSource || "unknown"} (expires ${new Date(
        cachedOAuth.expiresAt
      ).toLocaleString()})`
    );
  }
  const expiresInSeconds = oauthExpiresInSeconds();
  return {
    ok: true,
    source: cachedOAuthSource || "unknown",
    canRefresh: Boolean(cachedOAuth.refreshToken),
    expiresAt: cachedOAuth.expiresAt,
    expiresInSeconds,
    stale: expiresInSeconds <= Math.ceil(REFRESH_SKEW_MS / 1000),
    lastUnauthorizedAt,
    lastUnauthorizedRoute,
    rateLimitSnapshot: lastRateLimitSnapshot,
  };
}

function firstHeaderValue(headers, name) {
  const value = headers?.[name];
  if (Array.isArray(value)) return value[0] || "";
  return value === undefined || value === null ? "" : String(value);
}

function numericHeader(headers, name) {
  const raw = firstHeaderValue(headers, name);
  if (!raw) return undefined;
  const n = Number(raw);
  return Number.isFinite(n) ? n : raw;
}

function rateLimitWindow(headers, prefix) {
  const status = firstHeaderValue(headers, `${prefix}-status`);
  const resetAt = numericHeader(headers, `${prefix}-reset`);
  const utilization = numericHeader(headers, `${prefix}-utilization`);
  if (!status && resetAt === undefined && utilization === undefined) return undefined;
  const out = {};
  if (status) out.status = status;
  if (resetAt !== undefined) out.resetAt = resetAt;
  if (utilization !== undefined) out.utilization = utilization;
  return out;
}

function updateRateLimitSnapshot(proxyRes, routeLabel) {
  const headers = proxyRes?.headers || {};
  const fiveHour = rateLimitWindow(headers, "anthropic-ratelimit-unified-5h");
  const sevenDay = rateLimitWindow(headers, "anthropic-ratelimit-unified-7d");
  const unifiedStatus = firstHeaderValue(headers, "anthropic-ratelimit-unified-status");
  const resetAt = numericHeader(headers, "anthropic-ratelimit-unified-reset");
  const representativeClaim = firstHeaderValue(
    headers,
    "anthropic-ratelimit-unified-representative-claim"
  );
  const fallbackPercentage = numericHeader(
    headers,
    "anthropic-ratelimit-unified-fallback-percentage"
  );
  const overageStatus = firstHeaderValue(headers, "anthropic-ratelimit-unified-overage-status");
  const overageDisabledReason = firstHeaderValue(
    headers,
    "anthropic-ratelimit-unified-overage-disabled-reason"
  );
  const retryAfter = numericHeader(headers, "retry-after");

  if (
    !fiveHour &&
    !sevenDay &&
    !unifiedStatus &&
    resetAt === undefined &&
    !representativeClaim &&
    fallbackPercentage === undefined &&
    !overageStatus &&
    !overageDisabledReason &&
    retryAfter === undefined
  ) {
    return;
  }

  const snapshot = {
    updatedAt: Date.now(),
    route: routeLabel || "",
    statusCode: proxyRes.statusCode || 0,
  };
  if (unifiedStatus) snapshot.status = unifiedStatus;
  if (resetAt !== undefined) snapshot.resetAt = resetAt;
  if (representativeClaim) snapshot.representativeClaim = representativeClaim;
  if (fallbackPercentage !== undefined) snapshot.fallbackPercentage = fallbackPercentage;
  if (overageStatus) snapshot.overageStatus = overageStatus;
  if (overageDisabledReason) snapshot.overageDisabledReason = overageDisabledReason;
  if (retryAfter !== undefined) snapshot.retryAfter = retryAfter;
  if (fiveHour) snapshot.fiveHour = fiveHour;
  if (sevenDay) snapshot.sevenDay = sevenDay;
  lastRateLimitSnapshot = snapshot;
}

function proxyToAnthropic(token, path, payload) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(payload);
    const req = https.request(
      {
        hostname: TARGET_HOST,
        port: 443,
        path,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          "anthropic-version": ANTHROPIC_VERSION,
          "anthropic-beta": BETA_HEADER,
          "User-Agent": `claude-code/${CLAUDE_CODE_VERSION} (external, cli)`,
          "Content-Length": Buffer.byteLength(data),
        },
      },
      (proxyRes) => resolve(proxyRes)
    );
    req.on("error", reject);
    req.write(data);
    req.end();
  });
}

function proxyGetAnthropic(token, path) {
  return new Promise((resolve, reject) => {
    const req = https.request(
      {
        hostname: TARGET_HOST,
        port: 443,
        path,
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
          "anthropic-version": ANTHROPIC_VERSION,
          "anthropic-beta": BETA_HEADER,
          "User-Agent": `claude-code/${CLAUDE_CODE_VERSION} (external, cli)`,
        },
      },
      (proxyRes) => resolve(proxyRes)
    );
    req.on("error", reject);
    req.end();
  });
}

function makeJsonProxyResponse(statusCode, payload) {
  const stream = Readable.from([JSON.stringify(payload)]);
  stream.statusCode = statusCode;
  stream.headers = { "content-type": "application/json" };
  return stream;
}

async function retryGetAfterUnauthorized(proxyRes, path, routeLabel) {
  const errData = await readStreamText(proxyRes).catch((e) => `read error: ${e.message}`);
  const hint = errData ? `: ${errData.slice(0, 500)}` : "";
  lastUnauthorizedAt = Date.now();
  lastUnauthorizedRoute = routeLabel || path || "";
  const staleAccessToken = cachedOAuth?.accessToken || "";
  log(`Got 401 from Anthropic for ${routeLabel}; refreshing OAuth token${hint}`);

  try {
    await refreshOAuthCredentials(`401 from ${routeLabel || path || "Anthropic"}`);
  } catch (e) {
    log(`OAuth refresh failed after 401: ${e.message}`);
    return makeJsonProxyResponse(401, {
      error: {
        type: "authentication_error",
        message: `Claude OAuth token was rejected and proxy refresh failed: ${e.message}`,
      },
    });
  }

  if (!cachedOAuth.accessToken || cachedOAuth.accessToken === staleAccessToken) {
    log("OAuth credentials unchanged after 401 refresh");
    return makeJsonProxyResponse(401, {
      error: {
        type: "authentication_error",
        message: "Claude OAuth token was rejected and refresh did not produce a new access token",
      },
    });
  }

  const retryRes = await proxyGetAnthropic(cachedOAuth.accessToken, path);
  log(`<= ${retryRes.statusCode} ${routeLabel} (retry after proxy refresh)`);
  return retryRes;
}

async function retryAfterUnauthorized(proxyRes, path, payload, routeLabel) {
  const errData = await readStreamText(proxyRes).catch((e) => `read error: ${e.message}`);
  const hint = errData ? `: ${errData.slice(0, 500)}` : "";
  lastUnauthorizedAt = Date.now();
  lastUnauthorizedRoute = routeLabel || path || "";
  const staleAccessToken = cachedOAuth?.accessToken || "";
  log(`Got 401 from Anthropic for ${routeLabel}; refreshing OAuth token${hint}`);

  try {
    await refreshOAuthCredentials(`401 from ${routeLabel || path || "Anthropic"}`);
  } catch (e) {
    log(`OAuth refresh failed after 401: ${e.message}`);
    return makeJsonProxyResponse(401, {
      error: {
        type: "authentication_error",
        message: `Claude OAuth token was rejected and proxy refresh failed: ${e.message}`,
      },
    });
  }

  if (!cachedOAuth.accessToken || cachedOAuth.accessToken === staleAccessToken) {
    log("OAuth credentials unchanged after 401 refresh");
    return makeJsonProxyResponse(401, {
      error: {
        type: "authentication_error",
        message: "Claude OAuth token was rejected and refresh did not produce a new access token",
      },
    });
  }

  const retryRes = await proxyToAnthropic(cachedOAuth.accessToken, path, payload);
  log(`<= ${retryRes.statusCode} ${routeLabel} (retry after proxy refresh)`);
  return retryRes;
}

// ──────────────────────────────────────
// Server
// ──────────────────────────────────────

const server = http.createServer(async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "*");
  res.setHeader("Access-Control-Allow-Headers", "*");
  if (req.method === "OPTIONS") {
    res.writeHead(204);
    return res.end();
  }

  if (!PROXY_KEY) {
    return sendError(res, 500, "PROXY_KEY is required");
  }

  const urlPath = String(req.url || "").split("?")[0];
  if (urlPath === "/internal/oauth-status") {
    if (!OAUTH_SYNC_KEY) {
      return sendError(res, 500, "CLAUDE_OAUTH_SYNC_KEY is required");
    }
    if (!secretMatches(requestSecret(req), OAUTH_SYNC_KEY)) {
      log(`OAUTH SYNC AUTH REJECTED ${req.method} ${req.url}`);
      return sendError(res, 401, "Invalid sync key");
    }
    if (req.method !== "GET") {
      return sendError(res, 405, "Method not allowed");
    }
    try {
      return sendJson(res, 200, oauthStatusPayload());
    } catch (e) {
      return sendError(res, 500, e.message);
    }
  }

  if (urlPath === "/internal/oauth-sync") {
    if (!OAUTH_SYNC_KEY) {
      return sendError(res, 500, "CLAUDE_OAUTH_SYNC_KEY is required");
    }
    if (!secretMatches(requestSecret(req), OAUTH_SYNC_KEY)) {
      log(`OAUTH SYNC AUTH REJECTED ${req.method} ${req.url}`);
      return sendError(res, 401, "Invalid sync key");
    }
    if (req.method !== "POST") {
      return sendError(res, 405, "Method not allowed");
    }
    const rawBody = await readBody(req);
    let payload;
    try {
      payload = JSON.parse(rawBody.toString("utf8"));
    } catch {
      return sendError(res, 400, "Invalid JSON body");
    }
    try {
      const synced = writeSyncedOAuthCredentials(payload);
      log(`OAuth credentials synced by HTTP (expires ${new Date(synced.expiresAt).toLocaleString()})`);
      return sendJson(res, 200, {
        ok: true,
        source: cachedOAuthSource,
        canRefresh: Boolean(synced.refreshToken),
        expiresAt: synced.expiresAt,
        expiresInSeconds: Math.floor((synced.expiresAt - Date.now()) / 1000),
        lastUnauthorizedAt,
        lastUnauthorizedRoute,
      });
    } catch (e) {
      log(`OAuth sync failed: ${e.message}`);
      return sendError(res, 400, e.message);
    }
  }

  const clientKey = requestSecret(req);
  if (!secretMatches(clientKey, PROXY_KEY)) {
    log(`AUTH REJECTED ${req.method} ${req.url}`);
    return sendError(res, 401, "Invalid proxy key");
  }

  // GET /v1/models - 转发真实可用模型列表
  if (req.method === "GET" && req.url.startsWith("/v1/models")) {
    log(`=> ${req.method} ${req.url}`);
    try {
      const token = await getAccessToken(req.url);
      let proxyRes = await proxyGetAnthropic(token, req.url);
      log(`<= ${proxyRes.statusCode} ${req.url}`);

      if (proxyRes.statusCode === 401) {
        proxyRes = await retryGetAfterUnauthorized(proxyRes, req.url, req.url);
      }
      updateRateLimitSnapshot(proxyRes, req.url);

      const responseHeaders = { ...proxyRes.headers, "access-control-allow-origin": "*" };
      res.writeHead(proxyRes.statusCode || 502, responseHeaders);
      proxyRes.pipe(res);
      return;
    } catch (e) {
      log(`Error: ${e.message}`);
      return sendError(res, proxyExceptionStatus(e), e.message);
    }
  }

  log(`=> ${req.method} ${req.url}`);

  const rawBody = await readBody(req);
  let body;
  try {
    body = JSON.parse(rawBody.toString());
  } catch {
    body = {};
  }

  const isOpenAI = req.url.startsWith("/v1/chat/completions");

  try {
    const token = await getAccessToken(req.url);

    if (isOpenAI) {
      // ─── OpenAI 兼容路径 ───
      const anthropicBody = await openaiToAnthropic(body);
      const requestModel = anthropicBody.model;
      processAnthropicBody(anthropicBody);

      let proxyRes = await proxyToAnthropic(token, "/v1/messages", anthropicBody);
      log(`<= ${proxyRes.statusCode} ${req.url}`);

      if (proxyRes.statusCode === 401) {
        proxyRes = await retryAfterUnauthorized(proxyRes, "/v1/messages", anthropicBody, req.url);
      }
      updateRateLimitSnapshot(proxyRes, req.url);

      if (proxyRes.statusCode !== 200) {
        const errData = await readStreamText(proxyRes);
        return sendOpenaiError(res, proxyRes.statusCode, errData);
      }

      if (body.stream) {
        res.writeHead(200, {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
        });

        let buffer = "";
        const decoder = new StringDecoder("utf8");
        const streamConverter = createOpenaiStreamConverter(requestModel);
        proxyRes.on("data", (chunk) => {
          buffer += decoder.write(chunk);
          const lines = buffer.split("\n");
          buffer = lines.pop();
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (raw === "[DONE]") continue;
            try {
              const event = JSON.parse(raw);
              const converted = streamConverter(event);
              if (converted) {
                res.write(`data: ${JSON.stringify(converted)}\n\n`);
              }
            } catch {}
          }
        });
        proxyRes.on("end", () => {
          buffer += decoder.end();
          if (buffer.trim()) {
            for (const line of buffer.split("\n")) {
              if (!line.startsWith("data: ")) continue;
              const raw = line.slice(6).trim();
              if (!raw || raw === "[DONE]") continue;
              try {
                const event = JSON.parse(raw);
                const converted = streamConverter(event);
                if (converted) {
                  res.write(`data: ${JSON.stringify(converted)}\n\n`);
                }
              } catch {}
            }
          }
          res.write("data: [DONE]\n\n");
          res.end();
        });
        proxyRes.on("error", () => res.end());
      } else {
        const data = await readStreamText(proxyRes);
        const anthropicResp = JSON.parse(data);
        const openaiResp = anthropicToOpenai(anthropicResp, requestModel, false);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(openaiResp));
      }
    } else {
      // ─── Anthropic 原生路径 ───
      processAnthropicBody(body);
      let proxyRes = await proxyToAnthropic(token, req.url, body);
      log(`<= ${proxyRes.statusCode} ${req.url}`);

      if (proxyRes.statusCode === 401) {
        proxyRes = await retryAfterUnauthorized(proxyRes, req.url, body, req.url);
      }
      updateRateLimitSnapshot(proxyRes, req.url);

      const responseHeaders = { ...proxyRes.headers, "access-control-allow-origin": "*" };
      res.writeHead(proxyRes.statusCode, responseHeaders);
      proxyRes.pipe(res);
    }
  } catch (e) {
    log(`Error: ${e.message}`);
    const status = proxyExceptionStatus(e);
    isOpenAI ? sendOpenaiError(res, status, e.message) : sendError(res, status, e.message);
  }
});

server.listen(PORT, HOST, () => {
  log(`Claude OAuth Proxy running on http://${HOST}:${PORT}`);
  log("Auth: PROXY_KEY required");
  log("");
  log("Endpoints:");
  log(`  POST http://localhost:${PORT}/v1/chat/completions  (OpenAI format)`);
  log(`  POST http://localhost:${PORT}/v1/messages          (Anthropic format)`);
  log(`  GET  http://localhost:${PORT}/v1/models`);
  log(`  POST http://localhost:${PORT}/internal/oauth-sync   (OAuth sync)`);
  log(`  GET  http://localhost:${PORT}/internal/oauth-status (OAuth status)`);
});
