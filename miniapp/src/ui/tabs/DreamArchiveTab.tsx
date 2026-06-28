import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dreamBottleRibbonUrl from "../../assets/dream-bottle-ribbon-trimmed.png";
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

type DreamFragmentLibraryResp = {
  ok?: boolean;
  stars?: FragmentStar[];
  fragments?: string[];
  packs?: FragmentPack[];
  count?: number;
};

type DreamView = "dreams" | "fragments" | "inspiration";

type FragmentStar = {
  id: string;
  label: string;
  text: string;
  color: "default" | "gold";
  theme_id?: string;
};

type FragmentPack = {
  id: string;
  stars: FragmentStar[];
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
  { col: 2, row: 1, rot: -21, scale: 1.34, offset: 0, opacity: 0.96 },
  { col: 8, row: 1, rot: 32, scale: 0.58, offset: 13, opacity: 0.58 },
  { col: 5, row: 2, rot: 8, scale: 0.94, offset: -7, opacity: 0.82 },
  { col: 11, row: 3, rot: -38, scale: 1.18, offset: 5, opacity: 0.9 },
  { col: 1, row: 4, rot: 46, scale: 0.66, offset: -4, opacity: 0.62 },
  { col: 7, row: 4, rot: -10, scale: 1.52, offset: 12, opacity: 1 },
  { col: 4, row: 5, rot: 24, scale: 0.76, offset: -10, opacity: 0.68 },
  { col: 10, row: 6, rot: -49, scale: 1.06, offset: 1, opacity: 0.86 },
  { col: 6, row: 7, rot: 35, scale: 0.6, offset: 15, opacity: 0.54 },
  { col: 2, row: 8, rot: -28, scale: 1.24, offset: -6, opacity: 0.92 },
  { col: 8, row: 8, rot: 13, scale: 0.72, offset: 6, opacity: 0.64 },
  { col: 12, row: 9, rot: -16, scale: 1.42, offset: -2, opacity: 0.96 },
  { col: 4, row: 10, rot: 41, scale: 0.55, offset: 10, opacity: 0.5 },
  { col: 9, row: 11, rot: -33, scale: 0.98, offset: -8, opacity: 0.78 },
];

const BOTTLE_STAR_LAYOUT = [
  { left: 45, bottom: 20, size: 72, rot: -15, opacity: 1, gold: true },
  { left: 25, bottom: 32, size: 20, rot: 34, opacity: 0.58, gold: false },
  { left: 68, bottom: 39, size: 66, rot: 18, opacity: 0.98, gold: true },
  { left: 49, bottom: 54, size: 18, rot: -28, opacity: 0.52, gold: false },
  { left: 32, bottom: 60, size: 58, rot: -24, opacity: 0.9, gold: true },
  { left: 80, bottom: 62, size: 18, rot: 42, opacity: 0.5, gold: false },
  { left: 59, bottom: 73, size: 50, rot: 13, opacity: 0.82, gold: true },
  { left: 22, bottom: 78, size: 16, rot: -36, opacity: 0.44, gold: false },
  { left: 75, bottom: 82, size: 20, rot: 25, opacity: 0.46, gold: false },
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
  --dream-display: 'Cormorant Garamond', 'Playfair Display', 'Noto Serif SC', 'Songti SC', serif;
  --dream-body: 'Lora', 'Noto Serif SC', 'Songti SC', serif;
  position: fixed;
  inset: 0;
  z-index: 40;
  height: 100dvh;
  min-height: 100dvh;
  overflow: hidden;
  background-color: var(--bg);
  color: var(--text-main);
  font-family: var(--dream-body);
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
  font-family: var(--dream-display);
  font-weight: 300;
  font-size: 10px;
  letter-spacing: 0.6em;
  color: var(--text-muted);
  opacity: 0.6;
  margin-bottom: 4px;
  padding-left: 2px;
}

.dreamArchiveTitle {
  font-family: var(--dream-display);
  font-weight: 500;
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
  font-family: var(--dream-display);
}

.dreamArchiveGhost:active {
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
  font-family: var(--dream-display);
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
  left: -42px;
  top: 1px;
  width: 26px;
  height: 26px;
  filter: drop-shadow(0 0 5px rgba(255,255,255,0.1));
  animation: dreamArchiveSoftFloat 6s ease-in-out infinite;
  animation-delay: var(--star-delay, 0s);
  will-change: transform;
}

