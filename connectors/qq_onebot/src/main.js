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

async function callGatewayChat(windowId, userContent, options = {}) {
  const base = gatewayBaseUrl();
  const chatPath = envStr("GATEWAY_CHAT_PATH", "/v1/chat/completions");
  const url = base + (chatPath.startsWith("/") ? chatPath : `/${chatPath}`);
  const configuredModel = envStr("GATEWAY_MODEL", "");
  const body = {
    messages: [
      { role: "user", content: userContent },
    ],
    stream: false,
  };
  const model = configuredModel || (await fetchGatewayFirstModel(base));
  if (model) body.model = model;
  const headers = {
    "Content-Type": "application/json",
    "X-Window-Id": String(windowId || "").trim(),
    "X-Reply-Channel": String(options.replyChannel || "qq").trim() || "qq",
  };
  if (envBool("GATEWAY_TG_USER_INPUT", true)) headers["X-TG-User-Input"] = "1";
  if (options.skipDynamicMemory) headers["X-Skip-Dynamic-Memory"] = "1";
  if (options.skipPostArchiveDynamicMemory) headers["X-Skip-Post-Archive-Dynamic-Memory"] = "1";
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
    const status = String(data.status || "").trim();
    const message = String(data.message || data.wording || data.msg || "").trim();
    const parts = [`OneBot ${action}`, `retcode=${data.retcode}`];
    if (status) parts.push(`status=${status}`);
    if (message) parts.push(`message=${message}`);
    throw new Error(parts.join(" "));
  }
  return data || {};
}

async function sendQqText(userId, text) {
  return onebotApi("send_private_msg", { user_id: Number(userId), message: String(text || "") });
}

async function sendQqGroupText(groupId, text) {
  return onebotApi("send_group_msg", { group_id: Number(groupId), message: String(text || "") });
}


async function sendQqImage(userId, imageUrl) {
  return onebotApi("send_private_msg", {
    user_id: Number(userId),
    message: [{ type: "image", data: { file: String(imageUrl || "").trim() } }],
  });
}

