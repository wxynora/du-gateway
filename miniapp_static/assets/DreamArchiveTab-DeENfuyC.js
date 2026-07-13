import{u as ge,r as s,b as w,j as e}from"./index-CeYhAk8U.js";const xe="/miniapp/assets/dream-bottle-ribbon-trimmed-P7Wvj72D.png",Z="miniapp.springDream.localFragments",Q="miniapp.springDream.inspirationStars",G=[{col:2,row:1,rot:-21,scale:1.34,offset:0,opacity:.96},{col:8,row:1,rot:32,scale:.58,offset:13,opacity:.58},{col:5,row:2,rot:8,scale:.94,offset:-7,opacity:.82},{col:11,row:3,rot:-38,scale:1.18,offset:5,opacity:.9},{col:1,row:4,rot:46,scale:.66,offset:-4,opacity:.62},{col:7,row:4,rot:-10,scale:1.52,offset:12,opacity:1},{col:4,row:5,rot:24,scale:.76,offset:-10,opacity:.68},{col:10,row:6,rot:-49,scale:1.06,offset:1,opacity:.86},{col:6,row:7,rot:35,scale:.6,offset:15,opacity:.54},{col:2,row:8,rot:-28,scale:1.24,offset:-6,opacity:.92},{col:8,row:8,rot:13,scale:.72,offset:6,opacity:.64},{col:12,row:9,rot:-16,scale:1.42,offset:-2,opacity:.96},{col:4,row:10,rot:41,scale:.55,offset:10,opacity:.5},{col:9,row:11,rot:-33,scale:.98,offset:-8,opacity:.78}],I=[{left:45,bottom:20,size:72,rot:-15,opacity:1,gold:!0},{left:25,bottom:32,size:20,rot:34,opacity:.58,gold:!1},{left:68,bottom:39,size:66,rot:18,opacity:.98,gold:!0},{left:49,bottom:54,size:18,rot:-28,opacity:.52,gold:!1},{left:32,bottom:60,size:58,rot:-24,opacity:.9,gold:!0},{left:80,bottom:62,size:18,rot:42,opacity:.5,gold:!1},{left:59,bottom:73,size:50,rot:13,opacity:.82,gold:!0},{left:22,bottom:78,size:16,rot:-36,opacity:.44,gold:!1},{left:75,bottom:82,size:20,rot:25,opacity:.46,gold:!1}],fe=`
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
`;function H(n){const o=String(n||"").trim();if(!o)return"--:--";const i=o.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);return i?`${i[1]}.${i[2]}.${i[3]} ${i[4]}:${i[5]}`:o.replace("+08:00","").replace("T"," ").slice(0,16)||o}function ve(n){return Array.isArray(n)?n.filter(o=>!!o&&typeof o=="object"&&!!String(o.id||"").trim()).map(o=>({...o,id:String(o.id||"").trim()})):[]}function S(n,o,i=80){if(!Array.isArray(n))return[];const p=new Set,d=[];return n.forEach((l,g)=>{const h=(typeof l=="string"?l:String((l==null?void 0:l.text)||"")).trim();if(!h||p.has(h))return;p.add(h);const v=typeof l=="object"&&l?String(l.label||""):"";d.push({id:typeof l=="object"&&l?String(l.id||`${o}-${g}`):`${o}-${g}`,label:(v.trim()||k(h,"梦境碎片")).slice(0,16),text:h,color:typeof l=="object"&&l&&l.color==="gold"?"gold":"default",theme_id:typeof l=="object"&&l?String(l.theme_id||""):""})}),d.slice(0,i)}function ue(n,o){return Array.isArray(n)?n.map((i,p)=>{const d=i&&typeof i=="object"?i:{},l=String(d.id||d.theme_id||`${o}-${p}`).trim()||`${o}-${p}`,g=Array.isArray(d.stars)?d.stars:d.fragments,A=S(g||[],l,12).map(h=>({...h,theme_id:h.theme_id||l}));return{id:l,stars:A}}).filter(i=>i.stars.length):[]}function be(n){const o=new Map;return n.forEach((i,p)=>{const d=String(i.theme_id||`pack-${Math.floor(p/5)}`).trim(),l=o.get(d)||[];l.push({...i,theme_id:i.theme_id||d}),o.set(d,l)}),Array.from(o.entries()).map(([i,p])=>({id:i,stars:p}))}function ee(n){try{return S(JSON.parse(localStorage.getItem(n)||"[]"),n)}catch{return[]}}function te(n,o){try{localStorage.setItem(n,JSON.stringify(o.slice(0,80)))}catch{}}function k(n,o){const i=n.replace(/[_#*-]+/g," ").replace(/\s+/g," ").trim();return i?i.length>8?i.slice(0,8):i:o}function re(n,o){const i=k(String(n.theme_id||""),"");if(i)return i;const p=k(String(n.preview||n.content||""),"");return p||`第 ${o+1} 场梦`}function ye(n){return String(n.preview||n.content||"没有预览").trim()}function D(n,o,i){return{id:`${i}-${o}-${n.slice(0,8)}`,label:k(n,"梦境碎片"),text:n,color:o%3===1?"gold":"default",theme_id:i}}function j({gold:n=!1}){return e.jsx("svg",{viewBox:"0 0 100 100",className:`dreamArchiveFoldedStar ${n?"gold":""}`,children:e.jsx("path",{d:"M50 5 L61 40 L95 40 L68 60 L78 95 L50 75 L22 95 L32 60 L5 40 L39 40 Z"})})}function Ae(n){if(n<=0)return"";const o=60,i=[[20,14]];for(let p=1;p<n;p+=1){const d=14+(p-1)*o,l=14+p*o;i.push([20,d+26],[p%2===1?12:28,d+46],[20,l])}return i.map(([p,d],l)=>`${l===0?"M":"L"} ${p},${d}`).join(" ")}function je({backHandlerRef:n}){const o=ge(),[i,p]=s.useState([]),[d,l]=s.useState(""),[g,A]=s.useState(null),[h,v]=s.useState("dreams"),[m,x]=s.useState(null),[z,_]=s.useState(!1),[ae,Y]=s.useState(!1),[$,N]=s.useState(""),[T,ie]=s.useState(()=>ee(Z)),[F,V]=s.useState([]),[ne,oe]=s.useState(!1),[b,X]=s.useState(()=>ee(Q)),[J,se]=s.useState(!1),C=s.useRef(0),B=s.useRef(!1),P=s.useRef(!1),E=s.useRef(JSON.stringify(b)),le=s.useMemo(()=>i.find(t=>t.id===d)||null,[i,d]),y=g||le,R=s.useCallback(async()=>{var t;_(!0);try{const r=await w("/miniapp-api/spring-dream-archives?limit=80"),a=ve(r.items);p(a),!d&&((t=a[0])!=null&&t.id)&&l(a[0].id)}catch(r){o(`读取失败：${(r==null?void 0:r.message)||r}`)}finally{_(!1)}},[d,o]);s.useEffect(()=>{R()},[R]),s.useEffect(()=>{let t=!1;const r=String(d||"").trim();if(!r){A(null);return}return Y(!0),w(`/miniapp-api/spring-dream-archives/${encodeURIComponent(r)}`).then(a=>{t||A(a.item||null)}).catch(a=>{t||o(`读取详情失败：${(a==null?void 0:a.message)||a}`)}).finally(()=>{t||Y(!1)}),()=>{t=!0}},[d,o]),s.useEffect(()=>te(Z,T),[T]),s.useEffect(()=>te(Q,b),[b]),s.useEffect(()=>{let t=!1;return w("/miniapp-api/spring-dream-fragments?limit=120").then(r=>{if(t)return;const a=ue(r.packs||[],"remote-library");if(a.length){V(a);return}const c=S(r.stars||r.fragments||[],"remote-library",120);c.length&&V(be(c))}).catch(()=>{}).finally(()=>{t||oe(!0)}),()=>{t=!0}},[]),s.useEffect(()=>{let t=!1;const r=C.current;return w("/miniapp-api/spring-dream-inspiration").then(a=>{if(t)return;const c=S(a.stars||a.fragments||[],"remote-inspiration");E.current=JSON.stringify(c),C.current===r&&X(c)}).catch(()=>{}).finally(()=>{t||se(!0)}),()=>{t=!0}},[]),s.useEffect(()=>{!J||JSON.stringify(b)===E.current||w("/miniapp-api/spring-dream-inspiration",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({stars:b})}).then(r=>{const a=S(r.stars||r.fragments||[],"saved-inspiration");E.current=JSON.stringify(a),B.current=!1,P.current=!1}).catch(r=>{!B.current||P.current||(P.current=!0,o(`灵感瓶同步失败：${(r==null?void 0:r.message)||r}`))})},[J,b,o]);const U=s.useMemo(()=>F.flatMap(t=>t.stars),[F]),L=s.useMemo(()=>{const t=Array.isArray(y==null?void 0:y.fragments)?y.fragments.filter(Boolean).map((f,u)=>D(String(f),u,"selected")):[],r=i.flatMap(f=>Array.isArray(f.fragments)?f.fragments:[]).filter(Boolean).slice(0,12).map((f,u)=>D(String(f),u,"archive")),a=[...U,...T,...t,...r],c=new Set;return a.filter(f=>{const u=f.text;return c.has(u)?!1:(c.add(u),!0)})},[y==null?void 0:y.fragments,i,U,T]),ce=s.useMemo(()=>L.slice(0,60),[L]),de=s.useMemo(()=>F.filter(t=>t.stars.length),[F]),pe=h==="dreams"?"梦境":h==="fragments"?"碎片":"灵感",M=s.useCallback(()=>m?(x(null),!0):h!=="dreams"?(v("dreams"),!0):!1,[m,h]);s.useEffect(()=>{if(n)return n.current=M,()=>{n.current===M&&(n.current=null)}},[n,M]);function me(t){l(t.id),x({type:"dream",item:t})}function O(t){C.current+=1,B.current=!0,X(t)}function W(t){t.length&&(O(r=>{const a=[...t,...r],c=new Set;return a.filter(f=>{const u=f.text;return c.has(u)?!1:(c.add(u),!0)}).slice(0,36)}),x(null),v("inspiration"))}function q(t){const r=$.trim();if(!r)return;const a={id:`local-${Date.now()}`,label:k(r,"梦境碎片"),text:r,color:t==="inspiration"?"gold":"default"};t==="fragment"?(ie(c=>[a,...c].slice(0,40)),v("fragments")):(O(c=>[a,...c].slice(0,36)),v("inspiration")),N(""),x(null)}function K(){const t=de;if(!t.length){x({type:"fish",stars:[]});return}const r=t[Math.floor(Math.random()*t.length)],a=((r==null?void 0:r.stars)||[]).slice(0,8);x({type:"fish",stars:a})}function he(){if(!m)return null;if(m.type==="dream"){const t=(g==null?void 0:g.id)===m.item.id?g:m.item,r=Array.isArray(t.fragments)?t.fragments.filter(Boolean):[];return e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"dreamArchiveTime",children:H(t.sent_at)}),e.jsx("div",{className:"dreamArchivePanelTitle",children:re(t,0)}),e.jsx("div",{className:"dreamArchivePanelText",children:ae&&!(g!=null&&g.content)?"读取中":(g==null?void 0:g.content)||t.content||t.preview||"没有正文"}),r.length?e.jsxs("div",{style:{borderTop:"0.5px solid var(--border)",paddingTop:20},children:[e.jsx("div",{style:{fontSize:10,color:"var(--text-muted)",marginBottom:12,letterSpacing:"0.1em"},children:"关联碎片"}),e.jsx("div",{style:{display:"flex",gap:8,flexWrap:"wrap"},children:r.slice(0,6).map((a,c)=>e.jsx("button",{type:"button",style:{width:24,height:24,border:0,padding:0,background:"transparent"},onClick:()=>x({type:"fragment",star:D(String(a),c,"detail")}),"aria-label":String(a),children:e.jsx(j,{gold:c%2===0})},`${a}-${c}`))})]}):null]})}return m.type==="fragment"?e.jsxs(e.Fragment,{children:[e.jsx("p",{className:"dreamArchivePanelMuted",children:m.star.text}),e.jsxs("div",{className:"dreamArchivePanelActions",children:[e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>W([m.star]),children:"放进瓶子"}),e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>{N(m.star.text),x({type:"fold"})},children:"编辑"})]})]}):m.type==="fold"?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"dreamArchivePanelTitle",children:"写一颗星"}),e.jsx("textarea",{className:"dreamArchiveTextarea",placeholder:"记录微小的碎片...",value:$,onChange:t=>N(t.target.value)}),e.jsxs("div",{className:"dreamArchiveTagRow",children:[e.jsx("span",{className:"dreamArchiveGhost",style:{borderColor:"var(--accent)",color:"var(--accent)"},children:"场景"}),e.jsx("span",{className:"dreamArchiveGhost",children:"道具"}),e.jsx("span",{className:"dreamArchiveGhost",children:"动作"}),e.jsx("span",{className:"dreamArchiveGhost",children:"氛围"})]}),e.jsx("button",{className:"dreamArchiveGhost dreamArchivePrimary",type:"button",onClick:()=>q("fragment"),children:"放好了"})]}):m.type==="write"?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"dreamArchivePanelTitle",children:"许一个灵感"}),e.jsx("textarea",{className:"dreamArchiveTextarea",style:{height:80},placeholder:"写下今晚的期待...",value:$,onChange:t=>N(t.target.value)}),e.jsx("button",{className:"dreamArchiveGhost dreamArchivePrimary",type:"button",onClick:()=>q("inspiration"),children:"放入瓶中"})]}):e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"dreamArchivePanelTitle",style:{textAlign:"center"},children:"打捞结果"}),m.stars.length?e.jsxs("div",{className:"dreamArchiveFishGrid",children:[e.jsx("svg",{className:"dreamArchiveFishSvg",viewBox:`0 0 50 ${Math.max(220,m.stars.length*60)}`,style:{height:Math.max(220,m.stars.length*60)},preserveAspectRatio:"none","aria-hidden":"true",children:e.jsx("path",{className:"dreamArchiveFishPath",d:Ae(m.stars.length)})}),m.stars.map((t,r)=>e.jsxs("button",{className:"dreamArchiveFishCard",type:"button",onClick:()=>x({type:"fragment",star:t}),children:[e.jsx("div",{className:"dreamArchiveFishStar",style:{"--star-delay":`${-(r%5)*.42}s`},children:e.jsx(j,{gold:t.color==="gold"})}),e.jsx("div",{className:"dreamArchiveFishText",children:t.text})]},t.id))]}):e.jsx("p",{className:"dreamArchivePanelMuted",style:{textAlign:"center"},children:"还没有可以打捞的碎片"}),e.jsxs("div",{className:"dreamArchivePanelActions",children:[e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>W(m.stars),children:"全部收进瓶子"}),e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:K,children:"换一批"})]})]})}return e.jsxs("div",{className:"dreamArchiveRoot",children:[e.jsx("style",{children:fe}),e.jsx("div",{className:"dreamArchiveVortex"}),e.jsx("div",{className:"dreamArchiveGrain"}),e.jsxs("header",{className:"dreamArchiveHeader",children:[e.jsxs("div",{className:"dreamArchiveTitleBlock",children:[e.jsx("div",{className:"dreamArchiveTitleEn",children:"DREAM"}),e.jsx("h1",{className:"dreamArchiveTitle",children:pe})]}),e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>void R(),disabled:z,children:z?"读取中":e.jsx("svg",{width:"14",height:"14",viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"2",children:e.jsx("path",{d:"M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"})})})]}),e.jsx("main",{className:`dreamArchiveView ${h==="dreams"?"active":""}`,children:i.length?e.jsxs("div",{className:"dreamArchiveTimeline",children:[e.jsx("svg",{className:"dreamArchiveTimelineSvg",viewBox:"0 0 50 340",style:{height:Math.max(340,i.length*116)},children:e.jsx("path",{className:"dreamArchiveTimelinePath",d:"M 20,14 L 20,70 L 12,110 L 20,140 L 20,190 L 28,230 L 20,265"})}),i.map((t,r)=>e.jsxs("button",{className:"dreamArchiveEntry",type:"button",onClick:()=>me(t),children:[e.jsx("div",{className:"dreamArchiveNode",children:e.jsx(j,{gold:t.id===d||r%2===0})}),e.jsxs("div",{className:"dreamArchiveTime",children:[H(t.sent_at),t.r2_key?e.jsx("span",{className:"dreamArchiveFav",children:"★"}):null]}),e.jsx("div",{className:"dreamArchiveDreamTitle",children:re(t,r)}),e.jsx("div",{className:"dreamArchivePreview",children:ye(t)})]},t.id))]}):e.jsx("div",{className:"dreamArchiveEmpty",children:z?"正在读取":"还没有梦境记录"})}),e.jsxs("main",{className:`dreamArchiveView dreamArchiveFragmentView ${h==="fragments"?"active":""}`,children:[e.jsxs("div",{className:"dreamArchiveOrbitField","aria-hidden":"true",children:[e.jsx("div",{className:"dreamArchiveOrbitRing"}),e.jsx("div",{className:"dreamArchiveOrbitRing"}),e.jsx("div",{className:"dreamArchiveOrbitRing"})]}),e.jsx("div",{style:{position:"relative",zIndex:1,display:"flex",justifyContent:"center",marginBottom:20},children:e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:K,children:"随机打捞"})}),e.jsxs("div",{className:"dreamArchiveStarPool",children:[ce.map((t,r)=>{const a=G[r%G.length],c=Math.floor(r/G.length);return e.jsx("button",{className:"dreamArchivePaperStar",type:"button",style:{gridColumn:`${a.col} / span 2`,gridRow:`${c*10+a.row} / span 1`,"--star-rot":`${a.rot+r*7}deg`,"--star-scale":`${a.scale}`,"--star-offset":`${a.offset}px`,"--star-drift":`${-5-r%3*2}px`,"--star-delay":`${-(r%7)*.38}s`,opacity:a.opacity},onClick:()=>x({type:"fragment",star:t}),"aria-label":t.label||"梦境碎片",children:e.jsx(j,{gold:t.color==="gold"||r%5===0})},`${t.id}-${r}`)}),L.length?null:e.jsx("div",{className:"dreamArchiveEmpty",children:ne?"没有读到春梦碎片库":"正在打捞碎片库"})]}),e.jsx("button",{className:"dreamArchiveFloat",type:"button",onClick:()=>x({type:"fold"}),"aria-label":"写一颗星",children:e.jsxs("svg",{width:"18",height:"18",viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"2.2",children:[e.jsx("line",{x1:"12",y1:"5",x2:"12",y2:"19"}),e.jsx("line",{x1:"5",y1:"12",x2:"19",y2:"12"})]})})]}),e.jsxs("main",{className:`dreamArchiveView dreamArchiveInspirationView ${h==="inspiration"?"active":""}`,children:[e.jsxs("div",{className:"dreamArchiveBottle",children:[e.jsx("img",{className:"dreamArchiveBottleRibbon",src:xe,alt:"","aria-hidden":"true"}),e.jsx("div",{className:"dreamArchiveBottleNeck"}),e.jsx("div",{className:"dreamArchiveBottleDust","aria-hidden":"true"}),e.jsx("div",{className:"dreamArchiveBottleStars",children:b.length?b.map((t,r)=>{const a=I[r%I.length],c=Math.floor(r/I.length);return e.jsx("button",{className:"dreamArchiveBottleStar",type:"button",style:{"--star-left":`${Math.min(88,Math.max(14,a.left+(c%2?4:-4)*c))}%`,"--star-bottom":`${Math.min(92,a.bottom+c*10)}%`,"--star-opacity":Math.max(.42,a.opacity-c*.08),"--star-size":`${Math.max(a.gold?46:14,a.size-c*6)}px`,"--star-rot":`${a.rot+c*19}deg`,"--star-delay":`${-(r%6)*.35}s`},onClick:()=>x({type:"fragment",star:t}),"aria-label":t.label,children:e.jsx(j,{gold:a.gold})},`${t.id}-${r}`)}):null})]}),e.jsxs("div",{className:"dreamArchiveInspirationActions",children:[e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>x({type:"write"}),children:"写一颗"}),e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>O([]),children:"清空瓶子"})]})]}),e.jsxs("nav",{className:"dreamArchiveNav",children:[e.jsx("button",{className:`dreamArchiveTab ${h==="dreams"?"active":""}`,type:"button",onClick:()=>v("dreams"),children:"梦境"}),e.jsx("button",{className:`dreamArchiveTab ${h==="fragments"?"active":""}`,type:"button",onClick:()=>v("fragments"),children:"碎片"}),e.jsx("button",{className:`dreamArchiveTab ${h==="inspiration"?"active":""}`,type:"button",onClick:()=>v("inspiration"),children:"灵感"})]}),e.jsx("button",{className:`dreamArchiveOverlay ${m?"active":""}`,type:"button",onClick:()=>x(null),"aria-label":"关闭"}),e.jsx("div",{className:`dreamArchivePanel ${m?"active":""}`,children:he()})]})}export{je as DreamArchiveTab};
