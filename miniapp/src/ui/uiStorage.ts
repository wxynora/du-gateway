export function readStoredBoolean(key: string, fallback = false): boolean {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    return raw === "1";
  } catch {
    return fallback;
  }
}

export function readStoredNumber(key: string, fallback: number): number {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    const text = String(raw).trim();
    if (!text) return fallback;
    const num = Number(text);
    return Number.isFinite(num) && num > 0 ? num : fallback;
  } catch {
    return fallback;
  }
}

export function clampStoredNumber(value: number, min: number, max: number, fallback: number): number {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return Math.max(min, Math.min(max, num));
}

export function readStoredString<T extends string>(key: string, fallback: T, allowed: readonly T[]): T {
  try {
    const raw = String(localStorage.getItem(key) || "").trim() as T;
    return allowed.includes(raw) ? raw : fallback;
  } catch {
    return fallback;
  }
}
