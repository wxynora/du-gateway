import { MiGPT } from "@mi-gpt/next";

const env = process.env;

const XIAOMI_USER_ID = (env.XIAOMI_USER_ID || "").trim();
const XIAOMI_PASSWORD = (env.XIAOMI_PASSWORD || "").trim();
const XIAOMI_PASS_TOKEN = (env.XIAOMI_PASS_TOKEN || "").trim();
const XIAOAI_DID = (env.XIAOAI_DID || "").trim();
const XIAOAI_SPEAKER = (env.XIAOAI_SPEAKER || XIAOAI_DID || "小爱音箱").trim();
const XIAOAI_RUNNER_NAME = (env.XIAOAI_RUNNER_NAME || "xiaoai-migpt").trim();
const XIAOAI_GATEWAY_TOKEN = (env.XIAOAI_GATEWAY_TOKEN || "").trim();
const DU_GATEWAY_URL = (env.DU_GATEWAY_URL || "").trim().replace(/\/+$/, "");
const DU_WINDOW_ID = (env.DU_WINDOW_ID || "").trim();

const HEARTBEAT_MS = positiveInt(env.XIAOAI_HEARTBEAT_MS, 1000, 1000);
const CONFIG_REFRESH_MS = positiveInt(env.XIAOAI_CONFIG_REFRESH_MS, 30000, 3000);
const ACTION_POLL_MS = positiveInt(env.XIAOAI_ACTION_POLL_MS, 5000, 1000);
const ACTION_CLAIM_WAIT_SECONDS = positiveInt(env.XIAOAI_ACTION_CLAIM_WAIT_SECONDS, 12, 0);
const ACTION_CLAIM_TIMEOUT_MS = positiveInt(
  env.XIAOAI_ACTION_CLAIM_TIMEOUT_MS,
  Math.max(15000, (ACTION_CLAIM_WAIT_SECONDS + 10) * 1000),
  1000,
);
const SESSION_TTL_SECONDS = positiveInt(env.XIAOAI_SESSION_TTL_SECONDS, 60, 0);
const DEDUP_TTL_MS = positiveInt(env.XIAOAI_DEDUP_TTL_MS, 10000, 1000);
const MUTE_RESTORE_FALLBACK_VOLUME = volumeInt(env.XIAOAI_MUTE_RESTORE_FALLBACK_VOLUME, 35);
const MUTE_VOLUME_READ_TIMEOUT_MS = positiveInt(env.XIAOAI_MUTE_VOLUME_READ_TIMEOUT_MS, 250, 50);
const MIN_PLAY_VOLUME = volumeInt(env.XIAOAI_MIN_PLAY_VOLUME, 20);
const PLAY_URL_STRATEGY = (env.XIAOAI_PLAY_URL_STRATEGY || "auto").trim().toLowerCase();
const PLAY_MUSIC_AUDIO_ID = (env.XIAOAI_PLAY_MUSIC_AUDIO_ID || "").trim();
const PLAY_MUSIC_CP_ID = (env.XIAOAI_PLAY_MUSIC_CP_ID || "355454500").trim();
const PLAY_LOOP_TYPE = positiveInt(env.XIAOAI_PLAY_LOOP_TYPE, 3, 0);
const PLAY_AUTO_STOP_PADDING_MS = positiveInt(env.XIAOAI_PLAY_AUTO_STOP_PADDING_MS, 800, 0);
const PLAY_AUTO_STOP_FALLBACK_MS = positiveInt(env.XIAOAI_PLAY_AUTO_STOP_FALLBACK_MS, 8000, 1000);
const PLAY_AUTO_STOP_MAX_MS = positiveInt(env.XIAOAI_PLAY_AUTO_STOP_MAX_MS, 60000, 5000);
const PLAY_MUSIC_HARDWARES = new Set(["LX04", "LX05", "L05B", "L05C", "L06", "L06A", "X08A", "X10A", "X08C", "X08E", "X8F"]);
const VOLUME_MEDIA_TARGETS = ["app_ios", "common", ""];

let currentConfig = {
  enabled: true,
  mute_native_reply: false,
  entry_phrases: ["请求连接渡", "请求连接度"],
  exit_phrases: ["退出渡"],
};
let lastConfigFetchAt = 0;
let sessionExpiresAt = 0;
let actionPollInFlight = false;
let playbackStopTimer = null;
const recentMessages = new Map();

function positiveInt(value, fallback, minimum) {
  const n = Number(value || fallback);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(minimum, Math.floor(n));
}