.dreamArchiveTime {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.1em;
  margin-bottom: 6px;
}

.dreamArchiveDreamTitle {
  font-family: var(--dream-display);
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
  overflow-y: auto;
  animation: none;
}

.dreamArchiveInspirationView {
  position: relative;
  overflow: visible;
}

.dreamArchiveInspirationView.active {
  z-index: 30;
}

.dreamArchiveBottleLabel,
.dreamArchiveBottle,
.dreamArchiveInspirationActions {
  position: relative;
  z-index: 1;
}

.dreamArchiveOrbitField {
  position: absolute;
  left: 50%;
  top: 24px;
  width: min(132vw, 620px);
  height: min(86vw, 400px);
  transform: translateX(-50%) rotate(-11deg);
  pointer-events: none;
  opacity: 0.68;
  z-index: 0;
  filter: blur(0.1px);
  animation: dreamArchiveOrbitDrift 9s ease-in-out infinite alternate;
}

.dreamArchiveOrbitRing {
  --ring-tilt: -18deg;
  --ring-scale-y: 1;
  position: absolute;
  inset: 8% 13%;
  border-radius: 50%;
  background:
    conic-gradient(
      from 20deg,
      transparent 0deg 18deg,
      rgba(253, 230, 138, 0.55) 18deg 20deg,
      transparent 20deg 66deg,
      rgba(255,255,255,0.32) 66deg 68deg,
      transparent 68deg 136deg,
      rgba(253, 230, 138, 0.34) 136deg 138deg,
      transparent 138deg 360deg
    );
  -webkit-mask: radial-gradient(ellipse at center, transparent 0 58%, #000 58.6% 59.8%, transparent 60.4%);
  mask: radial-gradient(ellipse at center, transparent 0 58%, #000 58.6% 59.8%, transparent 60.4%);
  animation: dreamArchiveOrbitSpin 32s linear infinite;
}

.dreamArchiveOrbitRing::before,
.dreamArchiveOrbitRing::after {
  content: '';
  position: absolute;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: rgba(253, 230, 138, 0.88);
  box-shadow:
    0 0 10px rgba(253, 230, 138, 0.7),
    34px 12px 0 -1px rgba(255,255,255,0.42),
    74px 40px 0 -1px rgba(255,255,255,0.24),
    -52px 34px 0 -1px rgba(255,255,255,0.32),
    -112px 74px 0 -1px rgba(253,230,138,0.2);
}

.dreamArchiveOrbitRing::before {
  top: 18%;
  left: 76%;
}

.dreamArchiveOrbitRing::after {
  right: 18%;
  bottom: 16%;
  opacity: 0.7;
}

.dreamArchiveOrbitRing:nth-child(2) {
  --ring-tilt: 21deg;
  --ring-scale-y: 0.84;
  inset: 18% 4%;
  animation-duration: 44s;
  animation-direction: reverse;
  opacity: 0.58;
  background:
    conic-gradient(
      from 110deg,
      transparent 0deg 44deg,
      rgba(255,255,255,0.26) 44deg 46deg,
      transparent 46deg 160deg,
      rgba(253, 230, 138, 0.34) 160deg 162deg,
      transparent 162deg 270deg,
      rgba(255,255,255,0.2) 270deg 272deg,
      transparent 272deg 360deg
    );
}

.dreamArchiveOrbitRing:nth-child(3) {
  --ring-tilt: 58deg;
  --ring-scale-y: 0.72;
  inset: 30% 24%;
  animation-duration: 26s;
  opacity: 0.42;
}

@keyframes dreamArchiveOrbitSpin {
  from { transform: rotate(var(--ring-tilt)) scaleY(var(--ring-scale-y)); }
  to { transform: rotate(calc(var(--ring-tilt) + 360deg)) scaleY(var(--ring-scale-y)); }
}

@keyframes dreamArchiveOrbitDrift {
  from { transform: translateX(-50%) translateY(-2px) rotate(-11deg); }
  to { transform: translateX(-50%) translateY(8px) rotate(-8deg); }
}

.dreamArchiveStarPool {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  grid-auto-rows: 34px;
  justify-items: center;
  align-items: center;
  gap: 4px 0;
  min-height: 0;
  margin-top: 18px;
  padding: 22px 10px 86px;
}

.dreamArchivePaperStar {
  --star-rot: 0deg;
  --star-scale: 0.82;
  --star-offset: 0px;
  --star-drift: -7px;
  position: relative;
  width: 26px;
  height: 26px;
  cursor: pointer;
  filter: drop-shadow(0 0 5px rgba(255,255,255,0.1));
  transition: transform 0.2s;
  border: 0;
  background: transparent;
  padding: 0;
  animation: dreamArchiveStarFloat 5.8s ease-in-out infinite;
  animation-delay: var(--star-delay, 0s);
  transform: translate3d(0, var(--star-offset), 0) rotate(var(--star-rot)) scale(var(--star-scale));
  will-change: transform;
}

@keyframes dreamArchiveStarFloat {
  0%, 100% {
    transform: translate3d(0, var(--star-offset), 0) rotate(var(--star-rot)) scale(var(--star-scale));
  }
  50% {
    transform: translate3d(0, calc(var(--star-offset) + var(--star-drift)), 0) rotate(calc(var(--star-rot) + 4deg)) scale(var(--star-scale));
  }
}

.dreamArchiveBottleLabel {
  text-align: center;
  font-family: var(--dream-display);
  color: var(--text-muted);
  font-size: 13px;
  margin-top: 2px;
}

.dreamArchiveInspirationActions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 70px;
}

.dreamArchiveBottle {
  --bottle-scale: 1.2;
  position: relative;
  left: 18px;
  width: 192px;
  height: 306px;
  margin: 78px auto 8px;
  background:
    radial-gradient(ellipse at 30% 28%, rgba(255,255,255,0.22) 0%, rgba(255,255,255,0.05) 30%, transparent 62%),
    radial-gradient(ellipse at 52% 86%, rgba(253,230,138,0.18) 0%, rgba(253,230,138,0.05) 36%, transparent 68%),
    linear-gradient(155deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.025) 48%, rgba(255,255,255,0.07) 100%);
  border-radius: 42px 42px 32px 32px / 54px 54px 30px 30px;
  border: 2px solid rgba(237,246,255,0.34);
  border-top-color: rgba(255,255,255,0.5);
  border-left-color: rgba(255,255,255,0.42);
  border-right-color: rgba(181,210,255,0.2);
  backdrop-filter: blur(12px) saturate(1.2);
  overflow: visible;
  transform: scale(var(--bottle-scale)) rotate(14deg);
  transform-origin: 50% 2%;
  animation: dreamArchiveBottleFloat 5.8s ease-in-out infinite;
  will-change: transform;
  box-shadow:
    inset 0 24px 46px rgba(255,255,255,0.09),
    inset -18px -20px 38px rgba(20,47,88,0.16),
    inset 18px 0 32px rgba(255,255,255,0.08),
    0 0 30px rgba(122,176,255,0.18),
    0 32px 72px rgba(0,0,0,0.5);
}

