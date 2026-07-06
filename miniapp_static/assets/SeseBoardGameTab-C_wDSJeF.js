import{u as ns,r as u,j as e,C as rs,M as os,S as ls,b as St}from"./index-B7o6aCby.js";const zt="du-gateway:sese-board-game:chat:v1",cs=new Set(["xinyue","du","system"]),ds=[{id:"system-ready",speaker:"system",text:"游戏内交流在这里。渡明确发送【掷骰】时，棋盘才会执行他的行动。"}];function ae(){return ds.map(s=>({...s}))}function ps(){if(typeof window>"u")return ae();try{const s=window.localStorage.getItem(zt);if(!s)return ae();const t=JSON.parse(s);if(!Array.isArray(t))return ae();const i=t.flatMap((n,c)=>{if(!n||typeof n!="object")return[];const f=n,l=typeof f.speaker=="string"?f.speaker:"",g=typeof f.text=="string"?f.text.trim():"";return!cs.has(l)||!g?[]:[{id:(typeof f.id=="string"?f.id.trim():"")||`stored-${c}`,speaker:l,text:g}]});return i.length?i:ae()}catch{return ae()}}function us(s){if(!(typeof window>"u"))try{window.localStorage.setItem(zt,JSON.stringify(s))}catch{}}const mt=["xinyue","du"],Ye={xinyue:"我",du:"渡"},xs={xinyue:0,du:0},Ct=[{id:"scissors",label:"剪刀",icon:"✌️"},{id:"rock",label:"石头",icon:"👊"},{id:"paper",label:"布",icon:"✋"}],fs={rock:"scissors",scissors:"paper",paper:"rock"},hs={scissors:"scissors",剪刀:"scissors","✌️":"scissors","✌":"scissors",rock:"rock",stone:"rock",石头:"rock",拳头:"rock","👊":"rock",paper:"paper",布:"paper",包袱:"paper","✋":"paper"};function ne(s){const t=String(s||"").trim();return t?hs[t]||t:""}function bt(s){var i;const t=ne(s);return((i=Ct.find(n=>n.id===t))==null?void 0:i.label)||String(s||"").trim()||"未出拳"}function gs(s,t){var g;const i=ne((g=s==null?void 0:s.picks)==null?void 0:g.xinyue),n=ne(t);if(!i||!n)return"";const c=bt(i),f=bt(n);if(i===n)return`你出了${c}，渡出了${f}。平局，重新出拳。`;const l=fs[i]===n?"你赢":"渡赢";return`你出了${c}，渡出了${f}。${l}。`}const $t={place:"最终地点",pose:"最终姿势"},ms=["跳蛋","震动乳夹","震动环","乳夹","锁精环","飞机杯","软绳","手腕绑带","眼罩","口球","春药"],bs=["跳蛋","震动","按摩棒","飞机杯","吸乳器","吸吮器"];function $e(s){return new Promise(t=>window.setTimeout(t,s))}function C(s){return String(s||"").replace(/小玥/g,"我")}function T(s){return String(s||"").replace(/小玥/g,"你").replace(/(^|[^自])我/g,"$1你")}function ie(s){return String(s||"")}function Re(s,t){return C(s.player_text||s.text||s.error||"").split(/\r?\n/).map(c=>c.trim()).find(c=>c&&!c.startsWith("【")&&!/^(进度|主题|轮到|手牌|我的状态|渡的状态|最终地点|最终姿势|待处理|可用命令)/.test(c))||t}function z(s){return`${s}-${Date.now()}-${Math.random().toString(36).slice(2,8)}`}function qe(s,t){const i=Math.floor(Number(s||0));return Math.max(1,Math.min(t,i||1))}function wt(s,t){const i=Math.floor(Number(s||0));return Math.max(0,Math.min(t,i||0))}function ws(s,t){const i=[];for(let n=1;n<=s;n+=t){const c=Array.from({length:Math.min(t,s-n+1)},(f,l)=>n+l);i.length%2===1&&c.reverse(),i.push(c)}return i.reverse().flat()}function ys(s,t,i){if(t===1)return"start";if(t===i)return"end";if(!s)return"empty";const n=`${s.kind||""} ${s.slot||""}`.toLowerCase();return/empty/.test(n)?"empty":/finish_self|finish-jump/.test(n)?"finish-jump":/reset/.test(n)?"reset":/swap/.test(n)?"swap":/move|back|forward/.test(n)?"move":/lock|pause|item/.test(n)?"item":/clear/.test(n)?"clear":/extend|time/.test(n)?"time":/limit/.test(n)?"limit":/place/.test(n)?"place":/pose/.test(n)?"pose":/theme/.test(n)?"theme":"task"}function vs(s){return s==="start"?"🚩":s==="end"?"🏆":s==="place"?"🏫":s==="item"?"🎁":s==="move"?"⏪":s==="reset"?"🔁":s==="finish-jump"?"🏁":s==="swap"?"🔄":s==="clear"?"✨":s==="time"?"⏳":s==="limit"?"🚫":s==="pose"?"◇":s==="theme"?"🚩":s==="task"?"📸":""}function ks(s,t,i){return t===1?"起点":t===i?"终点":C((s==null?void 0:s.name)||"空")}function js(s){const t=C(s).match(/(我|渡)掷出\s*(\d+)，从\s*(\d+)\s*走到\s*(\d+)/);return t?{actor:t[1]==="渡"?"du":"xinyue",dice:Number(t[2]||1),from:Number(t[3]||0),to:Number(t[4]||0)}:null}function Me(s){return s.replace(/[。.!！?？\s]+$/g,"").trim()}function Ns(s,t,i,n){const f=[s,...t].map(g=>g.trim()).filter(Boolean).filter(g=>!/^下一次行动[:：]/.test(g)&&!/^待处理[:：]/.test(g)).join(" ");if(/双方回到起点/.test(f))return"双方回到起点";let l=f.match(/(我|你|渡|对方|双方)?\s*从\s*\d+\s*(前进|后退)\s*(\d+)\s*格(?:到|至)\s*\d+/);return l?`${l[1]||i||"玩家"}${l[2]}了 ${l[3]} 格`:(l=f.match(/(我|你|渡|对方|双方)\s*(前进|后退)\s*(\d+)\s*格/),l?`${l[1]}${l[2]}了 ${l[3]} 格`:(l=f.match(/(我|你|渡|对方)\s*从\s*\d+\s*回到起点/),l?`${l[1]}回到起点`:(l=f.match(/(我|你|渡|对方)\s*从\s*\d+\s*直达终点/),l?`${l[1]}直达终点`:Me(s)===Me(n)?"":s?`触发：${s}`:"")))}function _s(s,t){var J,Y;const i=C(s).split(`
`).map(b=>b.trim()).filter(Boolean),n=i.findIndex(b=>/^第\s*\d+\s*格：/.test(b)),c=n>=0?i[n]:"";if(!c)return null;const f=c.match(/^第\s*(\d+)\s*格：([^，。]+)/),l=(f==null?void 0:f[2])||"格子事件",g=((J=c.match(/抽到「([^」]+)」/))==null?void 0:J[1])||"",o=((Y=c.match(/获得\s*([^（，。]+)/))==null?void 0:Y[1])||"",A=!!(g||o||/抽卡|惩罚任务|选择惩罚/.test(l)),R=/奖励|Pass卡|获得/.test(c)?"reward":/选择/.test(l)?"choice":"penalty",O=Number((f==null?void 0:f[1])||0),q=t==null?void 0:t.actor,X=c.replace(/^第\s*\d+\s*格：/,"").trim(),w=q?Ye[q]:"",S=Ns(X,i.slice(n+1,n+4),w,l);return{position:O,actor:q,actorLabel:w,from:t==null?void 0:t.from,to:(t==null?void 0:t.to)??O,title:l,text:c,detail:S,kind:A?"draw":"event",cardTitle:g||o||l,cardType:R==="reward"?"奖励卡":R==="choice"?"选择惩罚":"惩罚任务",tone:R}}function yt(s){const t=T(s.cardType||"").trim(),i=T(s.cardTitle||s.title).trim(),n=T(s.title).trim();return!t||t===i||t===n?"":t}function vt(s){const t=T(s.detail||"").trim(),i=T(s.title).trim();return!t||Me(t.replace(/^触发[:：]\s*/,""))===Me(i)?"":t}function Ss(s,t,i){const n=C(s).trim();if(!n)return null;const c=Array.isArray(i)?i.map(A=>C(A).trim()).filter(Boolean):[],o=[...[...Array.from(new Set(c)).filter(A=>A!==n)].sort(()=>Math.random()-.5).slice(0,7),n];for(;o.length<8;)o.unshift(n);return{theme:n,direction:C(t||"待定"),items:o,spinKey:`${Date.now()}-${Math.random().toString(36).slice(2,8)}`}}function zs(s){const t=String(s.duration_type||"");if(t==="actions"){const i=Math.max(0,Number(s.remaining_actions||0));return s.blocks_action?`停步剩余 ${i} 次`:`剩余 ${i} 次行动`}return t==="minutes"?`${Math.max(1,Number(s.minutes||0))} 分钟`:t==="until_finish"?"到终点前有效":t==="until_clear"?"待解除":""}function Pt(s){return!!$t[String(s||"").trim()]}function Mt(s,t){const i=new Map;for(const f of s||[]){const l=String((f==null?void 0:f.slot)||"").trim();if(!Pt(l))continue;const g=C((f==null?void 0:f.value)||"").trim();g&&i.set(l,g)}const n=C((t==null?void 0:t.final_place)||"").trim(),c=C((t==null?void 0:t.final_pose)||"").trim();return n&&!i.has("place")&&i.set("place",n),c&&!i.has("pose")&&i.set("pose",c),["place","pose"].map(f=>{const l=i.get(f);return l?{label:$t[f]||"终局素材",values:[l]}:null}).filter(f=>!!f)}function Cs(s){const t=C(s.label||s.slot||"状态");return s.slot==="prop"||t==="道具"?"道具惩罚":t}function $s(s){const t=C(s.value||""),i=[],n=Math.max(1,Number(s.level||1));s.slot==="prop"&&n>1&&Tt(t)&&i.push(`${n}档`);const c=zs(s);return c&&i.push(c),t?i.length?`${t}（${i.join("，")}）`:t:i.length?i.join("，"):"状态"}function Tt(s){return bs.some(t=>s.includes(t))}function Ps(s){const t=new Map;return s.filter(i=>!Pt(i.slot)).slice(-6).forEach(i=>{const n=Cs(i),c=t.get(n)||[];c.push($s(i)),t.set(n,c)}),Array.from(t.entries()).map(([i,n])=>({label:i,values:n}))}function kt(s){return(s||[]).some(t=>t.blocks_action&&Number(t.remaining_actions||0)>0)}function Ms(s){const t=[/^(我|渡)掷出\s*\d+/,/^第\s*\d+\s*格：/,/^下一次行动：/,/行动权/,/到达终点/,/^新局已开始。?$/,/^本局已结束。?$/];return C(s).split(`
`).map(i=>i.trim()).filter(i=>i&&t.some(n=>n.test(i))).slice(0,4)}function Ts(s){return String(s).split(/\r?\n/).map(i=>i.trim()).find(Boolean)==="【掷骰】"}function jt(s,t){return s.slice(t).map(i=>{const n=i.trim(),c=n.match(/^【描述[:：](.*)】$/);return c?c[1].trim():n}).filter(Boolean).join(`
`).trim()}function As(s){const t=String(s).split(/\r?\n/),i=t.findIndex(R=>R.trim());if(i<0)return{kind:"",body:""};const n=t[i].trim(),c=jt(t,i+1),f=n.match(/^【描述[:：](.*)】$/);if(f)return{kind:"submit",body:f[1].trim()||c};const l=n.match(/^【真心话出题[:：](.*)】$/);if(l)return{kind:"submit",body:l[1].trim()||c};const g=n.match(/^【真心话回答[:：](.*)】$/);if(g)return{kind:"submit",body:g[1].trim()||c};if(n==="【掷骰】")return{kind:"roll",body:c};if(n==="【提交】")return{kind:"submit",body:c};if(n==="【通过】")return{kind:"approve",body:c};if(n==="【不通过】"||n==="【打回】"||n==="【驳回】")return{kind:"reject",body:c};if(n==="【Pass】"||n==="【PASS】"||n==="【使用Pass卡】")return{kind:"pass",body:c};const o=n.match(/^【选择[:：](.+)】$/);if(o)return{kind:"choose",choice:o[1].trim(),body:c};const A=n.match(/^【(?:剪刀石头布|石头剪刀布)[:：](.+)】$/);return A?{kind:"choose",choice:A[1].trim(),body:c}:{kind:"",body:jt(t,i)}}function Is(s,t="rock"){const i=((s==null?void 0:s.choices)||[]).find(n=>(n==null?void 0:n.id)||(n==null?void 0:n.label));return String((i==null?void 0:i.id)||(i==null?void 0:i.label)||t).trim()}const Ls=new Set(["反向诱惑","全部暴露！","羞耻台词大放送","自慰陈述"]);function Es(s,t){if(s==="final_note")return"本地预览：终局小纸条收到了。";const i=(t==null?void 0:t.pending_event)||null;if((i==null?void 0:i.type)==="duel"&&i.current_actor==="du")return"【剪刀石头布：石头】";if((i==null?void 0:i.type)==="choice"&&i.actor==="du"){const n=Is(i,"");if(n)return`【选择：${n}】`}return(i==null?void 0:i.type)==="review"&&i.reviewer==="du"&&i.phase==="questioning"?"【真心话出题：本地预览：渡想问你的真心话问题。】":(i==null?void 0:i.type)==="review"&&i.actor==="du"&&i.phase==="assigned"?i.name==="真心话点名"?"【真心话回答：本地预览：渡已经回答真心话。】":Ls.has(String(i.name||""))?"【描述：本地预览：渡已经完成任务，提交给你验收。】":`【提交】
本地预览：渡已经完成任务，提交给你验收。`:(i==null?void 0:i.type)==="review"&&i.reviewer==="du"&&i.phase==="submitted"?"【通过】":ye(t)?"【掷骰】":"本地预览：我看到了，等你继续行动。"}async function L(s){const t=await St("/miniapp-api/game-tools/private_board",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:s,save_id:"default"})});if(!(t!=null&&t.ok))throw new Error((t==null?void 0:t.error)||"走格棋命令失败");return t}async function Bs(s){var i;const t=await St("/miniapp-api/game-tools/private_board/sync-du",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({save_id:"default",mode:s.mode,message:s.message||"",roll_text:s.rollText||""})});if(!(t!=null&&t.ok))throw new Error((t==null?void 0:t.error)||((i=t==null?void 0:t.wakeup)==null?void 0:i.error)||"游戏内交流失败");return t}function ye(s){return!!(s&&s.turn_actor==="du"&&!s.game_over)}function Nt(s){const t=(s==null?void 0:s.pending_event)||null;if(!s||s.game_over||!t)return!1;if(t.type==="duel")return t.current_actor==="du";if(t.type==="choice")return t.actor==="du";if(t.type==="review"){const i=String(t.phase||"");return i==="questioning"||i==="submitted"?t.reviewer==="du":t.actor==="du"}return!1}function we(s){const t=(s==null?void 0:s.pending_event)||null;if(!t)return"现在轮到渡行动。";if(t.type==="duel")return"现在轮到渡完成剪刀石头布对抗。";if(t.type==="choice")return"渡刚触发了需要自己选择的惩罚。";if(t.type==="review"){const i=String(t.phase||"");return i==="questioning"?"现在需要渡给出真心话题目。":i==="submitted"?"现在需要渡验收小玥提交的惩罚任务。":"现在需要渡提交惩罚任务。"}return"现在轮到渡处理棋局。"}function Hs({onBack:s}){var at,nt,rt,ot,lt,ct,dt,pt,ut,xt,ft;const t=ns(),i=u.useRef(null),n=u.useRef(!1),c=u.useRef(null),f=u.useRef(null),l=u.useRef(null),g=u.useRef(null),[o,A]=u.useState(null),[R,O]=u.useState(xs),[q,X]=u.useState(1),[w,S]=u.useState(!1),[J,Y]=u.useState(!1),[b,re]=u.useState(!1),[ve,Z]=u.useState(null),[k,H]=u.useState(null),[Q,ee]=u.useState(!0),[te,oe]=u.useState(null),[K,$]=u.useState(!1),[G,le]=u.useState(0),[ke,Ge]=u.useState(""),[M,je]=u.useState(!1),[I,Ne]=u.useState(!1),[At,ce]=u.useState(!1),[Fe,It]=u.useState(""),[Lt,Ue]=u.useState(!1),[He,Et]=u.useState(1),[Te,Ke]=u.useState(""),[_e,We]=u.useState(ps),v=(o==null?void 0:o.state)||{},B=Math.max(12,Math.min(80,Number(v.board_size||36))),Ae=B<=36?6:8,Ie=v.turn_actor==="du"?"du":"xinyue",F=!!(v.game_over||o!=null&&o.game_over),de=Ie==="du"&&!F,_=v.pending_event||null,Se=u.useMemo(()=>{try{return!!new URLSearchParams(window.location.search).has("preview")}catch{return!1}},[]);u.useLayoutEffect(()=>{i.current&&(i.current.scrollTop=0)},[]),u.useEffect(()=>{n.current=K,K&&le(0)},[K]),u.useEffect(()=>{K&&window.setTimeout(()=>{var a;return(a=c.current)==null?void 0:a.scrollIntoView({block:"end"})},40)},[_e.length,K,M]),u.useEffect(()=>{us(_e)},[_e]),u.useEffect(()=>{if(!k||k.kind!=="draw"||k.tone!=="reward"){ee(!0);return}ee(!1);const a=window.setTimeout(()=>ee(!0),900);return()=>window.clearTimeout(a)},[k]);const j=u.useCallback((a,d=!1)=>{We(x=>[...x,a]),d&&!n.current&&le(x=>Math.min(9,x+1))},[]),Je=u.useMemo(()=>{const a=new Map;for(const d of v.cell_events||[]){const x=Number((d==null?void 0:d.position)||0);x>0&&a.set(x,d)}return a},[v.cell_events]),Bt=u.useMemo(()=>ws(B,Ae).map(a=>{const d=Je.get(a),x=ys(d,a,B);return{position:a,event:d,kind:x,icon:vs(x),name:ks(d,a,B)}}),[B,Ae,Je]),y=u.useCallback(a=>{var d,x,p,h;A(a),O({xinyue:Number(((x=(d=a.state)==null?void 0:d.positions)==null?void 0:x.xinyue)||0),du:Number(((h=(p=a.state)==null?void 0:p.positions)==null?void 0:h.du)||0)})},[]),Ve=u.useCallback(async()=>{S(!0);try{const a=await L("status");y(a)}catch(a){t(`加载涩涩走格棋失败：${(a==null?void 0:a.message)||a}`)}finally{S(!1)}},[y,t]);u.useEffect(()=>{Ve()},[Ve]);const Xe=u.useCallback(async a=>{Y(!0);for(let d=0;d<12;d+=1)X(Math.floor(Math.random()*6)+1),await $e(58);X(Math.max(1,Math.min(6,a||1))),Y(!1)},[]),Le=u.useCallback(async(a,d,x,p)=>{const h=Number(x||0),r=Number(p||0);if(h===r){a[d]=r,O({...a}),Z(qe(r,B)),await $e(120);return}const P=r>h?1:-1;for(let D=h+P;P>0?D<=r:D>=r;D+=P)a[d]=D,O({...a}),Z(qe(D,B)),await $e(145)},[B]),Ee=u.useCallback(async()=>{var a,d,x,p,h;if(!(w||b)){S(!0),H(null);try{const r=await L("new_game");X(1),y(r),We(ae()),le(0),oe(Ss((d=(a=r.state)==null?void 0:a.theme_profile)==null?void 0:d.theme,(p=(x=r.state)==null?void 0:x.theme_profile)==null?void 0:p.direction_label,(h=r.state)==null?void 0:h.theme_options))}catch(r){t(`开新局失败：${(r==null?void 0:r.message)||r}`)}finally{S(!1)}}},[b,y,w,t]);u.useCallback(async()=>{if(!(w||b)){S(!0);try{const a=await L("end_game");y(a)}catch(a){t(`结束本局失败：${(a==null?void 0:a.message)||a}`)}finally{S(!1)}}},[b,y,w,t]);const se=u.useCallback(async(a,d)=>{var P,D,pe,ue,xe,fe,he,ge,me;const x=a.trim()||"我看到了。",p=As(x),h=p.body.trim();h&&j({id:z("du"),speaker:"du",text:h},!0);const r=(d==null?void 0:d.pending_event)||null;try{if((r==null?void 0:r.type)==="duel"&&r.current_actor==="du"){if(p.kind!=="choose"||!p.choice.trim())return;const m=p.choice.trim(),N=gs(r,m),W=await L(`choose ${m}`);y(W);const be=ye(W.state)&&!((P=W.state)!=null&&P.pending_event);N&&(g.current=be?{state:W.state,message:"剪刀石头布对抗已结算，现在轮到渡行动。"}:null,H({position:Number(r.cell||((pe=(D=W.state)==null?void 0:D.positions)==null?void 0:pe.du)||0),kicker:"剪刀石头布对抗",title:"对抗结果",text:N,detail:N,kind:"event"})),j({id:z("system"),speaker:"system",text:N||Re(W,"渡已出拳，系统已判定对抗结果。")},!0),!N&&be&&await((ue=l.current)==null?void 0:ue.call(l,W.state,"剪刀石头布对抗已结算，现在轮到渡行动。"));return}if((r==null?void 0:r.reviewer)==="du"&&r.type==="review"&&r.phase==="questioning"){if(p.kind!=="submit")return;const m=p.body.trim();if(!m){j({id:z("system"),speaker:"system",text:"渡发了【提交】，但后面没有题目。"},!0);return}const N=await L(`submit ${m}`);y(N),j({id:z("system"),speaker:"system",text:"渡已出题，轮到你回答。"},!0);return}if((r==null?void 0:r.actor)==="du"&&r.type==="review"&&r.phase==="assigned"){if(p.kind!=="submit")return;const m=p.body.trim();if(!m){j({id:z("system"),speaker:"system",text:"渡发了【提交】，但后面没有提交内容。"},!0);return}const N=await L(`submit ${m}`);y(N),j({id:z("system"),speaker:"system",text:"渡已提交惩罚任务，等你验收。"},!0),await((xe=l.current)==null?void 0:xe.call(l,N.state,we(N.state)));return}if((r==null?void 0:r.actor)==="du"&&r.type==="choice"){if(p.kind==="pass"){const N=await L("pass");if(y(N),N.ok===!1){j({id:z("system"),speaker:"system",text:Re(N,"渡没有Pass卡，不能跳过。")},!0);return}j({id:z("system"),speaker:"system",text:"渡使用Pass卡跳过了惩罚。"},!0),await((fe=l.current)==null?void 0:fe.call(l,N.state,we(N.state)));return}if(p.kind!=="choose"||!p.choice.trim())return;const m=await L(`choose ${p.choice.trim()}`);y(m),j({id:z("system"),speaker:"system",text:"渡已选择惩罚选项。"},!0),await((he=l.current)==null?void 0:he.call(l,m.state,we(m.state)));return}if((r==null?void 0:r.reviewer)==="du"&&r.type==="review"&&r.phase==="submitted"){if(p.kind==="approve"){const m=await L("approve");y(m),j({id:z("system"),speaker:"system",text:"渡验收通过，棋局继续。"},!0),await((ge=l.current)==null?void 0:ge.call(l,m.state,we(m.state)));return}if(p.kind==="reject"){const m=await L(p.body.trim()?`reject ${p.body.trim()}`:"reject");y(m),j({id:z("system"),speaker:"system",text:"渡打回了任务，需要重新提交。"},!0);return}return}ye(d)&&Ts(x)&&(await $e(260),j({id:z("system"),speaker:"system",text:"渡发送【掷骰】，已执行他的行动。"},!0),await((me=f.current)==null?void 0:me.call(f,{notifyAfterUserRoll:!1})))}catch(m){j({id:z("system"),speaker:"system",text:`渡的指令执行失败：${String((m==null?void 0:m.message)||m)}`},!0)}},[j,y]),V=u.useCallback(async(a,d)=>{if(!Se)return Bs(a);let x=d,p="";if(a.mode==="final_note"){const r=await L("final_note_sent");x=r.state||x,p=r.player_text||r.text||""}const h=Es(a.mode,x);return{ok:!0,state:x,player_text:p,reply_text:h,reply_preview:h.slice(0,120),wakeup:{reply_text:h,reply_preview:h.slice(0,120)}}},[Se]),Qe=u.useCallback(async(a,d="现在轮到渡行动。")=>{var p,h;const x=Nt(a);if(!(!ye(a)||a!=null&&a.pending_event&&!x)){Ne(!0);try{const r=await V({mode:"state_update",message:d,rollText:""},a);r.state&&y({ok:!0,state:r.state,player_text:r.player_text||""});const P=ie(r.reply_text||((p=r.wakeup)==null?void 0:p.reply_text)||r.reply_preview||((h=r.wakeup)==null?void 0:h.reply_preview)||"").trim();await se(P,r.state||a)}catch(r){const P=String((r==null?void 0:r.message)||r||"同步失败");j({id:z("system"),speaker:"system",text:`渡行动同步失败：${P}`},!0),t(`渡行动同步失败：${P}`)}finally{Ne(!1)}}},[j,y,se,V,t]);u.useEffect(()=>{l.current=Qe},[Qe]);const Ot=u.useCallback(()=>{var d;const a=g.current;g.current=null,H(null),a&&((d=l.current)==null||d.call(l,a.state,a.message))},[]),ze=u.useCallback(async(a,d="小玥刚掷完骰子。")=>{var p,h;const x=ie(a.text||a.du_text||a.player_text||"").trim();Ne(!0);try{const r=await V({mode:"roll_result",message:d,rollText:x},a.state);r.state&&y({ok:!0,state:r.state,player_text:r.player_text||a.player_text||""});const P=ie(r.reply_text||((p=r.wakeup)==null?void 0:p.reply_text)||r.reply_preview||((h=r.wakeup)==null?void 0:h.reply_preview)||"").trim();await se(P,r.state||a.state)}catch(r){const P=String((r==null?void 0:r.message)||r||"同步失败");j({id:z("system"),speaker:"system",text:`自动同步失败：${P}`},!0),t(`自动同步给渡失败：${P}`)}finally{Ne(!1)}},[j,y,se,V,t]),Be=u.useCallback(async(a={})=>{var P,D,pe,ue,xe,fe,he,ge,me;if(w||b||F)return;let d=null,x=null;S(!0),re(!0),H(null);const p={xinyue:Number(((P=v.positions)==null?void 0:P.xinyue)||0),du:Number(((D=v.positions)==null?void 0:D.du)||0)},h=v.turn_actor==="du"?"du":"xinyue",r={...p};try{const m=await L("roll"),N=js(m.player_text||"");await Xe((N==null?void 0:N.dice)||Math.floor(Math.random()*6)+1),N&&await Le(r,N.actor,N.from,N.to);const W={xinyue:Number(((ue=(pe=m.state)==null?void 0:pe.positions)==null?void 0:ue.xinyue)||0),du:Number(((fe=(xe=m.state)==null?void 0:xe.positions)==null?void 0:fe.du)||0)};for(const De of mt){const ht=Number(r[De]||0),gt=Number(W[De]||0);ht!==gt&&await Le(r,De,ht,gt)}y(m);const be=_s(m.player_text||"",N);be&&H(be);const as=((he=m.state)==null?void 0:he.pending_event)||null;a.notifyAfterUserRoll!==!1&&h==="xinyue"&&!((ge=m.state)!=null&&ge.game_over)&&(!as||Nt(m.state))?d=m:a.notifyAfterUserRoll===!1&&h==="du"&&ye(m.state)&&(x=m)}catch(m){t(`掷骰失败：${(m==null?void 0:m.message)||m}`)}finally{S(!1),re(!1),window.setTimeout(()=>Z(null),260)}d?await ze(d):x&&await((me=l.current)==null?void 0:me.call(l,x.state,we(x.state)))},[Le,Xe,b,y,w,F,ze,v.positions,v.turn_actor,t]);u.useEffect(()=>{f.current=Be},[Be]);const U=u.useCallback(async(a,d={})=>{if(w||!(o!=null&&o.state))return;let x=null;S(!0),H(null);try{const p=await L(a);if(x=p,y(p),p.ok===!1){t(Re(p,"这次操作没有生效。"));return}Ke(""),d.success&&j({id:z("system"),speaker:"system",text:d.success},!0)}catch(p){t(`处理惩罚任务失败：${(p==null?void 0:p.message)||p}`)}finally{S(!1)}x&&d.notify&&await ze(x,d.notifyMessage||"小玥处理了涩涩走格棋的惩罚任务。")},[j,y,w,ze,o==null?void 0:o.state,t]),Dt=u.useCallback(()=>{const a=Te.trim();if(!a){t("先写提交内容。");return}U(`submit ${a}`,{success:"已提交任务，等渡验收。",notify:!0,notifyMessage:"小玥提交了惩罚任务，请你验收。"})},[U,Te,t]),Rt=u.useCallback(()=>{U("approve",{success:"你通过了任务，棋局继续。",notify:!0,notifyMessage:"小玥通过了你的惩罚任务。"})},[U]),qt=u.useCallback(()=>{U("reject",{success:"你打回了任务，等渡重新提交。",notify:!0,notifyMessage:"小玥打回了你的惩罚任务，请重新提交。"})},[U]),Yt=u.useCallback(a=>{const d=(_==null?void 0:_.type)==="duel",x=(_==null?void 0:_.current_actor)||(_==null?void 0:_.actor);if(d&&!(d&&x==="xinyue")){t("等待渡出拳。");return}U(`choose ${a}`,{success:d?"已出拳，等待渡出拳。":"已选择惩罚，棋局继续。",notify:!0,notifyMessage:d?"小玥已在剪刀石头布对抗中出拳。请第一行单独发送【剪刀石头布：石头】、【剪刀石头布：剪刀】或【剪刀石头布：布】。":"小玥处理完选择惩罚，棋局继续。"})},[U,_==null?void 0:_.actor,_==null?void 0:_.current_actor,_==null?void 0:_.type,t]),Gt=u.useCallback(()=>{U("pass",{success:"已使用Pass卡跳过惩罚。",notify:!0,notifyMessage:"小玥使用Pass卡跳过了惩罚任务。"})},[U]),Ft=u.useCallback(async()=>{var d,x,p;const a=((d=o==null?void 0:o.state)==null?void 0:d.final_note)||null;if(!(M||I||w||b||!(o!=null&&o.state)||!a||a.sent)){je(!0);try{const h=await V({mode:"final_note",message:a.text||""},o.state);h.state&&y({ok:!0,state:h.state,player_text:h.player_text||o.player_text||""}),j({id:z("system"),speaker:"system",text:Se?"预览模式：终局小纸条已同步。":"终局小纸条已发送给渡。"},!0);const r=ie(h.reply_text||((x=h.wakeup)==null?void 0:x.reply_text)||h.reply_preview||((p=h.wakeup)==null?void 0:p.reply_preview)||"").trim();r&&j({id:z("du"),speaker:"du",text:r},!0),ce(!1)}catch(h){const r=String((h==null?void 0:h.message)||h||"同步失败");j({id:z("system"),speaker:"system",text:`小纸条发送失败：${r}`},!0),t(`发送终局小纸条失败：${r}`)}finally{je(!1)}}},[b,j,y,w,M,I,Se,o,V,t]),Ut=u.useCallback(async(a,d,x=1)=>{if(M||I||w||b||!(o!=null&&o.state))return;const p=d.replace(/\s+/g," ").trim();if(!p){t("先选要追加的内容。");return}const h=a==="prop"&&Tt(p)?` level=${Math.max(1,Math.min(5,Math.round(Number(x)||1)))}`:"";S(!0);try{const r=await L(`append_final_status ${a} ${p}${h}`);y(r),ce(!0),t(`已启用：${p}`)}catch(r){t(`追加失败：${(r==null?void 0:r.message)||r}`)}finally{S(!1)}},[b,y,w,M,I,o==null?void 0:o.state,t]),Ht=u.useCallback(async(a,d)=>{if(M||I||w||b||!(o!=null&&o.state))return;const x=d.replace(/\s+/g," ").trim();if(x){S(!0);try{const p=await L(`remove_final_status ${a} ${x}`);y(p),ce(!0),t(`已取消：${x}`)}catch(p){t(`取消失败：${(p==null?void 0:p.message)||p}`)}finally{S(!1)}}},[b,y,w,M,I,o==null?void 0:o.state,t]),Kt=u.useCallback(async()=>{var x,p;if(M||I||w||b||!(o!=null&&o.state))return;const a=ke.trim();if(!a)return;const d={id:z("me"),speaker:"xinyue",text:a};Ge(""),j(d),je(!0);try{const h=await V({mode:"chat",message:a},o.state);h.state&&y({ok:!0,state:h.state,player_text:h.player_text||o.player_text||""});const r=ie(h.reply_text||((x=h.wakeup)==null?void 0:x.reply_text)||h.reply_preview||((p=h.wakeup)==null?void 0:p.reply_preview)||"").trim();await se(r,h.state||o.state)}catch(h){const r=String((h==null?void 0:h.message)||h||"同步失败");j({id:z("system"),speaker:"system",text:`交流失败：${r}`}),t(`游戏内交流失败：${r}`)}finally{je(!1)}},[b,j,y,w,ke,M,I,o,se,V,t]),Wt=C(((at=v.theme_profile)==null?void 0:at.theme)||"未触发"),Jt=C(((nt=v.theme_profile)==null?void 0:nt.direction_label)||"待定"),Vt=wt((rt=v.positions)==null?void 0:rt.xinyue,B),Xt=wt((ot=v.positions)==null?void 0:ot.du,B),Oe=v.winner?Ye[v.winner]:"",Ze=Ms((o==null?void 0:o.player_text)||""),E=v.final_note||null,et=Mt(v.final_note_items||[],E),Ce=String((E==null?void 0:E.id)||`${v.winner||""}-${v.updated_at||""}`),tt=!!(F&&v.winner==="xinyue"&&(!E||E.target==="du")&&!(E!=null&&E.sent)),Qt=(((lt=v.statuses)==null?void 0:lt.du)||[]).filter(a=>a.slot==="prop").map(a=>C(a.value||""));u.useEffect(()=>{!F||!E||!Ce||Fe!==Ce&&(It(Ce),ce(!0))},[E,Ce,Fe,F]);const Zt=Math.max(0,Number(((dt=(ct=v.hands)==null?void 0:ct.xinyue)==null?void 0:dt.pass)||0)),es=Math.max(0,Number(v.pass_skips_used||0)),st={xinyue:kt((pt=v.statuses)==null?void 0:pt.xinyue),du:kt((ut=v.statuses)==null?void 0:ut.du)},it=de&&st.du&&!_,ts=w||b||M||I||!(o!=null&&o.state)||!!_||de&&!it,ss=!(o!=null&&o.state),is=M||I||w||b||!(o!=null&&o.state);return e.jsxs("div",{className:"sese-game",ref:i,children:[e.jsxs("div",{className:"sese-header",children:[e.jsx("button",{className:"sese-back",type:"button",onClick:s,"aria-label":"返回游戏",children:e.jsx(rs,{})}),e.jsxs("button",{className:"sese-chat-entry",type:"button",onClick:()=>$(!0),"aria-label":"游戏内交流",children:[e.jsx(os,{}),G?e.jsx("span",{children:G}):null]}),e.jsx("div",{className:"sese-header-title",children:"涩涩走格棋"}),e.jsxs("div",{className:"sese-game-status-bar",children:[e.jsx(Pe,{label:"主题",value:Wt}),e.jsx(Pe,{label:"主导方",value:Jt}),e.jsx(Pe,{label:"我 进度",value:`${String(Vt).padStart(2,"0")} / ${B}`}),e.jsx(Pe,{label:"渡 进度",value:`${String(Xt).padStart(2,"0")} / ${B}`}),e.jsx("div",{className:"sese-turn-indicator",children:F&&Oe?`${Oe} 到达终点`:de?"等待 渡 行动...":"轮到 我 行动"})]})]}),e.jsx("section",{className:"sese-board-container","aria-label":"走格棋盘",children:e.jsx("div",{className:"sese-board",style:{gridTemplateColumns:`repeat(${Ae}, minmax(0, 1fr))`},children:Bt.map(a=>{const d=mt.filter(x=>qe(R[x],B)===a.position);return e.jsxs("div",{className:`sese-tile sese-tile-${a.kind} ${ve===a.position?"is-active":""}`,children:[e.jsx("div",{className:"sese-tile-number",children:a.position}),e.jsx("div",{className:"sese-tile-icon",children:a.icon}),e.jsx("div",{className:"sese-tile-name",children:a.name}),e.jsx("div",{className:"sese-piece-stack",children:d.map(x=>e.jsx("span",{className:`sese-piece ${x==="xinyue"?"sese-piece-me":"sese-piece-du"} ${st[x]?"paused":""}`,children:Ye[x]},x))})]},a.position)})})}),e.jsxs("section",{className:"sese-controls",children:[e.jsxs("div",{className:"sese-player-states",children:[e.jsx(_t,{actor:"xinyue",statuses:((xt=v.statuses)==null?void 0:xt.xinyue)||[],active:Ie==="xinyue"}),e.jsx(_t,{actor:"du",statuses:((ft=v.statuses)==null?void 0:ft.du)||[],active:Ie==="du"})]}),et.length?e.jsx("div",{className:"sese-final-pose-panel",children:et.map(a=>e.jsxs("div",{className:"sese-final-material-row",children:[e.jsx("span",{children:a.label}),e.jsx("strong",{children:a.values.join("、")})]},a.label))}):null,e.jsxs("div",{className:"sese-action-area",children:[e.jsx("div",{className:`sese-dice ${J?"rolling":""}`,"aria-label":`骰子 ${q}`,children:q}),e.jsx("button",{className:"sese-roll-button",type:"button",disabled:ts,onClick:F?Ee:()=>void Be({notifyAfterUserRoll:!0}),children:F?"开新局":_?"先处理任务":it?"处理停步":de?"等渡掷骰":w||b?"移动中":M||I?"等渡回应":"掷骰子"}),e.jsx("button",{className:"sese-restart-button",type:"button",disabled:w||b||M||I,onClick:Ee,children:"重开"})]}),e.jsx("div",{className:"sese-history",children:Ze.length?`最近：${Ze[0]}`:"最近：等待第一次掷骰"})]}),K?e.jsx("div",{className:"sese-chat-mask",role:"dialog","aria-modal":"true","aria-label":"游戏内交流",onClick:()=>$(!1),children:e.jsxs("div",{className:"sese-chat-panel",onClick:a=>a.stopPropagation(),children:[e.jsxs("div",{className:"sese-chat-head",children:[e.jsxs("div",{children:[e.jsx("strong",{children:"游戏内交流"}),e.jsx("span",{children:de?"等待渡发送【掷骰】":"当前轮到你行动"})]}),e.jsx("button",{type:"button",onClick:()=>$(!1),"aria-label":"关闭交流",children:"×"})]}),e.jsxs("div",{className:"sese-chat-list",children:[_e.map(a=>e.jsxs("div",{className:`sese-chat-message ${a.speaker}`,children:[e.jsx("span",{children:a.speaker==="xinyue"?"我":a.speaker==="du"?"渡":"系统"}),e.jsx("p",{children:ie(a.text)})]},a.id)),M?e.jsxs("div",{className:"sese-chat-message du pending",children:[e.jsx("span",{children:"渡"}),e.jsx("p",{children:"正在回复..."})]}):null,e.jsx("div",{ref:c})]}),e.jsxs("form",{className:"sese-chat-form",onSubmit:a=>{a.preventDefault(),Kt()},children:[e.jsx("input",{value:ke,disabled:ss,placeholder:"和渡说一句游戏内的话",onChange:a=>Ge(a.target.value)}),e.jsx("button",{type:"submit",disabled:is||!ke.trim(),"aria-label":M?"发送中":"发送",children:e.jsx(ls,{})})]})]})}):null,te?e.jsx("div",{className:"sese-theme-mask",role:"dialog","aria-modal":"true","aria-label":"开局主题抽取",children:e.jsxs("div",{className:"sese-theme-modal",children:[e.jsxs("div",{className:"sese-slot-lights","aria-hidden":"true",children:[e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{})]}),e.jsxs("div",{className:"sese-slot-marquee",children:[e.jsx("span",{children:"THEME"}),e.jsx("strong",{children:"JACKPOT"})]}),e.jsxs("div",{className:"sese-slot-face",children:[e.jsx("div",{className:"sese-theme-window",children:e.jsx("div",{className:"sese-theme-strip",children:te.items.map((a,d)=>e.jsx("div",{className:"sese-theme-item",children:C(a)},`${a}-${d}`))},te.spinKey)}),e.jsxs("p",{className:"sese-slot-plaque",children:["主导方：",te.direction]}),e.jsxs("div",{className:"sese-theme-actions",children:[e.jsx("button",{className:"secondary",type:"button",disabled:w,onClick:Ee,children:w?"重抽中":"重抽主题"}),e.jsx("button",{type:"button",onClick:()=>oe(null),children:"开始本局"})]}),e.jsx("div",{className:"sese-slot-tray","aria-hidden":"true"})]})]})}):null,_&&!k?e.jsx("div",{className:"sese-pending-mask",role:"dialog","aria-modal":"true","aria-label":"待处理惩罚",children:e.jsx("div",{className:"sese-pending-modal",children:e.jsx(Gs,{pending:_,passCount:Zt,passSkipsUsed:es,submission:Te,disabled:w||I,onSubmissionChange:Ke,onSubmit:Dt,onApprove:Rt,onReject:qt,onChoose:Yt,onPass:Gt})})}):null,F&&E&&At?e.jsx("div",{className:"sese-final-note-mask",role:"dialog","aria-modal":"true","aria-label":"终局小纸条",children:e.jsxs("div",{className:"sese-final-note-modal",children:[e.jsxs("div",{className:"sese-final-note-head",children:[e.jsx("span",{children:"终局小纸条"}),e.jsx("button",{type:"button",onClick:()=>ce(!1),"aria-label":"关闭终局小纸条",children:"关闭"})]}),e.jsxs("h2",{children:[Oe||"玩家"," 到达终点"]}),e.jsx(Ds,{note:E,canAddStatus:tt,onAddStatus:()=>Ue(!0)}),E.sent?e.jsx("em",{children:"已发送给渡"}):e.jsx("button",{className:"sese-final-note-send",type:"button",disabled:M||I||w||b,onClick:()=>void Ft(),children:M?"发送中":"发送给渡"})]})}):null,tt&&Lt?e.jsx(Os,{level:He,activeProps:Qt,disabled:M||I||w||b,onClose:()=>Ue(!1),onLevelChange:Et,onToggleProp:(a,d)=>{d?Ht("prop",a):Ut("prop",a,He)}}):null,k?e.jsx("div",{className:"sese-popup-mask",role:"dialog","aria-modal":"true",children:e.jsxs("div",{className:`sese-popup ${k.kind==="draw"?`sese-popup-draw tone-${k.tone||"penalty"}`:""}`,children:[e.jsx("div",{className:"sese-popup-kicker",children:T(k.kicker||(k.actorLabel?`${k.actorLabel}走到第 ${k.position} 格`:`第 ${k.position} 格`))}),k.kind==="draw"?e.jsx("div",{className:`sese-draw-card ${k.tone==="reward"&&!Q?"is-covered":"is-revealed"}`,children:k.tone==="reward"&&!Q?e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"sese-card-pile","aria-hidden":"true",children:[e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("b",{})]}),e.jsx("span",{children:"奖励抽卡"}),e.jsx("em",{children:"抽卡中"})]}):e.jsxs(e.Fragment,{children:[yt(k)?e.jsx("span",{children:yt(k)}):null,e.jsx("strong",{children:T(k.cardTitle||k.title)})]})}):null,k.kind==="draw"?null:e.jsx("h2",{children:T(k.title)}),k.tone==="reward"&&!Q?e.jsx("p",{children:"正在洗牌..."}):vt(k)?e.jsx("p",{children:vt(k)}):null,k.tone==="reward"&&!Q?null:e.jsx("button",{type:"button",onClick:Ot,children:"确 认"})]})}):null,e.jsx("style",{children:`
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
        `})]})}function Pe({label:s,value:t}){return e.jsxs("div",{className:"sese-pill",children:[e.jsx("span",{children:s}),e.jsx("strong",{children:t})]})}function _t({actor:s,statuses:t,active:i}){const n=Ps(t);return e.jsxs("div",{className:`sese-player-card sese-player-card-${s} ${i?"active":""}`,children:[e.jsx("div",{className:"sese-player-card-head",children:e.jsx("h2",{children:s==="xinyue"?"我的状态":"渡的状态"})}),e.jsx("div",{className:"sese-status-list",children:n.length?n.map(c=>e.jsxs("div",{className:"sese-status-group",children:[e.jsx("span",{className:"sese-status-group-label",children:c.label}),e.jsx("div",{className:"sese-status-chip-row",children:c.values.map(f=>e.jsx("span",{className:"sese-status-chip",children:f},`${c.label}-${f}`))})]},c.label)):e.jsx("div",{className:"sese-status-empty",children:"无状态"})})]})}function Os({level:s,activeProps:t,disabled:i,onClose:n,onLevelChange:c,onToggleProp:f}){const l=new Set(t);return e.jsx("div",{className:"sese-toy-console-mask",role:"dialog","aria-modal":"true","aria-label":"玩具控制台",onClick:n,children:e.jsxs("div",{className:"sese-toy-console-sheet",onClick:g=>g.stopPropagation(),children:[e.jsxs("div",{className:"sese-toy-console-head",children:[e.jsxs("div",{children:[e.jsx("span",{children:"玩具控制台"}),e.jsx("strong",{children:"控制渡当前状态"})]}),e.jsx("button",{type:"button",onClick:n,"aria-label":"关闭玩具控制台",children:"关闭"})]}),e.jsxs("div",{className:"sese-toy-console-section",children:[e.jsx("label",{children:"道具档位"}),e.jsx("div",{className:"sese-toy-level-row",children:[1,2,3,4,5].map(g=>e.jsx("button",{type:"button",disabled:i,className:g===s?"selected":"",onClick:()=>c(g),children:g},g))})]}),e.jsxs("div",{className:"sese-toy-console-section",children:[e.jsx("label",{children:"启用道具"}),e.jsx("div",{className:"sese-toy-chip-grid",children:ms.map(g=>(()=>{const o=l.has(g);return e.jsx("button",{type:"button",disabled:i,className:o?"selected":"","aria-pressed":o,"aria-label":o?`取消启用${g}`:`启用${g}`,onClick:()=>f(g,o),children:g},g)})())})]})]})})}function Ds({note:s,canAddStatus:t=!1,onAddStatus:i}){const n=qs(s),c=C(s.theme||"本局主题"),f=s.target==="du"?"渡当前状态":"你的当前状态",l=Ys(s.target_status||""),g=Mt([],s);return e.jsxs("div",{className:"sese-final-note-body",children:[e.jsx("div",{className:"sese-final-note-intro",children:n}),e.jsxs("div",{className:"sese-final-note-section",children:[e.jsx("span",{children:"本局主题"}),e.jsx("strong",{children:c})]}),e.jsxs("div",{className:"sese-final-note-section",children:[e.jsxs("div",{className:"sese-final-note-section-title",children:[e.jsx("span",{children:f}),t?e.jsx("button",{type:"button",onClick:i,"aria-label":"打开玩具控制台",children:e.jsx(Rs,{})}):null]}),l.length?l.map(o=>e.jsxs("div",{className:"sese-final-note-status-group",children:[e.jsx("b",{children:o.label}),e.jsx("div",{className:"sese-final-note-status-values",children:o.values.map(A=>e.jsx("span",{children:A},A))})]},o.label)):e.jsx("div",{className:"sese-final-note-empty",children:"没有遗留状态，可以自由决定最后玩法。"})]}),g.map(o=>e.jsxs("div",{className:"sese-final-note-section",children:[e.jsx("span",{children:o.label}),e.jsx("strong",{children:o.values.join("、")})]},o.label)),e.jsx("div",{className:"sese-final-note-closing",children:"请尽情享受你们的ooxx吧！"})]})}function Rs(){return e.jsx("svg",{viewBox:"0 0 24 24","aria-hidden":"true",children:e.jsx("path",{d:"M12 5v14M5 12h14"})})}function qs(s){return T(s.text||"").split(`
`).map(n=>n.trim()).filter(Boolean).find(n=>!n.startsWith("【")&&!n.startsWith("请根据")&&!n.startsWith("本局主题")&&!n.startsWith("请尽情"))||"终点已到达，赢家状态已清空。"}function Ys(s){const t=T(s).trim();return!t||t==="无"?[]:t.split("；").map(i=>i.trim()).filter(Boolean).map(i=>{const n=i.indexOf("：");if(n<0)return{label:"状态",values:[i]};const c=i.slice(0,n).trim()||"状态",f=i.slice(n+1).split("、").map(l=>l.trim()).filter(Boolean);return{label:c,values:f.length?f:["无"]}})}function Gs({pending:s,passCount:t,passSkipsUsed:i,submission:n,disabled:c,onSubmissionChange:f,onSubmit:l,onApprove:g,onReject:o,onChoose:A,onPass:R}){var oe,K;const O=T(s.name||"惩罚任务"),q=s.actor||"xinyue",X=s.reviewer||(q==="xinyue"?"du":"xinyue"),w=s.current_actor||q,S=q==="xinyue",J=w==="xinyue",Y=X==="xinyue",b=!!C(s.question_text||"").trim(),re=S&&s.pass_allowed!==!1&&t>0&&i<1&&!["submitted","questioning"].includes(String(s.phase||"")),ve=T(s.submission||"").trim(),Z=/^你的回答[。.]?$/.test(ve)?"":ve,[k,H]=u.useState("");u.useEffect(()=>{H("")},[s.id,s.current_actor,s.phase]);const Q=ne(k||((oe=s.picks)==null?void 0:oe.xinyue)),ee=!!ne((K=s.picks)==null?void 0:K.xinyue);if(s.type==="choice")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:S?"你的选择惩罚":"等待渡选择"}),e.jsx("strong",{children:O})]}),e.jsx("p",{children:T(s.prompt||"选择一项惩罚。")}),S?e.jsx("div",{className:"sese-choice-list",children:(s.choices||[]).map($=>{const G=String($.id||$.label||"");return e.jsx("button",{type:"button",disabled:c||!G,onClick:()=>A(G),children:T($.label||G)},G)})}):e.jsx("div",{className:"sese-pending-wait",children:"等待渡选择惩罚。"}),re?e.jsx("button",{className:"sese-pass-button",type:"button",disabled:c,onClick:R,children:"使用Pass卡跳过"}):null]});if(s.type==="duel")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:J?"轮到你出拳":"等待渡出拳"}),e.jsx("strong",{children:O||"剪刀石头布对抗"})]}),e.jsx("p",{children:"同格触发对抗。双方各出石头、剪刀或布，系统判定胜负；赢的前进 3 格，输的后退 3 格。"}),e.jsx("div",{className:"sese-choice-list sese-rps-list",children:Ct.map($=>e.jsx("button",{className:`sese-rps-button ${Q===$.id?"is-selected":""}`,type:"button",title:$.label,"aria-label":$.label,"aria-pressed":Q===$.id,disabled:c||!J||ee,onClick:()=>{H(ne($.id)),A($.id)},children:$.icon},$.id))}),J?null:e.jsx("div",{className:"sese-pending-wait",children:ee?"你的出拳已记录，等待渡出拳。":"等待渡出拳。"})]});if(s.phase==="submitted")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:Y?"需要你验收":"等待渡验收"}),e.jsx("strong",{children:O})]}),e.jsx("p",{className:"sese-submission-text",children:C(s.submission_text||"")}),Y?e.jsxs("div",{className:"sese-review-actions",children:[e.jsx("button",{type:"button",disabled:c,onClick:g,children:"通过"}),e.jsx("button",{type:"button",disabled:c,onClick:o,children:"打回"})]}):e.jsx("div",{className:"sese-pending-wait",children:"等待渡验收你的提交。"})]});if(s.phase==="questioning"){const $=T(s.question_prompt||"请问对方一个你很想知道答案却一直没有问的问题。"),G=T(s.waiting_task||"对方正在出题中。");return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:Y?"你来出题":"等待渡出题"}),e.jsx("strong",{children:O})]}),Y?e.jsxs(e.Fragment,{children:[e.jsx("p",{children:$}),e.jsx("textarea",{value:n,placeholder:"写下你的问题",onChange:le=>f(le.target.value)}),e.jsx("div",{className:"sese-review-actions",children:e.jsx("button",{type:"button",disabled:c||!n.trim(),onClick:l,children:"提交题目"})})]}):e.jsx("div",{className:"sese-pending-wait",children:G==="对方正在出题中。"?"等待渡给出真心话题目。":G})]})}const te=b?"等待渡回答这个问题。":"等待渡完成并提交任务。";return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:S?"你的惩罚任务":"等待渡提交"}),e.jsx("strong",{children:O})]}),b?e.jsxs("p",{className:"sese-submission-text",children:["题目：",C(s.question_text)]}):null,S?e.jsxs(e.Fragment,{children:[b?null:e.jsx("p",{children:T(s.task||"")}),!b&&Z?e.jsxs("div",{className:"sese-pending-tip",children:["提交要求：",Z]}):null,e.jsx("textarea",{value:n,placeholder:b?"在这里写回答":"在这里写提交内容",onChange:$=>f($.target.value)}),e.jsxs("div",{className:"sese-review-actions",children:[e.jsx("button",{type:"button",disabled:c||!n.trim(),onClick:l,children:b?"提交回答":"提交验收"}),re?e.jsx("button",{type:"button",disabled:c,onClick:R,children:"使用Pass卡"}):null]})]}):e.jsx("div",{className:"sese-pending-wait",children:e.jsx("span",{children:te})})]})}export{Hs as SeseBoardGameTab};
