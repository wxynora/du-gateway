import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import process from "node:process";
import QRCode from "qrcode";
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

function nowIso() {
  return new Date().toISOString();
}

function gatewayBaseUrl() {
  return envStr("GATEWAY_BASE_URL", "http://127.0.0.1:5000").replace(/\/+$/, "");
}

function maskToken(s) {
  const t = String(s || "").trim();
  if (t.length <= 10) return "***";
  return `${t.slice(0, 4)}...${t.slice(-4)}`;
}

function randomWechatUinHeader() {
  // uint32 -> decimal string -> base64
  const n = crypto.randomBytes(4).readUInt32BE(0) >>> 0;
  const dec = String(n);
  return Buffer.from(dec, "utf-8").toString("base64");
}

function ilinkBaseUrl() {
  return envStr("ILINK_BASE_URL", "https://ilinkai.weixin.qq.com").replace(/\/+$/, "");
}

function resolveStateFilePath() {
  const configured = envStr("WECHAT_ILINK_STATE_FILE", ".wechat_ilink_state.json");
  if (path.isAbsolute(configured)) return configured;
  return path.resolve(process.cwd(), configured);
}

function loadState() {
  const p = resolveStateFilePath();
  try {
    if (!fs.existsSync(p)) return { bot_token: "", get_updates_buf: "", updated_at: "" };
    const raw = fs.readFileSync(p, "utf-8");
    const data = JSON.parse(raw);
    return {
      bot_token: String(data?.bot_token || "").trim(),
      get_updates_buf: String(data?.get_updates_buf || "").trim(),
      updated_at: String(data?.updated_at || "").trim(),
    };
  } catch {
    return { bot_token: "", get_updates_buf: "", updated_at: "" };
  }
}

function saveState(next) {
  const p = resolveStateFilePath();
  const payload = {
    bot_token: String(next?.bot_token || "").trim(),
    get_updates_buf: String(next?.get_updates_buf || "").trim(),
    updated_at: nowIso(),
  };
  fs.writeFileSync(p, JSON.stringify(payload, null, 2), "utf-8");
}

async function ilinkGetJson(url, botToken = "") {
  const headers = {
    "Content-Type": "application/json",
    "X-WECHAT-UIN": randomWechatUinHeader(),
  };
  if (botToken) {
    headers["AuthorizationType"] = "ilink_bot_token";
    headers["Authorization"] = `Bearer ${botToken}`;
  }
  const r = await fetch(url, { method: "GET", headers });
  const text = await r.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  return { status: r.status, data, text };
}

async function ilinkPostJson(pathname, body, botToken) {
  const url = ilinkBaseUrl() + (pathname.startsWith("/") ? pathname : `/${pathname}`);
  const headers = {
    "Content-Type": "application/json",
    "AuthorizationType": "ilink_bot_token",
    "X-WECHAT-UIN": randomWechatUinHeader(),
    "Authorization": `Bearer ${botToken}`,
  };
  const r = await fetch(url, { method: "POST", headers, body: JSON.stringify(body || {}) });
  const text = await r.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  return { status: r.status, data, text };
}

async function loginByQrcode() {
  const base = ilinkBaseUrl();
  console.log("[wechat-ilink] 🔐 开始微信扫码登录...");

  async function fetchQr() {
    const qrUrl = `${base}/ilink/bot/get_bot_qrcode?bot_type=3`;
    const r = await ilinkGetJson(qrUrl, "");
    const qrcodeToken = String(r.data?.qrcode || "").trim();
    const img = String(r.data?.qrcode_img_content || "").trim();
    if (!qrcodeToken || !img) {
      throw new Error(
        `get_bot_qrcode 未返回 qrcode/qrcode_img_content status=${r.status} body=${(r.text || "").slice(0, 220)}`
      );
    }
    return { qrcodeToken, img };
  }

  let { qrcodeToken, img } = await fetchQr();
  const qrStr = await QRCode.toString(img, { type: "terminal", small: true });
  console.log("📱 请用微信扫描以下二维码：\n");
  console.log(qrStr);
  console.log("⏳ 等待扫码...");

  const deadline = Date.now() + 5 * 60_000;
  let refreshCount = 0;

  while (Date.now() < deadline) {
    await sleep(1000);
    const stUrl = `${base}/ilink/bot/get_qrcode_status?qrcode=${encodeURIComponent(qrcodeToken)}`;
    const r2 = await ilinkGetJson(stUrl, "");
    const status = String(r2.data?.status || "").trim().toLowerCase();

    switch (status) {
      case "wait":
        process.stdout.write(".");
        break;
      case "scaned":
        console.log("\n[wechat-ilink] 👀 已扫码，请在微信端确认...");
        break;
      case "expired": {
        refreshCount += 1;
        if (refreshCount > 3) throw new Error("二维码多次过期，请重新运行 login");
        console.log(`\n[wechat-ilink] ⏳ 二维码过期，刷新中 (${refreshCount}/3)...`);
        const fresh = await fetchQr();
        qrcodeToken = fresh.qrcodeToken;
        img = fresh.img;
        const freshStr = await QRCode.toString(img, { type: "terminal", small: true });
        console.log(freshStr);
        console.log("⏳ 等待扫码...");
        break;
      }
      case "confirmed": {
        const botToken = String(r2.data?.bot_token || "").trim();
        if (!botToken) throw new Error("扫码已确认，但未返回 bot_token");
        console.log(`\n[wechat-ilink] ✅ 登录成功 bot_token=${maskToken(botToken)}`);
        return botToken;
      }
      default:
        if (status) console.log(`\n[wechat-ilink] login status=${status}`);
        break;
    }
  }

  throw new Error("登录超时");
}