@keyframes dreamArchiveBottleFloat {
  0%, 100% { transform: translateY(0) scale(var(--bottle-scale)) rotate(14deg); }
  50% { transform: translateY(-4px) scale(var(--bottle-scale)) rotate(15deg); }
}

.dreamArchiveBottle::before {
  content: '';
  position: absolute;
  inset: 10px 11px 12px;
  border-radius: 40px 40px 28px 28px / 52px 52px 28px 28px;
  border: 1px solid rgba(255,255,255,0.13);
  pointer-events: none;
  background:
    linear-gradient(154deg, rgba(255,255,255,0.1) 0%, transparent 28%, transparent 70%, rgba(255,255,255,0.04) 100%);
}

.dreamArchiveBottle::after {
  content: '';
  position: absolute;
  right: 39px;
  top: 32px;
  width: 18px;
  height: 82px;
  background: linear-gradient(180deg, rgba(255,255,255,0.5) 0%, rgba(255,255,255,0.18) 38%, rgba(255,255,255,0.04) 100%);
  border-radius: 999px;
  filter: blur(2px);
  transform: rotate(0deg);
  pointer-events: none;
}

.dreamArchiveBottleNeck {
  position: absolute;
  top: -46px;
  left: 50%;
  transform: translateX(-50%);
  width: 100px;
  height: 52px;
  background:
    repeating-linear-gradient(180deg, rgba(255,255,255,0.2) 0 3px, rgba(255,255,255,0.04) 3px 7px),
    linear-gradient(90deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.19) 36%, rgba(255,255,255,0.04) 100%);
  border: 1.5px solid rgba(237,246,255,0.32);
  border-bottom: none;
  border-radius: 20px 20px 8px 8px;
  box-shadow:
    inset 0 2px 8px rgba(255,255,255,0.1),
    0 4px 20px rgba(0,0,0,0.3);
  z-index: 12;
  overflow: hidden;
}

