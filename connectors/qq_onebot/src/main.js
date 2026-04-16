import http from "node:http";
import path from "node:path";
import process from "node:process";
import dotenv from "dotenv";
import { fileURLToPath } from "node:url";

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "../../..");
dotenv.config({ path: path.join(REPO_ROOT, ".env"), override: false });

function envStr(name, fallback = "") {
  return (process.env[name] || fallback || "").trim();
}

function envInt(name, fallback) {
  const raw = envStr(name, "");
  if (!raw) return fallback;
  const n = Number(raw);
  return Number.isFinite(n) ? n : fallback;
}

function envBool(name, fallback = false) {
  const raw = envStr(name, "");
  if (!raw) return fallback;
  return ["1", "true", "yes", "y", "on"].includes(raw.toLowerCase());
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function gatewayBaseUrl() {
  return envStr("GATEWAY_BASE_URL", "http://127.0.0.1:5000").replace(/\/+$/, "");
}

function absolutizeGatewayUrl(raw) {
  const s = String(raw || "").trim();
  if (!s) return "";
  if (/^https?:\/\//i.test(s)) return s;
  return `${gatewayBaseUrl()}${s.startsWith("/") ? s : `/${s}`}`;
}

function resolveSharedWindowId() {
  const tgUserId = envStr("TELEGRAM_PROACTIVE_TARGET_USER_ID", "");
  if (!tgUserId) {
    throw new Error("缺少 TELEGRAM_PROACTIVE_TARGET_USER_ID，无法把 QQ 入口并到 TG 上下文");
  }
  return `tg_${tgUserId}`;
}

function buildQqStyleSystem() {
  const tagsLine = getStickerTagsLineForSystemPrompt();
  return [
    "请遵守以下输出格式要求：",
    "0) 情绪明显时可在整条回复末尾加一个英文标签（方括号）；每条最多一个，平淡时不加。",
    `   ${tagsLine}`,
    "1) 只输出给她看的正文，不要输出“（脑内OS：）”或任何内心独白部分。",
    "2) 不要输出分割线（例如 ---、———、***）。",
    "3) 不要使用 Markdown 强调符号 * 或 **。",
    "4) 不要输出“(表情包:xxx)”这类占位符；可以直接使用 emoji。",
    "5) 允许自然分段，但不要为了格式刻意堆很多空行。",
    "6) 你可以在想发语音的时候发语音：把想让她听到的那句话用 <voice>...</voice> 包起来（不要在里面写分割线或 *）。",
    "   - 你可以同时输出文字正文；Bot 会额外发送一条语音。",
    "   - 如果你不想发语音，就不要输出 <voice> 标签。",
    "7) 如需控制电脑，可在整条回复里最多追加一个 [PCMD:...] 标签；不确定就不要加。",
    "   - 仅允许这些指令：",
    "     [PCMD:lock] 锁屏",
    "     [PCMD:shutdown] 关机（默认 60 秒后）",
    "     [PCMD:shutdown:秒数] 定时关机（0-86400）",
    "     [PCMD:restart] 重启（默认 60 秒后）",
    "     [PCMD:restart:秒数] 定时重启（0-86400）",
    "     [PCMD:sleep] 睡眠",
    "     [PCMD:mute] 静音",
    "     [PCMD:volume:0-100] 设置音量（整数）",
    "     [PCMD:notify:标题:内容] 电脑通知",
    "     [PCMD:open:notepad] 打开记事本",
    "     [PCMD:open:notepad:要写入的内容] 打开记事本并预填内容",
    "     [PCMD:open:chrome] 打开 Chrome",
    "     [PCMD:open:vscode] 打开 VS Code",
    "     [PCMD:open:wechat] 打开微信",
    "     [PCMD:open:notion] 打开 Notion",
    "     [PCMD:url:https://... ] 打开网页（仅 https）",
    "     [PCMD:media:play] 播放/暂停媒体",
    "   - 严禁输出未列出的 PCMD；若不确定，请不要输出 PCMD。",
    "   - 仅在确有必要时输出；平时不要输出。",
  ].join("\n");
}

function extractUserContentFromMessage(message) {
  if (typeof message === "string") {
    const t = String(message || "").trim();
    return t || "";
  }
  if (!Array.isArray(message)) return "";
  const parts = [];
  for (const seg of message) {
    if (!seg || typeof seg !== "object") continue;
    const type = String(seg.type || "").trim();
    if (type === "text") {
      const text = String(seg.data?.text || "").trim();
      if (text) parts.push({ type: "text", text });
      continue;
    }
    if (type === "image") {
      const url = String(seg.data?.url || seg.data?.file || "").trim();
      if (/^https?:\/\//i.test(url)) {
        parts.push({ type: "image_url", image_url: { url } });
      }
    }
  }
  if (!parts.length) return "";
  const hasText = parts.some((p) => p?.type === "text" && String(p.text || "").trim());
  if (!hasText) return [{ type: "text", text: "[图片]" }, ...parts];
  return parts.length === 1 && parts[0]?.type === "text" ? String(parts[0].text || "") : parts;
}

function normalizeUserContentToParts(content) {
  if (typeof content === "string") {
    const t = String(content || "").trim();
    return t ? [{ type: "text", text: t }] : [];
  }
  if (Array.isArray(content)) {
    return content.filter((p) => p && typeof p === "object" && p.type);
  }
  return [];
}

function mergeUserContents(contents) {
  if (!contents.length) return "";
  if (contents.every((x) => typeof x === "string")) {
    return contents.map((x) => String(x || "").trim()).filter(Boolean).join("\n").trim();
  }
  const parts = [];
  for (const c of contents) {
    parts.push(...normalizeUserContentToParts(c));
  }
  return parts;
}

function userContentPreview(content, limit = 80) {
  if (typeof content === "string") {
    const t = String(content || "").trim();
    return t.length > limit ? `${t.slice(0, limit)}...` : t;
  }
  if (Array.isArray(content)) {
    const flat = content
      .map((p) => (p?.type === "image_url" ? "[image]" : String(p?.text || "").trim()))
      .filter(Boolean)
      .join(" ");
    return flat.length > limit ? `${flat.slice(0, limit)}...` : flat;
  }
  return "";
}

function splitReplyByNewlineAndLen(text, chunkChars, maxTotalChars) {
  const raw = String(text || "").trim();
  if (!raw) return [];
  const limit = Math.max(20, Number(chunkChars || 100));
  const maxTotal = Math.max(0, Number(maxTotalChars || 0));
  const minStandaloneChars = 2;
  const clipped = maxTotal > 0 && raw.length > maxTotal ? raw.slice(0, maxTotal) : raw;
  const lines = clipped.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  const src = lines.length ? lines : [clipped];
  const out = [];
  for (const line of src) {
    const one = String(line || "").trim();
    if (!one) continue;
    if (one.length <= limit) {
      if (one.length < minStandaloneChars && out.length > 0) {
        const prev = out[out.length - 1];
        if ((prev + "\n" + one).length <= limit) {
          out[out.length - 1] = prev + "\n" + one;
          continue;
        }
      }
      out.push(one);
      continue;
    }
    for (let i = 0; i < one.length; i += limit) out.push(one.slice(i, i + limit));
  }
  return out.filter(Boolean);
}

async function fetchGatewayFirstModel(base) {
  try {
    const modelsUrl = `${base}/v1/models`;
    const r = await fetch(modelsUrl, { method: "GET", headers: { "Content-Type": "application/json" } });
    const text = await r.text();
    if (!r.ok) return "";
    const data = text ? JSON.parse(text) : null;
    const arr = Array.isArray(data?.data) ? data.data : [];
    if (!arr.length) return "";
    const first = arr[0];
    if (typeof first === "string") return first.trim();
    return String(first?.id || "").trim();
  } catch {
    return "";
  }
}

async function callGatewayChat(windowId, userContent) {
  const base = gatewayBaseUrl();
  const chatPath = envStr("GATEWAY_CHAT_PATH", "/v1/chat/completions");
  const url = base + (chatPath.startsWith("/") ? chatPath : `/${chatPath}`);
  const configuredModel = envStr("GATEWAY_MODEL", "");
  const body = {
    messages: [
      { role: "system", content: buildQqStyleSystem() },
      { role: "user", content: userContent },
    ],
    stream: false,
  };
  const model = configuredModel || (await fetchGatewayFirstModel(base));
  if (model) body.model = model;
  const headers = {
    "Content-Type": "application/json",
    "X-Window-Id": String(windowId || "").trim(),
  };
  if (envBool("GATEWAY_TG_USER_INPUT", true)) headers["X-TG-User-Input"] = "1";
  const r = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
  const text = await r.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!r.ok) throw new Error(`网关返回 ${r.status}: ${(text || "").slice(0, 200)}`);
  return String(data?.choices?.[0]?.message?.content || "").trim();
}

async function callGatewayTts(text) {
  const base = gatewayBaseUrl();
  const ttsPath = envStr("GATEWAY_TTS_PREVIEW_PATH", "/miniapp-api/tts-preview");
  const url = base + (ttsPath.startsWith("/") ? ttsPath : `/${ttsPath}`);
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: String(text || "") }),
  });
  const raw = await r.text();
  let data = null;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    data = null;
  }
  if (!r.ok) throw new Error(`TTS 返回 ${r.status}: ${(raw || "").slice(0, 200)}`);
  const audioB64 = String(data?.audio_b64 || "").trim();
  if (!audioB64) return null;
  return Buffer.from(audioB64, "base64");
}