function extractTextFromMsg(msg) {
  const items = Array.isArray(msg?.item_list) ? msg.item_list : [];
  for (const it of items) {
    if (!it || typeof it !== "object") continue;
    const t = Number(it.type || 0);
    if (t === 1 && it.text_item && typeof it.text_item === "object") {
      const text = String(it.text_item.text || "").trim();
      if (text) return text;
    }
  }
  return "";
}

function decryptAesEcb(ciphertext, key) {
  const decipher = crypto.createDecipheriv("aes-128-ecb", key, null);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]);
}

function parseAesKey(aesKeyBase64) {
  const decoded = Buffer.from(String(aesKeyBase64 || ""), "base64");
  if (decoded.length === 16) return decoded;
  if (decoded.length === 32 && /^[0-9a-fA-F]{32}$/.test(decoded.toString("ascii"))) {
    return Buffer.from(decoded.toString("ascii"), "hex");
  }
  throw new Error(`无法解析 aes_key，解码后长度=${decoded.length}`);
}

function buildCdnDownloadUrl(cdnBaseUrl, encryptedQueryParam) {
  const base = String(cdnBaseUrl || "https://novac2c.cdn.weixin.qq.com/c2c").replace(/\/+$/, "");
  return `${base}/download?encrypted_query_param=${encodeURIComponent(String(encryptedQueryParam || ""))}`;
}

async function downloadAndDecryptImageFromItem(item) {
  const img = item?.image_item;
  const media = img?.media || {};
  const fullUrl = String(media.full_url || "").trim();
  const encryptedQueryParam = String(media.encrypt_query_param || "").trim();
  if (!fullUrl && !encryptedQueryParam) return null;
  const url = fullUrl || buildCdnDownloadUrl(envStr("WECHAT_CDN_BASE_URL", "https://novac2c.cdn.weixin.qq.com/c2c"), encryptedQueryParam);
  const r = await fetch(url);
  if (!r.ok) throw new Error(`图片下载失败 status=${r.status}`);
  const encrypted = Buffer.from(await r.arrayBuffer());
  const aesKeyBase64 = img?.aeskey
    ? Buffer.from(String(img.aeskey || "").trim(), "hex").toString("base64")
    : String(media.aes_key || "").trim();
  return aesKeyBase64 ? decryptAesEcb(encrypted, parseAesKey(aesKeyBase64)) : encrypted;
}

