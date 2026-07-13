import{r as s,j as e,C as le,b as z}from"./index-CEFep49V.js";const A="/miniapp-api/exchange-diary",xe=20;function R(a){return`${a}_${Date.now()}_${Math.random().toString(36).slice(2,8)}`}function te(a){return String(a||"").toLowerCase()==="du"?"du":"xy"}function ae(a){const d=String(a||"").trim();if(!d)return"";const c=new Date(d);return Number.isNaN(c.getTime())?d.replace("T"," ").replace("+08:00","").slice(0,16).replace(/-/g,"."):c.toLocaleString("zh-CN",{year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:!1}).replace(/\//g,".")}function ge(a){const d=a.created_at||a.createdAt||"";return{id:String(a.id||R("comment")),author:te(a.author),content:String(a.content||""),createdAt:ae(d).slice(-5)||String(d||""),replyToCommentId:String(a.reply_to_comment_id||a.replyToCommentId||"")}}function T(a){const d=a.created_at||a.createdAt||"",c=a.updated_at||a.updatedAt||d;return{id:String(a.id||R("diary")),author:te(a.author),title:String(a.title||"没有标题的小纸条"),createdAt:ae(d),updatedAt:String(c||""),emoji:String(a.emoji||a.mood||"✦").slice(0,4)||"✦",content:String(a.content||""),comments:Array.isArray(a.comments)?a.comments.map(ge):[]}}function q(a){return a==="du"?"渡":"我"}function pe(a,d){const c=q(a.author);if(!a.replyToCommentId)return c;const b=d.find(C=>C.id===a.replyToCommentId);return b?`${c} 回复 ${q(b.author)}`:`${c} 回复`}function he(a,d=32){const c=a.replace(/\s+/g," ").trim();return c.length>d?`${c.slice(0,d)}...`:c}function me(a){return{author:a,title:"",emoji:"✦",content:""}}function ve({onBack:a,backHandlerRef:d}){const[c,b]=s.useState("du"),[C,m]=s.useState([]),[D,j]=s.useState(null),[g,p]=s.useState(null),[P,k]=s.useState(""),[X,v]=s.useState(""),[w,u]=s.useState(""),[M,Y]=s.useState(!1),[ne,F]=s.useState(!1),[W,B]=s.useState(""),[y,S]=s.useState(!1),[G,f]=s.useState(""),[Z,$]=s.useState(""),[K,O]=s.useState(""),[Q,V]=s.useState(!1),_=s.useRef(0),E=s.useRef(0),H=C,x=s.useMemo(()=>C.find(t=>t.id===D)||null,[C,D]),I=s.useMemo(()=>(x==null?void 0:x.comments.find(t=>t.id===w))||null,[x,w]);async function ee(t=c,n=""){const r=_.current+1;_.current=r;const i=!!n;i?(V(!0),$("")):(Y(!0),O(""),$("")),i||f("");try{const l=new URLSearchParams({author:t,limit:String(xe)});n&&l.set("cursor",n);const o=await z(`${A}?${l.toString()}`);if(r!==_.current)return;const h=(o.items||[]).map(T);O(String(o.next_cursor||o.nextCursor||"")),m(i?N=>{const L=new Set(N.map(J=>J.id));return[...N,...h.filter(J=>!L.has(J.id))]}:h)}catch(l){if(r!==_.current)return;const o=l instanceof Error?l.message:String(l);i?$(o):f(o),i||m([])}finally{r===_.current&&(Y(!1),V(!1))}}async function ie(t){const n=E.current+1;E.current=n,j(t),k(""),v(""),u(""),F(!0),B("");try{const r=await z(`${A}/${encodeURIComponent(t)}`);if(n!==E.current)return;const i=r.item?T(r.item):null;i&&m(l=>l.map(o=>o.id===i.id?i:o))}catch(r){if(n!==E.current)return;B(r instanceof Error?r.message:String(r)),r&&typeof r=="object"&&"status"in r&&r.status===404&&(m(i=>i.filter(l=>l.id!==t)),j(null))}finally{n===E.current&&F(!1)}}function U(){return g?(p(null),!0):D?(E.current+=1,j(null),k(""),v(""),u(""),F(!1),B(""),!0):!1}s.useEffect(()=>{if(d)return d.current=U,()=>{d.current===U&&(d.current=null)}},[d,g,D]),s.useEffect(()=>{m([]),O(""),$(""),f(""),ee(c)},[c]),s.useEffect(()=>{!w||!x||x.comments.some(t=>t.id===w)||u("")},[w,x]);function re(){U()||a()}function oe(t){p({id:t.id,author:t.author,title:t.title,emoji:t.emoji,content:t.content})}async function ce(){if(!g||y)return;const t=g.title.trim()||"没有标题的小纸条",n=g.emoji.trim()||"✦",r=g.content.trim();if(r){S(!0),f("");try{let i=null;if(g.id){const l=C.find(h=>h.id===g.id),o=await z(`${A}/${encodeURIComponent(g.id)}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({author:g.author,title:t,mood:n,content:r,base_updated_at:(l==null?void 0:l.updatedAt)||""})});i=o.item?T(o.item):null,i&&(i.author!==c?(b(i.author),m([i])):m(h=>h.map(N=>N.id===i.id?i:N)))}else{const l=await z(A,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({author:"xy",title:t,mood:n,content:r,client_request_id:R("exchange_diary")})});i=l.item?T(l.item):null,i&&(b(i.author),m(o=>[i,...o.filter(h=>h.id!==i.id)]),j(i.id))}p(null)}catch(i){f(i instanceof Error?i.message:String(i))}finally{S(!1)}}}async function se(t){if(!y){S(!0),f("");try{await z(`${A}/${encodeURIComponent(t)}`,{method:"DELETE"}),m(n=>n.filter(r=>r.id!==t)),j(null),k(""),v(""),u(""),p(null)}catch(n){f(n instanceof Error?n.message:String(n))}finally{S(!1)}}}async function de(t){if(y)return;const n=P.trim();if(!n)return;const r=X||R("exchange_diary_comment");X||v(r);const i=t.comments.some(o=>o.id===w)?w:"",l={author:"xy",content:n,client_request_id:r};i&&(l.reply_to_comment_id=i),S(!0),f("");try{const o=await z(`${A}/${encodeURIComponent(t.id)}/comments`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(l)}),h=o.item?T(o.item):null;h&&m(N=>N.map(L=>L.id===h.id?h:L)),k(""),v(""),u("")}catch(o){f(o instanceof Error?o.message:String(o))}finally{S(!1)}}return e.jsxs("div",{className:"exchange-diary-page",children:[e.jsx(fe,{}),e.jsxs("header",{className:"exchange-diary-header-lace",children:[e.jsx("button",{className:"exchange-diary-back",type:"button",onClick:re,"aria-label":"返回",children:e.jsx(le,{})}),e.jsxs("div",{className:"exchange-diary-toggle",role:"tablist","aria-label":"交换日记",children:[e.jsxs("button",{className:`exchange-diary-toggle-btn ${c==="du"?"active":""}`,type:"button",onClick:()=>b("du"),role:"tab","aria-selected":c==="du",children:[e.jsx(ue,{}),"渡的Diary"]}),e.jsx("button",{className:`exchange-diary-toggle-btn ${c==="xy"?"active":""}`,type:"button",onClick:()=>b("xy"),role:"tab","aria-selected":c==="xy",children:"我的Diary"})]})]}),e.jsxs("main",{className:"exchange-diary-timeline-container",children:[e.jsx("div",{className:"exchange-diary-timeline-line"}),G?e.jsx("div",{className:"exchange-diary-status error",children:G}):null,M?e.jsx("div",{className:"exchange-diary-status",children:"翻日记中..."}):null,!M&&!G&&H.length===0?e.jsx("div",{className:"exchange-diary-status",children:"还没有日记"}):null,H.map((t,n)=>e.jsxs("article",{className:`exchange-diary-entry ${n%2===0?"side-left":"side-right"} author-${t.author}`,children:[n<2?e.jsx("div",{className:"exchange-diary-star-ornament",style:n%2===0?{top:"-20px",left:"10%"}:{top:"0",right:"5%"},children:"★"}):null,e.jsx("button",{className:"exchange-diary-sticky-note",type:"button",onClick:()=>void ie(t.id),children:e.jsxs("div",{className:"exchange-diary-entry-header compact",children:[e.jsxs("div",{className:"exchange-diary-card-title-line",children:[e.jsx("span",{className:"exchange-diary-entry-title compact",children:t.title}),e.jsx("span",{className:"exchange-diary-entry-emoji compact",children:t.emoji})]}),e.jsx("span",{className:"exchange-diary-entry-time compact",children:t.createdAt})]})})]},t.id)),Z?e.jsx("div",{className:"exchange-diary-status inline error",children:Z}):null,!M&&K?e.jsx("button",{className:"exchange-diary-load-more",type:"button",onClick:()=>void ee(c,K),disabled:Q,children:Q?"翻页中...":"继续翻"}):null]}),e.jsx("button",{className:"exchange-diary-add-entry-btn",type:"button",onClick:()=>{b("xy"),p(me("xy"))},"aria-label":"写一条日记",children:e.jsx(ye,{})}),x?e.jsx("div",{className:"exchange-diary-overlay active",onClick:()=>{j(null),k(""),v(""),u("")},children:e.jsxs("div",{className:"exchange-diary-detail-card",onClick:t=>t.stopPropagation(),children:[e.jsxs("div",{className:"exchange-diary-entry-header",children:[e.jsx("span",{className:"exchange-diary-entry-title",children:x.title}),e.jsx("span",{className:"exchange-diary-entry-time",children:x.createdAt})]}),ne?e.jsx("div",{className:"exchange-diary-status inline",children:"翻这一页中..."}):null,W?e.jsx("div",{className:"exchange-diary-status inline error",children:W}):null,e.jsx("div",{className:"exchange-diary-entry-content detail",children:x.content}),e.jsxs("div",{className:"exchange-diary-entry-footer detail-footer",children:[e.jsx("span",{className:"exchange-diary-entry-emoji",children:x.emoji}),e.jsxs("span",{className:"exchange-diary-comment-count",children:[q(x.author),"写的"]})]}),e.jsxs("div",{className:"exchange-diary-comments-section",children:[e.jsxs("p",{className:"exchange-diary-comments-title",children:["Comments (",x.comments.length,")"]}),x.comments.map(t=>e.jsxs("div",{className:`exchange-diary-comment-row ${t.replyToCommentId?"reply":""}`,children:[e.jsxs("div",{className:"exchange-diary-comment-meta",children:[e.jsx("strong",{children:pe(t,x.comments)}),e.jsxs("div",{className:"exchange-diary-comment-tools",children:[t.createdAt?e.jsx("span",{children:t.createdAt}):null,e.jsx("button",{className:"exchange-diary-comment-reply-btn",type:"button",onClick:()=>u(t.id),disabled:y,children:"回复"})]})]}),e.jsx("div",{className:"exchange-diary-comment-content",children:t.content})]},t.id)),e.jsxs("div",{className:"exchange-diary-comment-box",children:[I?e.jsxs("div",{className:"exchange-diary-replying-to",children:[e.jsxs("span",{children:["回复 ",q(I.author),"：",he(I.content)]}),e.jsx("button",{type:"button",onClick:()=>u(""),disabled:y,children:"取消"})]}):null,e.jsx("textarea",{value:P,onChange:t=>{k(t.target.value),v("")},placeholder:I?"写一句回复...":"写一句评论...",rows:2,disabled:y}),e.jsx("button",{type:"button",onClick:()=>de(x),disabled:y||!P.trim(),children:I?"保存回复":"保存评论"})]})]}),e.jsxs("div",{className:"exchange-diary-actions",children:[e.jsx("button",{className:"exchange-diary-action-link",type:"button",onClick:()=>oe(x),children:"Edit"}),e.jsx("button",{className:"exchange-diary-action-link",type:"button",onClick:()=>se(x.id),disabled:y,children:"Delete"}),e.jsx("button",{className:"exchange-diary-action-link push-right",type:"button",onClick:()=>{j(null),k(""),v(""),u("")},children:"Close"})]})]})}):null,g?e.jsx("div",{className:"exchange-diary-overlay active",onClick:()=>p(null),children:e.jsxs("div",{className:"exchange-diary-detail-card editor",onClick:t=>t.stopPropagation(),children:[e.jsxs("div",{className:"exchange-diary-editor-row",children:[e.jsx("input",{className:"title-input",value:g.title,onChange:t=>p(n=>n&&{...n,title:t.target.value}),placeholder:"标题"}),e.jsxs("label",{className:"exchange-diary-emoji-field",children:[e.jsx("span",{children:"emoji"}),e.jsx("input",{className:"emoji-input",value:g.emoji,onChange:t=>p(n=>n&&{...n,emoji:t.target.value.slice(0,4)}),placeholder:"✦","aria-label":"emoji"})]})]}),g.id?e.jsxs("div",{className:"exchange-diary-author-switch",children:[e.jsx("button",{type:"button",className:g.author==="du"?"active":"",onClick:()=>p(t=>t&&{...t,author:"du"}),children:"渡"}),e.jsx("button",{type:"button",className:g.author==="xy"?"active":"",onClick:()=>p(t=>t&&{...t,author:"xy"}),children:"我"})]}):null,e.jsx("textarea",{className:"exchange-diary-editor-content",value:g.content,onChange:t=>p(n=>n&&{...n,content:t.target.value}),placeholder:"把今天想留下的事写在这里...",rows:8}),e.jsxs("div",{className:"exchange-diary-actions",children:[e.jsx("button",{className:"exchange-diary-action-link",type:"button",onClick:()=>p(null),children:"Cancel"}),e.jsx("button",{className:"exchange-diary-action-link push-right",type:"button",onClick:ce,disabled:y,children:"Save"})]})]})}):null]})}function ue(){return e.jsx("svg",{viewBox:"0 0 24 24","aria-hidden":"true",children:e.jsx("path",{d:"M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"})})}function ye(){return e.jsxs("svg",{viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"2",strokeLinecap:"round",strokeLinejoin:"round","aria-hidden":"true",children:[e.jsx("line",{x1:"12",y1:"5",x2:"12",y2:"19"}),e.jsx("line",{x1:"5",y1:"12",x2:"19",y2:"12"})]})}function fe(){return e.jsx("style",{children:`
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

      .exchange-diary-comment-row.reply {
        border-left: 2px solid rgba(203, 161, 145, 0.42);
      }

      .exchange-diary-comment-meta {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 4px;
        color: var(--text-main);
      }

      .exchange-diary-comment-meta strong {
        font-weight: 600;
      }

      .exchange-diary-comment-meta span {
        flex: 0 0 auto;
        color: var(--text-light);
        font-size: 11px;
      }

      .exchange-diary-comment-tools {
        flex: 0 0 auto;
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .exchange-diary-comment-reply-btn {
        border: none;
        background: transparent;
        padding: 0;
        color: var(--text-light);
        font-size: 11px;
        line-height: 1.2;
      }

      .exchange-diary-comment-content {
        line-height: 1.7;
      }

      .exchange-diary-comment-box {
        margin-top: 14px;
        display: grid;
        gap: 10px;
      }

      .exchange-diary-replying-to {
        min-width: 0;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        border-left: 2px solid rgba(203, 161, 145, 0.42);
        background: rgba(255,255,255,0.56);
        color: var(--text-light);
        padding: 7px 9px;
        font-size: 12px;
        line-height: 1.4;
      }

      .exchange-diary-replying-to span {
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
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

      .exchange-diary-comment-box .exchange-diary-replying-to button {
        flex: 0 0 auto;
        justify-self: auto;
        border: none;
        background: transparent;
        color: var(--text-light);
        padding: 0;
        font-size: 11px;
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
    `})}export{ve as ExchangeDiaryTab};