function extractVoiceTag(text) {
  const raw = String(text || "");
  const m = raw.match(/<voice>([\s\S]*?)<\/voice>/i);
  if (!m) return { cleanText: raw.trim(), voiceText: "" };
  const voiceText = String(m[1] || "").trim();
  const cleanText = raw.replace(/<voice>[\s\S]*?<\/voice>/gi, "").trim();
  return { cleanText, voiceText };
}

let _STICKER_TAGS_CACHE_AT = 0;
let _STICKER_TAGS_CACHE = [];
let _STICKER_REGEX_CACHE_AT = 0;
let _STICKER_REGEX_CACHE = /(?!x)x/;
const _STICKER_CACHE_TTL_MS = 45_000;

async function fetchStickerTags() {
  const now = Date.now();
  if (now - _STICKER_TAGS_CACHE_AT < _STICKER_CACHE_TTL_MS && _STICKER_TAGS_CACHE.length) {
    return _STICKER_TAGS_CACHE;
  }
  try {
    const r = await fetch(`${gatewayBaseUrl()}/miniapp-api/stickers/tags-public`);
    const text = await r.text();
    if (!r.ok) return _STICKER_TAGS_CACHE;
    const data = text ? JSON.parse(text) : null;
    const rows = Array.isArray(data?.tags) ? data.tags : [];
    const keys = rows.map((it) => String(it || "").trim().toLowerCase()).filter(Boolean);
    _STICKER_TAGS_CACHE_AT = now;
    _STICKER_TAGS_CACHE = [...new Set(keys)];
    return _STICKER_TAGS_CACHE;
  } catch {
    return _STICKER_TAGS_CACHE;
  }
}

