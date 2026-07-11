import{u as ps,r as u,j as e,C as xs,M as us,S as fs,b as Tt}from"./index-CP4_HXn_.js";const Bt="du-gateway:sese-board-game:chat:v1",hs=new Set(["xinyue","du","system"]),gs=[{id:"system-ready",speaker:"system",text:"游戏内交流在这里。渡明确发送【掷骰】时，棋盘才会执行他的行动。"}];function ge(){return gs.map(t=>({...t}))}function ms(){if(typeof window>"u")return ge();try{const t=window.localStorage.getItem(Bt);if(!t)return ge();const s=JSON.parse(t);if(!Array.isArray(s))return ge();const i=s.flatMap((r,c)=>{if(!r||typeof r!="object")return[];const d=r,n=typeof d.speaker=="string"?d.speaker:"",g=typeof d.text=="string"?d.text.trim():"";return!hs.has(n)||!g?[]:[{id:(typeof d.id=="string"?d.id.trim():"")||`stored-${c}`,speaker:n,text:g}]});return i.length?i:ge()}catch{return ge()}}function bs(t){if(!(typeof window>"u"))try{window.localStorage.setItem(Bt,JSON.stringify(t))}catch{}}const _t=["xinyue","du"],We={xinyue:"我",du:"渡"},ws={xinyue:0,du:0},It=[{id:"scissors",label:"剪刀",icon:"✌️"},{id:"rock",label:"石头",icon:"👊"},{id:"paper",label:"布",icon:"✋"}],ys={rock:"scissors",scissors:"paper",paper:"rock"},vs={scissors:"scissors",剪刀:"scissors","✌️":"scissors","✌":"scissors",rock:"rock",stone:"rock",石头:"rock",拳头:"rock","👊":"rock",paper:"paper",布:"paper",包袱:"paper","✋":"paper"};function me(t){const s=String(t||"").trim();return s?vs[s]||s:""}function St(t){var i;const s=me(t);return((i=It.find(r=>r.id===s))==null?void 0:i.label)||String(t||"").trim()||"未出拳"}function ks(t,s){var g;const i=me((g=t==null?void 0:t.picks)==null?void 0:g.xinyue),r=me(s);if(!i||!r)return"";const c=St(i),d=St(r);if(i===r)return`你出了${c}，渡出了${d}。平局，重新出拳。`;const n=ys[i]===r?"你赢":"渡赢";return`你出了${c}，渡出了${d}。${n}。`}const Lt={place:"最终地点",pose:"最终姿势"},js=["跳蛋","震动乳夹","震动环","乳夹","锁精环","飞机杯","软绳","手腕绑带","眼罩","口球","春药"],Ns=["跳蛋","震动","按摩棒","飞机杯","吸乳器","吸吮器"];function _e(t){return new Promise(s=>window.setTimeout(s,t))}function P(t){return String(t||"").replace(/小玥/g,"我")}function L(t){return String(t||"").replace(/小玥/g,"你").replace(/(^|[^自])我/g,"$1你")}function he(t){return String(t||"")}function Ge(t,s){return P(t.player_text||t.text||t.error||"").split(/\r?\n/).map(c=>c.trim()).find(c=>c&&!c.startsWith("【")&&!/^(进度|主题|轮到|手牌|我的状态|渡的状态|最终地点|最终姿势|待处理|可用命令)/.test(c))||s}function B(t){return`${t}-${Date.now()}-${Math.random().toString(36).slice(2,8)}`}function Ue(t,s){const i=Math.floor(Number(t||0));return Math.max(1,Math.min(s,i||1))}function zt(t,s){const i=Math.floor(Number(t||0));return Math.max(0,Math.min(s,i||0))}function _s(t,s){const i=[];for(let r=1;r<=t;r+=s){const c=Array.from({length:Math.min(s,t-r+1)},(d,n)=>r+n);i.length%2===1&&c.reverse(),i.push(c)}return i.reverse().flat()}function Ss(t,s,i){if(s===1)return"start";if(s===i)return"end";if(!t)return"empty";const r=`${t.kind||""} ${t.slot||""}`.toLowerCase();return/empty/.test(r)?"empty":/finish_self|finish-jump/.test(r)?"finish-jump":/reset/.test(r)?"reset":/swap/.test(r)?"swap":/move|back|forward/.test(r)?"move":/lock|pause|item/.test(r)?"item":/clear/.test(r)?"clear":/extend|time/.test(r)?"time":/limit/.test(r)?"limit":/place/.test(r)?"place":/pose/.test(r)?"pose":/theme/.test(r)?"theme":"task"}function zs(t){return t==="start"?"🚩":t==="end"?"🏆":t==="place"?"🏫":t==="item"?"🎁":t==="move"?"⏪":t==="reset"?"🔁":t==="finish-jump"?"🏁":t==="swap"?"🔄":t==="clear"?"✨":t==="time"?"⏳":t==="limit"?"🚫":t==="pose"?"◇":t==="theme"?"🚩":t==="task"?"📸":""}function Cs(t,s,i){return s===1?"起点":s===i?"终点":P((t==null?void 0:t.name)||"空")}function $s(t){const s=P(t).match(/(我|渡)掷出\s*(\d+)，从\s*(\d+)\s*走到\s*(\d+)/);return s?{actor:s[1]==="渡"?"du":"xinyue",dice:Number(s[2]||1),from:Number(s[3]||0),to:Number(s[4]||0)}:null}function Ie(t){return t.replace(/[。.!！?？\s]+$/g,"").trim()}function Ps(t,s,i,r){const d=[t,...s].map(g=>g.trim()).filter(Boolean).filter(g=>!/^下一次行动[:：]/.test(g)&&!/^待处理[:：]/.test(g)).join(" ");if(/双方回到起点/.test(d))return"双方回到起点";let n=d.match(/(我|你|渡|对方|双方)?\s*从\s*\d+\s*(前进|后退)\s*(\d+)\s*格(?:到|至)\s*\d+/);return n?`${n[1]||i||"玩家"}${n[2]}了 ${n[3]} 格`:(n=d.match(/(我|你|渡|对方|双方)\s*(前进|后退)\s*(\d+)\s*格/),n?`${n[1]}${n[2]}了 ${n[3]} 格`:(n=d.match(/(我|你|渡|对方)\s*从\s*\d+\s*回到起点/),n?`${n[1]}回到起点`:(n=d.match(/(我|你|渡|对方)\s*从\s*\d+\s*直达终点/),n?`${n[1]}直达终点`:Ie(t)===Ie(r)?"":t?`触发：${t}`:"")))}function Ms(t,s){var z,te;const i=P(t).split(`
`).map(G=>G.trim()).filter(Boolean),r=i.findIndex(G=>/^第\s*\d+\s*格：/.test(G)),c=r>=0?i[r]:"";if(!c)return null;const d=c.match(/^第\s*(\d+)\s*格：([^，。]+)/),n=(d==null?void 0:d[2])||"格子事件",g=((z=c.match(/抽到「([^」]+)」/))==null?void 0:z[1])||"",b=((te=c.match(/获得\s*([^（，。]+)/))==null?void 0:te[1])||"",x=!!(g||b||/抽卡|惩罚任务|选择惩罚/.test(n)),F=/奖励|Pass卡|获得/.test(c)?"reward":/选择/.test(n)?"choice":"penalty",K=Number((d==null?void 0:d[1])||0),E=s==null?void 0:s.actor,Z=c.replace(/^第\s*\d+\s*格：/,"").trim(),ee=E?We[E]:"",y=Ps(Z,i.slice(r+1,r+4),ee,n);return{position:K,actor:E,actorLabel:ee,from:s==null?void 0:s.from,to:(s==null?void 0:s.to)??K,title:n,text:c,detail:y,kind:x?"draw":"event",cardTitle:g||b||n,cardType:F==="reward"?"奖励卡":F==="choice"?"选择惩罚":"惩罚任务",tone:F}}function Ct(t){const s=L(t.cardType||"").trim(),i=L(t.cardTitle||t.title).trim(),r=L(t.title).trim();return!s||s===i||s===r?"":s}function $t(t){const s=L(t.detail||"").trim(),i=L(t.title).trim();return!s||Ie(s.replace(/^触发[:：]\s*/,""))===Ie(i)?"":s}function As(t,s,i){const r=P(t).trim();if(!r)return null;const c=Array.isArray(i)?i.map(x=>P(x).trim()).filter(Boolean):[],b=[...[...Array.from(new Set(c)).filter(x=>x!==r)].sort(()=>Math.random()-.5).slice(0,7),r];for(;b.length<8;)b.unshift(r);return{theme:r,direction:P(s||"待定"),items:b,spinKey:`${Date.now()}-${Math.random().toString(36).slice(2,8)}`}}function Ts(t){const s=String(t.duration_type||"");if(s==="actions"){const i=Math.max(0,Number(t.remaining_actions||0));return t.blocks_action?`停步剩余 ${i} 次`:`剩余 ${i} 次行动`}return s==="minutes"?`${Math.max(1,Number(t.minutes||0))} 分钟`:s==="until_finish"?"到终点前有效":s==="until_clear"?"待解除":""}function Et(t){return!!Lt[String(t||"").trim()]}function Ot(t,s){const i=new Map;for(const d of t||[]){const n=String((d==null?void 0:d.slot)||"").trim();if(!Et(n))continue;const g=P((d==null?void 0:d.value)||"").trim();g&&i.set(n,g)}const r=P((s==null?void 0:s.final_place)||"").trim(),c=P((s==null?void 0:s.final_pose)||"").trim();return r&&!i.has("place")&&i.set("place",r),c&&!i.has("pose")&&i.set("pose",c),["place","pose"].map(d=>{const n=i.get(d);return n?{label:Lt[d]||"终局素材",values:[n]}:null}).filter(d=>!!d)}function Bs(t){const s=P(t.label||t.slot||"状态");return t.slot==="prop"||s==="道具"?"道具惩罚":s}function Is(t){const s=P(t.value||""),i=[],r=Math.max(1,Number(t.level||1));t.slot==="prop"&&r>1&&Rt(s)&&i.push(`${r}档`);const c=Ts(t);return c&&i.push(c),s?i.length?`${s}（${i.join("，")}）`:s:i.length?i.join("，"):"状态"}function Rt(t){return Ns.some(s=>t.includes(s))}function Ls(t){const s=new Map;return t.filter(i=>!Et(i.slot)).slice(-6).forEach(i=>{const r=Bs(i),c=s.get(r)||[];c.push(Is(i)),s.set(r,c)}),Array.from(s.entries()).map(([i,r])=>({label:i,values:r}))}function Pt(t){return(t||[]).some(s=>s.blocks_action&&Number(s.remaining_actions||0)>0)}function Es(t){const s=[/^(我|渡)掷出\s*\d+/,/^第\s*\d+\s*格：/,/^下一次行动：/,/行动权/,/到达终点/,/^新局已开始。?$/,/^本局已结束。?$/];return P(t).split(`
`).map(i=>i.trim()).filter(i=>i&&s.some(r=>r.test(i))).slice(0,4)}function Os(t){return String(t).split(/\r?\n/).map(i=>i.trim()).find(Boolean)==="【掷骰】"}function Rs(t){return String(t).split(/\r?\n/).some(s=>s.trim()==="【掷骰】")}function Mt(t,s){return t.slice(s).map(i=>{const r=i.trim();if(r==="【掷骰】")return"";const c=r.match(/^【描述[:：](.*)】$/);return c?c[1].trim():r}).filter(Boolean).join(`
`).trim()}function He(t,s,i){var b;const c=(((b=t[s])==null?void 0:b.trim())||"").match(i);if(!c)return null;const d=c[1]||"",n=d.indexOf("】");if(n>=0)return d.slice(0,n).trim();const g=[d,...t.slice(s+1)].join(`
`).trim();return g.endsWith("】")?g.slice(0,-1).trim():g}function Ds(t){const s=String(t).split(/\r?\n/),i=s.findIndex(E=>E.trim());if(i<0)return{kind:"",body:""};const r=s[i].trim(),c=Mt(s,i+1),d=He(s,i,/^【描述[:：](.*)$/);if(d!==null)return{kind:"submit",body:d||c};const n=He(s,i,/^【真心话出题[:：](.*)$/);if(n!==null)return{kind:"submit",body:n||c};const g=He(s,i,/^【真心话回答[:：](.*)$/);if(g!==null)return{kind:"submit",body:g||c};if(r==="【掷骰】")return{kind:"roll",body:c};if(r==="【提交】")return{kind:"submit",body:c};const b=r.match(/^【通过[:：](.*?)(?:】)?$/);if(b)return{kind:"approve",body:b[1].trim()||c};const x=r.match(/^【(?:不通过|打回|驳回)[:：](.*?)(?:】)?$/);if(x)return{kind:"reject",body:x[1].trim()||c};if(r==="【通过】")return{kind:"approve",body:c};if(r==="【不通过】"||r==="【打回】"||r==="【驳回】")return{kind:"reject",body:c};if(r==="【Pass】"||r==="【PASS】"||r==="【使用Pass卡】")return{kind:"pass",body:c};const F=r.match(/^【选择[:：](.+)】$/);if(F)return{kind:"choose",choice:F[1].trim(),body:c};const K=r.match(/^【(?:剪刀石头布|石头剪刀布)[:：](.+)】$/);return K?{kind:"choose",choice:K[1].trim(),body:c}:{kind:"",body:Mt(s,i)}}function qs(t,s="rock"){const i=((t==null?void 0:t.choices)||[]).find(r=>(r==null?void 0:r.id)||(r==null?void 0:r.label));return String((i==null?void 0:i.id)||(i==null?void 0:i.label)||s).trim()}const Ys=new Set(["反向诱惑","全部暴露！","羞耻台词大放送","自慰陈述"]);function Fs(t,s){if(t==="final_note")return"本地预览：终局小纸条收到了。";const i=(s==null?void 0:s.pending_event)||null;if((i==null?void 0:i.type)==="duel"&&i.current_actor==="du")return"【剪刀石头布：石头】";if((i==null?void 0:i.type)==="choice"&&i.actor==="du"){const r=qs(i,"");if(r)return`【选择：${r}】`}return(i==null?void 0:i.type)==="review"&&i.reviewer==="du"&&i.phase==="questioning"?"【真心话出题：本地预览：渡想问你的真心话问题。】":(i==null?void 0:i.type)==="review"&&i.actor==="du"&&i.phase==="assigned"?i.name==="真心话点名"?"【真心话回答：本地预览：渡已经回答真心话。】":Ys.has(String(i.name||""))?"【描述：本地预览：渡已经完成任务，提交给你验收。】":`【提交】
本地预览：渡已经完成任务，提交给你验收。`:(i==null?void 0:i.type)==="review"&&i.reviewer==="du"&&i.phase==="submitted"?`【通过：本地预览：验收通过。】
【掷骰】`:le(s)?"【掷骰】":"本地预览：我看到了，等你继续行动。"}async function R(t){const s=await Tt("/miniapp-api/game-tools/private_board",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:t,save_id:"default"})});if(!(s!=null&&s.ok))throw new Error((s==null?void 0:s.error)||"走格棋命令失败");return s}async function Gs(t){var i;const s=await Tt("/miniapp-api/game-tools/private_board/sync-du",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({save_id:"default",mode:t.mode,message:t.message||"",roll_text:t.rollText||""})});if(!(s!=null&&s.ok))throw new Error((s==null?void 0:s.error)||((i=s==null?void 0:s.wakeup)==null?void 0:i.error)||"游戏内交流失败");return s}function le(t){return!!(t&&t.turn_actor==="du"&&!t.game_over)}function Je(t){const s=(t==null?void 0:t.pending_event)||null;if(!t||t.game_over||!s)return!1;if(s.type==="duel")return s.current_actor==="du";if(s.type==="choice")return s.actor==="du";if(s.type==="review"){const i=String(s.phase||"");return i==="questioning"||i==="submitted"?s.reviewer==="du":s.actor==="du"}return!1}function Be(t){return Array.isArray(t==null?void 0:t.applied_reply_commands)&&t.applied_reply_commands.length>0}function Ke(t){if(!Be(t)||Array.isArray(t==null?void 0:t.followup_wakeups)&&t.followup_wakeups.length>0)return!1;const s=t==null?void 0:t.state;return le(s)&&(!(s!=null&&s.pending_event)||Je(s))}function Q(t){const s=(t==null?void 0:t.pending_event)||null;if(!s)return"现在轮到渡行动。";if(s.type==="duel")return"现在轮到渡完成剪刀石头布对抗。";if(s.type==="choice")return"渡刚触发了需要自己选择的惩罚。";if(s.type==="review"){const i=String(s.phase||"");return i==="questioning"?"现在需要渡给出真心话题目。":i==="submitted"?"现在需要渡验收小玥提交的惩罚任务。":"现在需要渡提交惩罚任务。"}return"现在轮到渡处理棋局。"}function ei({onBack:t}){var xt,ut,ft,ht,gt,mt,bt,wt,yt,vt,kt;const s=ps(),i=u.useRef(null),r=u.useRef(!1),c=u.useRef(null),d=u.useRef(null),n=u.useRef(null),g=u.useRef(null),b=u.useRef(""),[x,F]=u.useState(null),[K,E]=u.useState(ws),[Z,ee]=u.useState(1),[y,z]=u.useState(!1),[te,G]=u.useState(!1),[j,be]=u.useState(!1),[Se,ce]=u.useState(null),[v,se]=u.useState(null),[re,de]=u.useState(!0),[ne,ze]=u.useState(null),[X,pe]=u.useState(!1),[M,U]=u.useState(0),[xe,Ve]=u.useState(""),[I,Ce]=u.useState(!1),[O,$e]=u.useState(!1),[Dt,we]=u.useState(!1),[Xe,qt]=u.useState(""),[Yt,Qe]=u.useState(!1),[Ze,Ft]=u.useState(1),[oe,et]=u.useState(""),[Le,Ee]=u.useState(null),[Pe,tt]=u.useState(ms),k=(x==null?void 0:x.state)||{},Y=Math.max(12,Math.min(80,Number(k.board_size||36))),Oe=Y<=36?6:8,Re=k.turn_actor==="du"?"du":"xinyue",W=!!(k.game_over||x!=null&&x.game_over),ye=Re==="du"&&!W,C=k.pending_event||null,Me=u.useMemo(()=>{try{return!!new URLSearchParams(window.location.search).has("preview")}catch{return!1}},[]);u.useLayoutEffect(()=>{i.current&&(i.current.scrollTop=0)},[]),u.useEffect(()=>{r.current=X,X&&U(0)},[X]),u.useEffect(()=>{X&&window.setTimeout(()=>{var a;return(a=c.current)==null?void 0:a.scrollIntoView({block:"end"})},40)},[Pe.length,X,I]),u.useEffect(()=>{bs(Pe)},[Pe]),u.useEffect(()=>{if(!v||v.kind!=="draw"||v.tone!=="reward"){de(!0);return}de(!1);const a=window.setTimeout(()=>de(!0),900);return()=>window.clearTimeout(a)},[v]);const N=u.useCallback((a,p=!1)=>{tt(f=>[...f,a]),p&&!r.current&&U(f=>Math.min(9,f+1))},[]),st=u.useMemo(()=>{const a=new Map;for(const p of k.cell_events||[]){const f=Number((p==null?void 0:p.position)||0);f>0&&a.set(f,p)}return a},[k.cell_events]),Gt=u.useMemo(()=>_s(Y,Oe).map(a=>{const p=st.get(a),f=Ss(p,a,Y);return{position:a,event:p,kind:f,icon:zs(f),name:Cs(p,a,Y)}}),[Y,Oe,st]),w=u.useCallback(a=>{var p,f,h,o;F(a),E({xinyue:Number(((f=(p=a.state)==null?void 0:p.positions)==null?void 0:f.xinyue)||0),du:Number(((o=(h=a.state)==null?void 0:h.positions)==null?void 0:o.du)||0)})},[]),it=u.useCallback(async()=>{z(!0);try{const a=await R("status");w(a)}catch(a){s(`加载涩涩走格棋失败：${(a==null?void 0:a.message)||a}`)}finally{z(!1)}},[w,s]);u.useEffect(()=>{it()},[it]);const at=u.useCallback(async a=>{G(!0);for(let p=0;p<12;p+=1)ee(Math.floor(Math.random()*6)+1),await _e(58);ee(Math.max(1,Math.min(6,a||1))),G(!1)},[]),De=u.useCallback(async(a,p,f,h)=>{const o=Number(f||0),l=Number(h||0);if(o===l){a[p]=l,E({...a}),ce(Ue(l,Y)),await _e(120);return}const m=l>o?1:-1;for(let A=o+m;m>0?A<=l:A>=l;A+=m)a[p]=A,E({...a}),ce(Ue(A,Y)),await _e(145)},[Y]),qe=u.useCallback(async()=>{var a,p,f,h,o;if(!(y||j)){z(!0),se(null);try{const l=await R("new_game");ee(1),w(l),tt(ge()),U(0),ze(As((p=(a=l.state)==null?void 0:a.theme_profile)==null?void 0:p.theme,(h=(f=l.state)==null?void 0:f.theme_profile)==null?void 0:h.direction_label,(o=l.state)==null?void 0:o.theme_options))}catch(l){s(`开新局失败：${(l==null?void 0:l.message)||l}`)}finally{z(!1)}}},[j,w,y,s]);u.useCallback(async()=>{if(!(y||j)){z(!0);try{const a=await R("end_game");w(a)}catch(a){s(`结束本局失败：${(a==null?void 0:a.message)||a}`)}finally{z(!1)}}},[j,w,y,s]);const ue=u.useCallback(async(a,p)=>{var A,ae,$,V,ve,ke,je,Ne,T,H;const f=a.trim()||"我看到了。",h=Ds(f),o=(p==null?void 0:p.pending_event)||null,l=h.body.trim(),m=(o==null?void 0:o.reviewer)==="du"&&o.type==="review"&&o.phase==="submitted"&&(h.kind==="approve"||h.kind==="reject");l&&!m&&N({id:B("du"),speaker:"du",text:l},!0);try{if((o==null?void 0:o.type)==="duel"&&o.current_actor==="du"){if(h.kind!=="choose"||!h.choice.trim())return;const _=h.choice.trim(),S=ks(o,_),q=await R(`choose ${_}`);w(q);const fe=le(q.state)&&!((A=q.state)!=null&&A.pending_event);S&&(g.current=fe?{state:q.state,message:"剪刀石头布对抗已结算，现在轮到渡行动。"}:null,se({position:Number(o.cell||(($=(ae=q.state)==null?void 0:ae.positions)==null?void 0:$.du)||0),kicker:"剪刀石头布对抗",title:"对抗结果",text:S,detail:S,kind:"event"})),N({id:B("system"),speaker:"system",text:S||Ge(q,"渡已出拳，系统已判定对抗结果。")},!0),!S&&fe&&await((V=n.current)==null?void 0:V.call(n,q.state,"剪刀石头布对抗已结算，现在轮到渡行动。"));return}if((o==null?void 0:o.reviewer)==="du"&&o.type==="review"&&o.phase==="questioning"){if(h.kind!=="submit")return;const _=h.body.trim();if(!_){N({id:B("system"),speaker:"system",text:"渡发了【提交】，但后面没有题目。"},!0);return}const S=await R(`submit ${_}`);w(S),N({id:B("system"),speaker:"system",text:"渡已出题，轮到你回答。"},!0);return}if((o==null?void 0:o.actor)==="du"&&o.type==="review"&&o.phase==="assigned"){if(h.kind!=="submit")return;const _=h.body.trim();if(!_){N({id:B("system"),speaker:"system",text:"渡发了【提交】，但后面没有提交内容。"},!0);return}const S=await R(`submit ${_}`);w(S),N({id:B("system"),speaker:"system",text:"渡已提交惩罚任务，等你验收。"},!0),await((ve=n.current)==null?void 0:ve.call(n,S.state,Q(S.state)));return}if((o==null?void 0:o.actor)==="du"&&o.type==="choice"){if(h.kind==="pass"){const S=await R("pass");if(w(S),S.ok===!1){N({id:B("system"),speaker:"system",text:Ge(S,"渡没有Pass卡，不能跳过。")},!0);return}N({id:B("system"),speaker:"system",text:"渡使用Pass卡跳过了惩罚。"},!0),await((ke=n.current)==null?void 0:ke.call(n,S.state,Q(S.state)));return}if(h.kind!=="choose"||!h.choice.trim())return;const _=await R(`choose ${h.choice.trim()}`);w(_),N({id:B("system"),speaker:"system",text:"渡已选择惩罚选项。"},!0),await((je=n.current)==null?void 0:je.call(n,_.state,Q(_.state)));return}if((o==null?void 0:o.reviewer)==="du"&&o.type==="review"&&o.phase==="submitted"){if(h.kind==="approve"){const _=Rs(f),S=h.body.trim()||"验收通过。",q=await R(`approve ${S}`);if(w(q),Ee({outcome:"approved",title:"渡验收通过",text:S,note:_?"已继续执行渡的掷骰。":"棋局继续。"}),_&&le(q.state)){await _e(260),await((Ne=d.current)==null?void 0:Ne.call(d,{notifyAfterUserRoll:!1}));return}await((T=n.current)==null?void 0:T.call(n,q.state,Q(q.state)));return}if(h.kind==="reject"){const _=h.body.trim()||"需要重新提交。",S=await R(`reject ${_}`);w(S),Ee({outcome:"rejected",title:"渡打回了任务",text:_,note:"请按反馈修改后重新提交。"});return}return}le(p)&&Os(f)&&(await _e(260),N({id:B("system"),speaker:"system",text:"渡发送【掷骰】，已执行他的行动。"},!0),await((H=d.current)==null?void 0:H.call(d,{notifyAfterUserRoll:!1})))}catch(_){N({id:B("system"),speaker:"system",text:`渡的指令执行失败：${String((_==null?void 0:_.message)||_)}`},!0)}},[N,w]),ie=u.useCallback(async(a,p)=>{if(!Me)return Gs(a);let f=p,h="";if(a.mode==="final_note"){const l=await R("final_note_sent");f=l.state||f,h=l.player_text||l.text||""}const o=Fs(a.mode,f);return{ok:!0,state:f,player_text:h,reply_text:o,reply_preview:o.slice(0,120),wakeup:{reply_text:o,reply_preview:o.slice(0,120)}}},[Me]),rt=u.useCallback(async(a,p="现在轮到渡行动。")=>{var h,o,l;const f=Je(a);if(!(!le(a)||a!=null&&a.pending_event&&!f)){$e(!0);try{const m=await ie({mode:"state_update",message:p,rollText:""},a);m.state&&w({ok:!0,state:m.state,player_text:m.player_text||""});const A=he(m.reply_text||((h=m.wakeup)==null?void 0:h.reply_text)||m.reply_preview||((o=m.wakeup)==null?void 0:o.reply_preview)||"").trim();if(Be(m)){Ke(m)&&await((l=n.current)==null?void 0:l.call(n,m.state,Q(m.state)));return}await ue(A,m.state||a)}catch(m){const A=String((m==null?void 0:m.message)||m||"同步失败");N({id:B("system"),speaker:"system",text:`渡行动同步失败：${A}`},!0),s(`渡行动同步失败：${A}`)}finally{$e(!1)}}},[N,w,ue,ie,s]);u.useEffect(()=>{n.current=rt},[rt]);const Ut=u.useCallback(()=>{var p;const a=g.current;g.current=null,se(null),a&&((p=n.current)==null||p.call(n,a.state,a.message))},[]),nt=u.useCallback(async(a,p="小玥刚掷完骰子。")=>{var m,A,ae;const f=he(a.text||a.du_text||a.player_text||"").trim(),h=b.current.trim(),o=p.trim()==="小玥刚掷完骰子。"?"":p.trim(),l=[h,o].filter(Boolean).join(`
`);$e(!0);try{const $=await ie({mode:"roll_result",message:l,rollText:f},a.state);h&&b.current.trim()===h&&(b.current=""),$.state&&w({ok:!0,state:$.state,player_text:$.player_text||a.player_text||""});const V=he($.reply_text||((m=$.wakeup)==null?void 0:m.reply_text)||$.reply_preview||((A=$.wakeup)==null?void 0:A.reply_preview)||"").trim();if(Be($)){Ke($)&&await((ae=n.current)==null?void 0:ae.call(n,$.state,Q($.state)));return}await ue(V,$.state||a.state)}catch($){const V=String(($==null?void 0:$.message)||$||"同步失败");N({id:B("system"),speaker:"system",text:`自动同步失败：${V}`},!0),s(`自动同步给渡失败：${V}`)}finally{$e(!1)}},[N,w,ue,ie,s]),Ye=u.useCallback(async(a={})=>{var m,A,ae,$,V,ve,ke,je,Ne;if(y||j||W)return;let p=null,f=null;z(!0),be(!0),se(null);const h={xinyue:Number(((m=k.positions)==null?void 0:m.xinyue)||0),du:Number(((A=k.positions)==null?void 0:A.du)||0)},o=k.turn_actor==="du"?"du":"xinyue",l={...h};try{const T=await R("roll"),H=$s(T.player_text||"");await at((H==null?void 0:H.dice)||Math.floor(Math.random()*6)+1),H&&await De(l,H.actor,H.from,H.to);const _={xinyue:Number((($=(ae=T.state)==null?void 0:ae.positions)==null?void 0:$.xinyue)||0),du:Number(((ve=(V=T.state)==null?void 0:V.positions)==null?void 0:ve.du)||0)};for(const fe of _t){const jt=Number(l[fe]||0),Nt=Number(_[fe]||0);jt!==Nt&&await De(l,fe,jt,Nt)}w(T);const S=Ms(T.player_text||"",H);S&&se(S);const q=((ke=T.state)==null?void 0:ke.pending_event)||null;a.notifyAfterUserRoll!==!1&&o==="xinyue"&&!((je=T.state)!=null&&je.game_over)&&(!q||Je(T.state))?p=T:a.notifyAfterUserRoll===!1&&o==="du"&&le(T.state)&&(f=T)}catch(T){s(`掷骰失败：${(T==null?void 0:T.message)||T}`)}finally{z(!1),be(!1),window.setTimeout(()=>ce(null),260)}p?await nt(p):f&&await((Ne=n.current)==null?void 0:Ne.call(n,f.state,Q(f.state)))},[De,at,j,w,y,W,nt,k.positions,k.turn_actor,s]);u.useEffect(()=>{d.current=Ye},[Ye]);const J=u.useCallback(async(a,p={})=>{var h,o;if(y||!(x!=null&&x.state))return;let f=null;z(!0),se(null);try{const l=await R(a);if(f=l,w(l),l.ok===!1){s(Ge(l,"这次操作没有生效。"));return}et(""),p.success&&N({id:B("system"),speaker:"system",text:p.success},!0),(h=p.deferSyncMessage)!=null&&h.trim()&&(b.current=p.deferSyncMessage.trim())}catch(l){s(`处理惩罚任务失败：${(l==null?void 0:l.message)||l}`)}finally{z(!1)}f&&p.syncAfter&&await((o=n.current)==null?void 0:o.call(n,f.state,p.syncMessage||Q(f.state)))},[N,w,y,x==null?void 0:x.state,s]),Ht=u.useCallback(()=>{const a=oe.trim();if(!a){s("先写提交内容。");return}J(`submit ${a}`,{success:"已提交任务，等渡验收。",syncAfter:!0,syncMessage:"小玥提交了惩罚任务，请你验收。"})},[J,oe,s]),Kt=u.useCallback(()=>{const a=oe.trim();J(a?`approve ${a}`:"approve",{success:"你通过了任务，棋局继续。",deferSyncMessage:a?`小玥刚刚通过了你的惩罚任务：${a}`:"小玥刚刚通过了你的惩罚任务。"})},[J,oe]),Wt=u.useCallback(()=>{const a=oe.trim();J(a?`reject ${a}`:"reject",{success:"你打回了任务，等渡重新提交。",syncAfter:!0,syncMessage:a?`小玥打回了你的惩罚任务：${a}`:"小玥打回了你的惩罚任务，请重新提交。"})},[J,oe]),Jt=u.useCallback(a=>{const p=(C==null?void 0:C.type)==="duel",f=(C==null?void 0:C.current_actor)||(C==null?void 0:C.actor);if(p&&!(p&&f==="xinyue")){s("等待渡出拳。");return}J(`choose ${a}`,{success:p?"已出拳，等待渡出拳。":"已选择惩罚，棋局继续。",syncAfter:!0,syncMessage:p?"小玥已在剪刀石头布对抗中出拳。请第一行单独发送【剪刀石头布：石头】、【剪刀石头布：剪刀】或【剪刀石头布：布】。":"小玥处理完选择惩罚，棋局继续。"})},[J,C==null?void 0:C.actor,C==null?void 0:C.current_actor,C==null?void 0:C.type,s]),Vt=u.useCallback(()=>{J("pass",{success:"已使用Pass卡跳过惩罚。",syncAfter:!0,syncMessage:"小玥使用Pass卡跳过了惩罚任务。"})},[J]),Xt=u.useCallback(async()=>{var p,f,h;const a=((p=x==null?void 0:x.state)==null?void 0:p.final_note)||null;if(!(I||O||y||j||!(x!=null&&x.state)||!a||a.sent)){Ce(!0);try{const o=await ie({mode:"final_note",message:a.text||""},x.state);o.state&&w({ok:!0,state:o.state,player_text:o.player_text||x.player_text||""}),N({id:B("system"),speaker:"system",text:Me?"预览模式：终局小纸条已同步。":"终局小纸条已发送给渡。"},!0);const l=he(o.reply_text||((f=o.wakeup)==null?void 0:f.reply_text)||o.reply_preview||((h=o.wakeup)==null?void 0:h.reply_preview)||"").trim();l&&N({id:B("du"),speaker:"du",text:l},!0),we(!1)}catch(o){const l=String((o==null?void 0:o.message)||o||"同步失败");N({id:B("system"),speaker:"system",text:`小纸条发送失败：${l}`},!0),s(`发送终局小纸条失败：${l}`)}finally{Ce(!1)}}},[j,N,w,y,I,O,Me,x,ie,s]),Qt=u.useCallback(async(a,p,f=1)=>{if(I||O||y||j||!(x!=null&&x.state))return;const h=p.replace(/\s+/g," ").trim();if(!h){s("先选要追加的内容。");return}const o=a==="prop"&&Rt(h)?` level=${Math.max(1,Math.min(5,Math.round(Number(f)||1)))}`:"";z(!0);try{const l=await R(`append_final_status ${a} ${h}${o}`);w(l),we(!0),s(`已启用：${h}`)}catch(l){s(`追加失败：${(l==null?void 0:l.message)||l}`)}finally{z(!1)}},[j,w,y,I,O,x==null?void 0:x.state,s]),Zt=u.useCallback(async(a,p)=>{if(I||O||y||j||!(x!=null&&x.state))return;const f=p.replace(/\s+/g," ").trim();if(f){z(!0);try{const h=await R(`remove_final_status ${a} ${f}`);w(h),we(!0),s(`已取消：${f}`)}catch(h){s(`取消失败：${(h==null?void 0:h.message)||h}`)}finally{z(!1)}}},[j,w,y,I,O,x==null?void 0:x.state,s]),es=u.useCallback(async()=>{var f,h,o;if(I||O||y||j||!(x!=null&&x.state))return;const a=xe.trim();if(!a)return;const p={id:B("me"),speaker:"xinyue",text:a};Ve(""),N(p),Ce(!0);try{const l=await ie({mode:"chat",message:a},x.state);l.state&&w({ok:!0,state:l.state,player_text:l.player_text||x.player_text||""});const m=he(l.reply_text||((f=l.wakeup)==null?void 0:f.reply_text)||l.reply_preview||((h=l.wakeup)==null?void 0:h.reply_preview)||"").trim();if(Be(l)){Ke(l)&&await((o=n.current)==null?void 0:o.call(n,l.state,Q(l.state)));return}await ue(m,l.state||x.state)}catch(l){const m=String((l==null?void 0:l.message)||l||"同步失败");N({id:B("system"),speaker:"system",text:`交流失败：${m}`}),s(`游戏内交流失败：${m}`)}finally{Ce(!1)}},[j,N,w,y,xe,I,O,x,ue,ie,s]),ts=P(((xt=k.theme_profile)==null?void 0:xt.theme)||"未触发"),ss=P(((ut=k.theme_profile)==null?void 0:ut.direction_label)||"待定"),is=zt((ft=k.positions)==null?void 0:ft.xinyue,Y),as=zt((ht=k.positions)==null?void 0:ht.du,Y),Fe=k.winner?We[k.winner]:"",ot=Es((x==null?void 0:x.player_text)||""),D=k.final_note||null,lt=Ot(k.final_note_items||[],D),Ae=String((D==null?void 0:D.id)||`${k.winner||""}-${k.updated_at||""}`),ct=!!(W&&k.winner==="xinyue"&&(!D||D.target==="du")&&!(D!=null&&D.sent)),rs=(((gt=k.statuses)==null?void 0:gt.du)||[]).filter(a=>a.slot==="prop").map(a=>P(a.value||""));u.useEffect(()=>{!W||!D||!Ae||Xe!==Ae&&(qt(Ae),we(!0))},[D,Ae,Xe,W]);const ns=Math.max(0,Number(((bt=(mt=k.hands)==null?void 0:mt.xinyue)==null?void 0:bt.pass)||0)),os=Math.max(0,Number(k.pass_skips_used||0)),dt={xinyue:Pt((wt=k.statuses)==null?void 0:wt.xinyue),du:Pt((yt=k.statuses)==null?void 0:yt.du)},pt=ye&&dt.du&&!C,ls=y||j||I||O||!(x!=null&&x.state)||!!C||ye&&!pt,cs=!(x!=null&&x.state),ds=I||O||y||j||!(x!=null&&x.state);return e.jsxs("div",{className:"sese-game",ref:i,children:[e.jsxs("div",{className:"sese-header",children:[e.jsx("button",{className:"sese-back",type:"button",onClick:t,"aria-label":"返回游戏",children:e.jsx(xs,{})}),e.jsxs("button",{className:"sese-chat-entry",type:"button",onClick:()=>pe(!0),"aria-label":"游戏内交流",children:[e.jsx(us,{}),M?e.jsx("span",{children:M}):null]}),e.jsx("div",{className:"sese-header-title",children:"涩涩走格棋"}),e.jsxs("div",{className:"sese-game-status-bar",children:[e.jsx(Te,{label:"主题",value:ts}),e.jsx(Te,{label:"主导方",value:ss}),e.jsx(Te,{label:"我 进度",value:`${String(is).padStart(2,"0")} / ${Y}`}),e.jsx(Te,{label:"渡 进度",value:`${String(as).padStart(2,"0")} / ${Y}`}),e.jsx("div",{className:"sese-turn-indicator",children:W&&Fe?`${Fe} 到达终点`:ye?"等待 渡 行动...":"轮到 我 行动"})]})]}),e.jsx("section",{className:"sese-board-container","aria-label":"走格棋盘",children:e.jsx("div",{className:"sese-board",style:{gridTemplateColumns:`repeat(${Oe}, minmax(0, 1fr))`},children:Gt.map(a=>{const p=_t.filter(f=>Ue(K[f],Y)===a.position);return e.jsxs("div",{className:`sese-tile sese-tile-${a.kind} ${Se===a.position?"is-active":""}`,children:[e.jsx("div",{className:"sese-tile-number",children:a.position}),e.jsx("div",{className:"sese-tile-icon",children:a.icon}),e.jsx("div",{className:"sese-tile-name",children:a.name}),e.jsx("div",{className:"sese-piece-stack",children:p.map(f=>e.jsx("span",{className:`sese-piece ${f==="xinyue"?"sese-piece-me":"sese-piece-du"} ${dt[f]?"paused":""}`,children:We[f]},f))})]},a.position)})})}),e.jsxs("section",{className:"sese-controls",children:[e.jsxs("div",{className:"sese-player-states",children:[e.jsx(At,{actor:"xinyue",statuses:((vt=k.statuses)==null?void 0:vt.xinyue)||[],active:Re==="xinyue"}),e.jsx(At,{actor:"du",statuses:((kt=k.statuses)==null?void 0:kt.du)||[],active:Re==="du"})]}),lt.length?e.jsx("div",{className:"sese-final-pose-panel",children:lt.map(a=>e.jsxs("div",{className:"sese-final-material-row",children:[e.jsx("span",{children:a.label}),e.jsx("strong",{children:a.values.join("、")})]},a.label))}):null,e.jsxs("div",{className:"sese-action-area",children:[e.jsx("div",{className:`sese-dice ${te?"rolling":""}`,"aria-label":`骰子 ${Z}`,children:Z}),e.jsx("button",{className:"sese-roll-button",type:"button",disabled:ls,onClick:W?qe:()=>void Ye({notifyAfterUserRoll:!0}),children:W?"开新局":C?"先处理任务":pt?"处理停步":ye?"等渡掷骰":y||j?"移动中":I||O?"等渡回应":"掷骰子"}),e.jsx("button",{className:"sese-restart-button",type:"button",disabled:y||j||I||O,onClick:qe,children:"重开"})]}),e.jsx("div",{className:"sese-history",children:ot.length?`最近：${ot[0]}`:"最近：等待第一次掷骰"})]}),X?e.jsx("div",{className:"sese-chat-mask",role:"dialog","aria-modal":"true","aria-label":"游戏内交流",onClick:()=>pe(!1),children:e.jsxs("div",{className:"sese-chat-panel",onClick:a=>a.stopPropagation(),children:[e.jsxs("div",{className:"sese-chat-head",children:[e.jsxs("div",{children:[e.jsx("strong",{children:"游戏内交流"}),e.jsx("span",{children:ye?"等待渡发送【掷骰】":"当前轮到你行动"})]}),e.jsx("button",{type:"button",onClick:()=>pe(!1),"aria-label":"关闭交流",children:"×"})]}),e.jsxs("div",{className:"sese-chat-list",children:[Pe.map(a=>e.jsxs("div",{className:`sese-chat-message ${a.speaker}`,children:[e.jsx("span",{children:a.speaker==="xinyue"?"我":a.speaker==="du"?"渡":"系统"}),e.jsx("p",{children:he(a.text)})]},a.id)),I?e.jsxs("div",{className:"sese-chat-message du pending",children:[e.jsx("span",{children:"渡"}),e.jsx("p",{children:"正在回复..."})]}):null,e.jsx("div",{ref:c})]}),e.jsxs("form",{className:"sese-chat-form",onSubmit:a=>{a.preventDefault(),es()},children:[e.jsx("input",{value:xe,disabled:cs,placeholder:"和渡说一句游戏内的话",onChange:a=>Ve(a.target.value)}),e.jsx("button",{type:"submit",disabled:ds||!xe.trim(),"aria-label":I?"发送中":"发送",children:e.jsx(fs,{})})]})]})}):null,ne?e.jsx("div",{className:"sese-theme-mask",role:"dialog","aria-modal":"true","aria-label":"开局主题抽取",children:e.jsxs("div",{className:"sese-theme-modal",children:[e.jsxs("div",{className:"sese-slot-lights","aria-hidden":"true",children:[e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{})]}),e.jsxs("div",{className:"sese-slot-marquee",children:[e.jsx("span",{children:"THEME"}),e.jsx("strong",{children:"JACKPOT"})]}),e.jsxs("div",{className:"sese-slot-face",children:[e.jsx("div",{className:"sese-theme-window",children:e.jsx("div",{className:"sese-theme-strip",children:ne.items.map((a,p)=>e.jsx("div",{className:"sese-theme-item",children:P(a)},`${a}-${p}`))},ne.spinKey)}),e.jsxs("p",{className:"sese-slot-plaque",children:["主导方：",ne.direction]}),e.jsxs("div",{className:"sese-theme-actions",children:[e.jsx("button",{className:"secondary",type:"button",disabled:y,onClick:qe,children:y?"重抽中":"重抽主题"}),e.jsx("button",{type:"button",onClick:()=>ze(null),children:"开始本局"})]}),e.jsx("div",{className:"sese-slot-tray","aria-hidden":"true"})]})]})}):null,C&&!v?e.jsx("div",{className:"sese-pending-mask",role:"dialog","aria-modal":"true","aria-label":"待处理惩罚",children:e.jsx("div",{className:"sese-pending-modal",children:e.jsx(Vs,{pending:C,reviewFeedback:Le,passCount:ns,passSkipsUsed:os,submission:oe,disabled:y||O,onSubmissionChange:et,onSubmit:Ht,onApprove:Kt,onReject:Wt,onChoose:Jt,onPass:Vt})})}):null,W&&D&&Dt?e.jsx("div",{className:"sese-final-note-mask",role:"dialog","aria-modal":"true","aria-label":"终局小纸条",children:e.jsxs("div",{className:"sese-final-note-modal",children:[e.jsxs("div",{className:"sese-final-note-head",children:[e.jsx("span",{children:"终局小纸条"}),e.jsx("button",{type:"button",onClick:()=>we(!1),"aria-label":"关闭终局小纸条",children:"关闭"})]}),e.jsxs("h2",{children:[Fe||"玩家"," 到达终点"]}),e.jsx(Hs,{note:D,canAddStatus:ct,onAddStatus:()=>Qe(!0)}),D.sent?e.jsx("em",{children:"已发送给渡"}):e.jsx("button",{className:"sese-final-note-send",type:"button",disabled:I||O||y||j,onClick:()=>void Xt(),children:I?"发送中":"发送给渡"})]})}):null,ct&&Yt?e.jsx(Us,{level:Ze,activeProps:rs,disabled:I||O||y||j,onClose:()=>Qe(!1),onLevelChange:Ft,onToggleProp:(a,p)=>{p?Zt("prop",a):Qt("prop",a,Ze)}}):null,v?e.jsx("div",{className:"sese-popup-mask",role:"dialog","aria-modal":"true",children:e.jsxs("div",{className:`sese-popup ${v.kind==="draw"?`sese-popup-draw tone-${v.tone||"penalty"}`:""}`,children:[e.jsx("div",{className:"sese-popup-kicker",children:L(v.kicker||(v.actorLabel?`${v.actorLabel}走到第 ${v.position} 格`:`第 ${v.position} 格`))}),v.kind==="draw"?e.jsx("div",{className:`sese-draw-card ${v.tone==="reward"&&!re?"is-covered":"is-revealed"}`,children:v.tone==="reward"&&!re?e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"sese-card-pile","aria-hidden":"true",children:[e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("b",{})]}),e.jsx("span",{children:"奖励抽卡"}),e.jsx("em",{children:"抽卡中"})]}):e.jsxs(e.Fragment,{children:[Ct(v)?e.jsx("span",{children:Ct(v)}):null,e.jsx("strong",{children:L(v.cardTitle||v.title)})]})}):null,v.kind==="draw"?null:e.jsx("h2",{children:L(v.title)}),v.tone==="reward"&&!re?e.jsx("p",{children:"正在洗牌..."}):$t(v)?e.jsx("p",{children:$t(v)}):null,v.tone==="reward"&&!re?null:e.jsx("button",{type:"button",onClick:Ut,children:"确 认"})]})}):null,Le?e.jsx("div",{className:"sese-pending-mask",role:"dialog","aria-modal":"true","aria-label":"验收反馈",children:e.jsx("div",{className:"sese-pending-modal",children:e.jsx(Xs,{feedback:Le,onClose:()=>Ee(null)})})}):null,e.jsx("style",{children:`
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
        `})]})}function Te({label:t,value:s}){return e.jsxs("div",{className:"sese-pill",children:[e.jsx("span",{children:t}),e.jsx("strong",{children:s})]})}function At({actor:t,statuses:s,active:i}){const r=Ls(s);return e.jsxs("div",{className:`sese-player-card sese-player-card-${t} ${i?"active":""}`,children:[e.jsx("div",{className:"sese-player-card-head",children:e.jsx("h2",{children:t==="xinyue"?"我的状态":"渡的状态"})}),e.jsx("div",{className:"sese-status-list",children:r.length?r.map(c=>e.jsxs("div",{className:"sese-status-group",children:[e.jsx("span",{className:"sese-status-group-label",children:c.label}),e.jsx("div",{className:"sese-status-chip-row",children:c.values.map(d=>e.jsx("span",{className:"sese-status-chip",children:d},`${c.label}-${d}`))})]},c.label)):e.jsx("div",{className:"sese-status-empty",children:"无状态"})})]})}function Us({level:t,activeProps:s,disabled:i,onClose:r,onLevelChange:c,onToggleProp:d}){const n=new Set(s);return e.jsx("div",{className:"sese-toy-console-mask",role:"dialog","aria-modal":"true","aria-label":"玩具控制台",onClick:r,children:e.jsxs("div",{className:"sese-toy-console-sheet",onClick:g=>g.stopPropagation(),children:[e.jsxs("div",{className:"sese-toy-console-head",children:[e.jsxs("div",{children:[e.jsx("span",{children:"玩具控制台"}),e.jsx("strong",{children:"控制渡当前状态"})]}),e.jsx("button",{type:"button",onClick:r,"aria-label":"关闭玩具控制台",children:"关闭"})]}),e.jsxs("div",{className:"sese-toy-console-section",children:[e.jsx("label",{children:"道具档位"}),e.jsx("div",{className:"sese-toy-level-row",children:[1,2,3,4,5].map(g=>e.jsx("button",{type:"button",disabled:i,className:g===t?"selected":"",onClick:()=>c(g),children:g},g))})]}),e.jsxs("div",{className:"sese-toy-console-section",children:[e.jsx("label",{children:"启用道具"}),e.jsx("div",{className:"sese-toy-chip-grid",children:js.map(g=>(()=>{const b=n.has(g);return e.jsx("button",{type:"button",disabled:i,className:b?"selected":"","aria-pressed":b,"aria-label":b?`取消启用${g}`:`启用${g}`,onClick:()=>d(g,b),children:g},g)})())})]})]})})}function Hs({note:t,canAddStatus:s=!1,onAddStatus:i}){const r=Ws(t),c=P(t.theme||"本局主题"),d=t.target==="du"?"渡当前状态":"你的当前状态",n=Js(t.target_status||""),g=Ot([],t);return e.jsxs("div",{className:"sese-final-note-body",children:[e.jsx("div",{className:"sese-final-note-intro",children:r}),e.jsxs("div",{className:"sese-final-note-section",children:[e.jsx("span",{children:"本局主题"}),e.jsx("strong",{children:c})]}),e.jsxs("div",{className:"sese-final-note-section",children:[e.jsxs("div",{className:"sese-final-note-section-title",children:[e.jsx("span",{children:d}),s?e.jsx("button",{type:"button",onClick:i,"aria-label":"打开玩具控制台",children:e.jsx(Ks,{})}):null]}),n.length?n.map(b=>e.jsxs("div",{className:"sese-final-note-status-group",children:[e.jsx("b",{children:b.label}),e.jsx("div",{className:"sese-final-note-status-values",children:b.values.map(x=>e.jsx("span",{children:x},x))})]},b.label)):e.jsx("div",{className:"sese-final-note-empty",children:"没有遗留状态，可以自由决定最后玩法。"})]}),g.map(b=>e.jsxs("div",{className:"sese-final-note-section",children:[e.jsx("span",{children:b.label}),e.jsx("strong",{children:b.values.join("、")})]},b.label)),e.jsx("div",{className:"sese-final-note-closing",children:"请尽情享受你们的ooxx吧！"})]})}function Ks(){return e.jsx("svg",{viewBox:"0 0 24 24","aria-hidden":"true",children:e.jsx("path",{d:"M12 5v14M5 12h14"})})}function Ws(t){return L(t.text||"").split(`
`).map(r=>r.trim()).filter(Boolean).find(r=>!r.startsWith("【")&&!r.startsWith("请根据")&&!r.startsWith("本局主题")&&!r.startsWith("请尽情"))||"终点已到达，赢家状态已清空。"}function Js(t){const s=L(t).trim();return!s||s==="无"?[]:s.split("；").map(i=>i.trim()).filter(Boolean).map(i=>{const r=i.indexOf("：");if(r<0)return{label:"状态",values:[i]};const c=i.slice(0,r).trim()||"状态",d=i.slice(r+1).split("、").map(n=>n.trim()).filter(Boolean);return{label:c,values:d.length?d:["无"]}})}function Vs({pending:t,reviewFeedback:s,passCount:i,passSkipsUsed:r,submission:c,disabled:d,onSubmissionChange:n,onSubmit:g,onApprove:b,onReject:x,onChoose:F,onPass:K}){var X,pe;const E=L(t.name||"惩罚任务"),Z=t.actor||"xinyue",ee=t.reviewer||(Z==="xinyue"?"du":"xinyue"),y=t.current_actor||Z,z=Z==="xinyue",te=y==="xinyue",G=ee==="xinyue",j=!!P(t.question_text||"").trim(),be=P(t.last_reject_reason||"").trim(),Se=z&&t.pass_allowed!==!1&&i>0&&r<1&&!["submitted","questioning"].includes(String(t.phase||"")),ce=L(t.submission||"").trim(),v=/^你的回答[。.]?$/.test(ce)?"":ce,[se,re]=u.useState("");u.useEffect(()=>{re("")},[t.id,t.current_actor,t.phase]);const de=me(se||((X=t.picks)==null?void 0:X.xinyue)),ne=!!me((pe=t.picks)==null?void 0:pe.xinyue);if(t.type==="choice")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:z?"你的选择惩罚":"等待渡选择"}),e.jsx("strong",{children:E})]}),e.jsx("p",{children:L(t.prompt||"选择一项惩罚。")}),z?e.jsx("div",{className:"sese-choice-list",children:(t.choices||[]).map(M=>{const U=String(M.id||M.label||"");return e.jsx("button",{type:"button",disabled:d||!U,onClick:()=>F(U),children:L(M.label||U)},U)})}):e.jsx("div",{className:"sese-pending-wait",children:"等待渡选择惩罚。"}),Se?e.jsx("button",{className:"sese-pass-button",type:"button",disabled:d,onClick:K,children:"使用Pass卡跳过"}):null]});if(t.type==="duel")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:te?"轮到你出拳":"等待渡出拳"}),e.jsx("strong",{children:E||"剪刀石头布对抗"})]}),e.jsx("p",{children:"同格触发对抗。双方各出石头、剪刀或布，系统判定胜负；赢的前进 3 格，输的后退 3 格。"}),e.jsx("div",{className:"sese-choice-list sese-rps-list",children:It.map(M=>e.jsx("button",{className:`sese-rps-button ${de===M.id?"is-selected":""}`,type:"button",title:M.label,"aria-label":M.label,"aria-pressed":de===M.id,disabled:d||!te||ne,onClick:()=>{re(me(M.id)),F(M.id)},children:M.icon},M.id))}),te?null:e.jsx("div",{className:"sese-pending-wait",children:ne?"你的出拳已记录，等待渡出拳。":"等待渡出拳。"})]});if(t.phase==="submitted")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:G?"需要你验收":"等待渡验收"}),e.jsx("strong",{children:E})]}),e.jsx("p",{className:"sese-submission-text",children:P(t.submission_text||"")}),G?e.jsxs(e.Fragment,{children:[e.jsx("textarea",{value:c,placeholder:"写一句验收反馈，会同步给渡",onChange:M=>n(M.target.value)}),e.jsxs("div",{className:"sese-review-actions",children:[e.jsx("button",{type:"button",disabled:d,onClick:b,children:"通过"}),e.jsx("button",{type:"button",disabled:d,onClick:x,children:"打回"})]})]}):e.jsx("div",{className:"sese-pending-wait",children:"等待渡验收你的提交。"})]});if(t.phase==="questioning"){const M=L(t.question_prompt||"请问对方一个你很想知道答案却一直没有问的问题。"),U=L(t.waiting_task||"对方正在出题中。");return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:G?"你来出题":"等待渡出题"}),e.jsx("strong",{children:E})]}),G?e.jsxs(e.Fragment,{children:[e.jsx("p",{children:M}),e.jsx("textarea",{value:c,placeholder:"写下你的问题",onChange:xe=>n(xe.target.value)}),e.jsx("div",{className:"sese-review-actions",children:e.jsx("button",{type:"button",disabled:d||!c.trim(),onClick:g,children:"提交题目"})})]}):e.jsx("div",{className:"sese-pending-wait",children:U==="对方正在出题中。"?"等待渡给出真心话题目。":U})]})}const ze=j?"等待渡回答这个问题。":"等待渡完成并提交任务。";return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:z?"你的惩罚任务":"等待渡提交"}),e.jsx("strong",{children:E})]}),be?e.jsxs("div",{className:"sese-review-feedback",children:["打回反馈：",be]}):null,s&&s.outcome==="rejected"&&z?e.jsxs("div",{className:"sese-review-feedback",children:["渡的反馈：",s.text]}):null,j?e.jsxs("p",{className:"sese-submission-text",children:["题目：",P(t.question_text)]}):null,z?e.jsxs(e.Fragment,{children:[j?null:e.jsx("p",{children:L(t.task||"")}),!j&&v?e.jsxs("div",{className:"sese-pending-tip",children:["提交要求：",v]}):null,e.jsx("textarea",{value:c,placeholder:j?"在这里写回答":"在这里写提交内容",onChange:M=>n(M.target.value)}),e.jsxs("div",{className:"sese-review-actions",children:[e.jsx("button",{type:"button",disabled:d||!c.trim(),onClick:g,children:j?"提交回答":"提交验收"}),Se?e.jsx("button",{type:"button",disabled:d,onClick:K,children:"使用Pass卡"}):null]})]}):e.jsx("div",{className:"sese-pending-wait",children:e.jsx("span",{children:ze})})]})}function Xs({feedback:t,onClose:s}){return e.jsxs("div",{className:"sese-pending-card sese-review-feedback-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:t.outcome==="approved"?"通过反馈":"打回反馈"}),e.jsx("strong",{children:t.title})]}),e.jsx("div",{className:"sese-review-feedback",children:t.text}),e.jsx("div",{className:"sese-pending-wait",children:t.note}),e.jsx("div",{className:"sese-review-actions",children:e.jsx("button",{type:"button",onClick:s,children:"知道了"})})]})}export{ei as SeseBoardGameTab};
