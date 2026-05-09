import { getInitData } from "./tg";
import { SumiOverlay } from "../plugins/sumi-overlay";

const PANEL_TOKEN_STORAGE_KEY = "miniapp.panel.token.v1";
const PANEL_DEVICE_ID_STORAGE_KEY = "miniapp.panel.device-id.v1";
const PANEL_PREVIOUS_DEVICE_ID_STORAGE_KEY = "miniapp.panel.device-id.previous.v1";
const API_BASE_URL = String(import.meta.env.VITE_API_BASE_URL || "").trim().replace(/\/+$/, "");
let pendingDeviceIdMigration: { from: string; to: string } | null = null;

export class ApiError extends Error {
  status: number;
  payload: any;
  constructor(message: string, status: number, payload: any) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

async function parseJsonSafe(r: Response): Promise<any> {
  const text = await r.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

export function getPanelToken(): string {
  try {
    return (window.localStorage.getItem(PANEL_TOKEN_STORAGE_KEY) || "").trim();
  } catch {
    return "";
  }
}

export function setPanelToken(token: string) {
  try {
    if (token) window.localStorage.setItem(PANEL_TOKEN_STORAGE_KEY, token);
    else window.localStorage.removeItem(PANEL_TOKEN_STORAGE_KEY);
  } catch {}
}

function randomId(): string {
  const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
  let out = "";
  for (let i = 0; i < 24; i += 1) {
    out += chars[Math.floor(Math.random() * chars.length)];
  }
  return out;
}

export async function getOrCreatePanelDeviceId(): Promise<string> {
  try {
    const existing = (window.localStorage.getItem(PANEL_DEVICE_ID_STORAGE_KEY) || "").trim();
    const previous = (window.localStorage.getItem(PANEL_PREVIOUS_DEVICE_ID_STORAGE_KEY) || "").trim();
    if (existing && previous && previous !== existing) {
      pendingDeviceIdMigration = { from: previous, to: existing };
      window.localStorage.removeItem(PANEL_PREVIOUS_DEVICE_ID_STORAGE_KEY);
    }
    const native = String((await SumiOverlay.getStableDeviceId().catch(() => ({ deviceId: "" })))?.deviceId || "").trim();
    if (native) {
      if (existing && existing !== native) {
        pendingDeviceIdMigration = { from: existing, to: native };
      }
      window.localStorage.setItem(PANEL_DEVICE_ID_STORAGE_KEY, native);
      return native;
    }
    if (existing) return existing;
    const next = `device_${randomId()}`;
    window.localStorage.setItem(PANEL_DEVICE_ID_STORAGE_KEY, next);
    return next;
  } catch {
    return `device_${randomId()}`;
  }
}

export function consumePendingPanelDeviceIdMigration(): { from: string; to: string } | null {
  const next = pendingDeviceIdMigration;
  pendingDeviceIdMigration = null;
  return next;
}

export function getPanelDeviceLabel(): string {
  const platform = [
    navigator.platform || "",
    navigator.language || "",
  ]
    .map((x) => String(x || "").trim())
    .filter(Boolean)
    .join(" · ");
  const ua = String(navigator.userAgent || "");
  let browser = "Browser";
  if (ua.includes("Edg/")) browser = "Edge";
  else if (ua.includes("Chrome/")) browser = "Chrome";
  else if (ua.includes("Safari/") && !ua.includes("Chrome/")) browser = "Safari";
  else if (ua.includes("Firefox/")) browser = "Firefox";
  return platform ? `${browser} @ ${platform}` : browser;
}

function withAuthUrl(path: string): string {
  try {
    const base = API_BASE_URL || window.location.origin;
    const u = new URL(path, base);
    const initData = getInitData();
    const panelToken = getPanelToken();
    if (initData && !u.searchParams.get("initData")) u.searchParams.set("initData", initData);
    if (panelToken && !u.searchParams.get("panel_token")) u.searchParams.set("panel_token", panelToken);
    return API_BASE_URL ? u.toString() : u.pathname + u.search;
  } catch {
    return path;
  }
}

function withAuthHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers || {});
  const initData = getInitData();
  const panelToken = getPanelToken();
  if (initData) headers.set("X-Telegram-Init-Data", initData);
  if (panelToken) headers.set("Authorization", `Bearer ${panelToken}`);
  return headers;
}

export async function publicApiFetch(path: string, init?: RequestInit): Promise<Response> {
  const finalPath = withAuthUrl(path);
  return fetch(finalPath, init);
}

/**
 * 只通过 Header 传 initData，不把 initData 拼进 URL。
 * 用于拉取图片二进制等（避免 query 过长 414；与 <img src> 不同，fetch 仍可能受跨域预检限制，见 app.py CORS）。
 */
export async function fetchWithInitDataHeaderOnly(path: string, init?: RequestInit): Promise<Response> {
  const headers = withAuthHeaders(init);
  const p = path.startsWith("/") ? path : `/${path}`;
  return fetch(withAuthUrl(p), { ...init, headers });
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = withAuthHeaders(init);
  const finalPath = withAuthUrl(path);
  return fetch(finalPath, { ...init, headers });
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await apiFetch(path, init);
  const j = await parseJsonSafe(r);
  if (!r.ok) {
    const code = String(j?.code || "").trim();
    if (code === "panel_token_invalid" || code === "not_trusted") {
      setPanelToken("");
      try {
        window.dispatchEvent(new CustomEvent("miniapp-auth-expired", { detail: { code, message: j?.error || "" } }));
      } catch {}
    }
    throw new ApiError(j?.error || j?.message || `HTTP ${r.status}`, r.status, j);
  }
  return j as T;
}

export function buildLogStreamUrl(startLines: number, category: string = "all"): string {
  const url = new URL("/miniapp-api/logs/stream", API_BASE_URL || window.location.origin);
  url.searchParams.set("start_lines", String(startLines));
  url.searchParams.set("category", category || "all");
  const initData = getInitData();
  const panelToken = getPanelToken();
  // EventSource 不能自定义 Header，所以走 query
  if (initData) url.searchParams.set("initData", initData);
  if (panelToken) url.searchParams.set("panel_token", panelToken);
  return url.toString();
}

export function buildRealtimeWebSocketUrl(path: string, params: Record<string, string> = {}): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(withAuthUrl(p), API_BASE_URL || window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    const v = String(value || "").trim();
    if (v && !url.searchParams.get(key)) url.searchParams.set(key, v);
  }
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export function buildApiAssetUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return withAuthUrl(p);
}