function volumeInt(value, fallback) {
  const n = Number(value ?? fallback);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(0, Math.min(100, Math.round(n)));
}

function asBool(value, fallback = false) {
  if (typeof value === "string") {
    const s = value.trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(s)) return true;
    if (["0", "false", "no", "off"].includes(s)) return false;
  }
  if (value === undefined || value === null) return fallback;
  return !!value;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function requireEnv() {
  const missing = [];
  if (!XIAOAI_DID) missing.push("XIAOAI_DID");
  if (!XIAOMI_PASS_TOKEN && !XIAOMI_USER_ID) missing.push("XIAOMI_USER_ID 或 XIAOMI_PASS_TOKEN");
  if (!XIAOMI_PASS_TOKEN && !XIAOMI_PASSWORD) missing.push("XIAOMI_PASSWORD 或 XIAOMI_PASS_TOKEN");
  if (!DU_GATEWAY_URL) missing.push("DU_GATEWAY_URL");
  if (missing.length) {
    throw new Error(`缺少环境变量：${missing.join(", ")}`);
  }
}

function normalizePhraseList(value, fallback) {
  const raw = Array.isArray(value) ? value : [];
  const seen = new Set();
  const items = [];
  for (const item of raw) {
    const text = String(item || "").trim();
    if (!text || seen.has(text)) continue;
    seen.add(text);
    items.push(text);
  }
  return items.length ? items : fallback;
}

function addEntryPhraseAliases(phrases) {
  const seen = new Set();
  const items = [];
  for (const phrase of phrases || []) {
    const text = String(phrase || "").trim();
    if (!text) continue;
    for (const candidate of [text, text.replaceAll("渡", "度")]) {
      if (!candidate || seen.has(candidate)) continue;
      seen.add(candidate);
      items.push(candidate);
    }
  }
  return items.length ? items : ["请求连接渡", "请求连接度"];
}

function normalizeGatewayConfig(data) {
  const cfg = data?.config && typeof data.config === "object" ? data.config : {};
  return {
    enabled: !!cfg.enabled,
    mute_native_reply: asBool(cfg.mute_native_reply, false),
    entry_phrases: addEntryPhraseAliases(normalizePhraseList(cfg.entry_phrases, ["请求连接渡"])),
    exit_phrases: normalizePhraseList(cfg.exit_phrases, ["退出渡"]),
  };
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  if (XIAOAI_GATEWAY_TOKEN) headers.Authorization = `Bearer ${XIAOAI_GATEWAY_TOKEN}`;
  return headers;
}

async function gatewayJson(path, init = {}) {
  const { timeoutMs, ...fetchInit } = init || {};
  const timeout = Number(timeoutMs || 0);
  const controller = timeout > 0 ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), timeout) : null;
  try {
    const res = await fetch(`${DU_GATEWAY_URL}${path}`, {
      ...fetchInit,
      headers: authHeaders(fetchInit.headers || {}),
      signal: fetchInit.signal || controller?.signal,
    });
    const text = await res.text();
    let data = {};
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { raw: text };
      }
    }
    if (!res.ok) {
      const msg = data?.error?.message || data?.error || data?.message || `HTTP ${res.status}`;
      throw new Error(String(msg));
    }
    return data;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

async function refreshConfig(force = false) {
  const now = Date.now();
  if (!force && now - lastConfigFetchAt < CONFIG_REFRESH_MS) return currentConfig;
  try {
    const data = await gatewayJson("/api/xiaoai/config");
    currentConfig = normalizeGatewayConfig(data);
    lastConfigFetchAt = now;
  } catch (e) {
    console.warn("[xiaoai] 拉取配置失败：", e?.message || e);
    lastConfigFetchAt = 0;
    await postLog("warn", "拉取小爱配置失败", { error: e?.message || String(e), event: "config_error" });
  }
  return currentConfig;
}

async function postStatus(fields = {}) {
  try {
    await gatewayJson("/api/xiaoai/status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        connected: true,
        runner: XIAOAI_RUNNER_NAME,
        speaker: XIAOAI_SPEAKER,
        ...fields,
      }),
    });
  } catch (e) {
    console.warn("[xiaoai] 上报状态失败：", e?.message || e);
  }
}

async function postLog(level, message, fields = {}) {
  try {
    await gatewayJson("/api/xiaoai/logs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        level,
        message,
        runner: XIAOAI_RUNNER_NAME,
        speaker: XIAOAI_SPEAKER,
        ...fields,
      }),
    });
  } catch (e) {
    console.warn("[xiaoai] 上报日志失败：", e?.message || e);
  }
}

