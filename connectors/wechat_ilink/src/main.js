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

function isDirectChatMsg(msg) {
  const gid = msg?.group_id ?? msg?.groupId ?? msg?.room_id ?? msg?.roomId;
  if (gid) return false;
  return true;
}

function buildWechatStyleSystem() {
  return [
    "请用中文回复，语气自然、简洁、温柔但不油腻。",
    "不要输出脑内 OS / 思维过程；只输出给用户看的最终回复。",
    "不要写“小本本/记事本更新”的指令或提示（除非用户明确要求）。",
    "输出尽量分段：优先用换行分条；每条不要太长，方便聊天窗口阅读。",
    "你可以在想发语音的时候发语音：把想让她听到的那句话用 <voice>...</voice> 包起来（不要在里面写分割线或 *）。",
    "你可以同时输出文字正文；连接器会额外发送一条语音。",
    "如果你不想发语音，就不要输出 <voice> 标签。",
  ].join("\n");
}

function resolveWechatWindowId() {
  const tgUserId = envStr("TELEGRAM_PROACTIVE_TARGET_USER_ID", "");
  if (!tgUserId) {
    throw new Error("缺少 TELEGRAM_PROACTIVE_TARGET_USER_ID，无法把微信入口并到 TG 上下文");
  }
  return `tg_${tgUserId}`;
}

