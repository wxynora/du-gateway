import{u as ae,r as h,b as G,j as i,R as oe}from"./index-CRdOMXsE.js";const se=[{name:"URSA MAJOR",label:{x:118,y:136},stars:[{x:74,y:174,major:!0},{x:130,y:204},{x:195,y:216},{x:244,y:184},{x:304,y:174},{x:356,y:144,major:!0},{x:414,y:120}],lines:[[0,1],[1,2],[2,3],[3,0],[3,4],[4,5],[5,6]]},{name:"LYRA",label:{x:792,y:142},stars:[{x:824,y:108,major:!0,name:"Vega"},{x:780,y:166},{x:846,y:178},{x:803,y:230}],lines:[[0,1],[0,2],[1,2],[1,3],[2,3]]},{name:"ORION",label:{x:662,y:654},stars:[{x:624,y:562,major:!0,name:"Betelgeuse"},{x:746,y:552},{x:660,y:654},{x:704,y:664},{x:748,y:676},{x:602,y:778},{x:804,y:776,major:!0,name:"Rigel"}],lines:[[0,2],[1,4],[2,3],[3,4],[2,5],[4,6],[5,6]]},{name:"CASSIOPEIA",label:{x:168,y:720},stars:[{x:96,y:682},{x:160,y:632,major:!0},{x:230,y:686},{x:300,y:640},{x:364,y:704}],lines:[[0,1],[1,2],[2,3],[3,4]]}];function ne(t){let r=2166136261;for(let o=0;o<t.length;o+=1)r^=t.charCodeAt(o),r=Math.imul(r,16777619);return r>>>0}function K(t){const r=String(t||"").replace(/\s+/g," ").trim();return r?r.length>18?`${r.slice(0,18)}...`:r:"Memory"}function ie(t){const r=String(t||"").replace(/\s+/g," ").trim();if(!r)return["Memory"];const o=(r.match(/[^，。！？；：\n]+[，。！？；：]?/g)||[r]).map(s=>s.trim()).filter(Boolean);return o.length<=5?o.length?o:[r]:[...o.slice(0,4),o.slice(4).join("")]}function ce(t,r,o){return r===0&&t.length<=8?"memory-phrase-title":r===Math.floor(o/2)||o<=2&&r===0?"memory-phrase-loud":r===o-1?"memory-phrase-soft":"memory-phrase-mid"}function le(t){const r=Number(t);return Number.isFinite(r)?r:null}function me(t){const r=String(t||"").trim();if(!r)return"T--";const o=new Date(r);if(!Number.isFinite(o.getTime()))return"T--";const s=String(o.getMonth()+1).padStart(2,"0"),c=String(o.getDate()).padStart(2,"0");return`T${s}.${c}`}function pe(t,r){if(t!==null)return t<=1?`S${t.toFixed(2)}`:`S${Math.round(t)}`;const o=Math.max(0,Math.min(99,Math.round(Number(r)||0)));return`S${String(o).padStart(2,"0")}`}function q({time:t,importance:r,score:o,mentionCount:s}){const c=Math.max(0,Math.min(9,Math.round(Number(r)||0)));return`${me(t)} / W${c} / ${pe(o??null,s)}`}function ue(t,r){const o=r==="core"?4:2,s=Number.isFinite(Number(t))?Number(t):o,c=Math.max(0,Math.min(4,s));return c<=0?.22:c<=1?.3:c<=2?.48:c<=3?.72:1}function W(t){const r=Number(t);return Number.isFinite(r)?r:0}function B(t){return String(t||"").replace(/\s+/g,"").trim()}function H(t){return t==="positive"||t==="negative"?t:"neutral"}function z(t,r){return String((t==null?void 0:t.memory_id)||(t==null?void 0:t.id)||r).trim()}function Z(t,r,o){const s=ne(t);if(o==="core"){const v=s%6283/1e3+r*.42,m=34+Math.sqrt(r+1)*9+(s>>>7)%34;return{x:Math.cos(v)*m+((s>>>17)%34-17),y:Math.sin(v)*m*.74+((s>>>22)%46-23),z:86+(s>>>12)%210-105}}const c=s%6283/1e3+r*.55,l=170+(s>>>7)%260,f=-230+(s>>>14)%470,w=-220+(s>>>22)%450;return{x:Math.cos(c)*l+((s>>>5)%88-44),y:f*.72+Math.sin(c*1.7)*72,z:w}}function fe(t,r){const o=[];return(t.recalled_items||[]).forEach((s,c)=>{const l=z(s,`item-${r}-${c}`);l&&o.push(l)}),(t.referenced_memories||[]).forEach((s,c)=>{const l=z(s,`ref-${r}-${c}`);l&&o.push(l)}),(t.recalled_lines||[]).forEach((s,c)=>{if(typeof s=="string")return;const l=z(s,`line-${r}-${c}`);l&&o.push(l)}),Array.from(new Set(o))}function de(t){const r=new Map,o=new Map,s=new Map,c=[...(t==null?void 0:t.recalls)||[],...(t==null?void 0:t.search_memory_events)||[],...(t==null?void 0:t.citation_events)||[]],l=(f,w,v)=>{if(!f)return;const m=le(w);m!==null&&m>(o.get(f)??-1/0)&&o.set(f,m),v&&!s.has(f)&&s.set(f,v)};return c.forEach((f,w)=>{const v=fe(f,w).slice(0,8);v.forEach((m,n)=>{const M=r.get(m)||new Set;v.forEach((x,b)=>{x!==m&&Math.abs(b-n)<=2&&M.add(x)}),r.set(m,M),l(m,void 0,f.timestamp)}),(f.recalled_lines||[]).forEach((m,n)=>{typeof m!="string"&&l(z(m,`line-${w}-${n}`),m.final_score,f.timestamp)}),(f.recalled_items||[]).forEach((m,n)=>{l(z(m,`item-${w}-${n}`),m.final_score,f.timestamp)}),(f.referenced_memories||[]).forEach((m,n)=>{l(z(m,`ref-${w}-${n}`),m.final_score,f.timestamp)})}),{connections:r,scores:o,timestamps:s}}function he(t,r){var m;const o=[],s=new Set,c=new Set,l=de(t);(((m=t==null?void 0:t.core_cache)==null?void 0:m.items)||[]).forEach((n,M)=>{const x=z(n,`core-${M}`),b=String(n.content||"").trim();if(!x||!b||s.has(x))return;const k=B(b);s.add(x),k&&c.add(k);const C=Z(x,M,"core");o.push({id:x,...C,title:q({time:n.promoted_at||l.timestamps.get(x),importance:n.importance,score:l.scores.get(x)??null,mentionCount:n.mention_count}),contentTitle:K(b),type:"core",importance:n.importance,emotion:H(n.emotion_label),desc:b,connections:[]})}),((r==null?void 0:r.memories)||[]).forEach((n,M)=>{const x=z(n,`dynamic-${M}`),b=String(n.content||"").trim();if(!x||!b||s.has(x))return;const k=B(b);if(k&&c.has(k))return;s.add(x),k&&c.add(k);const C=Z(x||b,M,"dynamic");o.push({id:x,...C,title:q({time:n.last_mentioned||n.created_at||l.timestamps.get(x),importance:n.importance,score:l.scores.get(x)??null,mentionCount:n.mention_count}),contentTitle:K(b),type:"dynamic",importance:n.importance,emotion:H(n.emotion_label),desc:b,connections:Array.from(l.connections.get(x)||[])})});const v=new Set(o.filter(n=>n.type==="core").slice().sort((n,M)=>W(M.importance)-W(n.importance)).slice(0,20).map(n=>n.id));return o.map(n=>n.type==="core"&&v.has(n.id)?{...n,coreGlow:!0}:n)}function xe(t){const[r,o]=h.useState({width:390,height:720});return h.useEffect(()=>{const s=t.current;if(!s)return;const c=()=>{const f=s.getBoundingClientRect();o({width:Math.max(320,f.width),height:Math.max(520,f.height)})};c();const l=new ResizeObserver(c);return l.observe(s),()=>l.disconnect()},[t]),r}function be({onBack:t}){const r=ae(),o=h.useRef(null),s=xe(o),[c,l]=h.useState(null),[f,w]=h.useState(null),[v,m]=h.useState(!1),[n,M]=h.useState(""),[x,b]=h.useState(""),[k,C]=h.useState(""),[X,Q]=h.useState(!0),[N,ee]=h.useState({x:.18,y:-.16}),E=h.useRef({active:!1,moved:!1,sx:0,sy:0,lx:0,ly:0}),R=h.useRef(N),T=h.useRef(null),Y=h.useCallback(async()=>{var e,a,p,y;m(!0);try{const[u,g]=await Promise.allSettled([G("/miniapp-api/memory-debug?limit=16&core_limit=240&scope=all"),G("/miniapp-api/dynamic-memory")]),S=[];if(u.status==="fulfilled"&&((e=u.value)!=null&&e.ok))l(u.value);else{const j=u.status==="rejected"?u.reason:(a=u.value)==null?void 0:a.error;S.push(`核心记忆 ${(j==null?void 0:j.message)||j||"加载失败"}`),l(null)}if(g.status==="fulfilled"&&((p=g.value)!=null&&p.ok))w(g.value);else{const j=g.status==="rejected"?g.reason:(y=g.value)==null?void 0:y.error;S.push(`动态记忆 ${(j==null?void 0:j.message)||j||"加载失败"}`),w(null)}if(M(""),S.length===2)throw new Error(S.join("；"));S.length===1&&r(`记忆星云部分加载失败：${S[0]}`)}catch(u){const g=(u==null?void 0:u.message)||String(u);M(g),r(`记忆星云加载失败：${g}`),l(null),w(null)}finally{m(!1)}},[r]);h.useEffect(()=>{Y()},[Y]),h.useEffect(()=>{R.current=N},[N]),h.useEffect(()=>()=>{T.current!==null&&window.cancelAnimationFrame(T.current)},[]);const $=h.useMemo(()=>he(c,f),[c,f]),d=$.find(e=>e.id===x)||null,L=h.useMemo(()=>d?ie(d.desc):[],[d]),_=h.useMemo(()=>{const e=new Map,a=Math.cos(N.y),p=Math.sin(N.y),y=Math.cos(N.x),u=Math.sin(N.x);return $.forEach(g=>{const S=g.x*a+g.z*p,j=-g.x*p+g.z*a,A=g.y*y-j*u,I=g.y*u+j*y,P=760,O=Math.max(.48,Math.min(1.7,P/(P-I)));e.set(g.id,{x:s.width/2+S*O,y:s.height/2+A*O,z:I,depth:O})}),e},[$,N.x,N.y,s.height,s.width]),F=h.useMemo(()=>{const e=new Set;return d&&(d.connections.forEach(a=>e.add(a)),$.forEach(a=>{a.connections.includes(d.id)&&e.add(a.id)})),e},[d,$]),te=h.useMemo(()=>d?Array.from(F).filter(e=>_.has(e)):[],[d,_,F]);function J(e,a){E.current={active:!0,moved:!1,sx:e,sy:a,lx:e,ly:a}}function U(e,a){const p=E.current;if(!p.active)return;const y=e-p.lx,u=a-p.ly;Math.abs(e-p.sx)+Math.abs(a-p.sy)>4&&(p.moved=!0),p.lx=e,p.ly=a,R.current={x:Math.max(-1.15,Math.min(1.15,R.current.x-u*.004)),y:R.current.y+y*.006},T.current===null&&(T.current=window.requestAnimationFrame(()=>{T.current=null,ee(R.current)}))}function V(){window.setTimeout(()=>{E.current.active=!1,E.current.moved=!1},0)}function re(e){E.current.moved||b(e.id)}function D(e){if(e==="atlas"){Q(a=>!a);return}C(a=>a===e?"":e)}return i.jsxs("div",{ref:o,className:`memory-nebula-root h-full min-h-full overflow-hidden ${d?"is-focused":""} ${k==="anchor"?"mode-anchor":""} ${k==="mood"?"mode-mood":""} ${X?"":"atlas-off"}`,onMouseDown:e=>J(e.clientX,e.clientY),onMouseMove:e=>U(e.clientX,e.clientY),onMouseUp:V,onMouseLeave:V,onTouchStart:e=>{const a=e.touches[0];a&&J(a.clientX,a.clientY)},onTouchMove:e=>{const a=e.touches[0];a&&U(a.clientX,a.clientY)},onTouchEnd:V,onClick:()=>{E.current.moved||b("")},children:[i.jsx("style",{children:ge}),i.jsx("div",{className:"nebula"}),i.jsx("div",{className:"sky-atlas","aria-hidden":!0,children:i.jsx("svg",{viewBox:"0 0 1000 1000",preserveAspectRatio:"none",children:se.map(e=>i.jsxs("g",{children:[e.lines.map(([a,p])=>{const y=e.stars[a],u=e.stars[p];return i.jsx("line",{className:"sky-atlas-line",x1:y.x,y1:y.y,x2:u.x,y2:u.y},`${a}-${p}`)}),e.stars.map((a,p)=>i.jsxs(oe.Fragment,{children:[i.jsx("circle",{className:`sky-atlas-star ${a.major?"major":""}`,cx:a.x,cy:a.y,r:a.major?2.4:1.25}),a.name?i.jsx("text",{className:"sky-atlas-star-label",x:a.x+9,y:a.y-7,children:a.name}):null]},`${e.name}-${p}`)),i.jsx("text",{className:"sky-atlas-label",x:e.label.x,y:e.label.y,children:e.name})]},e.name))})}),i.jsxs("div",{className:"hud",children:[i.jsxs("div",{className:"hud-top",children:[i.jsx("button",{type:"button",className:"crescent-btn",onClick:e=>{e.stopPropagation(),t==null||t()},"aria-label":"返回日常",children:i.jsx("svg",{className:"crescent-svg",width:"24",height:"24",viewBox:"0 0 24 24",children:i.jsx("path",{d:"M12 3a9 9 0 1 0 9 9 9.011 9.011 0 0 1-9-9Z"})})}),i.jsx("h1",{className:"app-title",children:"MNEMOSYNE"}),i.jsx("div",{className:"memory-count",children:v?"...":$.length?`${$.length} stars`:"NO DATA"})]}),i.jsxs("div",{className:"hud-side",children:[i.jsx("button",{type:"button",className:`filter-btn ${k==="anchor"?"active":""}`,onClick:e=>{e.stopPropagation(),D("anchor")},children:"ANCHOR"}),i.jsx("button",{type:"button",className:`filter-btn ${X?"active":""}`,onClick:e=>{e.stopPropagation(),D("atlas")},children:"ATLAS"}),i.jsx("button",{type:"button",className:`filter-btn ${k==="mood"?"active":""}`,onClick:e=>{e.stopPropagation(),D("mood")},children:"MOOD"})]})]}),i.jsxs("div",{className:"constellation-canvas",children:[$.map(e=>{const a=_.get(e.id);if(!a)return null;const p=(d==null?void 0:d.id)===e.id,y=F.has(e.id),S=(e.type==="core"?.7:.74)*(p?1.84:y?1.12:1)*a.depth,A=Math.max(.22,Math.min(1,.42+a.depth*.42))*ue(e.importance,e.type),I=p?Math.max(A,.86):y?Math.max(A,.58):A,P={left:a.x,top:a.y,opacity:I,transform:`translate(-50%, -50%) scale(${S})`,zIndex:Math.round(50+a.z),"--label-scale":String(1/Math.max(.72,S))};return i.jsx("button",{type:"button",className:`star star-${e.type} ${e.coreGlow?"core-glow":""} ${p?"active":""} ${y?"related":""}`,"data-emotion":e.emotion,style:P,onClick:O=>{O.stopPropagation(),re(e)},"aria-label":`${e.title} ${e.contentTitle}`,children:i.jsx("span",{className:"star-label",children:e.title})},e.id)}),d?te.map(e=>{const a=_.get(d.id),p=_.get(e);if(!a||!p)return null;const y=p.x-a.x,u=p.y-a.y,g=Math.sqrt(y*y+u*u),S=Math.atan2(u,y)*180/Math.PI;return i.jsx("div",{className:"constellation-line active",style:{left:a.x,top:a.y,width:g,transform:`rotate(${S}deg)`}},`${d.id}-${e}`)}):null]}),$.length?null:i.jsxs("div",{className:"memory-empty-state",onClick:e=>e.stopPropagation(),children:[i.jsx("p",{className:"memory-empty-kicker",children:"NO SAMPLE MEMORY"}),i.jsx("h2",{children:v?"正在读取真实记忆":n?"没有拿到真实记忆":"还没有可显示的记忆"}),i.jsx("p",{children:v?"星云只会从网关返回的记忆内容生成。":n?"接口没有返回可用数据，所以这里不再展示样例卡片。":"等核心记忆或动态召回出现后，这里会生成真实星点。"}),i.jsx("button",{type:"button",onClick:e=>{e.stopPropagation(),Y()},children:"重新读取"})]}),d?i.jsxs("div",{className:"memory-verse-layer","aria-live":"polite",children:[i.jsxs("div",{className:"memory-observation memory-observation-left",children:["MEMORY ",d.type.toUpperCase()," // ",d.title]}),i.jsxs("div",{className:"memory-observation memory-observation-right",children:["EMOTION: ",d.emotion.toUpperCase()," // INDEX: ",d.id.slice(0,8)]}),i.jsx("div",{className:"memory-verse","aria-label":d.desc,children:L.map((e,a)=>i.jsx("div",{className:`memory-phrase ${ce(e,a,L.length)}`,children:e},`${d.id}-${a}`))})]}):null]})}const ge=`
.memory-nebula-root {
  position: fixed;
  inset: 0;
  z-index: 80;
  width: 100%;
  height: 100dvh;
  min-height: 100dvh;
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
.hud { position: absolute; inset: 0; z-index: 42; pointer-events: none; }
.hud-top {
  position: absolute;
  top: calc(18px + env(safe-area-inset-top, 0px));
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
.constellation-canvas { position: absolute; inset: 0; z-index: 24; }
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
  background: radial-gradient(circle, rgba(242, 227, 182, 0.82) 0%, rgba(142, 186, 255, 0.26) 42%, transparent 72%);
  filter: blur(4px);
  opacity: 0;
  transition: opacity 0.28s ease, transform 0.28s ease;
}
.star.active::before,
.star.related::before {
  animation: nebulaPulse 4s infinite ease-in-out;
}
.star-core {
  width: 4.6px;
  height: 4.6px;
  background: #f2e3b6;
  box-shadow: 0 0 3px rgba(242, 227, 182, 0.32);
}
.star-dynamic {
  width: 2.8px;
  height: 2.8px;
  background: #fff;
  box-shadow: 0 0 2px rgba(255, 255, 255, 0.32);
}
.star-dynamic::before {
  background: radial-gradient(circle, rgba(223, 231, 255, 0.66) 0%, rgba(126, 183, 255, 0.18) 44%, transparent 74%);
}
.star-label {
  position: absolute;
  top: 10px;
  left: 50%;
  transform: translateX(-50%) scale(var(--label-scale, 1));
  transform-origin: top center;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  color: rgba(213, 221, 248, 0.42);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 5.5px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  text-shadow: 0 0 14px rgba(4, 5, 26, 0.9);
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.constellation-line {
  position: absolute;
  z-index: 18;
  height: 1px;
  transform-origin: 0 50%;
  pointer-events: none;
  background: linear-gradient(90deg, transparent, rgba(157, 211, 255, 0.8), rgba(242, 227, 182, 0.68), transparent);
  opacity: 0.86;
  filter: drop-shadow(0 0 8px rgba(126, 183, 255, 0.5)) drop-shadow(0 0 18px rgba(242, 227, 182, 0.22));
}
.is-focused .star:not(.active):not(.related) { opacity: 0.15 !important; filter: grayscale(1); }
.mode-anchor .sky-atlas { opacity: 0.18; }
.mode-anchor .star-dynamic { opacity: 0.12 !important; filter: grayscale(1); }
.mode-anchor .star-core { filter: brightness(1.06); }
.mode-anchor .star-core .star-label { opacity: 0.58; transform: translateX(-50%) translateY(1px) scale(var(--label-scale, 1)); }
.mode-mood .star-core { opacity: 0.38 !important; filter: grayscale(0.7); }
.mode-mood .star-dynamic { width: 6px; height: 6px; }
.mode-mood .star-dynamic[data-emotion="positive"] { background: #f2e3b6; box-shadow: 0 0 14px rgba(242, 227, 182, 0.72), 0 0 28px rgba(242, 227, 182, 0.28); }
.mode-mood .star-dynamic[data-emotion="negative"] { background: #c5a3ff; box-shadow: 0 0 14px rgba(197, 163, 255, 0.72), 0 0 28px rgba(98, 76, 170, 0.34); }
.mode-mood .star-dynamic[data-emotion="neutral"] { background: #dfe7ff; box-shadow: 0 0 12px rgba(223, 231, 255, 0.56); }
.star.related::before { opacity: 0.22; }
.star.active::before { opacity: 0.74; }
.star-core.core-glow {
  box-shadow: 0 0 5px rgba(242, 227, 182, 0.54), 0 0 14px rgba(242, 227, 182, 0.2);
}
.star-core.core-glow::before {
  opacity: 0.2;
}
.star.related { filter: brightness(1.08) drop-shadow(0 0 7px rgba(157, 211, 255, 0.22)); }
.star.active { filter: brightness(1.24) drop-shadow(0 0 16px rgba(157, 211, 255, 0.48)) drop-shadow(0 0 28px rgba(242, 227, 182, 0.2)); }
.star.active .star-label,
.star.related .star-label { opacity: 0.58; transform: translateX(-50%) translateY(1px) scale(var(--label-scale, 1)); }
.memory-verse-layer {
  position: absolute;
  inset: 0;
  z-index: 30;
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
  margin: 5px 0;
  color: rgba(238, 244, 255, 0.78);
  font-family: "Songti SC", "STSong", "SimSun", "Noto Serif CJK SC", serif;
  letter-spacing: 0;
  line-height: 1.34;
  text-shadow: 0 0 18px rgba(126, 183, 255, 0.28), 0 0 34px rgba(41, 96, 176, 0.24);
}
.memory-phrase-title {
  color: #9fdcff;
  font-family: "Songti SC", "STSong", "SimSun", "Noto Serif CJK SC", serif;
  font-size: clamp(22px, 6.2vw, 36px);
  font-weight: 900;
  line-height: 1.05;
  text-shadow: 0 0 16px rgba(95, 190, 255, 0.68), 0 0 42px rgba(38, 104, 190, 0.48);
}
.memory-phrase-loud {
  color: rgba(245, 249, 255, 0.96);
  font-family: "Songti SC", "STSong", "SimSun", "Noto Serif CJK SC", serif;
  font-size: clamp(17px, 4.8vw, 27px);
  font-weight: 800;
  text-shadow: 0 0 16px rgba(196, 224, 255, 0.72), 0 0 40px rgba(73, 129, 216, 0.4);
}
.memory-phrase-mid {
  color: rgba(226, 234, 250, 0.78);
  font-size: clamp(13px, 3.6vw, 19px);
  font-weight: 500;
}
.memory-phrase-soft {
  color: rgba(209, 217, 236, 0.54);
  font-size: clamp(11px, 3vw, 15px);
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
`;export{be as MemoryNebulaTab};
