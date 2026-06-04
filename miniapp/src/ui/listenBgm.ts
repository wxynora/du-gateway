export type MusicBgmContext = {
  active?: boolean;
  is_playing?: boolean;
  entry_id?: string;
  title?: string;
  artist?: string;
  current_time?: number;
  duration_seconds?: number;
  segment?: unknown;
  source?: "listen-with-du";
  updated_at?: number;
};

const MUSIC_BGM_STORAGE_KEY = "miniapp.listenWithDu.bgmContext.v1";
const MUSIC_BGM_EVENT = "miniapp-listen-bgm-context";
const MUSIC_BGM_MAX_AGE_MS = 2 * 60 * 1000;

function asFiniteNumber(value: unknown): number {
  const n = Number(value || 0);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

function cleanText(value: unknown, limit = 160): string {
  const text = String(value || "").trim();
  return text.length > limit ? text.slice(0, limit).trim() : text;
}

function cleanContext(raw: MusicBgmContext | null | undefined): MusicBgmContext | null {
  if (!raw || typeof raw !== "object") return null;
  const entryId = cleanText(raw.entry_id, 120);
  const title = cleanText(raw.title, 120);
  const artist = cleanText(raw.artist, 120);
  const active = Boolean(raw.active && (entryId || title));
  return {
    active,
    is_playing: Boolean(raw.is_playing && active),
    entry_id: entryId,
    title,
    artist,
    current_time: asFiniteNumber(raw.current_time),
    duration_seconds: asFiniteNumber(raw.duration_seconds),
    segment: raw.segment && typeof raw.segment === "object" ? raw.segment : undefined,
    source: "listen-with-du",
    updated_at: asFiniteNumber(raw.updated_at) || Date.now(),
  };
}

export function writeMusicBgmContext(raw: MusicBgmContext) {
  if (typeof window === "undefined") return;
  const context = cleanContext({ ...raw, updated_at: Date.now() });
  if (!context) return;
  try {
    window.sessionStorage.setItem(MUSIC_BGM_STORAGE_KEY, JSON.stringify(context));
  } catch {
    // BGM context is best-effort; playback must keep working if storage is unavailable.
  }
  window.dispatchEvent(new CustomEvent(MUSIC_BGM_EVENT, { detail: context }));
}

export function readMusicBgmContext(maxAgeMs = MUSIC_BGM_MAX_AGE_MS): MusicBgmContext | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(MUSIC_BGM_STORAGE_KEY);
    if (!raw) return null;
    const context = cleanContext(JSON.parse(raw) as MusicBgmContext);
    if (!context?.active || !context.is_playing) return null;
    if (Date.now() - Number(context.updated_at || 0) > maxAgeMs) return null;
    return context;
  } catch {
    return null;
  }
}