function stripPrefixText(raw, prefix) {
  const rest = String(raw || "").slice(prefix.length);
  return rest.replace(/^[\s,，。.!！?？:：;；-]+/, "").trim();
}

function matchPrefix(raw, phrases) {
  const text = String(raw || "").trim();
  for (const phrase of phrases || []) {
    if (text.startsWith(phrase)) {
      return { phrase, rest: stripPrefixText(text, phrase) };
    }
  }
  return null;
}

function isExitText(raw, phrases) {
  const text = String(raw || "").trim();
  return (phrases || []).some((phrase) => text === phrase || text.startsWith(`${phrase}，`) || text.startsWith(`${phrase},`));
}

function isDuplicate(speaker, text) {
  const key = `${speaker}:${String(text || "").trim()}`;
  const now = Date.now();
  const last = recentMessages.get(key) || 0;
  recentMessages.set(key, now);
  for (const [k, ts] of recentMessages) {
    if (now - ts > DEDUP_TTL_MS * 3) recentMessages.delete(k);
  }
  return now - last < DEDUP_TTL_MS;
}

function withTimeout(promise, ms, fallback) {
  return Promise.race([promise, sleep(ms).then(() => fallback)]);
}

async function safeAbort(engine) {
  try {
    await engine.speaker.abortXiaoAI();
  } catch (e) {
    console.warn("[xiaoai] abortXiaoAI 失败：", e?.message || e);
  }
}

function parseVolume(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return volumeInt(n, 0);
}

function parseStatusInfo(info) {
  if (!info) return {};
  if (typeof info === "object") return info;
  if (typeof info !== "string") return {};
  try {
    return JSON.parse(info);
  } catch {
    return {};
  }
}

async function getSpeakerVolume(engine) {
  try {
    if (engine.MiNA?.getVolume) {
      const volume = parseVolume(await engine.MiNA.getVolume());
      if (volume !== null) return volume;
    }
  } catch (e) {
    console.warn("[xiaoai] 读取当前音量失败：", e?.message || e);
  }
  try {
    if (engine.MiNA?.callUbus) {
      for (const media of VOLUME_MEDIA_TARGETS) {
        const payload = media ? { media } : undefined;
        const res = await engine.MiNA.callUbus("mediaplayer", "player_get_play_status", payload);
        const info = parseStatusInfo(res?.info);
        const volume = parseVolume(info?.volume);
        if (volume !== null) return volume;
      }
    }
  } catch (e) {
    console.warn("[xiaoai] 读取播放状态音量失败：", e?.message || e);
  }
  return null;
}

async function setSpeakerVolume(engine, volume) {
  const nextVolume = volumeInt(volume, MUTE_RESTORE_FALLBACK_VOLUME);
  let lastResult = null;
  let lastError = null;
  try {
    if (engine.MiNA?.callUbus) {
      let ok = false;
      for (const media of VOLUME_MEDIA_TARGETS) {
        const payload = media ? { volume: nextVolume, media } : { volume: nextVolume };
        try {
          const res = await engine.MiNA.callUbus("mediaplayer", "player_set_volume", payload);
          lastResult = res;
          if (typeof res === "boolean" ? res : res?.code === 0 || res?.data?.code === 0) {
            ok = true;
          }
        } catch (e) {
          lastError = e;
        }
      }
      if (ok) return true;
    }
    if (engine.MiNA?.setVolume) {
      return !!(await engine.MiNA.setVolume(nextVolume));
    }
  } catch (e) {
    lastError = e;
  }
  console.warn(`[xiaoai] 设置音量 ${nextVolume} 失败：`, lastError?.message || lastError || formatPlayResult(lastResult));
  return false;
}

async function ensureSpeakerAudible(engine, reason) {
  try {
    if (engine.MiOT?.setProperty) {
      await engine.MiOT.setProperty(2, 2, false);
    }
  } catch (e) {
    console.warn("[xiaoai] 解除音箱静音失败：", e?.message || e);
    await postLog("warn", "解除音箱静音失败", { event: "play_unmute_failed", text: reason, error: e?.message || String(e) });
  }

  try {
    let volume = null;
    if (engine.MiOT?.getProperty) {
      volume = parseVolume(await engine.MiOT.getProperty(2, 1));
    }
    if (volume === null) {
      volume = await withTimeout(getSpeakerVolume(engine), MUTE_VOLUME_READ_TIMEOUT_MS, null);
    }
    if (volume !== null && volume < MIN_PLAY_VOLUME) {
      await setSpeakerVolume(engine, MIN_PLAY_VOLUME);
    }
  } catch (e) {
    console.warn("[xiaoai] 播放前音量检查失败：", e?.message || e);
  }
}

