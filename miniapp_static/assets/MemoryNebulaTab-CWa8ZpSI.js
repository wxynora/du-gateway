import{u as re,r as f,b as U,j as i,R as ae}from"./index-CmoADDf6.js";const oe=[{name:"URSA MAJOR",label:{x:118,y:136},stars:[{x:74,y:174,major:!0},{x:130,y:204},{x:195,y:216},{x:244,y:184},{x:304,y:174},{x:356,y:144,major:!0},{x:414,y:120}],lines:[[0,1],[1,2],[2,3],[3,0],[3,4],[4,5],[5,6]]},{name:"LYRA",label:{x:792,y:142},stars:[{x:824,y:108,major:!0,name:"Vega"},{x:780,y:166},{x:846,y:178},{x:803,y:230}],lines:[[0,1],[0,2],[1,2],[1,3],[2,3]]},{name:"ORION",label:{x:662,y:654},stars:[{x:624,y:562,major:!0,name:"Betelgeuse"},{x:746,y:552},{x:660,y:654},{x:704,y:664},{x:748,y:676},{x:602,y:778},{x:804,y:776,major:!0,name:"Rigel"}],lines:[[0,2],[1,4],[2,3],[3,4],[2,5],[4,6],[5,6]]},{name:"CASSIOPEIA",label:{x:168,y:720},stars:[{x:96,y:682},{x:160,y:632,major:!0},{x:230,y:686},{x:300,y:640},{x:364,y:704}],lines:[[0,1],[1,2],[2,3],[3,4]]}];function se(t){let a=2166136261;for(let o=0;o<t.length;o+=1)a^=t.charCodeAt(o),a=Math.imul(a,16777619);return a>>>0}function K(t){const a=String(t||"").replace(/\s+/g," ").trim();return a?a.length>18?`${a.slice(0,18)}...`:a:"Memory"}function ne(t){const a=String(t||"").replace(/\s+/g," ").trim();if(!a)return["Memory"];const o=(a.match(/[^，。！？；：\n]+[，。！？；：]?/g)||[a]).map(s=>s.trim()).filter(Boolean);return o.length<=5?o.length?o:[a]:[...o.slice(0,4),o.slice(4).join("")]}function ie(t,a,o){return a===0&&t.length<=8?"memory-phrase-title":a===Math.floor(o/2)||o<=2&&a===0?"memory-phrase-loud":a===o-1?"memory-phrase-soft":"memory-phrase-mid"}function ce(t){const a=Number(t);return Number.isFinite(a)?a:null}function le(t){const a=String(t||"").trim();if(!a)return"T--";const o=new Date(a);if(!Number.isFinite(o.getTime()))return"T--";const s=String(o.getMonth()+1).padStart(2,"0"),m=String(o.getDate()).padStart(2,"0");return`T${s}.${m}`}function me(t,a){if(t!==null)return t<=1?`S${t.toFixed(2)}`:`S${Math.round(t)}`;const o=Math.max(0,Math.min(99,Math.round(Number(a)||0)));return`S${String(o).padStart(2,"0")}`}function q({time:t,importance:a,score:o,mentionCount:s}){const m=Math.max(0,Math.min(9,Math.round(Number(a)||0)));return`${le(t)} / W${m} / ${me(o??null,s)}`}function B(t){return String(t||"").replace(/\s+/g,"").trim()}function G(t){return t==="positive"||t==="negative"?t:"neutral"}function z(t,a){return String((t==null?void 0:t.memory_id)||(t==null?void 0:t.id)||a).trim()}function H(t,a,o){const s=se(t);if(o==="core"){const b=s%6283/1e3+a*.42,n=34+Math.sqrt(a+1)*9+(s>>>7)%34;return{x:Math.cos(b)*n+((s>>>17)%34-17),y:Math.sin(b)*n*.74+((s>>>22)%46-23),z:86+(s>>>12)%210-105}}const m=s%6283/1e3+a*.55,c=170+(s>>>7)%260,d=-230+(s>>>14)%470,M=-220+(s>>>22)%450;return{x:Math.cos(m)*c+((s>>>5)%88-44),y:d*.72+Math.sin(m*1.7)*72,z:M}}function pe(t,a){const o=[];return(t.recalled_items||[]).forEach((s,m)=>{const c=z(s,`item-${a}-${m}`);c&&o.push(c)}),(t.referenced_memories||[]).forEach((s,m)=>{const c=z(s,`ref-${a}-${m}`);c&&o.push(c)}),(t.recalled_lines||[]).forEach((s,m)=>{if(typeof s=="string")return;const c=z(s,`line-${a}-${m}`);c&&o.push(c)}),Array.from(new Set(o))}function de(t){const a=new Map,o=new Map,s=new Map,m=[...(t==null?void 0:t.recalls)||[],...(t==null?void 0:t.search_memory_events)||[],...(t==null?void 0:t.citation_events)||[]],c=(d,M,b)=>{if(!d)return;const n=ce(M);n!==null&&n>(o.get(d)??-1/0)&&o.set(d,n),b&&!s.has(d)&&s.set(d,b)};return m.forEach((d,M)=>{const b=pe(d,M).slice(0,8);b.forEach((n,y)=>{const h=a.get(n)||new Set;b.forEach((v,j)=>{v!==n&&Math.abs(j-y)<=2&&h.add(v)}),a.set(n,h),c(n,void 0,d.timestamp)}),(d.recalled_lines||[]).forEach((n,y)=>{typeof n!="string"&&c(z(n,`line-${M}-${y}`),n.final_score,d.timestamp)}),(d.recalled_items||[]).forEach((n,y)=>{c(z(n,`item-${M}-${y}`),n.final_score,d.timestamp)}),(d.referenced_memories||[]).forEach((n,y)=>{c(z(n,`ref-${M}-${y}`),n.final_score,d.timestamp)})}),{connections:a,scores:o,timestamps:s}}function ue(t,a){var b;const o=[],s=new Set,m=new Set,c=de(t);return(((b=t==null?void 0:t.core_cache)==null?void 0:b.items)||[]).forEach((n,y)=>{const h=z(n,`core-${y}`),v=String(n.content||"").trim();if(!h||!v||s.has(h))return;const j=B(v);s.add(h),j&&m.add(j);const N=H(h,y,"core");o.push({id:h,...N,title:q({time:n.promoted_at||c.timestamps.get(h),importance:n.importance,score:c.scores.get(h)??null,mentionCount:n.mention_count}),contentTitle:K(v),type:"core",emotion:G(n.emotion_label),desc:v,connections:[]})}),((a==null?void 0:a.memories)||[]).forEach((n,y)=>{const h=z(n,`dynamic-${y}`),v=String(n.content||"").trim();if(!h||!v||s.has(h))return;const j=B(v);if(j&&m.has(j))return;s.add(h),j&&m.add(j);const N=H(h||v,y,"dynamic");o.push({id:h,...N,title:q({time:n.last_mentioned||n.created_at||c.timestamps.get(h),importance:n.importance,score:c.scores.get(h)??null,mentionCount:n.mention_count}),contentTitle:K(v),type:"dynamic",emotion:G(n.emotion_label),desc:v,connections:Array.from(c.connections.get(h)||[])})}),o}function fe(t){const[a,o]=f.useState({width:390,height:720});return f.useEffect(()=>{const s=t.current;if(!s)return;const m=()=>{const d=s.getBoundingClientRect();o({width:Math.max(320,d.width),height:Math.max(520,d.height)})};m();const c=new ResizeObserver(m);return c.observe(s),()=>c.disconnect()},[t]),a}function ge({onBack:t}){const a=re(),o=f.useRef(null),s=fe(o),[m,c]=f.useState(null),[d,M]=f.useState(null),[b,n]=f.useState(!1),[y,h]=f.useState(""),[v,j]=f.useState(""),[N,W]=f.useState(""),[F,Z]=f.useState(!0),[k,Q]=f.useState({x:.18,y:-.16}),E=f.useRef({active:!1,moved:!1,sx:0,sy:0,lx:0,ly:0}),C=f.useRef(k),R=f.useRef(null),_=f.useCallback(async()=>{var e,r,l,g;n(!0);try{const[p,x]=await Promise.allSettled([U("/miniapp-api/memory-debug?limit=16&core_limit=240&scope=all"),U("/miniapp-api/dynamic-memory")]),S=[];if(p.status==="fulfilled"&&((e=p.value)!=null&&e.ok))c(p.value);else{const w=p.status==="rejected"?p.reason:(r=p.value)==null?void 0:r.error;S.push(`核心记忆 ${(w==null?void 0:w.message)||w||"加载失败"}`),c(null)}if(x.status==="fulfilled"&&((l=x.value)!=null&&l.ok))M(x.value);else{const w=x.status==="rejected"?x.reason:(g=x.value)==null?void 0:g.error;S.push(`动态记忆 ${(w==null?void 0:w.message)||w||"加载失败"}`),M(null)}if(h(""),S.length===2)throw new Error(S.join("；"));S.length===1&&a(`记忆星云部分加载失败：${S[0]}`)}catch(p){const x=(p==null?void 0:p.message)||String(p);h(x),a(`记忆星云加载失败：${x}`),c(null),M(null)}finally{n(!1)}},[a]);f.useEffect(()=>{_()},[_]),f.useEffect(()=>{C.current=k},[k]),f.useEffect(()=>()=>{R.current!==null&&window.cancelAnimationFrame(R.current)},[]);const $=f.useMemo(()=>ue(m,d),[m,d]),u=$.find(e=>e.id===v)||null,V=f.useMemo(()=>u?ne(u.desc):[],[u]),T=f.useMemo(()=>{const e=new Map,r=Math.cos(k.y),l=Math.sin(k.y),g=Math.cos(k.x),p=Math.sin(k.x);return $.forEach(x=>{const S=x.x*r+x.z*l,w=-x.x*l+x.z*r,O=x.y*g-w*p,L=x.y*p+w*g,J=760,Y=Math.max(.48,Math.min(1.7,J/(J-L)));e.set(x.id,{x:s.width/2+S*Y,y:s.height/2+O*Y,z:L,depth:Y})}),e},[$,k.x,k.y,s.height,s.width]),A=f.useMemo(()=>{const e=new Set;return u&&(u.connections.forEach(r=>e.add(r)),$.forEach(r=>{r.connections.includes(u.id)&&e.add(r.id)})),e},[u,$]),ee=f.useMemo(()=>u?Array.from(A).filter(e=>T.has(e)):[],[u,T,A]);function D(e,r){E.current={active:!0,moved:!1,sx:e,sy:r,lx:e,ly:r}}function X(e,r){const l=E.current;if(!l.active)return;const g=e-l.lx,p=r-l.ly;Math.abs(e-l.sx)+Math.abs(r-l.sy)>4&&(l.moved=!0),l.lx=e,l.ly=r,C.current={x:Math.max(-1.15,Math.min(1.15,C.current.x-p*.004)),y:C.current.y+g*.006},R.current===null&&(R.current=window.requestAnimationFrame(()=>{R.current=null,Q(C.current)}))}function P(){window.setTimeout(()=>{E.current.active=!1,E.current.moved=!1},0)}function te(e){E.current.moved||j(e.id)}function I(e){if(e==="atlas"){Z(r=>!r);return}W(r=>r===e?"":e)}return i.jsxs("div",{ref:o,className:`memory-nebula-root h-full min-h-full overflow-hidden ${u?"is-focused":""} ${N==="anchor"?"mode-anchor":""} ${N==="mood"?"mode-mood":""} ${F?"":"atlas-off"}`,onMouseDown:e=>D(e.clientX,e.clientY),onMouseMove:e=>X(e.clientX,e.clientY),onMouseUp:P,onMouseLeave:P,onTouchStart:e=>{const r=e.touches[0];r&&D(r.clientX,r.clientY)},onTouchMove:e=>{const r=e.touches[0];r&&X(r.clientX,r.clientY)},onTouchEnd:P,onClick:()=>{E.current.moved||j("")},children:[i.jsx("style",{children:he}),i.jsx("div",{className:"nebula"}),i.jsx("div",{className:"sky-atlas","aria-hidden":!0,children:i.jsx("svg",{viewBox:"0 0 1000 1000",preserveAspectRatio:"none",children:oe.map(e=>i.jsxs("g",{children:[e.lines.map(([r,l])=>{const g=e.stars[r],p=e.stars[l];return i.jsx("line",{className:"sky-atlas-line",x1:g.x,y1:g.y,x2:p.x,y2:p.y},`${r}-${l}`)}),e.stars.map((r,l)=>i.jsxs(ae.Fragment,{children:[i.jsx("circle",{className:`sky-atlas-star ${r.major?"major":""}`,cx:r.x,cy:r.y,r:r.major?2.4:1.25}),r.name?i.jsx("text",{className:"sky-atlas-star-label",x:r.x+9,y:r.y-7,children:r.name}):null]},`${e.name}-${l}`)),i.jsx("text",{className:"sky-atlas-label",x:e.label.x,y:e.label.y,children:e.name})]},e.name))})}),i.jsxs("div",{className:"hud",children:[i.jsxs("div",{className:"hud-top",children:[i.jsx("button",{type:"button",className:"crescent-btn",onClick:e=>{e.stopPropagation(),t==null||t()},"aria-label":"返回日常",children:i.jsx("svg",{className:"crescent-svg",width:"24",height:"24",viewBox:"0 0 24 24",children:i.jsx("path",{d:"M12 3a9 9 0 1 0 9 9 9.011 9.011 0 0 1-9-9Z"})})}),i.jsx("h1",{className:"app-title",children:"MNEMOSYNE"}),i.jsx("div",{className:"memory-count",children:b?"...":$.length?`${$.length} stars`:"NO DATA"})]}),i.jsxs("div",{className:"hud-side",children:[i.jsx("button",{type:"button",className:`filter-btn ${N==="anchor"?"active":""}`,onClick:e=>{e.stopPropagation(),I("anchor")},children:"ANCHOR"}),i.jsx("button",{type:"button",className:`filter-btn ${F?"active":""}`,onClick:e=>{e.stopPropagation(),I("atlas")},children:"ATLAS"}),i.jsx("button",{type:"button",className:`filter-btn ${N==="mood"?"active":""}`,onClick:e=>{e.stopPropagation(),I("mood")},children:"MOOD"})]})]}),i.jsxs("div",{className:"constellation-canvas",children:[$.map(e=>{const r=T.get(e.id);if(!r)return null;const l=(u==null?void 0:u.id)===e.id,g=A.has(e.id),S=(e.type==="core"?.82:.86)*(l?1.84:g?1.12:1)*r.depth,w={left:r.x,top:r.y,opacity:Math.max(.22,Math.min(1,.42+r.depth*.42)),transform:`translate(-50%, -50%) scale(${S})`,zIndex:Math.round(50+r.z),"--label-scale":String(1/Math.max(.72,S))};return i.jsx("button",{type:"button",className:`star star-${e.type} ${l?"active":""} ${g?"related":""}`,"data-emotion":e.emotion,style:w,onClick:O=>{O.stopPropagation(),te(e)},"aria-label":`${e.title} ${e.contentTitle}`,children:i.jsx("span",{className:"star-label",children:e.title})},e.id)}),u?ee.map(e=>{const r=T.get(u.id),l=T.get(e);if(!r||!l)return null;const g=l.x-r.x,p=l.y-r.y,x=Math.sqrt(g*g+p*p),S=Math.atan2(p,g)*180/Math.PI;return i.jsx("div",{className:"constellation-line active",style:{left:r.x,top:r.y,width:x,transform:`rotate(${S}deg)`}},`${u.id}-${e}`)}):null]}),$.length?null:i.jsxs("div",{className:"memory-empty-state",onClick:e=>e.stopPropagation(),children:[i.jsx("p",{className:"memory-empty-kicker",children:"NO SAMPLE MEMORY"}),i.jsx("h2",{children:b?"正在读取真实记忆":y?"没有拿到真实记忆":"还没有可显示的记忆"}),i.jsx("p",{children:b?"星云只会从网关返回的记忆内容生成。":y?"接口没有返回可用数据，所以这里不再展示样例卡片。":"等核心记忆或动态召回出现后，这里会生成真实星点。"}),i.jsx("button",{type:"button",onClick:e=>{e.stopPropagation(),_()},children:"重新读取"})]}),u?i.jsxs("div",{className:"memory-verse-layer","aria-live":"polite",children:[i.jsxs("div",{className:"memory-observation memory-observation-left",children:["MEMORY ",u.type.toUpperCase()," // ",u.title]}),i.jsxs("div",{className:"memory-observation memory-observation-right",children:["EMOTION: ",u.emotion.toUpperCase()," // INDEX: ",u.id.slice(0,8)]}),i.jsx("div",{className:"memory-verse","aria-label":u.desc,children:V.map((e,r)=>i.jsx("div",{className:`memory-phrase ${ie(e,r,V.length)}`,children:e},`${u.id}-${r}`))})]}):null]})}const he=`
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
  width: 5.5px;
  height: 5.5px;
  background: #f2e3b6;
  box-shadow: 0 0 3px rgba(242, 227, 182, 0.32);
}
.star-dynamic {
  width: 3.5px;
  height: 3.5px;
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
`;export{ge as MemoryNebulaTab};