function getStickerTagsLineForSystemPrompt() {
  if (_STICKER_TAGS_CACHE.length) {
    return `当前全部可用英文代号（与 MiniApp/R2 一致，新增分类也会出现在此列表）：${_STICKER_TAGS_CACHE.map((k) => `[${k}]`).join(" ")}`;
  }
  return "表情包英文代号以 MiniApp 配置为准；句末可加小写 [tag]。";
}

async function refreshStickerRegex() {
  const now = Date.now();
  if (now - _STICKER_REGEX_CACHE_AT < _STICKER_CACHE_TTL_MS) {
    return _STICKER_REGEX_CACHE;
  }
  const keys = (await fetchStickerTags()).slice().sort((a, b) => b.length - a.length);
  _STICKER_REGEX_CACHE = keys.length
    ? new RegExp(`\\[(${keys.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})\\]`, "i")
    : /(?!x)x/;
  _STICKER_REGEX_CACHE_AT = now;
  return _STICKER_REGEX_CACHE;
}

async function extractStickerTag(text) {
  const raw = String(text || "").trim();
  if (!raw) return { cleanText: "", tag: "" };
  const pat = await refreshStickerRegex();
  const m = pat.exec(raw);
  if (!m) return { cleanText: raw, tag: "" };
  const tag = String(m[1] || "").trim().toLowerCase();
  if (!tag) return { cleanText: raw, tag: "" };
  const cleanText = (raw.slice(0, m.index) + raw.slice(m.index + m[0].length)).replace(/\n{3,}/g, "\n\n").trim();
  return { cleanText, tag };
}

