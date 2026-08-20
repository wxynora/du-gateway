import{u as ye,r as l,b as w,j as e}from"./index-CvUR0Xo2.js";const Ae="/miniapp/assets/dream-bottle-ribbon-trimmed-P7Wvj72D.png",te="miniapp.springDream.localFragments",re="miniapp.springDream.inspirationStars",V=[{col:2,row:1,rot:-21,scale:1.34,offset:0,opacity:.96},{col:8,row:1,rot:32,scale:.58,offset:13,opacity:.58},{col:5,row:2,rot:8,scale:.94,offset:-7,opacity:.82},{col:11,row:3,rot:-38,scale:1.18,offset:5,opacity:.9},{col:1,row:4,rot:46,scale:.66,offset:-4,opacity:.62},{col:7,row:4,rot:-10,scale:1.52,offset:12,opacity:1},{col:4,row:5,rot:24,scale:.76,offset:-10,opacity:.68},{col:10,row:6,rot:-49,scale:1.06,offset:1,opacity:.86},{col:6,row:7,rot:35,scale:.6,offset:15,opacity:.54},{col:2,row:8,rot:-28,scale:1.24,offset:-6,opacity:.92},{col:8,row:8,rot:13,scale:.72,offset:6,opacity:.64},{col:12,row:9,rot:-16,scale:1.42,offset:-2,opacity:.96},{col:4,row:10,rot:41,scale:.55,offset:10,opacity:.5},{col:9,row:11,rot:-33,scale:.98,offset:-8,opacity:.78}],J=[{left:45,bottom:20,size:72,rot:-15,opacity:1,gold:!0},{left:25,bottom:32,size:20,rot:34,opacity:.58,gold:!1},{left:68,bottom:39,size:66,rot:18,opacity:.98,gold:!0},{left:49,bottom:54,size:18,rot:-28,opacity:.52,gold:!1},{left:32,bottom:60,size:58,rot:-24,opacity:.9,gold:!0},{left:80,bottom:62,size:18,rot:42,opacity:.5,gold:!1},{left:59,bottom:73,size:50,rot:13,opacity:.82,gold:!0},{left:22,bottom:78,size:16,rot:-36,opacity:.44,gold:!1},{left:75,bottom:82,size:20,rot:25,opacity:.46,gold:!1}],we=`
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
`;function ae(s){const i=String(s||"").trim();if(!i)return"--:--";const n=i.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);return n?`${n[1]}.${n[2]}.${n[3]} ${n[4]}:${n[5]}`:i.replace("+08:00","").replace("T"," ").slice(0,16)||i}function je(s){return Array.isArray(s)?s.filter(i=>!!i&&typeof i=="object"&&!!String(i.id||"").trim()).map(i=>({...i,id:String(i.id||"").trim()})):[]}function j(s,i,n=80){if(!Array.isArray(s))return[];const m=new Set,p=[];return s.forEach((c,x)=>{const h=(typeof c=="string"?c:String((c==null?void 0:c.text)||"")).trim();if(!h||m.has(h))return;m.add(h);const u=typeof c=="object"&&c?String(c.label||""):"";p.push({id:typeof c=="object"&&c?String(c.id||`${i}-${x}`):`${i}-${x}`,label:(u.trim()||F(h,"梦境碎片")).slice(0,16),text:h,color:typeof c=="object"&&c&&c.color==="gold"?"gold":"default",theme_id:typeof c=="object"&&c?String(c.theme_id||""):""})}),p.slice(0,n)}function Se(s,i){return Array.isArray(s)?s.map((n,m)=>{const p=n&&typeof n=="object"?n:{},c=String(p.id||p.theme_id||`${i}-${m}`).trim()||`${i}-${m}`,x=Array.isArray(p.stars)?p.stars:p.fragments,N=j(x||[],c,12).map(h=>({...h,theme_id:h.theme_id||c}));return{id:c,stars:N}}).filter(n=>n.stars.length):[]}function Ne(s){const i=new Map;return s.forEach((n,m)=>{const p=String(n.theme_id||`pack-${Math.floor(m/5)}`).trim(),c=i.get(p)||[];c.push({...n,theme_id:n.theme_id||p}),i.set(p,c)}),Array.from(i.entries()).map(([n,m])=>({id:n,stars:m}))}function ie(s){try{return j(JSON.parse(localStorage.getItem(s)||"[]"),s)}catch{return[]}}function ne(s,i){try{localStorage.setItem(s,JSON.stringify(i.slice(0,80)))}catch{}}function F(s,i){const n=s.replace(/[_#*-]+/g," ").replace(/\s+/g," ").trim();return n?n.length>8?n.slice(0,8):n:i}function se(s,i){const n=F(String(s.theme_id||""),"");if(n)return n;const m=F(String(s.preview||s.content||""),"");return m||`第 ${i+1} 场梦`}function ke(s){return String(s.preview||s.content||"没有预览").trim()}function X(s,i,n){return{id:`${n}-${i}-${s.slice(0,8)}`,label:F(s,"梦境碎片"),text:s,color:i%3===1?"gold":"default",theme_id:n}}function T({gold:s=!1}){return e.jsx("svg",{viewBox:"0 0 100 100",className:`dreamArchiveFoldedStar ${s?"gold":""}`,children:e.jsx("path",{d:"M50 5 L61 40 L95 40 L68 60 L78 95 L50 75 L22 95 L32 60 L5 40 L39 40 Z"})})}function Te(s){if(s<=0)return"";const i=60,n=[[20,14]];for(let m=1;m<s;m+=1){const p=14+(m-1)*i,c=14+m*i;n.push([20,p+26],[m%2===1?12:28,p+46],[20,c])}return n.map(([m,p],c)=>`${c===0?"M":"L"} ${m},${p}`).join(" ")}function $e({backHandlerRef:s}){const i=ye(),[n,m]=l.useState([]),[p,c]=l.useState(""),[x,N]=l.useState(null),[h,u]=l.useState("dreams"),[d,g]=l.useState(null),[R,U]=l.useState(!1),[oe,W]=l.useState(!1),[S,y]=l.useState(""),[$,le]=l.useState(()=>ie(te)),[k,C]=l.useState([]),[ce,de]=l.useState(!1),[z,P]=l.useState(!1),[b,M]=l.useState(()=>ie(re)),[q,pe]=l.useState(!1),O=l.useRef(0),B=l.useRef(!1),E=l.useRef(!1),L=l.useRef(JSON.stringify(b)),me=l.useMemo(()=>n.find(t=>t.id===p)||null,[n,p]),A=x||me,I=l.useCallback(async()=>{var t;U(!0);try{const r=await w("/miniapp-api/spring-dream-archives?limit=80"),a=je(r.items);m(a),!p&&((t=a[0])!=null&&t.id)&&c(a[0].id)}catch(r){i(`读取失败：${(r==null?void 0:r.message)||r}`)}finally{U(!1)}},[p,i]);l.useEffect(()=>{I()},[I]),l.useEffect(()=>{let t=!1;const r=String(p||"").trim();if(!r){N(null);return}return W(!0),w(`/miniapp-api/spring-dream-archives/${encodeURIComponent(r)}`).then(a=>{t||N(a.item||null)}).catch(a=>{t||i(`读取详情失败：${(a==null?void 0:a.message)||a}`)}).finally(()=>{t||W(!1)}),()=>{t=!0}},[p,i]),l.useEffect(()=>ne(te,$),[$]),l.useEffect(()=>ne(re,b),[b]),l.useEffect(()=>{let t=!1;return w("/miniapp-api/spring-dream-fragments?limit=320").then(r=>{if(t)return;const a=Se(r.packs||[],"remote-library");if(a.length){C(a);return}const o=j(r.stars||r.fragments||[],"remote-library",120);o.length&&C(Ne(o))}).catch(()=>{}).finally(()=>{t||de(!0)}),()=>{t=!0}},[]),l.useEffect(()=>{let t=!1;const r=O.current;return w("/miniapp-api/spring-dream-inspiration").then(a=>{if(t)return;const o=j(a.stars||a.fragments||[],"remote-inspiration");L.current=JSON.stringify(o),O.current===r&&M(o)}).catch(()=>{}).finally(()=>{t||pe(!0)}),()=>{t=!0}},[]),l.useEffect(()=>{!q||JSON.stringify(b)===L.current||w("/miniapp-api/spring-dream-inspiration",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({stars:b})}).then(r=>{const a=j(r.stars||r.fragments||[],"saved-inspiration");L.current=JSON.stringify(a),B.current=!1,E.current=!1}).catch(r=>{!B.current||E.current||(E.current=!0,i(`灵感瓶同步失败：${(r==null?void 0:r.message)||r}`))})},[q,b,i]);const K=l.useMemo(()=>k.flatMap(t=>t.stars),[k]),G=l.useMemo(()=>{const t=Array.isArray(A==null?void 0:A.fragments)?A.fragments.filter(Boolean).map((f,v)=>X(String(f),v,"selected")):[],r=n.flatMap(f=>Array.isArray(f.fragments)?f.fragments:[]).filter(Boolean).slice(0,12).map((f,v)=>X(String(f),v,"archive")),a=[...K,...$,...t,...r],o=new Set;return a.filter(f=>{const v=f.text;return o.has(v)?!1:(o.add(v),!0)})},[A==null?void 0:A.fragments,n,K,$]),he=l.useMemo(()=>G.slice(0,60),[G]),ge=l.useMemo(()=>k.filter(t=>t.stars.length),[k]),xe=h==="dreams"?"梦境":h==="fragments"?"碎片":"灵感",_=l.useCallback(()=>d?(g(null),!0):h!=="dreams"?(u("dreams"),!0):!1,[d,h]);l.useEffect(()=>{if(s)return s.current=_,()=>{s.current===_&&(s.current=null)}},[s,_]);function fe(t){c(t.id),g({type:"dream",item:t})}function D(t){O.current+=1,B.current=!0,M(t)}function Z(t){t.length&&(D(r=>{const a=[...t,...r],o=new Set;return a.filter(f=>{const v=f.text;return o.has(v)?!1:(o.add(v),!0)}).slice(0,36)}),g(null),u("inspiration"))}function Q(t){if(!t)return;const r=j(t.stars||t.fragments||[],"saved-inspiration");M(r),L.current=JSON.stringify(r),B.current=!1,E.current=!1}async function ve(t){const r=String(t.theme_id||"").trim(),a=S.trim();if(!(!r||!a||z)){P(!0);try{const o=await w(`/miniapp-api/spring-dream-materials/${encodeURIComponent(r)}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:a})}),f=j([o.material||{...t,text:a}],r,1)[0];f&&C(v=>v.map(Y=>Y.id===r?{...Y,stars:[{...f,theme_id:r}]}:Y)),Q(o.inspiration),y(""),g(null),i("素材已保存")}catch(o){i(`素材保存失败：${(o==null?void 0:o.message)||o}`)}finally{P(!1)}}}async function ue(t){const r=String(t.theme_id||"").trim();if(!(!r||z)&&window.confirm(`删除“${t.label||r}”这条春梦素材？`)){P(!0);try{const a=await w(`/miniapp-api/spring-dream-materials/${encodeURIComponent(r)}`,{method:"DELETE"});C(o=>o.filter(f=>f.id!==r)),Q(a.inspiration),g(null),i("素材已删除")}catch(a){i(`素材删除失败：${(a==null?void 0:a.message)||a}`)}finally{P(!1)}}}function H(t){const r=S.trim();if(!r)return;const a={id:`local-${Date.now()}`,label:F(r,"梦境碎片"),text:r,color:t==="inspiration"?"gold":"default"};t==="fragment"?(le(o=>[a,...o].slice(0,40)),u("fragments")):(D(o=>[a,...o].slice(0,36)),u("inspiration")),y(""),g(null)}function ee(){const t=ge;if(!t.length){g({type:"fish",stars:[]});return}const r=t[Math.floor(Math.random()*t.length)],a=((r==null?void 0:r.stars)||[]).slice(0,8);g({type:"fish",stars:a})}function be(){if(!d)return null;if(d.type==="dream"){const t=(x==null?void 0:x.id)===d.item.id?x:d.item,r=Array.isArray(t.fragments)?t.fragments.filter(Boolean):[];return e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"dreamArchiveTime",children:ae(t.sent_at)}),e.jsx("div",{className:"dreamArchivePanelTitle",children:se(t,0)}),e.jsx("div",{className:"dreamArchivePanelText",children:oe&&!(x!=null&&x.content)?"读取中":(x==null?void 0:x.content)||t.content||t.preview||"没有正文"}),r.length?e.jsxs("div",{style:{borderTop:"0.5px solid var(--border)",paddingTop:20},children:[e.jsx("div",{style:{fontSize:10,color:"var(--text-muted)",marginBottom:12,letterSpacing:"0.1em"},children:"关联碎片"}),e.jsx("div",{style:{display:"flex",gap:8,flexWrap:"wrap"},children:r.slice(0,6).map((a,o)=>e.jsx("button",{type:"button",style:{width:24,height:24,border:0,padding:0,background:"transparent"},onClick:()=>g({type:"fragment",star:X(String(a),o,"detail")}),"aria-label":String(a),children:e.jsx(T,{gold:o%2===0})},`${a}-${o}`))})]}):null]})}if(d.type==="fragment"){const t=String(d.star.theme_id||"").trim(),r=!!(t&&k.some(a=>a.id===t&&a.stars.some(o=>o.id===d.star.id)));return e.jsxs(e.Fragment,{children:[e.jsx("p",{className:"dreamArchivePanelMuted",children:d.star.text}),e.jsxs("div",{className:"dreamArchivePanelActions",children:[e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>Z([d.star]),children:"放进瓶子"}),r?e.jsxs(e.Fragment,{children:[e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>{y(d.star.text),g({type:"material-edit",star:d.star})},children:"编辑素材"}),e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>void ue(d.star),children:"删除素材"})]}):e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>{y(d.star.text),g({type:"fold"})},children:"编辑"})]})]})}return d.type==="material-edit"?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"dreamArchivePanelTitle",children:"编辑主题素材"}),e.jsx("textarea",{className:"dreamArchiveTextarea",value:S,onChange:t=>y(t.target.value)}),e.jsx("button",{className:"dreamArchiveGhost dreamArchivePrimary",type:"button",disabled:z||!S.trim(),onClick:()=>void ve(d.star),children:z?"保存中":"保存素材"})]}):d.type==="fold"?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"dreamArchivePanelTitle",children:"写一颗星"}),e.jsx("textarea",{className:"dreamArchiveTextarea",placeholder:"记录微小的碎片...",value:S,onChange:t=>y(t.target.value)}),e.jsxs("div",{className:"dreamArchiveTagRow",children:[e.jsx("span",{className:"dreamArchiveGhost",style:{borderColor:"var(--accent)",color:"var(--accent)"},children:"场景"}),e.jsx("span",{className:"dreamArchiveGhost",children:"道具"}),e.jsx("span",{className:"dreamArchiveGhost",children:"动作"}),e.jsx("span",{className:"dreamArchiveGhost",children:"氛围"})]}),e.jsx("button",{className:"dreamArchiveGhost dreamArchivePrimary",type:"button",onClick:()=>H("fragment"),children:"放好了"})]}):d.type==="write"?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"dreamArchivePanelTitle",children:"许一个灵感"}),e.jsx("textarea",{className:"dreamArchiveTextarea",style:{height:80},placeholder:"写下今晚的期待...",value:S,onChange:t=>y(t.target.value)}),e.jsx("button",{className:"dreamArchiveGhost dreamArchivePrimary",type:"button",onClick:()=>H("inspiration"),children:"放入瓶中"})]}):e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"dreamArchivePanelTitle",style:{textAlign:"center"},children:"打捞结果"}),d.stars.length?e.jsxs("div",{className:"dreamArchiveFishGrid",children:[e.jsx("svg",{className:"dreamArchiveFishSvg",viewBox:`0 0 50 ${Math.max(220,d.stars.length*60)}`,style:{height:Math.max(220,d.stars.length*60)},preserveAspectRatio:"none","aria-hidden":"true",children:e.jsx("path",{className:"dreamArchiveFishPath",d:Te(d.stars.length)})}),d.stars.map((t,r)=>e.jsxs("button",{className:"dreamArchiveFishCard",type:"button",onClick:()=>g({type:"fragment",star:t}),children:[e.jsx("div",{className:"dreamArchiveFishStar",style:{"--star-delay":`${-(r%5)*.42}s`},children:e.jsx(T,{gold:t.color==="gold"})}),e.jsx("div",{className:"dreamArchiveFishText",children:t.text})]},t.id))]}):e.jsx("p",{className:"dreamArchivePanelMuted",style:{textAlign:"center"},children:"还没有可以打捞的碎片"}),e.jsxs("div",{className:"dreamArchivePanelActions",children:[e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>Z(d.stars),children:"全部收进瓶子"}),e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:ee,children:"换一批"})]})]})}return e.jsxs("div",{className:"dreamArchiveRoot",children:[e.jsx("style",{children:we}),e.jsx("div",{className:"dreamArchiveVortex"}),e.jsx("div",{className:"dreamArchiveGrain"}),e.jsxs("header",{className:"dreamArchiveHeader",children:[e.jsxs("div",{className:"dreamArchiveTitleBlock",children:[e.jsx("div",{className:"dreamArchiveTitleEn",children:"DREAM"}),e.jsx("h1",{className:"dreamArchiveTitle",children:xe})]}),e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>void I(),disabled:R,children:R?"读取中":e.jsx("svg",{width:"14",height:"14",viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"2",children:e.jsx("path",{d:"M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"})})})]}),e.jsx("main",{className:`dreamArchiveView ${h==="dreams"?"active":""}`,children:n.length?e.jsxs("div",{className:"dreamArchiveTimeline",children:[e.jsx("svg",{className:"dreamArchiveTimelineSvg",viewBox:"0 0 50 340",style:{height:Math.max(340,n.length*116)},children:e.jsx("path",{className:"dreamArchiveTimelinePath",d:"M 20,14 L 20,70 L 12,110 L 20,140 L 20,190 L 28,230 L 20,265"})}),n.map((t,r)=>e.jsxs("button",{className:"dreamArchiveEntry",type:"button",onClick:()=>fe(t),children:[e.jsx("div",{className:"dreamArchiveNode",children:e.jsx(T,{gold:t.id===p||r%2===0})}),e.jsxs("div",{className:"dreamArchiveTime",children:[ae(t.sent_at),t.r2_key?e.jsx("span",{className:"dreamArchiveFav",children:"★"}):null]}),e.jsx("div",{className:"dreamArchiveDreamTitle",children:se(t,r)}),e.jsx("div",{className:"dreamArchivePreview",children:ke(t)})]},t.id))]}):e.jsx("div",{className:"dreamArchiveEmpty",children:R?"正在读取":"还没有梦境记录"})}),e.jsxs("main",{className:`dreamArchiveView dreamArchiveFragmentView ${h==="fragments"?"active":""}`,children:[e.jsxs("div",{className:"dreamArchiveOrbitField","aria-hidden":"true",children:[e.jsx("div",{className:"dreamArchiveOrbitRing"}),e.jsx("div",{className:"dreamArchiveOrbitRing"}),e.jsx("div",{className:"dreamArchiveOrbitRing"})]}),e.jsx("div",{style:{position:"relative",zIndex:1,display:"flex",justifyContent:"center",marginBottom:20},children:e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:ee,children:"随机打捞"})}),e.jsxs("div",{className:"dreamArchiveStarPool",children:[he.map((t,r)=>{const a=V[r%V.length],o=Math.floor(r/V.length);return e.jsx("button",{className:"dreamArchivePaperStar",type:"button",style:{gridColumn:`${a.col} / span 2`,gridRow:`${o*10+a.row} / span 1`,"--star-rot":`${a.rot+r*7}deg`,"--star-scale":`${a.scale}`,"--star-offset":`${a.offset}px`,"--star-drift":`${-5-r%3*2}px`,"--star-delay":`${-(r%7)*.38}s`,opacity:a.opacity},onClick:()=>g({type:"fragment",star:t}),"aria-label":t.label||"梦境碎片",children:e.jsx(T,{gold:t.color==="gold"||r%5===0})},`${t.id}-${r}`)}),G.length?null:e.jsx("div",{className:"dreamArchiveEmpty",children:ce?"没有读到春梦碎片库":"正在打捞碎片库"})]}),e.jsx("button",{className:"dreamArchiveFloat",type:"button",onClick:()=>g({type:"fold"}),"aria-label":"写一颗星",children:e.jsxs("svg",{width:"18",height:"18",viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"2.2",children:[e.jsx("line",{x1:"12",y1:"5",x2:"12",y2:"19"}),e.jsx("line",{x1:"5",y1:"12",x2:"19",y2:"12"})]})})]}),e.jsxs("main",{className:`dreamArchiveView dreamArchiveInspirationView ${h==="inspiration"?"active":""}`,children:[e.jsxs("div",{className:"dreamArchiveBottle",children:[e.jsx("img",{className:"dreamArchiveBottleRibbon",src:Ae,alt:"","aria-hidden":"true"}),e.jsx("div",{className:"dreamArchiveBottleNeck"}),e.jsx("div",{className:"dreamArchiveBottleDust","aria-hidden":"true"}),e.jsx("div",{className:"dreamArchiveBottleStars",children:b.length?b.map((t,r)=>{const a=J[r%J.length],o=Math.floor(r/J.length);return e.jsx("button",{className:"dreamArchiveBottleStar",type:"button",style:{"--star-left":`${Math.min(88,Math.max(14,a.left+(o%2?4:-4)*o))}%`,"--star-bottom":`${Math.min(92,a.bottom+o*10)}%`,"--star-opacity":Math.max(.42,a.opacity-o*.08),"--star-size":`${Math.max(a.gold?46:14,a.size-o*6)}px`,"--star-rot":`${a.rot+o*19}deg`,"--star-delay":`${-(r%6)*.35}s`},onClick:()=>g({type:"fragment",star:t}),"aria-label":t.label,children:e.jsx(T,{gold:a.gold})},`${t.id}-${r}`)}):null})]}),e.jsxs("div",{className:"dreamArchiveInspirationActions",children:[e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>g({type:"write"}),children:"写一颗"}),e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>D([]),children:"清空瓶子"})]})]}),e.jsxs("nav",{className:"dreamArchiveNav",children:[e.jsx("button",{className:`dreamArchiveTab ${h==="dreams"?"active":""}`,type:"button",onClick:()=>u("dreams"),children:"梦境"}),e.jsx("button",{className:`dreamArchiveTab ${h==="fragments"?"active":""}`,type:"button",onClick:()=>u("fragments"),children:"碎片"}),e.jsx("button",{className:`dreamArchiveTab ${h==="inspiration"?"active":""}`,type:"button",onClick:()=>u("inspiration"),children:"灵感"})]}),e.jsx("button",{className:`dreamArchiveOverlay ${d?"active":""}`,type:"button",onClick:()=>g(null),"aria-label":"关闭"}),e.jsx("div",{className:`dreamArchivePanel ${d?"active":""}`,children:be()})]})}export{$e as DreamArchiveTab};
