import{u as Gt,r as x,j as e,C as Vt,M as Jt,S as Xt,b as bt}from"./index-DNZp3R2d.js";const ct=["xinyue","du"],Me={xinyue:"我",du:"渡"},Qt={xinyue:0,du:0},mt=[{id:"scissors",label:"剪刀",icon:"✌️"},{id:"rock",label:"石头",icon:"👊"},{id:"paper",label:"布",icon:"✋"}],Zt={rock:"scissors",scissors:"paper",paper:"rock"},es={scissors:"scissors",剪刀:"scissors","✌️":"scissors","✌":"scissors",rock:"rock",stone:"rock",石头:"rock",拳头:"rock","👊":"rock",paper:"paper",布:"paper",包袱:"paper","✋":"paper"};function ne(t){const s=String(t||"").trim();return s?es[s]||s:""}function dt(t){var a;const s=ne(t);return((a=mt.find(n=>n.id===s))==null?void 0:a.label)||String(t||"").trim()||"未出拳"}function ts(t,s){var g;const a=ne((g=t==null?void 0:t.picks)==null?void 0:g.xinyue),n=ne(s);if(!a||!n)return"";const l=dt(a),h=dt(n);if(a===n)return`你出了${l}，渡出了${h}。平局，重新出拳。`;const f=Zt[a]===n?"你赢":"渡赢";return`你出了${l}，渡出了${h}。${f}。`}const yt={place:"最终地点",pose:"最终姿势"},ss=["跳蛋","震动乳夹","震动环","乳夹","锁精环","飞机杯","软绳","手腕绑带","眼罩","口球","春药"],as=["跳蛋","震动","按摩棒","飞机杯","吸乳器","吸吮器"];function me(t){return new Promise(s=>window.setTimeout(s,t))}function S(t){return String(t||"").replace(/小玥/g,"我")}function T(t){return String(t||"").replace(/小玥/g,"你").replace(/(^|[^自])我/g,"$1你")}function ie(t){return String(t||"")}function Pe(t,s){return S(t.player_text||t.text||t.error||"").split(/\r?\n/).map(l=>l.trim()).find(l=>l&&!l.startsWith("【")&&!/^(进度|主题|轮到|手牌|我的状态|渡的状态|最终地点|最终姿势|待处理|可用命令)/.test(l))||s}function z(t){return`${t}-${Date.now()}-${Math.random().toString(36).slice(2,8)}`}function Te(t,s){const a=Math.floor(Number(t||0));return Math.max(1,Math.min(s,a||1))}function pt(t,s){const a=Math.floor(Number(t||0));return Math.max(0,Math.min(s,a||0))}function is(t,s){const a=[];for(let n=1;n<=t;n+=s){const l=Array.from({length:Math.min(s,t-n+1)},(h,f)=>n+f);a.length%2===1&&l.reverse(),a.push(l)}return a.reverse().flat()}function ns(t,s,a){if(s===1)return"start";if(s===a)return"end";if(!t)return"empty";const n=`${t.kind||""} ${t.slot||""}`.toLowerCase();return/empty/.test(n)?"empty":/finish_self|finish-jump/.test(n)?"finish-jump":/reset/.test(n)?"reset":/swap/.test(n)?"swap":/move|back|forward/.test(n)?"move":/lock|pause|item/.test(n)?"item":/clear/.test(n)?"clear":/extend|time/.test(n)?"time":/limit/.test(n)?"limit":/place/.test(n)?"place":/pose/.test(n)?"pose":/theme/.test(n)?"theme":"task"}function rs(t){return t==="start"?"🚩":t==="end"?"🏆":t==="place"?"🏫":t==="item"?"🎁":t==="move"?"⏪":t==="reset"?"🔁":t==="finish-jump"?"🏁":t==="swap"?"🔄":t==="clear"?"✨":t==="time"?"⏳":t==="limit"?"🚫":t==="pose"?"◇":t==="theme"?"🚩":t==="task"?"📸":""}function os(t,s,a){return s===1?"起点":s===a?"终点":S((t==null?void 0:t.name)||"空")}function ls(t){const s=S(t).match(/(我|渡)掷出\s*(\d+)，从\s*(\d+)\s*走到\s*(\d+)/);return s?{actor:s[1]==="渡"?"du":"xinyue",dice:Number(s[2]||1),from:Number(s[3]||0),to:Number(s[4]||0)}:null}function ve(t){return t.replace(/[。.!！?？\s]+$/g,"").trim()}function cs(t,s,a,n){const h=[t,...s].map(g=>g.trim()).filter(Boolean).filter(g=>!/^下一次行动[:：]/.test(g)&&!/^待处理[:：]/.test(g)).join(" ");if(/双方回到起点/.test(h))return"双方回到起点";let f=h.match(/(我|你|渡|对方|双方)?\s*从\s*\d+\s*(前进|后退)\s*(\d+)\s*格(?:到|至)\s*\d+/);return f?`${f[1]||a||"玩家"}${f[2]}了 ${f[3]} 格`:(f=h.match(/(我|你|渡|对方|双方)\s*(前进|后退)\s*(\d+)\s*格/),f?`${f[1]}${f[2]}了 ${f[3]} 格`:(f=h.match(/(我|你|渡|对方)\s*从\s*\d+\s*回到起点/),f?`${f[1]}回到起点`:(f=h.match(/(我|你|渡|对方)\s*从\s*\d+\s*直达终点/),f?`${f[1]}直达终点`:ve(t)===ve(n)?"":t?`触发：${t}`:"")))}function ds(t,s){var G,E;const a=S(t).split(`
`).map(b=>b.trim()).filter(Boolean),n=a.findIndex(b=>/^第\s*\d+\s*格：/.test(b)),l=n>=0?a[n]:"";if(!l)return null;const h=l.match(/^第\s*(\d+)\s*格：([^，。]+)/),f=(h==null?void 0:h[2])||"格子事件",g=((G=l.match(/抽到「([^」]+)」/))==null?void 0:G[1])||"",o=((E=l.match(/获得\s*([^（，。]+)/))==null?void 0:E[1])||"",R=!!(g||o||/抽卡|惩罚任务|选择惩罚/.test(f)),W=/奖励|Pass卡|获得/.test(l)?"reward":/选择/.test(f)?"choice":"penalty",B=Number((h==null?void 0:h[1])||0),q=s==null?void 0:s.actor,Q=l.replace(/^第\s*\d+\s*格：/,"").trim(),m=q?Me[q]:"",C=cs(Q,a.slice(n+1,n+4),m,f);return{position:B,actor:q,actorLabel:m,from:s==null?void 0:s.from,to:(s==null?void 0:s.to)??B,title:f,text:l,detail:C,kind:R?"draw":"event",cardTitle:g||o||f,cardType:W==="reward"?"奖励卡":W==="choice"?"选择惩罚":"惩罚任务",tone:W}}function xt(t){const s=T(t.cardType||"").trim(),a=T(t.cardTitle||t.title).trim(),n=T(t.title).trim();return!s||s===a||s===n?"":s}function ut(t){const s=T(t.detail||"").trim(),a=T(t.title).trim();return!s||ve(s.replace(/^触发[:：]\s*/,""))===ve(a)?"":s}function ps(t,s,a){const n=S(t).trim();if(!n)return null;const l=Array.isArray(a)?a.map(R=>S(R).trim()).filter(Boolean):[],o=[...[...Array.from(new Set(l)).filter(R=>R!==n)].sort(()=>Math.random()-.5).slice(0,7),n];for(;o.length<8;)o.unshift(n);return{theme:n,direction:S(s||"待定"),items:o,spinKey:`${Date.now()}-${Math.random().toString(36).slice(2,8)}`}}function xs(t){const s=String(t.duration_type||"");if(s==="actions"){const a=Math.max(0,Number(t.remaining_actions||0));return t.blocks_action?`停步剩余 ${a} 次`:`剩余 ${a} 次行动`}return s==="minutes"?`${Math.max(1,Number(t.minutes||0))} 分钟`:s==="until_finish"?"到终点前有效":s==="until_clear"?"待解除":""}function wt(t){return!!yt[String(t||"").trim()]}function vt(t,s){const a=new Map;for(const h of t||[]){const f=String((h==null?void 0:h.slot)||"").trim();if(!wt(f))continue;const g=S((h==null?void 0:h.value)||"").trim();g&&a.set(f,g)}const n=S((s==null?void 0:s.final_place)||"").trim(),l=S((s==null?void 0:s.final_pose)||"").trim();return n&&!a.has("place")&&a.set("place",n),l&&!a.has("pose")&&a.set("pose",l),["place","pose"].map(h=>{const f=a.get(h);return f?{label:yt[h]||"终局素材",values:[f]}:null}).filter(h=>!!h)}function us(t){const s=S(t.label||t.slot||"状态");return t.slot==="prop"||s==="道具"?"道具惩罚":s}function fs(t){const s=S(t.value||""),a=[],n=Math.max(1,Number(t.level||1));t.slot==="prop"&&n>1&&kt(s)&&a.push(`${n}档`);const l=xs(t);return l&&a.push(l),s?a.length?`${s}（${a.join("，")}）`:s:a.length?a.join("，"):"状态"}function kt(t){return as.some(s=>t.includes(s))}function hs(t){const s=new Map;return t.filter(a=>!wt(a.slot)).slice(-6).forEach(a=>{const n=us(a),l=s.get(n)||[];l.push(fs(a)),s.set(n,l)}),Array.from(s.entries()).map(([a,n])=>({label:a,values:n}))}function ft(t){return(t||[]).some(s=>s.blocks_action&&Number(s.remaining_actions||0)>0)}function gs(t){const s=[/^(我|渡)掷出\s*\d+/,/^第\s*\d+\s*格：/,/^下一次行动：/,/行动权/,/到达终点/,/^新局已开始。?$/,/^本局已结束。?$/];return S(t).split(`
`).map(a=>a.trim()).filter(a=>a&&s.some(n=>n.test(a))).slice(0,4)}function bs(t){return String(t).split(/\r?\n/).map(a=>a.trim()).find(Boolean)==="【掷骰】"}function ht(t,s){return t.slice(s).map(a=>{const n=a.trim(),l=n.match(/^【描述[:：](.*)】$/);return l?l[1].trim():n}).filter(Boolean).join(`
`).trim()}function ms(t){const s=String(t).split(/\r?\n/),a=s.findIndex(g=>g.trim());if(a<0)return{kind:"",body:""};const n=s[a].trim(),l=ht(s,a+1);if(n==="【掷骰】")return{kind:"roll",body:l};if(n==="【提交】")return{kind:"submit",body:l};if(n==="【通过】")return{kind:"approve",body:l};if(n==="【不通过】")return{kind:"reject",body:l};if(n==="【Pass】"||n==="【PASS】"||n==="【使用Pass卡】")return{kind:"pass",body:l};const h=n.match(/^【选择[:：](.+)】$/);if(h)return{kind:"choose",choice:h[1].trim(),body:l};const f=n.match(/^【(?:剪刀石头布|石头剪刀布)[:：](.+)】$/);return f?{kind:"choose",choice:f[1].trim(),body:l}:{kind:"",body:ht(s,a)}}function ys(t,s="rock"){const a=((t==null?void 0:t.choices)||[]).find(n=>(n==null?void 0:n.id)||(n==null?void 0:n.label));return String((a==null?void 0:a.id)||(a==null?void 0:a.label)||s).trim()}function ws(t,s){if(t==="final_note")return"本地预览：终局小纸条收到了。";const a=(s==null?void 0:s.pending_event)||null;if((a==null?void 0:a.type)==="duel"&&a.current_actor==="du")return`【剪刀石头布：石头】
【描述：本地预览：我出石头。】`;if((a==null?void 0:a.type)==="choice"&&a.actor==="du"){const n=ys(a,"");if(n)return`【选择：${n}】
【描述：本地预览：我选这个。】`}return(a==null?void 0:a.type)==="review"&&a.reviewer==="du"&&a.phase==="questioning"?`【提交】
【描述：本地预览：渡想问你的真心话问题。】`:(a==null?void 0:a.type)==="review"&&a.actor==="du"&&a.phase==="assigned"?`【提交】
【描述：本地预览：渡已经完成任务，提交给你验收。】`:(a==null?void 0:a.type)==="review"&&a.reviewer==="du"&&a.phase==="submitted"?`【通过】
【描述：本地预览：这次算你通过。】`:we(s)?`【掷骰】
【描述：本地预览：我来掷这一回合。】`:"本地预览：我看到了，等你继续行动。"}async function M(t){const s=await bt("/miniapp-api/game-tools/private_board",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:t,save_id:"default"})});if(!(s!=null&&s.ok))throw new Error((s==null?void 0:s.error)||"走格棋命令失败");return s}async function vs(t){var a;const s=await bt("/miniapp-api/game-tools/private_board/sync-du",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({save_id:"default",mode:t.mode,message:t.message||"",roll_text:t.rollText||""})});if(!(s!=null&&s.ok))throw new Error((s==null?void 0:s.error)||((a=s==null?void 0:s.wakeup)==null?void 0:a.error)||"游戏内交流失败");return s}function we(t){return!!(t&&t.turn_actor==="du"&&!t.game_over)}function Ps({onBack:t}){var Ve,Je,Xe,Qe,Ze,et,tt,st,at,it,nt;const s=Gt(),a=x.useRef(null),n=x.useRef(!1),l=x.useRef(null),h=x.useRef(null),f=x.useRef(null),g=x.useRef(null),[o,R]=x.useState(null),[W,B]=x.useState(Qt),[q,Q]=x.useState(1),[m,C]=x.useState(!1),[G,E]=x.useState(!1),[b,re]=x.useState(!1),[ue,ee]=x.useState(null),[k,H]=x.useState(null),[Z,te]=x.useState(!0),[se,oe]=x.useState(null),[K,$]=x.useState(!1),[Y,fe]=x.useState(0),[he,Ae]=x.useState(""),[P,V]=x.useState(!1),[jt,le]=x.useState(!1),[De,Nt]=x.useState(""),[_t,Re]=x.useState(!1),[Le,zt]=x.useState(1),[ke,Be]=x.useState(""),[Ie,Ct]=x.useState([{id:"system-ready",speaker:"system",text:"游戏内交流在这里。渡明确发送【掷骰】时，棋盘才会执行他的行动。"}]),w=(o==null?void 0:o.state)||{},L=Math.max(12,Math.min(80,Number(w.board_size||36))),je=L<=36?6:8,Ne=w.turn_actor==="du"?"du":"xinyue",F=!!(w.game_over||o!=null&&o.game_over),ce=Ne==="du"&&!F,_=w.pending_event||null,J=x.useMemo(()=>{try{return!!new URLSearchParams(window.location.search).has("preview")}catch{return!1}},[]);x.useLayoutEffect(()=>{a.current&&(a.current.scrollTop=0)},[]),x.useEffect(()=>{n.current=K,K&&fe(0)},[K]),x.useEffect(()=>{K&&window.setTimeout(()=>{var i;return(i=l.current)==null?void 0:i.scrollIntoView({block:"end"})},40)},[Ie.length,K,P]),x.useEffect(()=>{if(!k||k.kind!=="draw"||k.tone!=="reward"){te(!0);return}te(!1);const i=window.setTimeout(()=>te(!0),900);return()=>window.clearTimeout(i)},[k]);const v=x.useCallback((i,d=!1)=>{Ct(u=>[...u,i]),d&&!n.current&&fe(u=>Math.min(9,u+1))},[]),Oe=x.useMemo(()=>{const i=new Map;for(const d of w.cell_events||[]){const u=Number((d==null?void 0:d.position)||0);u>0&&i.set(u,d)}return i},[w.cell_events]),St=x.useMemo(()=>is(L,je).map(i=>{const d=Oe.get(i),u=ns(d,i,L);return{position:i,event:d,kind:u,icon:rs(u),name:os(d,i,L)}}),[L,je,Oe]),y=x.useCallback(i=>{var d,u,p,c;R(i),B({xinyue:Number(((u=(d=i.state)==null?void 0:d.positions)==null?void 0:u.xinyue)||0),du:Number(((c=(p=i.state)==null?void 0:p.positions)==null?void 0:c.du)||0)})},[]),qe=x.useCallback(async()=>{C(!0);try{const i=await M("status");y(i)}catch(i){s(`加载涩涩走格棋失败：${(i==null?void 0:i.message)||i}`)}finally{C(!1)}},[y,s]);x.useEffect(()=>{qe()},[qe]);const Ee=x.useCallback(async i=>{E(!0);for(let d=0;d<12;d+=1)Q(Math.floor(Math.random()*6)+1),await me(58);Q(Math.max(1,Math.min(6,i||1))),E(!1)},[]),_e=x.useCallback(async(i,d,u,p)=>{const c=Number(u||0),r=Number(p||0);if(c===r){i[d]=r,B({...i}),ee(Te(r,L)),await me(120);return}const D=r>c?1:-1;for(let I=c+D;D>0?I<=r:I>=r;I+=D)i[d]=I,B({...i}),ee(Te(I,L)),await me(145)},[L]),ze=x.useCallback(async()=>{var i,d,u,p,c;if(!(m||b)){C(!0),H(null);try{const r=await M("new_game");Q(1),y(r),oe(ps((d=(i=r.state)==null?void 0:i.theme_profile)==null?void 0:d.theme,(p=(u=r.state)==null?void 0:u.theme_profile)==null?void 0:p.direction_label,(c=r.state)==null?void 0:c.theme_options))}catch(r){s(`开新局失败：${(r==null?void 0:r.message)||r}`)}finally{C(!1)}}},[b,y,m,s]);x.useCallback(async()=>{if(!(m||b)){C(!0);try{const i=await M("end_game");y(i)}catch(i){s(`结束本局失败：${(i==null?void 0:i.message)||i}`)}finally{C(!1)}}},[b,y,m,s]);const ae=x.useCallback(async(i,d)=>{var D,I,de,pe,xe;const u=i.trim()||"我看到了。",p=ms(u),c=p.body.trim();c&&v({id:z("du"),speaker:"du",text:c},!0);const r=(d==null?void 0:d.pending_event)||null;try{if((r==null?void 0:r.type)==="duel"&&r.current_actor==="du"){if(p.kind!=="choose"||!p.choice.trim())return;const N=ts(r,p.choice.trim()),j=await M(`choose ${p.choice.trim()}`);y(j);const O=we(j.state)&&!((D=j.state)!=null&&D.pending_event);N&&(g.current=O?{state:j.state,message:"剪刀石头布对抗已结算，现在轮到渡行动。"}:null,H({position:Number(r.cell||((de=(I=j.state)==null?void 0:I.positions)==null?void 0:de.du)||0),kicker:"剪刀石头布对抗",title:"对抗结果",text:N,detail:N,kind:"event"})),v({id:z("system"),speaker:"system",text:N||Pe(j,"渡已出拳，系统已判定对抗结果。")},!0),!N&&O&&await((pe=f.current)==null?void 0:pe.call(f,j.state,"剪刀石头布对抗已结算，现在轮到渡行动。"));return}if((r==null?void 0:r.reviewer)==="du"&&r.type==="review"&&r.phase==="questioning"){if(p.kind!=="submit")return;const N=p.body.trim();if(!N){v({id:z("system"),speaker:"system",text:"渡发了【提交】，但后面没有题目。"},!0);return}const j=await M(`submit ${N}`);y(j),v({id:z("system"),speaker:"system",text:"渡已出题，轮到你回答。"},!0);return}if((r==null?void 0:r.actor)==="du"&&r.type==="review"&&r.phase==="assigned"){if(p.kind!=="submit")return;const N=p.body.trim();if(!N){v({id:z("system"),speaker:"system",text:"渡发了【提交】，但后面没有提交内容。"},!0);return}const j=await M(`submit ${N}`);y(j),v({id:z("system"),speaker:"system",text:"渡已提交惩罚任务，等你验收。"},!0);return}if((r==null?void 0:r.actor)==="du"&&r.type==="choice"){if(p.kind==="pass"){const j=await M("pass");if(y(j),j.ok===!1){v({id:z("system"),speaker:"system",text:Pe(j,"渡没有Pass卡，不能跳过。")},!0);return}v({id:z("system"),speaker:"system",text:"渡使用Pass卡跳过了惩罚。"},!0);return}if(p.kind!=="choose"||!p.choice.trim())return;const N=await M(`choose ${p.choice.trim()}`);y(N),v({id:z("system"),speaker:"system",text:"渡已选择惩罚选项。"},!0);return}if((r==null?void 0:r.reviewer)==="du"&&r.type==="review"&&r.phase==="submitted"){if(p.kind==="approve"){const N=await M("approve");y(N),v({id:z("system"),speaker:"system",text:"渡验收通过，棋局继续。"},!0);return}if(p.kind==="reject"){const N=await M(p.body.trim()?`reject ${p.body.trim()}`:"reject");y(N),v({id:z("system"),speaker:"system",text:"渡打回了任务，需要重新提交。"},!0);return}return}we(d)&&bs(u)&&(await me(260),v({id:z("system"),speaker:"system",text:"渡发送【掷骰】，已执行他的行动。"},!0),await((xe=h.current)==null?void 0:xe.call(h,{notifyAfterUserRoll:!1})))}catch(N){v({id:z("system"),speaker:"system",text:`渡的指令执行失败：${String((N==null?void 0:N.message)||N)}`},!0)}},[v,y]),X=x.useCallback(async(i,d)=>{if(!J)return vs(i);let u=d,p="";if(i.mode==="final_note"){const r=await M("final_note_sent");u=r.state||u,p=r.player_text||r.text||""}const c=ws(i.mode,u);return{ok:!0,state:u,player_text:p,reply_text:c,reply_preview:c.slice(0,120),wakeup:{reply_text:c,reply_preview:c.slice(0,120)}}},[J]),Ye=x.useCallback(async(i,d="现在轮到渡行动。")=>{var u,p;if(!(!we(i)||i!=null&&i.pending_event)){v({id:z("system"),speaker:"system",text:J?"预览模式：轮到渡行动，已继续同步。":"轮到渡行动，已把棋局发给渡。"},!0),V(!0);try{const c=await X({mode:"roll_result",message:d,rollText:""},i);c.state&&y({ok:!0,state:c.state,player_text:c.player_text||""});const r=ie(c.reply_text||((u=c.wakeup)==null?void 0:u.reply_text)||c.reply_preview||((p=c.wakeup)==null?void 0:p.reply_preview)||"").trim();await ae(r,c.state||i)}catch(c){const r=String((c==null?void 0:c.message)||c||"同步失败");v({id:z("system"),speaker:"system",text:`渡行动同步失败：${r}`},!0),s(`渡行动同步失败：${r}`)}finally{V(!1)}}},[v,y,J,ae,X,s]);x.useEffect(()=>{f.current=Ye},[Ye]);const $t=x.useCallback(()=>{var d;const i=g.current;g.current=null,H(null),i&&((d=f.current)==null||d.call(f,i.state,i.message))},[]),ge=x.useCallback(async(i,d="小玥刚掷完骰子。")=>{var p,c;const u=ie(i.text||i.du_text||i.player_text||"").trim();v({id:z("system"),speaker:"system",text:J?"预览模式：已同步这次棋局。":d.includes("掷")?"已把这次掷骰结果和当前棋局发给渡。":"已把棋局变化发给渡。"},!0),V(!0);try{const r=await X({mode:"roll_result",message:d,rollText:u},i.state);r.state&&y({ok:!0,state:r.state,player_text:r.player_text||i.player_text||""});const D=ie(r.reply_text||((p=r.wakeup)==null?void 0:p.reply_text)||r.reply_preview||((c=r.wakeup)==null?void 0:c.reply_preview)||"").trim();await ae(D,r.state||i.state)}catch(r){const D=String((r==null?void 0:r.message)||r||"同步失败");v({id:z("system"),speaker:"system",text:`自动同步失败：${D}`},!0),s(`自动同步给渡失败：${D}`)}finally{V(!1)}},[v,y,J,ae,X,s]),Ce=x.useCallback(async(i={})=>{var r,D,I,de,pe,xe,N;if(m||b||F)return;let d=null;C(!0),re(!0),H(null);const u={xinyue:Number(((r=w.positions)==null?void 0:r.xinyue)||0),du:Number(((D=w.positions)==null?void 0:D.du)||0)},p=w.turn_actor==="du"?"du":"xinyue",c={...u};try{const j=await M("roll"),O=ls(j.player_text||"");await Ee((O==null?void 0:O.dice)||Math.floor(Math.random()*6)+1),O&&await _e(c,O.actor,O.from,O.to);const Wt={xinyue:Number(((de=(I=j.state)==null?void 0:I.positions)==null?void 0:de.xinyue)||0),du:Number(((xe=(pe=j.state)==null?void 0:pe.positions)==null?void 0:xe.du)||0)};for(const $e of ct){const ot=Number(c[$e]||0),lt=Number(Wt[$e]||0);ot!==lt&&await _e(c,$e,ot,lt)}y(j);const rt=ds(j.player_text||"",O);rt&&H(rt),i.notifyAfterUserRoll!==!1&&p==="xinyue"&&!((N=j.state)!=null&&N.game_over)&&(d=j)}catch(j){s(`掷骰失败：${(j==null?void 0:j.message)||j}`)}finally{C(!1),re(!1),window.setTimeout(()=>ee(null),260)}d&&await ge(d)},[_e,Ee,b,y,m,F,ge,w.positions,w.turn_actor,s]);x.useEffect(()=>{h.current=Ce},[Ce]);const U=x.useCallback(async(i,d={})=>{if(m||!(o!=null&&o.state))return;let u=null;C(!0),H(null);try{const p=await M(i);if(u=p,y(p),p.ok===!1){s(Pe(p,"这次操作没有生效。"));return}Be(""),d.success&&v({id:z("system"),speaker:"system",text:d.success},!0)}catch(p){s(`处理惩罚任务失败：${(p==null?void 0:p.message)||p}`)}finally{C(!1)}u&&d.notify&&await ge(u,d.notifyMessage||"小玥处理了涩涩走格棋的惩罚任务。")},[v,y,m,ge,o==null?void 0:o.state,s]),Pt=x.useCallback(()=>{const i=ke.trim();if(!i){s("先写提交内容。");return}U(`submit ${i}`,{success:"已提交任务，等渡验收。",notify:!0,notifyMessage:"小玥提交了惩罚任务，请你验收。"})},[U,ke,s]),Tt=x.useCallback(()=>{U("approve",{success:"你通过了任务，棋局继续。",notify:!0,notifyMessage:"小玥通过了你的惩罚任务。"})},[U]),Mt=x.useCallback(()=>{U("reject",{success:"你打回了任务，等渡重新提交。",notify:!0,notifyMessage:"小玥打回了你的惩罚任务，请重新提交。"})},[U]),At=x.useCallback(i=>{const d=(_==null?void 0:_.type)==="duel",u=(_==null?void 0:_.current_actor)||(_==null?void 0:_.actor);if(d&&!(d&&u==="xinyue")){s("等待渡出拳。");return}U(`choose ${i}`,{success:d?"已出拳，等待渡出拳。":"已选择惩罚，棋局继续。",notify:!0,notifyMessage:d?"小玥已在剪刀石头布对抗中出拳。请第一行单独发送【剪刀石头布：石头】、【剪刀石头布：剪刀】或【剪刀石头布：布】；描述另起一行写成【描述：...】。":"小玥处理完选择惩罚，棋局继续。"})},[U,_==null?void 0:_.actor,_==null?void 0:_.current_actor,_==null?void 0:_.type,s]),Dt=x.useCallback(()=>{U("pass",{success:"已使用Pass卡跳过惩罚。",notify:!0,notifyMessage:"小玥使用Pass卡跳过了惩罚任务。"})},[U]),Rt=x.useCallback(async()=>{var d,u,p;const i=((d=o==null?void 0:o.state)==null?void 0:d.final_note)||null;if(!(P||m||b||!(o!=null&&o.state)||!i||i.sent)){V(!0);try{const c=await X({mode:"final_note",message:i.text||""},o.state);c.state&&y({ok:!0,state:c.state,player_text:c.player_text||o.player_text||""}),v({id:z("system"),speaker:"system",text:J?"预览模式：终局小纸条已同步。":"终局小纸条已发送给渡。"},!0);const r=ie(c.reply_text||((u=c.wakeup)==null?void 0:u.reply_text)||c.reply_preview||((p=c.wakeup)==null?void 0:p.reply_preview)||"").trim();r&&v({id:z("du"),speaker:"du",text:r},!0),le(!1)}catch(c){const r=String((c==null?void 0:c.message)||c||"同步失败");v({id:z("system"),speaker:"system",text:`小纸条发送失败：${r}`},!0),s(`发送终局小纸条失败：${r}`)}finally{V(!1)}}},[b,v,y,m,P,J,o,X,s]),Lt=x.useCallback(async(i,d,u=1)=>{if(P||m||b||!(o!=null&&o.state))return;const p=d.replace(/\s+/g," ").trim();if(!p){s("先选要追加的内容。");return}const c=i==="prop"&&kt(p)?` level=${Math.max(1,Math.min(5,Math.round(Number(u)||1)))}`:"";C(!0);try{const r=await M(`append_final_status ${i} ${p}${c}`);y(r),le(!0),s(`已启用：${p}`)}catch(r){s(`追加失败：${(r==null?void 0:r.message)||r}`)}finally{C(!1)}},[b,y,m,P,o==null?void 0:o.state,s]),Bt=x.useCallback(async(i,d)=>{if(P||m||b||!(o!=null&&o.state))return;const u=d.replace(/\s+/g," ").trim();if(u){C(!0);try{const p=await M(`remove_final_status ${i} ${u}`);y(p),le(!0),s(`已取消：${u}`)}catch(p){s(`取消失败：${(p==null?void 0:p.message)||p}`)}finally{C(!1)}}},[b,y,m,P,o==null?void 0:o.state,s]),It=x.useCallback(async()=>{var u,p;if(P||m||b||!(o!=null&&o.state))return;const i=he.trim();if(!i)return;const d={id:z("me"),speaker:"xinyue",text:i};Ae(""),v(d),V(!0);try{const c=await X({mode:"chat",message:i},o.state);c.state&&y({ok:!0,state:c.state,player_text:c.player_text||o.player_text||""});const r=ie(c.reply_text||((u=c.wakeup)==null?void 0:u.reply_text)||c.reply_preview||((p=c.wakeup)==null?void 0:p.reply_preview)||"").trim();await ae(r,c.state||o.state)}catch(c){const r=String((c==null?void 0:c.message)||c||"同步失败");v({id:z("system"),speaker:"system",text:`交流失败：${r}`}),s(`游戏内交流失败：${r}`)}finally{V(!1)}},[b,v,y,m,he,P,o,ae,X,s]),Ot=S(((Ve=w.theme_profile)==null?void 0:Ve.theme)||"未触发"),qt=S(((Je=w.theme_profile)==null?void 0:Je.direction_label)||"待定"),Et=pt((Xe=w.positions)==null?void 0:Xe.xinyue,L),Yt=pt((Qe=w.positions)==null?void 0:Qe.du,L),Se=w.winner?Me[w.winner]:"",Fe=gs((o==null?void 0:o.player_text)||""),A=w.final_note||null,Ue=vt(w.final_note_items||[],A),be=String((A==null?void 0:A.id)||`${w.winner||""}-${w.updated_at||""}`),He=!!(F&&w.winner==="xinyue"&&(!A||A.target==="du")&&!(A!=null&&A.sent)),Ft=(((Ze=w.statuses)==null?void 0:Ze.du)||[]).filter(i=>i.slot==="prop").map(i=>S(i.value||""));x.useEffect(()=>{!F||!A||!be||De!==be&&(Nt(be),le(!0))},[A,be,De,F]);const Ut=Math.max(0,Number(((tt=(et=w.hands)==null?void 0:et.xinyue)==null?void 0:tt.pass)||0)),Ht=Math.max(0,Number(w.pass_skips_used||0)),Ke={xinyue:ft((st=w.statuses)==null?void 0:st.xinyue),du:ft((at=w.statuses)==null?void 0:at.du)},We=ce&&Ke.du&&!_,Kt=m||b||P||!(o!=null&&o.state)||!!_||ce&&!We,Ge=P||m||b||!(o!=null&&o.state);return e.jsxs("div",{className:"sese-game",ref:a,children:[e.jsxs("div",{className:"sese-header",children:[e.jsx("button",{className:"sese-back",type:"button",onClick:t,"aria-label":"返回游戏",children:e.jsx(Vt,{})}),e.jsxs("button",{className:"sese-chat-entry",type:"button",onClick:()=>$(!0),"aria-label":"游戏内交流",children:[e.jsx(Jt,{}),Y?e.jsx("span",{children:Y}):null]}),e.jsx("div",{className:"sese-header-title",children:"涩涩走格棋"}),e.jsxs("div",{className:"sese-game-status-bar",children:[e.jsx(ye,{label:"主题",value:Ot}),e.jsx(ye,{label:"主导方",value:qt}),e.jsx(ye,{label:"我 进度",value:`${String(Et).padStart(2,"0")} / ${L}`}),e.jsx(ye,{label:"渡 进度",value:`${String(Yt).padStart(2,"0")} / ${L}`}),e.jsx("div",{className:"sese-turn-indicator",children:F&&Se?`${Se} 到达终点`:ce?"等待 渡 行动...":"轮到 我 行动"})]})]}),e.jsx("section",{className:"sese-board-container","aria-label":"走格棋盘",children:e.jsx("div",{className:"sese-board",style:{gridTemplateColumns:`repeat(${je}, minmax(0, 1fr))`},children:St.map(i=>{const d=ct.filter(u=>Te(W[u],L)===i.position);return e.jsxs("div",{className:`sese-tile sese-tile-${i.kind} ${ue===i.position?"is-active":""}`,children:[e.jsx("div",{className:"sese-tile-number",children:i.position}),e.jsx("div",{className:"sese-tile-icon",children:i.icon}),e.jsx("div",{className:"sese-tile-name",children:i.name}),e.jsx("div",{className:"sese-piece-stack",children:d.map(u=>e.jsx("span",{className:`sese-piece ${u==="xinyue"?"sese-piece-me":"sese-piece-du"} ${Ke[u]?"paused":""}`,children:Me[u]},u))})]},i.position)})})}),e.jsxs("section",{className:"sese-controls",children:[e.jsxs("div",{className:"sese-player-states",children:[e.jsx(gt,{actor:"xinyue",statuses:((it=w.statuses)==null?void 0:it.xinyue)||[],active:Ne==="xinyue"}),e.jsx(gt,{actor:"du",statuses:((nt=w.statuses)==null?void 0:nt.du)||[],active:Ne==="du"})]}),Ue.length?e.jsx("div",{className:"sese-final-pose-panel",children:Ue.map(i=>e.jsxs("div",{className:"sese-final-material-row",children:[e.jsx("span",{children:i.label}),e.jsx("strong",{children:i.values.join("、")})]},i.label))}):null,e.jsxs("div",{className:"sese-action-area",children:[e.jsx("div",{className:`sese-dice ${G?"rolling":""}`,"aria-label":`骰子 ${q}`,children:q}),e.jsx("button",{className:"sese-roll-button",type:"button",disabled:Kt,onClick:F?ze:()=>void Ce({notifyAfterUserRoll:!0}),children:F?"开新局":_?"先处理任务":We?"处理停步":ce?"等渡掷骰":m||b?"移动中":P?"等渡回应":"掷骰子"}),e.jsx("button",{className:"sese-restart-button",type:"button",disabled:m||b||P,onClick:ze,children:"重开"})]}),e.jsx("div",{className:"sese-history",children:Fe.length?`最近：${Fe[0]}`:"最近：等待第一次掷骰"})]}),K?e.jsx("div",{className:"sese-chat-mask",role:"dialog","aria-modal":"true","aria-label":"游戏内交流",onClick:()=>$(!1),children:e.jsxs("div",{className:"sese-chat-panel",onClick:i=>i.stopPropagation(),children:[e.jsxs("div",{className:"sese-chat-head",children:[e.jsxs("div",{children:[e.jsx("strong",{children:"游戏内交流"}),e.jsx("span",{children:ce?"等待渡发送【掷骰】":"当前轮到你行动"})]}),e.jsx("button",{type:"button",onClick:()=>$(!1),"aria-label":"关闭交流",children:"×"})]}),e.jsxs("div",{className:"sese-chat-list",children:[Ie.map(i=>e.jsxs("div",{className:`sese-chat-message ${i.speaker}`,children:[e.jsx("span",{children:i.speaker==="xinyue"?"我":i.speaker==="du"?"渡":"系统"}),e.jsx("p",{children:ie(i.text)})]},i.id)),P?e.jsxs("div",{className:"sese-chat-message du pending",children:[e.jsx("span",{children:"渡"}),e.jsx("p",{children:"正在回复..."})]}):null,e.jsx("div",{ref:l})]}),e.jsxs("form",{className:"sese-chat-form",onSubmit:i=>{i.preventDefault(),It()},children:[e.jsx("input",{value:he,disabled:Ge,placeholder:"和渡说一句游戏内的话",onChange:i=>Ae(i.target.value)}),e.jsx("button",{type:"submit",disabled:Ge||!he.trim(),"aria-label":P?"发送中":"发送",children:e.jsx(Xt,{})})]})]})}):null,se?e.jsx("div",{className:"sese-theme-mask",role:"dialog","aria-modal":"true","aria-label":"开局主题抽取",children:e.jsxs("div",{className:"sese-theme-modal",children:[e.jsxs("div",{className:"sese-slot-lights","aria-hidden":"true",children:[e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{})]}),e.jsxs("div",{className:"sese-slot-marquee",children:[e.jsx("span",{children:"THEME"}),e.jsx("strong",{children:"JACKPOT"})]}),e.jsxs("div",{className:"sese-slot-face",children:[e.jsx("div",{className:"sese-theme-window",children:e.jsx("div",{className:"sese-theme-strip",children:se.items.map((i,d)=>e.jsx("div",{className:"sese-theme-item",children:S(i)},`${i}-${d}`))},se.spinKey)}),e.jsxs("p",{className:"sese-slot-plaque",children:["主导方：",se.direction]}),e.jsxs("div",{className:"sese-theme-actions",children:[e.jsx("button",{className:"secondary",type:"button",disabled:m,onClick:ze,children:m?"重抽中":"重抽主题"}),e.jsx("button",{type:"button",onClick:()=>oe(null),children:"开始本局"})]}),e.jsx("div",{className:"sese-slot-tray","aria-hidden":"true"})]})]})}):null,_&&!k?e.jsx("div",{className:"sese-pending-mask",role:"dialog","aria-modal":"true","aria-label":"待处理惩罚",children:e.jsx("div",{className:"sese-pending-modal",children:e.jsx(Cs,{pending:_,passCount:Ut,passSkipsUsed:Ht,submission:ke,disabled:m,onSubmissionChange:Be,onSubmit:Pt,onApprove:Tt,onReject:Mt,onChoose:At,onPass:Dt})})}):null,F&&A&&jt?e.jsx("div",{className:"sese-final-note-mask",role:"dialog","aria-modal":"true","aria-label":"终局小纸条",children:e.jsxs("div",{className:"sese-final-note-modal",children:[e.jsxs("div",{className:"sese-final-note-head",children:[e.jsx("span",{children:"终局小纸条"}),e.jsx("button",{type:"button",onClick:()=>le(!1),"aria-label":"关闭终局小纸条",children:"关闭"})]}),e.jsxs("h2",{children:[Se||"玩家"," 到达终点"]}),e.jsx(js,{note:A,canAddStatus:He,onAddStatus:()=>Re(!0)}),A.sent?e.jsx("em",{children:"已发送给渡"}):e.jsx("button",{className:"sese-final-note-send",type:"button",disabled:P||m||b,onClick:()=>void Rt(),children:P?"发送中":"发送给渡"})]})}):null,He&&_t?e.jsx(ks,{level:Le,activeProps:Ft,disabled:P||m||b,onClose:()=>Re(!1),onLevelChange:zt,onToggleProp:(i,d)=>{d?Bt("prop",i):Lt("prop",i,Le)}}):null,k?e.jsx("div",{className:"sese-popup-mask",role:"dialog","aria-modal":"true",children:e.jsxs("div",{className:`sese-popup ${k.kind==="draw"?`sese-popup-draw tone-${k.tone||"penalty"}`:""}`,children:[e.jsx("div",{className:"sese-popup-kicker",children:T(k.kicker||(k.actorLabel?`${k.actorLabel}走到第 ${k.position} 格`:`第 ${k.position} 格`))}),k.kind==="draw"?e.jsx("div",{className:`sese-draw-card ${k.tone==="reward"&&!Z?"is-covered":"is-revealed"}`,children:k.tone==="reward"&&!Z?e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"sese-card-pile","aria-hidden":"true",children:[e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("b",{})]}),e.jsx("span",{children:"奖励抽卡"}),e.jsx("em",{children:"抽卡中"})]}):e.jsxs(e.Fragment,{children:[xt(k)?e.jsx("span",{children:xt(k)}):null,e.jsx("strong",{children:T(k.cardTitle||k.title)})]})}):null,k.kind==="draw"?null:e.jsx("h2",{children:T(k.title)}),k.tone==="reward"&&!Z?e.jsx("p",{children:"正在洗牌..."}):ut(k)?e.jsx("p",{children:ut(k)}):null,k.tone==="reward"&&!Z?null:e.jsx("button",{type:"button",onClick:$t,children:"确 认"})]})}):null,e.jsx("style",{children:`
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
          --sese-safe-top: max(calc(env(safe-area-inset-top, 0px) + 12px), 44px);
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
          padding: var(--sese-safe-top) 14px calc(env(safe-area-inset-bottom, 0px) + 22px);
        }
        .sese-game,
        .sese-game * {
          box-sizing: border-box;
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
        .sese-tile-reset { background: #ffe0ec; }
        .sese-tile-finish-jump { background: #fff3b0; }
        .sese-tile-swap { background: #e0f2f1; }
        .sese-tile-clear { background: #ffffff; }
        .sese-tile-time { background: #fff7dd; }
        .sese-tile-limit { background: #ffe3ea; }
        .sese-tile-pose { background: #edf7ff; }
        .sese-tile-theme { background: #f6e9ff; }
        .sese-tile-empty {
          border-color: rgba(255, 255, 255, 0.55);
          background: rgba(255, 255, 255, 0.46);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.62);
        }
        .sese-tile-empty .sese-tile-icon {
          display: none;
        }
        .sese-tile-empty .sese-tile-name {
          color: rgba(136, 77, 138, 0.38);
          font-weight: 700;
        }
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
        .sese-player-card-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          margin: 0 0 7px;
        }
        .sese-player-card h2 {
          margin: 0;
          color: var(--text-main);
          font-size: 14px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-status-list {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .sese-status-empty {
          border-radius: 12px;
          background: rgba(248, 187, 208, 0.22);
          padding: 6px 7px;
          color: #7c4a80;
          font-size: 11px;
          font-weight: 800;
          line-height: 1.25;
        }
        .sese-status-group {
          display: grid;
          gap: 4px;
        }
        .sese-status-group-label {
          color: rgba(124, 74, 128, 0.62);
          font-size: 10px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-status-chip-row {
          display: flex;
          flex-wrap: wrap;
          gap: 4px;
        }
        .sese-status-chip {
          display: inline-flex;
          align-items: center;
          box-sizing: border-box;
          max-width: 100%;
          min-height: 22px;
          border-radius: 999px;
          background: rgba(248, 187, 208, 0.26);
          color: #7c4a80;
          padding: 4px 7px;
          font-size: 11px;
          font-weight: 800;
          line-height: 1.2;
        }
        .sese-pending-mask {
          position: fixed;
          inset: 0;
          z-index: 92;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(136, 77, 138, 0.34);
          padding: max(env(safe-area-inset-top, 0px), 18px) 18px max(env(safe-area-inset-bottom, 0px), 18px);
          backdrop-filter: blur(6px);
        }
        .sese-pending-modal {
          width: min(360px, 100%);
        }
        .sese-pending-modal .sese-pending-card {
          border-width: 4px;
          border-radius: var(--radius-lg);
          background: rgba(255, 255, 255, 0.97);
          padding: 18px;
          box-shadow: 0 20px 40px rgba(0,0,0,0.2);
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
          --sese-safe-top: max(calc(env(safe-area-inset-top, 0px) + 12px), 44px);
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
          padding: var(--sese-safe-top) 16px 18px;
        }
        .sese-back {
          position: absolute;
          left: 10px;
          top: var(--sese-safe-top);
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
          top: var(--sese-safe-top);
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
          padding: 14px 12px 20px;
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
        .sese-tile-reset { background: #ffe0ec; }
        .sese-tile-finish-jump { background: #fff3b0; }
        .sese-tile-empty {
          border-color: rgba(255,255,255,0.45);
          background: rgba(255,255,255,0.42);
          box-shadow: inset 0 0 0 1px rgba(255,255,255,0.26);
        }
        .sese-tile-empty .sese-tile-icon {
          display: none;
        }
        .sese-tile-empty .sese-tile-name {
          color: rgba(136, 77, 138, 0.42);
          font-weight: 400;
        }
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
        .sese-final-pose-panel {
          display: grid;
          gap: 4px;
          border-radius: var(--radius-md);
          background: rgba(255, 249, 196, 0.72);
          padding: 8px 10px;
          color: var(--text-main);
        }
        .sese-final-material-row {
          display: grid;
          gap: 2px;
        }
        .sese-final-pose-panel span {
          color: var(--text-light);
          font-size: 10px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-final-pose-panel strong {
          font-size: 11px;
          font-weight: 900;
          line-height: 1.35;
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
        .sese-player-card-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 6px;
          margin: 0 0 4px;
        }
        .sese-player-card h2 {
          margin: 0;
          color: var(--text-main);
          font-size: 11px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-status-list {
          display: grid;
          gap: 4px;
        }
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
        .sese-status-group {
          display: grid;
          gap: 3px;
        }
        .sese-status-group-label {
          color: var(--text-light);
          font-size: 9px;
          font-weight: 700;
          line-height: 1.2;
        }
        .sese-status-chip-row {
          display: flex;
          flex-wrap: wrap;
          gap: 3px;
        }
        .sese-status-chip {
          display: inline-flex;
          align-items: center;
          box-sizing: border-box;
          max-width: 100%;
          border: 1px solid rgba(0,0,0,0.05);
          border-radius: 999px;
          background: var(--soft-lavender);
          color: var(--text-main);
          padding: 2px 6px;
          font-size: 9px;
          font-weight: 400;
          line-height: 1.2;
        }
        .sese-pending-card {
          border: 2px solid rgba(248, 187, 208, 0.9);
          border-radius: var(--radius-md);
          background: rgba(255, 255, 255, 0.9);
          padding: 10px;
          box-shadow: var(--shadow-soft);
        }
        .sese-pending-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          margin-bottom: 6px;
        }
        .sese-pending-head span {
          flex: 0 0 auto;
          border-radius: 999px;
          background: var(--accent-yellow);
          padding: 3px 7px;
          color: var(--text-main);
          font-size: 9px;
          font-weight: 900;
          line-height: 1;
        }
        .sese-pending-head strong {
          min-width: 0;
          overflow: hidden;
          color: var(--text-main);
          font-size: 13px;
          font-weight: 900;
          line-height: 1.2;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .sese-pending-card p,
        .sese-pending-tip,
        .sese-pending-wait {
          margin: 0;
          color: #7c4a80;
          font-size: 11px;
          font-weight: 700;
          line-height: 1.45;
        }
        .sese-pending-tip,
        .sese-pending-wait {
          margin-top: 6px;
          border-radius: 10px;
          background: var(--soft-lavender);
          padding: 6px 8px;
        }
        .sese-submission-text {
          min-height: 44px;
          white-space: pre-wrap;
          word-break: break-word;
        }
        .sese-pending-card textarea {
          display: block;
          width: 100%;
          min-height: 82px;
          margin-top: 8px;
          resize: vertical;
          border: 1px solid rgba(186, 104, 200, 0.24);
          border-radius: 12px;
          background: #fff;
          color: var(--text-main);
          padding: 8px 10px;
          font-size: 12px;
          line-height: 1.45;
          outline: none;
        }
        .sese-choice-list,
        .sese-review-actions {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 8px;
          margin-top: 9px;
        }
        .sese-choice-list button,
        .sese-review-actions button,
        .sese-pass-button {
          min-height: 36px;
          border: 0;
          border-radius: 14px;
          background: var(--primary-pink);
          color: #fff;
          padding: 7px 9px;
          font-size: 11px;
          font-weight: 900;
          line-height: 1.25;
          box-shadow: 0 3px 0 #d81b60;
        }
        .sese-choice-list button:disabled,
        .sese-review-actions button:disabled,
        .sese-pass-button:disabled {
          opacity: 0.5;
        }
        .sese-rps-list {
          grid-template-columns: repeat(3, minmax(0, 1fr));
        }
        .sese-choice-list .sese-rps-button {
          min-height: 54px;
          border-radius: 18px;
          background: #ffffff;
          color: var(--text-main);
          font-size: 26px;
          line-height: 1;
          box-shadow: inset 0 0 0 2px rgba(248, 187, 208, 0.82), 0 4px 0 #f48fb1;
        }
        .sese-choice-list .sese-rps-button.is-selected {
          background: var(--primary-pink);
          color: #ffffff;
          box-shadow: inset 0 0 0 2px #ffffff, 0 4px 0 #d81b60;
          transform: translateY(1px);
        }
        .sese-choice-list .sese-rps-button.is-selected:disabled {
          opacity: 1;
        }
        .sese-pass-button {
          width: 100%;
          margin-top: 8px;
          background: #ba68c8;
          box-shadow: 0 3px 0 #8e24aa;
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
        .sese-restart-button {
          flex: 0 0 46px;
          height: 42px;
          border: 0;
          border-radius: 21px;
          background: #fff;
          color: var(--text-main);
          font-size: 12px;
          font-weight: 900;
          box-shadow: 0 3px 0 rgba(136, 77, 138, 0.18);
        }
        .sese-restart-button:disabled {
          opacity: 0.5;
        }
        .sese-theme-mask {
          position: fixed;
          inset: 0;
          z-index: 105;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(136, 77, 138, 0.42);
          padding: max(env(safe-area-inset-top, 0px), 18px) 18px max(env(safe-area-inset-bottom, 0px), 18px);
          backdrop-filter: blur(6px);
        }
        .sese-theme-modal {
          position: relative;
          width: min(380px, calc(100vw - 54px));
          border: 5px solid #ffffff;
          border-radius: 32px 32px 26px 26px;
          background: #e975a5;
          padding: 13px 16px 18px;
          text-align: center;
          box-shadow:
            0 24px 50px rgba(73, 34, 81, 0.32),
            inset 0 2px 0 rgba(255,255,255,0.74),
            inset 0 -7px 0 rgba(174, 42, 100, 0.28);
        }
        .sese-slot-lights {
          display: flex;
          justify-content: center;
          gap: 7px;
          margin-bottom: 8px;
        }
        .sese-slot-lights i {
          width: 11px;
          height: 11px;
          border: 2px solid rgba(255,255,255,0.86);
          border-radius: 50%;
          background: #fff7a8;
          box-shadow: 0 0 12px rgba(255, 247, 168, 0.88);
          animation: seseSlotLight 900ms ease-in-out infinite alternate;
        }
        .sese-slot-lights i:nth-child(2),
        .sese-slot-lights i:nth-child(4) {
          background: #ffffff;
          animation-delay: 180ms;
        }
        .sese-slot-marquee {
          display: grid;
          grid-template-columns: 1fr;
          gap: 2px;
          margin-bottom: 10px;
          border: 3px solid #7b3c78;
          border-radius: 18px;
          background: #fff2ac;
          padding: 7px 12px;
          box-shadow: inset 0 -4px 0 rgba(123,60,120,0.16), 0 5px 0 rgba(123,60,120,0.22);
        }
        .sese-slot-marquee span,
        .sese-slot-marquee strong {
          color: #7b3c78;
          line-height: 1;
          letter-spacing: 0;
        }
        .sese-slot-marquee span {
          font-size: 10px;
          font-weight: 900;
        }
        .sese-slot-marquee strong {
          font-size: 20px;
          font-weight: 900;
        }
        .sese-slot-face {
          position: relative;
          border: 4px solid rgba(255,255,255,0.88);
          border-radius: 24px;
          background: #fff4fa;
          padding: 13px;
          box-shadow:
            inset 0 0 0 2px rgba(216, 95, 146, 0.16),
            0 8px 0 rgba(157, 47, 103, 0.25);
        }
        .sese-reel-bank {
          display: grid;
          grid-template-columns: 58px minmax(0, 1fr) 58px;
          gap: 7px;
          border: 4px solid #7b3c78;
          border-radius: 20px;
          background: #7b3c78;
          padding: 7px;
          box-shadow: inset 0 0 0 2px rgba(255,255,255,0.22);
        }
        .sese-theme-window {
          position: relative;
          height: 70px;
          margin: 0;
          overflow: hidden;
          border: 3px solid #fff;
          border-radius: 14px;
          background: #fff;
          box-shadow:
            inset 0 8px 12px rgba(74, 34, 78, 0.12),
            inset 0 -8px 12px rgba(74, 34, 78, 0.1);
        }
        .sese-theme-window-main {
          border-width: 4px;
        }
        .sese-theme-window-side {
          background: #fff7c8;
        }
        .sese-theme-window::before,
        .sese-theme-window::after {
          content: "";
          position: absolute;
          left: 0;
          right: 0;
          z-index: 2;
          height: 16px;
          pointer-events: none;
        }
        .sese-theme-window::before {
          top: 0;
          border-top: 5px solid rgba(123,60,120,0.18);
        }
        .sese-theme-window::after {
          bottom: 0;
          border-bottom: 5px solid rgba(123,60,120,0.16);
        }
        .sese-theme-strip {
          animation: seseThemeSpin 1200ms cubic-bezier(0.16, 1, 0.3, 1) both;
        }
        .sese-theme-item {
          display: flex;
          align-items: center;
          justify-content: center;
          height: 70px;
          color: var(--text-main);
          font-size: 18px;
          font-weight: 900;
          line-height: 1;
          text-align: center;
          word-break: keep-all;
          padding: 0 8px;
        }
        .sese-theme-window-side .sese-theme-item {
          color: #9b3f78;
          font-size: 12px;
          padding: 0 3px;
        }
        .sese-slot-plaque {
          margin: 12px 0 10px;
          border-radius: 14px;
          background: #f3e5f5;
          color: #7c4a80;
          padding: 8px 10px;
          font-size: 13px;
          font-weight: 900;
        }
        .sese-theme-actions {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
        }
        .sese-theme-modal button {
          min-width: 0;
          min-height: 38px;
          border: 0;
          border-radius: 16px;
          background: #ff6f9f;
          color: #fff;
          padding: 8px 12px;
          font-size: 12px;
          font-weight: 900;
          box-shadow: 0 4px 0 #bd3367;
        }
        .sese-theme-modal button.secondary {
          background: #ffffff;
          color: #7b3c78;
          box-shadow: 0 4px 0 rgba(123,60,120,0.22);
        }
        .sese-theme-modal button:disabled {
          opacity: 0.52;
          box-shadow: none;
        }
        .sese-slot-tray {
          width: 70px;
          height: 11px;
          margin: 13px auto 0;
          border-radius: 999px;
          background: #7b3c78;
          box-shadow: inset 0 3px 0 rgba(0,0,0,0.18), 0 2px 0 rgba(255,255,255,0.54);
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
          padding: calc(var(--sese-safe-top) + 42px) 14px 14px;
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
        .sese-final-note-mask {
          position: fixed;
          inset: 0;
          z-index: 110;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(136, 77, 138, 0.34);
          padding: 18px;
          backdrop-filter: blur(4px);
        }
        .sese-final-note-modal {
          width: min(430px, 100%);
          border: 4px solid var(--primary-pink);
          border-radius: var(--radius-lg);
          background: rgba(255, 255, 255, 0.96);
          padding: 22px;
          box-shadow: 0 18px 36px rgba(136, 77, 138, 0.22);
        }
        .sese-final-note-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
        }
        .sese-final-note-head span {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          height: 24px;
          padding: 0 12px;
          border-radius: 999px;
          background: #fff9c4;
          color: var(--text-main);
          font-size: 11px;
          font-weight: 900;
        }
        .sese-final-note-head button {
          height: 28px;
          border: 0;
          border-radius: 14px;
          background: rgba(240, 98, 146, 0.12);
          color: var(--text-light);
          padding: 0 10px;
          font-size: 12px;
          font-weight: 900;
        }
        .sese-final-note-modal h2 {
          margin: 12px 0 10px;
          color: var(--text-main);
          font-size: 22px;
          line-height: 1.18;
          text-align: center;
        }
        .sese-final-note-body {
          display: grid;
          gap: 10px;
          margin-top: 12px;
        }
        .sese-final-note-intro,
        .sese-final-note-closing {
          border-radius: 16px;
          background: #fff7fb;
          color: #875183;
          padding: 10px 12px;
          font-size: 13px;
          font-weight: 900;
          line-height: 1.55;
        }
        .sese-final-note-section {
          display: grid;
          gap: 9px;
          border: 1px solid #f3c6dd;
          border-radius: 18px;
          background: #fff;
          padding: 11px 12px;
        }
        .sese-final-note-section > span {
          color: #b45a91;
          font-size: 11px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-final-note-section-title {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
        }
        .sese-final-note-section-title > span {
          color: #b45a91;
          font-size: 11px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-final-note-section-title > button {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          flex: 0 0 auto;
          width: 26px;
          height: 26px;
          border: 0;
          border-radius: 50%;
          background: #f8a9c6;
          color: #fff;
          box-shadow: 0 3px 0 #d81b60;
        }
        .sese-final-note-section-title > button svg {
          width: 15px;
          height: 15px;
          fill: none;
          stroke: currentColor;
          stroke-width: 3;
          stroke-linecap: round;
        }
        .sese-final-note-section-title > button:active {
          transform: translateY(1px);
          box-shadow: 0 2px 0 #d81b60;
        }
        .sese-final-note-section > strong {
          color: var(--text-main);
          font-size: 14px;
          line-height: 1.35;
        }
        .sese-final-note-status-group {
          display: grid;
          gap: 7px;
        }
        .sese-final-note-status-group > b {
          justify-self: start;
          border-radius: 999px;
          background: #fff1f7;
          color: #8d4a86;
          padding: 4px 9px;
          font-size: 11px;
          line-height: 1.2;
        }
        .sese-final-note-status-values {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .sese-final-note-status-values span {
          display: inline-flex;
          align-items: center;
          box-sizing: border-box;
          max-width: 100%;
          border-radius: 999px;
          background: #f8edf6;
          color: #795078;
          padding: 6px 10px;
          font-size: 12px;
          line-height: 1.25;
          word-break: break-word;
        }
        .sese-final-note-empty {
          color: #9b7598;
          font-size: 12px;
          line-height: 1.45;
        }
        .sese-final-note-closing {
          text-align: center;
          background: #fff9c4;
        }
        .sese-toy-console-mask {
          position: fixed;
          inset: 0;
          z-index: 125;
          display: flex;
          align-items: flex-end;
          justify-content: center;
          background: rgba(74, 37, 70, 0.28);
          padding: 14px;
          backdrop-filter: blur(4px);
        }
        .sese-toy-console-sheet {
          width: min(460px, 100%);
          max-height: min(78vh, 620px);
          overflow: auto;
          border: 3px solid #f4a9c5;
          border-radius: 28px 28px 20px 20px;
          background: #fffafc;
          padding: 18px;
          box-shadow: 0 18px 42px rgba(112, 63, 105, 0.24);
        }
        .sese-toy-console-head {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 14px;
        }
        .sese-toy-console-head div {
          display: grid;
          gap: 5px;
        }
        .sese-toy-console-head span {
          color: var(--text-main);
          font-size: 20px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-toy-console-head strong {
          color: #9b6b97;
          font-size: 12px;
          font-weight: 900;
          line-height: 1.35;
        }
        .sese-toy-console-head button {
          flex: 0 0 auto;
          height: 30px;
          border: 0;
          border-radius: 15px;
          background: #fce5ef;
          color: var(--text-light);
          padding: 0 11px;
          font-size: 12px;
          font-weight: 900;
        }
        .sese-toy-console-section {
          display: grid;
          gap: 9px;
          margin-top: 14px;
        }
        .sese-toy-console-section label {
          color: #8d4a86;
          font-size: 12px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-toy-level-row,
        .sese-toy-chip-grid {
          display: grid;
          gap: 8px;
        }
        .sese-toy-level-row {
          grid-template-columns: repeat(5, minmax(0, 1fr));
        }
        .sese-toy-chip-grid {
          grid-template-columns: repeat(3, minmax(0, 1fr));
        }
        .sese-toy-level-row button,
        .sese-toy-chip-grid button {
          min-height: 38px;
          border: 2px solid #f1c2d6;
          border-radius: 14px;
          background: #fff;
          color: var(--text-main);
          padding: 7px 9px;
          font-size: 12px;
          font-weight: 900;
          line-height: 1.25;
          box-shadow: 0 3px 0 rgba(216, 27, 96, 0.18);
        }
        .sese-toy-level-row button.selected,
        .sese-toy-chip-grid button.selected {
          border-color: #e91e63;
          background: #f8a9c6;
          color: #fff;
          box-shadow: 0 3px 0 #d81b60;
        }
        .sese-toy-level-row button:disabled,
        .sese-toy-chip-grid button:disabled {
          opacity: 0.58;
        }
        .sese-final-note-modal em {
          display: block;
          margin-top: 18px;
          color: var(--text-light);
          font-size: 13px;
          font-style: normal;
          font-weight: 900;
          text-align: center;
        }
        .sese-final-note-send {
          width: 100%;
          height: 46px;
          margin-top: 18px;
          border: 0;
          border-radius: 23px;
          background: #f06292;
          color: #fff;
          font-size: 15px;
          font-weight: 900;
          box-shadow: 0 4px 0 #d81b60;
        }
        .sese-final-note-send:disabled {
          opacity: 0.58;
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
        .sese-popup-draw {
          overflow: hidden;
        }
        .sese-popup-kicker {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          margin: 0 auto 10px;
          border-radius: 999px;
          background: var(--accent-yellow);
          padding: 5px 12px;
          color: var(--text-main);
          font-size: 12px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-draw-card {
          margin: 0 auto 14px;
          border-radius: 18px;
          background: var(--soft-lavender);
          padding: 16px 12px;
          box-shadow: inset 0 0 0 2px rgba(248, 187, 208, 0.8);
          animation: seseDrawCard 420ms cubic-bezier(0.16, 1, 0.3, 1) both;
        }
        .sese-draw-card.is-covered {
          min-height: 118px;
          border: 3px solid #ffffff;
          background: #e975a5;
          box-shadow:
            inset 0 0 0 3px rgba(123,60,120,0.18),
            inset 0 -6px 0 rgba(123,60,120,0.18),
            0 8px 0 rgba(123,60,120,0.22);
          animation: seseDrawCard 360ms cubic-bezier(0.16, 1, 0.3, 1) both, seseCardPulse 740ms ease-in-out infinite alternate;
        }
        .sese-card-pile {
          position: relative;
          width: 132px;
          height: 94px;
          margin: 2px auto 12px;
        }
        .sese-card-pile i,
        .sese-card-pile b {
          position: absolute;
          display: block;
          width: 62px;
          height: 82px;
          border: 3px solid #ffffff;
          border-radius: 12px;
          background: #fff2ac;
          box-shadow: 0 5px 0 rgba(123,60,120,0.16), inset 0 -5px 0 rgba(123,60,120,0.1);
        }
        .sese-card-pile i:nth-child(1) {
          left: 13px;
          top: 9px;
          transform: rotate(-9deg);
          background: #f3e5f5;
        }
        .sese-card-pile i:nth-child(2) {
          left: 18px;
          top: 6px;
          transform: rotate(-4deg);
          background: #fff2ac;
        }
        .sese-card-pile i:nth-child(3) {
          left: 23px;
          top: 3px;
          transform: rotate(3deg);
          background: #ffe0ec;
        }
        .sese-card-pile i:nth-child(4) {
          left: 28px;
          top: 0;
          transform: rotate(7deg);
          background: #ffffff;
        }
        .sese-card-pile b {
          left: 52px;
          top: 3px;
          z-index: 2;
          background: #fff7c8;
          animation: seseCardDrawOut 900ms cubic-bezier(0.16, 1, 0.3, 1) both;
        }
        .sese-draw-card span {
          display: block;
          color: var(--text-light);
          font-size: 11px;
          font-weight: 900;
          line-height: 1;
        }
        .sese-draw-card strong {
          display: block;
          margin-top: 8px;
          color: var(--text-main);
          font-size: 20px;
          font-weight: 900;
          line-height: 1.2;
        }
        .sese-draw-card em {
          display: block;
          margin-top: 8px;
          color: #fff;
          font-size: 12px;
          font-style: normal;
          font-weight: 900;
        }
        .sese-draw-card.is-covered span,
        .sese-draw-card.is-covered strong {
          color: #fff;
        }
        .sese-draw-card.is-covered strong {
          margin-top: 0;
          font-size: 28px;
        }
        .sese-popup-draw.tone-reward .sese-draw-card {
          background: var(--accent-yellow);
        }
        .sese-popup-draw.tone-reward .sese-draw-card.is-covered {
          background: #e975a5;
        }
        .sese-popup-draw.tone-choice .sese-draw-card {
          background: #f8bbd0;
        }
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
        @keyframes seseThemeSpin {
          from { transform: translateY(0); }
          to { transform: translateY(-490px); }
        }
        @keyframes seseSlotLight {
          from { opacity: 0.58; transform: scale(0.86); }
          to { opacity: 1; transform: scale(1); }
        }
        @keyframes seseDrawCard {
          from { transform: translateY(18px) scale(0.94); opacity: 0; }
          to { transform: translateY(0) scale(1); opacity: 1; }
        }
        @keyframes seseCardPulse {
          from { transform: translateY(0) rotate(-1deg); }
          to { transform: translateY(-3px) rotate(1deg); }
        }
        @keyframes seseCardDrawOut {
          0% { transform: translateX(-18px) rotate(7deg) scale(0.96); opacity: 0.86; }
          58% { transform: translateX(28px) translateY(-10px) rotate(13deg) scale(1); opacity: 1; }
          100% { transform: translateX(36px) translateY(-14px) rotate(10deg) scale(1.04); opacity: 1; }
        }
        `})]})}function ye({label:t,value:s}){return e.jsxs("div",{className:"sese-pill",children:[e.jsx("span",{children:t}),e.jsx("strong",{children:s})]})}function gt({actor:t,statuses:s,active:a}){const n=hs(s);return e.jsxs("div",{className:`sese-player-card sese-player-card-${t} ${a?"active":""}`,children:[e.jsx("div",{className:"sese-player-card-head",children:e.jsx("h2",{children:t==="xinyue"?"我的状态":"渡的状态"})}),e.jsx("div",{className:"sese-status-list",children:n.length?n.map(l=>e.jsxs("div",{className:"sese-status-group",children:[e.jsx("span",{className:"sese-status-group-label",children:l.label}),e.jsx("div",{className:"sese-status-chip-row",children:l.values.map(h=>e.jsx("span",{className:"sese-status-chip",children:h},`${l.label}-${h}`))})]},l.label)):e.jsx("div",{className:"sese-status-empty",children:"无状态"})})]})}function ks({level:t,activeProps:s,disabled:a,onClose:n,onLevelChange:l,onToggleProp:h}){const f=new Set(s);return e.jsx("div",{className:"sese-toy-console-mask",role:"dialog","aria-modal":"true","aria-label":"玩具控制台",onClick:n,children:e.jsxs("div",{className:"sese-toy-console-sheet",onClick:g=>g.stopPropagation(),children:[e.jsxs("div",{className:"sese-toy-console-head",children:[e.jsxs("div",{children:[e.jsx("span",{children:"玩具控制台"}),e.jsx("strong",{children:"控制渡当前状态"})]}),e.jsx("button",{type:"button",onClick:n,"aria-label":"关闭玩具控制台",children:"关闭"})]}),e.jsxs("div",{className:"sese-toy-console-section",children:[e.jsx("label",{children:"道具档位"}),e.jsx("div",{className:"sese-toy-level-row",children:[1,2,3,4,5].map(g=>e.jsx("button",{type:"button",disabled:a,className:g===t?"selected":"",onClick:()=>l(g),children:g},g))})]}),e.jsxs("div",{className:"sese-toy-console-section",children:[e.jsx("label",{children:"启用道具"}),e.jsx("div",{className:"sese-toy-chip-grid",children:ss.map(g=>(()=>{const o=f.has(g);return e.jsx("button",{type:"button",disabled:a,className:o?"selected":"","aria-pressed":o,"aria-label":o?`取消启用${g}`:`启用${g}`,onClick:()=>h(g,o),children:g},g)})())})]})]})})}function js({note:t,canAddStatus:s=!1,onAddStatus:a}){const n=_s(t),l=S(t.theme||"本局主题"),h=t.target==="du"?"渡当前状态":"你的当前状态",f=zs(t.target_status||""),g=vt([],t);return e.jsxs("div",{className:"sese-final-note-body",children:[e.jsx("div",{className:"sese-final-note-intro",children:n}),e.jsxs("div",{className:"sese-final-note-section",children:[e.jsx("span",{children:"本局主题"}),e.jsx("strong",{children:l})]}),e.jsxs("div",{className:"sese-final-note-section",children:[e.jsxs("div",{className:"sese-final-note-section-title",children:[e.jsx("span",{children:h}),s?e.jsx("button",{type:"button",onClick:a,"aria-label":"打开玩具控制台",children:e.jsx(Ns,{})}):null]}),f.length?f.map(o=>e.jsxs("div",{className:"sese-final-note-status-group",children:[e.jsx("b",{children:o.label}),e.jsx("div",{className:"sese-final-note-status-values",children:o.values.map(R=>e.jsx("span",{children:R},R))})]},o.label)):e.jsx("div",{className:"sese-final-note-empty",children:"没有遗留状态，可以自由决定最后玩法。"})]}),g.map(o=>e.jsxs("div",{className:"sese-final-note-section",children:[e.jsx("span",{children:o.label}),e.jsx("strong",{children:o.values.join("、")})]},o.label)),e.jsx("div",{className:"sese-final-note-closing",children:"请尽情享受你们的ooxx吧！"})]})}function Ns(){return e.jsx("svg",{viewBox:"0 0 24 24","aria-hidden":"true",children:e.jsx("path",{d:"M12 5v14M5 12h14"})})}function _s(t){return T(t.text||"").split(`
`).map(n=>n.trim()).filter(Boolean).find(n=>!n.startsWith("【")&&!n.startsWith("请根据")&&!n.startsWith("本局主题")&&!n.startsWith("请尽情"))||"终点已到达，赢家状态已清空。"}function zs(t){const s=T(t).trim();return!s||s==="无"?[]:s.split("；").map(a=>a.trim()).filter(Boolean).map(a=>{const n=a.indexOf("：");if(n<0)return{label:"状态",values:[a]};const l=a.slice(0,n).trim()||"状态",h=a.slice(n+1).split("、").map(f=>f.trim()).filter(Boolean);return{label:l,values:h.length?h:["无"]}})}function Cs({pending:t,passCount:s,passSkipsUsed:a,submission:n,disabled:l,onSubmissionChange:h,onSubmit:f,onApprove:g,onReject:o,onChoose:R,onPass:W}){var oe,K;const B=T(t.name||"惩罚任务"),q=t.actor||"xinyue",Q=t.reviewer||(q==="xinyue"?"du":"xinyue"),m=t.current_actor||q,C=q==="xinyue",G=m==="xinyue",E=Q==="xinyue",b=!!S(t.question_text||"").trim(),re=C&&t.pass_allowed!==!1&&s>0&&a<1&&!["submitted","questioning"].includes(String(t.phase||"")),ue=T(t.submission||"").trim(),ee=/^你的回答[。.]?$/.test(ue)?"":ue,[k,H]=x.useState("");x.useEffect(()=>{H("")},[t.id,t.current_actor,t.phase]);const Z=ne(k||((oe=t.picks)==null?void 0:oe.xinyue)),te=!!ne((K=t.picks)==null?void 0:K.xinyue);if(t.type==="choice")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:C?"你的选择惩罚":"等待渡选择"}),e.jsx("strong",{children:B})]}),e.jsx("p",{children:T(t.prompt||"选择一项惩罚。")}),C?e.jsx("div",{className:"sese-choice-list",children:(t.choices||[]).map($=>{const Y=String($.id||$.label||"");return e.jsx("button",{type:"button",disabled:l||!Y,onClick:()=>R(Y),children:T($.label||Y)},Y)})}):e.jsx("div",{className:"sese-pending-wait",children:"等待渡选择惩罚。"}),re?e.jsx("button",{className:"sese-pass-button",type:"button",disabled:l,onClick:W,children:"使用Pass卡跳过"}):null]});if(t.type==="duel")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:G?"轮到你出拳":"等待渡出拳"}),e.jsx("strong",{children:B||"剪刀石头布对抗"})]}),e.jsx("p",{children:"同格触发对抗。双方各出石头、剪刀或布，系统判定胜负；赢的前进 3 格，输的后退 3 格。"}),e.jsx("div",{className:"sese-choice-list sese-rps-list",children:mt.map($=>e.jsx("button",{className:`sese-rps-button ${Z===$.id?"is-selected":""}`,type:"button",title:$.label,"aria-label":$.label,"aria-pressed":Z===$.id,disabled:l||!G||te,onClick:()=>{H(ne($.id)),R($.id)},children:$.icon},$.id))}),G?null:e.jsx("div",{className:"sese-pending-wait",children:te?"你的出拳已记录，等待渡出拳。":"等待渡出拳。"})]});if(t.phase==="submitted")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:E?"需要你验收":"等待渡验收"}),e.jsx("strong",{children:B})]}),e.jsx("p",{className:"sese-submission-text",children:S(t.submission_text||"")}),E?e.jsxs("div",{className:"sese-review-actions",children:[e.jsx("button",{type:"button",disabled:l,onClick:g,children:"通过"}),e.jsx("button",{type:"button",disabled:l,onClick:o,children:"打回"})]}):e.jsx("div",{className:"sese-pending-wait",children:"等待渡验收你的提交。"})]});if(t.phase==="questioning"){const $=T(t.question_prompt||"请问对方一个你很想知道答案却一直没有问的问题。"),Y=T(t.waiting_task||"对方正在出题中。");return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:E?"你来出题":"等待渡出题"}),e.jsx("strong",{children:B})]}),E?e.jsxs(e.Fragment,{children:[e.jsx("p",{children:$}),e.jsx("textarea",{value:n,disabled:l,placeholder:"写下你的问题",onChange:fe=>h(fe.target.value)}),e.jsx("div",{className:"sese-review-actions",children:e.jsx("button",{type:"button",disabled:l||!n.trim(),onClick:f,children:"提交题目"})})]}):e.jsx("div",{className:"sese-pending-wait",children:Y==="对方正在出题中。"?"等待渡给出真心话题目。":Y})]})}const se=b?"等待渡回答这个问题。":"等待渡完成并提交任务。";return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:C?"你的惩罚任务":"等待渡提交"}),e.jsx("strong",{children:B})]}),b?e.jsxs("p",{className:"sese-submission-text",children:["题目：",S(t.question_text)]}):null,C?e.jsxs(e.Fragment,{children:[b?null:e.jsx("p",{children:T(t.task||"")}),!b&&ee?e.jsxs("div",{className:"sese-pending-tip",children:["提交要求：",ee]}):null,e.jsx("textarea",{value:n,disabled:l,placeholder:b?"在这里写回答":"在这里写提交内容",onChange:$=>h($.target.value)}),e.jsxs("div",{className:"sese-review-actions",children:[e.jsx("button",{type:"button",disabled:l||!n.trim(),onClick:f,children:b?"提交回答":"提交验收"}),re?e.jsx("button",{type:"button",disabled:l,onClick:W,children:"使用Pass卡"}):null]})]}):e.jsx("div",{className:"sese-pending-wait",children:e.jsx("span",{children:se})})]})}export{Ps as SeseBoardGameTab};
