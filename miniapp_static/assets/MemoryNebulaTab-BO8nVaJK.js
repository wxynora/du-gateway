import{u as Q,r as u,b as V,j as o,R as W}from"./index-BmQwYVUz.js";const ee=[{name:"URSA MAJOR",label:{x:118,y:136},stars:[{x:74,y:174,major:!0},{x:130,y:204},{x:195,y:216},{x:244,y:184},{x:304,y:174},{x:356,y:144,major:!0},{x:414,y:120}],lines:[[0,1],[1,2],[2,3],[3,0],[3,4],[4,5],[5,6]]},{name:"LYRA",label:{x:792,y:142},stars:[{x:824,y:108,major:!0,name:"Vega"},{x:780,y:166},{x:846,y:178},{x:803,y:230}],lines:[[0,1],[0,2],[1,2],[1,3],[2,3]]},{name:"ORION",label:{x:662,y:654},stars:[{x:624,y:562,major:!0,name:"Betelgeuse"},{x:746,y:552},{x:660,y:654},{x:704,y:664},{x:748,y:676},{x:602,y:778},{x:804,y:776,major:!0,name:"Rigel"}],lines:[[0,2],[1,4],[2,3],[3,4],[2,5],[4,6],[5,6]]},{name:"CASSIOPEIA",label:{x:168,y:720},stars:[{x:96,y:682},{x:160,y:632,major:!0},{x:230,y:686},{x:300,y:640},{x:364,y:704}],lines:[[0,1],[1,2],[2,3],[3,4]]}];function te(a){let s=2166136261;for(let r=0;r<a.length;r+=1)s^=a.charCodeAt(r),s=Math.imul(s,16777619);return s>>>0}function _(a,s){const r=String(a||"").replace(/\s+/g," ").trim(),n=String(s||"").trim();return n&&n!=="default"?n:r?r.length>18?`${r.slice(0,18)}...`:r:"Memory"}function F(a){return String(a||"").replace(/\s+/g,"").trim()}function G(a){return a==="positive"||a==="negative"?a:"neutral"}function C(a,s){return String((a==null?void 0:a.memory_id)||(a==null?void 0:a.id)||s).trim()}function ae(a){const s=String(a.last_mentioned||a.created_at||"").trim();return s?s.length>10?s.slice(0,10):s:"DYNAMIC MEMORY"}function U(a,s,r){if(r==="core"){const j=[{x:-72,y:-32,z:138},{x:74,y:42,z:124},{x:-18,y:8,z:190},{x:46,y:-76,z:96}];return j[s%j.length]}const n=te(a),d=n%6283/1e3+s*.55,x=170+(n>>>7)%260,b=-230+(n>>>14)%470,N=-220+(n>>>22)%450;return{x:Math.cos(d)*x+((n>>>5)%88-44),y:b*.72+Math.sin(d*1.7)*72,z:N}}function oe(a,s){const r=[];return(a.recalled_items||[]).forEach((n,d)=>{const x=C(n,`item-${s}-${d}`);x&&r.push(x)}),(a.referenced_memories||[]).forEach((n,d)=>{const x=C(n,`ref-${s}-${d}`);x&&r.push(x)}),(a.recalled_lines||[]).forEach((n,d)=>{if(typeof n=="string")return;const x=C(n,`line-${s}-${d}`);x&&r.push(x)}),Array.from(new Set(r))}function se(a){const s=new Map;return[...(a==null?void 0:a.recalls)||[],...(a==null?void 0:a.search_memory_events)||[],...(a==null?void 0:a.citation_events)||[]].forEach((n,d)=>{const x=oe(n,d).slice(0,8);x.forEach((b,N)=>{const j=s.get(b)||new Set;x.forEach((m,y)=>{m!==b&&Math.abs(y-N)<=2&&j.add(m)}),s.set(b,j)})}),s}function ne(a,s){var j;const r=[],n=new Set,d=new Set,x=se(a);return(((j=a==null?void 0:a.core_cache)==null?void 0:j.items)||[]).slice(0,12).forEach((m,y)=>{const g=C(m,`core-${y}`),f=String(m.content||"").trim();if(!g||!f||n.has(g))return;const v=F(f);n.add(g),v&&d.add(v);const $=U(g,y,"core");r.push({id:g,...$,title:_(f,m.tag),type:"core",emotion:G(m.emotion_label),anchor:y===0?"Polaris":y===1?"Vega":"Anchor",asterism:`${_(f,m.tag)} Asterism`,date:"CORE MEMORY",desc:f,coord:`imp ${m.importance??"-"} | mention ${m.mention_count??0}`,connections:[],importance:m.importance})}),((s==null?void 0:s.memories)||[]).forEach((m,y)=>{const g=C(m,`dynamic-${y}`),f=String(m.content||"").trim();if(!g||!f||n.has(g))return;const v=F(f);if(v&&d.has(v))return;n.add(g),v&&d.add(v);const $=U(g||f,y,"dynamic");r.push({id:g,...$,title:_(f,m.tag),type:"dynamic",emotion:G(m.emotion_label),date:ae(m),desc:f,coord:`imp ${m.importance??"-"} | mention ${m.mention_count??0}`,connections:Array.from(x.get(g)||[]),importance:m.importance})}),r}function re(a){const[s,r]=u.useState({width:390,height:720});return u.useEffect(()=>{const n=a.current;if(!n)return;const d=()=>{const b=n.getBoundingClientRect();r({width:Math.max(320,b.width),height:Math.max(520,b.height)})};d();const x=new ResizeObserver(d);return x.observe(n),()=>x.disconnect()},[a]),s}function le(){var X,L;const a=Q(),s=u.useRef(null),r=re(s),[n,d]=u.useState(null),[x,b]=u.useState(null),[N,j]=u.useState(!1),[m,y]=u.useState(""),[g,f]=u.useState(""),[v,$]=u.useState(""),[I,J]=u.useState(!0),[S,q]=u.useState({x:.18,y:-.16}),z=u.useRef({active:!1,moved:!1,sx:0,sy:0,lx:0,ly:0}),R=u.useCallback(async()=>{var e,t,i,h;j(!0);try{const[c,p]=await Promise.allSettled([V("/miniapp-api/memory-debug?limit=16&core_limit=48&scope=all"),V("/miniapp-api/dynamic-memory")]),k=[];if(c.status==="fulfilled"&&((e=c.value)!=null&&e.ok))d(c.value);else{const w=c.status==="rejected"?c.reason:(t=c.value)==null?void 0:t.error;k.push(`核心记忆 ${(w==null?void 0:w.message)||w||"加载失败"}`),d(null)}if(p.status==="fulfilled"&&((i=p.value)!=null&&i.ok))b(p.value);else{const w=p.status==="rejected"?p.reason:(h=p.value)==null?void 0:h.error;k.push(`动态记忆 ${(w==null?void 0:w.message)||w||"加载失败"}`),b(null)}if(y(""),k.length===2)throw new Error(k.join("；"));k.length===1&&a(`记忆星云部分加载失败：${k[0]}`)}catch(c){const p=(c==null?void 0:c.message)||String(c);y(p),a(`记忆星云加载失败：${p}`),d(null),b(null)}finally{j(!1)}},[a]);u.useEffect(()=>{R()},[R]);const M=u.useMemo(()=>ne(n,x),[n,x]);u.useMemo(()=>M.filter(e=>e.type==="core"),[M]);const l=M.find(e=>e.id===g)||null,E=u.useMemo(()=>{const e=new Map,t=Math.cos(S.y),i=Math.sin(S.y),h=Math.cos(S.x),c=Math.sin(S.x);return M.forEach(p=>{const k=p.x*t+p.z*i,w=-p.x*i+p.z*t,Z=p.y*h-w*c,B=p.y*c+w*h,D=760,O=Math.max(.48,Math.min(1.7,D/(D-B)));e.set(p.id,{x:r.width/2+k*O,y:r.height/2+Z*O,z:B,depth:O})}),e},[M,S.x,S.y,r.height,r.width]),H=u.useMemo(()=>{const e=new Set;return l&&(l.connections.forEach(t=>e.add(t)),M.forEach(t=>{t.connections.includes(l.id)&&e.add(t.id)})),e},[l,M]);function Y(e,t){z.current={active:!0,moved:!1,sx:e,sy:t,lx:e,ly:t}}function T(e,t){const i=z.current;if(!i.active)return;const h=e-i.lx,c=t-i.ly;Math.abs(e-i.sx)+Math.abs(t-i.sy)>4&&(i.moved=!0),i.lx=e,i.ly=t,q(p=>({x:Math.max(-1.15,Math.min(1.15,p.x-c*.004)),y:p.y+h*.006}))}function A(){window.setTimeout(()=>{z.current.active=!1,z.current.moved=!1},0)}function K(e){z.current.moved||f(e.id)}function P(e){if(e==="atlas"){J(t=>!t);return}$(t=>t===e?"":e)}return o.jsxs("div",{ref:s,className:`memory-nebula-root -mx-3.5 min-h-[calc(100dvh-74px)] overflow-hidden ${l?"is-focused":""} ${v==="anchor"?"mode-anchor":""} ${v==="mood"?"mode-mood":""} ${I?"":"atlas-off"}`,onMouseDown:e=>Y(e.clientX,e.clientY),onMouseMove:e=>T(e.clientX,e.clientY),onMouseUp:A,onMouseLeave:A,onTouchStart:e=>{const t=e.touches[0];t&&Y(t.clientX,t.clientY)},onTouchMove:e=>{const t=e.touches[0];t&&T(t.clientX,t.clientY)},onTouchEnd:A,onClick:()=>{z.current.moved||f("")},children:[o.jsx("style",{children:ie}),o.jsx("div",{className:"nebula"}),o.jsx("div",{className:"sky-atlas","aria-hidden":!0,children:o.jsx("svg",{viewBox:"0 0 1000 1000",preserveAspectRatio:"none",children:ee.map(e=>o.jsxs("g",{children:[e.lines.map(([t,i])=>{const h=e.stars[t],c=e.stars[i];return o.jsx("line",{className:"sky-atlas-line",x1:h.x,y1:h.y,x2:c.x,y2:c.y},`${t}-${i}`)}),e.stars.map((t,i)=>o.jsxs(W.Fragment,{children:[o.jsx("circle",{className:`sky-atlas-star ${t.major?"major":""}`,cx:t.x,cy:t.y,r:t.major?2.4:1.25}),t.name?o.jsx("text",{className:"sky-atlas-star-label",x:t.x+9,y:t.y-7,children:t.name}):null]},`${e.name}-${i}`)),o.jsx("text",{className:"sky-atlas-label",x:e.label.x,y:e.label.y,children:e.name})]},e.name))})}),o.jsxs("div",{className:"hud",children:[o.jsxs("div",{className:"hud-top",children:[o.jsx("button",{type:"button",className:"crescent-btn",onClick:e=>{e.stopPropagation(),R()},"aria-label":"刷新记忆星云",children:o.jsx("svg",{className:"crescent-svg",width:"24",height:"24",viewBox:"0 0 24 24",children:o.jsx("path",{d:"M12 3a9 9 0 1 0 9 9 9.011 9.011 0 0 1-9-9Z"})})}),o.jsx("h1",{className:"app-title",children:"MNEMOSYNE"}),o.jsx("div",{className:"memory-count",children:N?"...":M.length?`${M.length} stars`:"NO DATA"})]}),o.jsxs("div",{className:"hud-side",children:[o.jsx("button",{type:"button",className:`filter-btn ${v==="anchor"?"active":""}`,onClick:e=>{e.stopPropagation(),P("anchor")},children:"ANCHOR"}),o.jsx("button",{type:"button",className:`filter-btn ${I?"active":""}`,onClick:e=>{e.stopPropagation(),P("atlas")},children:"ATLAS"}),o.jsx("button",{type:"button",className:`filter-btn ${v==="mood"?"active":""}`,onClick:e=>{e.stopPropagation(),P("mood")},children:"MOOD"})]})]}),o.jsxs("div",{className:"constellation-canvas",children:[M.map(e=>{const t=E.get(e.id);if(!t)return null;const i=(l==null?void 0:l.id)===e.id,h=H.has(e.id),c=e.type==="core"?1.08:.92,p=i?1.72:h?1.18:1;return o.jsxs("button",{type:"button",className:`star star-${e.type} ${i?"active":""} ${h?"related":""}`,"data-emotion":e.emotion,style:{left:t.x,top:t.y,opacity:Math.max(.22,Math.min(1,.42+t.depth*.42)),transform:`translate(-50%, -50%) scale(${c*p*t.depth})`,zIndex:Math.round(50+t.z)},onClick:k=>{k.stopPropagation(),K(e)},"aria-label":e.title,children:[o.jsx("span",{className:"star-label",children:e.title}),e.anchor?o.jsx("span",{className:"anchor-name",children:e.anchor}):null]},e.id)}),l?l.connections.map(e=>{const t=E.get(l.id),i=E.get(e);if(!t||!i)return null;const h=i.x-t.x,c=i.y-t.y,p=Math.sqrt(h*h+c*c),k=Math.atan2(c,h)*180/Math.PI;return o.jsx("div",{className:"constellation-line active",style:{left:t.x,top:t.y,width:p,transform:`rotate(${k}deg)`}},`${l.id}-${e}`)}):null]}),M.length?null:o.jsxs("div",{className:"memory-empty-state",onClick:e=>e.stopPropagation(),children:[o.jsx("p",{className:"memory-empty-kicker",children:"NO SAMPLE MEMORY"}),o.jsx("h2",{children:N?"正在读取真实记忆":m?"没有拿到真实记忆":"还没有可显示的记忆"}),o.jsx("p",{children:N?"星云只会从网关返回的记忆内容生成。":m?"接口没有返回可用数据，所以这里不再展示样例卡片。":"等核心记忆或动态召回出现后，这里会生成真实星点。"}),o.jsx("button",{type:"button",onClick:e=>{e.stopPropagation(),R()},children:"重新读取"})]}),l?o.jsx("div",{className:"private-asterism active",style:{left:((X=E.get(l.id))==null?void 0:X.x)||r.width/2,top:Math.max(64,(((L=E.get(l.id))==null?void 0:L.y)||r.height/2)-54)},children:l.asterism||`${l.title} Asterism`}):null,l?o.jsxs("div",{className:"logbook active",onClick:e=>e.stopPropagation(),children:[o.jsxs("div",{className:"logbook-header",children:[o.jsxs("div",{children:[o.jsx("p",{className:"memory-date",children:l.date}),o.jsx("h2",{className:"memory-title",children:l.title})]}),o.jsx("button",{type:"button",className:"close-btn",onClick:()=>f(""),"aria-label":"关闭记忆卡片",children:"×"})]}),o.jsx("div",{className:"memory-body",children:l.desc}),o.jsxs("div",{className:"metadata-grid",children:[o.jsxs("div",{className:"meta-item",children:[o.jsx("label",{children:"Coordinates"}),o.jsx("span",{children:l.coord})]}),o.jsxs("div",{className:"meta-item",children:[o.jsx("label",{children:"Intensity"}),o.jsx("span",{children:l.anchor?`${l.anchor} Anchor`:"Temporal Flicker"})]})]})]}):null]})}const ie=`
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
`;export{le as MemoryNebulaTab};
