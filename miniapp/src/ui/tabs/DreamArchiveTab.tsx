import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type DreamArchiveItem = {
  id: string;
  window_id?: string;
  sleep_session_key?: string;
  theme_id?: string;
  sleep_source?: string;
  channel?: string;
  target?: string;
  created_at?: string;
  sent_at?: string;
  preview?: string;
  content?: string;
  content_chars?: number;
  prompt?: string;
  fragments?: string[];
  meta?: Record<string, any>;
  r2_key?: string;
  updated_at?: string;
};

type DreamListResp = {
  ok?: boolean;
  items?: DreamArchiveItem[];
  count?: number;
};

type DreamDetailResp = {
  ok?: boolean;
  item?: DreamArchiveItem;
};

type DreamInspirationResp = {
  ok?: boolean;
  stars?: FragmentStar[];
  fragments?: string[];
  updated_at?: string;
};

type DreamView = "dreams" | "fragments" | "inspiration";

type FragmentStar = {
  id: string;
  label: string;
  text: string;
  color: "default" | "gold";
};

type PanelState =
  | { type: "dream"; item: DreamArchiveItem }
  | { type: "fragment"; star: FragmentStar }
  | { type: "fold" }
  | { type: "write" }
  | { type: "fish"; stars: FragmentStar[] };

const DREAM_LOCAL_FRAGMENTS_KEY = "miniapp.springDream.localFragments";
const DREAM_INSPIRATION_KEY = "miniapp.springDream.inspirationStars";

const STAR_LAYOUT = [
  { x: 13, y: 12, rot: -18, scale: 1.02 },
  { x: 61, y: 15, rot: 24, scale: 0.82 },
  { x: 35, y: 31, rot: 9, scale: 1.24 },
  { x: 75, y: 39, rot: -31, scale: 0.92 },
  { x: 17, y: 55, rot: 42, scale: 0.74 },
  { x: 51, y: 63, rot: -8, scale: 1.1 },
  { x: 72, y: 72, rot: 18, scale: 0.7 },
  { x: 30, y: 76, rot: -44, scale: 0.88 },
];

