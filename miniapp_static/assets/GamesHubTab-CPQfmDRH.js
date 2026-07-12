import{r as t,b as u,j as a,B as S,d,e as $}from"./index-B7JyRbLT.js";function _({onOpenWenyou:h,onOpenSeseBoard:j,onOpenCaptivitySimulator:y}){const[o,v]=t.useState("副本大厅"),[w,k]=t.useState("掷骰走格"),[N,M]=t.useState("未开局");return t.useEffect(()=>{let n=!1;return(async()=>{var c,l,m,p,g;const[i,r]=await Promise.allSettled([u("/miniapp-api/wenyou/status"),u("/miniapp-api/game-tools/private_board",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:"status",save_id:"default"})})]);if(!n&&(i.status==="fulfilled"&&((c=i.value)!=null&&c.ok)&&i.value.active&&i.value.session&&v(`当前副本：${i.value.session.instance_name||"系统空间进行中"}`),r.status==="fulfilled"&&((l=r.value)!=null&&l.ok)&&r.value.state)){const e=r.value.state,s=Number(e.board_size||36),x=Math.max(0,Math.min(s,Number(((m=e.positions)==null?void 0:m.xinyue)||0))),b=Math.max(0,Math.min(s,Number(((p=e.positions)==null?void 0:p.du)||0))),f=String(((g=e.theme_profile)==null?void 0:g.theme)||"").trim();k(f?`${f} · 我 ${x}/${s} · 渡 ${b}/${s}`:`我 ${x}/${s} · 渡 ${b}/${s}`),M(e.game_over?"已结束":e.turn_actor==="du"?"渡行动":"我行动")}})(),()=>{n=!0}},[]),a.jsxs("div",{className:"games-hub",children:[a.jsxs("button",{className:"games-card games-card-wenyou",type:"button",onClick:h,children:[a.jsx("div",{className:"games-card-icon games-card-icon-wenyou",children:a.jsx(S,{})}),a.jsxs("div",{className:"games-card-main",children:[a.jsxs("div",{className:"games-card-title-row",children:[a.jsx("h2",{children:"无限流"}),a.jsx("span",{children:o.includes("当前副本")?"继续":"进入"})]}),a.jsx("p",{children:o})]}),a.jsx(d,{})]}),a.jsxs("button",{className:"games-card games-card-board",type:"button",onClick:j,children:[a.jsx("div",{className:"games-card-icon games-card-icon-board",children:a.jsx($,{className:"h-6 w-6 stroke-[1.7]"})}),a.jsxs("div",{className:"games-card-main",children:[a.jsxs("div",{className:"games-card-title-row",children:[a.jsx("h2",{children:"涩涩走格棋"}),a.jsx("span",{children:N})]}),a.jsx("p",{children:w}),a.jsxs("div",{className:"games-board-strip","aria-hidden":"true",children:[a.jsx("i",{className:"filled"}),a.jsx("i",{}),a.jsx("i",{}),a.jsx("i",{className:"me"}),a.jsx("i",{}),a.jsx("i",{className:"du"}),a.jsx("i",{className:"finish"})]})]}),a.jsx(d,{})]}),a.jsxs("button",{className:"games-card games-card-captivity",type:"button",onClick:y,children:[a.jsxs("div",{className:"games-card-main",children:[a.jsxs("div",{className:"games-card-title-row",children:[a.jsx("h2",{children:"囚禁模拟器"}),a.jsx("span",{children:"开局"})]}),a.jsx("p",{children:"CAPTIVE / MASTER · 30 天囚禁档案"}),a.jsxs("div",{className:"games-captivity-strip","aria-hidden":"true",children:[a.jsx("i",{}),a.jsx("i",{}),a.jsx("i",{}),a.jsx("i",{})]})]}),a.jsx(d,{})]}),a.jsx("style",{children:`
        .games-hub {
          display: flex;
          flex-direction: column;
          gap: 12px;
          padding: 16px 2px 28px;
          font-family: "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        .games-card {
          display: flex;
          align-items: center;
          gap: 12px;
          width: 100%;
          min-height: 96px;
          border: 1px solid rgba(255, 255, 255, 0.72);
          border-radius: 24px;
          padding: 14px;
          text-align: left;
          box-shadow: 0 18px 38px rgba(109, 74, 109, 0.12);
          transition: transform 160ms ease, box-shadow 160ms ease;
        }
        .games-card:active {
          transform: scale(0.985);
          box-shadow: 0 10px 24px rgba(109, 74, 109, 0.12);
        }
        .games-card-wenyou {
          background: linear-gradient(135deg, rgba(248, 240, 244, 0.96), rgba(231, 246, 255, 0.92));
        }
        .games-card-board {
          background: linear-gradient(135deg, rgba(255, 240, 247, 0.98), rgba(232, 247, 244, 0.92));
        }
        .games-card-captivity {
          border-color: #eb79b0;
          background: #121212;
        }
        .games-card-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 52px;
          height: 52px;
          flex: 0 0 52px;
          border-radius: 18px;
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78), 0 10px 22px rgba(104, 70, 113, 0.12);
        }
        .games-card-icon-wenyou {
          color: #704a5d;
          background: #fff8dd;
        }
        .games-card-icon-board {
          color: #884d8a;
          background: #f8bbd0;
        }
        .games-card-main {
          min-width: 0;
          flex: 1;
        }
        .games-card-title-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
        }
        .games-card h2 {
          margin: 0;
          color: #3d3043;
          font-size: 17px;
          font-weight: 800;
          line-height: 1.2;
        }
        .games-card-title-row span {
          flex: 0 0 auto;
          border-radius: 999px;
          background: rgba(255, 255, 255, 0.68);
          padding: 4px 8px;
          color: #9b5fa1;
          font-size: 11px;
          font-weight: 700;
          line-height: 1;
        }
        .games-card-captivity h2 {
          color: #ffffff;
          font-family: "Times New Roman", serif;
          font-style: italic;
          letter-spacing: -0.05em;
        }
        .games-card-captivity .games-card-title-row span {
          border: 1px solid #eb79b0;
          border-radius: 0;
          background: transparent;
          color: #eb79b0;
          text-transform: uppercase;
        }
        .games-card p {
          margin: 7px 0 0;
          overflow: hidden;
          color: #7b6a80;
          font-size: 13px;
          font-weight: 600;
          line-height: 1.35;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .games-card-captivity p {
          color: #aaaaaa;
        }
        .games-board-strip {
          display: grid;
          grid-template-columns: repeat(7, minmax(0, 1fr));
          gap: 5px;
          margin-top: 10px;
          max-width: 230px;
        }
        .games-board-strip i {
          display: block;
          aspect-ratio: 1;
          border: 1px solid rgba(186, 104, 200, 0.18);
          border-radius: 7px;
          background: rgba(255, 255, 255, 0.62);
        }
        .games-board-strip .filled {
          background: #fff9c4;
        }
        .games-board-strip .me {
          background: #f8bbd0;
          box-shadow: inset 0 0 0 3px #ffffff;
        }
        .games-board-strip .du {
          background: #e1f5fe;
          box-shadow: inset 0 0 0 3px #ffffff;
        }
        .games-board-strip .finish {
          background: #e0f2f1;
        }
        .games-captivity-strip {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 5px;
          margin-top: 10px;
          max-width: 180px;
        }
        .games-captivity-strip i {
          display: block;
          height: 2px;
          background: #2a2a2a;
        }
        .games-captivity-strip i:first-child,
        .games-captivity-strip i:nth-child(2) {
          background: #eb79b0;
        }
        `})]})}export{_ as GamesHubTab};