async function resolveStickerUrl(tag) {
  const t = String(tag || "").trim().toLowerCase();
  if (!t) return "";
  try {
    const r = await fetch(`${gatewayBaseUrl()}/miniapp-api/stickers/resolve?tag=${encodeURIComponent(t)}`);
    const text = await r.text();
    if (!r.ok) return "";
    const data = text ? JSON.parse(text) : null;
    const url = String(data?.url || "").trim();
    const key = String(data?.key || "").trim();
    // 若 URL 是 R2 私有存储地址（需要鉴权），NapCatQQ 无法访问，
    // 改走网关 raw-public 代理（与 connector 同机器，可直连）
    if (url && !/r2\.cloudflarestorage\.com/.test(url)) {
      return absolutizeGatewayUrl(url);
    }
    if (key) {
      return `${gatewayBaseUrl()}/miniapp-api/stickers/raw-public?key=${encodeURIComponent(key)}`;
    }
    return "";
  } catch {
    return "";
  }
}

async function processPcmdViaGateway(text) {
  const token = envStr("PC_COMMAND_TOKEN", "");
  if (!token) return { visibleText: String(text || ""), queued: false };
  try {
    const r = await fetch(`${gatewayBaseUrl()}/api/pc_command/assistant`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-PC-Token": token,
      },
      body: JSON.stringify({ text: String(text || "") }),
    });
    const raw = await r.text();
    const data = raw ? JSON.parse(raw) : null;
    if (!r.ok || !data?.ok) {
      return { visibleText: String(text || ""), queued: false };
    }
    return { visibleText: String(data?.visible_text || ""), queued: Boolean(data?.queued) };
  } catch {
    return { visibleText: String(text || ""), queued: false };
  }
}

async function onebotApi(action, params) {
  const base = envStr("QQ_ONEBOT_API_BASE", "http://127.0.0.1:3000").replace(/\/+$/, "");
  const token = envStr("QQ_ONEBOT_API_TOKEN", "");
  const url = `${base}/${String(action || "").replace(/^\/+/, "")}`;
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const r = await fetch(url, { method: "POST", headers, body: JSON.stringify(params || {}) });
  const text = await r.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!r.ok) throw new Error(`OneBot ${action} ${r.status}: ${(text || "").slice(0, 200)}`);
  if (data && Number(data.retcode || 0) !== 0) {
    throw new Error(`OneBot ${action} retcode=${data.retcode} msg=${data.msg || ""}`.trim());
  }
  return data || {};
}

async function sendQqText(userId, text) {
  return onebotApi("send_private_msg", { user_id: Number(userId), message: String(text || "") });
}


async function sendQqImage(userId, imageUrl) {
  return onebotApi("send_private_msg", {
    user_id: Number(userId),
    message: [{ type: "image", data: { file: String(imageUrl || "").trim() } }],
  });
}

async function sendQqRecord(userId, audioBytes) {
  const b64 = Buffer.from(audioBytes || []).toString("base64");
  return onebotApi("send_private_msg", {
    user_id: Number(userId),
    message: [{ type: "record", data: { file: `base64://${b64}` } }],
  });
}

const pending = new Map();
const dedupe = new Set();
const dedupeMax = 2000;
const inFlightUsers = new Set();
const recentInboundByUser = new Map();
const inboundDedupeWindowMs = Math.max(2000, envInt("QQ_INBOUND_DEDUPE_WINDOW_MS", 12000));