async function callGatewayChat(windowId, userText) {
  const base = envStr("GATEWAY_BASE_URL", "http://127.0.0.1:5000").replace(/\/+$/, "");
  const chatPath = envStr("GATEWAY_CHAT_PATH", "/v1/chat/completions");
  const url = base + (chatPath.startsWith("/") ? chatPath : `/${chatPath}`);
  const configuredModel = envStr("GATEWAY_MODEL", "");
  const styleSystem = buildWechatStyleSystem();
  const body = {
    messages: [
      { role: "system", content: styleSystem },
      { role: "user", content: String(userText || "") },
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

async function callGatewayTts(text) {
  const base = envStr("GATEWAY_BASE_URL", "http://127.0.0.1:5000").replace(/\/+$/, "");
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
  if (!r.ok) {
    throw new Error(`TTS 返回 ${r.status}: ${(raw || "").slice(0, 200)}`);
  }
  const audioB64 = String(data?.audio_b64 || "").trim();
  const audioFormat = String(data?.audio_format || "mp3").trim() || "mp3";
  if (!audioB64) return null;
  return {
    audio: Buffer.from(audioB64, "base64"),
    format: audioFormat,
  };
}

function extractVoiceTag(text) {
  const raw = String(text || "");
  const m = raw.match(/<voice>([\s\S]*?)<\/voice>/i);
  if (!m) return { cleanText: raw.trim(), voiceText: "" };
  const voiceText = String(m[1] || "").trim();
  const cleanText = raw.replace(/<voice>[\s\S]*?<\/voice>/gi, "").trim();
  return { cleanText, voiceText };
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

async function uploadVoiceToWeixin(botToken, toUserId, audioBytes) {
  const plaintext = Buffer.from(audioBytes || []);
  const rawsize = plaintext.length;
  const rawfilemd5 = crypto.createHash("md5").update(plaintext).digest("hex");
  const filesize = aesEcbPaddedSize(rawsize);
  const filekey = crypto.randomBytes(16).toString("hex");
  const aeskeyHex = crypto.randomBytes(16).toString("hex");
  const uploadMeta = await getUploadUrl(botToken, {
    filekey,
    media_type: 4,
    to_user_id: String(toUserId || "").trim(),
    rawsize,
    rawfilemd5,
    filesize,
    no_need_thumb: true,
    aeskey: aeskeyHex,
  });
  const uploadParam = String(uploadMeta?.upload_param || "").trim();
  if (!uploadParam) throw new Error("getuploadurl 未返回 upload_param");
  const uploaded = await uploadBufferToCdn(plaintext, uploadParam, filekey, aeskeyHex);
  return {
    encrypt_query_param: uploaded.encryptedParam,
    aes_key: Buffer.from(aeskeyHex, "hex").toString("base64"),
    file_size: rawsize,
    ciphertext_size: uploaded.ciphertextSize,
  };
}

async function sendWeixinVoice(botToken, toUserId, contextToken, uploaded, voiceText = "") {
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
          type: 3,
          voice_item: {
            media: {
              encrypt_query_param: String(uploaded?.encrypt_query_param || "").trim(),
              aes_key: String(uploaded?.aes_key || "").trim(),
              encrypt_type: 1,
            },
            encode_type: 7,
            text: String(voiceText || "").trim(),
            playtime: 0,
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

function splitReplyByNewlineAndLen(text, chunkChars, maxTotalChars) {
  const raw = String(text || "").trim();
  if (!raw) return [];
  const limit = Math.max(20, Number(chunkChars || 100));
  const maxTotal = Math.max(0, Number(maxTotalChars || 0));
  const minStandaloneChars = 10;
  const clipped = maxTotal > 0 && raw.length > maxTotal ? raw.slice(0, maxTotal) : raw;
  const lines = clipped.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  const src = lines.length ? lines : [clipped];
  // 按“换行一条一条”切分；单行过长再按长度硬切
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
  /** @type {Map<string, {parts: string[], toUserId: string, contextToken: string, timer: any, lastApologyAt: number, failureNotified: boolean}>} */
  const pending = new Map();

  async function flushUser(fromUserId) {
    const it = pending.get(fromUserId);
    if (!it) return;
    if (it.timer) {
      clearTimeout(it.timer);
      it.timer = null;
    }
    const merged = it.parts.map((x) => String(x || "").trim()).filter(Boolean).join("\n").trim();
    if (!merged) {
      pending.delete(fromUserId);
      return;
    }

    const windowId = resolveWechatWindowId();
    console.log(`[wechat-ilink] flush from=${fromUserId} window_id=${windowId} chars=${merged.length}`);

    let reply = "";
    let replyClean = "";
    let voiceText = "";
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
      ({ cleanText: replyClean, voiceText } = extractVoiceTag(reply));
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

    if (voiceText) {
      try {
        const ttsResult = await callGatewayTts(voiceText);
        if (ttsResult?.audio?.length) {
          const uploadedVoice = await uploadVoiceToWeixin(botToken, it.toUserId, ttsResult.audio);
          const voiceResp = await sendWeixinVoice(botToken, it.toUserId, it.contextToken, uploadedVoice, voiceText);
          if (!voiceResp.ok) {
            console.log(
              `[wechat-ilink] send voice 失败 ret=${voiceResp.ret} status=${voiceResp.status} body=${voiceResp.body}`
            );
          }
        }
      } catch (e) {
        console.log(`[wechat-ilink] 发送语音失败：${String(e?.message || e)}`);
      }
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
        const text = extractTextFromMsg(msg);
        if (!fromUserId || !contextToken || !text) continue;

        const dedupeKey = `${fromUserId}::${contextToken}`;
        if (dedupe.has(dedupeKey)) continue;
        dedupe.add(dedupeKey);
        if (dedupe.size > dedupeMax) dedupe.clear();

        console.log(`[wechat-ilink] inbound from=${fromUserId} text=${text.slice(0, 60)}`);

        const existing = pending.get(fromUserId) || {
          parts: [],
          toUserId: fromUserId,
          contextToken,
          timer: null,
          lastApologyAt: 0,
          failureNotified: false,
        };
        existing.parts.push(text);
        // 以最新的 context_token 为准（一般更能保证回到当前会话）
        existing.contextToken = contextToken;
        existing.toUserId = fromUserId;

        // 重新计时：idleSeconds 后 flush
        if (existing.timer) clearTimeout(existing.timer);
        existing.timer = setTimeout(() => flushUser(fromUserId), idleSeconds * 1000);
        pending.set(fromUserId, existing);

        const mergedLen = existing.parts.reduce((acc, s) => acc + String(s || "").length, 0);
        if (String(text).length >= immediateChars || mergedLen >= immediateChars) {
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
