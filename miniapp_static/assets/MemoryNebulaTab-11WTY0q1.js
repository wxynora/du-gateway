import{u as te,r as h,b as L,j as i,R as oe}from"./index-Bv5N-O_c.js";const re=[{name:"URSA MAJOR",label:{x:118,y:136},stars:[{x:74,y:174,major:!0},{x:130,y:204},{x:195,y:216},{x:244,y:184},{x:304,y:174},{x:356,y:144,major:!0},{x:414,y:120}],lines:[[0,1],[1,2],[2,3],[3,0],[3,4],[4,5],[5,6]]},{name:"LYRA",label:{x:792,y:142},stars:[{x:824,y:108,major:!0,name:"Vega"},{x:780,y:166},{x:846,y:178},{x:803,y:230}],lines:[[0,1],[0,2],[1,2],[1,3],[2,3]]},{name:"ORION",label:{x:662,y:654},stars:[{x:624,y:562,major:!0,name:"Betelgeuse"},{x:746,y:552},{x:660,y:654},{x:704,y:664},{x:748,y:676},{x:602,y:778},{x:804,y:776,major:!0,name:"Rigel"}],lines:[[0,2],[1,4],[2,3],[3,4],[2,5],[4,6],[5,6]]},{name:"CASSIOPEIA",label:{x:168,y:720},stars:[{x:96,y:682},{x:160,y:632,major:!0},{x:230,y:686},{x:300,y:640},{x:364,y:704}],lines:[[0,1],[1,2],[2,3],[3,4]]}];function se(t){let r=2166136261;for(let n=0;n<t.length;n+=1)r^=t.charCodeAt(n),r=Math.imul(r,16777619);return r>>>0}function U(t){const r=String(t||"").replace(/\s+/g," ").trim();return r?r.length>18?`${r.slice(0,18)}...`:r:"Memory"}function ne(t){const r=String(t||"").replace(/\s+/g," ").trim();if(!r)return["Memory"];const n=[];return r.split(/[，。！？；：、\n]+/).map(s=>s.trim()).filter(Boolean).forEach(s=>{if(s.length<=18){n.push(s);return}for(let c=0;c<s.length;c+=18)n.push(s.slice(c,c+18))}),(n.length?n:[r]).slice(0,5)}function ae(t,r,n){return r===0&&t.length<=8?"memory-phrase-title":t.length>=12||r===Math.floor(n/2)?"memory-phrase-loud":r===n-1?"memory-phrase-soft":"memory-phrase-mid"}function ie(t){const r=Number(t);return Number.isFinite(r)?r:null}function ce(t){const r=String(t||"").trim();if(!r)return"T--";const n=new Date(r);if(!Number.isFinite(n.getTime()))return"T--";const s=String(n.getMonth()+1).padStart(2,"0"),c=String(n.getDate()).padStart(2,"0");return`T${s}.${c}`}function le(t,r){if(t!==null)return t<=1?`S${t.toFixed(2)}`:`S${Math.round(t)}`;const n=Math.max(0,Math.min(99,Math.round(Number(r)||0)));return`S${String(n).padStart(2,"0")}`}function B({time:t,importance:r,score:n,mentionCount:s}){const c=Math.max(0,Math.min(9,Math.round(Number(r)||0)));return`${ce(t)} / W${c} / ${le(n??null,s)}`}function q(t){return String(t||"").replace(/\s+/g,"").trim()}function G(t){return t==="positive"||t==="negative"?t:"neutral"}function z(t,r){return String((t==null?void 0:t.memory_id)||(t==null?void 0:t.id)||r).trim()}function H(t,r,n){if(n==="core"){const b=[{x:-72,y:-32,z:138},{x:74,y:42,z:124},{x:-18,y:8,z:190},{x:46,y:-76,z:96}];return b[r%b.length]}const s=se(t),c=s%6283/1e3+r*.55,l=170+(s>>>7)%260,u=-230+(s>>>14)%470,w=-220+(s>>>22)%450;return{x:Math.cos(c)*l+((s>>>5)%88-44),y:u*.72+Math.sin(c*1.7)*72,z:w}}function me(t,r){const n=[];return(t.recalled_items||[]).forEach((s,c)=>{const l=z(s,`item-${r}-${c}`);l&&n.push(l)}),(t.referenced_memories||[]).forEach((s,c)=>{const l=z(s,`ref-${r}-${c}`);l&&n.push(l)}),(t.recalled_lines||[]).forEach((s,c)=>{if(typeof s=="string")return;const l=z(s,`line-${r}-${c}`);l&&n.push(l)}),Array.from(new Set(n))}function pe(t){const r=new Map,n=new Map,s=new Map,c=[...(t==null?void 0:t.recalls)||[],...(t==null?void 0:t.search_memory_events)||[],...(t==null?void 0:t.citation_events)||[]],l=(u,w,b)=>{if(!u)return;const a=ie(w);a!==null&&a>(n.get(u)??-1/0)&&n.set(u,a),b&&!s.has(u)&&s.set(u,b)};return c.forEach((u,w)=>{const b=me(u,w).slice(0,8);b.forEach((a,g)=>{const d=r.get(a)||new Set;b.forEach((v,M)=>{v!==a&&Math.abs(M-g)<=2&&d.add(v)}),r.set(a,d),l(a,void 0,u.timestamp)}),(u.recalled_lines||[]).forEach((a,g)=>{typeof a!="string"&&l(z(a,`line-${w}-${g}`),a.final_score,u.timestamp)}),(u.recalled_items||[]).forEach((a,g)=>{l(z(a,`item-${w}-${g}`),a.final_score,u.timestamp)}),(u.referenced_memories||[]).forEach((a,g)=>{l(z(a,`ref-${w}-${g}`),a.final_score,u.timestamp)})}),{connections:r,scores:n,timestamps:s}}function ue(t,r){var b;const n=[],s=new Set,c=new Set,l=pe(t);return(((b=t==null?void 0:t.core_cache)==null?void 0:b.items)||[]).slice(0,12).forEach((a,g)=>{const d=z(a,`core-${g}`),v=String(a.content||"").trim();if(!d||!v||s.has(d))return;const M=q(v);s.add(d),M&&c.add(M);const N=H(d,g,"core");n.push({id:d,...N,title:B({time:a.promoted_at||l.timestamps.get(d),importance:a.importance,score:l.scores.get(d)??null,mentionCount:a.mention_count}),contentTitle:U(v),type:"core",emotion:G(a.emotion_label),desc:v,connections:[]})}),((r==null?void 0:r.memories)||[]).forEach((a,g)=>{const d=z(a,`dynamic-${g}`),v=String(a.content||"").trim();if(!d||!v||s.has(d))return;const M=q(v);if(M&&c.has(M))return;s.add(d),M&&c.add(M);const N=H(d||v,g,"dynamic");n.push({id:d,...N,title:B({time:a.last_mentioned||a.created_at||l.timestamps.get(d),importance:a.importance,score:l.scores.get(d)??null,mentionCount:a.mention_count}),contentTitle:U(v),type:"dynamic",emotion:G(a.emotion_label),desc:v,connections:Array.from(l.connections.get(d)||[])})}),n}function de(t){const[r,n]=h.useState({width:390,height:720});return h.useEffect(()=>{const s=t.current;if(!s)return;const c=()=>{const u=s.getBoundingClientRect();n({width:Math.max(320,u.width),height:Math.max(520,u.height)})};c();const l=new ResizeObserver(c);return l.observe(s),()=>l.disconnect()},[t]),r}function xe({onBack:t}){const r=te(),n=h.useRef(null),s=de(n),[c,l]=h.useState(null),[u,w]=h.useState(null),[b,a]=h.useState(!1),[g,d]=h.useState(""),[v,M]=h.useState(""),[N,J]=h.useState(""),[O,K]=h.useState(!0),[$,W]=h.useState({x:.18,y:-.16}),E=h.useRef({active:!1,moved:!1,sx:0,sy:0,lx:0,ly:0}),R=h.useRef($),C=h.useRef(null),_=h.useCallback(async()=>{var e,o,m,y;a(!0);try{const[p,x]=await Promise.allSettled([L("/miniapp-api/memory-debug?limit=16&core_limit=48&scope=all"),L("/miniapp-api/dynamic-memory")]),j=[];if(p.status==="fulfilled"&&((e=p.value)!=null&&e.ok))l(p.value);else{const k=p.status==="rejected"?p.reason:(o=p.value)==null?void 0:o.error;j.push(`核心记忆 ${(k==null?void 0:k.message)||k||"加载失败"}`),l(null)}if(x.status==="fulfilled"&&((m=x.value)!=null&&m.ok))w(x.value);else{const k=x.status==="rejected"?x.reason:(y=x.value)==null?void 0:y.error;j.push(`动态记忆 ${(k==null?void 0:k.message)||k||"加载失败"}`),w(null)}if(d(""),j.length===2)throw new Error(j.join("；"));j.length===1&&r(`记忆星云部分加载失败：${j[0]}`)}catch(p){const x=(p==null?void 0:p.message)||String(p);d(x),r(`记忆星云加载失败：${x}`),l(null),w(null)}finally{a(!1)}},[r]);h.useEffect(()=>{_()},[_]),h.useEffect(()=>{R.current=$},[$]),h.useEffect(()=>()=>{C.current!==null&&window.cancelAnimationFrame(C.current)},[]);const S=h.useMemo(()=>ue(c,u),[c,u]),f=S.find(e=>e.id===v)||null,Y=h.useMemo(()=>f?ne(f.desc):[],[f]),T=h.useMemo(()=>{const e=new Map,o=Math.cos($.y),m=Math.sin($.y),y=Math.cos($.x),p=Math.sin($.x);return S.forEach(x=>{const j=x.x*o+x.z*m,k=-x.x*m+x.z*o,ee=x.y*y-k*p,D=x.y*p+k*y,X=760,I=Math.max(.48,Math.min(1.7,X/(X-D)));e.set(x.id,{x:s.width/2+j*I,y:s.height/2+ee*I,z:D,depth:I})}),e},[S,$.x,$.y,s.height,s.width]),Z=h.useMemo(()=>{const e=new Set;return f&&(f.connections.forEach(o=>e.add(o)),S.forEach(o=>{o.connections.includes(f.id)&&e.add(o.id)})),e},[f,S]);function F(e,o){E.current={active:!0,moved:!1,sx:e,sy:o,lx:e,ly:o}}function V(e,o){const m=E.current;if(!m.active)return;const y=e-m.lx,p=o-m.ly;Math.abs(e-m.sx)+Math.abs(o-m.sy)>4&&(m.moved=!0),m.lx=e,m.ly=o,R.current={x:Math.max(-1.15,Math.min(1.15,R.current.x-p*.004)),y:R.current.y+y*.006},C.current===null&&(C.current=window.requestAnimationFrame(()=>{C.current=null,W(R.current)}))}function A(){window.setTimeout(()=>{E.current.active=!1,E.current.moved=!1},0)}function Q(e){E.current.moved||M(e.id)}function P(e){if(e==="atlas"){K(o=>!o);return}J(o=>o===e?"":e)}return i.jsxs("div",{ref:n,className:`memory-nebula-root h-full min-h-full overflow-hidden ${f?"is-focused":""} ${N==="anchor"?"mode-anchor":""} ${N==="mood"?"mode-mood":""} ${O?"":"atlas-off"}`,onMouseDown:e=>F(e.clientX,e.clientY),onMouseMove:e=>V(e.clientX,e.clientY),onMouseUp:A,onMouseLeave:A,onTouchStart:e=>{const o=e.touches[0];o&&F(o.clientX,o.clientY)},onTouchMove:e=>{const o=e.touches[0];o&&V(o.clientX,o.clientY)},onTouchEnd:A,onClick:()=>{E.current.moved||M("")},children:[i.jsx("style",{children:fe}),i.jsx("div",{className:"nebula"}),i.jsx("div",{className:"sky-atlas","aria-hidden":!0,children:i.jsx("svg",{viewBox:"0 0 1000 1000",preserveAspectRatio:"none",children:re.map(e=>i.jsxs("g",{children:[e.lines.map(([o,m])=>{const y=e.stars[o],p=e.stars[m];return i.jsx("line",{className:"sky-atlas-line",x1:y.x,y1:y.y,x2:p.x,y2:p.y},`${o}-${m}`)}),e.stars.map((o,m)=>i.jsxs(oe.Fragment,{children:[i.jsx("circle",{className:`sky-atlas-star ${o.major?"major":""}`,cx:o.x,cy:o.y,r:o.major?2.4:1.25}),o.name?i.jsx("text",{className:"sky-atlas-star-label",x:o.x+9,y:o.y-7,children:o.name}):null]},`${e.name}-${m}`)),i.jsx("text",{className:"sky-atlas-label",x:e.label.x,y:e.label.y,children:e.name})]},e.name))})}),i.jsxs("div",{className:"hud",children:[i.jsxs("div",{className:"hud-top",children:[i.jsx("button",{type:"button",className:"crescent-btn",onClick:e=>{e.stopPropagation(),t?t():_()},"aria-label":"返回日常",children:i.jsx("svg",{className:"crescent-svg",width:"24",height:"24",viewBox:"0 0 24 24",children:i.jsx("path",{d:"M12 3a9 9 0 1 0 9 9 9.011 9.011 0 0 1-9-9Z"})})}),i.jsx("h1",{className:"app-title",children:"MNEMOSYNE"}),i.jsx("div",{className:"memory-count",children:b?"...":S.length?`${S.length} stars`:"NO DATA"})]}),i.jsxs("div",{className:"hud-side",children:[i.jsx("button",{type:"button",className:`filter-btn ${N==="anchor"?"active":""}`,onClick:e=>{e.stopPropagation(),P("anchor")},children:"ANCHOR"}),i.jsx("button",{type:"button",className:`filter-btn ${O?"active":""}`,onClick:e=>{e.stopPropagation(),P("atlas")},children:"ATLAS"}),i.jsx("button",{type:"button",className:`filter-btn ${N==="mood"?"active":""}`,onClick:e=>{e.stopPropagation(),P("mood")},children:"MOOD"})]})]}),i.jsxs("div",{className:"constellation-canvas",children:[S.map(e=>{const o=T.get(e.id);if(!o)return null;const m=(f==null?void 0:f.id)===e.id,y=Z.has(e.id),p=e.type==="core"?1.08:.92,x=m?1.72:y?1.18:1;return i.jsx("button",{type:"button",className:`star star-${e.type} ${m?"active":""} ${y?"related":""}`,"data-emotion":e.emotion,style:{left:o.x,top:o.y,opacity:Math.max(.22,Math.min(1,.42+o.depth*.42)),transform:`translate(-50%, -50%) scale(${p*x*o.depth})`,zIndex:Math.round(50+o.z)},onClick:j=>{j.stopPropagation(),Q(e)},"aria-label":`${e.title} ${e.contentTitle}`,children:i.jsx("span",{className:"star-label",children:e.title})},e.id)}),f?f.connections.map(e=>{const o=T.get(f.id),m=T.get(e);if(!o||!m)return null;const y=m.x-o.x,p=m.y-o.y,x=Math.sqrt(y*y+p*p),j=Math.atan2(p,y)*180/Math.PI;return i.jsx("div",{className:"constellation-line active",style:{left:o.x,top:o.y,width:x,transform:`rotate(${j}deg)`}},`${f.id}-${e}`)}):null]}),S.length?null:i.jsxs("div",{className:"memory-empty-state",onClick:e=>e.stopPropagation(),children:[i.jsx("p",{className:"memory-empty-kicker",children:"NO SAMPLE MEMORY"}),i.jsx("h2",{children:b?"正在读取真实记忆":g?"没有拿到真实记忆":"还没有可显示的记忆"}),i.jsx("p",{children:b?"星云只会从网关返回的记忆内容生成。":g?"接口没有返回可用数据，所以这里不再展示样例卡片。":"等核心记忆或动态召回出现后，这里会生成真实星点。"}),i.jsx("button",{type:"button",onClick:e=>{e.stopPropagation(),_()},children:"重新读取"})]}),f?i.jsxs("div",{className:"memory-verse-layer","aria-live":"polite",children:[i.jsxs("div",{className:"memory-observation memory-observation-left",children:["MEMORY ",f.type.toUpperCase()," // ",f.title]}),i.jsxs("div",{className:"memory-observation memory-observation-right",children:["EMOTION: ",f.emotion.toUpperCase()," // INDEX: ",f.id.slice(0,8)]}),i.jsx("div",{className:"memory-verse","aria-label":f.desc,children:Y.map((e,o)=>i.jsx("div",{className:`memory-phrase ${ae(e,o,Y.length)}`,children:e},`${f.id}-${o}`))})]}):null]})}const fe=`
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
  top: 13px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  color: rgba(232, 236, 255, 0.62);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 8px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  text-shadow: 0 0 14px rgba(4, 5, 26, 0.9);
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
.mode-anchor .star-core .star-label { opacity: 0.92; transform: translateX(-50%) translateY(2px); }
.mode-mood .star-core { opacity: 0.38 !important; filter: grayscale(0.7); }
.mode-mood .star-dynamic { width: 6px; height: 6px; }
.mode-mood .star-dynamic[data-emotion="positive"] { background: #f2e3b6; box-shadow: 0 0 14px rgba(242, 227, 182, 0.72), 0 0 28px rgba(242, 227, 182, 0.28); }
.mode-mood .star-dynamic[data-emotion="negative"] { background: #c5a3ff; box-shadow: 0 0 14px rgba(197, 163, 255, 0.72), 0 0 28px rgba(98, 76, 170, 0.34); }
.mode-mood .star-dynamic[data-emotion="neutral"] { background: #dfe7ff; box-shadow: 0 0 12px rgba(223, 231, 255, 0.56); }
.star.active { filter: none; }
.star.active .star-label,
.star.related .star-label { opacity: 0.82; transform: translateX(-50%) translateY(2px); }
.memory-verse-layer {
  position: absolute;
  inset: 0;
  z-index: 32;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 88px 48px 92px;
  pointer-events: none;
}
.memory-verse {
  width: min(560px, calc(100vw - 96px));
  transform: translateY(-2vh);
  text-align: center;
  animation: memoryVerseIn 0.48s cubic-bezier(0.16, 1, 0.3, 1);
}
.memory-phrase {
  margin: 8px 0;
  color: rgba(238, 244, 255, 0.78);
  font-family: "Inter", "PingFang SC", "Microsoft YaHei UI", sans-serif;
  letter-spacing: 0;
  line-height: 1.25;
  text-shadow: 0 0 18px rgba(126, 183, 255, 0.28), 0 0 34px rgba(41, 96, 176, 0.24);
}
.memory-phrase-title {
  color: #9fdcff;
  font-size: clamp(28px, 8.5vw, 52px);
  font-weight: 800;
  line-height: 1.05;
  text-shadow: 0 0 16px rgba(95, 190, 255, 0.68), 0 0 42px rgba(38, 104, 190, 0.48);
}
.memory-phrase-loud {
  color: rgba(245, 249, 255, 0.96);
  font-size: clamp(22px, 6vw, 34px);
  font-weight: 800;
  text-shadow: 0 0 16px rgba(196, 224, 255, 0.72), 0 0 40px rgba(73, 129, 216, 0.4);
}
.memory-phrase-mid {
  color: rgba(226, 234, 250, 0.78);
  font-size: clamp(16px, 4.3vw, 23px);
  font-weight: 650;
}
.memory-phrase-soft {
  color: rgba(209, 217, 236, 0.54);
  font-size: clamp(13px, 3.4vw, 18px);
  font-weight: 500;
  font-style: italic;
}
.memory-observation {
  position: absolute;
  max-height: min(72vh, 520px);
  overflow: hidden;
  color: rgba(168, 178, 210, 0.58);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 9px;
  letter-spacing: 0.18em;
  line-height: 1.6;
  text-transform: uppercase;
  text-shadow: 0 0 18px rgba(4, 5, 26, 0.95);
  white-space: nowrap;
  writing-mode: vertical-rl;
}
.memory-observation-left {
  left: 20px;
  bottom: calc(env(safe-area-inset-bottom, 0px) + 24px);
  transform: rotate(180deg);
}
.memory-observation-right {
  right: 18px;
  top: calc(env(safe-area-inset-top, 0px) + 24px);
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
@media (max-width: 460px) {
  .memory-verse-layer { padding-left: 34px; padding-right: 34px; }
  .memory-verse { width: min(330px, calc(100vw - 84px)); }
  .memory-observation {
    font-size: 8px;
    letter-spacing: 0.14em;
    opacity: 0.72;
  }
  .memory-observation-left { left: 10px; }
  .memory-observation-right { right: 9px; }
}
@keyframes memoryVerseIn {
  0% { opacity: 0; transform: translateY(1vh) scale(0.98); filter: blur(6px); }
  100% { opacity: 1; transform: translateY(-2vh) scale(1); filter: blur(0); }
}
@keyframes nebulaPulse {
  0%, 100% { opacity: 0.4; transform: translate(-50%, -50%) scale(1); }
  50% { opacity: 0.8; transform: translate(-50%, -50%) scale(1.3); }
}
`;export{xe as MemoryNebulaTab};