async function muteNativeReplyVolume(engine, reason) {
  const originalVolume = await withTimeout(getSpeakerVolume(engine), MUTE_VOLUME_READ_TIMEOUT_MS, null);
  const restoreVolume = originalVolume ?? MUTE_RESTORE_FALLBACK_VOLUME;
  const ok = await setSpeakerVolume(engine, 0);
  const state = {
    active: ok,
    restored: false,
    originalVolume,
    restoreVolume,
  };
  if (ok) {
    console.log("[xiaoai] 入口静音：", `volume=${restoreVolume}`, `reason=${reason}`);
    await postLog("info", originalVolume === null ? "入口静音已启用：使用兜底音量恢复" : "入口静音已启用", { event: "entry_mute", text: reason });
  } else {
    await postLog("warn", "入口静音失败", { event: "entry_mute_failed", text: reason });
  }
  return state;
}

async function restoreNativeReplyVolume(engine, muteState, reason) {
  if (!muteState?.active || muteState.restored) return true;
  muteState.restored = true;
  const ok = await setSpeakerVolume(engine, muteState.restoreVolume);
  if (ok) {
    console.log("[xiaoai] 恢复入口静音音量：", `volume=${muteState.restoreVolume}`, `reason=${reason}`);
  } else {
    await postLog("warn", "恢复入口静音音量失败", { event: "entry_volume_restore_failed", text: reason, error: `volume=${muteState.restoreVolume}` });
  }
  return ok;
}

function formatPlayResult(result) {
  try {
    return JSON.stringify(result).slice(0, 500);
  } catch {
    return String(result);
  }
}

function getSpeakerHardware(engine) {
  return String(engine?.MiNA?.account?.device?.hardware || "").trim().toUpperCase();
}

function shouldUseMusicApi(engine) {
  if (PLAY_URL_STRATEGY === "music") return true;
  if (PLAY_URL_STRATEGY === "url") return false;
  return PLAY_MUSIC_HARDWARES.has(getSpeakerHardware(engine));
}

function musicAudioIdForUrl(url) {
  if (PLAY_MUSIC_AUDIO_ID) return PLAY_MUSIC_AUDIO_ID;
  let h = 1469598103934665603n;
  for (const ch of String(url || "")) {
    h ^= BigInt(ch.charCodeAt(0));
    h = BigInt.asUintN(64, h * 1099511628211n);
  }
  return String((h % 9000000000000000n) + 1000000000000000n);
}

async function stopPlayback(engine, reason = "") {
  if (!engine.MiNA?.callUbus) return false;
  try {
    const res = await engine.MiNA.callUbus("mediaplayer", "player_play_operation", { action: "stop", media: "app_ios" });
    const ok = typeof res === "boolean" ? res : res?.code === 0 || res?.data?.code === 0;
    console.log("[xiaoai] 停止播放：", ok ? "ok" : formatPlayResult(res), reason ? `reason=${reason}` : "");
    return !!ok;
  } catch (e) {
    console.warn("[xiaoai] 停止播放失败：", e?.message || e);
    return false;
  }
}

async function verifyMusicPlayback(engine, expectedAudioId) {
  await sleep(500);
  const status = await getRawPlaybackStatus(engine);
  const actualAudioId = String(status?.play_song_detail?.audio_id || "").trim();
  if (actualAudioId && actualAudioId !== String(expectedAudioId || "")) {
    console.warn("[xiaoai] player_play_music audio_id 不匹配：", `expected=${expectedAudioId}`, `actual=${actualAudioId}`);
    await stopPlayback(engine, "music_audio_id_mismatch");
    await postLog("warn", "小爱可能误播小米音乐，已停止", {
      event: "music_audio_id_mismatch",
      error: `expected=${expectedAudioId} actual=${actualAudioId}`,
    });
    return false;
  }
  return true;
}

function shouldFallbackToTextForAudioUrl() {
  if (PLAY_URL_STRATEGY === "music") return true;
  if (PLAY_URL_STRATEGY === "auto") return true;
  return false;
}