const dreamArchiveCss = `
.dreamArchiveRoot {
  --bg: #0A0A0C;
  --surface: #141418;
  --text-main: #E5E5E7;
  --text-muted: #71717A;
  --accent: #FDE68A;
  --border: rgba(255, 255, 255, 0.1);
  --ink: rgba(255, 255, 255, 0.05);
  position: fixed;
  inset: 0;
  z-index: 40;
  height: 100dvh;
  min-height: 100dvh;
  overflow: hidden;
  background-color: var(--bg);
  color: var(--text-main);
  font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  user-select: none;
}

.dreamArchiveRoot * {
  box-sizing: border-box;
  -webkit-tap-highlight-color: transparent;
}

.dreamArchiveVortex {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at center, transparent 0%, var(--bg) 80%),
    repeating-radial-gradient(circle at center, transparent 0, transparent 40px, rgba(255,255,255,0.02) 41px, transparent 42px);
  z-index: 0;
  opacity: 0.6;
}

.dreamArchiveGrain {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 20;
  opacity: 0.04;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
}

.dreamArchiveHeader {
  position: relative;
  z-index: 2;
  padding: 40px 24px 20px;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.dreamArchiveTitleBlock {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.dreamArchiveTitleEn {
  font-family: 'Noto Serif SC', serif;
  font-weight: 300;
  font-size: 10px;
  letter-spacing: 0.6em;
  color: var(--text-muted);
  opacity: 0.6;
  margin-bottom: 4px;
  padding-left: 2px;
}

.dreamArchiveTitle {
  font-family: 'Noto Serif SC', serif;
  font-weight: 600;
  font-size: 32px;
  letter-spacing: 0.25em;
  text-shadow: 0 0 20px rgba(255,255,255,0.2);
  line-height: 1.2;
}

.dreamArchiveGhost {
  background: transparent;
  border: 0.5px solid var(--border);
  color: var(--text-muted);
  padding: 8px 16px;
  font-size: 11px;
  border-radius: 20px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.dreamArchiveGhost:active,
.dreamArchiveFloat:active {
  transform: scale(0.97);
}

.dreamArchiveRoot button:focus {
  outline: none;
}

.dreamArchiveNav {
  position: fixed;
  bottom: 30px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 32px;
  background: transparent;
  z-index: 100;
  padding: 0;
  border: none;
  box-shadow: none;
}

.dreamArchiveTab {
  padding: 0;
  font-size: 15px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.4s cubic-bezier(0.23, 1, 0.32, 1);
  font-family: 'Noto Serif SC', serif;
  letter-spacing: 0.15em;
  position: relative;
  background: none;
  border: 0;
}

.dreamArchiveTab.active {
  color: var(--text-main);
}

.dreamArchiveTab.active::after {
  content: '';
  position: absolute;
  bottom: -8px;
  left: 50%;
  transform: translateX(-50%);
  width: 5px;
  height: 5px;
  background: var(--accent);
  border-radius: 50%;
  box-shadow: 0 0 10px var(--accent), 0 0 20px rgba(253, 230, 138, 0.4);
}

.dreamArchiveView {
  position: relative;
  z-index: 1;
  display: none;
  height: calc(100% - 112px);
  overflow-y: auto;
  padding: 0 20px 120px;
  animation: dreamArchiveFadeIn 0.8s ease-out;
}

.dreamArchiveView.active {
  display: block;
}

@keyframes dreamArchiveFadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.dreamArchiveTimeline {
  position: relative;
  margin-top: 30px;
  padding-left: 50px;
}

.dreamArchiveTimelineSvg {
  position: absolute;
  top: 0;
  left: 0;
  width: 50px;
  min-height: 340px;
  pointer-events: none;
  z-index: 0;
}

.dreamArchiveTimelinePath {
  fill: none;
  stroke: rgba(255,255,255,0.15);
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.dreamArchiveEntry {
  position: relative;
  margin-bottom: 40px;
  cursor: pointer;
  text-align: left;
  width: 100%;
  border: 0;
  background: transparent;
  color: inherit;
  display: block;
}

.dreamArchiveEntry:nth-of-type(odd) {
  transform: translateX(-8px);
}

.dreamArchiveEntry:nth-of-type(even) {
  transform: translateX(8px);
}

.dreamArchiveNode {
  position: absolute;
  left: -46px;
  top: -2px;
  width: 32px;
  height: 32px;
  filter: drop-shadow(0 0 5px rgba(255,255,255,0.1));
}

.dreamArchiveTime {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.1em;
  margin-bottom: 6px;
}

.dreamArchiveDreamTitle {
  font-family: 'Noto Serif SC', serif;
  font-size: 18px;
  color: var(--text-main);
  margin-bottom: 8px;
}

.dreamArchivePreview {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.dreamArchiveFav {
  color: var(--accent);
  font-size: 12px;
  margin-left: 4px;
}

.dreamArchiveEmpty {
  margin: 60px auto 0;
  max-width: 240px;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.8;
  text-align: center;
}

.dreamArchiveFragmentView {
  position: relative;
  overflow: hidden;
}

.dreamArchiveStarPool {
  position: absolute;
  inset: 56px 0 0;
}

.dreamArchivePaperStar {
  position: absolute;
  width: 50px;
  height: 50px;
  cursor: pointer;
  filter: drop-shadow(0 0 5px rgba(255,255,255,0.1));
  transition: transform 0.2s;
  border: 0;
  background: transparent;
  padding: 0;
}

.dreamArchiveStarLabel {
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  color: var(--text-muted);
  white-space: nowrap;
  margin-top: 4px;
  opacity: 0.7;
}

.dreamArchiveBottleLabel {
  text-align: center;
  font-family: 'Noto Serif SC', serif;
  color: var(--text-muted);
  font-size: 13px;
  margin-top: 10px;
}

.dreamArchiveBottle {
  position: relative;
  width: 240px;
  height: 360px;
  margin: 70px auto 40px;
  background:
    radial-gradient(ellipse at 35% 20%, rgba(255,255,255,0.12) 0%, transparent 50%),
    radial-gradient(ellipse at 70% 80%, rgba(255,255,255,0.04) 0%, transparent 40%),
    linear-gradient(170deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.01) 40%, rgba(255,255,255,0.03) 100%);
  border-radius: 100px 100px 36px 36px;
  border: 1.5px solid rgba(255,255,255,0.2);
  border-top-color: rgba(255,255,255,0.3);
  border-left-color: rgba(255,255,255,0.25);
  border-right-color: rgba(255,255,255,0.1);
  backdrop-filter: blur(12px) saturate(1.2);
  overflow: visible;
  box-shadow:
    inset 0 30px 60px rgba(255,255,255,0.06),
    inset -20px -20px 40px rgba(0,0,0,0.15),
    inset 20px 0 40px rgba(255,255,255,0.04),
    0 40px 80px rgba(0,0,0,0.5),
    0 0 0 1px rgba(255,255,255,0.05);
}

.dreamArchiveBottle::before {
  content: '';
  position: absolute;
  inset: 8px;
  border-radius: 92px 92px 30px 30px;
  border: 1px solid rgba(255,255,255,0.08);
  pointer-events: none;
  background: linear-gradient(160deg, rgba(255,255,255,0.05) 0%, transparent 30%, transparent 70%, rgba(255,255,255,0.02) 100%);
}

.dreamArchiveBottle::after {
  content: '';
  position: absolute;
  top: 15%;
  left: 8%;
  width: 25px;
  height: 80px;
  background: linear-gradient(180deg, rgba(255,255,255,0.15) 0%, rgba(255,255,255,0.05) 100%);
  border-radius: 12px;
  filter: blur(4px);
  transform: rotate(8deg);
  pointer-events: none;
}

.dreamArchiveBottleNeck {
  position: absolute;
  top: -50px;
  left: 50%;
  transform: translateX(-50%);
  width: 64px;
  height: 52px;
  background: linear-gradient(90deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.12) 30%, rgba(255,255,255,0.04) 100%);
  border: 1.5px solid rgba(255,255,255,0.2);
  border-bottom: none;
  border-radius: 10px 10px 4px 4px;
  box-shadow:
    inset 0 2px 8px rgba(255,255,255,0.1),
    0 4px 20px rgba(0,0,0,0.3);
  z-index: 10;
  overflow: hidden;
}

.dreamArchiveBottleNeck::before {
  content: '';
  position: absolute;
  top: -14px;
  left: 50%;
  transform: translateX(-50%);
  width: 80px;
  height: 18px;
  background: linear-gradient(180deg, rgba(255,255,255,0.14) 0%, rgba(255,255,255,0.06) 100%);
  border: 1.5px solid rgba(255,255,255,0.25);
  border-radius: 10px;
  box-shadow:
    0 2px 12px rgba(0,0,0,0.25),
    inset 0 1px 2px rgba(255,255,255,0.3);
}

.dreamArchiveBottleNeck::after {
  content: '';
  position: absolute;
  top: -4px;
  left: 50%;
  transform: translateX(-50%);
  width: 72px;
  height: 8px;
  background: rgba(255,255,255,0.08);
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.15);
  box-shadow: inset 0 1px 2px rgba(255,255,255,0.1);
}

.dreamArchiveBottleStars {
  position: absolute;
  bottom: 20px;
  left: 0;
  right: 0;
  height: 100%;
  display: flex;
  flex-wrap: wrap-reverse;
  justify-content: center;
  align-content: flex-start;
  padding: 20px 30px;
  gap: 2px;
}

.dreamArchiveBottleStar {
  width: 44px;
  height: 44px;
  margin: -4px;
  border: 0;
  background: transparent;
  padding: 0;
}

.dreamArchiveFloat {
  position: fixed;
  right: 22px;
  bottom: 102px;
  width: 42px;
  height: 42px;
  background: var(--text-main);
  color: var(--bg);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 16px rgba(0,0,0,0.38);
  z-index: 101;
  border: none;
}

.dreamArchiveOverlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.8);
  backdrop-filter: blur(4px);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.4s;
  z-index: 999;
}

.dreamArchiveOverlay.active {
  opacity: 1;
  pointer-events: auto;
}

.dreamArchivePanel {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  max-height: 74vh;
  overflow-y: auto;
  background: var(--surface);
  border-top: 1px solid var(--border);
  padding: 30px 24px 40px;
  transform: translateY(100%);
  transition: transform 0.4s cubic-bezier(0.23, 1, 0.32, 1);
  z-index: 1000;
  border-radius: 30px 30px 0 0;
}

.dreamArchivePanel.active {
  transform: translateY(0);
}

.dreamArchivePanelTitle {
  font-family: 'Noto Serif SC', serif;
  font-size: 20px;
  margin-bottom: 20px;
}

.dreamArchivePanelText {
  color: var(--text-main);
  line-height: 1.8;
  margin-bottom: 30px;
  white-space: pre-wrap;
  word-break: break-word;
}

.dreamArchivePanelMuted {
  color: var(--text-muted);
  line-height: 1.8;
  margin-bottom: 30px;
}

.dreamArchivePanelActions {
  display: flex;
  gap: 10px;
}

.dreamArchivePanelActions .dreamArchiveGhost {
  flex: 1;
}

.dreamArchiveTextarea {
  width: 100%;
  height: 120px;
  background: rgba(255,255,255,0.03);
  border: 0.5px solid var(--border);
  color: white;
  padding: 15px;
  border-radius: 10px;
  margin-bottom: 20px;
  outline: none;
  resize: none;
}

.dreamArchiveTagRow {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.dreamArchivePrimary {
  width: 100%;
  background: var(--text-main);
  color: var(--bg);
}

.dreamArchiveFishGrid {
  display: flex;
  justify-content: space-around;
  margin: 30px 0;
  gap: 16px;
}

.dreamArchiveFishCard {
  width: 100px;
  text-align: center;
  background: rgba(255,255,255,0.04);
  border: 0.5px solid rgba(255,255,255,0.1);
  border-radius: 16px;
  padding: 20px 12px;
  backdrop-filter: blur(8px);
  box-shadow: 0 4px 20px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.05);
}

.dreamArchiveFishStar {
  width: 48px;
  height: 48px;
  margin: 0 auto 10px;
}

.dreamArchiveFishTitle {
  font-size: 11px;
  color: var(--text-main);
  font-family: 'Noto Serif SC', serif;
  margin-bottom: 4px;
}

.dreamArchiveFishText {
  font-size: 10px;
  color: var(--text-muted);
  line-height: 1.4;
}

.dreamArchiveFoldedStar {
  fill: var(--text-muted);
  opacity: 0.8;
  stroke: var(--text-main);
  stroke-width: 0.5;
}

.dreamArchiveFoldedStar.gold {
  fill: var(--accent);
  opacity: 1;
  filter: drop-shadow(0 0 8px var(--accent));
}
`;

