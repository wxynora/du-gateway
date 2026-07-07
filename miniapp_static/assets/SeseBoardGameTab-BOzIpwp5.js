import{u as cs,r as u,j as e,C as ds,M as ps,S as xs,b as Mt}from"./index-Bv_CfRKJ.js";const Tt="du-gateway:sese-board-game:chat:v1",us=new Set(["xinyue","du","system"]),fs=[{id:"system-ready",speaker:"system",text:"游戏内交流在这里。渡明确发送【掷骰】时，棋盘才会执行他的行动。"}];function fe(){return fs.map(s=>({...s}))}function hs(){if(typeof window>"u")return fe();try{const s=window.localStorage.getItem(Tt);if(!s)return fe();const t=JSON.parse(s);if(!Array.isArray(t))return fe();const i=t.flatMap((r,l)=>{if(!r||typeof r!="object")return[];const d=r,o=typeof d.speaker=="string"?d.speaker:"",g=typeof d.text=="string"?d.text.trim():"";return!us.has(o)||!g?[]:[{id:(typeof d.id=="string"?d.id.trim():"")||`stored-${l}`,speaker:o,text:g}]});return i.length?i:fe()}catch{return fe()}}function gs(s){if(!(typeof window>"u"))try{window.localStorage.setItem(Tt,JSON.stringify(s))}catch{}}const kt=["xinyue","du"],He={xinyue:"我",du:"渡"},ms={xinyue:0,du:0},At=[{id:"scissors",label:"剪刀",icon:"✌️"},{id:"rock",label:"石头",icon:"👊"},{id:"paper",label:"布",icon:"✋"}],bs={rock:"scissors",scissors:"paper",paper:"rock"},ws={scissors:"scissors",剪刀:"scissors","✌️":"scissors","✌":"scissors",rock:"rock",stone:"rock",石头:"rock",拳头:"rock","👊":"rock",paper:"paper",布:"paper",包袱:"paper","✋":"paper"};function ge(s){const t=String(s||"").trim();return t?ws[t]||t:""}function jt(s){var i;const t=ge(s);return((i=At.find(r=>r.id===t))==null?void 0:i.label)||String(s||"").trim()||"未出拳"}function ys(s,t){var g;const i=ge((g=s==null?void 0:s.picks)==null?void 0:g.xinyue),r=ge(t);if(!i||!r)return"";const l=jt(i),d=jt(r);if(i===r)return`你出了${l}，渡出了${d}。平局，重新出拳。`;const o=bs[i]===r?"你赢":"渡赢";return`你出了${l}，渡出了${d}。${o}。`}const Rt={place:"最终地点",pose:"最终姿势"},vs=["跳蛋","震动乳夹","震动环","乳夹","锁精环","飞机杯","软绳","手腕绑带","眼罩","口球","春药"],ks=["跳蛋","震动","按摩棒","飞机杯","吸乳器","吸吮器"];function _e(s){return new Promise(t=>window.setTimeout(t,s))}function C(s){return String(s||"").replace(/小玥/g,"我")}function R(s){return String(s||"").replace(/小玥/g,"你").replace(/(^|[^自])我/g,"$1你")}function xe(s){return String(s||"")}function Fe(s,t){return C(s.player_text||s.text||s.error||"").split(/\r?\n/).map(l=>l.trim()).find(l=>l&&!l.startsWith("【")&&!/^(进度|主题|轮到|手牌|我的状态|渡的状态|最终地点|最终姿势|待处理|可用命令)/.test(l))||t}function T(s){return`${s}-${Date.now()}-${Math.random().toString(36).slice(2,8)}`}function Ge(s,t){const i=Math.floor(Number(s||0));return Math.max(1,Math.min(t,i||1))}function Nt(s,t){const i=Math.floor(Number(s||0));return Math.max(0,Math.min(t,i||0))}function js(s,t){const i=[];for(let r=1;r<=s;r+=t){const l=Array.from({length:Math.min(t,s-r+1)},(d,o)=>r+o);i.length%2===1&&l.reverse(),i.push(l)}return i.reverse().flat()}function Ns(s,t,i){if(t===1)return"start";if(t===i)return"end";if(!s)return"empty";const r=`${s.kind||""} ${s.slot||""}`.toLowerCase();return/empty/.test(r)?"empty":/finish_self|finish-jump/.test(r)?"finish-jump":/reset/.test(r)?"reset":/swap/.test(r)?"swap":/move|back|forward/.test(r)?"move":/lock|pause|item/.test(r)?"item":/clear/.test(r)?"clear":/extend|time/.test(r)?"time":/limit/.test(r)?"limit":/place/.test(r)?"place":/pose/.test(r)?"pose":/theme/.test(r)?"theme":"task"}function _s(s){return s==="start"?"🚩":s==="end"?"🏆":s==="place"?"🏫":s==="item"?"🎁":s==="move"?"⏪":s==="reset"?"🔁":s==="finish-jump"?"🏁":s==="swap"?"🔄":s==="clear"?"✨":s==="time"?"⏳":s==="limit"?"🚫":s==="pose"?"◇":s==="theme"?"🚩":s==="task"?"📸":""}function Ss(s,t,i){return t===1?"起点":t===i?"终点":C((s==null?void 0:s.name)||"空")}function zs(s){const t=C(s).match(/(我|渡)掷出\s*(\d+)，从\s*(\d+)\s*走到\s*(\d+)/);return t?{actor:t[1]==="渡"?"du":"xinyue",dice:Number(t[2]||1),from:Number(t[3]||0),to:Number(t[4]||0)}:null}function Re(s){return s.replace(/[。.!！?？\s]+$/g,"").trim()}function Cs(s,t,i,r){const d=[s,...t].map(g=>g.trim()).filter(Boolean).filter(g=>!/^下一次行动[:：]/.test(g)&&!/^待处理[:：]/.test(g)).join(" ");if(/双方回到起点/.test(d))return"双方回到起点";let o=d.match(/(我|你|渡|对方|双方)?\s*从\s*\d+\s*(前进|后退)\s*(\d+)\s*格(?:到|至)\s*\d+/);return o?`${o[1]||i||"玩家"}${o[2]}了 ${o[3]} 格`:(o=d.match(/(我|你|渡|对方|双方)\s*(前进|后退)\s*(\d+)\s*格/),o?`${o[1]}${o[2]}了 ${o[3]} 格`:(o=d.match(/(我|你|渡|对方)\s*从\s*\d+\s*回到起点/),o?`${o[1]}回到起点`:(o=d.match(/(我|你|渡|对方)\s*从\s*\d+\s*直达终点/),o?`${o[1]}直达终点`:Re(s)===Re(r)?"":s?`触发：${s}`:"")))}function $s(s,t){var S,ee;const i=C(s).split(`
`).map(G=>G.trim()).filter(Boolean),r=i.findIndex(G=>/^第\s*\d+\s*格：/.test(G)),l=r>=0?i[r]:"";if(!l)return null;const d=l.match(/^第\s*(\d+)\s*格：([^，。]+)/),o=(d==null?void 0:d[2])||"格子事件",g=((S=l.match(/抽到「([^」]+)」/))==null?void 0:S[1])||"",m=((ee=l.match(/获得\s*([^（，。]+)/))==null?void 0:ee[1])||"",x=!!(g||m||/抽卡|惩罚任务|选择惩罚/.test(o)),F=/奖励|Pass卡|获得/.test(l)?"reward":/选择/.test(o)?"choice":"penalty",K=Number((d==null?void 0:d[1])||0),L=t==null?void 0:t.actor,Q=l.replace(/^第\s*\d+\s*格：/,"").trim(),Z=L?He[L]:"",w=Cs(Q,i.slice(r+1,r+4),Z,o);return{position:K,actor:L,actorLabel:Z,from:t==null?void 0:t.from,to:(t==null?void 0:t.to)??K,title:o,text:l,detail:w,kind:x?"draw":"event",cardTitle:g||m||o,cardType:F==="reward"?"奖励卡":F==="choice"?"选择惩罚":"惩罚任务",tone:F}}function _t(s){const t=R(s.cardType||"").trim(),i=R(s.cardTitle||s.title).trim(),r=R(s.title).trim();return!t||t===i||t===r?"":t}function St(s){const t=R(s.detail||"").trim(),i=R(s.title).trim();return!t||Re(t.replace(/^触发[:：]\s*/,""))===Re(i)?"":t}function Ps(s,t,i){const r=C(s).trim();if(!r)return null;const l=Array.isArray(i)?i.map(x=>C(x).trim()).filter(Boolean):[],m=[...[...Array.from(new Set(l)).filter(x=>x!==r)].sort(()=>Math.random()-.5).slice(0,7),r];for(;m.length<8;)m.unshift(r);return{theme:r,direction:C(t||"待定"),items:m,spinKey:`${Date.now()}-${Math.random().toString(36).slice(2,8)}`}}function Ms(s){const t=String(s.duration_type||"");if(t==="actions"){const i=Math.max(0,Number(s.remaining_actions||0));return s.blocks_action?`停步剩余 ${i} 次`:`剩余 ${i} 次行动`}return t==="minutes"?`${Math.max(1,Number(s.minutes||0))} 分钟`:t==="until_finish"?"到终点前有效":t==="until_clear"?"待解除":""}function It(s){return!!Rt[String(s||"").trim()]}function Lt(s,t){const i=new Map;for(const d of s||[]){const o=String((d==null?void 0:d.slot)||"").trim();if(!It(o))continue;const g=C((d==null?void 0:d.value)||"").trim();g&&i.set(o,g)}const r=C((t==null?void 0:t.final_place)||"").trim(),l=C((t==null?void 0:t.final_pose)||"").trim();return r&&!i.has("place")&&i.set("place",r),l&&!i.has("pose")&&i.set("pose",l),["place","pose"].map(d=>{const o=i.get(d);return o?{label:Rt[d]||"终局素材",values:[o]}:null}).filter(d=>!!d)}function Ts(s){const t=C(s.label||s.slot||"状态");return s.slot==="prop"||t==="道具"?"道具惩罚":t}function As(s){const t=C(s.value||""),i=[],r=Math.max(1,Number(s.level||1));s.slot==="prop"&&r>1&&Bt(t)&&i.push(`${r}档`);const l=Ms(s);return l&&i.push(l),t?i.length?`${t}（${i.join("，")}）`:t:i.length?i.join("，"):"状态"}function Bt(s){return ks.some(t=>s.includes(t))}function Rs(s){const t=new Map;return s.filter(i=>!It(i.slot)).slice(-6).forEach(i=>{const r=Ts(i),l=t.get(r)||[];l.push(As(i)),t.set(r,l)}),Array.from(t.entries()).map(([i,r])=>({label:i,values:r}))}function zt(s){return(s||[]).some(t=>t.blocks_action&&Number(t.remaining_actions||0)>0)}function Is(s){const t=[/^(我|渡)掷出\s*\d+/,/^第\s*\d+\s*格：/,/^下一次行动：/,/行动权/,/到达终点/,/^新局已开始。?$/,/^本局已结束。?$/];return C(s).split(`
`).map(i=>i.trim()).filter(i=>i&&t.some(r=>r.test(i))).slice(0,4)}function Ls(s){return String(s).split(/\r?\n/).map(i=>i.trim()).find(Boolean)==="【掷骰】"}function Bs(s){return String(s).split(/\r?\n/).some(t=>t.trim()==="【掷骰】")}function Ct(s,t){return s.slice(t).map(i=>{const r=i.trim();if(r==="【掷骰】")return"";const l=r.match(/^【描述[:：](.*)】$/);return l?l[1].trim():r}).filter(Boolean).join(`
`).trim()}function Ue(s,t,i){var o;const l=(((o=s[t])==null?void 0:o.trim())||"").match(i);if(!l)return null;const d=[l[1]||"",...s.slice(t+1)].join(`
`).trim();return d.endsWith("】")?d.slice(0,-1).trim():d}function Es(s){const t=String(s).split(/\r?\n/),i=t.findIndex(L=>L.trim());if(i<0)return{kind:"",body:""};const r=t[i].trim(),l=Ct(t,i+1),d=Ue(t,i,/^【描述[:：](.*)$/);if(d!==null)return{kind:"submit",body:d||l};const o=Ue(t,i,/^【真心话出题[:：](.*)$/);if(o!==null)return{kind:"submit",body:o||l};const g=Ue(t,i,/^【真心话回答[:：](.*)$/);if(g!==null)return{kind:"submit",body:g||l};if(r==="【掷骰】")return{kind:"roll",body:l};if(r==="【提交】")return{kind:"submit",body:l};const m=r.match(/^【通过[:：](.*?)(?:】)?$/);if(m)return{kind:"approve",body:m[1].trim()||l};const x=r.match(/^【(?:不通过|打回|驳回)[:：](.*?)(?:】)?$/);if(x)return{kind:"reject",body:x[1].trim()||l};if(r==="【通过】")return{kind:"approve",body:l};if(r==="【不通过】"||r==="【打回】"||r==="【驳回】")return{kind:"reject",body:l};if(r==="【Pass】"||r==="【PASS】"||r==="【使用Pass卡】")return{kind:"pass",body:l};const F=r.match(/^【选择[:：](.+)】$/);if(F)return{kind:"choose",choice:F[1].trim(),body:l};const K=r.match(/^【(?:剪刀石头布|石头剪刀布)[:：](.+)】$/);return K?{kind:"choose",choice:K[1].trim(),body:l}:{kind:"",body:Ct(t,i)}}function Ds(s,t="rock"){const i=((s==null?void 0:s.choices)||[]).find(r=>(r==null?void 0:r.id)||(r==null?void 0:r.label));return String((i==null?void 0:i.id)||(i==null?void 0:i.label)||t).trim()}const Os=new Set(["反向诱惑","全部暴露！","羞耻台词大放送","自慰陈述"]);function qs(s,t){if(s==="final_note")return"本地预览：终局小纸条收到了。";const i=(t==null?void 0:t.pending_event)||null;if((i==null?void 0:i.type)==="duel"&&i.current_actor==="du")return"【剪刀石头布：石头】";if((i==null?void 0:i.type)==="choice"&&i.actor==="du"){const r=Ds(i,"");if(r)return`【选择：${r}】`}return(i==null?void 0:i.type)==="review"&&i.reviewer==="du"&&i.phase==="questioning"?"【真心话出题：本地预览：渡想问你的真心话问题。】":(i==null?void 0:i.type)==="review"&&i.actor==="du"&&i.phase==="assigned"?i.name==="真心话点名"?"【真心话回答：本地预览：渡已经回答真心话。】":Os.has(String(i.name||""))?"【描述：本地预览：渡已经完成任务，提交给你验收。】":`【提交】
本地预览：渡已经完成任务，提交给你验收。`:(i==null?void 0:i.type)==="review"&&i.reviewer==="du"&&i.phase==="submitted"?`【通过：本地预览：验收通过。】
【掷骰】`:he(t)?"【掷骰】":"本地预览：我看到了，等你继续行动。"}async function E(s){const t=await Mt("/miniapp-api/game-tools/private_board",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:s,save_id:"default"})});if(!(t!=null&&t.ok))throw new Error((t==null?void 0:t.error)||"走格棋命令失败");return t}async function Ys(s){var i;const t=await Mt("/miniapp-api/game-tools/private_board/sync-du",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({save_id:"default",mode:s.mode,message:s.message||"",roll_text:s.rollText||""})});if(!(t!=null&&t.ok))throw new Error((t==null?void 0:t.error)||((i=t==null?void 0:t.wakeup)==null?void 0:i.error)||"游戏内交流失败");return t}function he(s){return!!(s&&s.turn_actor==="du"&&!s.game_over)}function $t(s){const t=(s==null?void 0:s.pending_event)||null;if(!s||s.game_over||!t)return!1;if(t.type==="duel")return t.current_actor==="du";if(t.type==="choice")return t.actor==="du";if(t.type==="review"){const i=String(t.phase||"");return i==="questioning"||i==="submitted"?t.reviewer==="du":t.actor==="du"}return!1}function ue(s){const t=(s==null?void 0:s.pending_event)||null;if(!t)return"现在轮到渡行动。";if(t.type==="duel")return"现在轮到渡完成剪刀石头布对抗。";if(t.type==="choice")return"渡刚触发了需要自己选择的惩罚。";if(t.type==="review"){const i=String(t.phase||"");return i==="questioning"?"现在需要渡给出真心话题目。":i==="submitted"?"现在需要渡验收小玥提交的惩罚任务。":"现在需要渡提交惩罚任务。"}return"现在轮到渡处理棋局。"}function Qs({onBack:s}){var ct,dt,pt,xt,ut,ft,ht,gt,mt,bt,wt;const t=cs(),i=u.useRef(null),r=u.useRef(!1),l=u.useRef(null),d=u.useRef(null),o=u.useRef(null),g=u.useRef(null),m=u.useRef(""),[x,F]=u.useState(null),[K,L]=u.useState(ms),[Q,Z]=u.useState(1),[w,S]=u.useState(!1),[ee,G]=u.useState(!1),[k,me]=u.useState(!1),[Se,ne]=u.useState(null),[y,te]=u.useState(null),[ie,oe]=u.useState(!0),[ae,ze]=u.useState(null),[X,le]=u.useState(!1),[$,U]=u.useState(0),[ce,Ke]=u.useState(""),[A,Ce]=u.useState(!1),[B,$e]=u.useState(!1),[Et,be]=u.useState(!1),[We,Dt]=u.useState(""),[Ot,Je]=u.useState(!1),[Ve,qt]=u.useState(1),[re,Xe]=u.useState(""),[Ie,Le]=u.useState(null),[Pe,Qe]=u.useState(hs),v=(x==null?void 0:x.state)||{},Y=Math.max(12,Math.min(80,Number(v.board_size||36))),Be=Y<=36?6:8,Ee=v.turn_actor==="du"?"du":"xinyue",W=!!(v.game_over||x!=null&&x.game_over),we=Ee==="du"&&!W,z=v.pending_event||null,Me=u.useMemo(()=>{try{return!!new URLSearchParams(window.location.search).has("preview")}catch{return!1}},[]);u.useLayoutEffect(()=>{i.current&&(i.current.scrollTop=0)},[]),u.useEffect(()=>{r.current=X,X&&U(0)},[X]),u.useEffect(()=>{X&&window.setTimeout(()=>{var a;return(a=l.current)==null?void 0:a.scrollIntoView({block:"end"})},40)},[Pe.length,X,A]),u.useEffect(()=>{gs(Pe)},[Pe]),u.useEffect(()=>{if(!y||y.kind!=="draw"||y.tone!=="reward"){oe(!0);return}oe(!1);const a=window.setTimeout(()=>oe(!0),900);return()=>window.clearTimeout(a)},[y]);const j=u.useCallback((a,p=!1)=>{Qe(f=>[...f,a]),p&&!r.current&&U(f=>Math.min(9,f+1))},[]),Ze=u.useMemo(()=>{const a=new Map;for(const p of v.cell_events||[]){const f=Number((p==null?void 0:p.position)||0);f>0&&a.set(f,p)}return a},[v.cell_events]),Yt=u.useMemo(()=>js(Y,Be).map(a=>{const p=Ze.get(a),f=Ns(p,a,Y);return{position:a,event:p,kind:f,icon:_s(f),name:Ss(p,a,Y)}}),[Y,Be,Ze]),b=u.useCallback(a=>{var p,f,h,n;F(a),L({xinyue:Number(((f=(p=a.state)==null?void 0:p.positions)==null?void 0:f.xinyue)||0),du:Number(((n=(h=a.state)==null?void 0:h.positions)==null?void 0:n.du)||0)})},[]),et=u.useCallback(async()=>{S(!0);try{const a=await E("status");b(a)}catch(a){t(`加载涩涩走格棋失败：${(a==null?void 0:a.message)||a}`)}finally{S(!1)}},[b,t]);u.useEffect(()=>{et()},[et]);const tt=u.useCallback(async a=>{G(!0);for(let p=0;p<12;p+=1)Z(Math.floor(Math.random()*6)+1),await _e(58);Z(Math.max(1,Math.min(6,a||1))),G(!1)},[]),De=u.useCallback(async(a,p,f,h)=>{const n=Number(f||0),c=Number(h||0);if(n===c){a[p]=c,L({...a}),ne(Ge(c,Y)),await _e(120);return}const I=c>n?1:-1;for(let O=n+I;I>0?O<=c:O>=c;O+=I)a[p]=O,L({...a}),ne(Ge(O,Y)),await _e(145)},[Y]),Oe=u.useCallback(async()=>{var a,p,f,h,n;if(!(w||k)){S(!0),te(null);try{const c=await E("new_game");Z(1),b(c),Qe(fe()),U(0),ze(Ps((p=(a=c.state)==null?void 0:a.theme_profile)==null?void 0:p.theme,(h=(f=c.state)==null?void 0:f.theme_profile)==null?void 0:h.direction_label,(n=c.state)==null?void 0:n.theme_options))}catch(c){t(`开新局失败：${(c==null?void 0:c.message)||c}`)}finally{S(!1)}}},[k,b,w,t]);u.useCallback(async()=>{if(!(w||k)){S(!0);try{const a=await E("end_game");b(a)}catch(a){t(`结束本局失败：${(a==null?void 0:a.message)||a}`)}finally{S(!1)}}},[k,b,w,t]);const de=u.useCallback(async(a,p)=>{var O,P,V,ye,ve,ke,je,Ne,M,H;const f=a.trim()||"我看到了。",h=Es(f),n=(p==null?void 0:p.pending_event)||null,c=h.body.trim(),I=(n==null?void 0:n.reviewer)==="du"&&n.type==="review"&&n.phase==="submitted"&&(h.kind==="approve"||h.kind==="reject");c&&!I&&j({id:T("du"),speaker:"du",text:c},!0);try{if((n==null?void 0:n.type)==="duel"&&n.current_actor==="du"){if(h.kind!=="choose"||!h.choice.trim())return;const N=h.choice.trim(),_=ys(n,N),q=await E(`choose ${N}`);b(q);const pe=he(q.state)&&!((O=q.state)!=null&&O.pending_event);_&&(g.current=pe?{state:q.state,message:"剪刀石头布对抗已结算，现在轮到渡行动。"}:null,te({position:Number(n.cell||((V=(P=q.state)==null?void 0:P.positions)==null?void 0:V.du)||0),kicker:"剪刀石头布对抗",title:"对抗结果",text:_,detail:_,kind:"event"})),j({id:T("system"),speaker:"system",text:_||Fe(q,"渡已出拳，系统已判定对抗结果。")},!0),!_&&pe&&await((ye=o.current)==null?void 0:ye.call(o,q.state,"剪刀石头布对抗已结算，现在轮到渡行动。"));return}if((n==null?void 0:n.reviewer)==="du"&&n.type==="review"&&n.phase==="questioning"){if(h.kind!=="submit")return;const N=h.body.trim();if(!N){j({id:T("system"),speaker:"system",text:"渡发了【提交】，但后面没有题目。"},!0);return}const _=await E(`submit ${N}`);b(_),j({id:T("system"),speaker:"system",text:"渡已出题，轮到你回答。"},!0);return}if((n==null?void 0:n.actor)==="du"&&n.type==="review"&&n.phase==="assigned"){if(h.kind!=="submit")return;const N=h.body.trim();if(!N){j({id:T("system"),speaker:"system",text:"渡发了【提交】，但后面没有提交内容。"},!0);return}const _=await E(`submit ${N}`);b(_),j({id:T("system"),speaker:"system",text:"渡已提交惩罚任务，等你验收。"},!0),await((ve=o.current)==null?void 0:ve.call(o,_.state,ue(_.state)));return}if((n==null?void 0:n.actor)==="du"&&n.type==="choice"){if(h.kind==="pass"){const _=await E("pass");if(b(_),_.ok===!1){j({id:T("system"),speaker:"system",text:Fe(_,"渡没有Pass卡，不能跳过。")},!0);return}j({id:T("system"),speaker:"system",text:"渡使用Pass卡跳过了惩罚。"},!0),await((ke=o.current)==null?void 0:ke.call(o,_.state,ue(_.state)));return}if(h.kind!=="choose"||!h.choice.trim())return;const N=await E(`choose ${h.choice.trim()}`);b(N),j({id:T("system"),speaker:"system",text:"渡已选择惩罚选项。"},!0),await((je=o.current)==null?void 0:je.call(o,N.state,ue(N.state)));return}if((n==null?void 0:n.reviewer)==="du"&&n.type==="review"&&n.phase==="submitted"){if(h.kind==="approve"){const N=Bs(f),_=h.body.trim()||"验收通过。",q=await E(`approve ${_}`);if(b(q),Le({outcome:"approved",title:"渡验收通过",text:_,note:N?"已继续执行渡的掷骰。":"棋局继续。"}),N&&he(q.state)){await _e(260),await((Ne=d.current)==null?void 0:Ne.call(d,{notifyAfterUserRoll:!1}));return}await((M=o.current)==null?void 0:M.call(o,q.state,ue(q.state)));return}if(h.kind==="reject"){const N=h.body.trim()||"需要重新提交。",_=await E(`reject ${N}`);b(_),Le({outcome:"rejected",title:"渡打回了任务",text:N,note:"请按反馈修改后重新提交。"});return}return}he(p)&&Ls(f)&&(await _e(260),j({id:T("system"),speaker:"system",text:"渡发送【掷骰】，已执行他的行动。"},!0),await((H=d.current)==null?void 0:H.call(d,{notifyAfterUserRoll:!1})))}catch(N){j({id:T("system"),speaker:"system",text:`渡的指令执行失败：${String((N==null?void 0:N.message)||N)}`},!0)}},[j,b]),se=u.useCallback(async(a,p)=>{if(!Me)return Ys(a);let f=p,h="";if(a.mode==="final_note"){const c=await E("final_note_sent");f=c.state||f,h=c.player_text||c.text||""}const n=qs(a.mode,f);return{ok:!0,state:f,player_text:h,reply_text:n,reply_preview:n.slice(0,120),wakeup:{reply_text:n,reply_preview:n.slice(0,120)}}},[Me]),st=u.useCallback(async(a,p="现在轮到渡行动。")=>{var h,n;const f=$t(a);if(!(!he(a)||a!=null&&a.pending_event&&!f)){$e(!0);try{const c=await se({mode:"state_update",message:p,rollText:""},a);c.state&&b({ok:!0,state:c.state,player_text:c.player_text||""});const I=xe(c.reply_text||((h=c.wakeup)==null?void 0:h.reply_text)||c.reply_preview||((n=c.wakeup)==null?void 0:n.reply_preview)||"").trim();await de(I,c.state||a)}catch(c){const I=String((c==null?void 0:c.message)||c||"同步失败");j({id:T("system"),speaker:"system",text:`渡行动同步失败：${I}`},!0),t(`渡行动同步失败：${I}`)}finally{$e(!1)}}},[j,b,de,se,t]);u.useEffect(()=>{o.current=st},[st]);const Ft=u.useCallback(()=>{var p;const a=g.current;g.current=null,te(null),a&&((p=o.current)==null||p.call(o,a.state,a.message))},[]),it=u.useCallback(async(a,p="小玥刚掷完骰子。")=>{var I,O;const f=xe(a.text||a.du_text||a.player_text||"").trim(),h=m.current.trim(),n=p.trim()==="小玥刚掷完骰子。"?"":p.trim(),c=[h,n].filter(Boolean).join(`
`);$e(!0);try{const P=await se({mode:"roll_result",message:c,rollText:f},a.state);h&&m.current.trim()===h&&(m.current=""),P.state&&b({ok:!0,state:P.state,player_text:P.player_text||a.player_text||""});const V=xe(P.reply_text||((I=P.wakeup)==null?void 0:I.reply_text)||P.reply_preview||((O=P.wakeup)==null?void 0:O.reply_preview)||"").trim();await de(V,P.state||a.state)}catch(P){const V=String((P==null?void 0:P.message)||P||"同步失败");j({id:T("system"),speaker:"system",text:`自动同步失败：${V}`},!0),t(`自动同步给渡失败：${V}`)}finally{$e(!1)}},[j,b,de,se,t]),qe=u.useCallback(async(a={})=>{var I,O,P,V,ye,ve,ke,je,Ne;if(w||k||W)return;let p=null,f=null;S(!0),me(!0),te(null);const h={xinyue:Number(((I=v.positions)==null?void 0:I.xinyue)||0),du:Number(((O=v.positions)==null?void 0:O.du)||0)},n=v.turn_actor==="du"?"du":"xinyue",c={...h};try{const M=await E("roll"),H=zs(M.player_text||"");await tt((H==null?void 0:H.dice)||Math.floor(Math.random()*6)+1),H&&await De(c,H.actor,H.from,H.to);const N={xinyue:Number(((V=(P=M.state)==null?void 0:P.positions)==null?void 0:V.xinyue)||0),du:Number(((ve=(ye=M.state)==null?void 0:ye.positions)==null?void 0:ve.du)||0)};for(const pe of kt){const yt=Number(c[pe]||0),vt=Number(N[pe]||0);yt!==vt&&await De(c,pe,yt,vt)}b(M);const _=$s(M.player_text||"",H);_&&te(_);const q=((ke=M.state)==null?void 0:ke.pending_event)||null;a.notifyAfterUserRoll!==!1&&n==="xinyue"&&!((je=M.state)!=null&&je.game_over)&&(!q||$t(M.state))?p=M:a.notifyAfterUserRoll===!1&&n==="du"&&he(M.state)&&(f=M)}catch(M){t(`掷骰失败：${(M==null?void 0:M.message)||M}`)}finally{S(!1),me(!1),window.setTimeout(()=>ne(null),260)}p?await it(p):f&&await((Ne=o.current)==null?void 0:Ne.call(o,f.state,ue(f.state)))},[De,tt,k,b,w,W,it,v.positions,v.turn_actor,t]);u.useEffect(()=>{d.current=qe},[qe]);const J=u.useCallback(async(a,p={})=>{var h,n;if(w||!(x!=null&&x.state))return;let f=null;S(!0),te(null);try{const c=await E(a);if(f=c,b(c),c.ok===!1){t(Fe(c,"这次操作没有生效。"));return}Xe(""),p.success&&j({id:T("system"),speaker:"system",text:p.success},!0),(h=p.deferSyncMessage)!=null&&h.trim()&&(m.current=p.deferSyncMessage.trim())}catch(c){t(`处理惩罚任务失败：${(c==null?void 0:c.message)||c}`)}finally{S(!1)}f&&p.syncAfter&&await((n=o.current)==null?void 0:n.call(o,f.state,p.syncMessage||ue(f.state)))},[j,b,w,x==null?void 0:x.state,t]),Gt=u.useCallback(()=>{const a=re.trim();if(!a){t("先写提交内容。");return}J(`submit ${a}`,{success:"已提交任务，等渡验收。",syncAfter:!0,syncMessage:"小玥提交了惩罚任务，请你验收。"})},[J,re,t]),Ut=u.useCallback(()=>{const a=re.trim();J(a?`approve ${a}`:"approve",{success:"你通过了任务，棋局继续。",deferSyncMessage:a?`小玥刚刚通过了你的惩罚任务：${a}`:"小玥刚刚通过了你的惩罚任务。"})},[J,re]),Ht=u.useCallback(()=>{const a=re.trim();J(a?`reject ${a}`:"reject",{success:"你打回了任务，等渡重新提交。",syncAfter:!0,syncMessage:a?`小玥打回了你的惩罚任务：${a}`:"小玥打回了你的惩罚任务，请重新提交。"})},[J,re]),Kt=u.useCallback(a=>{const p=(z==null?void 0:z.type)==="duel",f=(z==null?void 0:z.current_actor)||(z==null?void 0:z.actor);if(p&&!(p&&f==="xinyue")){t("等待渡出拳。");return}J(`choose ${a}`,{success:p?"已出拳，等待渡出拳。":"已选择惩罚，棋局继续。",syncAfter:!0,syncMessage:p?"小玥已在剪刀石头布对抗中出拳。请第一行单独发送【剪刀石头布：石头】、【剪刀石头布：剪刀】或【剪刀石头布：布】。":"小玥处理完选择惩罚，棋局继续。"})},[J,z==null?void 0:z.actor,z==null?void 0:z.current_actor,z==null?void 0:z.type,t]),Wt=u.useCallback(()=>{J("pass",{success:"已使用Pass卡跳过惩罚。",syncAfter:!0,syncMessage:"小玥使用Pass卡跳过了惩罚任务。"})},[J]),Jt=u.useCallback(async()=>{var p,f,h;const a=((p=x==null?void 0:x.state)==null?void 0:p.final_note)||null;if(!(A||B||w||k||!(x!=null&&x.state)||!a||a.sent)){Ce(!0);try{const n=await se({mode:"final_note",message:a.text||""},x.state);n.state&&b({ok:!0,state:n.state,player_text:n.player_text||x.player_text||""}),j({id:T("system"),speaker:"system",text:Me?"预览模式：终局小纸条已同步。":"终局小纸条已发送给渡。"},!0);const c=xe(n.reply_text||((f=n.wakeup)==null?void 0:f.reply_text)||n.reply_preview||((h=n.wakeup)==null?void 0:h.reply_preview)||"").trim();c&&j({id:T("du"),speaker:"du",text:c},!0),be(!1)}catch(n){const c=String((n==null?void 0:n.message)||n||"同步失败");j({id:T("system"),speaker:"system",text:`小纸条发送失败：${c}`},!0),t(`发送终局小纸条失败：${c}`)}finally{Ce(!1)}}},[k,j,b,w,A,B,Me,x,se,t]),Vt=u.useCallback(async(a,p,f=1)=>{if(A||B||w||k||!(x!=null&&x.state))return;const h=p.replace(/\s+/g," ").trim();if(!h){t("先选要追加的内容。");return}const n=a==="prop"&&Bt(h)?` level=${Math.max(1,Math.min(5,Math.round(Number(f)||1)))}`:"";S(!0);try{const c=await E(`append_final_status ${a} ${h}${n}`);b(c),be(!0),t(`已启用：${h}`)}catch(c){t(`追加失败：${(c==null?void 0:c.message)||c}`)}finally{S(!1)}},[k,b,w,A,B,x==null?void 0:x.state,t]),Xt=u.useCallback(async(a,p)=>{if(A||B||w||k||!(x!=null&&x.state))return;const f=p.replace(/\s+/g," ").trim();if(f){S(!0);try{const h=await E(`remove_final_status ${a} ${f}`);b(h),be(!0),t(`已取消：${f}`)}catch(h){t(`取消失败：${(h==null?void 0:h.message)||h}`)}finally{S(!1)}}},[k,b,w,A,B,x==null?void 0:x.state,t]),Qt=u.useCallback(async()=>{var f,h;if(A||B||w||k||!(x!=null&&x.state))return;const a=ce.trim();if(!a)return;const p={id:T("me"),speaker:"xinyue",text:a};Ke(""),j(p),Ce(!0);try{const n=await se({mode:"chat",message:a},x.state);n.state&&b({ok:!0,state:n.state,player_text:n.player_text||x.player_text||""});const c=xe(n.reply_text||((f=n.wakeup)==null?void 0:f.reply_text)||n.reply_preview||((h=n.wakeup)==null?void 0:h.reply_preview)||"").trim();await de(c,n.state||x.state)}catch(n){const c=String((n==null?void 0:n.message)||n||"同步失败");j({id:T("system"),speaker:"system",text:`交流失败：${c}`}),t(`游戏内交流失败：${c}`)}finally{Ce(!1)}},[k,j,b,w,ce,A,B,x,de,se,t]),Zt=C(((ct=v.theme_profile)==null?void 0:ct.theme)||"未触发"),es=C(((dt=v.theme_profile)==null?void 0:dt.direction_label)||"待定"),ts=Nt((pt=v.positions)==null?void 0:pt.xinyue,Y),ss=Nt((xt=v.positions)==null?void 0:xt.du,Y),Ye=v.winner?He[v.winner]:"",at=Is((x==null?void 0:x.player_text)||""),D=v.final_note||null,rt=Lt(v.final_note_items||[],D),Te=String((D==null?void 0:D.id)||`${v.winner||""}-${v.updated_at||""}`),nt=!!(W&&v.winner==="xinyue"&&(!D||D.target==="du")&&!(D!=null&&D.sent)),is=(((ut=v.statuses)==null?void 0:ut.du)||[]).filter(a=>a.slot==="prop").map(a=>C(a.value||""));u.useEffect(()=>{!W||!D||!Te||We!==Te&&(Dt(Te),be(!0))},[D,Te,We,W]);const as=Math.max(0,Number(((ht=(ft=v.hands)==null?void 0:ft.xinyue)==null?void 0:ht.pass)||0)),rs=Math.max(0,Number(v.pass_skips_used||0)),ot={xinyue:zt((gt=v.statuses)==null?void 0:gt.xinyue),du:zt((mt=v.statuses)==null?void 0:mt.du)},lt=we&&ot.du&&!z,ns=w||k||A||B||!(x!=null&&x.state)||!!z||we&&!lt,os=!(x!=null&&x.state),ls=A||B||w||k||!(x!=null&&x.state);return e.jsxs("div",{className:"sese-game",ref:i,children:[e.jsxs("div",{className:"sese-header",children:[e.jsx("button",{className:"sese-back",type:"button",onClick:s,"aria-label":"返回游戏",children:e.jsx(ds,{})}),e.jsxs("button",{className:"sese-chat-entry",type:"button",onClick:()=>le(!0),"aria-label":"游戏内交流",children:[e.jsx(ps,{}),$?e.jsx("span",{children:$}):null]}),e.jsx("div",{className:"sese-header-title",children:"涩涩走格棋"}),e.jsxs("div",{className:"sese-game-status-bar",children:[e.jsx(Ae,{label:"主题",value:Zt}),e.jsx(Ae,{label:"主导方",value:es}),e.jsx(Ae,{label:"我 进度",value:`${String(ts).padStart(2,"0")} / ${Y}`}),e.jsx(Ae,{label:"渡 进度",value:`${String(ss).padStart(2,"0")} / ${Y}`}),e.jsx("div",{className:"sese-turn-indicator",children:W&&Ye?`${Ye} 到达终点`:we?"等待 渡 行动...":"轮到 我 行动"})]})]}),e.jsx("section",{className:"sese-board-container","aria-label":"走格棋盘",children:e.jsx("div",{className:"sese-board",style:{gridTemplateColumns:`repeat(${Be}, minmax(0, 1fr))`},children:Yt.map(a=>{const p=kt.filter(f=>Ge(K[f],Y)===a.position);return e.jsxs("div",{className:`sese-tile sese-tile-${a.kind} ${Se===a.position?"is-active":""}`,children:[e.jsx("div",{className:"sese-tile-number",children:a.position}),e.jsx("div",{className:"sese-tile-icon",children:a.icon}),e.jsx("div",{className:"sese-tile-name",children:a.name}),e.jsx("div",{className:"sese-piece-stack",children:p.map(f=>e.jsx("span",{className:`sese-piece ${f==="xinyue"?"sese-piece-me":"sese-piece-du"} ${ot[f]?"paused":""}`,children:He[f]},f))})]},a.position)})})}),e.jsxs("section",{className:"sese-controls",children:[e.jsxs("div",{className:"sese-player-states",children:[e.jsx(Pt,{actor:"xinyue",statuses:((bt=v.statuses)==null?void 0:bt.xinyue)||[],active:Ee==="xinyue"}),e.jsx(Pt,{actor:"du",statuses:((wt=v.statuses)==null?void 0:wt.du)||[],active:Ee==="du"})]}),rt.length?e.jsx("div",{className:"sese-final-pose-panel",children:rt.map(a=>e.jsxs("div",{className:"sese-final-material-row",children:[e.jsx("span",{children:a.label}),e.jsx("strong",{children:a.values.join("、")})]},a.label))}):null,e.jsxs("div",{className:"sese-action-area",children:[e.jsx("div",{className:`sese-dice ${ee?"rolling":""}`,"aria-label":`骰子 ${Q}`,children:Q}),e.jsx("button",{className:"sese-roll-button",type:"button",disabled:ns,onClick:W?Oe:()=>void qe({notifyAfterUserRoll:!0}),children:W?"开新局":z?"先处理任务":lt?"处理停步":we?"等渡掷骰":w||k?"移动中":A||B?"等渡回应":"掷骰子"}),e.jsx("button",{className:"sese-restart-button",type:"button",disabled:w||k||A||B,onClick:Oe,children:"重开"})]}),e.jsx("div",{className:"sese-history",children:at.length?`最近：${at[0]}`:"最近：等待第一次掷骰"})]}),X?e.jsx("div",{className:"sese-chat-mask",role:"dialog","aria-modal":"true","aria-label":"游戏内交流",onClick:()=>le(!1),children:e.jsxs("div",{className:"sese-chat-panel",onClick:a=>a.stopPropagation(),children:[e.jsxs("div",{className:"sese-chat-head",children:[e.jsxs("div",{children:[e.jsx("strong",{children:"游戏内交流"}),e.jsx("span",{children:we?"等待渡发送【掷骰】":"当前轮到你行动"})]}),e.jsx("button",{type:"button",onClick:()=>le(!1),"aria-label":"关闭交流",children:"×"})]}),e.jsxs("div",{className:"sese-chat-list",children:[Pe.map(a=>e.jsxs("div",{className:`sese-chat-message ${a.speaker}`,children:[e.jsx("span",{children:a.speaker==="xinyue"?"我":a.speaker==="du"?"渡":"系统"}),e.jsx("p",{children:xe(a.text)})]},a.id)),A?e.jsxs("div",{className:"sese-chat-message du pending",children:[e.jsx("span",{children:"渡"}),e.jsx("p",{children:"正在回复..."})]}):null,e.jsx("div",{ref:l})]}),e.jsxs("form",{className:"sese-chat-form",onSubmit:a=>{a.preventDefault(),Qt()},children:[e.jsx("input",{value:ce,disabled:os,placeholder:"和渡说一句游戏内的话",onChange:a=>Ke(a.target.value)}),e.jsx("button",{type:"submit",disabled:ls||!ce.trim(),"aria-label":A?"发送中":"发送",children:e.jsx(xs,{})})]})]})}):null,ae?e.jsx("div",{className:"sese-theme-mask",role:"dialog","aria-modal":"true","aria-label":"开局主题抽取",children:e.jsxs("div",{className:"sese-theme-modal",children:[e.jsxs("div",{className:"sese-slot-lights","aria-hidden":"true",children:[e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{})]}),e.jsxs("div",{className:"sese-slot-marquee",children:[e.jsx("span",{children:"THEME"}),e.jsx("strong",{children:"JACKPOT"})]}),e.jsxs("div",{className:"sese-slot-face",children:[e.jsx("div",{className:"sese-theme-window",children:e.jsx("div",{className:"sese-theme-strip",children:ae.items.map((a,p)=>e.jsx("div",{className:"sese-theme-item",children:C(a)},`${a}-${p}`))},ae.spinKey)}),e.jsxs("p",{className:"sese-slot-plaque",children:["主导方：",ae.direction]}),e.jsxs("div",{className:"sese-theme-actions",children:[e.jsx("button",{className:"secondary",type:"button",disabled:w,onClick:Oe,children:w?"重抽中":"重抽主题"}),e.jsx("button",{type:"button",onClick:()=>ze(null),children:"开始本局"})]}),e.jsx("div",{className:"sese-slot-tray","aria-hidden":"true"})]})]})}):null,z&&!y?e.jsx("div",{className:"sese-pending-mask",role:"dialog","aria-modal":"true","aria-label":"待处理惩罚",children:e.jsx("div",{className:"sese-pending-modal",children:e.jsx(Ws,{pending:z,reviewFeedback:Ie,passCount:as,passSkipsUsed:rs,submission:re,disabled:w||B,onSubmissionChange:Xe,onSubmit:Gt,onApprove:Ut,onReject:Ht,onChoose:Kt,onPass:Wt})})}):null,W&&D&&Et?e.jsx("div",{className:"sese-final-note-mask",role:"dialog","aria-modal":"true","aria-label":"终局小纸条",children:e.jsxs("div",{className:"sese-final-note-modal",children:[e.jsxs("div",{className:"sese-final-note-head",children:[e.jsx("span",{children:"终局小纸条"}),e.jsx("button",{type:"button",onClick:()=>be(!1),"aria-label":"关闭终局小纸条",children:"关闭"})]}),e.jsxs("h2",{children:[Ye||"玩家"," 到达终点"]}),e.jsx(Gs,{note:D,canAddStatus:nt,onAddStatus:()=>Je(!0)}),D.sent?e.jsx("em",{children:"已发送给渡"}):e.jsx("button",{className:"sese-final-note-send",type:"button",disabled:A||B||w||k,onClick:()=>void Jt(),children:A?"发送中":"发送给渡"})]})}):null,nt&&Ot?e.jsx(Fs,{level:Ve,activeProps:is,disabled:A||B||w||k,onClose:()=>Je(!1),onLevelChange:qt,onToggleProp:(a,p)=>{p?Xt("prop",a):Vt("prop",a,Ve)}}):null,y?e.jsx("div",{className:"sese-popup-mask",role:"dialog","aria-modal":"true",children:e.jsxs("div",{className:`sese-popup ${y.kind==="draw"?`sese-popup-draw tone-${y.tone||"penalty"}`:""}`,children:[e.jsx("div",{className:"sese-popup-kicker",children:R(y.kicker||(y.actorLabel?`${y.actorLabel}走到第 ${y.position} 格`:`第 ${y.position} 格`))}),y.kind==="draw"?e.jsx("div",{className:`sese-draw-card ${y.tone==="reward"&&!ie?"is-covered":"is-revealed"}`,children:y.tone==="reward"&&!ie?e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"sese-card-pile","aria-hidden":"true",children:[e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("b",{})]}),e.jsx("span",{children:"奖励抽卡"}),e.jsx("em",{children:"抽卡中"})]}):e.jsxs(e.Fragment,{children:[_t(y)?e.jsx("span",{children:_t(y)}):null,e.jsx("strong",{children:R(y.cardTitle||y.title)})]})}):null,y.kind==="draw"?null:e.jsx("h2",{children:R(y.title)}),y.tone==="reward"&&!ie?e.jsx("p",{children:"正在洗牌..."}):St(y)?e.jsx("p",{children:St(y)}):null,y.tone==="reward"&&!ie?null:e.jsx("button",{type:"button",onClick:Ft,children:"确 认"})]})}):null,Ie?e.jsx("div",{className:"sese-pending-mask",role:"dialog","aria-modal":"true","aria-label":"验收反馈",children:e.jsx("div",{className:"sese-pending-modal",children:e.jsx(Js,{feedback:Ie,onClose:()=>Le(null)})})}):null,e.jsx("style",{children:`
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
          display: flex;
          max-height: calc(100dvh - max(env(safe-area-inset-top, 0px), 18px) - max(env(safe-area-inset-bottom, 0px), 18px) - 24px);
          min-height: 0;
          width: min(360px, 100%);
        }
        .sese-pending-modal .sese-pending-card {
          box-sizing: border-box;
          display: flex;
          flex-direction: column;
          max-height: 100%;
          min-height: 0;
          width: 100%;
          overflow: hidden;
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
          flex: 0 0 auto;
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
        .sese-pending-card > p,
        .sese-pending-card > .sese-review-feedback,
        .sese-pending-card > .sese-pending-tip,
        .sese-pending-card > .sese-pending-wait {
          flex: 0 1 auto;
          min-height: 0;
          max-height: min(32dvh, 240px);
          overflow-y: auto;
          overscroll-behavior: contain;
          -webkit-overflow-scrolling: touch;
        }
        .sese-pending-tip,
        .sese-pending-wait {
          margin-top: 6px;
          border-radius: 10px;
          background: var(--soft-lavender);
          padding: 6px 8px;
        }
        .sese-review-feedback {
          margin-top: 8px;
          border: 1px solid rgba(186, 104, 200, 0.24);
          border-radius: 12px;
          background: #fff;
          color: var(--text-main);
          padding: 8px 10px;
          font-size: 12px;
          font-weight: 800;
          line-height: 1.45;
          white-space: pre-wrap;
          word-break: break-word;
        }
        .sese-submission-text {
          max-height: min(36dvh, 260px);
          overflow-y: auto;
          overscroll-behavior: contain;
          -webkit-overflow-scrolling: touch;
          min-height: 44px;
          white-space: pre-wrap;
          word-break: break-word;
        }
        .sese-pending-card textarea {
          flex: 0 0 auto;
          display: block;
          width: 100%;
          min-height: 82px;
          max-height: min(24dvh, 150px);
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
        .sese-choice-list {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 8px;
          margin-top: 9px;
        }
        .sese-review-actions {
          flex: 0 0 auto;
          display: flex;
          flex-wrap: wrap;
          justify-content: center;
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
        .sese-review-actions button {
          flex: 1 1 112px;
          max-width: 180px;
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
        `})]})}function Ae({label:s,value:t}){return e.jsxs("div",{className:"sese-pill",children:[e.jsx("span",{children:s}),e.jsx("strong",{children:t})]})}function Pt({actor:s,statuses:t,active:i}){const r=Rs(t);return e.jsxs("div",{className:`sese-player-card sese-player-card-${s} ${i?"active":""}`,children:[e.jsx("div",{className:"sese-player-card-head",children:e.jsx("h2",{children:s==="xinyue"?"我的状态":"渡的状态"})}),e.jsx("div",{className:"sese-status-list",children:r.length?r.map(l=>e.jsxs("div",{className:"sese-status-group",children:[e.jsx("span",{className:"sese-status-group-label",children:l.label}),e.jsx("div",{className:"sese-status-chip-row",children:l.values.map(d=>e.jsx("span",{className:"sese-status-chip",children:d},`${l.label}-${d}`))})]},l.label)):e.jsx("div",{className:"sese-status-empty",children:"无状态"})})]})}function Fs({level:s,activeProps:t,disabled:i,onClose:r,onLevelChange:l,onToggleProp:d}){const o=new Set(t);return e.jsx("div",{className:"sese-toy-console-mask",role:"dialog","aria-modal":"true","aria-label":"玩具控制台",onClick:r,children:e.jsxs("div",{className:"sese-toy-console-sheet",onClick:g=>g.stopPropagation(),children:[e.jsxs("div",{className:"sese-toy-console-head",children:[e.jsxs("div",{children:[e.jsx("span",{children:"玩具控制台"}),e.jsx("strong",{children:"控制渡当前状态"})]}),e.jsx("button",{type:"button",onClick:r,"aria-label":"关闭玩具控制台",children:"关闭"})]}),e.jsxs("div",{className:"sese-toy-console-section",children:[e.jsx("label",{children:"道具档位"}),e.jsx("div",{className:"sese-toy-level-row",children:[1,2,3,4,5].map(g=>e.jsx("button",{type:"button",disabled:i,className:g===s?"selected":"",onClick:()=>l(g),children:g},g))})]}),e.jsxs("div",{className:"sese-toy-console-section",children:[e.jsx("label",{children:"启用道具"}),e.jsx("div",{className:"sese-toy-chip-grid",children:vs.map(g=>(()=>{const m=o.has(g);return e.jsx("button",{type:"button",disabled:i,className:m?"selected":"","aria-pressed":m,"aria-label":m?`取消启用${g}`:`启用${g}`,onClick:()=>d(g,m),children:g},g)})())})]})]})})}function Gs({note:s,canAddStatus:t=!1,onAddStatus:i}){const r=Hs(s),l=C(s.theme||"本局主题"),d=s.target==="du"?"渡当前状态":"你的当前状态",o=Ks(s.target_status||""),g=Lt([],s);return e.jsxs("div",{className:"sese-final-note-body",children:[e.jsx("div",{className:"sese-final-note-intro",children:r}),e.jsxs("div",{className:"sese-final-note-section",children:[e.jsx("span",{children:"本局主题"}),e.jsx("strong",{children:l})]}),e.jsxs("div",{className:"sese-final-note-section",children:[e.jsxs("div",{className:"sese-final-note-section-title",children:[e.jsx("span",{children:d}),t?e.jsx("button",{type:"button",onClick:i,"aria-label":"打开玩具控制台",children:e.jsx(Us,{})}):null]}),o.length?o.map(m=>e.jsxs("div",{className:"sese-final-note-status-group",children:[e.jsx("b",{children:m.label}),e.jsx("div",{className:"sese-final-note-status-values",children:m.values.map(x=>e.jsx("span",{children:x},x))})]},m.label)):e.jsx("div",{className:"sese-final-note-empty",children:"没有遗留状态，可以自由决定最后玩法。"})]}),g.map(m=>e.jsxs("div",{className:"sese-final-note-section",children:[e.jsx("span",{children:m.label}),e.jsx("strong",{children:m.values.join("、")})]},m.label)),e.jsx("div",{className:"sese-final-note-closing",children:"请尽情享受你们的ooxx吧！"})]})}function Us(){return e.jsx("svg",{viewBox:"0 0 24 24","aria-hidden":"true",children:e.jsx("path",{d:"M12 5v14M5 12h14"})})}function Hs(s){return R(s.text||"").split(`
`).map(r=>r.trim()).filter(Boolean).find(r=>!r.startsWith("【")&&!r.startsWith("请根据")&&!r.startsWith("本局主题")&&!r.startsWith("请尽情"))||"终点已到达，赢家状态已清空。"}function Ks(s){const t=R(s).trim();return!t||t==="无"?[]:t.split("；").map(i=>i.trim()).filter(Boolean).map(i=>{const r=i.indexOf("：");if(r<0)return{label:"状态",values:[i]};const l=i.slice(0,r).trim()||"状态",d=i.slice(r+1).split("、").map(o=>o.trim()).filter(Boolean);return{label:l,values:d.length?d:["无"]}})}function Ws({pending:s,reviewFeedback:t,passCount:i,passSkipsUsed:r,submission:l,disabled:d,onSubmissionChange:o,onSubmit:g,onApprove:m,onReject:x,onChoose:F,onPass:K}){var X,le;const L=R(s.name||"惩罚任务"),Q=s.actor||"xinyue",Z=s.reviewer||(Q==="xinyue"?"du":"xinyue"),w=s.current_actor||Q,S=Q==="xinyue",ee=w==="xinyue",G=Z==="xinyue",k=!!C(s.question_text||"").trim(),me=C(s.last_reject_reason||"").trim(),Se=S&&s.pass_allowed!==!1&&i>0&&r<1&&!["submitted","questioning"].includes(String(s.phase||"")),ne=R(s.submission||"").trim(),y=/^你的回答[。.]?$/.test(ne)?"":ne,[te,ie]=u.useState("");u.useEffect(()=>{ie("")},[s.id,s.current_actor,s.phase]);const oe=ge(te||((X=s.picks)==null?void 0:X.xinyue)),ae=!!ge((le=s.picks)==null?void 0:le.xinyue);if(s.type==="choice")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:S?"你的选择惩罚":"等待渡选择"}),e.jsx("strong",{children:L})]}),e.jsx("p",{children:R(s.prompt||"选择一项惩罚。")}),S?e.jsx("div",{className:"sese-choice-list",children:(s.choices||[]).map($=>{const U=String($.id||$.label||"");return e.jsx("button",{type:"button",disabled:d||!U,onClick:()=>F(U),children:R($.label||U)},U)})}):e.jsx("div",{className:"sese-pending-wait",children:"等待渡选择惩罚。"}),Se?e.jsx("button",{className:"sese-pass-button",type:"button",disabled:d,onClick:K,children:"使用Pass卡跳过"}):null]});if(s.type==="duel")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:ee?"轮到你出拳":"等待渡出拳"}),e.jsx("strong",{children:L||"剪刀石头布对抗"})]}),e.jsx("p",{children:"同格触发对抗。双方各出石头、剪刀或布，系统判定胜负；赢的前进 3 格，输的后退 3 格。"}),e.jsx("div",{className:"sese-choice-list sese-rps-list",children:At.map($=>e.jsx("button",{className:`sese-rps-button ${oe===$.id?"is-selected":""}`,type:"button",title:$.label,"aria-label":$.label,"aria-pressed":oe===$.id,disabled:d||!ee||ae,onClick:()=>{ie(ge($.id)),F($.id)},children:$.icon},$.id))}),ee?null:e.jsx("div",{className:"sese-pending-wait",children:ae?"你的出拳已记录，等待渡出拳。":"等待渡出拳。"})]});if(s.phase==="submitted")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:G?"需要你验收":"等待渡验收"}),e.jsx("strong",{children:L})]}),e.jsx("p",{className:"sese-submission-text",children:C(s.submission_text||"")}),G?e.jsxs(e.Fragment,{children:[e.jsx("textarea",{value:l,placeholder:"写一句验收反馈，会同步给渡",onChange:$=>o($.target.value)}),e.jsxs("div",{className:"sese-review-actions",children:[e.jsx("button",{type:"button",disabled:d,onClick:m,children:"通过"}),e.jsx("button",{type:"button",disabled:d,onClick:x,children:"打回"})]})]}):e.jsx("div",{className:"sese-pending-wait",children:"等待渡验收你的提交。"})]});if(s.phase==="questioning"){const $=R(s.question_prompt||"请问对方一个你很想知道答案却一直没有问的问题。"),U=R(s.waiting_task||"对方正在出题中。");return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:G?"你来出题":"等待渡出题"}),e.jsx("strong",{children:L})]}),G?e.jsxs(e.Fragment,{children:[e.jsx("p",{children:$}),e.jsx("textarea",{value:l,placeholder:"写下你的问题",onChange:ce=>o(ce.target.value)}),e.jsx("div",{className:"sese-review-actions",children:e.jsx("button",{type:"button",disabled:d||!l.trim(),onClick:g,children:"提交题目"})})]}):e.jsx("div",{className:"sese-pending-wait",children:U==="对方正在出题中。"?"等待渡给出真心话题目。":U})]})}const ze=k?"等待渡回答这个问题。":"等待渡完成并提交任务。";return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:S?"你的惩罚任务":"等待渡提交"}),e.jsx("strong",{children:L})]}),me?e.jsxs("div",{className:"sese-review-feedback",children:["打回反馈：",me]}):null,t&&t.outcome==="rejected"&&S?e.jsxs("div",{className:"sese-review-feedback",children:["渡的反馈：",t.text]}):null,k?e.jsxs("p",{className:"sese-submission-text",children:["题目：",C(s.question_text)]}):null,S?e.jsxs(e.Fragment,{children:[k?null:e.jsx("p",{children:R(s.task||"")}),!k&&y?e.jsxs("div",{className:"sese-pending-tip",children:["提交要求：",y]}):null,e.jsx("textarea",{value:l,placeholder:k?"在这里写回答":"在这里写提交内容",onChange:$=>o($.target.value)}),e.jsxs("div",{className:"sese-review-actions",children:[e.jsx("button",{type:"button",disabled:d||!l.trim(),onClick:g,children:k?"提交回答":"提交验收"}),Se?e.jsx("button",{type:"button",disabled:d,onClick:K,children:"使用Pass卡"}):null]})]}):e.jsx("div",{className:"sese-pending-wait",children:e.jsx("span",{children:ze})})]})}function Js({feedback:s,onClose:t}){return e.jsxs("div",{className:"sese-pending-card sese-review-feedback-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:s.outcome==="approved"?"通过反馈":"打回反馈"}),e.jsx("strong",{children:s.title})]}),e.jsx("div",{className:"sese-review-feedback",children:s.text}),e.jsx("div",{className:"sese-pending-wait",children:s.note}),e.jsx("div",{className:"sese-review-actions",children:e.jsx("button",{type:"button",onClick:t,children:"知道了"})})]})}export{Qs as SeseBoardGameTab};
