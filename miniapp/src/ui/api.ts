import { getInitData } from "./tg";

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

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers || {});
  const initData = getInitData();
  if (initData) headers.set("X-Telegram-Init-Data", initData);
  let finalPath = path;
  if (initData) {
    try {
      const u = new URL(path, window.location.origin);
      if (!u.searchParams.get("initData")) u.searchParams.set("initData", initData);
      finalPath = u.pathname + u.search;
    } catch {}
  }
  return fetch(finalPath, { ...init, headers });
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await apiFetch(path, init);
  const j = await parseJsonSafe(r);
  if (!r.ok) {
    throw new ApiError(j?.error || j?.message || `HTTP ${r.status}`, r.status, j);
  }
  return j as T;
}

export function buildLogStreamUrl(startLines: number): string {
  const initData = getInitData();
  const url = new URL("/miniapp-api/logs/stream", window.location.origin);
  url.searchParams.set("start_lines", String(startLines));
  // EventSource 不能自定义 Header，所以走 query
  if (initData) url.searchParams.set("initData", initData);
  return url.toString();
}

