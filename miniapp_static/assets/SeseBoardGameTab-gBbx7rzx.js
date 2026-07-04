import{u as Ve,r,j as a,C as He,M as Ke,S as We,b as Re}from"./index-3WuSoq8D.js";const Se=["xinyue","du"],Ce={xinyue:"我",du:"渡"},Ze={xinyue:0,du:0};function I(s){return new Promise(t=>window.setTimeout(t,s))}function v(s){return String(s||"").replace(/小玥/g,"我")}function L(s){return String(s||"")}function M(s){return`${s}-${Date.now()}-${Math.random().toString(36).slice(2,8)}`}function Q(s,t){const n=Math.floor(Number(s||0));return Math.max(1,Math.min(t,n||1))}function $e(s,t){const n=Math.floor(Number(s||0));return Math.max(0,Math.min(t,n||0))}function Qe(s,t){const n=[];for(let p=1;p<=s;p+=t){const w=Array.from({length:Math.min(t,s-p+1)},(_,c)=>p+c);n.length%2===1&&w.reverse(),n.push(w)}return n.reverse().flat()}function Xe(s,t,n){if(t===1)return"start";if(t===n)return"end";if(!s)return"empty";const p=`${s.kind||""} ${s.slot||""}`.toLowerCase();return/swap/.test(p)?"swap":/move|back|forward/.test(p)?"move":/lock|pause|item/.test(p)?"item":/clear/.test(p)?"clear":/extend|time/.test(p)?"time":/limit/.test(p)?"limit":/place/.test(p)?"place":/pose/.test(p)?"pose":/theme/.test(p)?"theme":"task"}function et(s){return s==="start"?"🚩":s==="end"?"🏆":s==="place"?"🏫":s==="item"?"🎁":s==="move"?"⏪":s==="swap"?"🔄":s==="clear"?"✨":s==="time"?"⏳":s==="limit"?"🚫":s==="pose"?"◇":s==="theme"?"🚩":s==="task"?"📸":""}function tt(s,t,n){return t===1?"起点":t===n?"终点":v((s==null?void 0:s.name)||"空")}function st(s){const t=v(s).match(/(我|渡)掷出\s*(\d+)，从\s*(\d+)\s*走到\s*(\d+)/);return t?{actor:t[1]==="渡"?"du":"xinyue",dice:Number(t[2]||1),from:Number(t[3]||0),to:Number(t[4]||0)}:null}function at(s){const t=v(s).split(`
`).map(p=>p.trim()).find(p=>/^第\s*\d+\s*格：/.test(p));if(!t)return null;const n=t.match(/^第\s*(\d+)\s*格：([^，。]+)/);return{position:Number((n==null?void 0:n[1])||0),title:(n==null?void 0:n[2])||"格子事件",text:t}}function it(s){const t=String(s.duration_type||"");return t==="actions"?`剩余 ${Math.max(0,Number(s.remaining_actions||0))} 次行动`:t==="minutes"?`${Math.max(1,Number(s.minutes||0))} 分钟`:t==="until_finish"?"到终点":t==="until_clear"?"待解除":""}function Me(s){return(s||[]).some(t=>t.blocks_action&&Number(t.remaining_actions||0)>0)}function rt(s){const t=[/^(我|渡)掷出\s*\d+/,/^第\s*\d+\s*格：/,/^下一次行动：/,/行动权/,/到达终点/,/^新局已开始。?$/,/^本局已结束。?$/];return v(s).split(`
`).map(n=>n.trim()).filter(n=>n&&t.some(p=>p.test(n))).slice(0,4)}function nt(s){return String(s).split(/\r?\n/).map(n=>n.trim()).find(Boolean)==="【掷骰】"}async function U(s){const t=await Re("/miniapp-api/game-tools/private_board",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:s,save_id:"default"})});if(!(t!=null&&t.ok))throw new Error((t==null?void 0:t.error)||"走格棋命令失败");return t}async function Pe(s){var n;const t=await Re("/miniapp-api/game-tools/private_board/sync-du",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({save_id:"default",mode:s.mode,message:s.message||"",roll_text:s.rollText||""})});if(!(t!=null&&t.ok))throw new Error((t==null?void 0:t.error)||((n=t==null?void 0:t.wakeup)==null?void 0:n.error)||"游戏内交流失败");return t}function ot(s){return!!(s&&s.turn_actor==="du"&&!s.game_over)}function pt({onBack:s}){var ue,fe,ge,he,be,me,we,ye;const t=Ve(),n=r.useRef(null),p=r.useRef(!1),w=r.useRef(null),_=r.useRef(null),[c,P]=r.useState(null),[T,q]=r.useState(Ze),[X,G]=r.useState(1),[b,j]=r.useState(!1),[De,ee]=r.useState(!1),[m,te]=r.useState(!1),[Ee,F]=r.useState(null),[R,D]=r.useState(null),[S,J]=r.useState(!1),[se,ae]=r.useState(0),[E,ie]=r.useState(""),[N,A]=r.useState(!1),[re,Ae]=r.useState([{id:"system-ready",speaker:"system",text:"游戏内交流在这里。渡的第一行是【掷骰】时，棋盘才会执行他的行动。"}]),x=(c==null?void 0:c.state)||{},f=Math.max(12,Math.min(80,Number(x.board_size||36))),V=f<=36?6:8,H=x.turn_actor==="du"?"du":"xinyue",C=!!(x.game_over||c!=null&&c.game_over),O=H==="du"&&!C;r.useLayoutEffect(()=>{n.current&&(n.current.scrollTop=0)},[]),r.useEffect(()=>{p.current=S,S&&ae(0)},[S]),r.useEffect(()=>{S&&window.setTimeout(()=>{var e;return(e=w.current)==null?void 0:e.scrollIntoView({block:"end"})},40)},[re.length,S,N]);const k=r.useCallback((e,o=!1)=>{Ae(l=>[...l,e]),o&&!p.current&&ae(l=>Math.min(9,l+1))},[]),ne=r.useMemo(()=>{const e=new Map;for(const o of x.cell_events||[]){const l=Number((o==null?void 0:o.position)||0);l>0&&e.set(l,o)}return e},[x.cell_events]),Oe=r.useMemo(()=>Qe(f,V).map(e=>{const o=ne.get(e),l=Xe(o,e,f);return{position:e,event:o,kind:l,icon:et(l),name:tt(o,e,f)}}),[f,V,ne]),g=r.useCallback(e=>{var o,l,u,i;P(e),q({xinyue:Number(((l=(o=e.state)==null?void 0:o.positions)==null?void 0:l.xinyue)||0),du:Number(((i=(u=e.state)==null?void 0:u.positions)==null?void 0:i.du)||0)})},[]),oe=r.useCallback(async()=>{j(!0);try{const e=await U("status");g(e)}catch(e){t(`加载涩涩走格棋失败：${(e==null?void 0:e.message)||e}`)}finally{j(!1)}},[g,t]);r.useEffect(()=>{oe()},[oe]);const le=r.useCallback(async e=>{ee(!0);for(let o=0;o<12;o+=1)G(Math.floor(Math.random()*6)+1),await I(58);G(Math.max(1,Math.min(6,e||1))),ee(!1)},[]),K=r.useCallback(async(e,o,l,u)=>{const i=Number(l||0),d=Number(u||0);if(i===d){e[o]=d,q({...e}),F(Q(d,f)),await I(120);return}const $=d>i?1:-1;for(let z=i+$;$>0?z<=d:z>=d;z+=$)e[o]=z,q({...e}),F(Q(z,f)),await I(145)},[f]),Be=r.useCallback(async()=>{if(!(b||m)){j(!0),D(null);try{const e=await U("new_game");G(1),g(e)}catch(e){t(`开新局失败：${(e==null?void 0:e.message)||e}`)}finally{j(!1)}}},[m,g,b,t]);r.useCallback(async()=>{if(!(b||m)){j(!0);try{const e=await U("end_game");g(e)}catch(e){t(`结束本局失败：${(e==null?void 0:e.message)||e}`)}finally{j(!1)}}},[m,g,b,t]);const B=r.useCallback(async(e,o)=>{var u;const l=e.trim()||"我看到了。";k({id:M("du"),speaker:"du",text:l},!0),ot(o)&&nt(l)&&(await I(260),k({id:M("system"),speaker:"system",text:"渡第一行发出【掷骰】，已执行他的行动。"},!0),await((u=_.current)==null?void 0:u.call(_,{notifyAfterUserRoll:!1})))},[k]),pe=r.useCallback(async e=>{var l,u;const o=L(e.text||e.du_text||e.player_text||"").trim();k({id:M("system"),speaker:"system",text:"已把这次掷骰结果和当前棋局发给渡。"},!0),A(!0);try{const i=await Pe({mode:"roll_result",message:"小玥刚掷完骰子。",rollText:o});i.state&&g({ok:!0,state:i.state,player_text:i.player_text||e.player_text||""});const d=L(i.reply_text||((l=i.wakeup)==null?void 0:l.reply_text)||i.reply_preview||((u=i.wakeup)==null?void 0:u.reply_preview)||"").trim();await B(d,i.state||e.state)}catch(i){const d=String((i==null?void 0:i.message)||i||"同步失败");k({id:M("system"),speaker:"system",text:`自动同步失败：${d}`},!0),t(`自动同步给渡失败：${d}`)}finally{A(!1)}},[k,g,B,t]),W=r.useCallback(async(e={})=>{var i,d,$,z,ve,ke,je;if(b||m||C)return;let o=null;j(!0),te(!0),D(null);const u={...{xinyue:Number(((i=x.positions)==null?void 0:i.xinyue)||0),du:Number(((d=x.positions)==null?void 0:d.du)||0)}};try{const h=await U("roll"),y=st(h.player_text||"");await le((y==null?void 0:y.dice)||Math.floor(Math.random()*6)+1),y&&await K(u,y.actor,y.from,y.to);const Je={xinyue:Number(((z=($=h.state)==null?void 0:$.positions)==null?void 0:z.xinyue)||0),du:Number(((ke=(ve=h.state)==null?void 0:ve.positions)==null?void 0:ke.du)||0)};for(const Z of Se){const ze=Number(u[Z]||0),_e=Number(Je[Z]||0);ze!==_e&&await K(u,Z,ze,_e)}g(h);const Ne=at(h.player_text||"");Ne&&D(Ne),e.notifyAfterUserRoll!==!1&&(y==null?void 0:y.actor)==="xinyue"&&!((je=h.state)!=null&&je.game_over)&&(o=h)}catch(h){t(`掷骰失败：${(h==null?void 0:h.message)||h}`)}finally{j(!1),te(!1),window.setTimeout(()=>F(null),260)}o&&await pe(o)},[K,le,m,g,b,C,pe,x.positions,t]);r.useEffect(()=>{_.current=W},[W]);const Ie=r.useCallback(async()=>{var l,u;if(N||b||m||!(c!=null&&c.state))return;const e=E.trim();if(!e)return;const o={id:M("me"),speaker:"xinyue",text:e};ie(""),k(o),A(!0);try{const i=await Pe({mode:"chat",message:e});i.state&&g({ok:!0,state:i.state,player_text:i.player_text||c.player_text||""});const d=L(i.reply_text||((l=i.wakeup)==null?void 0:l.reply_text)||i.reply_preview||((u=i.wakeup)==null?void 0:u.reply_preview)||"").trim();await B(d,i.state||c.state)}catch(i){const d=String((i==null?void 0:i.message)||i||"同步失败");k({id:M("system"),speaker:"system",text:`交流失败：${d}`}),t(`游戏内交流失败：${d}`)}finally{A(!1)}},[m,k,g,b,E,N,c,B,t]),Le=v(((ue=x.theme_profile)==null?void 0:ue.theme)||"未触发"),Ue=v(((fe=x.theme_profile)==null?void 0:fe.direction_label)||"待定"),Ye=$e((ge=x.positions)==null?void 0:ge.xinyue,f),qe=$e((he=x.positions)==null?void 0:he.du,f),ce=x.winner?Ce[x.winner]:"",de=rt((c==null?void 0:c.player_text)||""),Ge=b||m||N||!(c!=null&&c.state)||O,xe=N||b||m||!(c!=null&&c.state),Fe={xinyue:Me((be=x.statuses)==null?void 0:be.xinyue),du:Me((me=x.statuses)==null?void 0:me.du)};return a.jsxs("div",{className:"sese-game",ref:n,children:[a.jsxs("div",{className:"sese-header",children:[a.jsx("button",{className:"sese-back",type:"button",onClick:s,"aria-label":"返回游戏",children:a.jsx(He,{})}),a.jsxs("button",{className:"sese-chat-entry",type:"button",onClick:()=>J(!0),"aria-label":"游戏内交流",children:[a.jsx(Ke,{}),se?a.jsx("span",{children:se}):null]}),a.jsx("div",{className:"sese-header-title",children:"涩涩走格棋"}),a.jsxs("div",{className:"sese-game-status-bar",children:[a.jsx(Y,{label:"主题",value:Le}),a.jsx(Y,{label:"主导方",value:Ue}),a.jsx(Y,{label:"我 进度",value:`${String(Ye).padStart(2,"0")} / ${f}`}),a.jsx(Y,{label:"渡 进度",value:`${String(qe).padStart(2,"0")} / ${f}`}),a.jsx("div",{className:"sese-turn-indicator",children:C&&ce?`${ce} 到达终点`:O?"等待 渡 行动...":"轮到 我 行动"})]})]}),a.jsx("section",{className:"sese-board-container","aria-label":"走格棋盘",children:a.jsx("div",{className:"sese-board",style:{gridTemplateColumns:`repeat(${V}, minmax(0, 1fr))`},children:Oe.map(e=>{const o=Se.filter(l=>Q(T[l],f)===e.position);return a.jsxs("div",{className:`sese-tile sese-tile-${e.kind} ${Ee===e.position?"is-active":""}`,children:[a.jsx("div",{className:"sese-tile-number",children:e.position}),a.jsx("div",{className:"sese-tile-icon",children:e.icon}),a.jsx("div",{className:"sese-tile-name",children:e.name}),a.jsx("div",{className:"sese-piece-stack",children:o.map(l=>a.jsx("span",{className:`sese-piece ${l==="xinyue"?"sese-piece-me":"sese-piece-du"} ${Fe[l]?"paused":""}`,children:Ce[l]},l))})]},e.position)})})}),a.jsxs("section",{className:"sese-controls",children:[a.jsxs("div",{className:"sese-player-states",children:[a.jsx(Te,{actor:"xinyue",statuses:((we=x.statuses)==null?void 0:we.xinyue)||[],active:H==="xinyue"}),a.jsx(Te,{actor:"du",statuses:((ye=x.statuses)==null?void 0:ye.du)||[],active:H==="du"})]}),a.jsxs("div",{className:"sese-action-area",children:[a.jsx("div",{className:`sese-dice ${De?"rolling":""}`,"aria-label":`骰子 ${X}`,children:X}),a.jsx("button",{className:"sese-roll-button",type:"button",disabled:Ge,onClick:C?Be:()=>void W({notifyAfterUserRoll:!0}),children:C?"开新局":O?"等渡掷骰":b||m?"移动中":N?"等渡回应":"掷骰子"})]}),a.jsx("div",{className:"sese-history",children:de.length?`最近：${de[0]}`:"最近：等待第一次掷骰"})]}),S?a.jsx("div",{className:"sese-chat-mask",role:"dialog","aria-modal":"true","aria-label":"游戏内交流",onClick:()=>J(!1),children:a.jsxs("div",{className:"sese-chat-panel",onClick:e=>e.stopPropagation(),children:[a.jsxs("div",{className:"sese-chat-head",children:[a.jsxs("div",{children:[a.jsx("strong",{children:"游戏内交流"}),a.jsx("span",{children:O?"渡第一行【掷骰】才算指令":"当前轮到我行动"})]}),a.jsx("button",{type:"button",onClick:()=>J(!1),"aria-label":"关闭交流",children:"×"})]}),a.jsxs("div",{className:"sese-chat-list",children:[re.map(e=>a.jsxs("div",{className:`sese-chat-message ${e.speaker}`,children:[a.jsx("span",{children:e.speaker==="xinyue"?"我":e.speaker==="du"?"渡":"系统"}),a.jsx("p",{children:L(e.text)})]},e.id)),N?a.jsxs("div",{className:"sese-chat-message du pending",children:[a.jsx("span",{children:"渡"}),a.jsx("p",{children:"正在回复..."})]}):null,a.jsx("div",{ref:w})]}),a.jsxs("form",{className:"sese-chat-form",onSubmit:e=>{e.preventDefault(),Ie()},children:[a.jsx("input",{value:E,disabled:xe,placeholder:"和渡说一句游戏内的话",onChange:e=>ie(e.target.value)}),a.jsx("button",{type:"submit",disabled:xe||!E.trim(),"aria-label":N?"发送中":"发送",children:a.jsx(We,{})})]})]})}):null,R?a.jsx("div",{className:"sese-popup-mask",role:"dialog","aria-modal":"true",children:a.jsxs("div",{className:"sese-popup",children:[a.jsxs("div",{className:"sese-popup-kicker",children:["第 ",R.position," 格"]}),a.jsx("h2",{children:v(R.title)}),a.jsx("p",{children:v(R.text)}),a.jsx("button",{type:"button",onClick:()=>D(null),children:"确 认"})]})}):null,a.jsx("style",{children:`
        .sese-game {
          --primary-pink: #f8bbd0;
          --soft-lavender: #f3e5f5;
          --accent-yellow: #fff9c4;
          --accent-mint: #e0f2f1;
          --accent-blue: #e1f5fe;
          --text-main: #884d8a;
          --text-light: #ba68c8;
          --bg-page: #fce4ec;
          --card-white: rgba(255, 255, 255, 0.86);
          position: absolute;
          inset: 0;
          z-index: 34;
          min-height: 100dvh;
          overflow-y: auto;
          background:
            linear-gradient(180deg, rgba(255,255,255,0.62) 0, rgba(255,255,255,0) 210px),
            var(--bg-page);
          color: var(--text-main);
          font-family: "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          padding: calc(env(safe-area-inset-top, 0px) + 10px) 14px calc(env(safe-area-inset-bottom, 0px) + 22px);
        }
        .sese-header {
          display: flex;
          align-items: center;
          gap: 10px;
          margin: 0 auto 12px;
          max-width: 720px;
        }
        .sese-back,
        .sese-header-button,
        .sese-quiet-button {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          border: 0;
          border-radius: 999px;
          background: rgba(255, 255, 255, 0.82);
          color: var(--text-main);
          box-shadow: 0 8px 18px rgba(136, 77, 138, 0.14);
          transition: transform 140ms ease, opacity 140ms ease;
        }
        .sese-back {
          width: 42px;
          height: 42px;
          flex: 0 0 42px;
        }
        .sese-header-button {
          min-width: 58px;
          height: 36px;
          padding: 0 14px;
          font-size: 13px;
          font-weight: 800;
        }
        .sese-back:active,
        .sese-header-button:active,
        .sese-roll-button:active,
        .sese-quiet-button:active {
          transform: scale(0.96);
        }
        .sese-header-button:disabled,
        .sese-roll-button:disabled,
        .sese-quiet-button:disabled {
          opacity: 0.54;
        }
        .sese-title-block {
          min-width: 0;
          flex: 1;
          text-align: center;
        }
        .sese-title-block h1 {
          margin: 0;
          color: var(--text-main);
          font-size: 24px;
          font-weight: 900;
          line-height: 1.12;
          text-shadow: 0 2px 0 rgba(255, 255, 255, 0.82);
        }
        .sese-title-block p {
          margin: 4px 0 0;
          color: var(--text-light);
          font-size: 12px;
          font-weight: 800;
          line-height: 1.2;
        }
        .sese-status-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 8px;
          margin: 0 auto 12px;
          max-width: 720px;
        }
        .sese-pill {
          min-height: 54px;
          overflow: hidden;
          border: 1px solid rgba(255, 255, 255, 0.72);
          border-radius: 18px;
          background: var(--card-white);
          padding: 8px 10px;
          box-shadow: 0 10px 22px rgba(136, 77, 138, 0.1);
        }
        .sese-pill span {
          display: block;
          color: var(--text-light);
          font-size: 10px;
          font-weight: 900;
          line-height: 1.1;
        }
        .sese-pill strong {
          display: block;
          margin-top: 4px;
          overflow: hidden;
          color: var(--text-main);
          font-size: 13px;
          font-weight: 900;
          line-height: 1.18;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .sese-board-wrap {
          margin: 0 auto;
          max-width: 720px;
          border: 6px solid rgba(255, 255, 255, 0.84);
          border-radius: 26px;
          background: rgba(255, 255, 255, 0.62);
          padding: 8px;
          box-shadow: 0 18px 38px rgba(136, 77, 138, 0.16);
        }
        .sese-board {
          display: grid;
          gap: 6px;
          width: 100%;
        }
        .sese-tile {
          position: relative;
          display: flex;
          aspect-ratio: 1;
          min-width: 0;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          overflow: hidden;
          border: 1px solid rgba(255, 255, 255, 0.8);
          border-radius: 14px;
          background: rgba(255, 255, 255, 0.8);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.9), 0 5px 10px rgba(136, 77, 138, 0.08);
          transition: transform 170ms ease, box-shadow 170ms ease;
        }
        .sese-tile.is-active {
          transform: translateY(-2px) scale(1.03);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.96), 0 10px 20px rgba(136, 77, 138, 0.2);
        }
        .sese-tile-start { background: #e0f2f1; }
        .sese-tile-end { background: #fff9c4; }
        .sese-tile-place { background: #e1f5fe; }
        .sese-tile-item { background: #f3e5f5; }
        .sese-tile-task { background: #f8bbd0; }
        .sese-tile-move { background: #fff9c4; }
        .sese-tile-swap { background: #e0f2f1; }
        .sese-tile-clear { background: #ffffff; }
        .sese-tile-time { background: #fff7dd; }
        .sese-tile-limit { background: #ffe3ea; }
        .sese-tile-pose { background: #edf7ff; }
        .sese-tile-theme { background: #f6e9ff; }
        .sese-tile-number {
          position: absolute;
          left: 6px;
          top: 5px;
          color: rgba(136, 77, 138, 0.46);
          font-size: 9px;
          font-weight: 900;
          line-height: 1;
        }
        .sese-tile-icon {
          height: 18px;
          color: var(--text-main);
          font-size: 15px;
          font-weight: 900;
          line-height: 18px;
        }
        .sese-tile-name {
          display: -webkit-box;
          width: calc(100% - 8px);
          min-height: 20px;
          overflow: hidden;
          -webkit-box-orient: vertical;
          -webkit-line-clamp: 2;
          color: var(--text-main);
          font-size: 9px;
          font-weight: 900;
          line-height: 10px;
          text-align: center;
        }
        .sese-piece-stack {
          position: absolute;
          inset: auto 4px 4px;
          display: flex;
          justify-content: center;
          gap: 3px;
          min-height: 17px;
          pointer-events: none;
        }
        .sese-piece {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 24px;
          height: 16px;
          border: 2px solid #ffffff;
          border-radius: 999px;
          font-size: 10px;
          font-weight: 900;
          line-height: 1;
          box-shadow: 0 5px 10px rgba(68, 42, 77, 0.18);
          animation: sesePiecePop 180ms ease both;
        }
        .sese-piece-xinyue {
          background: #ff6f91;
          color: #ffffff;
        }
        .sese-piece-du {
          background: #7bc9ff;
          color: #ffffff;
        }
        .sese-control-panel {
          margin: 12px auto 0;
          max-width: 720px;
          border: 1px solid rgba(255, 255, 255, 0.78);
          border-radius: 26px;
          background: var(--card-white);
          padding: 12px;
          box-shadow: 0 16px 36px rgba(136, 77, 138, 0.12);
        }
        .sese-player-row {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 10px;
        }
        .sese-player-card {
          min-height: 98px;
          border-radius: 20px;
          padding: 10px;
          background: rgba(255, 255, 255, 0.74);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.78);
        }
        .sese-player-card h2 {
          margin: 0 0 7px;
          color: var(--text-main);
          font-size: 14px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-status-list {
          display: flex;
          flex-direction: column;
          gap: 5px;
        }
        .sese-status-item,
        .sese-status-empty {
          border-radius: 12px;
          background: rgba(248, 187, 208, 0.22);
          padding: 6px 7px;
          color: #7c4a80;
          font-size: 11px;
          font-weight: 800;
          line-height: 1.25;
        }
        .sese-status-item span {
          display: block;
          margin-top: 2px;
          color: rgba(124, 74, 128, 0.62);
          font-size: 10px;
          font-weight: 800;
        }
        .sese-roll-row {
          display: grid;
          grid-template-columns: 70px minmax(0, 1fr) 68px;
          gap: 10px;
          align-items: center;
          margin-top: 12px;
        }
        .sese-dice {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 70px;
          height: 70px;
          border: 3px solid #ffffff;
          border-radius: 20px;
          background: #ffffff;
          color: var(--text-main);
          font-size: 42px;
          line-height: 1;
          box-shadow: 0 12px 24px rgba(136, 77, 138, 0.16);
        }
        .sese-dice.rolling {
          animation: seseDiceRoll 120ms linear infinite;
        }
        .sese-roll-button {
          min-width: 0;
          height: 54px;
          border: 0;
          border-radius: 18px;
          background: linear-gradient(135deg, #f48fb1, #ba68c8);
          color: #ffffff;
          font-size: 16px;
          font-weight: 900;
          box-shadow: 0 12px 24px rgba(186, 104, 200, 0.24);
          transition: transform 140ms ease, opacity 140ms ease;
        }
        .sese-quiet-button {
          height: 48px;
          padding: 0 10px;
          font-size: 13px;
          font-weight: 900;
        }
        .sese-log {
          display: flex;
          flex-direction: column;
          gap: 5px;
          margin-top: 12px;
          border-radius: 18px;
          background: rgba(255, 255, 255, 0.62);
          padding: 10px;
        }
        .sese-log p {
          margin: 0;
          color: #7b5a7f;
          font-size: 12px;
          font-weight: 700;
          line-height: 1.35;
        }
        .sese-popup-mask {
          position: fixed;
          inset: 0;
          z-index: 60;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(73, 34, 81, 0.28);
          padding: 24px;
          backdrop-filter: blur(8px);
        }
        .sese-popup {
          width: min(340px, 100%);
          border: 1px solid rgba(255, 255, 255, 0.82);
          border-radius: 28px;
          background: rgba(255, 255, 255, 0.95);
          padding: 20px;
          text-align: center;
          box-shadow: 0 22px 48px rgba(73, 34, 81, 0.24);
        }
        .sese-popup-kicker {
          display: inline-flex;
          border-radius: 999px;
          background: #f3e5f5;
          padding: 5px 10px;
          color: var(--text-light);
          font-size: 11px;
          font-weight: 900;
          line-height: 1;
        }
        .sese-popup h2 {
          margin: 12px 0 8px;
          color: var(--text-main);
          font-size: 20px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-popup p {
          margin: 0;
          color: #7b5a7f;
          font-size: 13px;
          font-weight: 700;
          line-height: 1.55;
          text-align: left;
        }
        .sese-popup button {
          width: 100%;
          height: 44px;
          margin-top: 16px;
          border: 0;
          border-radius: 16px;
          background: linear-gradient(135deg, #f48fb1, #ba68c8);
          color: #ffffff;
          font-size: 14px;
          font-weight: 900;
        }
        @keyframes seseDiceRoll {
          0% { transform: rotate(-8deg) scale(1); }
          50% { transform: rotate(8deg) scale(1.06); }
          100% { transform: rotate(-8deg) scale(1); }
        }
        @keyframes sesePiecePop {
          from { transform: translateY(4px) scale(0.82); opacity: 0.6; }
          to { transform: translateY(0) scale(1); opacity: 1; }
        }
        @media (max-width: 380px) {
          .sese-game {
            padding-left: 10px;
            padding-right: 10px;
          }
          .sese-board {
            gap: 4px;
          }
          .sese-board-wrap {
            border-width: 5px;
            padding: 6px;
          }
          .sese-tile {
            border-radius: 11px;
          }
          .sese-piece {
            width: 21px;
            height: 15px;
          }
          .sese-roll-row {
            grid-template-columns: 62px minmax(0, 1fr) 58px;
          }
          .sese-dice {
            width: 62px;
            height: 62px;
          }
        }
        .sese-game {
          --card-white: rgba(255, 255, 255, 0.85);
          --radius-lg: 24px;
          --radius-md: 16px;
          --shadow-soft: 0 4px 12px rgba(233, 30, 99, 0.1);
          --wavy-border: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 120' preserveAspectRatio='none'%3E%3Cpath d='M0,0V46.29c47.79,22.2,103.59,32.17,158,28,70.36-5.37,136.33-33.31,206.8-37.5C438.64,32.43,512.34,53.67,583,72.05c69.27,18,138.3,24.88,209.4,13.08,36.15-6,69.85-17.84,104.45-29.34C989.49,25,1113-14.29,1200,52.47V0Z' fill='%23f8bbd0'/%3E%3C/svg%3E");
          display: flex;
          flex-direction: column;
          min-height: 100dvh;
          overflow-x: hidden;
          overflow-y: auto;
          padding: 0;
          background: var(--bg-page);
          color: var(--text-main);
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }
        .sese-header {
          position: relative;
          z-index: 10;
          display: block;
          max-width: none;
          margin: 0;
          background-color: var(--primary-pink);
          padding: 12px 16px 18px;
        }
        .sese-header::after {
          content: "";
          position: absolute;
          bottom: -24px;
          left: 0;
          width: 100%;
          height: 28px;
          background-image: var(--wavy-border);
          background-size: cover;
          transform: rotate(180deg);
        }
        .sese-back {
          position: absolute;
          left: 10px;
          top: 12px;
          z-index: 12;
          width: 34px;
          height: 34px;
          border: 0;
          border-radius: 50%;
          background: rgba(255,255,255,0.22);
          color: #fff;
          box-shadow: none;
        }
        .sese-chat-entry {
          position: absolute;
          right: 10px;
          top: 12px;
          z-index: 12;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 34px;
          height: 34px;
          border: 0;
          border-radius: 17px;
          background: rgba(255,255,255,0.24);
          color: #fff;
          padding: 0;
          box-shadow: none;
        }
        .sese-chat-entry span {
          position: absolute;
          right: -4px;
          top: -4px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-width: 16px;
          height: 16px;
          border-radius: 8px;
          background: #fff9c4;
          color: var(--text-main);
          font-size: 10px;
          line-height: 1;
        }
        .sese-header-title {
          margin-bottom: 8px;
          color: #fff;
          font-size: 18px;
          font-weight: 900;
          line-height: 1.15;
          text-align: center;
          text-shadow: 1px 1px 2px rgba(0,0,0,0.1);
        }
        .sese-game-status-bar {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 5px 8px;
          border-radius: 14px;
          background: var(--card-white);
          padding: 7px 10px;
          backdrop-filter: blur(5px);
        }
        .sese-pill {
          min-height: 0;
          overflow: hidden;
          border: 0;
          border-radius: 0;
          background: transparent;
          padding: 0;
          box-shadow: none;
          font-size: 11px;
        }
        .sese-pill span {
          display: block;
          color: var(--text-light);
          font-size: 9px;
          font-weight: bold;
          line-height: 1.2;
        }
        .sese-pill strong {
          display: block;
          margin-top: 1px;
          overflow: hidden;
          color: var(--text-main);
          font-size: 11px;
          font-weight: 800;
          line-height: 1.2;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .sese-turn-indicator {
          grid-column: span 2;
          margin-top: 1px;
          border-radius: 20px;
          background: var(--accent-yellow);
          padding: 3px;
          font-size: 10px;
          font-weight: bold;
          text-align: center;
        }
        .sese-board-container {
          flex: 0 0 auto;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: visible;
          padding: 30px 12px 20px;
        }
        .sese-board {
          display: grid;
          grid-template-rows: repeat(6, 1fr);
          gap: 4px;
          width: 100%;
          max-width: 400px;
          aspect-ratio: 1 / 1;
          border-radius: var(--radius-lg);
          background: var(--card-white);
          padding: 6px;
          box-shadow: var(--shadow-soft);
          position: relative;
        }
        .sese-tile {
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          aspect-ratio: 1;
          overflow: hidden;
          border: 1px solid rgba(255,255,255,0.5);
          border-radius: 8px;
          background: var(--soft-lavender);
          box-shadow: none;
          transition: all 0.3s;
        }
        .sese-tile.is-active {
          z-index: 5;
          background: var(--accent-yellow) !important;
          transform: scale(1.05);
          box-shadow: 0 0 15px var(--accent-yellow);
        }
        .sese-tile-start,
        .sese-tile-theme { background: #ffecb3; font-weight: bold; }
        .sese-tile-end { background: #b2dfdb; font-weight: bold; }
        .sese-tile-task { background: #f8bbd0; }
        .sese-tile-place { background: #e1f5fe; }
        .sese-tile-pose { background: #d1c4e9; }
        .sese-tile-number {
          position: absolute;
          top: 2px;
          left: 3px;
          color: var(--text-main);
          font-size: 9px;
          font-weight: 400;
          line-height: 1;
          opacity: 0.6;
        }
        .sese-tile-icon {
          height: auto;
          margin-bottom: 2px;
          color: var(--text-main);
          font-size: 14px;
          font-weight: 400;
          line-height: 1;
        }
        .sese-tile-name {
          display: block;
          width: auto;
          min-height: 0;
          max-width: calc(100% - 4px);
          overflow: hidden;
          color: var(--text-main);
          font-size: 8px;
          font-weight: 400;
          line-height: 1.1;
          text-align: center;
          text-overflow: ellipsis;
          transform: scale(0.9);
          white-space: nowrap;
        }
        .sese-piece-stack {
          position: absolute;
          inset: 0;
          min-height: 0;
          pointer-events: none;
        }
        .sese-piece {
          position: absolute;
          z-index: 10;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 20px;
          height: 20px;
          border: 2px solid #fff;
          border-radius: 50%;
          color: #fff;
          font-size: 10px;
          font-weight: bold;
          line-height: 1;
          box-shadow: 0 2px 4px rgba(0,0,0,0.2);
          transition: all 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }
        .sese-piece-me { left: 10%; bottom: 10%; background: #ec407a; }
        .sese-piece-du { right: 10%; bottom: 10%; background: #7e57c2; }
        .sese-piece.paused { filter: grayscale(1); opacity: 0.7; }
        .sese-piece.paused::after {
          content: "🔒";
          position: absolute;
          top: -5px;
          right: -5px;
          font-size: 8px;
        }
        .sese-controls {
          display: flex;
          flex-direction: column;
          gap: 12px;
          padding: 0 16px calc(env(safe-area-inset-bottom, 0px) + 20px);
        }
        .sese-player-states {
          display: flex;
          gap: 10px;
        }
        .sese-player-card {
          flex: 1;
          min-height: 80px;
          border-radius: var(--radius-md);
          background: var(--card-white);
          padding: 8px;
          font-size: 11px;
          box-shadow: none;
        }
        .sese-player-card.active { border: 2px solid var(--primary-pink); }
        .sese-player-card h2 {
          margin: 0 0 4px;
          color: var(--text-main);
          font-size: 11px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-status-list {
          display: block;
        }
        .sese-status-item,
        .sese-status-empty {
          display: inline-block;
          margin: 2px;
          border: 1px solid rgba(0,0,0,0.05);
          border-radius: 4px;
          background: var(--soft-lavender);
          padding: 2px 6px;
          color: var(--text-main);
          font-size: 9px;
          font-weight: 400;
          line-height: 1.2;
        }
        .sese-status-item span {
          display: inline;
          margin: 0 0 0 4px;
          color: var(--text-light);
          font-size: 9px;
          font-weight: 400;
        }
        .sese-action-area {
          display: flex;
          align-items: center;
          gap: 16px;
          border-radius: 40px;
          background: var(--card-white);
          padding: 12px;
        }
        .sese-dice {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 50px;
          height: 50px;
          border: 0;
          border-radius: 12px;
          background: white;
          color: var(--text-main);
          font-size: 24px;
          font-weight: 900;
          line-height: 1;
          box-shadow: inset 0 -4px 0 rgba(0,0,0,0.1), 0 4px 8px rgba(0,0,0,0.1);
        }
        .sese-dice.rolling { animation: seseDiceRoll 0.1s infinite; }
        .sese-roll-button {
          flex: 1;
          height: 50px;
          border: none;
          border-radius: 25px;
          background: var(--primary-pink);
          color: white;
          font-size: 18px;
          font-weight: 900;
          box-shadow: 0 4px 0 #d81b60;
          transition: all 0.1s;
        }
        .sese-roll-button:active {
          transform: translateY(2px);
          box-shadow: 0 2px 0 #d81b60;
        }
        .sese-roll-button:disabled {
          background: #ce93d8;
          box-shadow: 0 4px 0 #ab47bc;
          opacity: 0.7;
        }
        .sese-history {
          padding: 0 10px;
          color: var(--text-light);
          font-size: 10px;
          text-align: center;
        }
        .sese-chat-mask {
          position: fixed;
          inset: 0;
          z-index: 110;
          display: flex;
          align-items: flex-start;
          justify-content: flex-end;
          background: rgba(136, 77, 138, 0.18);
          padding: calc(env(safe-area-inset-top, 0px) + 54px) 14px 14px;
          backdrop-filter: blur(2px);
        }
        .sese-chat-panel {
          display: flex;
          flex-direction: column;
          width: min(360px, calc(100vw - 28px));
          max-height: min(70dvh, 560px);
          overflow: hidden;
          border: 2px solid rgba(248, 187, 208, 0.9);
          border-radius: 18px;
          background: #fff6fb;
          box-shadow: 0 18px 42px rgba(136, 77, 138, 0.22);
        }
        .sese-chat-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          border-bottom: 1px solid rgba(186, 104, 200, 0.16);
          background: #f8bbd0;
          padding: 9px 10px;
          color: #fff;
        }
        .sese-chat-head strong,
        .sese-chat-head span {
          display: block;
          line-height: 1.2;
        }
        .sese-chat-head strong {
          font-size: 13px;
          font-weight: 900;
        }
        .sese-chat-head span {
          margin-top: 2px;
          font-size: 10px;
          font-weight: 700;
          opacity: 0.9;
        }
        .sese-chat-head button {
          flex: 0 0 28px;
          width: 28px;
          height: 28px;
          border: 0;
          border-radius: 50%;
          background: rgba(255,255,255,0.24);
          color: #fff;
          font-size: 20px;
          font-weight: 700;
          line-height: 1;
        }
        .sese-chat-list {
          display: flex;
          flex: 1;
          min-height: 180px;
          flex-direction: column;
          gap: 8px;
          overflow-y: auto;
          padding: 10px;
        }
        .sese-chat-message {
          max-width: 86%;
          border-radius: 12px;
          padding: 7px 9px;
          color: var(--text-main);
          font-size: 12px;
          line-height: 1.45;
        }
        .sese-chat-message span {
          display: block;
          margin-bottom: 2px;
          font-size: 9px;
          font-weight: 900;
          opacity: 0.72;
        }
        .sese-chat-message p {
          margin: 0;
          white-space: pre-wrap;
          word-break: break-word;
        }
        .sese-chat-message.xinyue {
          align-self: flex-end;
          background: #ffe0ec;
        }
        .sese-chat-message.du {
          align-self: flex-start;
          background: #efe7f6;
        }
        .sese-chat-message.system {
          align-self: center;
          max-width: 100%;
          background: #fff9c4;
          color: #8a6d3b;
          font-size: 10px;
          text-align: center;
        }
        .sese-chat-message.pending {
          opacity: 0.72;
        }
        .sese-chat-form {
          display: flex;
          gap: 6px;
          border-top: 1px solid rgba(186, 104, 200, 0.16);
          background: rgba(255,255,255,0.74);
          padding: 8px;
        }
        .sese-chat-form input {
          flex: 1;
          min-width: 0;
          height: 36px;
          border: 1px solid rgba(186, 104, 200, 0.22);
          border-radius: 18px;
          background: #fff;
          color: var(--text-main);
          padding: 0 12px;
          font-size: 12px;
          outline: none;
        }
        .sese-chat-form input:disabled {
          opacity: 0.6;
        }
        .sese-chat-form button {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          flex: 0 0 44px;
          width: 44px;
          height: 36px;
          border: 0;
          border-radius: 18px;
          background: #f06292;
          color: #fff;
          font-size: 13px;
          font-weight: 900;
          box-shadow: 0 3px 0 #d81b60;
        }
        .sese-chat-form button svg {
          color: currentColor;
        }
        .sese-chat-form button:disabled {
          opacity: 0.5;
        }
        .sese-popup-mask {
          position: fixed;
          inset: 0;
          z-index: 100;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(136, 77, 138, 0.4);
          padding: 0;
          backdrop-filter: blur(4px);
        }
        .sese-popup {
          width: 80%;
          border: 4px solid var(--primary-pink);
          border-radius: var(--radius-lg);
          background: white;
          padding: 24px;
          text-align: center;
          box-shadow: 0 20px 40px rgba(0,0,0,0.2);
        }
        .sese-popup-kicker { display: none; }
        .sese-popup h2 {
          margin: 0 0 12px;
          color: var(--text-main);
          font-size: 20px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-popup p {
          margin: 0 0 20px;
          color: #666;
          font-size: 14px;
          font-weight: 400;
          line-height: 1.6;
          text-align: center;
        }
        .sese-popup button {
          width: auto;
          height: auto;
          margin: 0;
          border: none;
          border-radius: 20px;
          background: var(--primary-pink);
          color: white;
          padding: 12px 30px;
          font-size: 14px;
          font-weight: bold;
          box-shadow: none;
        }
        @keyframes seseDiceRoll {
          0% { transform: rotate(0deg) scale(1); }
          50% { transform: rotate(10deg) scale(1.1); }
          100% { transform: rotate(-10deg) scale(1); }
        }
        `})]})}function Y({label:s,value:t}){return a.jsxs("div",{className:"sese-pill",children:[a.jsx("span",{children:s}),a.jsx("strong",{children:t})]})}function Te({actor:s,statuses:t,active:n}){const p=t.slice(-3).reverse();return a.jsxs("div",{className:`sese-player-card sese-player-card-${s} ${n?"active":""}`,children:[a.jsx("h2",{children:s==="xinyue"?"我的状态":"渡的状态"}),a.jsx("div",{className:"sese-status-list",children:p.length?p.map((w,_)=>{const c=v(w.label||w.slot||"状态"),P=v(w.value||""),T=it(w);return a.jsxs("div",{className:"sese-status-item",children:[c,P?`：${P}`:"",T?a.jsx("span",{children:T}):null]},`${c}-${P}-${_}`)}):a.jsx("div",{className:"sese-status-empty",children:"无状态"})})]})}export{pt as SeseBoardGameTab};