.dreamArchiveBottleNeck::before {
  content: '';
  position: absolute;
  top: -16px;
  left: 50%;
  transform: translateX(-50%);
  width: 70px;
  height: 18px;
  background: linear-gradient(180deg, rgba(224,192,143,0.76) 0%, rgba(176,138,92,0.42) 100%);
  border: 1px solid rgba(253,230,180,0.24);
  border-radius: 10px 10px 4px 4px;
  box-shadow:
    0 2px 12px rgba(0,0,0,0.25),
    inset 0 1px 2px rgba(255,255,255,0.3);
}

.dreamArchiveBottleNeck::after {
  content: '';
  position: absolute;
  left: -8px;
  right: -8px;
  top: 12px;
  height: 5px;
  border-radius: 999px;
  background: rgba(255,255,255,0.22);
  box-shadow:
    0 10px 0 rgba(255,255,255,0.12),
    0 20px 0 rgba(255,255,255,0.08);
}

.dreamArchiveBottleRibbon {
  position: absolute;
  left: 50%;
  top: -148px;
  width: 356px;
  max-width: none;
  height: auto;
  display: block;
  transform: translateX(-60%) rotate(-14deg);
  pointer-events: none;
  z-index: 18;
  filter: drop-shadow(0 10px 16px rgba(6,18,42,0.28));
  transform-origin: 50% 50%;
}

.dreamArchiveBottleDust {
  position: absolute;
  left: 26px;
  right: 28px;
  bottom: 14px;
  height: 128px;
  pointer-events: none;
  z-index: 1;
  opacity: 0.88;
  background:
    radial-gradient(circle at 50% 16%, rgba(255,255,255,0.95) 0 2px, transparent 3px),
    radial-gradient(circle at 20% 48%, rgba(253,230,138,0.95) 0 2px, transparent 3px),
    radial-gradient(circle at 76% 58%, rgba(255,255,255,0.86) 0 1px, transparent 2px),
    radial-gradient(circle at 58% 38%, rgba(253,230,138,0.8) 0 1px, transparent 2px),
    radial-gradient(ellipse at 50% 92%, rgba(253,230,138,0.56) 0%, rgba(253,230,138,0.22) 34%, rgba(84,142,199,0.12) 58%, transparent 78%);
  filter: drop-shadow(0 0 10px rgba(253,230,138,0.36));
  animation: dreamArchiveBottleGlow 4.8s ease-in-out infinite alternate;
}

.dreamArchiveBottleStars {
  position: absolute;
  inset: 0;
  z-index: 3;
  pointer-events: none;
}

.dreamArchiveBottleStar {
  position: absolute;
  width: var(--star-size);
  height: var(--star-size);
  left: var(--star-left);
  bottom: var(--star-bottom);
  opacity: var(--star-opacity);
  border: 0;
  background: transparent;
  padding: 0;
  transform: translate(-50%, 50%) rotate(var(--star-rot));
  animation: dreamArchiveBottleStarFloat 6.4s ease-in-out infinite;
  animation-delay: var(--star-delay, 0s);
  will-change: transform;
  pointer-events: auto;
}

@keyframes dreamArchiveBottleStarFloat {
  0%, 100% { transform: translate(-50%, 50%) translate3d(0, 0, 0) rotate(var(--star-rot, 0deg)); }
  50% { transform: translate(-50%, 50%) translate3d(2px, -6px, 0) rotate(calc(var(--star-rot, 0deg) + 4deg)); }
}