function formatTime(value?: string): string {
  const raw = String(value || "").trim();
  if (!raw) return "--:--";
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (match) return `${match[1]}.${match[2]}.${match[3]} ${match[4]}:${match[5]}`;
  return raw.replace("+08:00", "").replace("T", " ").slice(0, 16) || raw;
}

function normalizeItems(input: unknown): DreamArchiveItem[] {
  if (!Array.isArray(input)) return [];
  return input
    .filter((item): item is DreamArchiveItem => !!item && typeof item === "object" && !!String((item as DreamArchiveItem).id || "").trim())
    .map((item) => ({ ...item, id: String(item.id || "").trim() }));
}

function normalizeStars(input: unknown, key: string): FragmentStar[] {
  if (!Array.isArray(input)) return [];
  const seen = new Set<string>();
  const out: FragmentStar[] = [];
  input.forEach((item, index) => {
    const text = typeof item === "string" ? item : String((item as FragmentStar)?.text || "");
    const cleanText = text.trim();
    if (!cleanText || seen.has(cleanText)) return;
    seen.add(cleanText);
    const rawLabel = typeof item === "object" && item ? String((item as FragmentStar).label || "") : "";
    out.push({
      id: typeof item === "object" && item ? String((item as FragmentStar).id || `${key}-${index}`) : `${key}-${index}`,
      label: (rawLabel.trim() || cleanLabel(cleanText, "梦境碎片")).slice(0, 16),
      text: cleanText,
      color: typeof item === "object" && item && (item as FragmentStar).color === "gold" ? "gold" : "default",
    });
  });
  return out.slice(0, 36);
}