function buildMusicPayload(url) {
  const audioId = musicAudioIdForUrl(url);
  return {
    audioId,
    startaudioid: audioId,
    music: JSON.stringify({
      payload: {
        audio_type: "",
        audio_items: [
          {
            item_id: {
              audio_id: audioId,
              cp: {
                album_id: "-1",
                episode_index: 0,
                id: PLAY_MUSIC_CP_ID || "355454500",
                name: "xiaowei",
              },
            },
            stream: { url },
          },
        ],
        list_params: {
          listId: "-1",
          loadmore_offset: 0,
          origin: "xiaowei",
          type: "MUSIC",
        },
      },
      play_behavior: "REPLACE_ALL",
    }),
  };
}

async function playUrlByMusicApi(engine, audioUrl, fallbackText) {
  if (!engine.MiNA?.callUbus) return false;
  await setPlaybackLoopMode(engine, PLAY_LOOP_TYPE);
  const payload = buildMusicPayload(audioUrl);
  const audioId = payload.audioId;
  delete payload.audioId;
  const res = await engine.MiNA.callUbus("mediaplayer", "player_play_music", payload);
  const ok = typeof res === "boolean" ? res : res?.code === 0 || res?.data?.code === 0;
  console.log("[xiaoai] 播放 URL(player_play_music) 结果：", ok ? "ok" : formatPlayResult(res), `audio_id=${audioId}`);
  if (ok && !(await verifyMusicPlayback(engine, audioId))) return false;
  if (ok) schedulePlaybackStop(engine, fallbackText || audioUrl);
  return !!ok;
}

async function playUrlByPlainUrl(engine, audioUrl) {
  if (!engine.MiNA?.callUbus) {
    return !!(await engine.speaker.play({ url: audioUrl }));
  }
  const payloads = [
    { url: audioUrl, type: 1, media: "app_ios" },
    { url: audioUrl, type: 1, media: "common" },
    { url: audioUrl, type: 1 },
  ];
  for (const payload of payloads) {
    const res = await engine.MiNA.callUbus("mediaplayer", "player_play_url", payload);
    const ok = typeof res === "boolean" ? res : res?.code === 0 || res?.data?.code === 0;
    console.log("[xiaoai] 播放 URL(player_play_url) 结果：", ok ? "ok" : formatPlayResult(res), `media=${payload.media || "default"}`);
    if (ok) {
      return true;
    }
  }
  return false;
}

async function setPlaybackLoopMode(engine, loopType) {
  if (!engine.MiNA?.callUbus) return false;
  try {
    const res = await engine.MiNA.callUbus("mediaplayer", "player_set_loop", { media: "common", type: loopType });
    const ok = typeof res === "boolean" ? res : res?.code === 0 || res?.data?.code === 0;
    console.log("[xiaoai] 设置播放循环模式：", loopType, ok ? "ok" : formatPlayResult(res));
    return !!ok;
  } catch (e) {
    console.warn("[xiaoai] 设置播放循环模式失败：", e?.message || e);
    return false;
  }
}

async function getRawPlaybackStatus(engine) {
  if (!engine.MiNA?.callUbus) return {};
  try {
    const res = await engine.MiNA.callUbus("mediaplayer", "player_get_play_status", { media: "app_ios" });
    return parseStatusInfo(res?.info);
  } catch (e) {
    console.warn("[xiaoai] 读取原始播放状态失败：", e?.message || e);
    return {};
  }
}

function estimatePlaybackStopMs(reason) {
  const text = String(reason || "").trim();
  if (!text) return PLAY_AUTO_STOP_FALLBACK_MS;
  return Math.min(PLAY_AUTO_STOP_MAX_MS, Math.max(PLAY_AUTO_STOP_FALLBACK_MS, text.length * 300 + 1500));
}

function schedulePlaybackStop(engine, reason) {
  if (playbackStopTimer) {
    clearTimeout(playbackStopTimer);
    playbackStopTimer = null;
  }
  playbackStopTimer = setTimeout(async () => {
    try {
      await setPlaybackLoopMode(engine, PLAY_LOOP_TYPE);
      const status = await getRawPlaybackStatus(engine);
      const detail = status?.play_song_detail || {};
      const duration = Number(detail.duration);
      const position = Number(detail.position || 0);
      let delay = estimatePlaybackStopMs(reason);
      if (Number.isFinite(duration) && duration > 0) {
        delay = Math.max(500, duration - (Number.isFinite(position) ? position : 0) + PLAY_AUTO_STOP_PADDING_MS);
      }
      delay = Math.min(PLAY_AUTO_STOP_MAX_MS, Math.max(500, Math.round(delay)));
      console.log("[xiaoai] 安排播放结束自动停止：", `delay=${delay}`, `duration=${duration || ""}`, `position=${position || ""}`);
      playbackStopTimer = setTimeout(async () => {
        playbackStopTimer = null;
        try {
          await stopPlayback(engine, "auto_stop");
        } catch (e) {
          console.warn("[xiaoai] 播放结束自动停止失败：", e?.message || e);
        }
      }, delay);
    } catch (e) {
      playbackStopTimer = null;
      console.warn("[xiaoai] 安排播放结束自动停止失败：", e?.message || e);
    }
  }, 600);
}