function guessImageMime(buf) {
  const b = Buffer.isBuffer(buf) ? buf : Buffer.from(buf || []);
  if (b.length >= 8 && b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return "image/png";
  if (b.length >= 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "image/jpeg";
  if (b.length >= 6 && (b.slice(0, 6).toString("ascii") === "GIF87a" || b.slice(0, 6).toString("ascii") === "GIF89a")) return "image/gif";
  if (b.length >= 12 && b.slice(0, 4).toString("ascii") === "RIFF" && b.slice(8, 12).toString("ascii") === "WEBP") return "image/webp";
  if (b.length >= 2 && b[0] === 0x42 && b[1] === 0x4d) return "image/bmp";
  return "image/jpeg";
}

async function extractUserContentFromMsg(msg) {
  const items = Array.isArray(msg?.item_list) ? msg.item_list : [];
  const parts = [];
  for (const it of items) {
    if (!it || typeof it !== "object") continue;
    const t = Number(it.type || 0);
    if (t === 1 && it.text_item && typeof it.text_item === "object") {
      const text = String(it.text_item.text || "").trim();
      if (text) parts.push({ type: "text", text });
      continue;
    }
    if (t === 2) {
      try {
        const buf = await downloadAndDecryptImageFromItem(it);
        if (!buf?.length) continue;
        const mime = guessImageMime(buf);
        parts.push({ type: "image_url", image_url: { url: `data:${mime};base64,${buf.toString("base64")}` } });
      } catch (e) {
        console.log(`[wechat-ilink] 入站图片解密失败：${String(e?.message || e)}`);
      }
    }
  }
  if (!parts.length) return "";
  const hasText = parts.some((p) => p?.type === "text" && String(p.text || "").trim());
  if (!hasText) {
    return [{ type: "text", text: "[图片]" }, ...parts];
  }
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

function isDirectChatMsg(msg) {
  const gid = msg?.group_id ?? msg?.groupId ?? msg?.room_id ?? msg?.roomId;
  if (gid) return false;
  return true;
}

function buildWechatStyleSystem() {
  const tagsLine = getStickerTagsLineForSystemPrompt();
  return [
    "请用中文回复，语气自然、简洁、温柔但不油腻。",
    "情绪明显时可在整条回复末尾加一个英文标签（方括号）；每条最多一个，平淡时不加。",
    tagsLine,
    "只输出给她看的正文，不要输出“（脑内OS：）”或任何内心独白部分。",
    "不要输出分割线（例如 ---、———、***）。",
    "不要使用 Markdown 强调符号 * 或 **。",
    "不要输出“(表情包:xxx)”这类占位符。",
    "允许自然分段，但不要为了格式刻意堆很多空行。",
    "不要写“小本本/记事本更新”的指令或提示（除非用户明确要求）。",
    "如果你想发图片，直接输出 Markdown 图片，例如 ![图](https://example.com/a.jpg) 。",
    "可以同时输出文字正文；连接器会尽量把图片单独发出去。",
    "如需控制电脑，可在整条回复里最多追加一个 [PCMD:...] 标签；不确定就不要加。",
    "仅允许这些指令：[PCMD:lock] [PCMD:shutdown] [PCMD:shutdown:秒数] [PCMD:restart] [PCMD:restart:秒数] [PCMD:sleep] [PCMD:mute] [PCMD:volume:0-100] [PCMD:notify:标题:内容] [PCMD:open:notepad] [PCMD:open:notepad:要写入的内容] [PCMD:open:chrome] [PCMD:open:vscode] [PCMD:open:wechat] [PCMD:open:notion] [PCMD:url:https://...] [PCMD:media:play]",
    "严禁输出未列出的 PCMD；若不确定，请不要输出 PCMD。仅在确有必要时输出；平时不要输出。",
  ].join("\n");
}

function resolveWechatWindowId() {
  const tgUserId = envStr("TELEGRAM_PROACTIVE_TARGET_USER_ID", "");
  if (!tgUserId) {
    throw new Error("缺少 TELEGRAM_PROACTIVE_TARGET_USER_ID，无法把微信入口并到 TG 上下文");
  }
  return `tg_${tgUserId}`;
}

async function callGatewayChat(windowId, userContent) {
  const base = gatewayBaseUrl();
  const chatPath = envStr("GATEWAY_CHAT_PATH", "/v1/chat/completions");
  const url = base + (chatPath.startsWith("/") ? chatPath : `/${chatPath}`);
  const configuredModel = envStr("GATEWAY_MODEL", "");
  const styleSystem = buildWechatStyleSystem();
  const body = {
    messages: [
      { role: "system", content: styleSystem },
      { role: "user", content: userContent },
    ],
    stream: false,
  };
  // 对齐 Telegram：优先用网关当前 active 上游可用的第一个模型，避免默认模型与权限不匹配导致 403
  async function fetchGatewayFirstModel() {
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
  const model = configuredModel || (await fetchGatewayFirstModel());
  if (model) body.model = model;
  const headers = {
    "Content-Type": "application/json",
    "X-Window-Id": String(windowId || "").trim(),
  };
  if (envBool("GATEWAY_TG_USER_INPUT", true)) {
    headers["X-TG-User-Input"] = "1";
  }
  const r = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
  const text = await r.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!r.ok) {
    throw new Error(`网关返回 ${r.status}: ${(text || "").slice(0, 200)}`);
  }
  const reply = data?.choices?.[0]?.message?.content;
  return String(reply || "").trim();
}

const DEFAULT_STICKER_TAGS = [
  "affectionate",
  "angry",
  "cute",
  "good_night",
  "happy",
  "kiss",
  "pitiful",
  "sad",
  "shy",
  "sorry",
  "speechless",
];

let _STICKER_TAGS_CACHE_AT = 0;
let _STICKER_TAGS_CACHE = [...DEFAULT_STICKER_TAGS];
let _STICKER_MAPPING_CACHE_AT = 0;
let _STICKER_MAPPING_CACHE = {};
let _STICKER_REGEX_CACHE_AT = 0;
let _STICKER_REGEX_CACHE = /(?!x)x/;
const _STICKER_CACHE_TTL_MS = 45_000;

async function fetchStickerTags() {
  const now = Date.now();
  if (now - _STICKER_TAGS_CACHE_AT < _STICKER_CACHE_TTL_MS && _STICKER_TAGS_CACHE.length) {
    return _STICKER_TAGS_CACHE;
  }
  try {
    const r = await fetch(`${gatewayBaseUrl()}/miniapp-api/stickers/tags`);
    const text = await r.text();
    if (!r.ok) return _STICKER_TAGS_CACHE;
    const data = text ? JSON.parse(text) : null;
    const rows = Array.isArray(data?.tags) ? data.tags : [];
    const keys = rows
      .map((it) => String(it?.key || "").trim().toLowerCase())
      .filter(Boolean);
    _STICKER_TAGS_CACHE_AT = now;
    _STICKER_TAGS_CACHE = [...new Set(keys)];
    return _STICKER_TAGS_CACHE;
  } catch {
    return _STICKER_TAGS_CACHE;
  }
}

async function fetchStickerMapping() {
  const now = Date.now();
  if (now - _STICKER_MAPPING_CACHE_AT < _STICKER_CACHE_TTL_MS && Object.keys(_STICKER_MAPPING_CACHE).length) {
    return _STICKER_MAPPING_CACHE;
  }
  try {
    const r = await fetch(`${gatewayBaseUrl()}/miniapp-api/stickers/mapping`);
    const text = await r.text();
    if (!r.ok) return _STICKER_MAPPING_CACHE;
    const data = text ? JSON.parse(text) : null;
    const mapping = (data?.mapping && typeof data.mapping === "object") ? data.mapping : {};
    _STICKER_MAPPING_CACHE_AT = now;
    _STICKER_MAPPING_CACHE = mapping;
    return _STICKER_MAPPING_CACHE;
  } catch {
    return _STICKER_MAPPING_CACHE;
  }
}

function getStickerTagsLineForSystemPrompt() {
  if (_STICKER_TAGS_CACHE.length) {
    return `当前全部可用英文代号：${_STICKER_TAGS_CACHE.map((k) => `[${k}]`).join(" ")}`;
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

async function pickRandomStickerKey(tag) {
  const t = String(tag || "").trim().toLowerCase();
  if (!t) return "";
  const mapping = await fetchStickerMapping();
  const keys = Array.isArray(mapping?.[t]) ? mapping[t].map((k) => String(k || "").trim()).filter(Boolean) : [];
  if (!keys.length) return "";
  return keys[Math.floor(Math.random() * keys.length)] || "";
}

function buildStickerRawUrl(key) {
  return `${gatewayBaseUrl()}/miniapp-api/stickers/raw?key=${encodeURIComponent(String(key || ""))}`;
}

function extractVoiceTag(text) {
  const raw = String(text || "");
  const m = raw.match(/<voice>([\s\S]*?)<\/voice>/i);
  if (!m) return { cleanText: raw.trim(), voiceText: "" };
  const voiceText = String(m[1] || "").trim();
  const cleanText = raw.replace(/<voice>[\s\S]*?<\/voice>/gi, "").trim();
  return { cleanText, voiceText };
}

function extractImageUrls(text) {
  const raw = String(text || "");
  const urls = [];
  const seen = new Set();
  const mdRe = /!\[[^\]]*?\]\((https?:\/\/[^\s)]+)\)/g;
  const plainRe = /\bhttps?:\/\/[^\s<>()]+?\.(?:png|jpe?g|gif|webp|bmp)(?:\?[^\s<>()]*)?/gi;
  let m;
  while ((m = mdRe.exec(raw)) !== null) {
    const url = String(m[1] || "").trim();
    if (url && !seen.has(url)) {
      seen.add(url);
      urls.push(url);
    }
  }
  while ((m = plainRe.exec(raw)) !== null) {
    const url = String(m[0] || "").trim();
    if (url && !seen.has(url)) {
      seen.add(url);
      urls.push(url);
    }
  }
  const cleanText = raw
    .replace(mdRe, "")
    .replace(plainRe, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  return { cleanText, imageUrls: urls };
}

async function downloadRemoteImageToTemp(url, destDir) {
  const r = await fetch(url);
  if (!r.ok) {
    throw new Error(`图片下载失败 status=${r.status} url=${String(url || "").slice(0, 120)}`);
  }
  const ab = await r.arrayBuffer();
  const buf = Buffer.from(ab);
  const ctype = String(r.headers.get("content-type") || "").toLowerCase();
  let ext = ".jpg";
  if (ctype.includes("png")) ext = ".png";
  else if (ctype.includes("gif")) ext = ".gif";
  else if (ctype.includes("webp")) ext = ".webp";
  else if (ctype.includes("bmp")) ext = ".bmp";
  else {
    const pathname = new URL(url).pathname.toLowerCase();
    if (pathname.endsWith(".png")) ext = ".png";
    else if (pathname.endsWith(".gif")) ext = ".gif";
    else if (pathname.endsWith(".webp")) ext = ".webp";
    else if (pathname.endsWith(".bmp")) ext = ".bmp";
  }
  fs.mkdirSync(destDir, { recursive: true });
  const filePath = path.join(destDir, `wechat-outbound-${Date.now()}-${crypto.randomUUID()}${ext}`);
  fs.writeFileSync(filePath, buf);
  return filePath;
}

async function uploadImageToWeixin(botToken, toUserId, filePath) {
  const plaintext = fs.readFileSync(filePath);
  const rawsize = plaintext.length;
  const rawfilemd5 = crypto.createHash("md5").update(plaintext).digest("hex");
  const filesize = aesEcbPaddedSize(rawsize);
  const filekey = crypto.randomBytes(16).toString("hex");
  const aeskeyHex = crypto.randomBytes(16).toString("hex");
  const uploadMeta = await getUploadUrl(botToken, {
    filekey,
    media_type: 1,
    to_user_id: String(toUserId || "").trim(),
    rawsize,
    rawfilemd5,
    filesize,
    no_need_thumb: true,
    aeskey: aeskeyHex,
  });
  const uploadParam = String(uploadMeta?.upload_param || "").trim();
  if (!uploadParam) throw new Error("图片 getuploadurl 未返回 upload_param");
  const uploaded = await uploadBufferToCdn(plaintext, uploadParam, filekey, aeskeyHex);
  return {
    encrypt_query_param: uploaded.encryptedParam,
    aes_key: Buffer.from(aeskeyHex, "hex").toString("base64"),
    file_size: rawsize,
    ciphertext_size: uploaded.ciphertextSize,
  };
}

async function sendWeixinImage(botToken, toUserId, contextToken, uploaded) {
  const clientId = `dg-${crypto.randomUUID()}`;
  const payload = {
    msg: {
      from_user_id: "",
      to_user_id: String(toUserId || "").trim(),
      client_id: clientId,
      message_type: 2,
      message_state: 2,
      context_token: String(contextToken || "").trim(),
      item_list: [
        {
          type: 2,
          image_item: {
            media: {
              encrypt_query_param: String(uploaded?.encrypt_query_param || "").trim(),
              aes_key: String(uploaded?.aes_key || "").trim(),
              encrypt_type: 1,
            },
            mid_size: Number(uploaded?.ciphertext_size || 0),
          },
        },
      ],
    },
    base_info: { channel_version: "1.0.2" },
  };
  const r = await ilinkPostJson("/ilink/bot/sendmessage", payload, botToken);
  if (r.status < 200 || r.status >= 300) {
    return { ok: false, ret: 0, status: r.status, body: (r.text || "").slice(0, 200) };
  }
  const ret = Number(r.data?.ret ?? 0);
  if (ret !== 0) {
    return { ok: false, ret, status: r.status, body: JSON.stringify(r.data).slice(0, 200) };
  }
  return { ok: true, ret: 0, status: r.status, body: "" };
}

function aesEcbPaddedSize(plaintextSize) {
  return Math.ceil((plaintextSize + 1) / 16) * 16;
}

function encryptAesEcb(plaintext, key) {
  const cipher = crypto.createCipheriv("aes-128-ecb", key, null);
  return Buffer.concat([cipher.update(plaintext), cipher.final()]);
}

async function getUploadUrl(botToken, body) {
  const url = ilinkBaseUrl() + "/ilink/bot/getuploadurl";
  const payload = { ...(body || {}), base_info: { channel_version: "1.0.2" } };
  const raw = JSON.stringify(payload);
  const headers = {
    "Content-Type": "application/json",
    "Content-Length": String(Buffer.byteLength(raw, "utf-8")),
    "AuthorizationType": "ilink_bot_token",
    "X-WECHAT-UIN": randomWechatUinHeader(),
    "Authorization": `Bearer ${botToken}`,
  };
  const r = await fetch(url, { method: "POST", headers, body: raw });
  const text = await r.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!r.ok) throw new Error(`getuploadurl ${r.status}: ${(text || "").slice(0, 200)}`);
  return data || {};
}

function buildCdnUploadUrl(cdnBaseUrl, uploadParam, filekey) {
  const base = String(cdnBaseUrl || "https://novac2c.cdn.weixin.qq.com/c2c").replace(/\/+$/, "");
  const u = new URL(base + "/upload");
  u.searchParams.set("encrypted_query_param", uploadParam);
  u.searchParams.set("filekey", filekey);
  return u.toString();
}

async function uploadBufferToCdn(buf, uploadParam, filekey, aeskeyHex) {
  const aeskey = Buffer.from(String(aeskeyHex || ""), "hex");
  const ciphertext = encryptAesEcb(buf, aeskey);
  const cdnUrl = buildCdnUploadUrl(envStr("WECHAT_CDN_BASE_URL", "https://novac2c.cdn.weixin.qq.com/c2c"), uploadParam, filekey);
  const r = await fetch(cdnUrl, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: new Uint8Array(ciphertext),
  });
  if (!r.ok) {
    const errText = await r.text();
    throw new Error(`cdn upload ${r.status}: ${(errText || "").slice(0, 200)}`);
  }
  const encryptedParam = r.headers.get("x-encrypted-param") || "";
  if (!encryptedParam) throw new Error("cdn upload 缺少 x-encrypted-param");
  return { encryptedParam, ciphertextSize: ciphertext.length };
}

function splitReplyByNewlineAndLen(text, chunkChars, maxTotalChars) {
  const raw = String(text || "").trim();
  if (!raw) return [];
  const limit = Math.max(20, Number(chunkChars || 100));
  const maxTotal = Math.max(0, Number(maxTotalChars || 0));
  const attachThreshold = 10;
  const maxChunks = 10;
  const clipped = maxTotal > 0 && raw.length > maxTotal ? raw.slice(0, maxTotal) : raw;
  const lines = clipped.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  const src = lines.length ? lines : [clipped];
  const out = [];
  for (let idx = 0; idx < src.length; idx += 1) {
    const one = String(src[idx] || "").trim();
    if (!one) continue;

    if (one.length <= attachThreshold) {
      const next = String(src[idx + 1] || "").trim();
      if (next) {
        const merged = `${one} ${next}`.trim();
        if (merged.length <= limit) {
          out.push(merged);
        } else {
          out.push(one);
          out.push(next);
        }
        idx += 1;
        continue;
      }
      // 最后一条很短时，不再并到上一条，避免把多条内容揉成一坨
      out.push(one);
      continue;
    }

    if (one.length <= limit) {
      out.push(one);
      continue;
    }

    for (let i = 0; i < one.length; i += limit) out.push(one.slice(i, i + limit));
  }
  const filtered = out.filter(Boolean);
  if (filtered.length <= maxChunks) return filtered;
  const head = filtered.slice(0, maxChunks - 1);
  const tail = filtered.slice(maxChunks - 1).join(" ").replace(/\s+/g, " ").trim();
  return [...head, tail].filter(Boolean);
}

async function sendWeixinText(botToken, toUserId, contextToken, text) {
  const clientId = `dg-${crypto.randomUUID()}`;
  const payload = {
    msg: {
      from_user_id: "",
      to_user_id: String(toUserId || "").trim(),
      client_id: clientId,
      message_type: 2,
      message_state: 2,
      context_token: String(contextToken || "").trim(),
      item_list: [{ type: 1, text_item: { text: String(text || "") } }],
    },
    base_info: { channel_version: "1.0.2" },
  };
  const r = await ilinkPostJson("/ilink/bot/sendmessage", payload, botToken);
  if (r.status < 200 || r.status >= 300) {
    return { ok: false, ret: 0, status: r.status, body: (r.text || "").slice(0, 200) };
  }
  const ret = Number(r.data?.ret ?? 0);
  if (ret !== 0) {
    return { ok: false, ret, status: r.status, body: JSON.stringify(r.data).slice(0, 200) };
  }
  return { ok: true, ret: 0, status: r.status, body: "" };
}

// typing_ticket 需要通过 getconfig(ilink_user_id + context_token) 获取
/** @type {Map<string, {ticket: string, updatedAt: number}>} */
const _typingTicketCacheByUser = new Map();

async function getTypingTicket(botToken, toUserId, contextToken) {
  const uid = String(toUserId || "").trim();
  if (!uid) return "";
  const cached = _typingTicketCacheByUser.get(uid);
  if (cached?.ticket) return cached.ticket;

  const payload = {
    ilink_user_id: uid,
    context_token: String(contextToken || "").trim(),
    base_info: { channel_version: "1.0.2" },
  };
  const r = await ilinkPostJson("/ilink/bot/getconfig", payload, botToken);
  if (r.status < 200 || r.status >= 300) return "";
  const ret = Number(r.data?.ret ?? 0);
  if (ret !== 0) return "";
  const ticket = String(r.data?.typing_ticket || "").trim();
  if (ticket) _typingTicketCacheByUser.set(uid, { ticket, updatedAt: Date.now() });
  return ticket;
}

async function sendTypingStatus(botToken, toUserId, contextToken, status) {
  const uid = String(toUserId || "").trim();
  const ticket = await getTypingTicket(botToken, uid, contextToken);
  if (!ticket) return false;
  const payload = {
    ilink_user_id: uid,
    typing_ticket: ticket,
    status: Number(status || 1), // 1=Typing, 2=CancelTyping
    base_info: { channel_version: "1.0.2" },
  };
  const r = await ilinkPostJson("/ilink/bot/sendtyping", payload, botToken);
  if (r.status < 200 || r.status >= 300) return false;
  const ret = Number(r.data?.ret ?? 0);
  // ret!=0 时可能是 ticket 失效：清缓存，留待下次重新 getconfig
  if (ret !== 0) _typingTicketCacheByUser.delete(uid);
  return ret === 0;
}

async function main() {
  const args = new Set(process.argv.slice(2));
  const forceLogin = args.has("--login");

  let state = loadState();
  if (!state.bot_token || forceLogin) {
    const botToken = await loginByQrcode();
    state.bot_token = botToken;
    state.get_updates_buf = state.get_updates_buf || "";
    saveState(state);
  } else {
    console.log(`[wechat-ilink] 读取本地 bot_token=${maskToken(state.bot_token)}`);
  }

  const botToken = state.bot_token;
  const idleSeconds = Math.max(1, envInt("WECHAT_INPUT_IDLE_SECONDS", 15));
  const immediateChars = Math.max(20, envInt("WECHAT_INPUT_IMMEDIATE_CHARS", 200));
  const outChunkChars = Math.max(20, envInt("WECHAT_OUTPUT_CHUNK_CHARS", 200));
  const maxReplyTotalChars = Math.max(0, envInt("WECHAT_MAX_REPLY_TOTAL_CHARS", 0));
  const sendDelayMs = Math.max(0, envInt("WECHAT_OUTPUT_SEND_DELAY_MS", 600));
  const retryDelayMs = Math.max(200, envInt("WECHAT_OUTPUT_RETRY_DELAY_MS", 1200));
  const typingEnabled = envBool("WECHAT_TYPING_ENABLED", true);
  const typingFirstDelayMs = Math.max(200, envInt("WECHAT_TYPING_FIRST_DELAY_MS", 1000));
  const typingIntervalMs = Math.max(800, envInt("WECHAT_TYPING_INTERVAL_MS", 4000));
  const typingMaxSignals = Math.max(1, envInt("WECHAT_TYPING_MAX_SIGNALS", 3));
  const dedupe = new Set();
  const dedupeMax = 2000;

  // 输入聚合（参考 Telegram）：同一用户 15s 内多条合并成一次请求
  /** @type {Map<string, {parts: any[], toUserId: string, contextToken: string, timer: any, lastApologyAt: number, failureNotified: boolean}>} */
  const pending = new Map();

  async function flushUser(fromUserId) {
    const it = pending.get(fromUserId);
    if (!it) return;
    if (it.timer) {
      clearTimeout(it.timer);
      it.timer = null;
    }
    const merged = mergeUserContents(it.parts || []);
    if (!merged) {
      pending.delete(fromUserId);
      return;
    }

    const windowId = resolveWechatWindowId();
    console.log(`[wechat-ilink] flush from=${fromUserId} window_id=${windowId} preview=${userContentPreview(merged)}`);

    let reply = "";
    let replyClean = "";
    let imageUrls = [];
    let ok = false;
    let typingTimer = null;
    let typingSignals = 0;
    let typingStopped = false;
    async function emitTyping() {
      if (!typingEnabled || typingStopped) return;
      if (typingSignals >= typingMaxSignals) return;
      typingSignals += 1;
      try {
        await sendTypingStatus(botToken, it.toUserId, it.contextToken, 1);
      } catch {
        // ignore typing failures
      }
      if (!typingStopped && typingSignals < typingMaxSignals) {
        typingTimer = setTimeout(emitTyping, typingIntervalMs);
      }
    }

    try {
      if (typingEnabled) {
        typingTimer = setTimeout(emitTyping, typingFirstDelayMs);
      }
      reply = await callGatewayChat(windowId, merged);
      const noVoice = extractVoiceTag(reply).cleanText;
      const stickerParsed = await extractStickerTag(noVoice);
      ({ cleanText: replyClean, imageUrls } = extractImageUrls(stickerParsed.cleanText));
      const stickerKey = await pickRandomStickerKey(stickerParsed.tag);
      if (stickerKey) {
        imageUrls.push(buildStickerRawUrl(stickerKey));
      }
      console.log(
        `[wechat-ilink] gateway reply chars=${reply.length} clean_chars=${replyClean.length} image_count=${imageUrls.length} preview=${reply.slice(0, 120)}`
      );
      ok = true;
    } catch (e) {
      ok = false;
      console.log(`[wechat-ilink] 调网关失败：${String(e?.message || e)}`);
    } finally {
      typingStopped = true;
      if (typingTimer) {
        clearTimeout(typingTimer);
        typingTimer = null;
      }
      if (typingEnabled) {
        // 尽量取消输入状态（失败不影响主流程）
        try {
          await sendTypingStatus(botToken, it.toUserId, it.contextToken, 2);
        } catch {
          // ignore
        }
      }
    }

    if (!ok) {
      // 失败兜底：保留 pending，下次新消息触发时会一起合并再试；
      // 连续失败期间仅提示一次，避免反复打扰用户。
      if (!it.failureNotified) {
        it.lastApologyAt = Date.now();
        it.failureNotified = true;
        try {
          await sendWeixinText(botToken, it.toUserId, it.contextToken, "我这边刚刚有点忙，稍后再试一次好吗？");
        } catch (e2) {
          console.log(`[wechat-ilink] 发送兜底提示失败：${String(e2?.message || e2)}`);
        }
      }
      // 重新挂定时器：避免一直不触发 flush
      it.timer = setTimeout(() => flushUser(fromUserId), idleSeconds * 1000);
      pending.set(fromUserId, it);
      return;
    }

    const chunks = splitReplyByNewlineAndLen(replyClean, outChunkChars, maxReplyTotalChars);
    for (const part of chunks) {
      // sendmessage 可能返回 ret=-2（限频/临时失败）；这里重试一次并且不崩进程
      let rSend = await sendWeixinText(botToken, it.toUserId, it.contextToken, part);
      if (!rSend.ok && Number(rSend.ret) === -2) {
        await sleep(retryDelayMs);
        rSend = await sendWeixinText(botToken, it.toUserId, it.contextToken, part);
      }
      if (!rSend.ok) {
        console.log(
          `[wechat-ilink] sendmessage 失败 ret=${rSend.ret} status=${rSend.status} body=${rSend.body}`
        );
        // 不再继续发后续段，避免刷屏/连续失败；保留 pending 让下一次有机会补发（由你决定是否要做“补发队列”）
        // 这里选择：直接停止发送后续段，但不崩溃。
        break;
      }
      if (sendDelayMs > 0) await sleep(sendDelayMs);
    }

    if (imageUrls.length) {
      try {
        const tempDir = path.join(process.cwd(), ".tmp_wechat_outbound_media");
        for (const imageUrl of imageUrls) {
          console.log(`[wechat-ilink] 开始发送图片 url=${imageUrl.slice(0, 160)}`);
          const filePath = await downloadRemoteImageToTemp(imageUrl, tempDir);
          try {
            const uploadedImage = await uploadImageToWeixin(botToken, it.toUserId, filePath);
            const imageResp = await sendWeixinImage(botToken, it.toUserId, it.contextToken, uploadedImage);
            if (!imageResp.ok) {
              console.log(
                `[wechat-ilink] send image 失败 ret=${imageResp.ret} status=${imageResp.status} body=${imageResp.body}`
              );
              break;
            }
            console.log(`[wechat-ilink] send image ok path=${filePath}`);
          } finally {
            try { fs.unlinkSync(filePath); } catch {}
          }
          if (sendDelayMs > 0) await sleep(sendDelayMs);
        }
      } catch (e) {
        console.log(`[wechat-ilink] 发送图片失败：${String(e?.message || e)}`);
      }
    } else {
      console.log("[wechat-ilink] 本次回复未产出图片，仅发送文字");
    }

    // 成功后清空该用户 pending
    pending.delete(fromUserId);
  }

  while (true) {
    try {
      const body = {
        get_updates_buf: String(state.get_updates_buf || ""),
        base_info: { channel_version: "1.0.2" },
      };
      const r = await ilinkPostJson("/ilink/bot/getupdates", body, botToken);
      if (r.status < 200 || r.status >= 300) {
        throw new Error(`getupdates 非 2xx status=${r.status} body=${(r.text || "").slice(0, 200)}`);
      }
      const ret = Number(r.data?.ret ?? 0);
      if (ret !== 0) {
        throw new Error(`getupdates ret=${ret} body=${JSON.stringify(r.data).slice(0, 200)}`);
      }

      const newBuf = String(r.data?.get_updates_buf || "").trim();
      if (newBuf && newBuf !== state.get_updates_buf) {
        state.get_updates_buf = newBuf;
        saveState(state);
      }

      const msgs = Array.isArray(r.data?.msgs) ? r.data.msgs : [];
      for (const msg of msgs) {
        if (!msg || typeof msg !== "object") continue;
        if (!isDirectChatMsg(msg)) continue;

        const fromUserId = String(msg.from_user_id || "").trim();
        const contextToken = String(msg.context_token || "").trim();
        const content = await extractUserContentFromMsg(msg);
        if (!fromUserId || !contextToken || !content) continue;

        const dedupeKey = `${fromUserId}::${contextToken}`;
        if (dedupe.has(dedupeKey)) continue;
        dedupe.add(dedupeKey);
        if (dedupe.size > dedupeMax) dedupe.clear();

        console.log(`[wechat-ilink] inbound from=${fromUserId} content=${userContentPreview(content, 60)}`);

        const existing = pending.get(fromUserId) || {
          parts: [],
          toUserId: fromUserId,
          contextToken,
          timer: null,
          lastApologyAt: 0,
          failureNotified: false,
        };
        existing.parts.push(content);
        // 以最新的 context_token 为准（一般更能保证回到当前会话）
        existing.contextToken = contextToken;
        existing.toUserId = fromUserId;

        // 重新计时：idleSeconds 后 flush
        if (existing.timer) clearTimeout(existing.timer);
        existing.timer = setTimeout(() => flushUser(fromUserId), idleSeconds * 1000);
        pending.set(fromUserId, existing);

        const mergedLen = userContentPreview(mergeUserContents(existing.parts || []), 10000).length;
        const currentLen = userContentPreview(content, 10000).length;
        if (currentLen >= immediateChars || mergedLen >= immediateChars) {
          // 超过阈值立即提交
          await flushUser(fromUserId);
        }
      }
    } catch (e) {
      console.log(`[wechat-ilink] loop 异常：${String(e?.message || e)}`);
      await sleep(2000);
    }
  }
}

main().catch((e) => {
  console.error(`[wechat-ilink] fatal: ${String(e?.message || e)}`);
  process.exit(1);
});