function readStoredStars(key: string): FragmentStar[] {
  try {
    return normalizeStars(JSON.parse(localStorage.getItem(key) || "[]"), key);
  } catch {
    return [];
  }
}

function writeStoredStars(key: string, stars: FragmentStar[]) {
  try {
    localStorage.setItem(key, JSON.stringify(stars.slice(0, 80)));
  } catch {}
}

function cleanLabel(value: string, fallback: string): string {
  const raw = value.replace(/[_#*-]+/g, " ").replace(/\s+/g, " ").trim();
  if (!raw) return fallback;
  return raw.length > 8 ? raw.slice(0, 8) : raw;
}

function titleForDream(item: DreamArchiveItem, index: number): string {
  const theme = cleanLabel(String(item.theme_id || ""), "");
  if (theme) return theme;
  const preview = cleanLabel(String(item.preview || item.content || ""), "");
  if (preview) return preview;
  return `第 ${index + 1} 场梦`;
}

function previewForDream(item: DreamArchiveItem): string {
  return String(item.preview || item.content || "没有预览").trim();
}

function starFromText(text: string, index: number, prefix: string): FragmentStar {
  return {
    id: `${prefix}-${index}-${text.slice(0, 8)}`,
    label: cleanLabel(text, "梦境碎片"),
    text,
    color: index % 3 === 1 ? "gold" : "default",
  };
}

function StarSvg({ gold = false }: { gold?: boolean }) {
  return (
    <svg viewBox="0 0 100 100" className={`dreamArchiveFoldedStar ${gold ? "gold" : ""}`}>
      <path d="M50 5 L61 40 L95 40 L68 60 L78 95 L50 75 L22 95 L32 60 L5 40 L39 40 Z" />
      <path d="M50 5 L50 75 M5 40 L68 60 M95 40 L32 60" strokeOpacity="0.3" fill="none" />
    </svg>
  );
}

export function DreamArchiveTab({
  backHandlerRef,
}: {
  backHandlerRef?: React.MutableRefObject<(() => boolean) | null>;
}) {
  const toast = useToast();
  const [items, setItems] = useState<DreamArchiveItem[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<DreamArchiveItem | null>(null);
  const [view, setView] = useState<DreamView>("dreams");
  const [panel, setPanel] = useState<PanelState | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [draftText, setDraftText] = useState("");
  const [localFragments, setLocalFragments] = useState<FragmentStar[]>(() => readStoredStars(DREAM_LOCAL_FRAGMENTS_KEY));
  const [inspirationStars, setInspirationStars] = useState<FragmentStar[]>(() => readStoredStars(DREAM_INSPIRATION_KEY));
  const [inspirationReady, setInspirationReady] = useState(false);
  const inspirationEditVersionRef = useRef(0);
  const inspirationDirtyRef = useRef(false);
  const inspirationSaveErrorShownRef = useRef(false);
  const lastSyncedInspirationJsonRef = useRef(JSON.stringify(inspirationStars));

  const selectedSummary = useMemo(
    () => items.find((item) => item.id === selectedId) || null,
    [items, selectedId],
  );

  const detail = selected || selectedSummary;

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiJson<DreamListResp>("/miniapp-api/spring-dream-archives?limit=80");
      const next = normalizeItems(res.items);
      setItems(next);
      if (!selectedId && next[0]?.id) setSelectedId(next[0].id);
    } catch (e: any) {
      toast(`读取失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }, [selectedId, toast]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    let cancelled = false;
    const id = String(selectedId || "").trim();
    if (!id) {
      setSelected(null);
      return;
    }
    setDetailLoading(true);
    apiJson<DreamDetailResp>(`/miniapp-api/spring-dream-archives/${encodeURIComponent(id)}`)
      .then((res) => {
        if (cancelled) return;
        setSelected(res.item || null);
      })
      .catch((e: any) => {
        if (!cancelled) toast(`读取详情失败：${e?.message || e}`);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, toast]);

  useEffect(() => writeStoredStars(DREAM_LOCAL_FRAGMENTS_KEY, localFragments), [localFragments]);
  useEffect(() => writeStoredStars(DREAM_INSPIRATION_KEY, inspirationStars), [inspirationStars]);

  useEffect(() => {
    let cancelled = false;
    const requestVersion = inspirationEditVersionRef.current;
    apiJson<DreamInspirationResp>("/miniapp-api/spring-dream-inspiration")
      .then((res) => {
        if (cancelled) return;
        const remote = normalizeStars(res.stars || res.fragments || [], "remote-inspiration");
        lastSyncedInspirationJsonRef.current = JSON.stringify(remote);
        if (inspirationEditVersionRef.current === requestVersion) {
          setInspirationStars(remote);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setInspirationReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!inspirationReady) return;
    const payloadJson = JSON.stringify(inspirationStars);
    if (payloadJson === lastSyncedInspirationJsonRef.current) return;
    apiJson<DreamInspirationResp>("/miniapp-api/spring-dream-inspiration", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stars: inspirationStars }),
    })
      .then((res) => {
        const saved = normalizeStars(res.stars || res.fragments || [], "saved-inspiration");
        lastSyncedInspirationJsonRef.current = JSON.stringify(saved);
        inspirationDirtyRef.current = false;
        inspirationSaveErrorShownRef.current = false;
      })
      .catch((e: any) => {
        if (!inspirationDirtyRef.current || inspirationSaveErrorShownRef.current) return;
        inspirationSaveErrorShownRef.current = true;
        toast(`灵感瓶同步失败：${e?.message || e}`);
      });
  }, [inspirationReady, inspirationStars, toast]);

  const fragmentStars = useMemo(() => {
    const fromSelected = Array.isArray(detail?.fragments)
      ? detail.fragments.filter(Boolean).map((fragment, index) => starFromText(String(fragment), index, "selected"))
      : [];
    const fromArchive = items
      .flatMap((item) => (Array.isArray(item.fragments) ? item.fragments : []))
      .filter(Boolean)
      .slice(0, 12)
      .map((fragment, index) => starFromText(String(fragment), index, "archive"));
    const merged = [...fromSelected, ...fromArchive, ...localFragments];
    const seen = new Set<string>();
    return merged.filter((star) => {
      const key = `${star.label}:${star.text}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [detail?.fragments, items, localFragments]);

  const viewTitle = view === "dreams" ? "梦境" : view === "fragments" ? "碎片" : "灵感";

  const handleBack = useCallback(() => {
    if (panel) {
      setPanel(null);
      return true;
    }
    if (view !== "dreams") {
      setView("dreams");
      return true;
    }
    return false;
  }, [panel, view]);

  useEffect(() => {
    if (!backHandlerRef) return;
    backHandlerRef.current = handleBack;
    return () => {
      if (backHandlerRef.current === handleBack) {
        backHandlerRef.current = null;
      }
    };
  }, [backHandlerRef, handleBack]);

  function openDream(item: DreamArchiveItem) {
    setSelectedId(item.id);
    setPanel({ type: "dream", item });
  }

  function updateInspirationStars(next: React.SetStateAction<FragmentStar[]>) {
    inspirationEditVersionRef.current += 1;
    inspirationDirtyRef.current = true;
    setInspirationStars(next);
  }

  function addStarsToBottle(stars: FragmentStar[]) {
    if (!stars.length) return;
    updateInspirationStars((prev) => {
      const next = [...stars, ...prev];
      const seen = new Set<string>();
      return next.filter((star) => {
        const key = `${star.label}:${star.text}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }).slice(0, 36);
    });
    setPanel(null);
    setView("inspiration");
  }

  function saveDraftAsFragment(target: "fragment" | "inspiration") {
    const text = draftText.trim();
    if (!text) return;
    const star: FragmentStar = {
      id: `local-${Date.now()}`,
      label: cleanLabel(text, "梦境碎片"),
      text,
      color: target === "inspiration" ? "gold" : "default",
    };
    if (target === "fragment") {
      setLocalFragments((prev) => [star, ...prev].slice(0, 40));
      setView("fragments");
    } else {
      updateInspirationStars((prev) => [star, ...prev].slice(0, 36));
      setView("inspiration");
    }
    setDraftText("");
    setPanel(null);
  }

  function randomFish() {
    const pool = fragmentStars.length ? fragmentStars : localFragments;
    const picked = pool
      .slice()
      .sort(() => Math.random() - 0.5)
      .slice(0, 2);
    setPanel({ type: "fish", stars: picked });
  }

  function renderPanelContent() {
    if (!panel) return null;
    if (panel.type === "dream") {
      const fullItem = selected?.id === panel.item.id ? selected : panel.item;
      const fragments = Array.isArray(fullItem.fragments) ? fullItem.fragments.filter(Boolean) : [];
      return (
        <>
          <div className="dreamArchiveTime">{formatTime(fullItem.sent_at)}</div>
          <div className="dreamArchivePanelTitle">{titleForDream(fullItem, 0)}</div>
          <div className="dreamArchivePanelText">
            {detailLoading && !selected?.content ? "读取中" : selected?.content || fullItem.content || fullItem.preview || "没有正文"}
          </div>
          {fragments.length ? (
            <div style={{ borderTop: "0.5px solid var(--border)", paddingTop: 20 }}>
              <div style={{ fontSize: 10, color: "var(--text-muted)", marginBottom: 12, letterSpacing: "0.1em" }}>关联碎片</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {fragments.slice(0, 6).map((fragment, index) => (
                  <button
                    key={`${fragment}-${index}`}
                    type="button"
                    style={{ width: 24, height: 24, border: 0, padding: 0, background: "transparent" }}
                    onClick={() => setPanel({ type: "fragment", star: starFromText(String(fragment), index, "detail") })}
                    aria-label={String(fragment)}
                  >
                    <StarSvg gold={index % 2 === 0} />
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </>
      );
    }
    if (panel.type === "fragment") {
      return (
        <>
          <div className="dreamArchivePanelTitle">{panel.star.label}</div>
          <p className="dreamArchivePanelMuted">{panel.star.text}</p>
          <div className="dreamArchivePanelActions">
            <button className="dreamArchiveGhost" type="button" onClick={() => addStarsToBottle([panel.star])}>放进瓶子</button>
            <button
              className="dreamArchiveGhost"
              type="button"
              onClick={() => {
                setDraftText(panel.star.text);
                setPanel({ type: "fold" });
              }}
            >
              编辑
            </button>
          </div>
        </>
      );
    }
    if (panel.type === "fold") {
      return (
        <>
          <div className="dreamArchivePanelTitle">折一颗星</div>
          <textarea
            className="dreamArchiveTextarea"
            placeholder="记录微小的碎片..."
            value={draftText}
            onChange={(event) => setDraftText(event.target.value)}
          />
          <div className="dreamArchiveTagRow">
            <span className="dreamArchiveGhost" style={{ borderColor: "var(--accent)", color: "var(--accent)" }}>场景</span>
            <span className="dreamArchiveGhost">道具</span>
            <span className="dreamArchiveGhost">动作</span>
            <span className="dreamArchiveGhost">氛围</span>
          </div>
          <button className="dreamArchiveGhost dreamArchivePrimary" type="button" onClick={() => saveDraftAsFragment("fragment")}>折好了</button>
        </>
      );
    }
    if (panel.type === "write") {
      return (
        <>
          <div className="dreamArchivePanelTitle">许一个灵感</div>
          <textarea
            className="dreamArchiveTextarea"
            style={{ height: 80 }}
            placeholder="写下今晚的期待..."
            value={draftText}
            onChange={(event) => setDraftText(event.target.value)}
          />
          <button className="dreamArchiveGhost dreamArchivePrimary" type="button" onClick={() => saveDraftAsFragment("inspiration")}>放入瓶中</button>
        </>
      );
    }
    return (
      <>
        <div className="dreamArchivePanelTitle" style={{ textAlign: "center" }}>打捞结果</div>
        {panel.stars.length ? (
          <div className="dreamArchiveFishGrid">
            {panel.stars.map((star) => (
              <div className="dreamArchiveFishCard" key={star.id}>
                <div className="dreamArchiveFishStar"><StarSvg gold={star.color === "gold"} /></div>
                <div className="dreamArchiveFishTitle">{star.label}</div>
                <div className="dreamArchiveFishText">{star.text}</div>
              </div>
            ))}
          </div>
        ) : (
          <p className="dreamArchivePanelMuted" style={{ textAlign: "center" }}>还没有可以打捞的碎片</p>
        )}
        <div className="dreamArchivePanelActions">
          <button className="dreamArchiveGhost" type="button" onClick={() => addStarsToBottle(panel.stars)}>全部收进瓶子</button>
          <button className="dreamArchiveGhost" type="button" onClick={randomFish}>换一批</button>
        </div>
      </>
    );
  }

  return (
    <div className="dreamArchiveRoot">
      <style>{dreamArchiveCss}</style>
      <div className="dreamArchiveVortex" />
      <div className="dreamArchiveGrain" />

      <header className="dreamArchiveHeader">
        <div className="dreamArchiveTitleBlock">
          <div className="dreamArchiveTitleEn">DREAM</div>
          <h1 className="dreamArchiveTitle">{viewTitle}</h1>
        </div>
        <button className="dreamArchiveGhost" type="button" onClick={() => void loadList()} disabled={loading}>
          {loading ? "读取中" : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
          )}
        </button>
      </header>

      <main className={`dreamArchiveView ${view === "dreams" ? "active" : ""}`}>
        {items.length ? (
          <div className="dreamArchiveTimeline">
            <svg className="dreamArchiveTimelineSvg" viewBox="0 0 50 340" style={{ height: Math.max(340, items.length * 116) }}>
              <path className="dreamArchiveTimelinePath" d="M 20,14 L 20,70 L 12,110 L 20,140 L 20,190 L 28,230 L 20,265" />
            </svg>
            {items.map((item, index) => (
              <button className="dreamArchiveEntry" type="button" key={item.id} onClick={() => openDream(item)}>
                <div className="dreamArchiveNode"><StarSvg gold={item.id === selectedId || index % 2 === 0} /></div>
                <div className="dreamArchiveTime">
                  {formatTime(item.sent_at)}
                  {item.r2_key ? <span className="dreamArchiveFav">★</span> : null}
                </div>
                <div className="dreamArchiveDreamTitle">{titleForDream(item, index)}</div>
                <div className="dreamArchivePreview">{previewForDream(item)}</div>
              </button>
            ))}
          </div>
        ) : (
          <div className="dreamArchiveEmpty">{loading ? "正在读取" : "还没有梦境记录"}</div>
        )}
      </main>

      <main className={`dreamArchiveView dreamArchiveFragmentView ${view === "fragments" ? "active" : ""}`}>
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 20 }}>
          <button className="dreamArchiveGhost" type="button" onClick={randomFish}>随机打捞</button>
        </div>
        <div className="dreamArchiveStarPool">
          {fragmentStars.map((star, index) => {
            const layout = STAR_LAYOUT[index % STAR_LAYOUT.length];
            return (
              <button
                key={`${star.id}-${index}`}
                className="dreamArchivePaperStar"
                type="button"
                style={{
                  left: `${layout.x}%`,
                  top: `${layout.y}%`,
                  transform: `rotate(${layout.rot + index * 7}deg) scale(${layout.scale})`,
                }}
                onClick={() => setPanel({ type: "fragment", star })}
              >
                <StarSvg gold={star.color === "gold"} />
                <div className="dreamArchiveStarLabel">{star.label}</div>
              </button>
            );
          })}
          {!fragmentStars.length ? <div className="dreamArchiveEmpty">还没有折好的星</div> : null}
        </div>
        <button className="dreamArchiveFloat" type="button" onClick={() => setPanel({ type: "fold" })} aria-label="折一颗星">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
      </main>

      <main className={`dreamArchiveView ${view === "inspiration" ? "active" : ""}`}>
        <div className="dreamArchiveBottleLabel">今晚的许愿瓶</div>
        <div className="dreamArchiveBottle">
          <div className="dreamArchiveBottleNeck" />
          <div className="dreamArchiveBottleStars">
            {inspirationStars.length ? inspirationStars.map((star, index) => (
              <button
                className="dreamArchiveBottleStar"
                type="button"
                key={`${star.id}-${index}`}
                style={{
                  width: `${28 + (index % 5) * 7}px`,
                  height: `${28 + (index % 5) * 7}px`,
                  transform: `rotate(${index * 31}deg)`,
                  opacity: 0.68 + (index % 3) * 0.12,
                }}
                onClick={() => setPanel({ type: "fragment", star })}
                aria-label={star.label}
              >
                <StarSvg gold={star.color === "gold" || index % 3 === 0} />
              </button>
            )) : (
              <div style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 100 }}>今晚还没有星星</div>
            )}
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "center", gap: 12, marginTop: 20 }}>
          <button className="dreamArchiveGhost" type="button" onClick={() => setPanel({ type: "write" })}>写一颗</button>
          <button className="dreamArchiveGhost" type="button" onClick={() => updateInspirationStars([])}>清空瓶子</button>
        </div>
      </main>

      <nav className="dreamArchiveNav">
        <button className={`dreamArchiveTab ${view === "dreams" ? "active" : ""}`} type="button" onClick={() => setView("dreams")}>梦境</button>
        <button className={`dreamArchiveTab ${view === "fragments" ? "active" : ""}`} type="button" onClick={() => setView("fragments")}>碎片</button>
        <button className={`dreamArchiveTab ${view === "inspiration" ? "active" : ""}`} type="button" onClick={() => setView("inspiration")}>灵感</button>
      </nav>

      <button className={`dreamArchiveOverlay ${panel ? "active" : ""}`} type="button" onClick={() => setPanel(null)} aria-label="关闭" />
      <div className={`dreamArchivePanel ${panel ? "active" : ""}`}>
        {renderPanelContent()}
      </div>
    </div>
  );
}