async function logPlaybackStatus(engine) {
  try {
    if (!engine.MiNA?.getStatus) return;
    const status = await engine.MiNA.getStatus();
    console.log("[xiaoai] 播放后状态：", formatPlayResult(status));
  } catch (e) {
    console.warn("[xiaoai] 读取播放状态失败：", e?.message || e);
  }
}

async function safePlayText(engine, text) {
  const content = String(text || "").trim();
  if (!content) return false;
  await ensureSpeakerAudible(engine, content);
  if (engine.MiOT?.doAction) {
    try {
      console.log("[xiaoai] MIoT 播放文字：", content);
      const ok = await engine.MiOT.doAction(5, 3, content);
      console.log("[xiaoai] MIoT 播放文字结果：", ok ? "ok" : "false");
      if (ok) return true;
    } catch (e) {
      console.warn("[xiaoai] MIoT 播放文本失败：", e?.message || e);
    }
  }
  try {
    console.log("[xiaoai] 播放文字：", content);
    const res = engine.MiNA?.callUbus
      ? await engine.MiNA.callUbus("mibrain", "text_to_speech", { text: content, save: 0 })
      : await engine.speaker.play({ text: content });
    const ok = typeof res === "boolean" ? res : res?.code === 0;
    console.log("[xiaoai] 播放文字结果：", ok ? "ok" : formatPlayResult(res));
    await logPlaybackStatus(engine);
    return !!ok;
  } catch (e) {
    console.warn("[xiaoai] 播放文本失败：", e?.message || e);
    return false;
  }
}

async function safePlayUrl(engine, url, fallbackText) {
  const audioUrl = String(url || "").trim();
  if (!audioUrl) {
    return safePlayText(engine, fallbackText);
  }
  await ensureSpeakerAudible(engine, fallbackText || audioUrl);
  try {
    let ok = false;
    if (shouldUseMusicApi(engine)) {
      ok = await playUrlByMusicApi(engine, audioUrl, fallbackText);
    } else {
      ok = await playUrlByPlainUrl(engine, audioUrl);
      if (!ok) ok = await playUrlByMusicApi(engine, audioUrl, fallbackText);
    }
    await logPlaybackStatus(engine);
    if (!ok) {
      return shouldFallbackToTextForAudioUrl() ? safePlayText(engine, fallbackText) : false;
    }
    return true;
  } catch (e) {
    console.warn("[xiaoai] 播放 URL 失败：", e?.message || e);
    await postLog("warn", "播放音频 URL 失败，回退文字播报", { error: e?.message || String(e), audio_url: audioUrl, event: "play_url_error" });
    return safePlayText(engine, fallbackText);
  }
}

async function claimActions() {
  const data = await gatewayJson("/api/xiaoai/actions/claim", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      runner: XIAOAI_RUNNER_NAME,
      limit: 3,
      wait_seconds: ACTION_CLAIM_WAIT_SECONDS,
    }),
    timeoutMs: ACTION_CLAIM_TIMEOUT_MS,
  });
  return Array.isArray(data?.actions) ? data.actions : [];
}

async function reportActionResult(action, ok, error = "", detail = {}) {
  const actionId = String(action?.id || "").trim();
  if (!actionId) return;
  await gatewayJson(`/api/xiaoai/actions/${encodeURIComponent(actionId)}/result`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ok: !!ok,
      runner: XIAOAI_RUNNER_NAME,
      error: String(error || ""),
      detail,
    }),
  });
}

async function executeAction(engine, action) {
  const type = String(action?.type || "").trim();
  const text = String(action?.text || "").trim();
  const audioUrl = String(action?.audio_url || "").trim();
  console.log("[xiaoai] 执行队列动作：", action?.id || "", type, text || audioUrl);
  try {
    let ok = false;
    if (type === "play_url") {
      ok = await safePlayUrl(engine, audioUrl, text);
    } else if (type === "speak_text") {
      ok = await safePlayText(engine, text);
    } else {
      throw new Error(`未知动作类型：${type || "<empty>"}`);
    }
    await reportActionResult(action, ok, ok ? "" : "播放命令返回失败", { type });
  } catch (e) {
    const message = e?.message || String(e);
    console.warn("[xiaoai] 执行动作失败：", message);
    await reportActionResult(action, false, message, { type });
  }
}

