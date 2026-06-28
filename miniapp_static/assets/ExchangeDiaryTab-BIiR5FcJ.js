import{r as c,j as e,C as ce,b as k}from"./index-DwYEQl2C.js";const w="/miniapp-api/exchange-diary",se=20;function L(i){return`${i}_${Date.now()}_${Math.random().toString(36).slice(2,8)}`}function Q(i){return String(i||"").toLowerCase()==="du"?"du":"xy"}function V(i){const l=String(i||"").trim();if(!l)return"";const x=new Date(l);return Number.isNaN(x.getTime())?l.replace("T"," ").replace("+08:00","").slice(0,16).replace(/-/g,"."):x.toLocaleString("zh-CN",{year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:!1}).replace(/\//g,".")}function de(i){const l=i.created_at||i.createdAt||"";return{id:String(i.id||L("comment")),author:Q(i.author),content:String(i.content||""),createdAt:V(l).slice(-5)||String(l||"")}}function z(i){const l=i.created_at||i.createdAt||"",x=i.updated_at||i.updatedAt||l;return{id:String(i.id||L("diary")),author:Q(i.author),title:String(i.title||"没有标题的小纸条"),createdAt:V(l),updatedAt:String(x||""),emoji:String(i.emoji||i.mood||"✦").slice(0,4)||"✦",content:String(i.content||""),comments:Array.isArray(i.comments)?i.comments.map(de):[]}}function K(i){return i==="du"?"渡":"我"}function le(i){return{author:i,title:"",emoji:"✦",content:""}}function me({onBack:i,backHandlerRef:l}){const[x,N]=c.useState("du"),[A,p]=c.useState([]),[D,y]=c.useState(null),[s,g]=c.useState(null),[$,C]=c.useState(""),[B,b]=c.useState(""),[I,G]=c.useState(!1),[H,T]=c.useState(!1),[O,R]=c.useState(""),[f,v]=c.useState(!1),[q,u]=c.useState(""),[U,_]=c.useState(""),[J,P]=c.useState(""),[X,Y]=c.useState(!1),S=c.useRef(0),j=c.useRef(0),W=A,h=c.useMemo(()=>A.find(t=>t.id===D)||null,[A,D]);async function Z(t=x,a=""){const r=S.current+1;S.current=r;const n=!!a;n?(Y(!0),_("")):(G(!0),P(""),_("")),n||u("");try{const o=new URLSearchParams({author:t,limit:String(se)});a&&o.set("cursor",a);const d=await k(`${w}?${o.toString()}`);if(r!==S.current)return;const m=(d.items||[]).map(z);P(String(d.next_cursor||d.nextCursor||"")),p(n?E=>{const oe=new Set(E.map(M=>M.id));return[...E,...m.filter(M=>!oe.has(M.id))]}:m)}catch(o){if(r!==S.current)return;const d=o instanceof Error?o.message:String(o);n?_(d):u(d),n||p([])}finally{r===S.current&&(G(!1),Y(!1))}}async function ee(t){const a=j.current+1;j.current=a,y(t),C(""),b(""),T(!0),R("");try{const r=await k(`${w}/${encodeURIComponent(t)}`);if(a!==j.current)return;const n=r.item?z(r.item):null;n&&p(o=>o.map(d=>d.id===n.id?n:d))}catch(r){if(a!==j.current)return;R(r instanceof Error?r.message:String(r)),r&&typeof r=="object"&&"status"in r&&r.status===404&&(p(n=>n.filter(o=>o.id!==t)),y(null))}finally{a===j.current&&T(!1)}}function F(){return s?(g(null),!0):D?(j.current+=1,y(null),C(""),b(""),T(!1),R(""),!0):!1}c.useEffect(()=>{if(l)return l.current=F,()=>{l.current===F&&(l.current=null)}},[l,s,D]),c.useEffect(()=>{p([]),P(""),_(""),u(""),Z(x)},[x]);function te(){F()||i()}function ae(t){g({id:t.id,author:t.author,title:t.title,emoji:t.emoji,content:t.content})}async function ne(){if(!s||f)return;const t=s.title.trim()||"没有标题的小纸条",a=s.emoji.trim()||"✦",r=s.content.trim();if(r){v(!0),u("");try{let n=null;if(s.id){const o=A.find(m=>m.id===s.id),d=await k(`${w}/${encodeURIComponent(s.id)}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({author:s.author,title:t,mood:a,content:r,base_updated_at:(o==null?void 0:o.updatedAt)||""})});n=d.item?z(d.item):null,n&&(n.author!==x?(N(n.author),p([n])):p(m=>m.map(E=>E.id===n.id?n:E)))}else{const o=await k(w,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({author:"xy",title:t,mood:a,content:r,client_request_id:L("exchange_diary")})});n=o.item?z(o.item):null,n&&(N(n.author),p(d=>[n,...d.filter(m=>m.id!==n.id)]),y(n.id))}g(null)}catch(n){u(n instanceof Error?n.message:String(n))}finally{v(!1)}}}async function ie(t){if(!f){v(!0),u("");try{await k(`${w}/${encodeURIComponent(t)}`,{method:"DELETE"}),p(a=>a.filter(r=>r.id!==t)),y(null),g(null)}catch(a){u(a instanceof Error?a.message:String(a))}finally{v(!1)}}}async function re(t){if(f)return;const a=$.trim();if(!a)return;const r=B||L("exchange_diary_comment");B||b(r),v(!0),u("");try{const n=await k(`${w}/${encodeURIComponent(t.id)}/comments`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({author:"xy",content:a,client_request_id:r})}),o=n.item?z(n.item):null;o&&p(d=>d.map(m=>m.id===o.id?o:m)),C(""),b("")}catch(n){u(n instanceof Error?n.message:String(n))}finally{v(!1)}}return e.jsxs("div",{className:"exchange-diary-page",children:[e.jsx(pe,{}),e.jsxs("header",{className:"exchange-diary-header-lace",children:[e.jsx("button",{className:"exchange-diary-back",type:"button",onClick:te,"aria-label":"返回",children:e.jsx(ce,{})}),e.jsxs("div",{className:"exchange-diary-toggle",role:"tablist","aria-label":"交换日记",children:[e.jsxs("button",{className:`exchange-diary-toggle-btn ${x==="du"?"active":""}`,type:"button",onClick:()=>N("du"),role:"tab","aria-selected":x==="du",children:[e.jsx(xe,{}),"渡的Diary"]}),e.jsx("button",{className:`exchange-diary-toggle-btn ${x==="xy"?"active":""}`,type:"button",onClick:()=>N("xy"),role:"tab","aria-selected":x==="xy",children:"我的Diary"})]})]}),e.jsxs("main",{className:"exchange-diary-timeline-container",children:[e.jsx("div",{className:"exchange-diary-timeline-line"}),q?e.jsx("div",{className:"exchange-diary-status error",children:q}):null,I?e.jsx("div",{className:"exchange-diary-status",children:"翻日记中..."}):null,!I&&!q&&W.length===0?e.jsx("div",{className:"exchange-diary-status",children:"还没有日记"}):null,W.map((t,a)=>e.jsxs("article",{className:`exchange-diary-entry ${a%2===0?"side-left":"side-right"} author-${t.author}`,children:[a<2?e.jsx("div",{className:"exchange-diary-star-ornament",style:a%2===0?{top:"-20px",left:"10%"}:{top:"0",right:"5%"},children:"★"}):null,e.jsx("button",{className:"exchange-diary-sticky-note",type:"button",onClick:()=>void ee(t.id),children:e.jsxs("div",{className:"exchange-diary-entry-header compact",children:[e.jsxs("div",{className:"exchange-diary-card-title-line",children:[e.jsx("span",{className:"exchange-diary-entry-title compact",children:t.title}),e.jsx("span",{className:"exchange-diary-entry-emoji compact",children:t.emoji})]}),e.jsx("span",{className:"exchange-diary-entry-time compact",children:t.createdAt})]})})]},t.id)),U?e.jsx("div",{className:"exchange-diary-status inline error",children:U}):null,!I&&J?e.jsx("button",{className:"exchange-diary-load-more",type:"button",onClick:()=>void Z(x,J),disabled:X,children:X?"翻页中...":"继续翻"}):null]}),e.jsx("button",{className:"exchange-diary-add-entry-btn",type:"button",onClick:()=>{N("xy"),g(le("xy"))},"aria-label":"写一条日记",children:e.jsx(ge,{})}),h?e.jsx("div",{className:"exchange-diary-overlay active",onClick:()=>{y(null),C(""),b("")},children:e.jsxs("div",{className:"exchange-diary-detail-card",onClick:t=>t.stopPropagation(),children:[e.jsxs("div",{className:"exchange-diary-entry-header",children:[e.jsx("span",{className:"exchange-diary-entry-title",children:h.title}),e.jsx("span",{className:"exchange-diary-entry-time",children:h.createdAt})]}),H?e.jsx("div",{className:"exchange-diary-status inline",children:"翻这一页中..."}):null,O?e.jsx("div",{className:"exchange-diary-status inline error",children:O}):null,e.jsx("div",{className:"exchange-diary-entry-content detail",children:h.content}),e.jsxs("div",{className:"exchange-diary-entry-footer detail-footer",children:[e.jsx("span",{className:"exchange-diary-entry-emoji",children:h.emoji}),e.jsxs("span",{className:"exchange-diary-comment-count",children:[K(h.author),"写的"]})]}),e.jsxs("div",{className:"exchange-diary-comments-section",children:[e.jsxs("p",{className:"exchange-diary-comments-title",children:["Comments (",h.comments.length,")"]}),h.comments.map(t=>e.jsxs("div",{className:"exchange-diary-comment-row",children:[e.jsxs("strong",{children:[K(t.author),":"]})," ",t.content]},t.id)),e.jsxs("div",{className:"exchange-diary-comment-box",children:[e.jsx("textarea",{value:$,onChange:t=>{C(t.target.value),b("")},placeholder:"写一句评论...",rows:2,disabled:f}),e.jsx("button",{type:"button",onClick:()=>re(h),disabled:f||!$.trim(),children:"保存评论"})]})]}),e.jsxs("div",{className:"exchange-diary-actions",children:[e.jsx("button",{className:"exchange-diary-action-link",type:"button",onClick:()=>ae(h),children:"Edit"}),e.jsx("button",{className:"exchange-diary-action-link",type:"button",onClick:()=>ie(h.id),disabled:f,children:"Delete"}),e.jsx("button",{className:"exchange-diary-action-link push-right",type:"button",onClick:()=>y(null),children:"Close"})]})]})}):null,s?e.jsx("div",{className:"exchange-diary-overlay active",onClick:()=>g(null),children:e.jsxs("div",{className:"exchange-diary-detail-card editor",onClick:t=>t.stopPropagation(),children:[e.jsxs("div",{className:"exchange-diary-editor-row",children:[e.jsx("input",{className:"title-input",value:s.title,onChange:t=>g(a=>a&&{...a,title:t.target.value}),placeholder:"标题"}),e.jsxs("label",{className:"exchange-diary-emoji-field",children:[e.jsx("span",{children:"emoji"}),e.jsx("input",{className:"emoji-input",value:s.emoji,onChange:t=>g(a=>a&&{...a,emoji:t.target.value.slice(0,4)}),placeholder:"✦","aria-label":"emoji"})]})]}),s.id?e.jsxs("div",{className:"exchange-diary-author-switch",children:[e.jsx("button",{type:"button",className:s.author==="du"?"active":"",onClick:()=>g(t=>t&&{...t,author:"du"}),children:"渡"}),e.jsx("button",{type:"button",className:s.author==="xy"?"active":"",onClick:()=>g(t=>t&&{...t,author:"xy"}),children:"我"})]}):null,e.jsx("textarea",{className:"exchange-diary-editor-content",value:s.content,onChange:t=>g(a=>a&&{...a,content:t.target.value}),placeholder:"把今天想留下的事写在这里...",rows:8}),e.jsxs("div",{className:"exchange-diary-actions",children:[e.jsx("button",{className:"exchange-diary-action-link",type:"button",onClick:()=>g(null),children:"Cancel"}),e.jsx("button",{className:"exchange-diary-action-link push-right",type:"button",onClick:ne,disabled:f,children:"Save"})]})]})}):null]})}function xe(){return e.jsx("svg",{viewBox:"0 0 24 24","aria-hidden":"true",children:e.jsx("path",{d:"M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"})})}function ge(){return e.jsxs("svg",{viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"2",strokeLinecap:"round",strokeLinejoin:"round","aria-hidden":"true",children:[e.jsx("line",{x1:"12",y1:"5",x2:"12",y2:"19"}),e.jsx("line",{x1:"5",y1:"12",x2:"19",y2:"12"})]})}function pe(){return e.jsx("style",{children:`
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

      .exchange-diary-load-more {
        position: relative;
        z-index: 2;
        display: block;
        margin: -8px auto 40px;
        padding: 8px 20px;
        border: 1px solid rgba(213, 168, 176, 0.38);
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.72);
        color: var(--text-light);
        font-size: 13px;
        letter-spacing: 0;
      }

      .exchange-diary-load-more:disabled {
        opacity: 0.55;
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
    `})}export{me as ExchangeDiaryTab};
