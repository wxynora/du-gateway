#!/usr/bin/env node

const http = require("http");
const https = require("https");
const fs = require("fs");
const { execSync } = require("child_process");

const PORT = parseInt(process.env.PORT || "8082");
const HOST = process.env.HOST || "127.0.0.1";
const PROXY_KEY = process.env.PROXY_KEY;
const DEFAULT_MAX_TOKENS = parseInt(process.env.CLAUDE_MAX_TOKENS || "8192", 10);
const THINKING_BUDGET_TOKENS = parseInt(
  process.env.CLAUDE_THINKING_BUDGET_TOKENS || "4096",
  10
);
const CLAUDE_OAUTH_FILE = process.env.CLAUDE_OAUTH_FILE || "";
const CLAUDE_OAUTH_JSON = process.env.CLAUDE_OAUTH_JSON || "";
const TARGET_HOST = "api.anthropic.com";
const CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e";
const REFRESH_URL = "https://console.anthropic.com/v1/oauth/token";
const ANTHROPIC_VERSION = "2023-06-01";
const BETA_HEADER = [
  "claude-code-20250219",
  "oauth-2025-04-20",
  "interleaved-thinking-2025-05-14",
  "fine-grained-tool-streaming-2025-05-14",
  "prompt-caching-scope-2026-01-05",
  "token-efficient-tools-2025-02-19",
  "context-management-2025-06-27",
  "effort-2025-11-24",
].join(",");

const SYSTEM_PROMPT_PREFIX = {
  type: "text",
  text: "You are Claude Code, Anthropic's official CLI for Claude.",
};

const MODEL_MAP = {
  "gpt-4o": "claude-sonnet-4-6",
  "gpt-4o-mini": "claude-haiku-4-5-20251001",
  "gpt-4-turbo": "claude-sonnet-4-6",
  "gpt-4": "claude-sonnet-4-6",
  "gpt-3.5-turbo": "claude-haiku-4-5-20251001",
};

let cachedOAuth = null;

function log(msg) {
  console.log(`[${new Date().toLocaleTimeString()}] ${msg}`);
}

function readKeychainOAuth() {
  const raw = execSync(
    'security find-generic-password -s "Claude Code-credentials" -w'
  )
    .toString()
    .trim();
  return JSON.parse(raw).claudeAiOauth;
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
  const accessToken = src.accessToken || src.access_token;
  const refreshToken = src.refreshToken || src.refresh_token;
  if (!accessToken || !refreshToken) {
    throw new Error("OAuth credentials must include accessToken/access_token and refreshToken/refresh_token");
  }
  return {
    accessToken,
    refreshToken,
    expiresAt: parseExpiresAt(src.expiresAt || src.expires_at || src.expiry || src.expires),
  };
}

function readOAuthCredentials() {
  if (CLAUDE_OAUTH_JSON) return normalizeOAuth(CLAUDE_OAUTH_JSON);
  if (CLAUDE_OAUTH_FILE) return normalizeOAuth(fs.readFileSync(CLAUDE_OAUTH_FILE, "utf8"));
  return normalizeOAuth({ claudeAiOauth: readKeychainOAuth() });
}

function httpsRequest(url, method, headers, body) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const req = https.request(
      { hostname: u.hostname, port: 443, path: u.pathname, method, headers },
      (res) => {
        let data = "";
        res.on("data", (c) => (data += c));
        res.on("end", () => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(JSON.parse(data));
          } else {
            reject(new Error(`HTTP ${res.statusCode}: ${data}`));
          }
        });
      }
    );
    req.on("error", reject);
    if (body) req.write(typeof body === "string" ? body : JSON.stringify(body));
    req.end();
  });
}

async function refreshToken(refreshTk) {
  log("Refreshing access token...");
  const result = await httpsRequest(
    REFRESH_URL,
    "POST",
    { "Content-Type": "application/json" },
    { grant_type: "refresh_token", refresh_token: refreshTk, client_id: CLIENT_ID }
  );
  return {
    accessToken: result.access_token,
    refreshToken: result.refresh_token || refreshTk,
    expiresAt: Date.now() + result.expires_in * 1000,
  };
}