async function pollActions(engine) {
  if (actionPollInFlight) return;
  // Only claim actions after MiNA is initialized; otherwise the queue item gets
  // consumed before the speaker can actually play it.
  if (!engine?.MiNA) return;
  actionPollInFlight = true;
  try {
    const actions = await claimActions();
    for (const action of actions) {
      await executeAction(engine, action);
    }
  } catch (e) {
    console.warn("[xiaoai] 轮询播放队列失败：", e?.message || e);
  } finally {
    actionPollInFlight = false;
  }
}

function isLocalCommandText(userText) {
  const text = String(userText || "").trim();
  return /^音量\s*\d{1,3}$/.test(text) || ["暂停", "暂停播放", "继续", "继续播放", "停止", "停止播放"].includes(text);
}

async function handleLocalCommand(engine, userText) {
  const volumeMatch = String(userText || "").match(/^音量\s*(\d{1,3})$/);
  if (volumeMatch) {
    const volume = Math.max(0, Math.min(100, Number(volumeMatch[1])));
    await setSpeakerVolume(engine, volume);
    await safePlayText(engine, `音量已调到 ${volume}`);
    await postLog("info", "本地音量控制", { text: userText, event: "local_volume" });
    return true;
  }
  if (["暂停", "暂停播放"].includes(userText)) {
    await engine.MiNA.pause();
    await postLog("info", "本地暂停播放", { text: userText, event: "local_pause" });
    return true;
  }
  if (["继续", "继续播放"].includes(userText)) {
    await engine.MiNA.play();
    await postLog("info", "本地继续播放", { text: userText, event: "local_play" });
    return true;
  }
  if (["停止", "停止播放"].includes(userText)) {
    await engine.MiNA.stop();
    await postLog("info", "本地停止播放", { text: userText, event: "local_stop" });
    return true;
  }
  return false;
}

async function sendToDuGateway(userText) {
  const headers = {
    "Content-Type": "application/json",
  };
  if (DU_WINDOW_ID) headers["X-Window-Id"] = DU_WINDOW_ID;
  return gatewayJson("/api/xiaoai/message", {
    method: "POST",
    headers,
    body: JSON.stringify({
      text: userText,
      speaker: XIAOAI_SPEAKER,
      source: "xiaoai",
      window_id: DU_WINDOW_ID,
    }),
  });
}