async function flushUser(userId) {
  if (inFlightUsers.has(userId)) {
    return;
  }
  const it = pending.get(userId);
  if (!it) return;
  inFlightUsers.add(userId);
  try {
    if (it.timer) {
      clearTimeout(it.timer);
      it.timer = null;
    }
    const merged = mergeUserContents(it.parts || []);
    if (!merged) {
      pending.delete(userId);
      return;
    }
    const windowId = resolveSharedWindowId();
    console.log(`[qq-onebot] flush user=${userId} window_id=${windowId} preview=${userContentPreview(merged)}`);
    let reply = "";
    try {
      reply = await callGatewayChat(windowId, merged);
    } catch (e) {
      console.log(`[qq-onebot] 调网关失败：${String(e?.message || e)}`);
      pending.delete(userId);
      return;
    }
    const outChunkChars = Math.max(20, envInt("QQ_OUTPUT_CHUNK_CHARS", 200));
    const maxReplyTotalChars = Math.max(0, envInt("QQ_MAX_REPLY_TOTAL_CHARS", 0));
    const sendDelayMs = Math.max(0, envInt("QQ_OUTPUT_SEND_DELAY_MS", 400));
    const { cleanText: noVoiceText, voiceText } = extractVoiceTag(reply);
    const pcmdHandled = await processPcmdViaGateway(noVoiceText);
    const { cleanText: replyClean, tag: stickerTag } = await extractStickerTag(pcmdHandled.visibleText);
    const stickerUrl = await resolveStickerUrl(stickerTag);
    const chunks = splitReplyByNewlineAndLen(replyClean, outChunkChars, maxReplyTotalChars);
    for (const part of chunks) {
      try {
        await sendQqText(userId, part);
      } catch (e) {
        console.log(`[qq-onebot] 发消息失败：${String(e?.message || e)}`);
        break;
      }
      if (sendDelayMs > 0) await sleep(sendDelayMs);
    }
    if (stickerUrl) {
      try {
        await sendQqImage(userId, stickerUrl);
      } catch (e) {
        console.log(`[qq-onebot] 发表情包失败：${String(e?.message || e)}`);
      }
      if (sendDelayMs > 0) await sleep(sendDelayMs);
    }
    if (voiceText) {
      try {
        const audioBytes = await callGatewayTts(voiceText);
        if (audioBytes?.length) {
          await sendQqRecord(userId, audioBytes);
        }
      } catch (e) {
        console.log(`[qq-onebot] 发语音失败：${String(e?.message || e)}`);
      }
    }
    pending.delete(userId);
  } finally {
    inFlightUsers.delete(userId);
  }
}

function scheduleUser(userId, text) {
  const idleSeconds = Math.max(1, envInt("QQ_INPUT_IDLE_SECONDS", 15));
  const immediateChars = Math.max(20, envInt("QQ_INPUT_IMMEDIATE_CHARS", 200));
  const cur = pending.get(userId) || { parts: [], timer: null };
  cur.parts.push(text);
  if (cur.timer) clearTimeout(cur.timer);
  cur.timer = setTimeout(() => flushUser(userId), idleSeconds * 1000);
  pending.set(userId, cur);
  const mergedLen = userContentPreview(mergeUserContents(cur.parts || []), 10000).length;
  const currentLen = userContentPreview(text, 10000).length;
  if (currentLen >= immediateChars || mergedLen >= immediateChars) {
    void flushUser(userId);
  }
}

function verifyIncoming(req) {
  const expected = envStr("QQ_ONEBOT_ACCESS_TOKEN", "");
  if (!expected) return true;
  const auth = String(req.headers.authorization || "").trim();
  const xToken = String(req.headers["x-onebot-token"] || "").trim();
  return auth === `Bearer ${expected}` || xToken === expected;
}

function verifyPush(req) {
  const expected = envStr("QQ_PROACTIVE_PUSH_TOKEN", "");
  if (!expected) return true;
  const auth = String(req.headers.authorization || "").trim();
  return auth === `Bearer ${expected}`;
}

function isPrivateMessageEvent(j) {
  return (
    String(j?.post_type || "") === "message" &&
    String(j?.message_type || "") === "private"
  );
}

