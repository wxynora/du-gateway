import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import process from "node:process";
import qrcode from "qrcode-terminal";
import dotenv from "dotenv";

dotenv.config();

function envStr(name, fallback = "") {
  return (process.env[name] || fallback || "").trim();
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
  const qrUrl = `${base}/ilink/bot/get_bot_qrcode?bot_type=3`;
  const r1 = await ilinkGetJson(qrUrl, "");
  const qrcodeToken = String(r1.data?.qrcode || "").trim();
  const qrcodeUrl =
    String(r1.data?.url || r1.data?.qrcode_url || r1.data?.scan_url || "").trim() || "";
  const qrContent = qrcodeUrl || qrcodeToken;
  if (!qrContent) {
    throw new Error(
      `get_bot_qrcode 未返回可用二维码内容(status=${r1.status}) body=${(r1.text || "").slice(0, 220)}`
    );
  }
  qrcode.generate(qrContent, { small: true });
  console.log("[wechat-ilink] 已在终端打印二维码，用微信扫码确认绑定。");
  if (qrcodeUrl) {
    console.log(`[wechat-ilink] （调试）二维码URL=${qrcodeUrl}`);
  }

  while (true) {
    await sleep(1200);
    const stUrl = `${base}/ilink/bot/get_qrcode_status?qrcode=${encodeURIComponent(qrcodeToken)}`;
    const r2 = await ilinkGetJson(stUrl, "");
    const status = String(r2.data?.status || "").trim().toLowerCase();
    if (status) console.log(`[wechat-ilink] login status=${status}`);
    if (status === "confirmed") {
      const botToken = String(r2.data?.bot_token || "").trim();
      if (!botToken) throw new Error("扫码已确认，但未返回 bot_token");
      console.log(`[wechat-ilink] 扫码确认成功 bot_token=${maskToken(botToken)}`);
      return botToken;
    }
  }
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

async function callGatewayChat(windowId, userText) {
  const base = envStr("GATEWAY_BASE_URL", "http://127.0.0.1:5000").replace(/\/+$/, "");
  const chatPath = envStr("GATEWAY_CHAT_PATH", "/v1/chat/completions");
  const url = base + (chatPath.startsWith("/") ? chatPath : `/${chatPath}`);
  const model = envStr("GATEWAY_MODEL", "");
  const body = {
    messages: [{ role: "user", content: String(userText || "") }],
    stream: false,
  };
  if (model) body.model = model;
  const headers = {
    "Content-Type": "application/json",
    "X-Window-Id": String(windowId || "").trim(),
  };
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

function splitReply(text, maxChars) {
  const s = String(text || "").trim();
  if (!s) return [];
  const n = Math.max(100, Number(maxChars || 800));
  if (s.length <= n) return [s];
  const out = [];
  for (let i = 0; i < s.length; i += n) out.push(s.slice(i, i + n));
  return out;
}

async function sendWeixinText(botToken, toUserId, contextToken, text) {
  const payload = {
    msg: {
      to_user_id: String(toUserId || "").trim(),
      message_type: 2,
      message_state: 2,
      context_token: String(contextToken || "").trim(),
      item_list: [{ type: 1, text_item: { text: String(text || "") } }],
    },
  };
  const r = await ilinkPostJson("/ilink/bot/sendmessage", payload, botToken);
  if (r.status < 200 || r.status >= 300) {
    throw new Error(`sendmessage 非 2xx status=${r.status} body=${(r.text || "").slice(0, 200)}`);
  }
  const ret = Number(r.data?.ret ?? 0);
  if (ret !== 0) {
    throw new Error(`sendmessage ret=${ret} body=${JSON.stringify(r.data).slice(0, 200)}`);
  }
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
  const maxReplyChars = Number(envStr("WECHAT_MAX_REPLY_CHARS", "800")) || 800;
  const dedupe = new Set();
  const dedupeMax = 2000;

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

        const windowId = `wechat_${fromUserId}`;
        console.log(`[wechat-ilink] inbound from=${fromUserId} window_id=${windowId} text=${text.slice(0, 60)}`);

        let reply = "";
        try {
          reply = await callGatewayChat(windowId, text);
        } catch (e) {
          reply = "我这边刚刚有点忙，稍后再试一次好吗？";
          console.log(`[wechat-ilink] 调网关失败：${String(e?.message || e)}`);
        }

        const parts = splitReply(reply, maxReplyChars);
        for (const part of parts) {
          await sendWeixinText(botToken, fromUserId, contextToken, part);
          await sleep(250);
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