async function onMessage(engine, msg) {
  const raw = String(msg?.text || "").trim();
  if (!raw) return { handled: true };

  const quickEntryMatch = matchPrefix(raw, currentConfig.entry_phrases);
  const quickInSession = SESSION_TTL_SECONDS > 0 && Date.now() < sessionExpiresAt;
  let muteState = null;
  if ((quickEntryMatch || quickInSession) && currentConfig.mute_native_reply) {
    muteState = await muteNativeReplyVolume(engine, quickEntryMatch ? quickEntryMatch.phrase : "session");
  }

  const cfg = await refreshConfig(false);
  const entryMatch = matchPrefix(raw, cfg.entry_phrases);
  const inSession = SESSION_TTL_SECONDS > 0 && Date.now() < sessionExpiresAt;
  console.log("[xiaoai] 收到消息：", raw, "entry=", entryMatch ? entryMatch.phrase : "", "session=", inSession ? "yes" : "no", "enabled=", cfg.enabled ? "yes" : "no");

  if (!cfg.enabled) {
    await restoreNativeReplyVolume(engine, muteState, "disabled");
    if (entryMatch) {
      console.warn("[xiaoai] 入口已关闭，忽略：", raw);
      await postLog("warn", "App 里小爱入口未启用，已忽略", { text: raw, event: "disabled" });
    }
    return { handled: true };
  }

  if (isExitText(raw, cfg.exit_phrases)) {
    sessionExpiresAt = 0;
    await safeAbort(engine);
    await restoreNativeReplyVolume(engine, muteState, "exit");
    await safePlayText(engine, "已退出渡。");
    await postStatus({ last_event: "exit", last_text: raw });
    await postLog("info", "退出渡模式", { text: raw, event: "exit" });
    return { handled: true };
  }

  if (!entryMatch && !inSession) {
    await restoreNativeReplyVolume(engine, muteState, "ignored");
    return { handled: true };
  }

  if (!muteState && cfg.mute_native_reply) {
    muteState = await muteNativeReplyVolume(engine, entryMatch ? entryMatch.phrase : "session");
  }

  await safeAbort(engine);

  let userText = entryMatch ? entryMatch.rest : raw;
  console.log("[xiaoai] 进入渡链路，文本：", userText || "<empty>");
  if (SESSION_TTL_SECONDS > 0) {
    sessionExpiresAt = Date.now() + SESSION_TTL_SECONDS * 1000;
  }

  if (!userText) {
    await restoreNativeReplyVolume(engine, muteState, "connected_prompt");
    await safePlayText(engine, "已连接渡，你说。");
    await postStatus({ last_event: "connected_prompt", last_text: raw });
    return { handled: true };
  }

  if (isDuplicate(XIAOAI_SPEAKER, userText)) {
    await restoreNativeReplyVolume(engine, muteState, "dedup");
    await postLog("info", "重复消息已忽略", { text: userText, event: "dedup" });
    return { handled: true };
  }

  if (isLocalCommandText(userText)) {
    await restoreNativeReplyVolume(engine, muteState, "before_local_command");
  }
  if (await handleLocalCommand(engine, userText)) {
    return { handled: true };
  }

  await postStatus({ last_event: "forward", last_text: userText });

  try {
    const data = await sendToDuGateway(userText);
    if (!data?.ok) {
      const text = data?.speak_text || "渡暂时无法接通。";
      await postLog("warn", "网关返回失败", { text: userText, error: data?.error?.message || data?.error || "", event: "gateway_bad_response" });
      await restoreNativeReplyVolume(engine, muteState, "gateway_bad_response");
      await safePlayText(engine, text);
      return { handled: true };
    }
    const voiceText = data.voice_text || "渡暂时说不出话。";
    await restoreNativeReplyVolume(engine, muteState, data.audio_url ? "before_play_audio" : "before_play_text");
    await safePlayUrl(engine, data.audio_url, voiceText);
    await postStatus({ last_event: data.audio_url ? "play_audio" : "play_text", last_text: userText, last_audio_url: data.audio_url || "" });
  } catch (e) {
    const message = e?.message || String(e);
    console.warn("[xiaoai] 转发网关失败：", message);
    await postStatus({ last_event: "gateway_error", last_text: userText, last_error: message });
    await postLog("error", "转发网关失败", { text: userText, error: message, event: "gateway_error" });
    await restoreNativeReplyVolume(engine, muteState, "gateway_error");
    await safePlayText(engine, "渡暂时无法接通。");
  }
  return { handled: true };
}

async function main() {
  requireEnv();
  await refreshConfig(true);
  await postStatus({ last_event: "runner_start" });
  await postLog("info", "MiGPT runner 已启动", { event: "runner_start" });
  setInterval(() => {
    void refreshConfig(false);
    void postStatus({ last_event: "heartbeat" });
  }, Math.max(HEARTBEAT_MS, CONFIG_REFRESH_MS));
  setInterval(() => {
    void pollActions(MiGPT);
  }, ACTION_POLL_MS);

  const speaker = {
    did: XIAOAI_DID,
    heartbeat: HEARTBEAT_MS,
  };
  if (XIAOMI_PASS_TOKEN) {
    speaker.passToken = XIAOMI_PASS_TOKEN;
    if (XIAOMI_USER_ID) speaker.userId = XIAOMI_USER_ID;
  } else {
    speaker.userId = XIAOMI_USER_ID;
    speaker.password = XIAOMI_PASSWORD;
  }

  await MiGPT.start({
    debug: (env.XIAOAI_DEBUG || "").toLowerCase() === "true",
    speaker,
    openai: {
      model: "unused",
      baseURL: "https://example.invalid/v1",
      apiKey: "unused",
    },
    prompt: { system: "" },
    callAIKeywords: currentConfig.entry_phrases,
    onMessage,
  });
}

process.on("unhandledRejection", async (reason) => {
  const message = reason?.message || String(reason);
  console.error("[xiaoai] unhandledRejection:", message);
  await postLog("error", "runner 未处理异常", { error: message, event: "unhandled_rejection" });
});

main().catch(async (e) => {
  const message = e?.message || String(e);
  console.error("[xiaoai] 启动失败：", message);
  await postLog("error", "MiGPT runner 启动失败", { error: message, event: "runner_start_error" });
  process.exit(1);
});
