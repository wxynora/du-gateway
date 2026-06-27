import{r as s,j as e,C as V,b as v}from"./index-Zb7cCRkx.js";const j="/miniapp-api/exchange-diary";function A(n){return`${n}_${Date.now()}_${Math.random().toString(36).slice(2,8)}`}function O(n){return String(n||"").toLowerCase()==="du"?"du":"xy"}function U(n){const c=String(n||"").trim();if(!c)return"";const l=new Date(c);return Number.isNaN(l.getTime())?c.replace("T"," ").replace("+08:00","").slice(0,16).replace(/-/g,"."):l.toLocaleString("zh-CN",{year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:!1}).replace(/\//g,".")}function Z(n){const c=n.created_at||n.createdAt||"";return{id:String(n.id||A("comment")),author:O(n.author),content:String(n.content||""),createdAt:U(c).slice(-5)||String(c||"")}}function C(n){const c=n.created_at||n.createdAt||"",l=n.updated_at||n.updatedAt||c;return{id:String(n.id||A("diary")),author:O(n.author),title:String(n.title||"没有标题的小纸条"),createdAt:U(c),updatedAt:String(l||""),emoji:String(n.emoji||n.mood||"✦").slice(0,4)||"✦",content:String(n.content||""),comments:Array.isArray(n.comments)?n.comments.map(Z):[]}}function B(n){return n==="du"?"渡":"我"}function H(n){return{author:n,title:"",emoji:"✦",content:""}}function ie({onBack:n,backHandlerRef:c}){const[l,k]=s.useState("du"),[S,h]=s.useState([]),[E,u]=s.useState(null),[o,x]=s.useState(null),[T,z]=s.useState(""),[I,R]=s.useState(!1),[G,D]=s.useState(!1),[q,$]=s.useState(""),[y,f]=s.useState(!1),[_,m]=s.useState(""),w=s.useRef(0),b=s.useRef(0),F=S,g=s.useMemo(()=>S.find(t=>t.id===E)||null,[S,E]);async function J(t=l){const a=w.current+1;w.current=a,R(!0),m("");try{const i=new URLSearchParams({author:t,limit:"80"}),r=await v(`${j}?${i.toString()}`);if(a!==w.current)return;const d=(r.items||[]).map(C);h(d)}catch(i){if(a!==w.current)return;m(i instanceof Error?i.message:String(i)),h([])}finally{a===w.current&&R(!1)}}async function M(t){const a=b.current+1;b.current=a,u(t),z(""),D(!0),$("");try{const i=await v(`${j}/${encodeURIComponent(t)}`);if(a!==b.current)return;const r=i.item?C(i.item):null;r&&h(d=>d.map(p=>p.id===r.id?r:p))}catch(i){if(a!==b.current)return;$(i instanceof Error?i.message:String(i)),i&&typeof i=="object"&&"status"in i&&i.status===404&&(h(r=>r.filter(d=>d.id!==t)),u(null))}finally{a===b.current&&D(!1)}}function L(){return o?(x(null),!0):E?(b.current+=1,u(null),z(""),D(!1),$(""),!0):!1}s.useEffect(()=>{if(c)return c.current=L,()=>{c.current===L&&(c.current=null)}},[c,o,E]),s.useEffect(()=>{J(l)},[l]);function X(){L()||n()}function Y(t){x({id:t.id,author:t.author,title:t.title,emoji:t.emoji,content:t.content})}async function W(){if(!o||y)return;const t=o.title.trim()||"没有标题的小纸条",a=o.emoji.trim()||"✦",i=o.content.trim();if(i){f(!0),m("");try{let r=null;if(o.id){const d=S.find(N=>N.id===o.id),p=await v(`${j}/${encodeURIComponent(o.id)}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({author:o.author,title:t,mood:a,content:i,base_updated_at:(d==null?void 0:d.updatedAt)||""})});r=p.item?C(p.item):null,r&&(r.author!==l?(k(r.author),h([r])):h(N=>N.map(P=>P.id===r.id?r:P)))}else{const d=await v(j,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({author:"xy",title:t,mood:a,content:i,client_request_id:A("exchange_diary")})});r=d.item?C(d.item):null,r&&(k(r.author),h(p=>[r,...p.filter(N=>N.id!==r.id)]),u(r.id))}x(null)}catch(r){m(r instanceof Error?r.message:String(r))}finally{f(!1)}}}async function K(t){if(!y){f(!0),m("");try{await v(`${j}/${encodeURIComponent(t)}`,{method:"DELETE"}),h(a=>a.filter(i=>i.id!==t)),u(null),x(null)}catch(a){m(a instanceof Error?a.message:String(a))}finally{f(!1)}}}async function Q(t){if(y)return;const a=T.trim();if(a){f(!0),m("");try{const i=await v(`${j}/${encodeURIComponent(t.id)}/comments`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({author:"xy",content:a,client_request_id:A("exchange_diary_comment")})}),r=i.item?C(i.item):null;r&&h(d=>d.map(p=>p.id===r.id?r:p)),z("")}catch(i){m(i instanceof Error?i.message:String(i))}finally{f(!1)}}}return e.jsxs("div",{className:"exchange-diary-page",children:[e.jsx(ae,{}),e.jsxs("header",{className:"exchange-diary-header-lace",children:[e.jsx("button",{className:"exchange-diary-back",type:"button",onClick:X,"aria-label":"返回",children:e.jsx(V,{})}),e.jsxs("div",{className:"exchange-diary-toggle",role:"tablist","aria-label":"交换日记",children:[e.jsxs("button",{className:`exchange-diary-toggle-btn ${l==="du"?"active":""}`,type:"button",onClick:()=>k("du"),role:"tab","aria-selected":l==="du",children:[e.jsx(ee,{}),"渡的Diary"]}),e.jsx("button",{className:`exchange-diary-toggle-btn ${l==="xy"?"active":""}`,type:"button",onClick:()=>k("xy"),role:"tab","aria-selected":l==="xy",children:"我的Diary"})]})]}),e.jsxs("main",{className:"exchange-diary-timeline-container",children:[e.jsx("div",{className:"exchange-diary-timeline-line"}),_?e.jsx("div",{className:"exchange-diary-status error",children:_}):null,I?e.jsx("div",{className:"exchange-diary-status",children:"翻日记中..."}):null,!I&&!_&&F.length===0?e.jsx("div",{className:"exchange-diary-status",children:"还没有日记"}):null,F.map((t,a)=>e.jsxs("article",{className:`exchange-diary-entry ${a%2===0?"side-left":"side-right"} author-${t.author}`,children:[a<2?e.jsx("div",{className:"exchange-diary-star-ornament",style:a%2===0?{top:"-20px",left:"10%"}:{top:"0",right:"5%"},children:"★"}):null,e.jsx("button",{className:"exchange-diary-sticky-note",type:"button",onClick:()=>void M(t.id),children:e.jsxs("div",{className:"exchange-diary-entry-header compact",children:[e.jsxs("div",{className:"exchange-diary-card-title-line",children:[e.jsx("span",{className:"exchange-diary-entry-title compact",children:t.title}),e.jsx("span",{className:"exchange-diary-entry-emoji compact",children:t.emoji})]}),e.jsx("span",{className:"exchange-diary-entry-time compact",children:t.createdAt})]})})]},t.id))]}),e.jsx("button",{className:"exchange-diary-add-entry-btn",type:"button",onClick:()=>{k("xy"),x(H("xy"))},"aria-label":"写一条日记",children:e.jsx(te,{})}),g?e.jsx("div",{className:"exchange-diary-overlay active",onClick:()=>u(null),children:e.jsxs("div",{className:"exchange-diary-detail-card",onClick:t=>t.stopPropagation(),children:[e.jsxs("div",{className:"exchange-diary-entry-header",children:[e.jsx("span",{className:"exchange-diary-entry-title",children:g.title}),e.jsx("span",{className:"exchange-diary-entry-time",children:g.createdAt})]}),G?e.jsx("div",{className:"exchange-diary-status inline",children:"翻这一页中..."}):null,q?e.jsx("div",{className:"exchange-diary-status inline error",children:q}):null,e.jsx("div",{className:"exchange-diary-entry-content detail",children:g.content}),e.jsxs("div",{className:"exchange-diary-entry-footer detail-footer",children:[e.jsx("span",{className:"exchange-diary-entry-emoji",children:g.emoji}),e.jsxs("span",{className:"exchange-diary-comment-count",children:[B(g.author),"写的"]})]}),e.jsxs("div",{className:"exchange-diary-comments-section",children:[e.jsxs("p",{className:"exchange-diary-comments-title",children:["Comments (",g.comments.length,")"]}),g.comments.map(t=>e.jsxs("div",{className:"exchange-diary-comment-row",children:[e.jsxs("strong",{children:[B(t.author),":"]})," ",t.content]},t.id)),e.jsxs("div",{className:"exchange-diary-comment-box",children:[e.jsx("textarea",{value:T,onChange:t=>z(t.target.value),placeholder:"写一句评论...",rows:2}),e.jsx("button",{type:"button",onClick:()=>Q(g),disabled:y,children:"保存评论"})]})]}),e.jsxs("div",{className:"exchange-diary-actions",children:[e.jsx("button",{className:"exchange-diary-action-link",type:"button",onClick:()=>Y(g),children:"Edit"}),e.jsx("button",{className:"exchange-diary-action-link",type:"button",onClick:()=>K(g.id),disabled:y,children:"Delete"}),e.jsx("button",{className:"exchange-diary-action-link push-right",type:"button",onClick:()=>u(null),children:"Close"})]})]})}):null,o?e.jsx("div",{className:"exchange-diary-overlay active",onClick:()=>x(null),children:e.jsxs("div",{className:"exchange-diary-detail-card editor",onClick:t=>t.stopPropagation(),children:[e.jsxs("div",{className:"exchange-diary-editor-row",children:[e.jsx("input",{className:"title-input",value:o.title,onChange:t=>x(a=>a&&{...a,title:t.target.value}),placeholder:"标题"}),e.jsxs("label",{className:"exchange-diary-emoji-field",children:[e.jsx("span",{children:"emoji"}),e.jsx("input",{className:"emoji-input",value:o.emoji,onChange:t=>x(a=>a&&{...a,emoji:t.target.value.slice(0,4)}),placeholder:"✦","aria-label":"emoji"})]})]}),o.id?e.jsxs("div",{className:"exchange-diary-author-switch",children:[e.jsx("button",{type:"button",className:o.author==="du"?"active":"",onClick:()=>x(t=>t&&{...t,author:"du"}),children:"渡"}),e.jsx("button",{type:"button",className:o.author==="xy"?"active":"",onClick:()=>x(t=>t&&{...t,author:"xy"}),children:"我"})]}):null,e.jsx("textarea",{className:"exchange-diary-editor-content",value:o.content,onChange:t=>x(a=>a&&{...a,content:t.target.value}),placeholder:"把今天想留下的事写在这里...",rows:8}),e.jsxs("div",{className:"exchange-diary-actions",children:[e.jsx("button",{className:"exchange-diary-action-link",type:"button",onClick:()=>x(null),children:"Cancel"}),e.jsx("button",{className:"exchange-diary-action-link push-right",type:"button",onClick:W,disabled:y,children:"Save"})]})]})}):null]})}function ee(){return e.jsx("svg",{viewBox:"0 0 24 24","aria-hidden":"true",children:e.jsx("path",{d:"M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"})})}function te(){return e.jsxs("svg",{viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"2",strokeLinecap:"round",strokeLinejoin:"round","aria-hidden":"true",children:[e.jsx("line",{x1:"12",y1:"5",x2:"12",y2:"19"}),e.jsx("line",{x1:"5",y1:"12",x2:"19",y2:"12"})]})}function ae(){return e.jsx("style",{children:`
      .exchange-diary-page {
        --bg-cream: #FDF9F8;
        --soft-pink: #F7E9EB;
        --soft-blue: #E8EEF4;
        --soft-yellow: #FFF8E6;
        --accent-pink: #EBD5D8;
        --text-main: #7A7272;
        --text-light: #A8A1A1;
        --border-color: #E2D6D8;
        --serif-font: "Georgia", "Times New Roman", "Songti SC", serif;
        --mono-font: "Courier New", Courier, monospace;
        position: fixed;
        inset: 0;
        z-index: 40;
        min-height: 100dvh;
        overflow-y: auto;
        overflow-x: hidden;
        background-color: var(--bg-cream);
        background-image:
          radial-gradient(circle, rgba(235, 213, 216, 0.22) 1px, transparent 1px),
          linear-gradient(to bottom, rgba(255,255,255,0.8), rgba(255,255,255,0.8));
        background-size: 20px 20px, 100% 100%;
        color: var(--text-main);
        font-family: var(--serif-font);
        -webkit-font-smoothing: antialiased;
      }

      .exchange-diary-page button,
      .exchange-diary-page input,
      .exchange-diary-page textarea {
        font-family: inherit;
      }

      .exchange-diary-header-lace {
        width: 100%;
        height: calc(env(safe-area-inset-top, 0px) + 60px);
        padding-top: env(safe-area-inset-top, 0px);
        background-color: white;
        position: sticky;
        top: 0;
        z-index: 100;
        display: flex;
        justify-content: center;
        align-items: center;
        border-bottom: 1px dashed var(--border-color);
        box-shadow: 0 2px 10px rgba(0,0,0,0.02);
      }

      .exchange-diary-header-lace::before {
        content: "";
        position: absolute;
        bottom: -12px;
        left: 0;
        right: 0;
        height: 12px;
        background-image: radial-gradient(circle at 6px 0, transparent 6px, white 6px);
        background-size: 12px 12px;
      }

      .exchange-diary-back {
        position: absolute;
        left: 12px;
        top: calc(env(safe-area-inset-top, 0px) + 10px);
        z-index: 2;
        width: 40px;
        height: 40px;
        border: none;
        border-radius: 999px;
        background: transparent;
        color: var(--text-main);
        display: flex;
        align-items: center;
        justify-content: center;
      }

      .exchange-diary-toggle {
        display: flex;
        background: var(--soft-pink);
        padding: 4px;
        border-radius: 20px;
        gap: 4px;
        position: relative;
      }

      .exchange-diary-toggle-btn {
        padding: 6px 24px;
        border-radius: 16px;
        border: none;
        cursor: pointer;
        font-size: 14px;
        transition: all 0.3s ease;
        background: transparent;
        color: var(--text-light);
        display: flex;
        align-items: center;
        gap: 6px;
      }

      .exchange-diary-toggle-btn.active {
        background: white;
        color: var(--text-main);
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
      }

      .exchange-diary-toggle-btn svg {
        width: 12px;
        height: 12px;
        fill: currentColor;
      }

      .exchange-diary-timeline-container {
        width: 100%;
        max-width: 700px;
        margin: 0 auto;
        padding: 60px 20px 120px;
        position: relative;
      }

      .exchange-diary-timeline-line {
        position: absolute;
        left: 50%;
        top: 0;
        bottom: 0;
        width: 1px;
        border-left: 1.5px dashed var(--border-color);
        z-index: 0;
      }

      .exchange-diary-status {
        position: relative;
        z-index: 2;
        width: fit-content;
        max-width: min(420px, calc(100vw - 56px));
        margin: 20px auto 34px;
        padding: 12px 18px;
        border: 1px dashed var(--border-color);
        background: rgba(255, 255, 255, 0.78);
        color: var(--text-light);
        font-size: 13px;
        text-align: center;
      }

      .exchange-diary-status.error {
        color: #9a5f66;
        background: rgba(255, 248, 248, 0.86);
      }

      .exchange-diary-status.inline {
        margin: 0 0 14px;
        width: 100%;
        max-width: none;
      }

      .exchange-diary-entry {
        width: 100%;
        margin-bottom: 52px;
        position: relative;
        z-index: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
      }

      .exchange-diary-sticky-note {
        width: 420px;
        padding: 30px;
        position: relative;
        text-align: left;
        color: var(--text-main);
        box-shadow: 0 4px 15px rgba(0,0,0,0.03);
        border: 1px solid rgba(235, 213, 216, 0.4);
        transition: transform 0.2s ease;
        cursor: pointer;
      }

      .exchange-diary-sticky-note:active {
        transform: translateY(-2px);
      }

      .exchange-diary-sticky-note::before {
        content: "♥";
        position: absolute;
        top: -15px;
        left: 50%;
        transform: translateX(-50%);
        font-size: 16px;
        color: var(--accent-pink);
        background: var(--bg-cream);
        padding: 0 10px;
      }

      .exchange-diary-entry.author-du .exchange-diary-sticky-note {
        background-color: var(--soft-blue);
      }

      .exchange-diary-entry.author-xy .exchange-diary-sticky-note {
        background-color: var(--soft-yellow);
      }

      .exchange-diary-entry.side-left .exchange-diary-sticky-note {
        align-self: flex-start;
        margin-left: 20px;
      }

      .exchange-diary-entry.side-right .exchange-diary-sticky-note {
        align-self: flex-end;
        margin-right: 20px;
      }

      .exchange-diary-entry-header {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 16px;
        margin-bottom: 15px;
        border-bottom: 1px solid rgba(0,0,0,0.05);
        padding-bottom: 10px;
      }

      .exchange-diary-entry-header.compact {
        flex-direction: column;
        justify-content: center;
        align-items: center;
        gap: 6px;
        margin-bottom: 0;
        border-bottom: none;
        padding-bottom: 0;
      }

      .exchange-diary-card-title-line {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 6px;
        width: 100%;
      }

      .exchange-diary-entry-title {
        min-width: 0;
        font-size: 18px;
        font-weight: 500;
        color: var(--text-main);
      }

      .exchange-diary-entry-title.compact {
        font-size: 15px;
        line-height: 1.35;
        text-align: center;
      }

      .exchange-diary-entry-time {
        flex-shrink: 0;
        font-family: var(--mono-font);
        font-size: 11px;
        color: var(--text-light);
        text-transform: uppercase;
      }

      .exchange-diary-entry-time.compact {
        font-size: 10px;
        letter-spacing: 0.04em;
      }

      .exchange-diary-entry-content {
        font-size: 14px;
        line-height: 1.8;
        color: var(--text-main);
        margin-bottom: 20px;
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
        overflow: hidden;
      }

      .exchange-diary-entry-content.detail {
        display: block;
        overflow: visible;
        -webkit-line-clamp: initial;
        white-space: pre-wrap;
      }

      .exchange-diary-entry-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        font-size: 12px;
      }

      .exchange-diary-entry-footer.compact {
        justify-content: center;
      }

      .exchange-diary-entry-footer.detail-footer {
        border-bottom: 1px solid var(--soft-pink);
        padding-bottom: 15px;
        margin-bottom: 20px;
      }

      .exchange-diary-entry-emoji {
        font-size: 16px;
      }

      .exchange-diary-entry-emoji.compact {
        flex-shrink: 0;
        font-size: 15px;
        line-height: 1;
      }

      .exchange-diary-comment-count {
        color: var(--text-light);
        display: flex;
        align-items: center;
        gap: 4px;
      }

      .exchange-diary-add-entry-btn {
        position: fixed;
        bottom: calc(env(safe-area-inset-bottom, 0px) + 32px);
        right: 28px;
        z-index: 90;
        width: 50px;
        height: 50px;
        background: white;
        border: 1px solid var(--accent-pink);
        border-radius: 50%;
        display: flex;
        justify-content: center;
        align-items: center;
        cursor: pointer;
        box-shadow: 0 4px 10px rgba(235, 213, 216, 0.4);
        transition: all 0.3s ease;
        color: var(--accent-pink);
      }

      .exchange-diary-add-entry-btn:active {
        transform: scale(1.1) rotate(90deg);
        background: var(--soft-pink);
      }

      .exchange-diary-add-entry-btn svg {
        width: 20px;
        height: 20px;
      }

      .exchange-diary-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(253, 249, 248, 0.95);
        z-index: 1000;
        display: none;
        justify-content: center;
        padding: calc(env(safe-area-inset-top, 0px) + 80px) 20px calc(env(safe-area-inset-bottom, 0px) + 40px);
        overflow-y: auto;
      }

      .exchange-diary-overlay.active {
        display: flex;
      }

      .exchange-diary-detail-card {
        width: 100%;
        max-width: 600px;
        background: white;
        padding: 40px;
        height: fit-content;
        border: 1px solid var(--border-color);
        box-shadow: 0 10px 40px rgba(0,0,0,0.05);
      }

      .exchange-diary-detail-card.editor {
        background: var(--soft-pink);
      }

      .exchange-diary-comments-section {
        font-size: 13px;
      }

      .exchange-diary-comments-title {
        color: var(--text-light);
        margin-bottom: 10px;
      }

      .exchange-diary-comment-row {
        margin-bottom: 10px;
        background: var(--bg-cream);
        padding: 10px;
      }

      .exchange-diary-comment-box {
        margin-top: 14px;
        display: grid;
        gap: 10px;
      }

      .exchange-diary-comment-box textarea,
      .exchange-diary-editor-row input,
      .exchange-diary-editor-content {
        width: 100%;
        border: 1px dashed var(--border-color);
        background: rgba(255,255,255,0.72);
        color: var(--text-main);
        outline: none;
        padding: 10px 12px;
        font-size: 14px;
        line-height: 1.7;
      }

      .exchange-diary-comment-box button {
        justify-self: end;
        border: 1px solid var(--accent-pink);
        background: white;
        color: var(--text-main);
        padding: 7px 14px;
        font-size: 12px;
      }

      .exchange-diary-actions {
        margin-top: 30px;
        padding-top: 20px;
        border-top: 1px dashed var(--border-color);
        display: flex;
        gap: 20px;
      }

      .exchange-diary-action-link {
        border: none;
        background: transparent;
        padding: 0;
        font-size: 12px;
        color: var(--text-light);
        text-decoration: none;
        cursor: pointer;
      }

      .exchange-diary-action-link:active {
        color: var(--text-main);
      }

      .exchange-diary-action-link.push-right {
        margin-left: auto;
      }

      .exchange-diary-editor-row {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 86px;
        align-items: end;
        gap: 10px;
        margin-bottom: 12px;
      }

      .exchange-diary-emoji-field {
        display: grid;
        grid-template-rows: auto 1fr;
        gap: 3px;
      }

      .exchange-diary-emoji-field span {
        font-family: var(--mono-font);
        font-size: 9px;
        line-height: 1;
        letter-spacing: 0.08em;
        text-align: center;
        text-transform: uppercase;
        color: var(--text-light);
      }

      .exchange-diary-editor-row .emoji-input {
        text-align: center;
      }

      .exchange-diary-author-switch {
        display: flex;
        width: fit-content;
        margin-bottom: 14px;
        padding: 4px;
        background: rgba(255,255,255,0.45);
        border-radius: 999px;
        gap: 4px;
      }

      .exchange-diary-author-switch button {
        border: none;
        background: transparent;
        color: var(--text-light);
        border-radius: 999px;
        padding: 5px 18px;
        font-size: 13px;
      }

      .exchange-diary-author-switch button.active {
        background: white;
        color: var(--text-main);
      }

      .exchange-diary-editor-content {
        resize: vertical;
        min-height: 170px;
      }

      .exchange-diary-star-ornament {
        position: absolute;
        color: var(--accent-pink);
        font-size: 10px;
        opacity: 0.6;
      }

      @media (max-width: 600px) {
        .exchange-diary-back {
          left: 8px;
        }

        .exchange-diary-toggle-btn {
          padding: 6px 18px;
          font-size: 13px;
        }

        .exchange-diary-timeline-container {
          padding: 52px 12px 118px;
        }

        .exchange-diary-sticky-note {
          width: min(74vw, 292px);
          padding: 24px 22px;
        }

        .exchange-diary-entry {
          margin-bottom: 34px;
        }

        .exchange-diary-entry.side-left .exchange-diary-sticky-note {
          align-self: flex-start;
          margin-left: 10px;
          margin-right: 0;
        }

        .exchange-diary-entry.side-right .exchange-diary-sticky-note {
          align-self: flex-end;
          margin-right: 10px;
          margin-left: 0;
        }

        .exchange-diary-entry-header {
          flex-direction: column;
          align-items: flex-start;
          gap: 4px;
        }

        .exchange-diary-detail-card {
          padding: 30px 24px;
        }

        .exchange-diary-add-entry-btn {
          right: 22px;
          bottom: calc(env(safe-area-inset-bottom, 0px) + 28px);
        }
      }

      @media (max-width: 360px) {
        .exchange-diary-sticky-note {
          width: min(76vw, 272px);
        }

        .exchange-diary-toggle-btn {
          padding-left: 14px;
          padding-right: 14px;
        }
      }
    `})}export{ie as ExchangeDiaryTab};