@keyframes dreamArchiveBottleGlow {
  from { opacity: 0.68; transform: translateY(2px) scale(0.98); }
  to { opacity: 0.96; transform: translateY(-4px) scale(1.03); }
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
  background: rgba(0,0,0,0.46);
  backdrop-filter: blur(3px);
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
  max-height: 68vh;
  overflow-y: auto;
  background: rgba(20, 20, 24, 0.72);
  border-top: 0.5px solid rgba(255,255,255,0.12);
  padding: 22px 22px 34px;
  transform: translateY(100%);
  transition: transform 0.4s cubic-bezier(0.23, 1, 0.32, 1);
  z-index: 1000;
  border-radius: 24px 24px 0 0;
  backdrop-filter: blur(18px) saturate(1.1);
  box-shadow: 0 -20px 60px rgba(0,0,0,0.34), inset 0 1px 0 rgba(255,255,255,0.06);
}

.dreamArchivePanel.active {
  transform: translateY(0);
}

.dreamArchivePanelTitle {
  font-family: var(--dream-display);
  font-size: 16px;
  margin-bottom: 14px;
  letter-spacing: 0.06em;
}

.dreamArchivePanelText {
  color: var(--text-main);
  font-size: 13px;
  line-height: 1.72;
  margin-bottom: 22px;
  white-space: pre-wrap;
  word-break: break-word;
}

.dreamArchivePanelMuted {
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.72;
  margin-bottom: 22px;
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
  height: 104px;
  background: rgba(255,255,255,0.045);
  border: 0.5px solid var(--border);
  color: white;
  padding: 12px;
  border-radius: 10px;
  margin-bottom: 16px;
  outline: none;
  resize: none;
  font-size: 13px;
  line-height: 1.65;
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
  position: relative;
  margin: 18px 0 22px;
  padding-left: 50px;
}

.dreamArchiveFishSvg {
  position: absolute;
  left: 0;
  top: 0;
  width: 50px;
  min-height: 340px;
  pointer-events: none;
  z-index: 0;
}

.dreamArchiveFishPath {
  fill: none;
  stroke: rgba(255,255,255,0.15);
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.dreamArchiveFishCard {
  position: relative;
  display: block;
  width: 100%;
  min-height: 42px;
  margin: 0 0 18px;
  padding: 0;
  text-align: left;
  background: transparent;
  border: 0;
  color: inherit;
  z-index: 1;
}

.dreamArchiveFishCard:nth-of-type(odd) {
  transform: translateX(-8px);
}

.dreamArchiveFishCard:nth-of-type(even) {
  transform: translateX(8px);
}

.dreamArchiveFishStar {
  position: absolute;
  left: -42px;
  top: 1px;
  width: 26px;
  height: 26px;
  filter: drop-shadow(0 0 5px rgba(255,255,255,0.1));
  animation: dreamArchiveSoftFloat 5.6s ease-in-out infinite;
  animation-delay: var(--star-delay, 0s);
  will-change: transform;
}

.dreamArchiveFishText {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.6;
  padding-top: 2px;
}

.dreamArchiveFoldedStar {
  fill: rgba(229, 229, 231, 0.72);
  opacity: 0.9;
  stroke: var(--text-main);
  stroke-width: 0.6;
}

.dreamArchiveFoldedStar.gold {
  fill: var(--accent);
  opacity: 1;
  filter: drop-shadow(0 0 8px var(--accent));
}

@keyframes dreamArchiveSoftFloat {
  0%, 100% { transform: translate3d(0, 0, 0) rotate(0deg); }
  50% { transform: translate3d(2px, -6px, 0) rotate(4deg); }
}

@media (prefers-reduced-motion: reduce) {
  .dreamArchiveOrbitField,
  .dreamArchiveOrbitRing,
  .dreamArchivePaperStar,
  .dreamArchiveFishStar,
  .dreamArchiveNode,
  .dreamArchiveBottle,
  .dreamArchiveBottleRibbon,
  .dreamArchiveBottleStar {
    animation: none;
  }
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

function normalizeStars(input: unknown, key: string, limit = 80): FragmentStar[] {
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
      theme_id: typeof item === "object" && item ? String((item as FragmentStar).theme_id || "") : "",
    });
  });
  return out.slice(0, limit);
}

