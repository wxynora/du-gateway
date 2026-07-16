import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { Blob } from "node:buffer";
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
    const t = stripRawReplySegments(message);
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

function isRecordSegmentType(type) {
  return ["record", "voice", "audio"].includes(String(type || "").trim().toLowerCase());
}

function cqDecode(value) {
  return String(value || "")
    .replace(/&#44;/g, ",")
    .replace(/&#91;/g, "[")
    .replace(/&#93;/g, "]")
    .replace(/&amp;/g, "&");
}

function parseCqParams(paramText) {
  const out = {};
  for (const part of String(paramText || "").split(",")) {
    const [key, ...rest] = String(part || "").split("=");
    const k = String(key || "").trim();
    if (!k) continue;
    out[k] = cqDecode(rest.join("=")).trim();
  }
  return out;
}

function parseRawRecordSegments(raw) {
  const out = [];
  for (const m of String(raw || "").matchAll(/\[CQ:(record|voice|audio),([^\]]*)\]/gi)) {
    out.push({ type: String(m?.[1] || "record").toLowerCase(), data: parseCqParams(m?.[2] || "") });
  }
  return out;
}

function parseRawReplyMessageIds(raw) {
  const out = [];
  for (const m of String(raw || "").matchAll(/\[CQ:(reply|quote),([^\]]*)\]/gi)) {
    const params = parseCqParams(m?.[2] || "");
    const id = String(params.id || params.message_id || "").trim();
    if (id && !out.includes(id)) out.push(id);
  }
  return out;
}

function stripRawReplySegments(raw) {
  return String(raw || "").replace(/\[CQ:(reply|quote),[^\]]*\]/gi, "").trim();
}