async function handleEvent(j) {
  if (!isPrivateMessageEvent(j)) return;
  // 过滤 self-message：NapCatQQ reportSelfMessage=true 时 bot 自己发的消息也会推回来
  if (j?.sub_type === "self" || Number(j?.sender?.user_id || 0) === Number(j?.self_id || 0)) return;
  const userId = Number(j?.user_id || 0);
  if (!userId) return;
  const content = extractUserContentFromMessage(j?.message || j?.raw_message || "");
  if (!content) return;
  const now = Date.now();
  const fp = `${userContentPreview(content, 200)}|${String(j?.raw_message || "")}`.slice(0, 600);
  const recent = recentInboundByUser.get(userId);
  if (recent && recent.fp === fp && now - Number(recent.ts || 0) <= inboundDedupeWindowMs) {
    return;
  }
  recentInboundByUser.set(userId, { fp, ts: now });
  if (recentInboundByUser.size > dedupeMax) recentInboundByUser.clear();
  const dedupeKey = `${userId}:${String(j?.message_id || "")}:${userContentPreview(content, 200)}`;
  if (dedupe.has(dedupeKey)) return;
  dedupe.add(dedupeKey);
  if (dedupe.size > dedupeMax) dedupe.clear();
  console.log(`[qq-onebot] inbound user=${userId} content=${userContentPreview(content, 80)}`);
  scheduleUser(userId, content);
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      try {
        const raw = Buffer.concat(chunks).toString("utf-8");
        resolve(raw ? JSON.parse(raw) : {});
      } catch (e) {
        reject(e);
      }
    });
    req.on("error", reject);
  });
}

async function main() {
  const port = Math.max(1, envInt("QQ_ONEBOT_PORT", 8092));
  const server = http.createServer(async (req, res) => {
    const url = String(req.url || "");
    try {
      if (req.method === "GET" && url === "/health") {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: true }));
        return;
      }
      // 主动推送端点：POST /push {"text":"..."}
      // 需配置 QQ_PROACTIVE_TARGET_USER_ID 和可选的 QQ_PROACTIVE_PUSH_TOKEN
      if (req.method === "POST" && url === "/push") {
        if (!verifyPush(req)) {
          res.writeHead(401, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ ok: false, error: "unauthorized" }));
          return;
        }
        const body = await readJsonBody(req);
        const text = String(body?.text || "").trim();
        const targetUserId = Number(envStr("QQ_PROACTIVE_TARGET_USER_ID", "0") || 0);
        if (!text) {
          res.writeHead(400, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ ok: false, error: "empty_text" }));
          return;
        }
        if (!targetUserId) {
          res.writeHead(503, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ ok: false, error: "QQ_PROACTIVE_TARGET_USER_ID not configured" }));
          return;
        }
        const outChunkChars = Math.max(20, envInt("QQ_OUTPUT_CHUNK_CHARS", 200));
        const sendDelayMs = Math.max(0, envInt("QQ_OUTPUT_SEND_DELAY_MS", 400));
        const chunks = splitReplyByNewlineAndLen(text, outChunkChars, 0);
        for (const part of chunks) {
          try {
            await sendQqText(targetUserId, part);
          } catch (e) {
            console.log(`[qq-onebot] /push 发消息失败：${String(e?.message || e)}`);
            res.writeHead(500, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ ok: false, error: String(e?.message || e) }));
            return;
          }
          if (sendDelayMs > 0) await sleep(sendDelayMs);
        }
        console.log(`[qq-onebot] /push 已发送 user=${targetUserId} preview=${text.slice(0, 80)}`);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: true }));
        return;
      }
      if (req.method !== "POST" || !url.startsWith("/onebot/events")) {
        res.writeHead(404, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: false, error: "not_found" }));
        return;
      }
      if (!verifyIncoming(req)) {
        res.writeHead(401, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: false, error: "unauthorized" }));
        return;
      }
      const body = await readJsonBody(req);
      void handleEvent(body);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
    } catch (e) {
      console.log(`[qq-onebot] webhook 异常：${String(e?.message || e)}`);
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: false, error: "internal_error" }));
    }
  });
  server.listen(port, "0.0.0.0", () => {
    console.log(`[qq-onebot] listening on :${port}`);
  });
}

main().catch((e) => {
  console.error(`[qq-onebot] fatal: ${String(e?.message || e)}`);
  process.exit(1);
});