function normalizePacks(input: unknown, key: string): FragmentPack[] {
  if (!Array.isArray(input)) return [];
  return input
    .map((pack, index) => {
      const rawPack = pack && typeof pack === "object" ? (pack as any) : {};
      const id = String(rawPack.id || rawPack.theme_id || `${key}-${index}`).trim() || `${key}-${index}`;
      const rawStars = Array.isArray(rawPack.stars) ? rawPack.stars : rawPack.fragments;
      const stars = normalizeStars(rawStars || [], id, 12).map((star) => ({
        ...star,
        theme_id: star.theme_id || id,
      }));
      return { id, stars };
    })
    .filter((pack) => pack.stars.length);
}

function groupStarsIntoPacks(stars: FragmentStar[]): FragmentPack[] {
  const grouped = new Map<string, FragmentStar[]>();
  stars.forEach((star, index) => {
    const id = String(star.theme_id || `pack-${Math.floor(index / 5)}`).trim();
    const bucket = grouped.get(id) || [];
    bucket.push({ ...star, theme_id: star.theme_id || id });
    grouped.set(id, bucket);
  });
  return Array.from(grouped.entries()).map(([id, packStars]) => ({ id, stars: packStars }));
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
    theme_id: prefix,
  };
}

function StarSvg({ gold = false }: { gold?: boolean }) {
  return (
    <svg viewBox="0 0 100 100" className={`dreamArchiveFoldedStar ${gold ? "gold" : ""}`}>
      <path d="M50 5 L61 40 L95 40 L68 60 L78 95 L50 75 L22 95 L32 60 L5 40 L39 40 Z" />
    </svg>
  );
}