function imageUrlsFromContent(content) {
  const out = [];
  for (const part of normalizeUserContentToParts(content)) {
    if (!part || part.type !== "image_url") continue;
    const url = String(part.image_url?.url || "").trim();
    if (/^https?:\/\//i.test(url) && !out.includes(url)) out.push(url);
  }
  return out;
}

function rawImageUrls(raw) {
  const out = [];
  for (const m of String(raw || "").matchAll(/\[CQ:image,([^\]]*)\]/gi)) {
    const params = parseCqParams(m?.[1] || "");
    const url = String(params.url || params.file || "").trim();
    if (/^https?:\/\//i.test(url) && !out.includes(url)) out.push(url);
  }
  return out;
}

function filenameFromUrl(rawUrl, fallback = "voice") {
  try {
    const u = new URL(String(rawUrl || ""));
    const name = path.basename(decodeURIComponent(u.pathname || ""));
    return name || fallback;
  } catch {
    return fallback;
  }
}

function safeAudioFilename(raw, fallback = "voice") {
  const name = path.basename(String(raw || "").trim() || fallback).replace(/[^\w.\-]+/g, "_");
  return name || fallback;
}

function mimeTypeFromName(name, fallback = "application/octet-stream") {
  const clean = String(name || "").split("?")[0].split("#")[0];
  const ext = clean.includes(".") ? clean.split(".").pop().toLowerCase() : "";
  const byExt = {
    mp3: "audio/mpeg",
    m4a: "audio/mp4",
    mp4: "audio/mp4",
    wav: "audio/wav",
    wave: "audio/wav",
    ogg: "audio/ogg",
    opus: "audio/ogg",
    webm: "audio/webm",
    flac: "audio/flac",
    aac: "audio/aac",
    amr: "audio/amr",
    silk: "audio/silk",
    slk: "audio/silk",
  };
  return byExt[ext] || fallback || "application/octet-stream";
}

function assertAudioSize(bytes, label = "audio") {
  const max = Math.max(128 * 1024, envInt("QQ_INBOUND_VOICE_MAX_BYTES", 12 * 1024 * 1024));
  if (!bytes?.length) throw new Error(`${label} 为空`);
  if (bytes.length > max) throw new Error(`${label} 过大：${bytes.length} > ${max}`);
}

async function fetchAudioBytes(url) {
  const r = await fetch(url, { method: "GET" });
  const contentType = String(r.headers.get("content-type") || "").split(";", 1)[0].trim().toLowerCase();
  const raw = await r.arrayBuffer();
  const bytes = Buffer.from(raw);
  if (!r.ok) throw new Error(`下载语音失败 ${r.status}`);
  assertAudioSize(bytes, "remote audio");
  const filename = safeAudioFilename(filenameFromUrl(url, "voice"));
  return { bytes, filename, mimeType: contentType || mimeTypeFromName(filename) };
}

async function readAudioFile(filePath) {
  const rawPath = String(filePath || "").trim();
  const localPath = rawPath.startsWith("file://") ? fileURLToPath(rawPath) : rawPath;
  const bytes = await fs.readFile(localPath);
  assertAudioSize(bytes, "local audio");
  const filename = safeAudioFilename(localPath, "voice");
  return { bytes, filename, mimeType: mimeTypeFromName(filename) };
}

function decodeBase64Audio(raw, filename = "voice") {
  const b64 = String(raw || "").replace(/^base64:\/\//i, "").trim();
  const bytes = Buffer.from(b64, "base64");
  assertAudioSize(bytes, "base64 audio");
  const safeName = safeAudioFilename(filename, "voice");
  return { bytes, filename: safeName, mimeType: mimeTypeFromName(safeName) };
}

async function resolveRecordAudio(data, options = {}) {
  const d = data && typeof data === "object" ? data : {};
  const rawFile = String(d.file || "").trim();
  const rawBase64 = String(d.base64 || d.audio_b64 || "").trim();
  if (rawBase64) return decodeBase64Audio(rawBase64, rawFile || d.file_name || "voice.wav");

  if (
    rawFile
    && options.allowGetRecord !== false
    && !/^base64:\/\//i.test(rawFile)
    && !/^https?:\/\//i.test(rawFile)
    && !rawFile.startsWith("/")
    && !rawFile.startsWith("file://")
  ) {
    const outFormat = envStr("QQ_INBOUND_RECORD_OUT_FORMAT", "wav") || "wav";
    const record = await onebotApi("get_record", { file: rawFile, out_format: outFormat });
    const rd = record?.data && typeof record.data === "object" ? record.data : record;
    return resolveRecordAudio({ ...rd, file: rd?.file || rawFile }, { allowGetRecord: false });
  }

  const rawPath = String(d.path || d.file_path || d.local_path || "").trim();
  if (rawPath) return readAudioFile(rawPath);

  const rawUrl = String(d.url || d.file_url || "").trim();
  if (/^https?:\/\//i.test(rawUrl)) return fetchAudioBytes(rawUrl);

  if (/^base64:\/\//i.test(rawFile)) return decodeBase64Audio(rawFile, "voice");
  if (/^https?:\/\//i.test(rawFile)) return fetchAudioBytes(rawFile);
  if (rawFile.startsWith("/") || rawFile.startsWith("file://")) return readAudioFile(rawFile);

  throw new Error("record 缺少可读取的 url/path/file");
}

function formatVoiceTranscript(result) {
  const text = String(result?.text || "").trim();
  if (!text) return "";
  const observations = String(result?.audio_observations || "").trim();
  const lines = [`（QQ语音转写）${text}`];
  if (observations) lines.push(`（声音观察：${observations}）`);
  return lines.join("\n");
}

async function transcribeRecordData(data) {
  if (!envBool("QQ_INBOUND_VOICE_ENABLED", true)) return "";
  const audio = await resolveRecordAudio(data);
  const result = await callGatewayStt(audio.bytes, audio.filename, audio.mimeType);
  return formatVoiceTranscript(result);
}

function contentFromParts(parts) {
  if (!parts.length) return "";
  const hasText = parts.some((p) => p?.type === "text" && String(p.text || "").trim());
  if (!hasText) return [{ type: "text", text: "[图片]" }, ...parts];
  return parts.length === 1 && parts[0]?.type === "text" ? String(parts[0].text || "") : parts;
}

async function extractUserContentFromMessageWithVoice(message, rawMessage = "") {
  if (typeof message === "string") {
    const raw = stripRawReplySegments(message);
    if (!raw) return "";
    const records = parseRawRecordSegments(raw);
    if (!records.length) return raw;
    const cleanText = raw.replace(/\[CQ:(record|voice|audio),[^\]]*\]/gi, "").trim();
    const parts = [];
    if (cleanText) parts.push({ type: "text", text: cleanText });
    for (const rec of records) {
      try {
        const text = await transcribeRecordData(rec.data || {});
        parts.push({ type: "text", text: text || "（收到一条 QQ 语音，但转写为空）" });
      } catch (e) {
        console.log(`[qq-onebot] 语音转写失败(raw)：${String(e?.message || e)}`);
        parts.push({ type: "text", text: "（收到一条 QQ 语音，但转写失败）" });
      }
    }
    return contentFromParts(parts);
  }
  if (!Array.isArray(message)) return "";
  const parts = [];
  for (const seg of message) {
    if (!seg || typeof seg !== "object") continue;
    const type = String(seg.type || "").trim();
    if (type === "reply" || type === "quote") {
      continue;
    }
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
      continue;
    }
    if (isRecordSegmentType(type)) {
      try {
        const text = await transcribeRecordData(seg.data || {});
        parts.push({ type: "text", text: text || "（收到一条 QQ 语音，但转写为空）" });
      } catch (e) {
        console.log(`[qq-onebot] 语音转写失败 message_id=${String(rawMessage || "").slice(0, 80)} err=${String(e?.message || e)}`);
        parts.push({ type: "text", text: "（收到一条 QQ 语音，但转写失败）" });
      }
    }
  }
  return contentFromParts(parts);
}

function replyMessageIdsFromMessage(message, rawMessage = "") {
  const out = [];
  if (Array.isArray(message)) {
    for (const seg of message) {
      if (!seg || typeof seg !== "object") continue;
      const type = String(seg.type || "").trim();
      if (type !== "reply" && type !== "quote") continue;
      const id = String(seg.data?.id || seg.data?.message_id || "").trim();
      if (id && !out.includes(id)) out.push(id);
    }
  }
  for (const id of parseRawReplyMessageIds(rawMessage || (typeof message === "string" ? message : ""))) {
    if (id && !out.includes(id)) out.push(id);
  }
  return out;
}

function onebotMessageIdParam(messageId) {
  const raw = String(messageId || "").trim();
  const n = Number(raw);
  return Number.isSafeInteger(n) && n > 0 ? n : raw;
}

function quotedSenderLabel(event, row) {
  const sender = row?.sender && typeof row.sender === "object" ? row.sender : {};
  const userId = Number(row?.user_id || sender.user_id || 0);
  const selfId = Number(eventSelfId(event) || 0);
  if (ownerQqUserId && userId === ownerQqUserId) return ownerQqDisplayName;
  if (selfId && userId === selfId) return "渡";
  const card = String(sender.card || "").trim();
  const nickname = String(sender.nickname || "").trim();
  return card || nickname || (userId ? `QQ ${userId}` : "");
}

async function fetchQuotedMessage(rowEvent, messageId) {
  const response = await onebotApi("get_msg", { message_id: onebotMessageIdParam(messageId) });
  const row = response?.data && typeof response.data === "object" ? response.data : response;
  const content = await extractUserContentFromMessageWithVoice(row?.message || row?.raw_message || "", row?.raw_message || "");
  const text = contentTextForGroupContext(content, 500);
  if (!text) return null;
  const speaker = quotedSenderLabel(rowEvent, row);
  return {
    messageId: String(messageId || "").trim(),
    text: speaker ? `${speaker}：${text}` : text,
  };
}

async function resolveQuotedMessageContext(event) {
  const ids = replyMessageIdsFromMessage(event?.message || "", event?.raw_message || "");
  if (!ids.length) return "";
  const lines = [];
  for (const id of ids.slice(0, 3)) {
    try {
      const quoted = await fetchQuotedMessage(event, id);
      if (quoted?.text) {
        lines.push(quoted.text);
      } else {
        lines.push(`（引用了一条 QQ 消息，但没有可读文本：message_id=${id}）`);
      }
    } catch (e) {
      console.log(`[qq-onebot] 引用消息拉取失败 message_id=${id}: ${String(e?.message || e)}`);
      lines.push(`（引用了一条 QQ 消息，但拉取失败：message_id=${id}）`);
    }
  }
  if (!lines.length) return "";
  return ["【QQ 引用的消息】", ...lines].join("\n");
}

function mergeQuoteContextIntoContent(content, quoteContext) {
  const quote = String(quoteContext || "").trim();
  if (!quote) return content;
  const fallback = "（只引用了这条消息，没有附加文字）";
  if (typeof content === "string") {
    const current = String(content || "").trim() || fallback;
    return `${quote}\n\n【当前消息】\n${current}`;
  }
  const parts = normalizeUserContentToParts(content);
  if (!parts.length) {
    return `${quote}\n\n【当前消息】\n${fallback}`;
  }
  return [{ type: "text", text: `${quote}\n\n【当前消息】` }, ...parts];
}

async function enrichContentWithQuotedMessage(event, content) {
  const quoteContext = await resolveQuotedMessageContext(event);
  return mergeQuoteContextIntoContent(content, quoteContext);
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

async function callGatewayChat(windowId, userContent, options = {}) {
  const base = gatewayBaseUrl();
  const chatPath = envStr("GATEWAY_CHAT_PATH", "/v1/chat/completions");
  const url = base + (chatPath.startsWith("/") ? chatPath : `/${chatPath}`);
  const body = {
    messages: [
      { role: "user", content: userContent },
    ],
    stream: false,
  };
  const headers = {
    "Content-Type": "application/json",
    "X-Window-Id": String(windowId || "").trim(),
    "X-Reply-Channel": String(options.replyChannel || "qq").trim() || "qq",
  };
  if (options.replyTarget) headers["X-Reply-Target"] = String(options.replyTarget).trim();
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

async function callGatewayStt(audioBytes, filename, mimeType) {
  const base = gatewayBaseUrl();
  const sttPath = envStr("GATEWAY_STT_PATH", "/api/internal/stt");
  const url = base + (sttPath.startsWith("/") ? sttPath : `/${sttPath}`);
  const safeName = safeAudioFilename(filename, "qq-voice");
  const contentType = String(mimeType || mimeTypeFromName(safeName)).trim() || "application/octet-stream";
  const form = new FormData();
  form.append("audio", new Blob([Buffer.from(audioBytes || [])], { type: contentType }), safeName);
  form.append("mime_type", contentType);
  form.append("filename", safeName);
  const headers = {};
  const token = envStr("GATEWAY_INTERNAL_STT_TOKEN", "")
    || envStr("MAIN_GATEWAY_BEARER_TOKEN", "")
    || envStr("XIAOAI_GATEWAY_TOKEN", "");
  if (token) headers.Authorization = `Bearer ${token}`;
  const r = await fetch(url, { method: "POST", headers, body: form });
  const raw = await r.text();
  let data = null;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    data = null;
  }
  if (!r.ok || !data?.ok) {
    throw new Error(`STT 返回 ${r.status}: ${(raw || "").slice(0, 200)}`);
  }
  return data;
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
const reportGroupActivityEnabled = envBool("QQ_GROUP_ACTIVITY_REPORT_ENABLED", true);
const groupActivityContextLimit = Math.max(1, envInt("QQ_GROUP_ACTIVITY_CONTEXT_MESSAGES", 20));

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
  const rawName = card || nickname || "群成员";
  const isOwner = !!ownerQqUserId && userId === ownerQqUserId;
  const name = isOwner ? ownerQqDisplayName : rawName;
  return { userId, name, rawName, isOwner };
}

function groupSpeakerPrefix(name, userId, isOwner = false) {
  void userId;
  const base = String(name || "群成员").trim() || "群成员";
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
  if (!groupId) return null;
  const { userId, name, isOwner } = senderLabel(j);
  const text = contentTextForGroupContext(content);
  const images = [...new Set([...imageUrlsFromContent(content), ...rawImageUrls(j?.raw_message || "")])];
  const rows = getGroupHistory(groupId);
  const row = {
    userId,
    name,
    isOwner,
    text,
    images,
    messageId: String(j?.message_id || ""),
    ts: Number(j?.time || 0),
  };
  rows.push(row);
  if (rows.length > groupHistoryKeepLimit) rows.splice(0, rows.length - groupHistoryKeepLimit);
  recentGroupMessages.set(String(groupId), rows);
  return row;
}

function groupActivityReportToken() {
  return envStr("QQ_GROUP_ACTIVITY_REPORT_TOKEN", "")
    || envStr("MAIN_GATEWAY_BEARER_TOKEN", "")
    || envStr("QQ_PROACTIVE_PUSH_TOKEN", "");
}

function rowForActivityReport(row, groupId) {
  return {
    group_id: Number(groupId || 0),
    user_id: Number(row?.userId || 0),
    sender_name: String(row?.name || "").trim(),
    is_owner: !!row?.isOwner,
    text: String(row?.text || "").trim(),
    images: Array.isArray(row?.images)
      ? row.images.map((x) => String(x || "").trim()).filter((x) => /^https?:\/\//i.test(x))
      : [],
    message_id: String(row?.messageId || "").trim(),
    timestamp: Number(row?.ts || 0),
  };
}

async function reportQqGroupActivity(j, previousRows, content) {
  if (!reportGroupActivityEnabled) return;
  const groupId = Number(j?.group_id || 0);
  if (!groupId || !ownerQqUserId) return;
  const { userId, name, isOwner } = senderLabel(j);
  if (!isOwner) return;
  const text = contentTextForGroupContext(content);
  const images = [...new Set([...imageUrlsFromContent(content), ...rawImageUrls(j?.raw_message || "")])];
  if (!text) return;
  const reportPath = envStr("QQ_GROUP_ACTIVITY_REPORT_PATH", "/api/internal/qq-group-activity");
  const url = absolutizeGatewayUrl(reportPath);
  const context = (previousRows || [])
    .slice(-groupActivityContextLimit)
    .map((row) => rowForActivityReport(row, groupId));
  const body = {
    source: "qq_onebot",
    group_id: groupId,
    user_id: userId,
    sender_name: name,
    is_owner: true,
    text,
    images,
    message_id: String(j?.message_id || ""),
    timestamp: Number(j?.time || 0),
    context,
  };
  const headers = { "Content-Type": "application/json" };
  const token = groupActivityReportToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  try {
    const r = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
    if (!r.ok) {
      const raw = await r.text().catch(() => "");
      console.log(`[qq-onebot] 群活动上报失败 status=${r.status} body=${raw.slice(0, 160)}`);
      return;
    }
    if (logGroupEvents) {
      console.log(`[qq-onebot] 群活动已上报 group=${groupId} message_id=${String(j?.message_id || "")} text=${text.slice(0, 60)}`);
    }
  } catch (e) {
    console.log(`[qq-onebot] 群活动上报异常：${String(e?.message || e)}`);
  }
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

async function contentWithoutSelfAt(j) {
  const selfId = eventSelfId(j);
  const msg = j?.message;
  if (Array.isArray(msg)) {
    const filtered = msg.filter((seg) => {
      if (!seg || typeof seg !== "object") return false;
      if (String(seg.type || "") !== "at") return true;
      return String(seg.data?.qq || "").trim() !== selfId;
    });
    return extractUserContentFromMessageWithVoice(filtered, j?.raw_message || "");
  }
  const raw = String(j?.raw_message || "");
  const clean = stripSelfAtFromRaw(raw, selfId);
  return extractUserContentFromMessageWithVoice(clean, j?.raw_message || "");
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
    ownerQqUserId ? "身份标记：带 [当前用户/辛玥] 的发言人是辛玥/当前用户；其他人是群友。" : "",
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
  const atTargets = groupAtTargets(j);
  const mentionsSelf = messageMentionsSelf(j);
  const baseContent = mentionsSelf
    ? await contentWithoutSelfAt(j)
    : extractUserContentFromMessage(j?.message || j?.raw_message || "");
  const content = await enrichContentWithQuotedMessage(j, baseContent);
  if (logGroupEvents) {
    console.log(`[qq-onebot] group event group=${groupId} user=${Number(j?.user_id || 0)} self_id=${eventSelfId(j) || "unknown"} at=${atTargets.join(",") || "-"} content=${userContentPreview(content, 80) || "-"}`);
  }
  const previousRows = getGroupHistory(groupId).slice(-groupHistoryContextLimit);
  void reportQqGroupActivity(j, previousRows, content || extractUserContentFromMessage(j?.message || j?.raw_message || ""));
  rememberGroupMessage(j, content || extractUserContentFromMessage(j?.message || j?.raw_message || ""));
  if (!mentionsSelf) {
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
      replyTarget: "qq_group_mention",
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
  const baseContent = await extractUserContentFromMessageWithVoice(j?.message || j?.raw_message || "", j?.raw_message || "");
  const content = await enrichContentWithQuotedMessage(j, baseContent);
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
