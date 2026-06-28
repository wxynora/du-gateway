import{u as se,r as o,b as T,j as e}from"./index-CTMDV7NP.js";const Y="miniapp.springDream.localFragments",U="miniapp.springDream.inspirationStars",W=[{x:13,y:12,rot:-18,scale:1.02},{x:61,y:15,rot:24,scale:.82},{x:35,y:31,rot:9,scale:1.24},{x:75,y:39,rot:-31,scale:.92},{x:17,y:55,rot:42,scale:.74},{x:51,y:63,rot:-8,scale:1.1},{x:72,y:72,rot:18,scale:.7},{x:30,y:76,rot:-44,scale:.88}],oe=`
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
`;function q(a){const n=String(a||"").trim();if(!n)return"--:--";const s=n.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);return s?`${s[1]}.${s[2]}.${s[3]} ${s[4]}:${s[5]}`:n.replace("+08:00","").replace("T"," ").slice(0,16)||n}function le(a){return Array.isArray(a)?a.filter(n=>!!n&&typeof n=="object"&&!!String(n.id||"").trim()).map(n=>({...n,id:String(n.id||"").trim()})):[]}function R(a,n){if(!Array.isArray(a))return[];const s=new Set,u=[];return a.forEach((l,y)=>{const v=(typeof l=="string"?l:String((l==null?void 0:l.text)||"")).trim();if(!v||s.has(v))return;s.add(v);const m=typeof l=="object"&&l?String(l.label||""):"";u.push({id:typeof l=="object"&&l?String(l.id||`${n}-${y}`):`${n}-${y}`,label:(m.trim()||N(v,"梦境碎片")).slice(0,16),text:v,color:typeof l=="object"&&l&&l.color==="gold"?"gold":"default"})}),u.slice(0,36)}function K(a){try{return R(JSON.parse(localStorage.getItem(a)||"[]"),a)}catch{return[]}}function Z(a,n){try{localStorage.setItem(a,JSON.stringify(n.slice(0,80)))}catch{}}function N(a,n){const s=a.replace(/[_#*-]+/g," ").replace(/\s+/g," ").trim();return s?s.length>8?s.slice(0,8):s:n}function H(a,n){const s=N(String(a.theme_id||""),"");if(s)return s;const u=N(String(a.preview||a.content||""),"");return u||`第 ${n+1} 场梦`}function ce(a){return String(a.preview||a.content||"没有预览").trim()}function M(a,n,s){return{id:`${s}-${n}-${a.slice(0,8)}`,label:N(a,"梦境碎片"),text:a,color:n%3===1?"gold":"default"}}function w({gold:a=!1}){return e.jsxs("svg",{viewBox:"0 0 100 100",className:`dreamArchiveFoldedStar ${a?"gold":""}`,children:[e.jsx("path",{d:"M50 5 L61 40 L95 40 L68 60 L78 95 L50 75 L22 95 L32 60 L5 40 L39 40 Z"}),e.jsx("path",{d:"M50 5 L50 75 M5 40 L68 60 M95 40 L32 60",strokeOpacity:"0.3",fill:"none"})]})}function pe({backHandlerRef:a}){const n=se(),[s,u]=o.useState([]),[l,y]=o.useState(""),[p,v]=o.useState(null),[m,b]=o.useState("dreams"),[c,h]=o.useState(null),[C,D]=o.useState(!1),[Q,I]=o.useState(!1),[$,S]=o.useState(""),[j,ee]=o.useState(()=>K(Y)),[f,O]=o.useState(()=>K(U)),[V,re]=o.useState(!1),F=o.useRef(0),E=o.useRef(!1),P=o.useRef(!1),z=o.useRef(JSON.stringify(f)),te=o.useMemo(()=>s.find(r=>r.id===l)||null,[s,l]),A=p||te,L=o.useCallback(async()=>{var r;D(!0);try{const t=await T("/miniapp-api/spring-dream-archives?limit=80"),i=le(t.items);u(i),!l&&((r=i[0])!=null&&r.id)&&y(i[0].id)}catch(t){n(`读取失败：${(t==null?void 0:t.message)||t}`)}finally{D(!1)}},[l,n]);o.useEffect(()=>{L()},[L]),o.useEffect(()=>{let r=!1;const t=String(l||"").trim();if(!t){v(null);return}return I(!0),T(`/miniapp-api/spring-dream-archives/${encodeURIComponent(t)}`).then(i=>{r||v(i.item||null)}).catch(i=>{r||n(`读取详情失败：${(i==null?void 0:i.message)||i}`)}).finally(()=>{r||I(!1)}),()=>{r=!0}},[l,n]),o.useEffect(()=>Z(Y,j),[j]),o.useEffect(()=>Z(U,f),[f]),o.useEffect(()=>{let r=!1;const t=F.current;return T("/miniapp-api/spring-dream-inspiration").then(i=>{if(r)return;const d=R(i.stars||i.fragments||[],"remote-inspiration");z.current=JSON.stringify(d),F.current===t&&O(d)}).catch(()=>{}).finally(()=>{r||re(!0)}),()=>{r=!0}},[]),o.useEffect(()=>{!V||JSON.stringify(f)===z.current||T("/miniapp-api/spring-dream-inspiration",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({stars:f})}).then(t=>{const i=R(t.stars||t.fragments||[],"saved-inspiration");z.current=JSON.stringify(i),E.current=!1,P.current=!1}).catch(t=>{!E.current||P.current||(P.current=!0,n(`灵感瓶同步失败：${(t==null?void 0:t.message)||t}`))})},[V,f,n]);const k=o.useMemo(()=>{const r=Array.isArray(A==null?void 0:A.fragments)?A.fragments.filter(Boolean).map((x,g)=>M(String(x),g,"selected")):[],t=s.flatMap(x=>Array.isArray(x.fragments)?x.fragments:[]).filter(Boolean).slice(0,12).map((x,g)=>M(String(x),g,"archive")),i=[...r,...t,...j],d=new Set;return i.filter(x=>{const g=`${x.label}:${x.text}`;return d.has(g)?!1:(d.add(g),!0)})},[A==null?void 0:A.fragments,s,j]),ae=m==="dreams"?"梦境":m==="fragments"?"碎片":"灵感",B=o.useCallback(()=>c?(h(null),!0):m!=="dreams"?(b("dreams"),!0):!1,[c,m]);o.useEffect(()=>{if(a)return a.current=B,()=>{a.current===B&&(a.current=null)}},[a,B]);function ie(r){y(r.id),h({type:"dream",item:r})}function G(r){F.current+=1,E.current=!0,O(r)}function J(r){r.length&&(G(t=>{const i=[...r,...t],d=new Set;return i.filter(x=>{const g=`${x.label}:${x.text}`;return d.has(g)?!1:(d.add(g),!0)}).slice(0,36)}),h(null),b("inspiration"))}function _(r){const t=$.trim();if(!t)return;const i={id:`local-${Date.now()}`,label:N(t,"梦境碎片"),text:t,color:r==="inspiration"?"gold":"default"};r==="fragment"?(ee(d=>[i,...d].slice(0,40)),b("fragments")):(G(d=>[i,...d].slice(0,36)),b("inspiration")),S(""),h(null)}function X(){const t=(k.length?k:j).slice().sort(()=>Math.random()-.5).slice(0,2);h({type:"fish",stars:t})}function ne(){if(!c)return null;if(c.type==="dream"){const r=(p==null?void 0:p.id)===c.item.id?p:c.item,t=Array.isArray(r.fragments)?r.fragments.filter(Boolean):[];return e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"dreamArchiveTime",children:q(r.sent_at)}),e.jsx("div",{className:"dreamArchivePanelTitle",children:H(r,0)}),e.jsx("div",{className:"dreamArchivePanelText",children:Q&&!(p!=null&&p.content)?"读取中":(p==null?void 0:p.content)||r.content||r.preview||"没有正文"}),t.length?e.jsxs("div",{style:{borderTop:"0.5px solid var(--border)",paddingTop:20},children:[e.jsx("div",{style:{fontSize:10,color:"var(--text-muted)",marginBottom:12,letterSpacing:"0.1em"},children:"关联碎片"}),e.jsx("div",{style:{display:"flex",gap:8,flexWrap:"wrap"},children:t.slice(0,6).map((i,d)=>e.jsx("button",{type:"button",style:{width:24,height:24,border:0,padding:0,background:"transparent"},onClick:()=>h({type:"fragment",star:M(String(i),d,"detail")}),"aria-label":String(i),children:e.jsx(w,{gold:d%2===0})},`${i}-${d}`))})]}):null]})}return c.type==="fragment"?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"dreamArchivePanelTitle",children:c.star.label}),e.jsx("p",{className:"dreamArchivePanelMuted",children:c.star.text}),e.jsxs("div",{className:"dreamArchivePanelActions",children:[e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>J([c.star]),children:"放进瓶子"}),e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>{S(c.star.text),h({type:"fold"})},children:"编辑"})]})]}):c.type==="fold"?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"dreamArchivePanelTitle",children:"折一颗星"}),e.jsx("textarea",{className:"dreamArchiveTextarea",placeholder:"记录微小的碎片...",value:$,onChange:r=>S(r.target.value)}),e.jsxs("div",{className:"dreamArchiveTagRow",children:[e.jsx("span",{className:"dreamArchiveGhost",style:{borderColor:"var(--accent)",color:"var(--accent)"},children:"场景"}),e.jsx("span",{className:"dreamArchiveGhost",children:"道具"}),e.jsx("span",{className:"dreamArchiveGhost",children:"动作"}),e.jsx("span",{className:"dreamArchiveGhost",children:"氛围"})]}),e.jsx("button",{className:"dreamArchiveGhost dreamArchivePrimary",type:"button",onClick:()=>_("fragment"),children:"折好了"})]}):c.type==="write"?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"dreamArchivePanelTitle",children:"许一个灵感"}),e.jsx("textarea",{className:"dreamArchiveTextarea",style:{height:80},placeholder:"写下今晚的期待...",value:$,onChange:r=>S(r.target.value)}),e.jsx("button",{className:"dreamArchiveGhost dreamArchivePrimary",type:"button",onClick:()=>_("inspiration"),children:"放入瓶中"})]}):e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"dreamArchivePanelTitle",style:{textAlign:"center"},children:"打捞结果"}),c.stars.length?e.jsx("div",{className:"dreamArchiveFishGrid",children:c.stars.map(r=>e.jsxs("div",{className:"dreamArchiveFishCard",children:[e.jsx("div",{className:"dreamArchiveFishStar",children:e.jsx(w,{gold:r.color==="gold"})}),e.jsx("div",{className:"dreamArchiveFishTitle",children:r.label}),e.jsx("div",{className:"dreamArchiveFishText",children:r.text})]},r.id))}):e.jsx("p",{className:"dreamArchivePanelMuted",style:{textAlign:"center"},children:"还没有可以打捞的碎片"}),e.jsxs("div",{className:"dreamArchivePanelActions",children:[e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>J(c.stars),children:"全部收进瓶子"}),e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:X,children:"换一批"})]})]})}return e.jsxs("div",{className:"dreamArchiveRoot",children:[e.jsx("style",{children:oe}),e.jsx("div",{className:"dreamArchiveVortex"}),e.jsx("div",{className:"dreamArchiveGrain"}),e.jsxs("header",{className:"dreamArchiveHeader",children:[e.jsxs("div",{className:"dreamArchiveTitleBlock",children:[e.jsx("div",{className:"dreamArchiveTitleEn",children:"DREAM"}),e.jsx("h1",{className:"dreamArchiveTitle",children:ae})]}),e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>void L(),disabled:C,children:C?"读取中":e.jsx("svg",{width:"14",height:"14",viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"2",children:e.jsx("path",{d:"M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"})})})]}),e.jsx("main",{className:`dreamArchiveView ${m==="dreams"?"active":""}`,children:s.length?e.jsxs("div",{className:"dreamArchiveTimeline",children:[e.jsx("svg",{className:"dreamArchiveTimelineSvg",viewBox:"0 0 50 340",style:{height:Math.max(340,s.length*116)},children:e.jsx("path",{className:"dreamArchiveTimelinePath",d:"M 20,14 L 20,70 L 12,110 L 20,140 L 20,190 L 28,230 L 20,265"})}),s.map((r,t)=>e.jsxs("button",{className:"dreamArchiveEntry",type:"button",onClick:()=>ie(r),children:[e.jsx("div",{className:"dreamArchiveNode",children:e.jsx(w,{gold:r.id===l||t%2===0})}),e.jsxs("div",{className:"dreamArchiveTime",children:[q(r.sent_at),r.r2_key?e.jsx("span",{className:"dreamArchiveFav",children:"★"}):null]}),e.jsx("div",{className:"dreamArchiveDreamTitle",children:H(r,t)}),e.jsx("div",{className:"dreamArchivePreview",children:ce(r)})]},r.id))]}):e.jsx("div",{className:"dreamArchiveEmpty",children:C?"正在读取":"还没有梦境记录"})}),e.jsxs("main",{className:`dreamArchiveView dreamArchiveFragmentView ${m==="fragments"?"active":""}`,children:[e.jsx("div",{style:{display:"flex",justifyContent:"center",marginBottom:20},children:e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:X,children:"随机打捞"})}),e.jsxs("div",{className:"dreamArchiveStarPool",children:[k.map((r,t)=>{const i=W[t%W.length];return e.jsxs("button",{className:"dreamArchivePaperStar",type:"button",style:{left:`${i.x}%`,top:`${i.y}%`,transform:`rotate(${i.rot+t*7}deg) scale(${i.scale})`},onClick:()=>h({type:"fragment",star:r}),children:[e.jsx(w,{gold:r.color==="gold"}),e.jsx("div",{className:"dreamArchiveStarLabel",children:r.label})]},`${r.id}-${t}`)}),k.length?null:e.jsx("div",{className:"dreamArchiveEmpty",children:"还没有折好的星"})]}),e.jsx("button",{className:"dreamArchiveFloat",type:"button",onClick:()=>h({type:"fold"}),"aria-label":"折一颗星",children:e.jsxs("svg",{width:"18",height:"18",viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"2.2",children:[e.jsx("line",{x1:"12",y1:"5",x2:"12",y2:"19"}),e.jsx("line",{x1:"5",y1:"12",x2:"19",y2:"12"})]})})]}),e.jsxs("main",{className:`dreamArchiveView ${m==="inspiration"?"active":""}`,children:[e.jsx("div",{className:"dreamArchiveBottleLabel",children:"今晚的许愿瓶"}),e.jsxs("div",{className:"dreamArchiveBottle",children:[e.jsx("div",{className:"dreamArchiveBottleNeck"}),e.jsx("div",{className:"dreamArchiveBottleStars",children:f.length?f.map((r,t)=>e.jsx("button",{className:"dreamArchiveBottleStar",type:"button",style:{width:`${28+t%5*7}px`,height:`${28+t%5*7}px`,transform:`rotate(${t*31}deg)`,opacity:.68+t%3*.12},onClick:()=>h({type:"fragment",star:r}),"aria-label":r.label,children:e.jsx(w,{gold:r.color==="gold"||t%3===0})},`${r.id}-${t}`)):e.jsx("div",{style:{color:"var(--text-muted)",fontSize:12,marginTop:100},children:"今晚还没有星星"})})]}),e.jsxs("div",{style:{display:"flex",justifyContent:"center",gap:12,marginTop:20},children:[e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>h({type:"write"}),children:"写一颗"}),e.jsx("button",{className:"dreamArchiveGhost",type:"button",onClick:()=>G([]),children:"清空瓶子"})]})]}),e.jsxs("nav",{className:"dreamArchiveNav",children:[e.jsx("button",{className:`dreamArchiveTab ${m==="dreams"?"active":""}`,type:"button",onClick:()=>b("dreams"),children:"梦境"}),e.jsx("button",{className:`dreamArchiveTab ${m==="fragments"?"active":""}`,type:"button",onClick:()=>b("fragments"),children:"碎片"}),e.jsx("button",{className:`dreamArchiveTab ${m==="inspiration"?"active":""}`,type:"button",onClick:()=>b("inspiration"),children:"灵感"})]}),e.jsx("button",{className:`dreamArchiveOverlay ${c?"active":""}`,type:"button",onClick:()=>h(null),"aria-label":"关闭"}),e.jsx("div",{className:`dreamArchivePanel ${c?"active":""}`,children:ne()})]})}export{pe as DreamArchiveTab};
