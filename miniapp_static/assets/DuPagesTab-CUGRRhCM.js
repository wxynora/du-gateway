import{u as ne,r,b as E,j as e}from"./index-CgeB9pcu.js";function q(s){const t=s.updated_at||s.created_at||"",i=t?new Date(t).getTime():0;return Number.isFinite(i)?i:0}function S(s){return s.slice().sort((t,i)=>q(i)-q(t))}function L(s){return Array.isArray(s)?s.filter(t=>!!t&&typeof t=="object"&&typeof t.id=="string").map(t=>({...t,tags:Array.isArray(t.tags)?t.tags.map(i=>String(i||"").trim()).filter(Boolean):[]})):[]}function p(s){return String(s||"").trim()}function H(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}function V(s,t){const i=H(s||"页笺"),g=H(t||"").replace(/\n/g,"<br>");return`<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${i}</title>
  <style>
    body{margin:0;min-height:100vh;background:#FAF7F0;color:#2D2926;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.7;padding:32px}
    main{max-width:680px;margin:0 auto;background:white;padding:32px;box-shadow:0 10px 40px rgba(0,0,0,.08)}
    h1{font-family:Georgia,"Times New Roman",serif;font-size:32px;margin:0 0 20px}
    p{white-space:pre-wrap}
  </style>
</head>
<body><main><h1>${i}</h1><p>${g}</p></main></body>
</html>`}function re(s,t){return`rotate(${(Array.from(String(s.id||t)).reduce((d,w)=>d+w.charCodeAt(0),0)*13%8-4)/2}deg)`}function U({index:s}){const t=[{top:"16.1972%",left:"46.766%"},{top:"68.583%",left:"15.0092%"},{top:"10.46%",left:"7.20462%"}],i=t[s%t.length]||t[0];return e.jsx("div",{className:"ladybug",style:i,children:e.jsxs("svg",{viewBox:"0 0 24 24",fill:"var(--red)",children:[e.jsx("circle",{cx:"12",cy:"12",r:"8"}),e.jsx("circle",{cx:"12",cy:"8",r:"2",fill:"black"}),e.jsx("circle",{cx:"9",cy:"12",r:"1",fill:"black"}),e.jsx("circle",{cx:"15",cy:"12",r:"1",fill:"black"}),e.jsx("circle",{cx:"12",cy:"16",r:"1",fill:"black"})]})})}function O(){return e.jsx("svg",{width:"16",height:"16",viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"2",children:e.jsx("polyline",{points:"15 18 9 12 15 6"})})}function oe(){return e.jsxs("svg",{width:"14",height:"14",viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"3",strokeLinecap:"round",children:[e.jsx("line",{x1:"12",y1:"5",x2:"12",y2:"19"}),e.jsx("line",{x1:"5",y1:"12",x2:"19",y2:"12"})]})}function pe({onExit:s,backHandlerRef:t}){const i=ne(),[g,d]=r.useState("list"),[w,v]=r.useState([]),[h,y]=r.useState(""),[D,J]=r.useState(""),[X,G]=r.useState(!1),[P,j]=r.useState(!1),[M,k]=r.useState(""),[R,N]=r.useState(""),[W,C]=r.useState(""),[Q,T]=r.useState(""),[Y,z]=r.useState(""),f=r.useMemo(()=>w,[w]),c=r.useMemo(()=>f.find(a=>a.id===h)||null,[h,f]),A=r.useMemo(()=>{const a=D.trim().toLowerCase(),o=a?f.filter(n=>[n.title,n.description,...Array.isArray(n.tags)?n.tags:[]].map(l=>String(l||"").toLowerCase()).join(`
`).includes(a)):f;return S(o)},[D,f]),_=r.useCallback(async()=>{G(!0);try{const a=await E("/miniapp-api/du-pages?limit=160");if(!(a!=null&&a.ok))throw new Error((a==null?void 0:a.error)||"加载失败");v(S(L(a.pages)))}catch(a){console.warn("du pages preview fallback:",(a==null?void 0:a.message)||a),i(`页笺加载失败：${(a==null?void 0:a.message)||a}`)}finally{G(!1)}},[i]);r.useEffect(()=>{_()},[_]);const F=r.useCallback(()=>g==="preview"?(d("detail"),!0):g==="edit"?(d(h?"detail":"list"),!0):g==="detail"?(d("list"),!0):!1,[h,g]);r.useEffect(()=>{if(t)return t.current=F,()=>{t.current===F&&(t.current=null)}},[t,F]);function I(){d("list"),y(""),k(""),N(""),C(""),T(""),z("")}async function K(a){y(a),d("detail");try{const o=await E(`/miniapp-api/du-pages/${encodeURIComponent(a)}?include_html=1`),n=o==null?void 0:o.item;o!=null&&o.ok&&(n!=null&&n.id)&&v(x=>{const l=L(x),m=l.findIndex(B=>B.id===n.id);return m>=0?l[m]={...l[m],...n}:l.unshift(n),S(l)})}catch{}}function Z(){y(""),k(""),N(""),C(""),d("edit")}function ee(){c&&(k(p(c.title)),N((c.tags||[]).join(", ")),C(p(c.description)),d("edit"))}async function ae(){const a=M.trim(),o=W.trim(),n=R.split(",").map(x=>x.trim()).filter(Boolean);if(!a){i("Please add a title");return}j(!0);try{const x=h?{title:a,description:o,tags:n}:{title:a,description:o,tags:n,html:V(a,o),source:"miniapp",created_by:"xy"},l=await E(h?`/miniapp-api/du-pages/${encodeURIComponent(h)}`:"/miniapp-api/du-pages",{method:h?"PATCH":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(x)});if(!(l!=null&&l.ok)||!l.item)throw new Error((l==null?void 0:l.error)||"保存失败");const m=l.item;v(B=>{const b=L(B),$=b.findIndex(se=>se.id===m.id);return $>=0?b[$]={...b[$],...m}:b.unshift(m),S(b)}),y(m.id),d("detail"),i("页笺已保存")}catch(x){i(`保存失败：${(x==null?void 0:x.message)||x}`)}finally{j(!1)}}async function te(){if(c&&window.confirm("Delete this page note?")){j(!0);try{const a=await E(`/miniapp-api/du-pages/${encodeURIComponent(c.id)}`,{method:"DELETE"});if(!(a!=null&&a.ok))throw new Error((a==null?void 0:a.error)||"删除失败");v(o=>o.filter(n=>n.id!==c.id)),I(),i("页笺已删除")}catch(a){i(`删除失败：${(a==null?void 0:a.message)||a}`)}finally{j(!1)}}}function ie(){if(!c)return;if(c.url){z(c.url),T(""),d("preview");return}const a=p(c.html)||V(p(c.title)||"页笺",p(c.description));if(a){T(a),z(""),d("preview");return}{i("这张页笺还没有打开地址");return}}const u=c;return e.jsxs("div",{className:"du-pages-shell",children:[e.jsx("style",{children:`
        .du-pages-shell {
          --paper-bg: #FAF7F0;
          --graph-line: #E8E2D2;
          --ink: #2D2926;
          --red: #D23636;
          --green: #8BA341;
          --blue: #4A6D8C;
          --shadow: rgba(0,0,0,0.08);
          --gloss: linear-gradient(180deg, rgba(255,255,255,0.8) 0%, rgba(255,255,255,0) 50%, rgba(0,0,0,0.05) 100%);
          position: absolute;
          inset: 0;
          z-index: 30;
          overflow-x: hidden;
          overflow-y: auto;
          background-color: var(--paper-bg);
          background-image:
            linear-gradient(var(--graph-line) 1px, transparent 1px),
            linear-gradient(90deg, var(--graph-line) 1px, transparent 1px);
          background-size: 20px 20px;
          color: var(--ink);
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
          -webkit-tap-highlight-color: transparent;
        }
        .du-pages-shell * { box-sizing: border-box; }
        .du-pages-app-container {
          max-width: 500px;
          margin: 0 auto;
          min-height: 100%;
          position: relative;
          padding-bottom: 100px;
        }
        .du-pages-header {
          padding: calc(env(safe-area-inset-top, 0px) + 40px) 20px 20px;
          text-align: center;
          position: relative;
        }
        .du-pages-exit {
          position: absolute;
          left: 20px;
          top: calc(env(safe-area-inset-top, 0px) + 36px);
        }
        .du-pages-logo {
          font-family: 'Playfair Display', Georgia, serif;
          font-size: 32px;
          font-style: italic;
          color: var(--red);
          letter-spacing: -1px;
          position: relative;
          display: inline-block;
        }
        .du-pages-logo::after {
          content: '';
          position: absolute;
          bottom: -5px;
          left: 0;
          width: 100%;
          height: 8px;
          background: rgba(139, 163, 65, 0.2);
          z-index: -1;
        }
        .du-pages-search-tray {
          padding: 0 20px;
          margin-bottom: 30px;
        }
        .du-pages-search-input-wrapper {
          background: white;
          border: 1px solid #DCD5C5;
          padding: 8px 15px;
          border-radius: 4px;
          box-shadow: inset 0 2px 4px var(--shadow);
          display: flex;
          align-items: center;
        }
        .du-pages-search-input {
          border: none;
          background: transparent;
          width: 100%;
          font-family: 'Courier New', Courier, monospace;
          font-size: 14px;
          outline: none;
          color: var(--ink);
        }
        .du-pages-view {
          padding: 20px;
          animation: duPagesFadeIn 0.4s ease;
        }
        @keyframes duPagesFadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .du-pages-list-view { padding: 0; }
        .du-pages-collage-list {
          position: relative;
          padding: 20px;
          min-height: 400px;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 10px;
        }
        .du-pages-note-card {
          position: relative;
          background: white;
          padding: 16px 18px;
          box-shadow: 2px 5px 15px var(--shadow);
          width: min(82vw, 340px);
          min-height: 96px;
          transition: transform 0.3s ease, z-index 0.3s ease;
          cursor: pointer;
          word-wrap: break-word;
          border: 0;
          color: inherit;
          text-align: left;
          display: block;
        }
        .du-pages-note-card:nth-child(odd) { background-color: #FFF9E5; }
        .du-pages-note-card:nth-child(3n) { background-color: #F6E4E4; width: min(84vw, 352px); }
        .du-pages-note-card:nth-child(4n) { background-color: #E7F0DC; }
        .du-pages-note-card .tape {
          position: absolute;
          top: -10px;
          left: 50%;
          transform: translateX(-50%) rotate(-2deg);
          width: 60px;
          height: 20px;
          background: rgba(255, 255, 255, 0.4);
          backdrop-filter: blur(1px);
          border: 1px solid rgba(0,0,0,0.05);
          z-index: 2;
        }
        .du-pages-note-card h3 {
          font-size: 14px;
          margin: 0 0 8px;
          line-height: 1.2;
          font-family: 'Playfair Display', Georgia, serif;
        }
        .du-pages-note-card p {
          font-size: 11px;
          color: #666;
          line-height: 1.4;
          font-family: 'Courier New', monospace;
          display: -webkit-box;
          -webkit-line-clamp: 3;
          -webkit-box-orient: vertical;
          overflow: hidden;
          margin: 0;
        }
        .du-pages-tag-pill {
          display: inline-block;
          font-size: 9px;
          text-transform: uppercase;
          padding: 2px 6px;
          border: 0.5px solid currentColor;
          margin-top: 10px;
          letter-spacing: 1px;
        }
        .du-pages-floating-action {
          position: fixed;
          bottom: 30px;
          left: 50%;
          transform: translateX(-50%);
          display: flex;
          gap: 10px;
          z-index: 100;
        }
        .du-pages-btn-capsule {
          background: #fff;
          border-radius: 50px;
          padding: 10px 20px;
          border: 1px solid #ddd;
          box-shadow: 0 4px 10px rgba(0,0,0,0.1), inset 0 2px 2px white;
          font-size: 13px;
          font-weight: 600;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          background-image: var(--gloss);
          cursor: pointer;
          color: var(--ink);
          white-space: nowrap;
        }
        .du-pages-btn-capsule:active {
          transform: translateY(2px);
          box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .du-pages-btn-icon-round {
          width: 32px;
          height: 32px;
          background: #fff;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          border: 1px solid #ddd;
          box-shadow: 0 4px 10px rgba(0,0,0,0.1), inset 0 2px 2px white;
          background-image: var(--gloss);
          color: var(--ink);
        }
        .du-pages-detail-back { margin-bottom: 30px; }
        .du-pages-preview-view {
          position: absolute;
          inset: 0;
          display: flex;
          flex-direction: column;
          background: #FAF7F0;
        }
        .du-pages-preview-header {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: calc(env(safe-area-inset-top, 0px) + 14px) 16px 12px;
          border-bottom: 1px solid rgba(45,41,38,0.08);
          background: rgba(250,247,240,0.92);
          backdrop-filter: blur(10px);
          z-index: 2;
        }
        .du-pages-preview-title {
          min-width: 0;
          flex: 1;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-family: 'Playfair Display', Georgia, serif;
          font-size: 17px;
          font-weight: 700;
        }
        .du-pages-preview-frame {
          width: 100%;
          min-height: 0;
          flex: 1;
          border: 0;
          background: white;
        }
        .du-pages-detail-sheet {
          background: white;
          padding: 40px 30px;
          box-shadow: 0 10px 40px rgba(0,0,0,0.1);
          min-height: 60vh;
          position: relative;
        }
        .du-pages-detail-sheet::before {
          content: '';
          position: absolute;
          top: 0; left: 0; right: 0; height: 10px;
          background-image: radial-gradient(circle at 10px 10px, transparent 10px, white 10px);
          background-size: 20px 20px;
          transform: translateY(-10px);
        }
        .du-pages-detail-title {
          font-family: 'Playfair Display', Georgia, serif;
          font-size: 28px;
          margin: 0 0 20px;
          border-bottom: 1px solid #eee;
          padding-bottom: 10px;
          line-height: 1.16;
        }
        .du-pages-detail-content {
          font-family: 'Courier New', monospace;
          line-height: 1.6;
          color: #444;
          white-space: pre-wrap;
        }
        .du-pages-form-field { margin-bottom: 25px; }
        .du-pages-form-label {
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 2px;
          color: #999;
          margin-bottom: 8px;
          display: block;
        }
        .du-pages-form-input,
        .du-pages-form-textarea {
          width: 100%;
          border: none;
          border-bottom: 1px dashed #ccc;
          background: transparent;
          padding: 10px 0;
          font-family: inherit;
          font-size: 16px;
          outline: none;
          color: var(--ink);
        }
        .du-pages-form-textarea {
          min-height: 150px;
          resize: none;
        }
        .ladybug {
          position: absolute;
          width: 24px;
          height: 24px;
          pointer-events: none;
          z-index: 50;
        }
        .du-pages-empty-state {
          text-align: center;
          padding: 100px 20px;
          color: #BDB7AB;
        }
        .du-pages-empty-icon {
          font-size: 40px;
          margin-bottom: 20px;
          filter: grayscale(1);
          opacity: 0.5;
        }
        .du-pages-muted {
          margin-top: 10px;
        }
      `}),e.jsxs("div",{className:"du-pages-app-container",children:[g==="list"?e.jsxs("div",{className:"du-pages-view du-pages-list-view",children:[e.jsxs("header",{className:"du-pages-header",children:[e.jsx("button",{className:"du-pages-btn-icon-round du-pages-exit",onClick:s,"aria-label":"返回",children:e.jsx(O,{})}),e.jsx("div",{className:"du-pages-logo",children:"页笺"})]}),e.jsx("div",{className:"du-pages-search-tray",children:e.jsx("div",{className:"du-pages-search-input-wrapper",children:e.jsx("input",{type:"text",className:"du-pages-search-input",placeholder:"SEARCH NOTES...",value:D,onChange:a=>J(a.target.value)})})}),e.jsx("div",{className:"du-pages-collage-list",children:X&&!A.length?e.jsxs("div",{className:"du-pages-empty-state",children:[e.jsx("div",{className:"du-pages-empty-icon",children:"🍂"}),e.jsx("h2",{children:"页笺加载中"}),e.jsx("p",{className:"du-pages-muted",children:"The drawer is waking up."})]}):A.length?e.jsxs(e.Fragment,{children:[A.map((a,o)=>e.jsxs("button",{type:"button",className:"du-pages-note-card",style:{transform:re(a,o),zIndex:o},onClick:()=>void K(a.id),children:[e.jsx("div",{className:"tape"}),e.jsx("h3",{children:p(a.title)||"Untitled Page"}),e.jsx("p",{children:p(a.description)||"No description yet."}),(a.tags||[]).map(n=>e.jsx("span",{className:"du-pages-tag-pill",children:n},n))]},a.id)),e.jsx(U,{index:0}),e.jsx(U,{index:1}),e.jsx(U,{index:2})]}):e.jsxs("div",{className:"du-pages-empty-state",children:[e.jsx("div",{className:"du-pages-empty-icon",children:"🍂"}),e.jsx("h2",{children:"这里还没有页笺"}),e.jsx("p",{className:"du-pages-muted",children:'Tap "New Note" to start your collection.'})]})}),e.jsx("div",{className:"du-pages-floating-action",children:e.jsxs("button",{className:"du-pages-btn-capsule",onClick:Z,children:[e.jsx(oe,{}),"NEW NOTE"]})})]}):null,g==="detail"&&u?e.jsxs("div",{className:"du-pages-view",children:[e.jsx("div",{className:"du-pages-detail-back",children:e.jsx("button",{className:"du-pages-btn-icon-round",onClick:I,"aria-label":"返回列表",children:e.jsx(O,{})})}),e.jsxs("div",{className:"du-pages-detail-sheet",children:[e.jsxs("h1",{className:"du-pages-detail-title",children:[p(u.emoji)?`${p(u.emoji)} `:"",p(u.title)||"Untitled Page"]}),e.jsx("div",{style:{marginBottom:20},children:(u.tags||[]).map(a=>e.jsx("span",{className:"du-pages-tag-pill",children:a},a))}),e.jsx("div",{className:"du-pages-detail-content",children:p(u.description)||"No description yet."})]}),e.jsxs("div",{className:"du-pages-floating-action",children:[e.jsx("button",{className:"du-pages-btn-capsule",onClick:ie,children:"OPEN"}),e.jsx("button",{className:"du-pages-btn-capsule",onClick:ee,children:"EDIT"}),e.jsx("button",{className:"du-pages-btn-capsule",style:{color:"var(--red)"},disabled:P,onClick:()=>void te(),children:"DELETE"})]})]}):null,g==="edit"?e.jsxs("div",{className:"du-pages-view",children:[e.jsxs("div",{className:"du-pages-detail-sheet",style:{paddingTop:20},children:[e.jsxs("div",{className:"du-pages-form-field",children:[e.jsx("label",{className:"du-pages-form-label",children:"TITLE"}),e.jsx("input",{type:"text",className:"du-pages-form-input",placeholder:"What's on your mind?",value:M,onChange:a=>k(a.target.value)})]}),e.jsxs("div",{className:"du-pages-form-field",children:[e.jsx("label",{className:"du-pages-form-label",children:"TAGS (COMMA SEPARATED)"}),e.jsx("input",{type:"text",className:"du-pages-form-input",placeholder:"design, thoughts, links",value:R,onChange:a=>N(a.target.value)})]}),e.jsxs("div",{className:"du-pages-form-field",children:[e.jsx("label",{className:"du-pages-form-label",children:"DESCRIPTION"}),e.jsx("textarea",{className:"du-pages-form-textarea",placeholder:"Paste link or write note here...",value:W,onChange:a=>C(a.target.value)})]})]}),e.jsxs("div",{className:"du-pages-floating-action",children:[e.jsx("button",{className:"du-pages-btn-capsule",disabled:P,onClick:()=>void ae(),children:P?"SAVING...":"SAVE NOTE"}),e.jsx("button",{className:"du-pages-btn-capsule",onClick:h?()=>d("detail"):I,children:"CANCEL"})]})]}):null,g==="preview"&&u?e.jsxs("div",{className:"du-pages-preview-view",children:[e.jsxs("div",{className:"du-pages-preview-header",children:[e.jsx("button",{className:"du-pages-btn-icon-round",onClick:()=>d("detail"),"aria-label":"返回页笺",children:e.jsx(O,{})}),e.jsxs("div",{className:"du-pages-preview-title",children:[p(u.emoji)?`${p(u.emoji)} `:"",p(u.title)||"Untitled Page"]})]}),e.jsx("iframe",{className:"du-pages-preview-frame",title:p(u.title)||"页笺预览",src:Y||void 0,srcDoc:Y?void 0:Q,sandbox:"allow-scripts allow-forms allow-popups allow-modals"})]}):null]})]})}export{pe as DuPagesTab};