async function getAccessToken() {
  if (!cachedOAuth) {
    cachedOAuth = readOAuthCredentials();
    log(`Token loaded (expires ${new Date(cachedOAuth.expiresAt).toLocaleString()})`);
  }
  if (Date.now() > cachedOAuth.expiresAt - 5 * 60 * 1000) {
    try {
      const r = await refreshToken(cachedOAuth.refreshToken);
      Object.assign(cachedOAuth, r);
      log(`Token refreshed (expires ${new Date(r.expiresAt).toLocaleString()})`);
    } catch (e) {
      log(`Refresh failed: ${e.message}, re-reading credentials...`);
      cachedOAuth = readOAuthCredentials();
    }
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

function openaiContentToAnthropic(content) {
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
        out.push({ type: "text", text: `[image: ${url}]` });
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

function openaiToAnthropic(oai) {
  const model = MODEL_MAP[oai.model] || oai.model;
  const messages = [];
  let systemText = "";
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
      if (text) systemText += (systemText ? "\n" : "") + text;
    } else if (msg.role === "tool" || msg.role === "function") {
      addToolResult(pendingToolResults, msg);
    } else if (msg.role === "user") {
      flushToolResults();
      const content = openaiContentToAnthropic(msg.content);
      messages.push({ role: "user", content: content.length ? content : [{ type: "text", text: "" }] });
    } else if (msg.role === "assistant") {
      flushToolResults();
      const content = openaiContentToAnthropic(msg.content);
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

  if (systemText) body.system = systemText;
  if (oai.temperature !== undefined) body.temperature = oai.temperature;
  if (oai.top_p !== undefined) body.top_p = oai.top_p;
  if (oai.stream) body.stream = true;
  if (oai.stop) body.stop_sequences = Array.isArray(oai.stop) ? oai.stop : [oai.stop];
  const tools = convertOpenaiTools(oai.tools);
  if (tools) body.tools = tools;
  const toolChoice = convertToolChoice(oai.tool_choice);
  if (toolChoice) body.tool_choice = toolChoice;
  if (oai.parallel_tool_calls === false) body.disable_parallel_tool_use = true;

  return body;
}

function applyDefaultThinking(body) {
  if (!body || typeof body !== "object") return body;
  if (body.thinking) return body;
  if (!modelSupportsThinking(body.model)) return body;

  const maxTokens = Number(body.max_tokens) || DEFAULT_MAX_TOKENS;
  const budget = Math.min(THINKING_BUDGET_TOKENS, maxTokens - 1);
  if (budget < 1024) return body;

  body.max_tokens = Math.max(maxTokens, budget + 1);
  body.thinking = { type: "enabled", budget_tokens: budget };

  delete body.temperature;
  delete body.top_k;
  return body;
}

function modelSupportsThinking(model) {
  return /claude-(opus|sonnet)-4|claude-3-7-sonnet/.test(String(model || ""));
}

function anthropicToOpenai(ant, model, isStream) {
  if (isStream) return createOpenaiStreamConverter(model)(ant);

  const textParts = [];
  const reasoningParts = [];
  const thinkingBlocks = [];
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
  if (toolCalls.length) message.tool_calls = toolCalls;

  return {
    id: "chatcmpl-" + ant.id,
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model,
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
    usage: {
      prompt_tokens: ant.usage?.input_tokens || 0,
      completion_tokens: ant.usage?.output_tokens || 0,
      total_tokens: (ant.usage?.input_tokens || 0) + (ant.usage?.output_tokens || 0),
    },
  };
}

function createOpenaiStreamConverter(model) {
  let messageId = "stream";
  let created = Math.floor(Date.now() / 1000);
  let nextToolIndex = 0;
  let inputTokens = 0;
  let outputTokens = 0;
  const blocks = new Map();

  const chunk = (delta, finish_reason = null, extra = {}) => ({
    id: "chatcmpl-" + messageId,
    object: "chat.completion.chunk",
    created,
    model,
    choices: [{ index: 0, delta, finish_reason }],
    ...extra,
  });

  return (event) => {
    if (event.type === "message_start") {
      messageId = event.message?.id || messageId;
      inputTokens = event.message?.usage?.input_tokens || 0;
      outputTokens = event.message?.usage?.output_tokens || 0;
      return chunk({ role: "assistant", content: "" });
    }

    if (event.type === "content_block_start") {
      const index = event.index ?? 0;
      const block = event.content_block || {};
      const state = { type: block.type };
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
      if (block.type === "thinking") return chunk({ reasoning_content: "" });
      return null;
    }

    if (event.type === "content_block_delta") {
      const state = blocks.get(event.index ?? 0) || {};
      if (event.delta?.type === "text_delta") {
        return chunk({ content: event.delta.text || "" });
      }
      if (event.delta?.type === "thinking_delta") {
        return chunk({ reasoning_content: event.delta.thinking || event.delta.text || "" });
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
      return chunk(
        {},
        stopReason === "tool_use" ? "tool_calls" : stopReason === "max_tokens" ? "length" : "stop",
        {
          usage: {
            prompt_tokens: inputTokens,
            completion_tokens: outputTokens,
            total_tokens: inputTokens + outputTokens,
          },
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
  if (body.system) {
    if (Array.isArray(body.system)) {
      body.system.unshift(SYSTEM_PROMPT_PREFIX);
    } else {
      body.system = [SYSTEM_PROMPT_PREFIX, { type: "text", text: body.system }];
    }
  } else {
    body.system = [SYSTEM_PROMPT_PREFIX];
  }
  stripTtlFromCacheControl(body);
  return body;
}

function sendError(res, status, msg) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: { type: "proxy_error", message: msg } }));
}

function sendOpenaiError(res, status, msg) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: { message: msg, type: "proxy_error", code: status } }));
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

  const clientKey =
    req.headers["x-api-key"] ||
    (req.headers.authorization || "").replace("Bearer ", "");
  if (clientKey !== PROXY_KEY) {
    log(`AUTH REJECTED ${req.method} ${req.url}`);
    return sendError(res, 401, "Invalid proxy key");
  }

  // GET /v1/models - 返回模型列表
  if (req.method === "GET" && req.url.startsWith("/v1/models")) {
    const models = [
      "claude-opus-4-7", "claude-opus-4-6",
      "claude-sonnet-4-6", "claude-sonnet-4-5-20241022",
      "claude-haiku-4-5-20251001",
    ].map((id) => ({ id, object: "model", created: 1700000000, owned_by: "anthropic" }));
    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify({ object: "list", data: models }));
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
    const token = await getAccessToken();

    if (isOpenAI) {
      // ─── OpenAI 兼容路径 ───
      const anthropicBody = openaiToAnthropic(body);
      const requestModel = anthropicBody.model;
      applyDefaultThinking(anthropicBody);
      processAnthropicBody(anthropicBody);

      const proxyRes = await proxyToAnthropic(token, "/v1/messages", anthropicBody);
      log(`<= ${proxyRes.statusCode} ${req.url}`);

      if (proxyRes.statusCode === 401) {
        cachedOAuth = null;
        log("Got 401, will refresh token on next request");
      }

      if (proxyRes.statusCode !== 200) {
        let errData = "";
        for await (const chunk of proxyRes) errData += chunk;
        return sendOpenaiError(res, proxyRes.statusCode, errData);
      }

      if (body.stream) {
        res.writeHead(200, {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
        });

        let buffer = "";
        proxyRes.on("data", (chunk) => {
          buffer += chunk.toString();
          const lines = buffer.split("\n");
          buffer = lines.pop();
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (raw === "[DONE]") continue;
            try {
              const event = JSON.parse(raw);
              const converted = anthropicStreamEventToOpenai(event, requestModel);
              if (converted) {
                res.write(`data: ${JSON.stringify(converted)}\n\n`);
              }
            } catch {}
          }
        });
        proxyRes.on("end", () => {
          res.write("data: [DONE]\n\n");
          res.end();
        });
        proxyRes.on("error", () => res.end());
      } else {
        let data = "";
        for await (const chunk of proxyRes) data += chunk;
        const anthropicResp = JSON.parse(data);
        const openaiResp = anthropicToOpenai(anthropicResp, requestModel, false);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(openaiResp));
      }
    } else {
      // ─── Anthropic 原生路径 ───
      processAnthropicBody(body);
      const proxyRes = await proxyToAnthropic(token, req.url, body);
      log(`<= ${proxyRes.statusCode} ${req.url}`);

      if (proxyRes.statusCode === 401) {
        cachedOAuth = null;
        log("Got 401, will refresh token on next request");
      }

      const responseHeaders = { ...proxyRes.headers, "access-control-allow-origin": "*" };
      res.writeHead(proxyRes.statusCode, responseHeaders);
      proxyRes.pipe(res);
    }
  } catch (e) {
    log(`Error: ${e.message}`);
    isOpenAI ? sendOpenaiError(res, 500, e.message) : sendError(res, 500, e.message);
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
});
