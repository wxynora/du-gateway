import{u as q,r as h,b as H,j as a,R as Z}from"./index-BMk-KOUz.js";const K=[{name:"URSA MAJOR",label:{x:118,y:136},stars:[{x:74,y:174,major:!0},{x:130,y:204},{x:195,y:216},{x:244,y:184},{x:304,y:174},{x:356,y:144,major:!0},{x:414,y:120}],lines:[[0,1],[1,2],[2,3],[3,0],[3,4],[4,5],[5,6]]},{name:"LYRA",label:{x:792,y:142},stars:[{x:824,y:108,major:!0,name:"Vega"},{x:780,y:166},{x:846,y:178},{x:803,y:230}],lines:[[0,1],[0,2],[1,2],[1,3],[2,3]]},{name:"ORION",label:{x:662,y:654},stars:[{x:624,y:562,major:!0,name:"Betelgeuse"},{x:746,y:552},{x:660,y:654},{x:704,y:664},{x:748,y:676},{x:602,y:778},{x:804,y:776,major:!0,name:"Rigel"}],lines:[[0,2],[1,4],[2,3],[3,4],[2,5],[4,6],[5,6]]},{name:"CASSIOPEIA",label:{x:168,y:720},stars:[{x:96,y:682},{x:160,y:632,major:!0},{x:230,y:686},{x:300,y:640},{x:364,y:704}],lines:[[0,1],[1,2],[2,3],[3,4]]}];function D(n){let p=2166136261;for(let r=0;r<n.length;r+=1)p^=n.charCodeAt(r),p=Math.imul(p,16777619);return p>>>0}function A(n,p){const r=String(n||"").replace(/\s+/g," ").trim(),m=String(p||"").trim();return m&&m!=="default"?m:r?r.length>18?`${r.slice(0,18)}...`:r:"Memory"}function L(n){return n==="positive"||n==="negative"?n:"neutral"}function B(n,p,r){if(r==="core"){const d=[{x:-72,y:-32,z:138},{x:74,y:42,z:124},{x:-18,y:8,z:190},{x:46,y:-76,z:96}];return d[p%d.length]}const m=D(n),v=m%6283/1e3+p*.55,f=170+(m>>>7)%260,k=-230+(m>>>14)%470,o=-220+(m>>>22)%450;return{x:Math.cos(v)*f+((m>>>5)%88-44),y:k*.72+Math.sin(v*1.7)*72,z:o}}function Q(n){var k;const p=[],r=new Set;(((k=n==null?void 0:n.core_cache)==null?void 0:k.items)||[]).slice(0,12).forEach((o,d)=>{const s=String(o.memory_id||o.id||`core-${d}`).trim(),x=String(o.content||"").trim();if(!s||!x||r.has(s))return;r.add(s);const l=B(s,d,"core");p.push({id:s,...l,title:A(x,o.tag),type:"core",emotion:L(o.emotion_label),anchor:d===0?"Polaris":d===1?"Vega":"Anchor",asterism:`${A(x,o.tag)} Asterism`,date:"CORE MEMORY",desc:x,coord:`imp ${o.importance??"-"} | mention ${o.mention_count??0}`,connections:[],importance:o.importance})});const v=[...(n==null?void 0:n.recalls)||[],...(n==null?void 0:n.search_memory_events)||[],...(n==null?void 0:n.citation_events)||[]],f=[];return v.forEach((o,d)=>{(o.recalled_items||[]).forEach((s,x)=>{const l=String(s.content||"").trim(),j=String(s.memory_id||s.id||`item-${d}-${x}`).trim();l&&f.push({id:j,content:l,tag:s.tag,importance:s.importance,mention:s.mention_count})}),(o.referenced_memories||[]).forEach((s,x)=>{const l=String(s.content||"").trim(),j=String(s.memory_id||s.id||`ref-${d}-${x}`).trim();l&&f.push({id:j,content:l,tag:s.tag,importance:s.importance,mention:s.mention_count})}),(o.recalled_lines||[]).forEach((s,x)=>{if(typeof s=="string"){const l=s.trim();l&&f.push({id:`line-${D(l)}`,content:l})}else{const l=String(s.content||"").trim(),j=String(s.memory_id||s.id||`line-${d}-${x}`).trim();l&&f.push({id:j,content:l,emotion:s.emotion_label})}})}),f.slice(0,28).forEach((o,d)=>{if(!o.id||r.has(o.id))return;r.add(o.id);const s=B(o.id||o.content,d,"dynamic"),x=p.find(w=>w.type==="core"),l=p.filter(w=>w.type==="core")[d%Math.max(1,p.filter(w=>w.type==="core").length)],j=l?[l.id]:x?[x.id]:[];p.push({id:o.id,...s,title:A(o.content,o.tag),type:"dynamic",emotion:L(o.emotion),date:"DYNAMIC MEMORY",desc:o.content,coord:`imp ${o.importance??"-"} | mention ${o.mention??0}`,connections:j,importance:o.importance})}),p}function W(n){const[p,r]=h.useState({width:390,height:720});return h.useEffect(()=>{const m=n.current;if(!m)return;const v=()=>{const k=m.getBoundingClientRect();r({width:Math.max(320,k.width),height:Math.max(520,k.height)})};v();const f=new ResizeObserver(v);return f.observe(m),()=>f.disconnect()},[n]),p}function at(){var O,Y;const n=q(),p=h.useRef(null),r=W(p),[m,v]=h.useState(null),[f,k]=h.useState(!1),[o,d]=h.useState(""),[s,x]=h.useState(""),[l,j]=h.useState(""),[w,V]=h.useState(!0),[M,F]=h.useState({x:.18,y:-.16}),N=h.useRef({active:!1,moved:!1,sx:0,sy:0,lx:0,ly:0}),$=h.useCallback(async()=>{k(!0);try{const t=await H("/miniapp-api/memory-debug?limit=16&core_limit=48&scope=all");if(!(t!=null&&t.ok))throw new Error((t==null?void 0:t.error)||"加载失败");d(""),v(t)}catch(t){const e=(t==null?void 0:t.message)||String(t);d(e),n(`记忆星云加载失败：${e}`),v(null)}finally{k(!1)}},[n]);h.useEffect(()=>{$()},[$]);const y=h.useMemo(()=>Q(m),[m]);h.useMemo(()=>y.filter(t=>t.type==="core"),[y]);const i=y.find(t=>t.id===s)||null,z=h.useMemo(()=>{const t=new Map,e=Math.cos(M.y),c=Math.sin(M.y),u=Math.cos(M.x),b=Math.sin(M.x);return y.forEach(g=>{const S=g.x*e+g.z*c,T=-g.x*c+g.z*e,J=g.y*u-T*b,I=g.y*b+T*u,X=760,R=Math.max(.48,Math.min(1.7,X/(X-I)));t.set(g.id,{x:r.width/2+S*R,y:r.height/2+J*R,z:I,depth:R})}),t},[y,M.x,M.y,r.height,r.width]),G=h.useMemo(()=>{const t=new Set;return i&&(i.connections.forEach(e=>t.add(e)),y.forEach(e=>{e.connections.includes(i.id)&&t.add(e.id)})),t},[i,y]);function _(t,e){N.current={active:!0,moved:!1,sx:t,sy:e,lx:t,ly:e}}function P(t,e){const c=N.current;if(!c.active)return;const u=t-c.lx,b=e-c.ly;Math.abs(t-c.sx)+Math.abs(e-c.sy)>4&&(c.moved=!0),c.lx=t,c.ly=e,F(g=>({x:Math.max(-1.15,Math.min(1.15,g.x-b*.004)),y:g.y+u*.006}))}function E(){window.setTimeout(()=>{N.current.active=!1,N.current.moved=!1},0)}function U(t){N.current.moved||x(t.id)}function C(t){if(t==="atlas"){V(e=>!e);return}j(e=>e===t?"":t)}return a.jsxs("div",{ref:p,className:`memory-nebula-root -mx-3.5 min-h-[calc(100dvh-74px)] overflow-hidden ${i?"is-focused":""} ${l==="anchor"?"mode-anchor":""} ${l==="mood"?"mode-mood":""} ${w?"":"atlas-off"}`,onMouseDown:t=>_(t.clientX,t.clientY),onMouseMove:t=>P(t.clientX,t.clientY),onMouseUp:E,onMouseLeave:E,onTouchStart:t=>{const e=t.touches[0];e&&_(e.clientX,e.clientY)},onTouchMove:t=>{const e=t.touches[0];e&&P(e.clientX,e.clientY)},onTouchEnd:E,onClick:()=>{N.current.moved||x("")},children:[a.jsx("style",{children:tt}),a.jsx("div",{className:"nebula"}),a.jsx("div",{className:"sky-atlas","aria-hidden":!0,children:a.jsx("svg",{viewBox:"0 0 1000 1000",preserveAspectRatio:"none",children:K.map(t=>a.jsxs("g",{children:[t.lines.map(([e,c])=>{const u=t.stars[e],b=t.stars[c];return a.jsx("line",{className:"sky-atlas-line",x1:u.x,y1:u.y,x2:b.x,y2:b.y},`${e}-${c}`)}),t.stars.map((e,c)=>a.jsxs(Z.Fragment,{children:[a.jsx("circle",{className:`sky-atlas-star ${e.major?"major":""}`,cx:e.x,cy:e.y,r:e.major?2.4:1.25}),e.name?a.jsx("text",{className:"sky-atlas-star-label",x:e.x+9,y:e.y-7,children:e.name}):null]},`${t.name}-${c}`)),a.jsx("text",{className:"sky-atlas-label",x:t.label.x,y:t.label.y,children:t.name})]},t.name))})}),a.jsxs("div",{className:"hud",children:[a.jsxs("div",{className:"hud-top",children:[a.jsx("button",{type:"button",className:"crescent-btn",onClick:t=>{t.stopPropagation(),$()},"aria-label":"刷新记忆星云",children:a.jsx("svg",{className:"crescent-svg",width:"24",height:"24",viewBox:"0 0 24 24",children:a.jsx("path",{d:"M12 3a9 9 0 1 0 9 9 9.011 9.011 0 0 1-9-9Z"})})}),a.jsx("h1",{className:"app-title",children:"MNEMOSYNE"}),a.jsx("div",{className:"memory-count",children:f?"...":y.length?`${y.length} stars`:"NO DATA"})]}),a.jsxs("div",{className:"hud-side",children:[a.jsx("button",{type:"button",className:`filter-btn ${l==="anchor"?"active":""}`,onClick:t=>{t.stopPropagation(),C("anchor")},children:"ANCHOR"}),a.jsx("button",{type:"button",className:`filter-btn ${w?"active":""}`,onClick:t=>{t.stopPropagation(),C("atlas")},children:"ATLAS"}),a.jsx("button",{type:"button",className:`filter-btn ${l==="mood"?"active":""}`,onClick:t=>{t.stopPropagation(),C("mood")},children:"MOOD"})]})]}),a.jsxs("div",{className:"constellation-canvas",children:[y.map(t=>{const e=z.get(t.id);if(!e)return null;const c=(i==null?void 0:i.id)===t.id,u=G.has(t.id),b=t.type==="core"?1.08:.92,g=c?1.72:u?1.18:1;return a.jsxs("button",{type:"button",className:`star star-${t.type} ${c?"active":""} ${u?"related":""}`,"data-emotion":t.emotion,style:{left:e.x,top:e.y,opacity:Math.max(.22,Math.min(1,.42+e.depth*.42)),transform:`translate(-50%, -50%) scale(${b*g*e.depth})`,zIndex:Math.round(50+e.z)},onClick:S=>{S.stopPropagation(),U(t)},"aria-label":t.title,children:[a.jsx("span",{className:"star-label",children:t.title}),t.anchor?a.jsx("span",{className:"anchor-name",children:t.anchor}):null]},t.id)}),i?i.connections.map(t=>{const e=z.get(i.id),c=z.get(t);if(!e||!c)return null;const u=c.x-e.x,b=c.y-e.y,g=Math.sqrt(u*u+b*b),S=Math.atan2(b,u)*180/Math.PI;return a.jsx("div",{className:"constellation-line active",style:{left:e.x,top:e.y,width:g,transform:`rotate(${S}deg)`}},`${i.id}-${t}`)}):null]}),y.length?null:a.jsxs("div",{className:"memory-empty-state",onClick:t=>t.stopPropagation(),children:[a.jsx("p",{className:"memory-empty-kicker",children:"NO SAMPLE MEMORY"}),a.jsx("h2",{children:f?"正在读取真实记忆":o?"没有拿到真实记忆":"还没有可显示的记忆"}),a.jsx("p",{children:f?"星云只会从网关返回的记忆内容生成。":o?"接口没有返回可用数据，所以这里不再展示样例卡片。":"等核心记忆或动态召回出现后，这里会生成真实星点。"}),a.jsx("button",{type:"button",onClick:t=>{t.stopPropagation(),$()},children:"重新读取"})]}),i?a.jsx("div",{className:"private-asterism active",style:{left:((O=z.get(i.id))==null?void 0:O.x)||r.width/2,top:Math.max(64,(((Y=z.get(i.id))==null?void 0:Y.y)||r.height/2)-54)},children:i.asterism||`${i.title} Asterism`}):null,i?a.jsxs("div",{className:"logbook active",onClick:t=>t.stopPropagation(),children:[a.jsxs("div",{className:"logbook-header",children:[a.jsxs("div",{children:[a.jsx("p",{className:"memory-date",children:i.date}),a.jsx("h2",{className:"memory-title",children:i.title})]}),a.jsx("button",{type:"button",className:"close-btn",onClick:()=>x(""),"aria-label":"关闭记忆卡片",children:"×"})]}),a.jsx("div",{className:"memory-body",children:i.desc}),a.jsxs("div",{className:"metadata-grid",children:[a.jsxs("div",{className:"meta-item",children:[a.jsx("label",{children:"Coordinates"}),a.jsx("span",{children:i.coord})]}),a.jsxs("div",{className:"meta-item",children:[a.jsx("label",{children:"Intensity"}),a.jsx("span",{children:i.anchor?`${i.anchor} Anchor`:"Temporal Flicker"})]})]})]}):null]})}const tt=`
.memory-nebula-root {
  position: relative;
  width: 100%;
  background: radial-gradient(circle at 50% 50%, #101435 0%, #04051a 100%);
  color: #f0f0d0;
  cursor: grab;
  touch-action: none;
  user-select: none;
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.memory-nebula-root:active { cursor: grabbing; }
.nebula {
  position: absolute;
  width: 150%;
  height: 150%;
  top: -25%;
  left: -25%;
  background: radial-gradient(circle at 20% 30%, rgba(65, 48, 122, 0.15) 0%, transparent 40%),
    radial-gradient(circle at 80% 70%, rgba(30, 58, 138, 0.1) 0%, transparent 50%);
  filter: blur(60px);
  pointer-events: none;
}
.sky-atlas {
  position: absolute;
  inset: 0;
  opacity: 0.32;
  mix-blend-mode: screen;
  pointer-events: none;
  transition: opacity 0.4s ease;
}
.atlas-off .sky-atlas { opacity: 0; }
.sky-atlas svg { width: 100%; height: 100%; display: block; }
.sky-atlas-line { stroke: rgba(178, 184, 216, 0.16); stroke-width: 0.72; vector-effect: non-scaling-stroke; }
.sky-atlas-star { fill: rgba(223, 229, 255, 0.42); }
.sky-atlas-star.major { fill: rgba(242, 227, 182, 0.66); filter: drop-shadow(0 0 4px rgba(242, 227, 182, 0.38)); }
.sky-atlas-label,
.sky-atlas-star-label {
  fill: rgba(189, 195, 224, 0.28);
  font-size: 8px;
  letter-spacing: 0.26em;
  text-transform: uppercase;
}
.sky-atlas-star-label { fill: rgba(242, 227, 182, 0.4); font-size: 7px; letter-spacing: 0.22em; }
.hud { position: absolute; inset: 0; z-index: 20; pointer-events: none; }
.hud-top {
  position: absolute;
  top: 18px;
  left: 18px;
  right: 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  pointer-events: auto;
}
.app-title {
  font-family: "Times New Roman", Georgia, serif;
  font-size: 18px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  font-style: italic;
}
.memory-count {
  min-width: 42px;
  text-align: right;
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(142, 148, 175, 0.76);
}
.crescent-btn {
  display: flex;
  width: 40px;
  height: 40px;
  align-items: center;
  justify-content: center;
  border: 0;
  background: transparent;
  color: #f2e3b6;
}
.crescent-svg { fill: none; stroke: #f2e3b6; stroke-width: 1.5; filter: drop-shadow(0 0 5px rgba(242, 227, 182, 0.8)); }
.hud-side {
  position: absolute;
  right: 16px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  gap: 20px;
  pointer-events: auto;
}
.filter-btn {
  appearance: none;
  border: 0;
  border-right: 1px solid rgba(142, 148, 175, 0.2);
  border-radius: 999px;
  background: transparent;
  writing-mode: vertical-rl;
  padding: 11px 7px;
  color: #8e94af;
  font: inherit;
  font-size: 9px;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  opacity: 0.62;
  transition: color 0.24s ease, opacity 0.24s ease, border-color 0.24s ease, text-shadow 0.24s ease, background 0.24s ease, box-shadow 0.24s ease, transform 0.24s ease;
}
.filter-btn.active {
  color: #f2e3b6;
  opacity: 1;
  border-right-color: rgba(242, 227, 182, 0.48);
  background: rgba(242, 227, 182, 0.06);
  box-shadow: inset -2px 0 0 rgba(242, 227, 182, 0.48), 0 0 22px rgba(242, 227, 182, 0.12);
  text-shadow: 0 0 12px rgba(242, 227, 182, 0.32);
  transform: translateX(-4px);
}
.constellation-canvas { position: absolute; inset: 0; z-index: 5; }
.star {
  position: absolute;
  border: 0;
  border-radius: 50%;
  padding: 0;
  cursor: pointer;
  transition: opacity 0.26s ease, filter 0.26s ease, box-shadow 0.3s ease;
}
.star::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  width: 300%;
  height: 300%;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  filter: blur(4px);
  opacity: 0.6;
  animation: nebulaPulse 4s infinite ease-in-out;
}
.star-core {
  width: 8px;
  height: 8px;
  background: #f2e3b6;
  box-shadow: 0 0 15px rgba(242, 227, 182, 0.8), 0 0 30px rgba(242, 227, 182, 0.8);
}
.star-dynamic {
  width: 4px;
  height: 4px;
  background: #fff;
  box-shadow: 0 0 10px rgba(255, 255, 255, 0.6);
}
.star-label {
  position: absolute;
  top: 15px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  font-family: Georgia, "Songti SC", serif;
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  text-shadow: 0 0 14px rgba(4, 5, 26, 0.9);
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.anchor-name {
  position: absolute;
  bottom: 15px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  color: rgba(242, 227, 182, 0.46);
  opacity: 0.52;
  pointer-events: none;
  font-size: 7px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  text-shadow: 0 0 12px rgba(4, 5, 26, 0.95);
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.constellation-line {
  position: absolute;
  height: 0.5px;
  transform-origin: 0 50%;
  pointer-events: none;
  background: linear-gradient(90deg, transparent, rgba(242, 227, 182, 0.8), transparent);
  opacity: 0.78;
  filter: drop-shadow(0 0 10px rgba(242, 227, 182, 0.35));
}
.is-focused .star:not(.active):not(.related) { opacity: 0.15 !important; filter: grayscale(1); }
.mode-anchor .sky-atlas { opacity: 0.18; }
.mode-anchor .star-dynamic { opacity: 0.12 !important; filter: grayscale(1); }
.mode-anchor .star-core { filter: brightness(1.18) drop-shadow(0 0 16px rgba(242, 227, 182, 0.55)); }
.mode-anchor .star-core .star-label,
.mode-anchor .star-core .anchor-name { opacity: 0.92; transform: translateX(-50%) translateY(2px); }
.mode-mood .star-core { opacity: 0.38 !important; filter: grayscale(0.7); }
.mode-mood .star-dynamic { width: 6px; height: 6px; }
.mode-mood .star-dynamic[data-emotion="positive"] { background: #f2e3b6; box-shadow: 0 0 14px rgba(242, 227, 182, 0.72), 0 0 28px rgba(242, 227, 182, 0.28); }
.mode-mood .star-dynamic[data-emotion="negative"] { background: #c5a3ff; box-shadow: 0 0 14px rgba(197, 163, 255, 0.72), 0 0 28px rgba(98, 76, 170, 0.34); }
.mode-mood .star-dynamic[data-emotion="neutral"] { background: #dfe7ff; box-shadow: 0 0 12px rgba(223, 231, 255, 0.56); }
.star.active { filter: none; }
.star.active .star-label,
.star.related .star-label { opacity: 0.82; transform: translateX(-50%) translateY(2px); }
.star.active .anchor-name,
.star.related .anchor-name { opacity: 0.86; transform: translateX(-50%) translateY(-2px); }
.private-asterism {
  position: absolute;
  z-index: 16;
  transform: translate(-50%, -50%);
  color: rgba(242, 227, 182, 0.42);
  font-size: 8px;
  letter-spacing: 0.28em;
  text-transform: uppercase;
  pointer-events: none;
  opacity: 0;
  text-shadow: 0 0 18px rgba(4, 5, 26, 0.96);
}
.private-asterism.active { opacity: 0.72; }
.logbook {
  position: absolute;
  left: 50%;
  bottom: calc(env(safe-area-inset-bottom, 0px) + 22px);
  z-index: 30;
  width: min(292px, calc(100% - 44px));
  transform: translateX(-50%);
  border: 1px solid rgba(242, 227, 182, 0.045);
  border-radius: 18px;
  background: rgba(6, 8, 30, 0.34);
  padding: 14px 15px 13px;
  box-shadow: 0 18px 46px rgba(0, 0, 0, 0.26), inset 0 1px 0 rgba(255, 255, 255, 0.035);
  backdrop-filter: blur(18px) saturate(1.18);
}
.logbook-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 9px; }
.memory-date { margin-bottom: 4px; color: #8e94af; opacity: 0.76; font-size: 8px; letter-spacing: 0.16em; text-transform: uppercase; }
.memory-title { color: #f0f0d0; font-family: Georgia, "Songti SC", serif; font-size: 18px; font-style: italic; line-height: 1.04; }
.close-btn { border: 0; background: transparent; color: rgba(142, 148, 175, 0.9); font-size: 22px; line-height: 1; }
.memory-body {
  max-height: 78px;
  overflow-y: auto;
  color: #8e94af;
  font-size: 12px;
  line-height: 1.45;
  -webkit-mask-image: linear-gradient(to bottom, black 86%, transparent 100%);
  mask-image: linear-gradient(to bottom, black 86%, transparent 100%);
}
.metadata-grid {
  margin-top: 13px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  border-top: 0.5px solid rgba(142, 148, 175, 0.14);
  padding-top: 10px;
}
.meta-item label { display: block; margin-bottom: 3px; color: #f2e3b6; opacity: 0.72; font-size: 7px; letter-spacing: 0.18em; text-transform: uppercase; }
.meta-item span { color: rgba(240, 240, 208, 0.68); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px; }
.memory-empty-state {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 18;
  width: min(286px, calc(100% - 68px));
  transform: translate(-50%, -50%);
  color: rgba(240, 240, 208, 0.72);
  text-align: center;
  pointer-events: auto;
}
.memory-empty-kicker {
  margin-bottom: 9px;
  color: rgba(242, 227, 182, 0.58);
  font-size: 8px;
  letter-spacing: 0.28em;
  text-transform: uppercase;
}
.memory-empty-state h2 {
  margin-bottom: 9px;
  color: #f0f0d0;
  font-family: Georgia, "Songti SC", serif;
  font-size: 20px;
  font-style: italic;
  line-height: 1.15;
}
.memory-empty-state p {
  color: rgba(142, 148, 175, 0.86);
  font-size: 12px;
  line-height: 1.55;
}
.memory-empty-state button {
  margin-top: 18px;
  border: 1px solid rgba(242, 227, 182, 0.16);
  border-radius: 999px;
  background: rgba(242, 227, 182, 0.06);
  padding: 9px 18px;
  color: rgba(240, 240, 208, 0.82);
  font: inherit;
  font-size: 11px;
  letter-spacing: 0.08em;
}
@keyframes nebulaPulse {
  0%, 100% { opacity: 0.4; transform: translate(-50%, -50%) scale(1); }
  50% { opacity: 0.8; transform: translate(-50%, -50%) scale(1.3); }
}
`;export{at as MemoryNebulaTab};