function fishPathForCount(count: number): string {
  if (count <= 0) return "";
  const step = 60;
  const points: Array<[number, number]> = [[20, 14]];
  for (let index = 1; index < count; index += 1) {
    const prev = 14 + (index - 1) * step;
    const next = 14 + index * step;
    points.push([20, prev + 26], [index % 2 === 1 ? 12 : 28, prev + 46], [20, next]);
  }
  return points.map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x},${y}`).join(" ");
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
  const [libraryPacks, setLibraryPacks] = useState<FragmentPack[]>([]);
  const [libraryLoaded, setLibraryLoaded] = useState(false);
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
    apiJson<DreamFragmentLibraryResp>("/miniapp-api/spring-dream-fragments?limit=120")
      .then((res) => {
        if (cancelled) return;
        const remotePacks = normalizePacks(res.packs || [], "remote-library");
        if (remotePacks.length) {
          setLibraryPacks(remotePacks);
          return;
        }
        const remote = normalizeStars(res.stars || res.fragments || [], "remote-library", 120);
        if (remote.length) setLibraryPacks(groupStarsIntoPacks(remote));
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLibraryLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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

  const libraryFragments = useMemo(() => libraryPacks.flatMap((pack) => pack.stars), [libraryPacks]);

  const fragmentStars = useMemo(() => {
    const fromSelected = Array.isArray(detail?.fragments)
      ? detail.fragments.filter(Boolean).map((fragment, index) => starFromText(String(fragment), index, "selected"))
      : [];
    const fromArchive = items
      .flatMap((item) => (Array.isArray(item.fragments) ? item.fragments : []))
      .filter(Boolean)
      .slice(0, 12)
      .map((fragment, index) => starFromText(String(fragment), index, "archive"));
    const merged = [...libraryFragments, ...localFragments, ...fromSelected, ...fromArchive];
    const seen = new Set<string>();
    return merged.filter((star) => {
      const key = star.text;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [detail?.fragments, items, libraryFragments, localFragments]);

  const visibleFragmentStars = useMemo(() => fragmentStars.slice(0, 60), [fragmentStars]);
  const fishPacks = useMemo(() => {
    return libraryPacks.filter((pack) => pack.stars.length);
  }, [libraryPacks]);

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
        const key = star.text;
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
    const packs = fishPacks;
    if (!packs.length) {
      setPanel({ type: "fish", stars: [] });
      return;
    }
    const pack = packs[Math.floor(Math.random() * packs.length)];
    const picked = (pack?.stars || []).slice(0, 8);
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
          <div className="dreamArchivePanelTitle">写一颗星</div>
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
          <button className="dreamArchiveGhost dreamArchivePrimary" type="button" onClick={() => saveDraftAsFragment("fragment")}>放好了</button>
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
            <svg
              className="dreamArchiveFishSvg"
              viewBox={`0 0 50 ${Math.max(220, panel.stars.length * 60)}`}
              style={{ height: Math.max(220, panel.stars.length * 60) }}
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <path className="dreamArchiveFishPath" d={fishPathForCount(panel.stars.length)} />
            </svg>
            {panel.stars.map((star, index) => (
              <button className="dreamArchiveFishCard" key={star.id} type="button" onClick={() => setPanel({ type: "fragment", star })}>
                <div
                  className="dreamArchiveFishStar"
                  style={{ "--star-delay": `${-(index % 5) * 0.42}s` } as React.CSSProperties}
                >
                  <StarSvg gold={star.color === "gold"} />
                </div>
                <div className="dreamArchiveFishText">{star.text}</div>
              </button>
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
        <div className="dreamArchiveOrbitField" aria-hidden="true">
          <div className="dreamArchiveOrbitRing" />
          <div className="dreamArchiveOrbitRing" />
          <div className="dreamArchiveOrbitRing" />
        </div>
        <div style={{ position: "relative", zIndex: 1, display: "flex", justifyContent: "center", marginBottom: 20 }}>
          <button className="dreamArchiveGhost" type="button" onClick={randomFish}>随机打捞</button>
        </div>
        <div className="dreamArchiveStarPool">
          {visibleFragmentStars.map((star, index) => {
            const layout = STAR_LAYOUT[index % STAR_LAYOUT.length];
            const cycle = Math.floor(index / STAR_LAYOUT.length);
            return (
              <button
                key={`${star.id}-${index}`}
                className="dreamArchivePaperStar"
                type="button"
                  style={{
                    gridColumn: `${layout.col} / span 2`,
                    gridRow: `${cycle * 10 + layout.row} / span 1`,
                    "--star-rot": `${layout.rot + index * 7}deg`,
                    "--star-scale": `${layout.scale}`,
                    "--star-offset": `${layout.offset}px`,
                    "--star-drift": `${-5 - (index % 3) * 2}px`,
                    "--star-delay": `${-(index % 7) * 0.38}s`,
                    opacity: layout.opacity,
                  } as React.CSSProperties}
                  onClick={() => setPanel({ type: "fragment", star })}
                  aria-label={star.label || "梦境碎片"}
                >
                  <StarSvg gold={star.color === "gold" || index % 5 === 0} />
                </button>
            );
          })}
          {!fragmentStars.length ? (
            <div className="dreamArchiveEmpty">
              {libraryLoaded ? "没有读到春梦碎片库" : "正在打捞碎片库"}
            </div>
          ) : null}
        </div>
        <button className="dreamArchiveFloat" type="button" onClick={() => setPanel({ type: "fold" })} aria-label="写一颗星">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
      </main>

      <main className={`dreamArchiveView dreamArchiveInspirationView ${view === "inspiration" ? "active" : ""}`}>
        <div className="dreamArchiveBottle">
          <img className="dreamArchiveBottleRibbon" src={dreamBottleRibbonUrl} alt="" aria-hidden="true" />
          <div className="dreamArchiveBottleNeck" />
          <div className="dreamArchiveBottleDust" aria-hidden="true" />
          <div className="dreamArchiveBottleStars">
            {inspirationStars.length ? inspirationStars.map((star, index) => {
              const layout = BOTTLE_STAR_LAYOUT[index % BOTTLE_STAR_LAYOUT.length];
              const layer = Math.floor(index / BOTTLE_STAR_LAYOUT.length);
              return (
                <button
                  className="dreamArchiveBottleStar"
                  type="button"
                  key={`${star.id}-${index}`}
                  style={{
                    "--star-left": `${Math.min(88, Math.max(14, layout.left + (layer % 2 ? 4 : -4) * layer))}%`,
                    "--star-bottom": `${Math.min(92, layout.bottom + layer * 10)}%`,
                    "--star-opacity": Math.max(0.42, layout.opacity - layer * 0.08),
                    "--star-size": `${Math.max(layout.gold ? 46 : 14, layout.size - layer * 6)}px`,
                    "--star-rot": `${layout.rot + layer * 19}deg`,
                    "--star-delay": `${-(index % 6) * 0.35}s`,
                  } as React.CSSProperties}
                  onClick={() => setPanel({ type: "fragment", star })}
                  aria-label={star.label}
                >
                  <StarSvg gold={layout.gold} />
                </button>
              );
            }) : null}
          </div>
        </div>
        <div className="dreamArchiveInspirationActions">
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