async function sendQqGroupImage(groupId, imageUrl) {
  return onebotApi("send_group_msg", {
    group_id: Number(groupId),
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

async function sendQqGroupRecord(groupId, audioBytes) {
  const b64 = Buffer.from(audioBytes || []).toString("base64");
  return onebotApi("send_group_msg", {
    group_id: Number(groupId),
    message: [{ type: "record", data: { file: `base64://${b64}` } }],
  });
}

const pending = new Map();
const dedupe = new Set();
const dedupeMax = 2000;
const recentInboundByUser = new Map();
const recentGroupMessages = new Map();
const inboundDedupeWindowMs = Math.max(2000, envInt("QQ_INBOUND_DEDUPE_WINDOW_MS", 12000));
const groupHistoryContextLimit = Math.max(1, envInt("QQ_GROUP_CONTEXT_MESSAGES", 20));
const groupHistoryKeepLimit = 50;
const configuredBotUserId = Number(envStr("QQ_BOT_USER_ID", "3195570280") || 0);
let resolvedBotUserId = configuredBotUserId;
const logInboundEvents = envBool("QQ_INBOUND_EVENT_LOG", true);
const logGroupEvents = envBool("QQ_GROUP_EVENT_LOG", true);
const ownerQqUserId = Number(envStr("QQ_OWNER_USER_ID", "1336091712") || 0);
const ownerQqDisplayName = envStr("QQ_OWNER_DISPLAY_NAME", "辛玥");

async function sendQqPrivateRichReply(userId, reply, options = {}) {
  const outChunkChars = Math.max(20, envInt("QQ_OUTPUT_CHUNK_CHARS", 200));
  const maxReplyTotalChars = Math.max(0, envInt("QQ_MAX_REPLY_TOTAL_CHARS", 0));
  const sendDelayMs = Math.max(0, envInt("QQ_OUTPUT_SEND_DELAY_MS", 400));
  const shouldSplit = options.split !== false && options.singleMessage !== true;
  const strict = options.strict === true;
  const { cleanText: noVoiceText, voiceText } = extractVoiceTag(reply);
  const pcmdHandled = await processPcmdViaGateway(noVoiceText);
  const { cleanText: replyClean, tag: stickerTag } = await extractStickerTag(pcmdHandled.visibleText);
  const stickerUrl = await resolveStickerUrl(stickerTag);
  const chunks = shouldSplit ? splitReplyByNewlineAndLen(replyClean, outChunkChars, maxReplyTotalChars) : [replyClean].filter(Boolean);
  let sentAny = false;
  for (const part of chunks) {
    try {
      await sendQqText(userId, part);
      sentAny = true;
    } catch (e) {
      console.log(`[qq-onebot] 发消息失败 user=${userId}: ${String(e?.message || e)}`);
      if (strict) throw e;
      break;
    }
    if (sendDelayMs > 0) await sleep(sendDelayMs);
  }
  if (stickerUrl) {
    try {
      await sendQqImage(userId, stickerUrl);
      sentAny = true;
      if (sendDelayMs > 0) await sleep(sendDelayMs);
    } catch (e) {
      console.log(`[qq-onebot] 发送表情失败 user=${userId}: ${String(e?.message || e)}`);
      if (strict && !sentAny) throw e;
    }
  }
  if (voiceText) {
    try {
      const audioBytes = await callGatewayTts(voiceText);
      if (audioBytes?.length) {
        await sendQqRecord(userId, audioBytes);
        sentAny = true;
      }
    } catch (e) {
      console.log(`[qq-onebot] 发送语音失败 user=${userId}: ${String(e?.message || e)}`);
      if (strict && !sentAny) throw e;
    }
  }
  return sentAny;
}

async function flushUser(userId) {
  const it = pending.get(userId);
  if (!it) return;
  if (it.timer) {
    clearTimeout(it.timer);
    it.timer = null;
  }
  const merged = mergeUserContents(it.parts || []);
  // 无内容可发：直接清理
  if (!merged) {
    pending.delete(userId);
    return;
  }
  try {
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
    try {
      await sendQqPrivateRichReply(userId, reply);
    } catch (e) {
      console.log(`[qq-onebot] 发送回复失败：${String(e?.message || e)}`);
    }
  } finally {
    // 本轮 flush 结束后，无论成功与否，都视为这一轮已经消费完成
    pending.delete(userId);
  }
}

function scheduleUser(userId, text) {
  const idleSeconds = Math.max(1, envInt("QQ_INPUT_IDLE_SECONDS", 15));
  const cur = pending.get(userId) || { parts: [], timer: null };
  cur.parts.push(text);
  if (cur.timer) clearTimeout(cur.timer);
  cur.timer = setTimeout(() => flushUser(userId), idleSeconds * 1000);
  pending.set(userId, cur);
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

function isGroupMessageEvent(j) {
  return (
    String(j?.post_type || "") === "message" &&
    String(j?.message_type || "") === "group"
  );
}

function eventSelfId(j) {
  return String(j?.self_id || resolvedBotUserId || configuredBotUserId || "").trim();
}

function eventSummary(j) {
  return [
    `post_type=${String(j?.post_type || "-")}`,
    `message_type=${String(j?.message_type || "-")}`,
    `sub_type=${String(j?.sub_type || "-")}`,
    `self_id=${eventSelfId(j) || "unknown"}`,
    `user=${Number(j?.user_id || j?.sender?.user_id || 0) || "-"}`,
    `group=${Number(j?.group_id || 0) || "-"}`,
    `message_id=${String(j?.message_id || "-")}`,
  ].join(" ");
}

function eventPreview(j) {
  const raw = String(j?.raw_message || "").trim();
  if (raw) return raw.length > 120 ? `${raw.slice(0, 120)}...` : raw;
  return userContentPreview(extractUserContentFromMessage(j?.message || ""), 120) || "-";
}

function logIncomingEvent(j) {
  if (!logInboundEvents) return;
  console.log(`[qq-onebot] event ${eventSummary(j)} preview=${eventPreview(j)}`);
}

function logIgnoredEvent(j, reason) {
  if (!logInboundEvents) return;
  console.log(`[qq-onebot] ignored event reason=${reason} ${eventSummary(j)} preview=${eventPreview(j)}`);
}

async function resolveBotUserId() {
  if (resolvedBotUserId) return resolvedBotUserId;
  try {
    const data = await onebotApi("get_login_info", {});
    const userId = Number(data?.data?.user_id || data?.user_id || 0);
    if (userId) {
      resolvedBotUserId = userId;
      console.log(`[qq-onebot] resolved bot user_id=${userId}`);
      return userId;
    }
    console.log("[qq-onebot] get_login_info 未返回 user_id；群聊 @ 判断将依赖事件 self_id 或 QQ_BOT_USER_ID");
  } catch (e) {
    console.log(`[qq-onebot] get_login_info 失败；群聊 @ 判断将依赖事件 self_id 或 QQ_BOT_USER_ID：${String(e?.message || e)}`);
  }
  return 0;
}

function isSelfMessage(j) {
  const selfId = Number(eventSelfId(j) || 0);
  const senderId = Number(j?.sender?.user_id || j?.user_id || 0);
  return j?.sub_type === "self" || (!!selfId && senderId === selfId);
}

function senderLabel(j) {
  const userId = Number(j?.user_id || j?.sender?.user_id || 0);
  const sender = j?.sender && typeof j.sender === "object" ? j.sender : {};
  const card = String(sender.card || "").trim();
  const nickname = String(sender.nickname || "").trim();
  const rawName = card || nickname || (userId ? `QQ${userId}` : "群成员");
  const isOwner = !!ownerQqUserId && userId === ownerQqUserId;
  const name = isOwner ? ownerQqDisplayName : rawName;
  return { userId, name, rawName, isOwner };
}

function groupSpeakerPrefix(name, userId, isOwner = false) {
  const id = Number(userId || 0);
  const base = `${String(name || "群成员").trim() || "群成员"}${id ? `(${id})` : ""}`;
  return isOwner ? `${base}[当前用户/辛玥]` : base;
}

function contentTextForGroupContext(content, limit = 300) {
  const preview = userContentPreview(content, limit).trim();
  return preview || "[非文本消息]";
}

function getGroupHistory(groupId) {
  return recentGroupMessages.get(String(groupId || "")) || [];
}

function rememberGroupMessage(j, content) {
  const groupId = Number(j?.group_id || 0);
  if (!groupId) return;
  const { userId, name, isOwner } = senderLabel(j);
  const text = contentTextForGroupContext(content);
  const rows = getGroupHistory(groupId);
  rows.push({
    userId,
    name,
    isOwner,
    text,
    messageId: String(j?.message_id || ""),
    ts: Number(j?.time || 0),
  });
  if (rows.length > groupHistoryKeepLimit) rows.splice(0, rows.length - groupHistoryKeepLimit);
  recentGroupMessages.set(String(groupId), rows);
}

function messageMentionsSelf(j) {
  const selfId = eventSelfId(j);
  if (!selfId) return false;
  return groupAtTargets(j).some((qq) => qq === selfId);
}

function cqAtTargets(raw) {
  const out = [];
  for (const m of String(raw || "").matchAll(/\[CQ:at,([^\]]*)\]/g)) {
    const params = String(m?.[1] || "").split(",");
    for (const part of params) {
      const [key, ...rest] = String(part || "").split("=");
      if (String(key || "").trim() !== "qq") continue;
      const qq = rest.join("=").trim();
      if (qq) out.push(qq);
    }
  }
  return out;
}

function stripSelfAtFromRaw(raw, selfId) {
  const id = String(selfId || "").trim();
  if (!id) return String(raw || "").trim();
  return String(raw || "")
    .replace(/\[CQ:at,([^\]]*)\]/g, (whole, paramText) => (
      cqAtTargets(`[CQ:at,${paramText}]`).includes(id) ? "" : whole
    ))
    .trim();
}

function groupAtTargets(j) {
  const out = [];
  const msg = j?.message;
  if (Array.isArray(msg)) {
    for (const seg of msg) {
      if (!seg || typeof seg !== "object") continue;
      if (String(seg.type || "") !== "at") continue;
      const qq = String(seg.data?.qq || "").trim();
      if (qq) out.push(qq);
    }
  }
  for (const qq of cqAtTargets(j?.raw_message || "")) {
    if (qq && !out.includes(qq)) out.push(qq);
  }
  return out;
}

function contentWithoutSelfAt(j) {
  const selfId = eventSelfId(j);
  const msg = j?.message;
  if (Array.isArray(msg)) {
    const filtered = msg.filter((seg) => {
      if (!seg || typeof seg !== "object") return false;
      if (String(seg.type || "") !== "at") return true;
      return String(seg.data?.qq || "").trim() !== selfId;
    });
    return extractUserContentFromMessage(filtered);
  }
  const raw = String(j?.raw_message || "");
  const clean = stripSelfAtFromRaw(raw, selfId);
  return extractUserContentFromMessage(clean);
}

function buildGroupGatewayContent(j, previousRows, currentContent) {
  const groupId = Number(j?.group_id || 0);
  const { userId, name, isOwner } = senderLabel(j);
  const lines = (previousRows || []).slice(-groupHistoryContextLimit).map((row) => {
    const prefix = groupSpeakerPrefix(row?.name || "群成员", row?.userId, !!row?.isOwner);
    return `${prefix}：${String(row?.text || "").trim() || "[非文本消息]"}`;
  });
  const currentText = contentTextForGroupContext(currentContent);
  const currentPrefix = groupSpeakerPrefix(name, userId, isOwner);
  const headerText = [
    "【QQ 群聊】",
    `群号：${groupId}`,
    ownerQqUserId ? `身份标记：QQ ${ownerQqUserId} 是辛玥/当前用户；其他人是群友。` : "",
    `当前发言人：${currentPrefix}`,
    "你只有在被 @ 时才回复。下面是本次 @ 前的最近群聊消息，用作公开上下文：",
    lines.length ? lines.join("\n") : "（前面没有可用群聊消息）",
    "",
    "当前 @ 你的消息：",
    `${currentPrefix}：${currentText}`,
  ].filter(Boolean).join("\n");
  const parts = normalizeUserContentToParts(currentContent);
  const imageParts = parts.filter((p) => p?.type === "image_url");
  if (!imageParts.length) return headerText;
  return [{ type: "text", text: headerText }, ...imageParts];
}

async function sendQqReplyToGroup(groupId, reply) {
  const outChunkChars = Math.max(20, envInt("QQ_OUTPUT_CHUNK_CHARS", 200));
  const maxReplyTotalChars = Math.max(0, envInt("QQ_MAX_REPLY_TOTAL_CHARS", 0));
  const sendDelayMs = Math.max(0, envInt("QQ_OUTPUT_SEND_DELAY_MS", 400));
  const { cleanText: noVoiceText, voiceText } = extractVoiceTag(reply);
  const pcmdHandled = await processPcmdViaGateway(noVoiceText);
  const { cleanText: replyClean, tag: stickerTag } = await extractStickerTag(pcmdHandled.visibleText);
  const stickerUrl = await resolveStickerUrl(stickerTag);
  const chunks = splitReplyByNewlineAndLen(replyClean, outChunkChars, maxReplyTotalChars);
  for (const part of chunks) {
    await sendQqGroupText(groupId, part);
    if (sendDelayMs > 0) await sleep(sendDelayMs);
  }
  if (stickerUrl) {
    await sendQqGroupImage(groupId, stickerUrl);
    if (sendDelayMs > 0) await sleep(sendDelayMs);
  }
  if (voiceText) {
    const audioBytes = await callGatewayTts(voiceText);
    if (audioBytes?.length) await sendQqGroupRecord(groupId, audioBytes);
  }
}

async function handleGroupEvent(j) {
  const groupId = Number(j?.group_id || 0);
  if (!groupId) return;
  const content = contentWithoutSelfAt(j);
  const atTargets = groupAtTargets(j);
  if (logGroupEvents) {
    console.log(`[qq-onebot] group event group=${groupId} user=${Number(j?.user_id || 0)} self_id=${eventSelfId(j) || "unknown"} at=${atTargets.join(",") || "-"} content=${userContentPreview(content, 80) || "-"}`);
  }
  const previousRows = getGroupHistory(groupId).slice(-groupHistoryContextLimit);
  rememberGroupMessage(j, content || extractUserContentFromMessage(j?.message || j?.raw_message || ""));
  if (!messageMentionsSelf(j)) {
    if (atTargets.length) {
      console.log(`[qq-onebot] 群聊 @ 未命中本机器人 group=${groupId} self_id=${eventSelfId(j) || "unknown"} at=${atTargets.join(",")}`);
    }
    return;
  }
  const now = Date.now();
  const scopeKey = `g:${groupId}`;
  const fp = `${Number(j?.user_id || 0)}|${userContentPreview(content, 200)}|${String(j?.raw_message || "")}`.slice(0, 800);
  const recent = recentInboundByUser.get(scopeKey);
  if (recent && recent.fp === fp && now - Number(recent.ts || 0) <= inboundDedupeWindowMs) return;
  recentInboundByUser.set(scopeKey, { fp, ts: now });
  if (recentInboundByUser.size > dedupeMax) recentInboundByUser.clear();
  const dedupeKey = `${scopeKey}:${String(j?.message_id || "")}:${userContentPreview(content, 200)}`;
  if (dedupe.has(dedupeKey)) return;
  dedupe.add(dedupeKey);
  if (dedupe.size > dedupeMax) dedupe.clear();

  const windowId = resolveSharedWindowId();
  const gatewayContent = buildGroupGatewayContent(j, previousRows, content || "（只 @ 了你，没有附加文字）");
  console.log(`[qq-onebot] inbound group=${groupId} window_id=${windowId} content=${userContentPreview(content, 80)}`);
  let reply = "";
  try {
    reply = await callGatewayChat(windowId, gatewayContent, {
      replyChannel: "qq",
      skipDynamicMemory: true,
      skipPostArchiveDynamicMemory: true,
    });
  } catch (e) {
    console.log(`[qq-onebot] 群聊调网关失败 group=${groupId}：${String(e?.message || e)}`);
    return;
  }
  try {
    await sendQqReplyToGroup(groupId, reply);
  } catch (e) {
    console.log(`[qq-onebot] 群聊发送失败 group=${groupId}：${String(e?.message || e)}`);
  }
}

async function handleEvent(j) {
  // 过滤 self-message：NapCatQQ reportSelfMessage=true 时 bot 自己发的消息也会推回来
  if (isSelfMessage(j)) {
    logIgnoredEvent(j, "self_message");
    return;
  }
  if (isGroupMessageEvent(j)) {
    await handleGroupEvent(j);
    return;
  }
  if (!isPrivateMessageEvent(j)) {
    logIgnoredEvent(j, "unsupported_event");
    return;
  }
  const userId = Number(j?.user_id || 0);
  if (!userId) {
    logIgnoredEvent(j, "missing_user_id");
    return;
  }
  const content = extractUserContentFromMessage(j?.message || j?.raw_message || "");
  if (!content) {
    logIgnoredEvent(j, "empty_content");
    return;
  }
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
  await resolveBotUserId();
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
        try {
          const sent = await sendQqPrivateRichReply(targetUserId, text, {
            split: body?.split !== false,
            singleMessage: body?.single_message === true,
            strict: true,
          });
          if (!sent) {
            res.writeHead(400, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ ok: false, error: "empty_after_parse" }));
            return;
          }
        } catch (e) {
          console.log(`[qq-onebot] /push 发送失败：${String(e?.message || e)}`);
          res.writeHead(500, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ ok: false, error: String(e?.message || e) }));
          return;
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
      logIncomingEvent(body);
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
