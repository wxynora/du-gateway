import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import process from "node:process";
import QRCode from "qrcode";
import dotenv from "dotenv";

dotenv.config();

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
    "你正在微信（WeChat）平台与用户私聊对话。",
    "请用中文回复，语气自然、简洁、温柔但不油腻。",
    "不要输出脑内 OS / 思维过程；只输出给用户看的最终回复。",
    "不要写“小本本/记事本更新”的指令或提示（除非用户明确要求）。",
    "输出尽量分段：优先用换行分条；每条不要太长，方便在微信里阅读。",
  ].join("\n");
}

function trimContextMessages(history, maxTurns) {
  const turns = Math.max(0, Number(maxTurns || 0));
  if (!Array.isArray(history) || turns <= 0) return [];
  const maxMsgs = turns * 2;
  if (history.length <= maxMsgs) return history;
  return history.slice(history.length - maxMsgs);
}

function sanitizeAssistantForContext(text) {
  let s = String(text || "").trim();
  if (!s) return "";
  // 对齐 Telegram 侧“避免污染多轮记忆”的思路：去掉 <voice> 与 [表情包tag] 的外壳（若有）
  s = s.replace(/<voice>[\s\S]*?<\/voice>/gi, "").trim();
  s = s.replace(/\[[a-zA-Z0-9_\-]{1,32}\]/g, "").trim();
  return s;
}

async function callGatewayChat(windowId, userText, historyMessages) {
  const base = envStr("GATEWAY_BASE_URL", "http://127.0.0.1:5000").replace(/\/+$/, "");
  const chatPath = envStr("GATEWAY_CHAT_PATH", "/v1/chat/completions");
  const url = base + (chatPath.startsWith("/") ? chatPath : `/${chatPath}`);
  const model = envStr("GATEWAY_MODEL", "");
  const styleSystem = buildWechatStyleSystem();
  const hist = Array.isArray(historyMessages) ? historyMessages : [];
  const body = {
    messages: [
      { role: "system", content: styleSystem },
      ...hist,
      { role: "user", content: String(userText || "") },
    ],
    stream: false,
  };
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

function splitReplyByNewlineAndLen(text, chunkChars, maxTotalChars) {
  const raw = String(text || "").trim();
  if (!raw) return [];
  const limit = Math.max(20, Number(chunkChars || 100));
  const maxTotal = Math.max(0, Number(maxTotalChars || 0));
  const clipped = maxTotal > 0 && raw.length > maxTotal ? raw.slice(0, maxTotal) : raw;
  const lines = clipped.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  const src = lines.length ? lines : [clipped];
  const out = [];
  for (const line of src) {
    if (line.length <= limit) {
      out.push(line);
      continue;
    }
    for (let i = 0; i < line.length; i += limit) {
      out.push(line.slice(i, i + limit));
    }
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
  const idleSeconds = Math.max(1, envInt("WECHAT_INPUT_IDLE_SECONDS", 15));
  const immediateChars = Math.max(20, envInt("WECHAT_INPUT_IMMEDIATE_CHARS", 200));
  const outChunkChars = Math.max(20, envInt("WECHAT_OUTPUT_CHUNK_CHARS", 100));
  const maxReplyTotalChars = Math.max(0, envInt("WECHAT_MAX_REPLY_TOTAL_CHARS", 4000));
  const dedupe = new Set();
  const dedupeMax = 2000;

  // 输入聚合（参考 Telegram）：同一用户 15s 内多条合并成一次请求
  /** @type {Map<string, {parts: string[], toUserId: string, contextToken: string, timer: any, lastApologyAt: number}>} */
  const pending = new Map();

  // 上下文缓存（参考 Telegram）：每个用户维护最近 N 轮 user/assistant
  /** @type {Map<string, {messages: any[]}>} */
  const ctx = new Map();
  const contextLastTurns = Math.max(0, envInt("WECHAT_CONTEXT_LAST_TURNS", 4));

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

    const windowId = `wechat_${fromUserId}`;
    console.log(`[wechat-ilink] flush from=${fromUserId} window_id=${windowId} chars=${merged.length}`);

    let reply = "";
    let ok = false;
    try {
      const history = trimContextMessages(ctx.get(fromUserId)?.messages || [], contextLastTurns);
      reply = await callGatewayChat(windowId, merged, history);
      ok = true;
    } catch (e) {
      ok = false;
      console.log(`[wechat-ilink] 调网关失败：${String(e?.message || e)}`);
    }

    if (!ok) {
      // 失败兜底：保留 pending，下次新消息触发时会一起合并再试；同时尽量只偶尔提示一次
      const now = Date.now();
      const shouldApologize = now - (it.lastApologyAt || 0) > 30_000;
      if (shouldApologize) {
        it.lastApologyAt = now;
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

    const chunks = splitReplyByNewlineAndLen(reply, outChunkChars, maxReplyTotalChars);
    for (const part of chunks) {
      await sendWeixinText(botToken, it.toUserId, it.contextToken, part);
      await sleep(250);
    }

    // 成功后更新上下文缓存（对齐 Telegram）：只缓存 user/assistant，不缓存 system
    try {
      const cur = Array.isArray(ctx.get(fromUserId)?.messages) ? [...ctx.get(fromUserId).messages] : [];
      cur.push({ role: "user", content: merged });
      const forCtx = sanitizeAssistantForContext(reply) || reply;
      cur.push({ role: "assistant", content: forCtx });
      ctx.set(fromUserId, { messages: trimContextMessages(cur, contextLastTurns) });
    } catch {
      // ignore
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

