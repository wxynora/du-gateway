import{u as ss,r as x,j as e,C as as,M as is,S as rs,b as _t}from"./index-CCOa2YrM.js";const St="du-gateway:sese-board-game:chat:v1",ns=new Set(["xinyue","du","system"]),os=[{id:"system-ready",speaker:"system",text:"游戏内交流在这里。渡明确发送【掷骰】时，棋盘才会执行他的行动。"}];function re(){return os.map(s=>({...s}))}function ls(){if(typeof window>"u")return re();try{const s=window.localStorage.getItem(St);if(!s)return re();const t=JSON.parse(s);if(!Array.isArray(t))return re();const a=t.flatMap((r,c)=>{if(!r||typeof r!="object")return[];const f=r,l=typeof f.speaker=="string"?f.speaker:"",g=typeof f.text=="string"?f.text.trim():"";return!ns.has(l)||!g?[]:[{id:(typeof f.id=="string"?f.id.trim():"")||`stored-${c}`,speaker:l,text:g}]});return a.length?a:re()}catch{return re()}}function cs(s){if(!(typeof window>"u"))try{window.localStorage.setItem(St,JSON.stringify(s))}catch{}}const gt=["xinyue","du"],De={xinyue:"我",du:"渡"},ds={xinyue:0,du:0},zt=[{id:"scissors",label:"剪刀",icon:"✌️"},{id:"rock",label:"石头",icon:"👊"},{id:"paper",label:"布",icon:"✋"}],ps={rock:"scissors",scissors:"paper",paper:"rock"},xs={scissors:"scissors",剪刀:"scissors","✌️":"scissors","✌":"scissors",rock:"rock",stone:"rock",石头:"rock",拳头:"rock","👊":"rock",paper:"paper",布:"paper",包袱:"paper","✋":"paper"};function ne(s){const t=String(s||"").trim();return t?xs[t]||t:""}function mt(s){var a;const t=ne(s);return((a=zt.find(r=>r.id===t))==null?void 0:a.label)||String(s||"").trim()||"未出拳"}function us(s,t){var g;const a=ne((g=s==null?void 0:s.picks)==null?void 0:g.xinyue),r=ne(t);if(!a||!r)return"";const c=mt(a),f=mt(r);if(a===r)return`你出了${c}，渡出了${f}。平局，重新出拳。`;const l=ps[a]===r?"你赢":"渡赢";return`你出了${c}，渡出了${f}。${l}。`}const Ct={place:"最终地点",pose:"最终姿势"},fs=["跳蛋","震动乳夹","震动环","乳夹","锁精环","飞机杯","软绳","手腕绑带","眼罩","口球","春药"],hs=["跳蛋","震动","按摩棒","飞机杯","吸乳器","吸吮器"];function ze(s){return new Promise(t=>window.setTimeout(t,s))}function C(s){return String(s||"").replace(/小玥/g,"我")}function T(s){return String(s||"").replace(/小玥/g,"你").replace(/(^|[^自])我/g,"$1你")}function ie(s){return String(s||"")}function Oe(s,t){return C(s.player_text||s.text||s.error||"").split(/\r?\n/).map(c=>c.trim()).find(c=>c&&!c.startsWith("【")&&!/^(进度|主题|轮到|手牌|我的状态|渡的状态|最终地点|最终姿势|待处理|可用命令)/.test(c))||t}function S(s){return`${s}-${Date.now()}-${Math.random().toString(36).slice(2,8)}`}function Re(s,t){const a=Math.floor(Number(s||0));return Math.max(1,Math.min(t,a||1))}function bt(s,t){const a=Math.floor(Number(s||0));return Math.max(0,Math.min(t,a||0))}function gs(s,t){const a=[];for(let r=1;r<=s;r+=t){const c=Array.from({length:Math.min(t,s-r+1)},(f,l)=>r+l);a.length%2===1&&c.reverse(),a.push(c)}return a.reverse().flat()}function ms(s,t,a){if(t===1)return"start";if(t===a)return"end";if(!s)return"empty";const r=`${s.kind||""} ${s.slot||""}`.toLowerCase();return/empty/.test(r)?"empty":/finish_self|finish-jump/.test(r)?"finish-jump":/reset/.test(r)?"reset":/swap/.test(r)?"swap":/move|back|forward/.test(r)?"move":/lock|pause|item/.test(r)?"item":/clear/.test(r)?"clear":/extend|time/.test(r)?"time":/limit/.test(r)?"limit":/place/.test(r)?"place":/pose/.test(r)?"pose":/theme/.test(r)?"theme":"task"}function bs(s){return s==="start"?"🚩":s==="end"?"🏆":s==="place"?"🏫":s==="item"?"🎁":s==="move"?"⏪":s==="reset"?"🔁":s==="finish-jump"?"🏁":s==="swap"?"🔄":s==="clear"?"✨":s==="time"?"⏳":s==="limit"?"🚫":s==="pose"?"◇":s==="theme"?"🚩":s==="task"?"📸":""}function ys(s,t,a){return t===1?"起点":t===a?"终点":C((s==null?void 0:s.name)||"空")}function ws(s){const t=C(s).match(/(我|渡)掷出\s*(\d+)，从\s*(\d+)\s*走到\s*(\d+)/);return t?{actor:t[1]==="渡"?"du":"xinyue",dice:Number(t[2]||1),from:Number(t[3]||0),to:Number(t[4]||0)}:null}function $e(s){return s.replace(/[。.!！?？\s]+$/g,"").trim()}function vs(s,t,a,r){const f=[s,...t].map(g=>g.trim()).filter(Boolean).filter(g=>!/^下一次行动[:：]/.test(g)&&!/^待处理[:：]/.test(g)).join(" ");if(/双方回到起点/.test(f))return"双方回到起点";let l=f.match(/(我|你|渡|对方|双方)?\s*从\s*\d+\s*(前进|后退)\s*(\d+)\s*格(?:到|至)\s*\d+/);return l?`${l[1]||a||"玩家"}${l[2]}了 ${l[3]} 格`:(l=f.match(/(我|你|渡|对方|双方)\s*(前进|后退)\s*(\d+)\s*格/),l?`${l[1]}${l[2]}了 ${l[3]} 格`:(l=f.match(/(我|你|渡|对方)\s*从\s*\d+\s*回到起点/),l?`${l[1]}回到起点`:(l=f.match(/(我|你|渡|对方)\s*从\s*\d+\s*直达终点/),l?`${l[1]}直达终点`:$e(s)===$e(r)?"":s?`触发：${s}`:"")))}function ks(s,t){var J,D;const a=C(s).split(`
`).map(b=>b.trim()).filter(Boolean),r=a.findIndex(b=>/^第\s*\d+\s*格：/.test(b)),c=r>=0?a[r]:"";if(!c)return null;const f=c.match(/^第\s*(\d+)\s*格：([^，。]+)/),l=(f==null?void 0:f[2])||"格子事件",g=((J=c.match(/抽到「([^」]+)」/))==null?void 0:J[1])||"",o=((D=c.match(/获得\s*([^（，。]+)/))==null?void 0:D[1])||"",B=!!(g||o||/抽卡|惩罚任务|选择惩罚/.test(l)),W=/奖励|Pass卡|获得/.test(c)?"reward":/选择/.test(l)?"choice":"penalty",I=Number((f==null?void 0:f[1])||0),R=t==null?void 0:t.actor,Q=c.replace(/^第\s*\d+\s*格：/,"").trim(),y=R?De[R]:"",z=vs(Q,a.slice(r+1,r+4),y,l);return{position:I,actor:R,actorLabel:y,from:t==null?void 0:t.from,to:(t==null?void 0:t.to)??I,title:l,text:c,detail:z,kind:B?"draw":"event",cardTitle:g||o||l,cardType:W==="reward"?"奖励卡":W==="choice"?"选择惩罚":"惩罚任务",tone:W}}function yt(s){const t=T(s.cardType||"").trim(),a=T(s.cardTitle||s.title).trim(),r=T(s.title).trim();return!t||t===a||t===r?"":t}function wt(s){const t=T(s.detail||"").trim(),a=T(s.title).trim();return!t||$e(t.replace(/^触发[:：]\s*/,""))===$e(a)?"":t}function js(s,t,a){const r=C(s).trim();if(!r)return null;const c=Array.isArray(a)?a.map(B=>C(B).trim()).filter(Boolean):[],o=[...[...Array.from(new Set(c)).filter(B=>B!==r)].sort(()=>Math.random()-.5).slice(0,7),r];for(;o.length<8;)o.unshift(r);return{theme:r,direction:C(t||"待定"),items:o,spinKey:`${Date.now()}-${Math.random().toString(36).slice(2,8)}`}}function Ns(s){const t=String(s.duration_type||"");if(t==="actions"){const a=Math.max(0,Number(s.remaining_actions||0));return s.blocks_action?`停步剩余 ${a} 次`:`剩余 ${a} 次行动`}return t==="minutes"?`${Math.max(1,Number(s.minutes||0))} 分钟`:t==="until_finish"?"到终点前有效":t==="until_clear"?"待解除":""}function $t(s){return!!Ct[String(s||"").trim()]}function Pt(s,t){const a=new Map;for(const f of s||[]){const l=String((f==null?void 0:f.slot)||"").trim();if(!$t(l))continue;const g=C((f==null?void 0:f.value)||"").trim();g&&a.set(l,g)}const r=C((t==null?void 0:t.final_place)||"").trim(),c=C((t==null?void 0:t.final_pose)||"").trim();return r&&!a.has("place")&&a.set("place",r),c&&!a.has("pose")&&a.set("pose",c),["place","pose"].map(f=>{const l=a.get(f);return l?{label:Ct[f]||"终局素材",values:[l]}:null}).filter(f=>!!f)}function _s(s){const t=C(s.label||s.slot||"状态");return s.slot==="prop"||t==="道具"?"道具惩罚":t}function Ss(s){const t=C(s.value||""),a=[],r=Math.max(1,Number(s.level||1));s.slot==="prop"&&r>1&&Mt(t)&&a.push(`${r}档`);const c=Ns(s);return c&&a.push(c),t?a.length?`${t}（${a.join("，")}）`:t:a.length?a.join("，"):"状态"}function Mt(s){return hs.some(t=>s.includes(t))}function zs(s){const t=new Map;return s.filter(a=>!$t(a.slot)).slice(-6).forEach(a=>{const r=_s(a),c=t.get(r)||[];c.push(Ss(a)),t.set(r,c)}),Array.from(t.entries()).map(([a,r])=>({label:a,values:r}))}function vt(s){return(s||[]).some(t=>t.blocks_action&&Number(t.remaining_actions||0)>0)}function Cs(s){const t=[/^(我|渡)掷出\s*\d+/,/^第\s*\d+\s*格：/,/^下一次行动：/,/行动权/,/到达终点/,/^新局已开始。?$/,/^本局已结束。?$/];return C(s).split(`
`).map(a=>a.trim()).filter(a=>a&&t.some(r=>r.test(a))).slice(0,4)}function $s(s){return String(s).split(/\r?\n/).map(a=>a.trim()).find(Boolean)==="【掷骰】"}function kt(s,t){return s.slice(t).map(a=>{const r=a.trim(),c=r.match(/^【描述[:：](.*)】$/);return c?c[1].trim():r}).filter(Boolean).join(`
`).trim()}function Ps(s){const t=String(s).split(/\r?\n/),a=t.findIndex(g=>g.trim());if(a<0)return{kind:"",body:""};const r=t[a].trim(),c=kt(t,a+1);if(r==="【掷骰】")return{kind:"roll",body:c};if(r==="【提交】")return{kind:"submit",body:c};if(r==="【通过】")return{kind:"approve",body:c};if(r==="【不通过】")return{kind:"reject",body:c};if(r==="【Pass】"||r==="【PASS】"||r==="【使用Pass卡】")return{kind:"pass",body:c};const f=r.match(/^【选择[:：](.+)】$/);if(f)return{kind:"choose",choice:f[1].trim(),body:c};const l=r.match(/^【(?:剪刀石头布|石头剪刀布)[:：](.+)】$/);return l?{kind:"choose",choice:l[1].trim(),body:c}:{kind:"",body:kt(t,a)}}function Ms(s,t="rock"){const a=((s==null?void 0:s.choices)||[]).find(r=>(r==null?void 0:r.id)||(r==null?void 0:r.label));return String((a==null?void 0:a.id)||(a==null?void 0:a.label)||t).trim()}function Ts(s,t){if(s==="final_note")return"本地预览：终局小纸条收到了。";const a=(t==null?void 0:t.pending_event)||null;if((a==null?void 0:a.type)==="duel"&&a.current_actor==="du")return`【剪刀石头布：石头】
【描述：本地预览：我出石头。】`;if((a==null?void 0:a.type)==="choice"&&a.actor==="du"){const r=Ms(a,"");if(r)return`【选择：${r}】
【描述：本地预览：我选这个。】`}return(a==null?void 0:a.type)==="review"&&a.reviewer==="du"&&a.phase==="questioning"?`【提交】
【描述：本地预览：渡想问你的真心话问题。】`:(a==null?void 0:a.type)==="review"&&a.actor==="du"&&a.phase==="assigned"?`【提交】
【描述：本地预览：渡已经完成任务，提交给你验收。】`:(a==null?void 0:a.type)==="review"&&a.reviewer==="du"&&a.phase==="submitted"?`【通过】
【描述：本地预览：这次算你通过。】`:ve(t)?`【掷骰】
【描述：本地预览：我来掷这一回合。】`:"本地预览：我看到了，等你继续行动。"}async function A(s){const t=await _t("/miniapp-api/game-tools/private_board",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:s,save_id:"default"})});if(!(t!=null&&t.ok))throw new Error((t==null?void 0:t.error)||"走格棋命令失败");return t}async function As(s){var a;const t=await _t("/miniapp-api/game-tools/private_board/sync-du",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({save_id:"default",mode:s.mode,message:s.message||"",roll_text:s.rollText||""})});if(!(t!=null&&t.ok))throw new Error((t==null?void 0:t.error)||((a=t==null?void 0:t.wakeup)==null?void 0:a.error)||"游戏内交流失败");return t}function ve(s){return!!(s&&s.turn_actor==="du"&&!s.game_over)}function jt(s){const t=(s==null?void 0:s.pending_event)||null;if(!s||s.game_over||!t)return!1;if(t.type==="duel")return t.current_actor==="du";if(t.type==="choice")return t.actor==="du";if(t.type==="review"){const a=String(t.phase||"");return a==="questioning"||a==="submitted"?t.reviewer==="du":t.actor==="du"}return!1}function we(s){const t=(s==null?void 0:s.pending_event)||null;if(!t)return"现在轮到渡行动。";if(t.type==="duel")return"现在轮到渡完成剪刀石头布对抗。";if(t.type==="choice")return"渡刚触发了需要自己选择的惩罚。";if(t.type==="review"){const a=String(t.phase||"");return a==="questioning"?"现在需要渡给出真心话题目。":a==="submitted"?"现在需要渡验收小玥提交的惩罚任务。":"现在需要渡提交惩罚任务。"}return"现在轮到渡处理棋局。"}function Ys({onBack:s}){var at,it,rt,nt,ot,lt,ct,dt,pt,xt,ut;const t=ss(),a=x.useRef(null),r=x.useRef(!1),c=x.useRef(null),f=x.useRef(null),l=x.useRef(null),g=x.useRef(null),[o,B]=x.useState(null),[W,I]=x.useState(ds),[R,Q]=x.useState(1),[y,z]=x.useState(!1),[J,D]=x.useState(!1),[b,oe]=x.useState(!1),[ke,ee]=x.useState(null),[j,G]=x.useState(null),[Z,te]=x.useState(!0),[se,le]=x.useState(null),[U,$]=x.useState(!1),[q,ce]=x.useState(0),[je,qe]=x.useState(""),[M,V]=x.useState(!1),[Tt,de]=x.useState(!1),[Ye,At]=x.useState(""),[Lt,Fe]=x.useState(!1),[Ge,Bt]=x.useState(1),[Pe,Ue]=x.useState(""),[Ne,He]=x.useState(ls),v=(o==null?void 0:o.state)||{},E=Math.max(12,Math.min(80,Number(v.board_size||36))),Me=E<=36?6:8,Te=v.turn_actor==="du"?"du":"xinyue",Y=!!(v.game_over||o!=null&&o.game_over),pe=Te==="du"&&!Y,_=v.pending_event||null,H=x.useMemo(()=>{try{return!!new URLSearchParams(window.location.search).has("preview")}catch{return!1}},[]);x.useLayoutEffect(()=>{a.current&&(a.current.scrollTop=0)},[]),x.useEffect(()=>{r.current=U,U&&ce(0)},[U]),x.useEffect(()=>{U&&window.setTimeout(()=>{var i;return(i=c.current)==null?void 0:i.scrollIntoView({block:"end"})},40)},[Ne.length,U,M]),x.useEffect(()=>{cs(Ne)},[Ne]),x.useEffect(()=>{if(!j||j.kind!=="draw"||j.tone!=="reward"){te(!0);return}te(!1);const i=window.setTimeout(()=>te(!0),900);return()=>window.clearTimeout(i)},[j]);const k=x.useCallback((i,d=!1)=>{He(u=>[...u,i]),d&&!r.current&&ce(u=>Math.min(9,u+1))},[]),Ke=x.useMemo(()=>{const i=new Map;for(const d of v.cell_events||[]){const u=Number((d==null?void 0:d.position)||0);u>0&&i.set(u,d)}return i},[v.cell_events]),Et=x.useMemo(()=>gs(E,Me).map(i=>{const d=Ke.get(i),u=ms(d,i,E);return{position:i,event:d,kind:u,icon:bs(u),name:ys(d,i,E)}}),[E,Me,Ke]),w=x.useCallback(i=>{var d,u,p,h;B(i),I({xinyue:Number(((u=(d=i.state)==null?void 0:d.positions)==null?void 0:u.xinyue)||0),du:Number(((h=(p=i.state)==null?void 0:p.positions)==null?void 0:h.du)||0)})},[]),We=x.useCallback(async()=>{z(!0);try{const i=await A("status");w(i)}catch(i){t(`加载涩涩走格棋失败：${(i==null?void 0:i.message)||i}`)}finally{z(!1)}},[w,t]);x.useEffect(()=>{We()},[We]);const Je=x.useCallback(async i=>{D(!0);for(let d=0;d<12;d+=1)Q(Math.floor(Math.random()*6)+1),await ze(58);Q(Math.max(1,Math.min(6,i||1))),D(!1)},[]),Ae=x.useCallback(async(i,d,u,p)=>{const h=Number(u||0),n=Number(p||0);if(h===n){i[d]=n,I({...i}),ee(Re(n,E)),await ze(120);return}const P=n>h?1:-1;for(let O=h+P;P>0?O<=n:O>=n;O+=P)i[d]=O,I({...i}),ee(Re(O,E)),await ze(145)},[E]),Le=x.useCallback(async()=>{var i,d,u,p,h;if(!(y||b)){z(!0),G(null);try{const n=await A("new_game");Q(1),w(n),He(re()),ce(0),le(js((d=(i=n.state)==null?void 0:i.theme_profile)==null?void 0:d.theme,(p=(u=n.state)==null?void 0:u.theme_profile)==null?void 0:p.direction_label,(h=n.state)==null?void 0:h.theme_options))}catch(n){t(`开新局失败：${(n==null?void 0:n.message)||n}`)}finally{z(!1)}}},[b,w,y,t]);x.useCallback(async()=>{if(!(y||b)){z(!0);try{const i=await A("end_game");w(i)}catch(i){t(`结束本局失败：${(i==null?void 0:i.message)||i}`)}finally{z(!1)}}},[b,w,y,t]);const ae=x.useCallback(async(i,d)=>{var P,O,xe,ue,fe,he,ge,me,be;const u=i.trim()||"我看到了。",p=Ps(u),h=p.body.trim();h&&k({id:S("du"),speaker:"du",text:h},!0);const n=(d==null?void 0:d.pending_event)||null;try{if((n==null?void 0:n.type)==="duel"&&n.current_actor==="du"){if(p.kind!=="choose"||!p.choice.trim())return;const m=p.choice.trim(),N=us(n,m),K=await A(`choose ${m}`);w(K);const ye=ve(K.state)&&!((P=K.state)!=null&&P.pending_event);N&&(g.current=ye?{state:K.state,message:"剪刀石头布对抗已结算，现在轮到渡行动。"}:null,G({position:Number(n.cell||((xe=(O=K.state)==null?void 0:O.positions)==null?void 0:xe.du)||0),kicker:"剪刀石头布对抗",title:"对抗结果",text:N,detail:N,kind:"event"})),k({id:S("system"),speaker:"system",text:N||Oe(K,"渡已出拳，系统已判定对抗结果。")},!0),!N&&ye&&await((ue=l.current)==null?void 0:ue.call(l,K.state,"剪刀石头布对抗已结算，现在轮到渡行动。"));return}if((n==null?void 0:n.reviewer)==="du"&&n.type==="review"&&n.phase==="questioning"){if(p.kind!=="submit")return;const m=p.body.trim();if(!m){k({id:S("system"),speaker:"system",text:"渡发了【提交】，但后面没有题目。"},!0);return}const N=await A(`submit ${m}`);w(N),k({id:S("system"),speaker:"system",text:"渡已出题，轮到你回答。"},!0);return}if((n==null?void 0:n.actor)==="du"&&n.type==="review"&&n.phase==="assigned"){if(p.kind!=="submit")return;const m=p.body.trim();if(!m){k({id:S("system"),speaker:"system",text:"渡发了【提交】，但后面没有提交内容。"},!0);return}const N=await A(`submit ${m}`);w(N),k({id:S("system"),speaker:"system",text:"渡已提交惩罚任务，等你验收。"},!0),await((fe=l.current)==null?void 0:fe.call(l,N.state,we(N.state)));return}if((n==null?void 0:n.actor)==="du"&&n.type==="choice"){if(p.kind==="pass"){const N=await A("pass");if(w(N),N.ok===!1){k({id:S("system"),speaker:"system",text:Oe(N,"渡没有Pass卡，不能跳过。")},!0);return}k({id:S("system"),speaker:"system",text:"渡使用Pass卡跳过了惩罚。"},!0),await((he=l.current)==null?void 0:he.call(l,N.state,we(N.state)));return}if(p.kind!=="choose"||!p.choice.trim())return;const m=await A(`choose ${p.choice.trim()}`);w(m),k({id:S("system"),speaker:"system",text:"渡已选择惩罚选项。"},!0),await((ge=l.current)==null?void 0:ge.call(l,m.state,we(m.state)));return}if((n==null?void 0:n.reviewer)==="du"&&n.type==="review"&&n.phase==="submitted"){if(p.kind==="approve"){const m=await A("approve");w(m),k({id:S("system"),speaker:"system",text:"渡验收通过，棋局继续。"},!0),await((me=l.current)==null?void 0:me.call(l,m.state,we(m.state)));return}if(p.kind==="reject"){const m=await A(p.body.trim()?`reject ${p.body.trim()}`:"reject");w(m),k({id:S("system"),speaker:"system",text:"渡打回了任务，需要重新提交。"},!0);return}return}ve(d)&&$s(u)&&(await ze(260),k({id:S("system"),speaker:"system",text:"渡发送【掷骰】，已执行他的行动。"},!0),await((be=f.current)==null?void 0:be.call(f,{notifyAfterUserRoll:!1})))}catch(m){k({id:S("system"),speaker:"system",text:`渡的指令执行失败：${String((m==null?void 0:m.message)||m)}`},!0)}},[k,w]),X=x.useCallback(async(i,d)=>{if(!H)return As(i);let u=d,p="";if(i.mode==="final_note"){const n=await A("final_note_sent");u=n.state||u,p=n.player_text||n.text||""}const h=Ts(i.mode,u);return{ok:!0,state:u,player_text:p,reply_text:h,reply_preview:h.slice(0,120),wakeup:{reply_text:h,reply_preview:h.slice(0,120)}}},[H]),Ve=x.useCallback(async(i,d="现在轮到渡行动。")=>{var p,h;const u=jt(i);if(!(!ve(i)||i!=null&&i.pending_event&&!u)){k({id:S("system"),speaker:"system",text:u?H?"预览模式：轮到渡处理任务，已继续同步。":"轮到渡处理任务，已把棋局发给渡。":H?"预览模式：轮到渡行动，已继续同步。":"轮到渡行动，已把棋局发给渡。"},!0),V(!0);try{const n=await X({mode:"state_update",message:d,rollText:""},i);n.state&&w({ok:!0,state:n.state,player_text:n.player_text||""});const P=ie(n.reply_text||((p=n.wakeup)==null?void 0:p.reply_text)||n.reply_preview||((h=n.wakeup)==null?void 0:h.reply_preview)||"").trim();await ae(P,n.state||i)}catch(n){const P=String((n==null?void 0:n.message)||n||"同步失败");k({id:S("system"),speaker:"system",text:`渡行动同步失败：${P}`},!0),t(`渡行动同步失败：${P}`)}finally{V(!1)}}},[k,w,H,ae,X,t]);x.useEffect(()=>{l.current=Ve},[Ve]);const It=x.useCallback(()=>{var d;const i=g.current;g.current=null,G(null),i&&((d=l.current)==null||d.call(l,i.state,i.message))},[]),_e=x.useCallback(async(i,d="小玥刚掷完骰子。")=>{var p,h;const u=ie(i.text||i.du_text||i.player_text||"").trim();k({id:S("system"),speaker:"system",text:H?"预览模式：已同步这次棋局。":d.includes("掷")?"已把这次掷骰结果和当前棋局发给渡。":"已把棋局变化发给渡。"},!0),V(!0);try{const n=await X({mode:"roll_result",message:d,rollText:u},i.state);n.state&&w({ok:!0,state:n.state,player_text:n.player_text||i.player_text||""});const P=ie(n.reply_text||((p=n.wakeup)==null?void 0:p.reply_text)||n.reply_preview||((h=n.wakeup)==null?void 0:h.reply_preview)||"").trim();await ae(P,n.state||i.state)}catch(n){const P=String((n==null?void 0:n.message)||n||"同步失败");k({id:S("system"),speaker:"system",text:`自动同步失败：${P}`},!0),t(`自动同步给渡失败：${P}`)}finally{V(!1)}},[k,w,H,ae,X,t]),Be=x.useCallback(async(i={})=>{var P,O,xe,ue,fe,he,ge,me,be;if(y||b||Y)return;let d=null,u=null;z(!0),oe(!0),G(null);const p={xinyue:Number(((P=v.positions)==null?void 0:P.xinyue)||0),du:Number(((O=v.positions)==null?void 0:O.du)||0)},h=v.turn_actor==="du"?"du":"xinyue",n={...p};try{const m=await A("roll"),N=ws(m.player_text||"");await Je((N==null?void 0:N.dice)||Math.floor(Math.random()*6)+1),N&&await Ae(n,N.actor,N.from,N.to);const K={xinyue:Number(((ue=(xe=m.state)==null?void 0:xe.positions)==null?void 0:ue.xinyue)||0),du:Number(((he=(fe=m.state)==null?void 0:fe.positions)==null?void 0:he.du)||0)};for(const Ie of gt){const ft=Number(n[Ie]||0),ht=Number(K[Ie]||0);ft!==ht&&await Ae(n,Ie,ft,ht)}w(m);const ye=ks(m.player_text||"",N);ye&&G(ye);const ts=((ge=m.state)==null?void 0:ge.pending_event)||null;i.notifyAfterUserRoll!==!1&&h==="xinyue"&&!((me=m.state)!=null&&me.game_over)&&(!ts||jt(m.state))?d=m:i.notifyAfterUserRoll===!1&&h==="du"&&ve(m.state)&&(u=m)}catch(m){t(`掷骰失败：${(m==null?void 0:m.message)||m}`)}finally{z(!1),oe(!1),window.setTimeout(()=>ee(null),260)}d?await _e(d):u&&await((be=l.current)==null?void 0:be.call(l,u.state,we(u.state)))},[Ae,Je,b,w,y,Y,_e,v.positions,v.turn_actor,t]);x.useEffect(()=>{f.current=Be},[Be]);const F=x.useCallback(async(i,d={})=>{if(y||!(o!=null&&o.state))return;let u=null;z(!0),G(null);try{const p=await A(i);if(u=p,w(p),p.ok===!1){t(Oe(p,"这次操作没有生效。"));return}Ue(""),d.success&&k({id:S("system"),speaker:"system",text:d.success},!0)}catch(p){t(`处理惩罚任务失败：${(p==null?void 0:p.message)||p}`)}finally{z(!1)}u&&d.notify&&await _e(u,d.notifyMessage||"小玥处理了涩涩走格棋的惩罚任务。")},[k,w,y,_e,o==null?void 0:o.state,t]),Ot=x.useCallback(()=>{const i=Pe.trim();if(!i){t("先写提交内容。");return}F(`submit ${i}`,{success:"已提交任务，等渡验收。",notify:!0,notifyMessage:"小玥提交了惩罚任务，请你验收。"})},[F,Pe,t]),Rt=x.useCallback(()=>{F("approve",{success:"你通过了任务，棋局继续。",notify:!0,notifyMessage:"小玥通过了你的惩罚任务。"})},[F]),Dt=x.useCallback(()=>{F("reject",{success:"你打回了任务，等渡重新提交。",notify:!0,notifyMessage:"小玥打回了你的惩罚任务，请重新提交。"})},[F]),qt=x.useCallback(i=>{const d=(_==null?void 0:_.type)==="duel",u=(_==null?void 0:_.current_actor)||(_==null?void 0:_.actor);if(d&&!(d&&u==="xinyue")){t("等待渡出拳。");return}F(`choose ${i}`,{success:d?"已出拳，等待渡出拳。":"已选择惩罚，棋局继续。",notify:!0,notifyMessage:d?"小玥已在剪刀石头布对抗中出拳。请第一行单独发送【剪刀石头布：石头】、【剪刀石头布：剪刀】或【剪刀石头布：布】；描述另起一行写成【描述：...】。":"小玥处理完选择惩罚，棋局继续。"})},[F,_==null?void 0:_.actor,_==null?void 0:_.current_actor,_==null?void 0:_.type,t]),Yt=x.useCallback(()=>{F("pass",{success:"已使用Pass卡跳过惩罚。",notify:!0,notifyMessage:"小玥使用Pass卡跳过了惩罚任务。"})},[F]),Ft=x.useCallback(async()=>{var d,u,p;const i=((d=o==null?void 0:o.state)==null?void 0:d.final_note)||null;if(!(M||y||b||!(o!=null&&o.state)||!i||i.sent)){V(!0);try{const h=await X({mode:"final_note",message:i.text||""},o.state);h.state&&w({ok:!0,state:h.state,player_text:h.player_text||o.player_text||""}),k({id:S("system"),speaker:"system",text:H?"预览模式：终局小纸条已同步。":"终局小纸条已发送给渡。"},!0);const n=ie(h.reply_text||((u=h.wakeup)==null?void 0:u.reply_text)||h.reply_preview||((p=h.wakeup)==null?void 0:p.reply_preview)||"").trim();n&&k({id:S("du"),speaker:"du",text:n},!0),de(!1)}catch(h){const n=String((h==null?void 0:h.message)||h||"同步失败");k({id:S("system"),speaker:"system",text:`小纸条发送失败：${n}`},!0),t(`发送终局小纸条失败：${n}`)}finally{V(!1)}}},[b,k,w,y,M,H,o,X,t]),Gt=x.useCallback(async(i,d,u=1)=>{if(M||y||b||!(o!=null&&o.state))return;const p=d.replace(/\s+/g," ").trim();if(!p){t("先选要追加的内容。");return}const h=i==="prop"&&Mt(p)?` level=${Math.max(1,Math.min(5,Math.round(Number(u)||1)))}`:"";z(!0);try{const n=await A(`append_final_status ${i} ${p}${h}`);w(n),de(!0),t(`已启用：${p}`)}catch(n){t(`追加失败：${(n==null?void 0:n.message)||n}`)}finally{z(!1)}},[b,w,y,M,o==null?void 0:o.state,t]),Ut=x.useCallback(async(i,d)=>{if(M||y||b||!(o!=null&&o.state))return;const u=d.replace(/\s+/g," ").trim();if(u){z(!0);try{const p=await A(`remove_final_status ${i} ${u}`);w(p),de(!0),t(`已取消：${u}`)}catch(p){t(`取消失败：${(p==null?void 0:p.message)||p}`)}finally{z(!1)}}},[b,w,y,M,o==null?void 0:o.state,t]),Ht=x.useCallback(async()=>{var u,p;if(M||y||b||!(o!=null&&o.state))return;const i=je.trim();if(!i)return;const d={id:S("me"),speaker:"xinyue",text:i};qe(""),k(d),V(!0);try{const h=await X({mode:"chat",message:i},o.state);h.state&&w({ok:!0,state:h.state,player_text:h.player_text||o.player_text||""});const n=ie(h.reply_text||((u=h.wakeup)==null?void 0:u.reply_text)||h.reply_preview||((p=h.wakeup)==null?void 0:p.reply_preview)||"").trim();await ae(n,h.state||o.state)}catch(h){const n=String((h==null?void 0:h.message)||h||"同步失败");k({id:S("system"),speaker:"system",text:`交流失败：${n}`}),t(`游戏内交流失败：${n}`)}finally{V(!1)}},[b,k,w,y,je,M,o,ae,X,t]),Kt=C(((at=v.theme_profile)==null?void 0:at.theme)||"未触发"),Wt=C(((it=v.theme_profile)==null?void 0:it.direction_label)||"待定"),Jt=bt((rt=v.positions)==null?void 0:rt.xinyue,E),Vt=bt((nt=v.positions)==null?void 0:nt.du,E),Ee=v.winner?De[v.winner]:"",Xe=Cs((o==null?void 0:o.player_text)||""),L=v.final_note||null,Qe=Pt(v.final_note_items||[],L),Se=String((L==null?void 0:L.id)||`${v.winner||""}-${v.updated_at||""}`),Ze=!!(Y&&v.winner==="xinyue"&&(!L||L.target==="du")&&!(L!=null&&L.sent)),Xt=(((ot=v.statuses)==null?void 0:ot.du)||[]).filter(i=>i.slot==="prop").map(i=>C(i.value||""));x.useEffect(()=>{!Y||!L||!Se||Ye!==Se&&(At(Se),de(!0))},[L,Se,Ye,Y]);const Qt=Math.max(0,Number(((ct=(lt=v.hands)==null?void 0:lt.xinyue)==null?void 0:ct.pass)||0)),Zt=Math.max(0,Number(v.pass_skips_used||0)),et={xinyue:vt((dt=v.statuses)==null?void 0:dt.xinyue),du:vt((pt=v.statuses)==null?void 0:pt.du)},tt=pe&&et.du&&!_,es=y||b||M||!(o!=null&&o.state)||!!_||pe&&!tt,st=M||y||b||!(o!=null&&o.state);return e.jsxs("div",{className:"sese-game",ref:a,children:[e.jsxs("div",{className:"sese-header",children:[e.jsx("button",{className:"sese-back",type:"button",onClick:s,"aria-label":"返回游戏",children:e.jsx(as,{})}),e.jsxs("button",{className:"sese-chat-entry",type:"button",onClick:()=>$(!0),"aria-label":"游戏内交流",children:[e.jsx(is,{}),q?e.jsx("span",{children:q}):null]}),e.jsx("div",{className:"sese-header-title",children:"涩涩走格棋"}),e.jsxs("div",{className:"sese-game-status-bar",children:[e.jsx(Ce,{label:"主题",value:Kt}),e.jsx(Ce,{label:"主导方",value:Wt}),e.jsx(Ce,{label:"我 进度",value:`${String(Jt).padStart(2,"0")} / ${E}`}),e.jsx(Ce,{label:"渡 进度",value:`${String(Vt).padStart(2,"0")} / ${E}`}),e.jsx("div",{className:"sese-turn-indicator",children:Y&&Ee?`${Ee} 到达终点`:pe?"等待 渡 行动...":"轮到 我 行动"})]})]}),e.jsx("section",{className:"sese-board-container","aria-label":"走格棋盘",children:e.jsx("div",{className:"sese-board",style:{gridTemplateColumns:`repeat(${Me}, minmax(0, 1fr))`},children:Et.map(i=>{const d=gt.filter(u=>Re(W[u],E)===i.position);return e.jsxs("div",{className:`sese-tile sese-tile-${i.kind} ${ke===i.position?"is-active":""}`,children:[e.jsx("div",{className:"sese-tile-number",children:i.position}),e.jsx("div",{className:"sese-tile-icon",children:i.icon}),e.jsx("div",{className:"sese-tile-name",children:i.name}),e.jsx("div",{className:"sese-piece-stack",children:d.map(u=>e.jsx("span",{className:`sese-piece ${u==="xinyue"?"sese-piece-me":"sese-piece-du"} ${et[u]?"paused":""}`,children:De[u]},u))})]},i.position)})})}),e.jsxs("section",{className:"sese-controls",children:[e.jsxs("div",{className:"sese-player-states",children:[e.jsx(Nt,{actor:"xinyue",statuses:((xt=v.statuses)==null?void 0:xt.xinyue)||[],active:Te==="xinyue"}),e.jsx(Nt,{actor:"du",statuses:((ut=v.statuses)==null?void 0:ut.du)||[],active:Te==="du"})]}),Qe.length?e.jsx("div",{className:"sese-final-pose-panel",children:Qe.map(i=>e.jsxs("div",{className:"sese-final-material-row",children:[e.jsx("span",{children:i.label}),e.jsx("strong",{children:i.values.join("、")})]},i.label))}):null,e.jsxs("div",{className:"sese-action-area",children:[e.jsx("div",{className:`sese-dice ${J?"rolling":""}`,"aria-label":`骰子 ${R}`,children:R}),e.jsx("button",{className:"sese-roll-button",type:"button",disabled:es,onClick:Y?Le:()=>void Be({notifyAfterUserRoll:!0}),children:Y?"开新局":_?"先处理任务":tt?"处理停步":pe?"等渡掷骰":y||b?"移动中":M?"等渡回应":"掷骰子"}),e.jsx("button",{className:"sese-restart-button",type:"button",disabled:y||b||M,onClick:Le,children:"重开"})]}),e.jsx("div",{className:"sese-history",children:Xe.length?`最近：${Xe[0]}`:"最近：等待第一次掷骰"})]}),U?e.jsx("div",{className:"sese-chat-mask",role:"dialog","aria-modal":"true","aria-label":"游戏内交流",onClick:()=>$(!1),children:e.jsxs("div",{className:"sese-chat-panel",onClick:i=>i.stopPropagation(),children:[e.jsxs("div",{className:"sese-chat-head",children:[e.jsxs("div",{children:[e.jsx("strong",{children:"游戏内交流"}),e.jsx("span",{children:pe?"等待渡发送【掷骰】":"当前轮到你行动"})]}),e.jsx("button",{type:"button",onClick:()=>$(!1),"aria-label":"关闭交流",children:"×"})]}),e.jsxs("div",{className:"sese-chat-list",children:[Ne.map(i=>e.jsxs("div",{className:`sese-chat-message ${i.speaker}`,children:[e.jsx("span",{children:i.speaker==="xinyue"?"我":i.speaker==="du"?"渡":"系统"}),e.jsx("p",{children:ie(i.text)})]},i.id)),M?e.jsxs("div",{className:"sese-chat-message du pending",children:[e.jsx("span",{children:"渡"}),e.jsx("p",{children:"正在回复..."})]}):null,e.jsx("div",{ref:c})]}),e.jsxs("form",{className:"sese-chat-form",onSubmit:i=>{i.preventDefault(),Ht()},children:[e.jsx("input",{value:je,disabled:st,placeholder:"和渡说一句游戏内的话",onChange:i=>qe(i.target.value)}),e.jsx("button",{type:"submit",disabled:st||!je.trim(),"aria-label":M?"发送中":"发送",children:e.jsx(rs,{})})]})]})}):null,se?e.jsx("div",{className:"sese-theme-mask",role:"dialog","aria-modal":"true","aria-label":"开局主题抽取",children:e.jsxs("div",{className:"sese-theme-modal",children:[e.jsxs("div",{className:"sese-slot-lights","aria-hidden":"true",children:[e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{})]}),e.jsxs("div",{className:"sese-slot-marquee",children:[e.jsx("span",{children:"THEME"}),e.jsx("strong",{children:"JACKPOT"})]}),e.jsxs("div",{className:"sese-slot-face",children:[e.jsx("div",{className:"sese-theme-window",children:e.jsx("div",{className:"sese-theme-strip",children:se.items.map((i,d)=>e.jsx("div",{className:"sese-theme-item",children:C(i)},`${i}-${d}`))},se.spinKey)}),e.jsxs("p",{className:"sese-slot-plaque",children:["主导方：",se.direction]}),e.jsxs("div",{className:"sese-theme-actions",children:[e.jsx("button",{className:"secondary",type:"button",disabled:y,onClick:Le,children:y?"重抽中":"重抽主题"}),e.jsx("button",{type:"button",onClick:()=>le(null),children:"开始本局"})]}),e.jsx("div",{className:"sese-slot-tray","aria-hidden":"true"})]})]})}):null,_&&!j?e.jsx("div",{className:"sese-pending-mask",role:"dialog","aria-modal":"true","aria-label":"待处理惩罚",children:e.jsx("div",{className:"sese-pending-modal",children:e.jsx(Rs,{pending:_,passCount:Qt,passSkipsUsed:Zt,submission:Pe,disabled:y,onSubmissionChange:Ue,onSubmit:Ot,onApprove:Rt,onReject:Dt,onChoose:qt,onPass:Yt})})}):null,Y&&L&&Tt?e.jsx("div",{className:"sese-final-note-mask",role:"dialog","aria-modal":"true","aria-label":"终局小纸条",children:e.jsxs("div",{className:"sese-final-note-modal",children:[e.jsxs("div",{className:"sese-final-note-head",children:[e.jsx("span",{children:"终局小纸条"}),e.jsx("button",{type:"button",onClick:()=>de(!1),"aria-label":"关闭终局小纸条",children:"关闭"})]}),e.jsxs("h2",{children:[Ee||"玩家"," 到达终点"]}),e.jsx(Bs,{note:L,canAddStatus:Ze,onAddStatus:()=>Fe(!0)}),L.sent?e.jsx("em",{children:"已发送给渡"}):e.jsx("button",{className:"sese-final-note-send",type:"button",disabled:M||y||b,onClick:()=>void Ft(),children:M?"发送中":"发送给渡"})]})}):null,Ze&&Lt?e.jsx(Ls,{level:Ge,activeProps:Xt,disabled:M||y||b,onClose:()=>Fe(!1),onLevelChange:Bt,onToggleProp:(i,d)=>{d?Ut("prop",i):Gt("prop",i,Ge)}}):null,j?e.jsx("div",{className:"sese-popup-mask",role:"dialog","aria-modal":"true",children:e.jsxs("div",{className:`sese-popup ${j.kind==="draw"?`sese-popup-draw tone-${j.tone||"penalty"}`:""}`,children:[e.jsx("div",{className:"sese-popup-kicker",children:T(j.kicker||(j.actorLabel?`${j.actorLabel}走到第 ${j.position} 格`:`第 ${j.position} 格`))}),j.kind==="draw"?e.jsx("div",{className:`sese-draw-card ${j.tone==="reward"&&!Z?"is-covered":"is-revealed"}`,children:j.tone==="reward"&&!Z?e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"sese-card-pile","aria-hidden":"true",children:[e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("b",{})]}),e.jsx("span",{children:"奖励抽卡"}),e.jsx("em",{children:"抽卡中"})]}):e.jsxs(e.Fragment,{children:[yt(j)?e.jsx("span",{children:yt(j)}):null,e.jsx("strong",{children:T(j.cardTitle||j.title)})]})}):null,j.kind==="draw"?null:e.jsx("h2",{children:T(j.title)}),j.tone==="reward"&&!Z?e.jsx("p",{children:"正在洗牌..."}):wt(j)?e.jsx("p",{children:wt(j)}):null,j.tone==="reward"&&!Z?null:e.jsx("button",{type:"button",onClick:It,children:"确 认"})]})}):null,e.jsx("style",{children:`
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
        `})]})}function Ce({label:s,value:t}){return e.jsxs("div",{className:"sese-pill",children:[e.jsx("span",{children:s}),e.jsx("strong",{children:t})]})}function Nt({actor:s,statuses:t,active:a}){const r=zs(t);return e.jsxs("div",{className:`sese-player-card sese-player-card-${s} ${a?"active":""}`,children:[e.jsx("div",{className:"sese-player-card-head",children:e.jsx("h2",{children:s==="xinyue"?"我的状态":"渡的状态"})}),e.jsx("div",{className:"sese-status-list",children:r.length?r.map(c=>e.jsxs("div",{className:"sese-status-group",children:[e.jsx("span",{className:"sese-status-group-label",children:c.label}),e.jsx("div",{className:"sese-status-chip-row",children:c.values.map(f=>e.jsx("span",{className:"sese-status-chip",children:f},`${c.label}-${f}`))})]},c.label)):e.jsx("div",{className:"sese-status-empty",children:"无状态"})})]})}function Ls({level:s,activeProps:t,disabled:a,onClose:r,onLevelChange:c,onToggleProp:f}){const l=new Set(t);return e.jsx("div",{className:"sese-toy-console-mask",role:"dialog","aria-modal":"true","aria-label":"玩具控制台",onClick:r,children:e.jsxs("div",{className:"sese-toy-console-sheet",onClick:g=>g.stopPropagation(),children:[e.jsxs("div",{className:"sese-toy-console-head",children:[e.jsxs("div",{children:[e.jsx("span",{children:"玩具控制台"}),e.jsx("strong",{children:"控制渡当前状态"})]}),e.jsx("button",{type:"button",onClick:r,"aria-label":"关闭玩具控制台",children:"关闭"})]}),e.jsxs("div",{className:"sese-toy-console-section",children:[e.jsx("label",{children:"道具档位"}),e.jsx("div",{className:"sese-toy-level-row",children:[1,2,3,4,5].map(g=>e.jsx("button",{type:"button",disabled:a,className:g===s?"selected":"",onClick:()=>c(g),children:g},g))})]}),e.jsxs("div",{className:"sese-toy-console-section",children:[e.jsx("label",{children:"启用道具"}),e.jsx("div",{className:"sese-toy-chip-grid",children:fs.map(g=>(()=>{const o=l.has(g);return e.jsx("button",{type:"button",disabled:a,className:o?"selected":"","aria-pressed":o,"aria-label":o?`取消启用${g}`:`启用${g}`,onClick:()=>f(g,o),children:g},g)})())})]})]})})}function Bs({note:s,canAddStatus:t=!1,onAddStatus:a}){const r=Is(s),c=C(s.theme||"本局主题"),f=s.target==="du"?"渡当前状态":"你的当前状态",l=Os(s.target_status||""),g=Pt([],s);return e.jsxs("div",{className:"sese-final-note-body",children:[e.jsx("div",{className:"sese-final-note-intro",children:r}),e.jsxs("div",{className:"sese-final-note-section",children:[e.jsx("span",{children:"本局主题"}),e.jsx("strong",{children:c})]}),e.jsxs("div",{className:"sese-final-note-section",children:[e.jsxs("div",{className:"sese-final-note-section-title",children:[e.jsx("span",{children:f}),t?e.jsx("button",{type:"button",onClick:a,"aria-label":"打开玩具控制台",children:e.jsx(Es,{})}):null]}),l.length?l.map(o=>e.jsxs("div",{className:"sese-final-note-status-group",children:[e.jsx("b",{children:o.label}),e.jsx("div",{className:"sese-final-note-status-values",children:o.values.map(B=>e.jsx("span",{children:B},B))})]},o.label)):e.jsx("div",{className:"sese-final-note-empty",children:"没有遗留状态，可以自由决定最后玩法。"})]}),g.map(o=>e.jsxs("div",{className:"sese-final-note-section",children:[e.jsx("span",{children:o.label}),e.jsx("strong",{children:o.values.join("、")})]},o.label)),e.jsx("div",{className:"sese-final-note-closing",children:"请尽情享受你们的ooxx吧！"})]})}function Es(){return e.jsx("svg",{viewBox:"0 0 24 24","aria-hidden":"true",children:e.jsx("path",{d:"M12 5v14M5 12h14"})})}function Is(s){return T(s.text||"").split(`
`).map(r=>r.trim()).filter(Boolean).find(r=>!r.startsWith("【")&&!r.startsWith("请根据")&&!r.startsWith("本局主题")&&!r.startsWith("请尽情"))||"终点已到达，赢家状态已清空。"}function Os(s){const t=T(s).trim();return!t||t==="无"?[]:t.split("；").map(a=>a.trim()).filter(Boolean).map(a=>{const r=a.indexOf("：");if(r<0)return{label:"状态",values:[a]};const c=a.slice(0,r).trim()||"状态",f=a.slice(r+1).split("、").map(l=>l.trim()).filter(Boolean);return{label:c,values:f.length?f:["无"]}})}function Rs({pending:s,passCount:t,passSkipsUsed:a,submission:r,disabled:c,onSubmissionChange:f,onSubmit:l,onApprove:g,onReject:o,onChoose:B,onPass:W}){var le,U;const I=T(s.name||"惩罚任务"),R=s.actor||"xinyue",Q=s.reviewer||(R==="xinyue"?"du":"xinyue"),y=s.current_actor||R,z=R==="xinyue",J=y==="xinyue",D=Q==="xinyue",b=!!C(s.question_text||"").trim(),oe=z&&s.pass_allowed!==!1&&t>0&&a<1&&!["submitted","questioning"].includes(String(s.phase||"")),ke=T(s.submission||"").trim(),ee=/^你的回答[。.]?$/.test(ke)?"":ke,[j,G]=x.useState("");x.useEffect(()=>{G("")},[s.id,s.current_actor,s.phase]);const Z=ne(j||((le=s.picks)==null?void 0:le.xinyue)),te=!!ne((U=s.picks)==null?void 0:U.xinyue);if(s.type==="choice")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:z?"你的选择惩罚":"等待渡选择"}),e.jsx("strong",{children:I})]}),e.jsx("p",{children:T(s.prompt||"选择一项惩罚。")}),z?e.jsx("div",{className:"sese-choice-list",children:(s.choices||[]).map($=>{const q=String($.id||$.label||"");return e.jsx("button",{type:"button",disabled:c||!q,onClick:()=>B(q),children:T($.label||q)},q)})}):e.jsx("div",{className:"sese-pending-wait",children:"等待渡选择惩罚。"}),oe?e.jsx("button",{className:"sese-pass-button",type:"button",disabled:c,onClick:W,children:"使用Pass卡跳过"}):null]});if(s.type==="duel")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:J?"轮到你出拳":"等待渡出拳"}),e.jsx("strong",{children:I||"剪刀石头布对抗"})]}),e.jsx("p",{children:"同格触发对抗。双方各出石头、剪刀或布，系统判定胜负；赢的前进 3 格，输的后退 3 格。"}),e.jsx("div",{className:"sese-choice-list sese-rps-list",children:zt.map($=>e.jsx("button",{className:`sese-rps-button ${Z===$.id?"is-selected":""}`,type:"button",title:$.label,"aria-label":$.label,"aria-pressed":Z===$.id,disabled:c||!J||te,onClick:()=>{G(ne($.id)),B($.id)},children:$.icon},$.id))}),J?null:e.jsx("div",{className:"sese-pending-wait",children:te?"你的出拳已记录，等待渡出拳。":"等待渡出拳。"})]});if(s.phase==="submitted")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:D?"需要你验收":"等待渡验收"}),e.jsx("strong",{children:I})]}),e.jsx("p",{className:"sese-submission-text",children:C(s.submission_text||"")}),D?e.jsxs("div",{className:"sese-review-actions",children:[e.jsx("button",{type:"button",disabled:c,onClick:g,children:"通过"}),e.jsx("button",{type:"button",disabled:c,onClick:o,children:"打回"})]}):e.jsx("div",{className:"sese-pending-wait",children:"等待渡验收你的提交。"})]});if(s.phase==="questioning"){const $=T(s.question_prompt||"请问对方一个你很想知道答案却一直没有问的问题。"),q=T(s.waiting_task||"对方正在出题中。");return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:D?"你来出题":"等待渡出题"}),e.jsx("strong",{children:I})]}),D?e.jsxs(e.Fragment,{children:[e.jsx("p",{children:$}),e.jsx("textarea",{value:r,disabled:c,placeholder:"写下你的问题",onChange:ce=>f(ce.target.value)}),e.jsx("div",{className:"sese-review-actions",children:e.jsx("button",{type:"button",disabled:c||!r.trim(),onClick:l,children:"提交题目"})})]}):e.jsx("div",{className:"sese-pending-wait",children:q==="对方正在出题中。"?"等待渡给出真心话题目。":q})]})}const se=b?"等待渡回答这个问题。":"等待渡完成并提交任务。";return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:z?"你的惩罚任务":"等待渡提交"}),e.jsx("strong",{children:I})]}),b?e.jsxs("p",{className:"sese-submission-text",children:["题目：",C(s.question_text)]}):null,z?e.jsxs(e.Fragment,{children:[b?null:e.jsx("p",{children:T(s.task||"")}),!b&&ee?e.jsxs("div",{className:"sese-pending-tip",children:["提交要求：",ee]}):null,e.jsx("textarea",{value:r,disabled:c,placeholder:b?"在这里写回答":"在这里写提交内容",onChange:$=>f($.target.value)}),e.jsxs("div",{className:"sese-review-actions",children:[e.jsx("button",{type:"button",disabled:c||!r.trim(),onClick:l,children:b?"提交回答":"提交验收"}),oe?e.jsx("button",{type:"button",disabled:c,onClick:W,children:"使用Pass卡"}):null]})]}):e.jsx("div",{className:"sese-pending-wait",children:e.jsx("span",{children:se})})]})}export{Ys as SeseBoardGameTab};
