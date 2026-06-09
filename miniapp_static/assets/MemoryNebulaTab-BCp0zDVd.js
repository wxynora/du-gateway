import{u as Q,r as m,b as B,j as o,R as W}from"./index-C97CwYwY.js";const ee=[{name:"URSA MAJOR",label:{x:118,y:136},stars:[{x:74,y:174,major:!0},{x:130,y:204},{x:195,y:216},{x:244,y:184},{x:304,y:174},{x:356,y:144,major:!0},{x:414,y:120}],lines:[[0,1],[1,2],[2,3],[3,0],[3,4],[4,5],[5,6]]},{name:"LYRA",label:{x:792,y:142},stars:[{x:824,y:108,major:!0,name:"Vega"},{x:780,y:166},{x:846,y:178},{x:803,y:230}],lines:[[0,1],[0,2],[1,2],[1,3],[2,3]]},{name:"ORION",label:{x:662,y:654},stars:[{x:624,y:562,major:!0,name:"Betelgeuse"},{x:746,y:552},{x:660,y:654},{x:704,y:664},{x:748,y:676},{x:602,y:778},{x:804,y:776,major:!0,name:"Rigel"}],lines:[[0,2],[1,4],[2,3],[3,4],[2,5],[4,6],[5,6]]},{name:"CASSIOPEIA",label:{x:168,y:720},stars:[{x:96,y:682},{x:160,y:632,major:!0},{x:230,y:686},{x:300,y:640},{x:364,y:704}],lines:[[0,1],[1,2],[2,3],[3,4]]}];function te(a){let s=2166136261;for(let c=0;c<a.length;c+=1)s^=a.charCodeAt(c),s=Math.imul(s,16777619);return s>>>0}function F(a){const s=String(a||"").replace(/\s+/g," ").trim();return s?s.length>18?`${s.slice(0,18)}...`:s:"Memory"}function V(a){return String(a||"").replace(/\s+/g,"").trim()}function G(a){return a==="positive"||a==="negative"?a:"neutral"}function A(a,s){return String((a==null?void 0:a.memory_id)||(a==null?void 0:a.id)||s).trim()}function U(a,s,c){if(c==="core"){const k=[{x:-72,y:-32,z:138},{x:74,y:42,z:124},{x:-18,y:8,z:190},{x:46,y:-76,z:96}];return k[s%k.length]}const n=te(a),l=n%6283/1e3+s*.55,p=170+(n>>>7)%260,y=-230+(n>>>14)%470,z=-220+(n>>>22)%450;return{x:Math.cos(l)*p+((n>>>5)%88-44),y:y*.72+Math.sin(l*1.7)*72,z}}function ae(a,s){const c=[];return(a.recalled_items||[]).forEach((n,l)=>{const p=A(n,`item-${s}-${l}`);p&&c.push(p)}),(a.referenced_memories||[]).forEach((n,l)=>{const p=A(n,`ref-${s}-${l}`);p&&c.push(p)}),(a.recalled_lines||[]).forEach((n,l)=>{if(typeof n=="string")return;const p=A(n,`line-${s}-${l}`);p&&c.push(p)}),Array.from(new Set(c))}function oe(a){const s=new Map;return[...(a==null?void 0:a.recalls)||[],...(a==null?void 0:a.search_memory_events)||[],...(a==null?void 0:a.citation_events)||[]].forEach((n,l)=>{const p=ae(n,l).slice(0,8);p.forEach((y,z)=>{const k=s.get(y)||new Set;p.forEach((b,j)=>{b!==y&&Math.abs(j-z)<=2&&k.add(b)}),s.set(y,k)})}),s}function se(a,s){var k;const c=[],n=new Set,l=new Set,p=oe(a);return(((k=a==null?void 0:a.core_cache)==null?void 0:k.items)||[]).slice(0,12).forEach((b,j)=>{const f=A(b,`core-${j}`),x=String(b.content||"").trim();if(!f||!x||n.has(f))return;const g=V(x);n.add(f),g&&l.add(g);const $=U(f,j,"core");c.push({id:f,...$,title:F(x),type:"core",emotion:G(b.emotion_label),anchor:"核心",desc:x,connections:[]})}),((s==null?void 0:s.memories)||[]).forEach((b,j)=>{const f=A(b,`dynamic-${j}`),x=String(b.content||"").trim();if(!f||!x||n.has(f))return;const g=V(x);if(g&&l.has(g))return;n.add(f),g&&l.add(g);const $=U(f||x,j,"dynamic");c.push({id:f,...$,title:F(x),type:"dynamic",emotion:G(b.emotion_label),desc:x,connections:Array.from(p.get(f)||[])})}),c}function ne(a){const[s,c]=m.useState({width:390,height:720});return m.useEffect(()=>{const n=a.current;if(!n)return;const l=()=>{const y=n.getBoundingClientRect();c({width:Math.max(320,y.width),height:Math.max(520,y.height)})};l();const p=new ResizeObserver(l);return p.observe(n),()=>p.disconnect()},[a]),s}function ce(){const a=Q(),s=m.useRef(null),c=ne(s),[n,l]=m.useState(null),[p,y]=m.useState(null),[z,k]=m.useState(!1),[b,j]=m.useState(""),[f,x]=m.useState(""),[g,$]=m.useState(""),[_,q]=m.useState(!0),[M,J]=m.useState({x:.18,y:-.16}),S=m.useRef({active:!1,moved:!1,sx:0,sy:0,lx:0,ly:0}),E=m.useRef(M),R=m.useRef(null),C=m.useCallback(async()=>{var e,t,r,u;k(!0);try{const[i,d]=await Promise.allSettled([B("/miniapp-api/memory-debug?limit=16&core_limit=48&scope=all"),B("/miniapp-api/dynamic-memory")]),v=[];if(i.status==="fulfilled"&&((e=i.value)!=null&&e.ok))l(i.value);else{const w=i.status==="rejected"?i.reason:(t=i.value)==null?void 0:t.error;v.push(`核心记忆 ${(w==null?void 0:w.message)||w||"加载失败"}`),l(null)}if(d.status==="fulfilled"&&((r=d.value)!=null&&r.ok))y(d.value);else{const w=d.status==="rejected"?d.reason:(u=d.value)==null?void 0:u.error;v.push(`动态记忆 ${(w==null?void 0:w.message)||w||"加载失败"}`),y(null)}if(j(""),v.length===2)throw new Error(v.join("；"));v.length===1&&a(`记忆星云部分加载失败：${v[0]}`)}catch(i){const d=(i==null?void 0:i.message)||String(i);j(d),a(`记忆星云加载失败：${d}`),l(null),y(null)}finally{k(!1)}},[a]);m.useEffect(()=>{C()},[C]),m.useEffect(()=>{E.current=M},[M]),m.useEffect(()=>()=>{R.current!==null&&window.cancelAnimationFrame(R.current)},[]);const N=m.useMemo(()=>se(n,p),[n,p]),h=N.find(e=>e.id===f)||null,P=m.useMemo(()=>{const e=new Map,t=Math.cos(M.y),r=Math.sin(M.y),u=Math.cos(M.x),i=Math.sin(M.x);return N.forEach(d=>{const v=d.x*t+d.z*r,w=-d.x*r+d.z*t,Z=d.y*u-w*i,D=d.y*i+w*u,L=760,I=Math.max(.48,Math.min(1.7,L/(L-D)));e.set(d.id,{x:c.width/2+v*I,y:c.height/2+Z*I,z:D,depth:I})}),e},[N,M.x,M.y,c.height,c.width]),H=m.useMemo(()=>{const e=new Set;return h&&(h.connections.forEach(t=>e.add(t)),N.forEach(t=>{t.connections.includes(h.id)&&e.add(t.id)})),e},[h,N]);function X(e,t){S.current={active:!0,moved:!1,sx:e,sy:t,lx:e,ly:t}}function Y(e,t){const r=S.current;if(!r.active)return;const u=e-r.lx,i=t-r.ly;Math.abs(e-r.sx)+Math.abs(t-r.sy)>4&&(r.moved=!0),r.lx=e,r.ly=t,E.current={x:Math.max(-1.15,Math.min(1.15,E.current.x-i*.004)),y:E.current.y+u*.006},R.current===null&&(R.current=window.requestAnimationFrame(()=>{R.current=null,J(E.current)}))}function T(){window.setTimeout(()=>{S.current.active=!1,S.current.moved=!1},0)}function K(e){S.current.moved||x(e.id)}function O(e){if(e==="atlas"){q(t=>!t);return}$(t=>t===e?"":e)}return o.jsxs("div",{ref:s,className:`memory-nebula-root h-full min-h-full overflow-hidden ${h?"is-focused":""} ${g==="anchor"?"mode-anchor":""} ${g==="mood"?"mode-mood":""} ${_?"":"atlas-off"}`,onMouseDown:e=>X(e.clientX,e.clientY),onMouseMove:e=>Y(e.clientX,e.clientY),onMouseUp:T,onMouseLeave:T,onTouchStart:e=>{const t=e.touches[0];t&&X(t.clientX,t.clientY)},onTouchMove:e=>{const t=e.touches[0];t&&Y(t.clientX,t.clientY)},onTouchEnd:T,onClick:()=>{S.current.moved||x("")},children:[o.jsx("style",{children:re}),o.jsx("div",{className:"nebula"}),o.jsx("div",{className:"sky-atlas","aria-hidden":!0,children:o.jsx("svg",{viewBox:"0 0 1000 1000",preserveAspectRatio:"none",children:ee.map(e=>o.jsxs("g",{children:[e.lines.map(([t,r])=>{const u=e.stars[t],i=e.stars[r];return o.jsx("line",{className:"sky-atlas-line",x1:u.x,y1:u.y,x2:i.x,y2:i.y},`${t}-${r}`)}),e.stars.map((t,r)=>o.jsxs(W.Fragment,{children:[o.jsx("circle",{className:`sky-atlas-star ${t.major?"major":""}`,cx:t.x,cy:t.y,r:t.major?2.4:1.25}),t.name?o.jsx("text",{className:"sky-atlas-star-label",x:t.x+9,y:t.y-7,children:t.name}):null]},`${e.name}-${r}`)),o.jsx("text",{className:"sky-atlas-label",x:e.label.x,y:e.label.y,children:e.name})]},e.name))})}),o.jsxs("div",{className:"hud",children:[o.jsxs("div",{className:"hud-top",children:[o.jsx("button",{type:"button",className:"crescent-btn",onClick:e=>{e.stopPropagation(),C()},"aria-label":"刷新记忆星云",children:o.jsx("svg",{className:"crescent-svg",width:"24",height:"24",viewBox:"0 0 24 24",children:o.jsx("path",{d:"M12 3a9 9 0 1 0 9 9 9.011 9.011 0 0 1-9-9Z"})})}),o.jsx("h1",{className:"app-title",children:"MNEMOSYNE"}),o.jsx("div",{className:"memory-count",children:z?"...":N.length?`${N.length} stars`:"NO DATA"})]}),o.jsxs("div",{className:"hud-side",children:[o.jsx("button",{type:"button",className:`filter-btn ${g==="anchor"?"active":""}`,onClick:e=>{e.stopPropagation(),O("anchor")},children:"ANCHOR"}),o.jsx("button",{type:"button",className:`filter-btn ${_?"active":""}`,onClick:e=>{e.stopPropagation(),O("atlas")},children:"ATLAS"}),o.jsx("button",{type:"button",className:`filter-btn ${g==="mood"?"active":""}`,onClick:e=>{e.stopPropagation(),O("mood")},children:"MOOD"})]})]}),o.jsxs("div",{className:"constellation-canvas",children:[N.map(e=>{const t=P.get(e.id);if(!t)return null;const r=(h==null?void 0:h.id)===e.id,u=H.has(e.id),i=e.type==="core"?1.08:.92,d=r?1.72:u?1.18:1;return o.jsxs("button",{type:"button",className:`star star-${e.type} ${r?"active":""} ${u?"related":""}`,"data-emotion":e.emotion,style:{left:t.x,top:t.y,opacity:Math.max(.22,Math.min(1,.42+t.depth*.42)),transform:`translate(-50%, -50%) scale(${i*d*t.depth})`,zIndex:Math.round(50+t.z)},onClick:v=>{v.stopPropagation(),K(e)},"aria-label":e.title,children:[o.jsx("span",{className:"star-label",children:e.title}),e.anchor?o.jsx("span",{className:"anchor-name",children:e.anchor}):null]},e.id)}),h?h.connections.map(e=>{const t=P.get(h.id),r=P.get(e);if(!t||!r)return null;const u=r.x-t.x,i=r.y-t.y,d=Math.sqrt(u*u+i*i),v=Math.atan2(i,u)*180/Math.PI;return o.jsx("div",{className:"constellation-line active",style:{left:t.x,top:t.y,width:d,transform:`rotate(${v}deg)`}},`${h.id}-${e}`)}):null]}),N.length?null:o.jsxs("div",{className:"memory-empty-state",onClick:e=>e.stopPropagation(),children:[o.jsx("p",{className:"memory-empty-kicker",children:"NO SAMPLE MEMORY"}),o.jsx("h2",{children:z?"正在读取真实记忆":b?"没有拿到真实记忆":"还没有可显示的记忆"}),o.jsx("p",{children:z?"星云只会从网关返回的记忆内容生成。":b?"接口没有返回可用数据，所以这里不再展示样例卡片。":"等核心记忆或动态召回出现后，这里会生成真实星点。"}),o.jsx("button",{type:"button",onClick:e=>{e.stopPropagation(),C()},children:"重新读取"})]}),h?o.jsxs("div",{className:"logbook active",onClick:e=>e.stopPropagation(),children:[o.jsx("div",{className:"logbook-header",children:o.jsx("button",{type:"button",className:"close-btn",onClick:()=>x(""),"aria-label":"关闭记忆卡片",children:"×"})}),o.jsx("div",{className:"memory-body",children:h.desc})]}):null]})}const re=`
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
  font-family: "Playfair Display", Georgia, "Times New Roman", serif;
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
  will-change: transform, opacity;
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
  opacity: 0.34;
}
.star-core::before,
.star.active::before {
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
  box-shadow: 0 0 7px rgba(255, 255, 255, 0.46);
}
.star-label {
  position: absolute;
  top: 15px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  font-family: "Playfair Display", Georgia, "Times New Roman", serif;
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
.logbook {
  position: absolute;
  left: 50%;
  bottom: calc(env(safe-area-inset-bottom, 0px) + 22px);
  z-index: 30;
  width: min(314px, calc(100% - 48px));
  transform: translateX(-50%);
  border: 1px solid rgba(242, 227, 182, 0.06);
  border-radius: 16px;
  background: rgba(7, 9, 30, 0.22);
  padding: 10px 13px 13px;
  box-shadow: 0 14px 38px rgba(0, 0, 0, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(16px) saturate(1.08);
}
.logbook-header { display: flex; justify-content: flex-end; margin-bottom: 2px; }
.close-btn {
  border: 0;
  background: transparent;
  color: rgba(223, 231, 255, 0.52);
  font-size: 18px;
  line-height: 1;
  padding: 0 0 2px 8px;
}
.memory-body {
  max-height: 116px;
  overflow-y: auto;
  color: rgba(232, 236, 255, 0.76);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
}
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
  font-family: "Playfair Display", Georgia, "Times New Roman", serif;
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
`;export{ce as MemoryNebulaTab};
