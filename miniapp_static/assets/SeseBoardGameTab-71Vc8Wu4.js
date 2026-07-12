import{u as xs,r as x,j as e,C as us,M as fs,S as hs,b as Bt}from"./index-CnzZL368.js";const It="du-gateway:sese-board-game:chat:v1",gs=new Set(["xinyue","du","system"]),ms=[{id:"system-ready",speaker:"system",text:"游戏内交流在这里。渡明确发送【掷骰】时，棋盘才会执行他的行动。"}];function me(){return ms.map(t=>({...t}))}function bs(){if(typeof window>"u")return me();try{const t=window.localStorage.getItem(It);if(!t)return me();const s=JSON.parse(t);if(!Array.isArray(s))return me();const i=s.flatMap((r,d)=>{if(!r||typeof r!="object")return[];const p=r,n=typeof p.speaker=="string"?p.speaker:"",g=typeof p.text=="string"?p.text.trim():"";return!gs.has(n)||!g?[]:[{id:(typeof p.id=="string"?p.id.trim():"")||`stored-${d}`,speaker:n,text:g}]});return i.length?i:me()}catch{return me()}}function ws(t){if(!(typeof window>"u"))try{window.localStorage.setItem(It,JSON.stringify(t))}catch{}}const St=["xinyue","du"],Je={xinyue:"我",du:"渡"},ys={xinyue:0,du:0},Lt=[{id:"scissors",label:"剪刀",icon:"✌️"},{id:"rock",label:"石头",icon:"👊"},{id:"paper",label:"布",icon:"✋"}],vs={rock:"scissors",scissors:"paper",paper:"rock"},ks={scissors:"scissors",剪刀:"scissors","✌️":"scissors","✌":"scissors",rock:"rock",stone:"rock",石头:"rock",拳头:"rock","👊":"rock",paper:"paper",布:"paper",包袱:"paper","✋":"paper"};function be(t){const s=String(t||"").trim();return s?ks[s]||s:""}function Ct(t){var i;const s=be(t);return((i=Lt.find(r=>r.id===s))==null?void 0:i.label)||String(t||"").trim()||"未出拳"}function js(t,s){var g;const i=be((g=t==null?void 0:t.picks)==null?void 0:g.xinyue),r=be(s);if(!i||!r)return"";const d=Ct(i),p=Ct(r);if(i===r)return`你出了${d}，渡出了${p}。平局，重新出拳。`;const n=vs[i]===r?"你赢":"渡赢";return`你出了${d}，渡出了${p}。${n}。`}const Et={place:"最终地点",pose:"最终姿势"},Ns=["跳蛋","震动乳夹","震动环","乳夹","锁精环","飞机杯","软绳","手腕绑带","眼罩","口球","春药"],_s=["跳蛋","震动","按摩棒","飞机杯","吸乳器","吸吮器"];function Se(t){return new Promise(s=>window.setTimeout(s,t))}function P(t){return String(t||"").replace(/小玥/g,"我")}function L(t){return String(t||"").replace(/小玥/g,"你").replace(/(^|[^自])我/g,"$1你")}function le(t){return String(t||"")}function Ue(t,s){return P(t.player_text||t.text||t.error||"").split(/\r?\n/).map(d=>d.trim()).find(d=>d&&!d.startsWith("【")&&!/^(进度|主题|轮到|手牌|我的状态|渡的状态|最终地点|最终姿势|待处理|可用命令)/.test(d))||s}function A(t){return`${t}-${Date.now()}-${Math.random().toString(36).slice(2,8)}`}function He(t,s){const i=Math.floor(Number(t||0));return Math.max(1,Math.min(s,i||1))}function zt(t,s){const i=Math.floor(Number(t||0));return Math.max(0,Math.min(s,i||0))}function Ss(t,s){const i=[];for(let r=1;r<=t;r+=s){const d=Array.from({length:Math.min(s,t-r+1)},(p,n)=>r+n);i.length%2===1&&d.reverse(),i.push(d)}return i.reverse().flat()}function Cs(t,s,i){if(s===1)return"start";if(s===i)return"end";if(!t)return"empty";const r=`${t.kind||""} ${t.slot||""}`.toLowerCase();return/empty/.test(r)?"empty":/finish_self|finish-jump/.test(r)?"finish-jump":/reset/.test(r)?"reset":/swap/.test(r)?"swap":/move|back|forward/.test(r)?"move":/lock|pause|item/.test(r)?"item":/clear/.test(r)?"clear":/extend|time/.test(r)?"time":/limit/.test(r)?"limit":/place/.test(r)?"place":/pose/.test(r)?"pose":/theme/.test(r)?"theme":"task"}function zs(t){return t==="start"?"🚩":t==="end"?"🏆":t==="place"?"🏫":t==="item"?"🎁":t==="move"?"⏪":t==="reset"?"🔁":t==="finish-jump"?"🏁":t==="swap"?"🔄":t==="clear"?"✨":t==="time"?"⏳":t==="limit"?"🚫":t==="pose"?"◇":t==="theme"?"🚩":t==="task"?"📸":""}function $s(t,s,i){return s===1?"起点":s===i?"终点":P((t==null?void 0:t.name)||"空")}function Ps(t){const s=P(t).match(/(我|渡)掷出\s*(\d+)，从\s*(\d+)\s*走到\s*(\d+)/);return s?{actor:s[1]==="渡"?"du":"xinyue",dice:Number(s[2]||1),from:Number(s[3]||0),to:Number(s[4]||0)}:null}function Le(t){return t.replace(/[。.!！?？\s]+$/g,"").trim()}function Ms(t,s,i,r){const p=[t,...s].map(g=>g.trim()).filter(Boolean).filter(g=>!/^下一次行动[:：]/.test(g)&&!/^待处理[:：]/.test(g)).join(" ");if(/双方回到起点/.test(p))return"双方回到起点";let n=p.match(/(我|你|渡|对方|双方)?\s*从\s*\d+\s*(前进|后退)\s*(\d+)\s*格(?:到|至)\s*\d+/);return n?`${n[1]||i||"玩家"}${n[2]}了 ${n[3]} 格`:(n=p.match(/(我|你|渡|对方|双方)\s*(前进|后退)\s*(\d+)\s*格/),n?`${n[1]}${n[2]}了 ${n[3]} 格`:(n=p.match(/(我|你|渡|对方)\s*从\s*\d+\s*回到起点/),n?`${n[1]}回到起点`:(n=p.match(/(我|你|渡|对方)\s*从\s*\d+\s*直达终点/),n?`${n[1]}直达终点`:Le(t)===Le(r)?"":t?`触发：${t}`:"")))}function As(t,s){var C,te;const i=P(t).split(`
`).map(G=>G.trim()).filter(Boolean),r=i.findIndex(G=>/^第\s*\d+\s*格：/.test(G)),d=r>=0?i[r]:"";if(!d)return null;const p=d.match(/^第\s*(\d+)\s*格：([^，。]+)/),n=(p==null?void 0:p[2])||"格子事件",g=((C=d.match(/抽到「([^」]+)」/))==null?void 0:C[1])||"",b=((te=d.match(/获得\s*([^（，。]+)/))==null?void 0:te[1])||"",u=!!(g||b||/抽卡|惩罚任务|选择惩罚/.test(n)),F=/奖励|Pass卡|获得/.test(d)?"reward":/选择/.test(n)?"choice":"penalty",K=Number((p==null?void 0:p[1])||0),E=s==null?void 0:s.actor,Z=d.replace(/^第\s*\d+\s*格：/,"").trim(),ee=E?Je[E]:"",y=Ms(Z,i.slice(r+1,r+4),ee,n);return{position:K,actor:E,actorLabel:ee,from:s==null?void 0:s.from,to:(s==null?void 0:s.to)??K,title:n,text:d,detail:y,kind:u?"draw":"event",cardTitle:g||b||n,cardType:F==="reward"?"奖励卡":F==="choice"?"选择惩罚":"惩罚任务",tone:F}}function $t(t){const s=L(t.cardType||"").trim(),i=L(t.cardTitle||t.title).trim(),r=L(t.title).trim();return!s||s===i||s===r?"":s}function Pt(t){const s=L(t.detail||"").trim(),i=L(t.title).trim();return!s||Le(s.replace(/^触发[:：]\s*/,""))===Le(i)?"":s}function Ts(t,s,i){const r=P(t).trim();if(!r)return null;const d=Array.isArray(i)?i.map(u=>P(u).trim()).filter(Boolean):[],b=[...[...Array.from(new Set(d)).filter(u=>u!==r)].sort(()=>Math.random()-.5).slice(0,7),r];for(;b.length<8;)b.unshift(r);return{theme:r,direction:P(s||"待定"),items:b,spinKey:`${Date.now()}-${Math.random().toString(36).slice(2,8)}`}}function Bs(t){const s=String(t.duration_type||"");if(s==="actions"){const i=Math.max(0,Number(t.remaining_actions||0));return t.blocks_action?`停步剩余 ${i} 次`:`剩余 ${i} 次行动`}return s==="minutes"?`${Math.max(1,Number(t.minutes||0))} 分钟`:s==="until_finish"?"到终点前有效":s==="until_clear"?"待解除":""}function Ot(t){return!!Et[String(t||"").trim()]}function Rt(t,s){const i=new Map;for(const p of t||[]){const n=String((p==null?void 0:p.slot)||"").trim();if(!Ot(n))continue;const g=P((p==null?void 0:p.value)||"").trim();g&&i.set(n,g)}const r=P((s==null?void 0:s.final_place)||"").trim(),d=P((s==null?void 0:s.final_pose)||"").trim();return r&&!i.has("place")&&i.set("place",r),d&&!i.has("pose")&&i.set("pose",d),["place","pose"].map(p=>{const n=i.get(p);return n?{label:Et[p]||"终局素材",values:[n]}:null}).filter(p=>!!p)}function Is(t){const s=P(t.label||t.slot||"状态");return t.slot==="prop"||s==="道具"?"道具惩罚":s}function Ls(t){const s=P(t.value||""),i=[],r=Math.max(1,Number(t.level||1));t.slot==="prop"&&r>1&&Dt(s)&&i.push(`${r}档`);const d=Bs(t);return d&&i.push(d),s?i.length?`${s}（${i.join("，")}）`:s:i.length?i.join("，"):"状态"}function Dt(t){return _s.some(s=>t.includes(s))}function Es(t){const s=new Map;return t.filter(i=>!Ot(i.slot)).slice(-6).forEach(i=>{const r=Is(i),d=s.get(r)||[];d.push(Ls(i)),s.set(r,d)}),Array.from(s.entries()).map(([i,r])=>({label:i,values:r}))}function Mt(t){return(t||[]).some(s=>s.blocks_action&&Number(s.remaining_actions||0)>0)}function Os(t){const s=[/^(我|渡)掷出\s*\d+/,/^第\s*\d+\s*格：/,/^下一次行动：/,/行动权/,/到达终点/,/^新局已开始。?$/,/^本局已结束。?$/];return P(t).split(`
`).map(i=>i.trim()).filter(i=>i&&s.some(r=>r.test(i))).slice(0,4)}function Rs(t){return String(t).split(/\r?\n/).map(i=>i.trim()).find(Boolean)==="【掷骰】"}function Ds(t){return String(t).split(/\r?\n/).some(s=>s.trim()==="【掷骰】")}function At(t,s){return t.slice(s).map(i=>{const r=i.trim();if(r==="【掷骰】")return"";const d=r.match(/^【描述[:：](.*)】$/);return d?d[1].trim():r}).filter(Boolean).join(`
`).trim()}function Ke(t,s,i){var b;const d=(((b=t[s])==null?void 0:b.trim())||"").match(i);if(!d)return null;const p=d[1]||"",n=p.indexOf("】");if(n>=0)return p.slice(0,n).trim();const g=[p,...t.slice(s+1)].join(`
`).trim();return g.endsWith("】")?g.slice(0,-1).trim():g}function qs(t){const s=String(t).split(/\r?\n/),i=s.findIndex(E=>E.trim());if(i<0)return{kind:"",body:""};const r=s[i].trim(),d=At(s,i+1),p=Ke(s,i,/^【描述[:：](.*)$/);if(p!==null)return{kind:"submit",body:p||d};const n=Ke(s,i,/^【真心话出题[:：](.*)$/);if(n!==null)return{kind:"submit",body:n||d};const g=Ke(s,i,/^【真心话回答[:：](.*)$/);if(g!==null)return{kind:"submit",body:g||d};if(r==="【掷骰】")return{kind:"roll",body:d};if(r==="【提交】")return{kind:"submit",body:d};const b=r.match(/^【通过[:：](.*?)(?:】)?$/);if(b)return{kind:"approve",body:b[1].trim()||d};const u=r.match(/^【(?:不通过|打回|驳回)[:：](.*?)(?:】)?$/);if(u)return{kind:"reject",body:u[1].trim()||d};if(r==="【通过】")return{kind:"approve",body:d};if(r==="【不通过】"||r==="【打回】"||r==="【驳回】")return{kind:"reject",body:d};if(r==="【Pass】"||r==="【PASS】"||r==="【使用Pass卡】")return{kind:"pass",body:d};const F=r.match(/^【选择[:：](.+)】$/);if(F)return{kind:"choose",choice:F[1].trim(),body:d};const K=r.match(/^【(?:剪刀石头布|石头剪刀布)[:：](.+)】$/);return K?{kind:"choose",choice:K[1].trim(),body:d}:{kind:"",body:At(s,i)}}function Ys(t,s="rock"){const i=((t==null?void 0:t.choices)||[]).find(r=>(r==null?void 0:r.id)||(r==null?void 0:r.label));return String((i==null?void 0:i.id)||(i==null?void 0:i.label)||s).trim()}const Fs=new Set(["反向诱惑","全部暴露！","羞耻台词大放送","自慰陈述"]);function Gs(t,s){if(t==="final_note")return"本地预览：终局小纸条收到了。";const i=(s==null?void 0:s.pending_event)||null;if((i==null?void 0:i.type)==="duel"&&i.current_actor==="du")return"【剪刀石头布：石头】";if((i==null?void 0:i.type)==="choice"&&i.actor==="du"){const r=Ys(i,"");if(r)return`【选择：${r}】`}return(i==null?void 0:i.type)==="review"&&i.reviewer==="du"&&i.phase==="questioning"?"【真心话出题：本地预览：渡想问你的真心话问题。】":(i==null?void 0:i.type)==="review"&&i.actor==="du"&&i.phase==="assigned"?i.name==="真心话点名"?"【真心话回答：本地预览：渡已经回答真心话。】":Fs.has(String(i.name||""))?"【描述：本地预览：渡已经完成任务，提交给你验收。】":`【提交】
本地预览：渡已经完成任务，提交给你验收。`:(i==null?void 0:i.type)==="review"&&i.reviewer==="du"&&i.phase==="submitted"?`【通过：本地预览：验收通过。】
【掷骰】`:ce(s)?"【掷骰】":"本地预览：我看到了，等你继续行动。"}async function R(t){const s=await Bt("/miniapp-api/game-tools/private_board",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:t,save_id:"default"})});if(!(s!=null&&s.ok))throw new Error((s==null?void 0:s.error)||"走格棋命令失败");return s}async function Us(t){var i;const s=await Bt("/miniapp-api/game-tools/private_board/sync-du",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({save_id:"default",client_version:"game_chat_v2",mode:t.mode,message:t.message||"",roll_text:t.rollText||""})});if(!(s!=null&&s.ok))throw new Error((s==null?void 0:s.error)||((i=s==null?void 0:s.wakeup)==null?void 0:i.error)||"游戏内交流失败");return s}function ce(t){return!!(t&&t.turn_actor==="du"&&!t.game_over)}function Ve(t){const s=(t==null?void 0:t.pending_event)||null;if(!t||t.game_over||!s)return!1;if(s.type==="duel")return s.current_actor==="du";if(s.type==="choice")return s.actor==="du";if(s.type==="review"){const i=String(s.phase||"");return i==="questioning"||i==="submitted"?s.reviewer==="du":s.actor==="du"}return!1}function Ie(t){return Array.isArray(t==null?void 0:t.applied_reply_commands)&&t.applied_reply_commands.length>0}function We(t){if(!Ie(t)||Array.isArray(t==null?void 0:t.followup_wakeups)&&t.followup_wakeups.length>0)return!1;const s=t==null?void 0:t.state;return ce(s)&&(!(s!=null&&s.pending_event)||Ve(s))}function Q(t){const s=(t==null?void 0:t.pending_event)||null;if(!s)return"现在轮到渡行动。";if(s.type==="duel")return"现在轮到渡完成剪刀石头布对抗。";if(s.type==="choice")return"渡刚触发了需要自己选择的惩罚。";if(s.type==="review"){const i=String(s.phase||"");return i==="questioning"?"现在需要渡给出真心话题目。":i==="submitted"?"现在需要渡验收小玥提交的惩罚任务。":"现在需要渡提交惩罚任务。"}return"现在轮到渡处理棋局。"}function ti({onBack:t}){var ut,ft,ht,gt,mt,bt,wt,yt,vt,kt,jt;const s=xs(),i=x.useRef(null),r=x.useRef(!1),d=x.useRef(null),p=x.useRef(null),n=x.useRef(null),g=x.useRef(null),b=x.useRef(""),[u,F]=x.useState(null),[K,E]=x.useState(ys),[Z,ee]=x.useState(1),[y,C]=x.useState(!1),[te,G]=x.useState(!1),[j,we]=x.useState(!1),[Ce,de]=x.useState(null),[v,se]=x.useState(null),[re,pe]=x.useState(!0),[ne,ze]=x.useState(null),[X,xe]=x.useState(!1),[M,U]=x.useState(0),[ue,Xe]=x.useState(""),[I,$e]=x.useState(!1),[O,Pe]=x.useState(!1),[qt,ye]=x.useState(!1),[Qe,Yt]=x.useState(""),[Ft,Ze]=x.useState(!1),[et,Gt]=x.useState(1),[oe,tt]=x.useState(""),[Ee,Oe]=x.useState(null),[Me,st]=x.useState(bs),k=(u==null?void 0:u.state)||{},Y=Math.max(12,Math.min(80,Number(k.board_size||36))),Re=Y<=36?6:8,De=k.turn_actor==="du"?"du":"xinyue",W=!!(k.game_over||u!=null&&u.game_over),ve=De==="du"&&!W,$=k.pending_event||null,Ae=x.useMemo(()=>{try{return!!new URLSearchParams(window.location.search).has("preview")}catch{return!1}},[]);x.useLayoutEffect(()=>{i.current&&(i.current.scrollTop=0)},[]),x.useEffect(()=>{r.current=X,X&&U(0)},[X]),x.useEffect(()=>{X&&window.setTimeout(()=>{var a;return(a=d.current)==null?void 0:a.scrollIntoView({block:"end"})},40)},[Me.length,X,I]),x.useEffect(()=>{ws(Me)},[Me]),x.useEffect(()=>{if(!v||v.kind!=="draw"||v.tone!=="reward"){pe(!0);return}pe(!1);const a=window.setTimeout(()=>pe(!0),900);return()=>window.clearTimeout(a)},[v]);const N=x.useCallback((a,o=!1)=>{st(h=>[...h,a]),o&&!r.current&&U(h=>Math.min(9,h+1))},[]),fe=x.useCallback(a=>{for(const o of a.game_chat_messages||[]){const h=le((o==null?void 0:o.text)||"").trim(),f=o==null?void 0:o.speaker;!h||f!=="du"&&f!=="system"||N({id:A(f),speaker:f,text:h},!0)}},[N]),it=x.useMemo(()=>{const a=new Map;for(const o of k.cell_events||[]){const h=Number((o==null?void 0:o.position)||0);h>0&&a.set(h,o)}return a},[k.cell_events]),Ut=x.useMemo(()=>Ss(Y,Re).map(a=>{const o=it.get(a),h=Cs(o,a,Y);return{position:a,event:o,kind:h,icon:zs(h),name:$s(o,a,Y)}}),[Y,Re,it]),w=x.useCallback(a=>{var o,h,f,l;F(a),E({xinyue:Number(((h=(o=a.state)==null?void 0:o.positions)==null?void 0:h.xinyue)||0),du:Number(((l=(f=a.state)==null?void 0:f.positions)==null?void 0:l.du)||0)})},[]),at=x.useCallback(async()=>{C(!0);try{const a=await R("status");w(a)}catch(a){s(`加载涩涩走格棋失败：${(a==null?void 0:a.message)||a}`)}finally{C(!1)}},[w,s]);x.useEffect(()=>{at()},[at]);const rt=x.useCallback(async a=>{G(!0);for(let o=0;o<12;o+=1)ee(Math.floor(Math.random()*6)+1),await Se(58);ee(Math.max(1,Math.min(6,a||1))),G(!1)},[]),qe=x.useCallback(async(a,o,h,f)=>{const l=Number(h||0),c=Number(f||0);if(l===c){a[o]=c,E({...a}),de(He(c,Y)),await Se(120);return}const m=c>l?1:-1;for(let T=l+m;m>0?T<=c:T>=c;T+=m)a[o]=T,E({...a}),de(He(T,Y)),await Se(145)},[Y]),Ye=x.useCallback(async()=>{var a,o,h,f,l;if(!(y||j)){C(!0),se(null);try{const c=await R("new_game");ee(1),w(c),st(me()),U(0),ze(Ts((o=(a=c.state)==null?void 0:a.theme_profile)==null?void 0:o.theme,(f=(h=c.state)==null?void 0:h.theme_profile)==null?void 0:f.direction_label,(l=c.state)==null?void 0:l.theme_options))}catch(c){s(`开新局失败：${(c==null?void 0:c.message)||c}`)}finally{C(!1)}}},[j,w,y,s]);x.useCallback(async()=>{if(!(y||j)){C(!0);try{const a=await R("end_game");w(a)}catch(a){s(`结束本局失败：${(a==null?void 0:a.message)||a}`)}finally{C(!1)}}},[j,w,y,s]);const he=x.useCallback(async(a,o)=>{var T,ae,z,V,ke,je,Ne,_e,B,H;const h=a.trim()||"我看到了。",f=qs(h),l=(o==null?void 0:o.pending_event)||null,c=f.body.trim(),m=(l==null?void 0:l.reviewer)==="du"&&l.type==="review"&&l.phase==="submitted"&&(f.kind==="approve"||f.kind==="reject");c&&!m&&N({id:A("du"),speaker:"du",text:c},!0);try{if((l==null?void 0:l.type)==="duel"&&l.current_actor==="du"){if(f.kind!=="choose"||!f.choice.trim())return;const _=f.choice.trim(),S=js(l,_),q=await R(`choose ${_}`);w(q);const ge=ce(q.state)&&!((T=q.state)!=null&&T.pending_event);S&&(g.current=ge?{state:q.state,message:"剪刀石头布对抗已结算，现在轮到渡行动。"}:null,se({position:Number(l.cell||((z=(ae=q.state)==null?void 0:ae.positions)==null?void 0:z.du)||0),kicker:"剪刀石头布对抗",title:"对抗结果",text:S,detail:S,kind:"event"})),N({id:A("system"),speaker:"system",text:S||Ue(q,"渡已出拳，系统已判定对抗结果。")},!0),!S&&ge&&await((V=n.current)==null?void 0:V.call(n,q.state,"剪刀石头布对抗已结算，现在轮到渡行动。"));return}if((l==null?void 0:l.reviewer)==="du"&&l.type==="review"&&l.phase==="questioning"){if(f.kind!=="submit")return;const _=f.body.trim();if(!_){N({id:A("system"),speaker:"system",text:"渡发了【提交】，但后面没有题目。"},!0);return}const S=await R(`submit ${_}`);w(S),N({id:A("system"),speaker:"system",text:"渡已出题，轮到你回答。"},!0);return}if((l==null?void 0:l.actor)==="du"&&l.type==="review"&&l.phase==="assigned"){if(f.kind!=="submit")return;const _=f.body.trim();if(!_){N({id:A("system"),speaker:"system",text:"渡发了【提交】，但后面没有提交内容。"},!0);return}const S=await R(`submit ${_}`);w(S),N({id:A("system"),speaker:"system",text:"渡已提交惩罚任务，等你验收。"},!0),await((ke=n.current)==null?void 0:ke.call(n,S.state,Q(S.state)));return}if((l==null?void 0:l.actor)==="du"&&l.type==="choice"){if(f.kind==="pass"){const S=await R("pass");if(w(S),S.ok===!1){N({id:A("system"),speaker:"system",text:Ue(S,"渡没有Pass卡，不能跳过。")},!0);return}N({id:A("system"),speaker:"system",text:"渡使用Pass卡跳过了惩罚。"},!0),await((je=n.current)==null?void 0:je.call(n,S.state,Q(S.state)));return}if(f.kind!=="choose"||!f.choice.trim())return;const _=await R(`choose ${f.choice.trim()}`);w(_),N({id:A("system"),speaker:"system",text:"渡已选择惩罚选项。"},!0),await((Ne=n.current)==null?void 0:Ne.call(n,_.state,Q(_.state)));return}if((l==null?void 0:l.reviewer)==="du"&&l.type==="review"&&l.phase==="submitted"){if(f.kind==="approve"){const _=Ds(h),S=f.body.trim()||"验收通过。",q=await R(`approve ${S}`);if(w(q),Oe({outcome:"approved",title:"渡验收通过",text:S,note:_?"已继续执行渡的掷骰。":"棋局继续。"}),_&&ce(q.state)){await Se(260),await((_e=p.current)==null?void 0:_e.call(p,{notifyAfterUserRoll:!1}));return}await((B=n.current)==null?void 0:B.call(n,q.state,Q(q.state)));return}if(f.kind==="reject"){const _=f.body.trim()||"需要重新提交。",S=await R(`reject ${_}`);w(S),Oe({outcome:"rejected",title:"渡打回了任务",text:_,note:"请按反馈修改后重新提交。"});return}return}ce(o)&&Rs(h)&&(await Se(260),N({id:A("system"),speaker:"system",text:"渡发送【掷骰】，已执行他的行动。"},!0),await((H=p.current)==null?void 0:H.call(p,{notifyAfterUserRoll:!1})))}catch(_){N({id:A("system"),speaker:"system",text:`渡的指令执行失败：${String((_==null?void 0:_.message)||_)}`},!0)}},[N,w]),ie=x.useCallback(async(a,o)=>{if(!Ae)return Us(a);let h=o,f="";if(a.mode==="final_note"){const c=await R("final_note_sent");h=c.state||h,f=c.player_text||c.text||""}const l=Gs(a.mode,h);return{ok:!0,state:h,player_text:f,reply_text:l,reply_preview:l.slice(0,120),wakeup:{reply_text:l,reply_preview:l.slice(0,120)}}},[Ae]),nt=x.useCallback(async(a,o="现在轮到渡行动。")=>{var f,l,c;const h=Ve(a);if(!(!ce(a)||a!=null&&a.pending_event&&!h)){Pe(!0);try{const m=await ie({mode:"state_update",message:o,rollText:""},a);m.state&&w({ok:!0,state:m.state,player_text:m.player_text||""});const T=le(m.reply_text||((f=m.wakeup)==null?void 0:f.reply_text)||m.reply_preview||((l=m.wakeup)==null?void 0:l.reply_preview)||"").trim();if(Ie(m)){fe(m),We(m)&&await((c=n.current)==null?void 0:c.call(n,m.state,Q(m.state)));return}await he(T,m.state||a)}catch(m){const T=String((m==null?void 0:m.message)||m||"同步失败");N({id:A("system"),speaker:"system",text:`渡行动同步失败：${T}`},!0),s(`渡行动同步失败：${T}`)}finally{Pe(!1)}}},[N,fe,w,he,ie,s]);x.useEffect(()=>{n.current=nt},[nt]);const Ht=x.useCallback(()=>{var o;const a=g.current;g.current=null,se(null),a&&((o=n.current)==null||o.call(n,a.state,a.message))},[]),ot=x.useCallback(async(a,o="小玥刚掷完骰子。")=>{var m,T,ae;const h=le(a.text||a.du_text||a.player_text||"").trim(),f=b.current.trim(),l=o.trim()==="小玥刚掷完骰子。"?"":o.trim(),c=[f,l].filter(Boolean).join(`
`);Pe(!0);try{const z=await ie({mode:"roll_result",message:c,rollText:h},a.state);f&&b.current.trim()===f&&(b.current=""),z.state&&w({ok:!0,state:z.state,player_text:z.player_text||a.player_text||""});const V=le(z.reply_text||((m=z.wakeup)==null?void 0:m.reply_text)||z.reply_preview||((T=z.wakeup)==null?void 0:T.reply_preview)||"").trim();if(Ie(z)){fe(z),We(z)&&await((ae=n.current)==null?void 0:ae.call(n,z.state,Q(z.state)));return}await he(V,z.state||a.state)}catch(z){const V=String((z==null?void 0:z.message)||z||"同步失败");N({id:A("system"),speaker:"system",text:`自动同步失败：${V}`},!0),s(`自动同步给渡失败：${V}`)}finally{Pe(!1)}},[N,fe,w,he,ie,s]),Fe=x.useCallback(async(a={})=>{var m,T,ae,z,V,ke,je,Ne,_e;if(y||j||W)return;let o=null,h=null;C(!0),we(!0),se(null);const f={xinyue:Number(((m=k.positions)==null?void 0:m.xinyue)||0),du:Number(((T=k.positions)==null?void 0:T.du)||0)},l=k.turn_actor==="du"?"du":"xinyue",c={...f};try{const B=await R("roll"),H=Ps(B.player_text||"");await rt((H==null?void 0:H.dice)||Math.floor(Math.random()*6)+1),H&&await qe(c,H.actor,H.from,H.to);const _={xinyue:Number(((z=(ae=B.state)==null?void 0:ae.positions)==null?void 0:z.xinyue)||0),du:Number(((ke=(V=B.state)==null?void 0:V.positions)==null?void 0:ke.du)||0)};for(const ge of St){const Nt=Number(c[ge]||0),_t=Number(_[ge]||0);Nt!==_t&&await qe(c,ge,Nt,_t)}w(B);const S=As(B.player_text||"",H);S&&se(S);const q=((je=B.state)==null?void 0:je.pending_event)||null;a.notifyAfterUserRoll!==!1&&l==="xinyue"&&!((Ne=B.state)!=null&&Ne.game_over)&&(!q||Ve(B.state))?o=B:a.notifyAfterUserRoll===!1&&l==="du"&&ce(B.state)&&(h=B)}catch(B){s(`掷骰失败：${(B==null?void 0:B.message)||B}`)}finally{C(!1),we(!1),window.setTimeout(()=>de(null),260)}o?await ot(o):h&&await((_e=n.current)==null?void 0:_e.call(n,h.state,Q(h.state)))},[qe,rt,j,w,y,W,ot,k.positions,k.turn_actor,s]);x.useEffect(()=>{p.current=Fe},[Fe]);const J=x.useCallback(async(a,o={})=>{var f,l;if(y||!(u!=null&&u.state))return;let h=null;C(!0),se(null);try{const c=await R(a);if(h=c,w(c),c.ok===!1){s(Ue(c,"这次操作没有生效。"));return}tt(""),o.success&&N({id:A("system"),speaker:"system",text:o.success},!0),(f=o.deferSyncMessage)!=null&&f.trim()&&(b.current=o.deferSyncMessage.trim())}catch(c){s(`处理惩罚任务失败：${(c==null?void 0:c.message)||c}`)}finally{C(!1)}h&&o.syncAfter&&await((l=n.current)==null?void 0:l.call(n,h.state,o.syncMessage||Q(h.state)))},[N,w,y,u==null?void 0:u.state,s]),Kt=x.useCallback(()=>{const a=oe.trim();if(!a){s("先写提交内容。");return}J(`submit ${a}`,{success:"已提交任务，等渡验收。",syncAfter:!0,syncMessage:"小玥提交了惩罚任务，请你验收。"})},[J,oe,s]),Wt=x.useCallback(()=>{const a=oe.trim();J(a?`approve ${a}`:"approve",{success:"你通过了任务，棋局继续。",deferSyncMessage:a?`小玥刚刚通过了你的惩罚任务：${a}`:"小玥刚刚通过了你的惩罚任务。"})},[J,oe]),Jt=x.useCallback(()=>{const a=oe.trim();J(a?`reject ${a}`:"reject",{success:"你打回了任务，等渡重新提交。",syncAfter:!0,syncMessage:a?`小玥打回了你的惩罚任务：${a}`:"小玥打回了你的惩罚任务，请重新提交。"})},[J,oe]),Vt=x.useCallback(a=>{const o=($==null?void 0:$.type)==="duel",h=($==null?void 0:$.current_actor)||($==null?void 0:$.actor);if(o&&!(o&&h==="xinyue")){s("等待渡出拳。");return}J(`choose ${a}`,{success:o?"已出拳，等待渡出拳。":"已选择惩罚，棋局继续。",syncAfter:!0,syncMessage:o?"小玥已在剪刀石头布对抗中出拳。请第一行单独发送【剪刀石头布：石头】、【剪刀石头布：剪刀】或【剪刀石头布：布】。":"小玥处理完选择惩罚，棋局继续。"})},[J,$==null?void 0:$.actor,$==null?void 0:$.current_actor,$==null?void 0:$.type,s]),Xt=x.useCallback(()=>{J("pass",{success:"已使用Pass卡跳过惩罚。",syncAfter:!0,syncMessage:"小玥使用Pass卡跳过了惩罚任务。"})},[J]),Qt=x.useCallback(async()=>{var o,h,f;const a=((o=u==null?void 0:u.state)==null?void 0:o.final_note)||null;if(!(I||O||y||j||!(u!=null&&u.state)||!a||a.sent)){$e(!0);try{const l=await ie({mode:"final_note",message:a.text||""},u.state);l.state&&w({ok:!0,state:l.state,player_text:l.player_text||u.player_text||""}),N({id:A("system"),speaker:"system",text:Ae?"预览模式：终局小纸条已同步。":"终局小纸条已发送给渡。"},!0);const c=le(l.reply_text||((h=l.wakeup)==null?void 0:h.reply_text)||l.reply_preview||((f=l.wakeup)==null?void 0:f.reply_preview)||"").trim();c&&N({id:A("du"),speaker:"du",text:c},!0),ye(!1)}catch(l){const c=String((l==null?void 0:l.message)||l||"同步失败");N({id:A("system"),speaker:"system",text:`小纸条发送失败：${c}`},!0),s(`发送终局小纸条失败：${c}`)}finally{$e(!1)}}},[j,N,w,y,I,O,Ae,u,ie,s]),Zt=x.useCallback(async(a,o,h=1)=>{if(I||O||y||j||!(u!=null&&u.state))return;const f=o.replace(/\s+/g," ").trim();if(!f){s("先选要追加的内容。");return}const l=a==="prop"&&Dt(f)?` level=${Math.max(1,Math.min(5,Math.round(Number(h)||1)))}`:"";C(!0);try{const c=await R(`append_final_status ${a} ${f}${l}`);w(c),ye(!0),s(`已启用：${f}`)}catch(c){s(`追加失败：${(c==null?void 0:c.message)||c}`)}finally{C(!1)}},[j,w,y,I,O,u==null?void 0:u.state,s]),es=x.useCallback(async(a,o)=>{if(I||O||y||j||!(u!=null&&u.state))return;const h=o.replace(/\s+/g," ").trim();if(h){C(!0);try{const f=await R(`remove_final_status ${a} ${h}`);w(f),ye(!0),s(`已取消：${h}`)}catch(f){s(`取消失败：${(f==null?void 0:f.message)||f}`)}finally{C(!1)}}},[j,w,y,I,O,u==null?void 0:u.state,s]),ts=x.useCallback(async()=>{var h,f,l;if(I||O||y||j||!(u!=null&&u.state))return;const a=ue.trim();if(!a)return;const o={id:A("me"),speaker:"xinyue",text:a};Xe(""),N(o),$e(!0);try{const c=await ie({mode:"chat",message:a},u.state);c.state&&w({ok:!0,state:c.state,player_text:c.player_text||u.player_text||""});const m=le(c.reply_text||((h=c.wakeup)==null?void 0:h.reply_text)||c.reply_preview||((f=c.wakeup)==null?void 0:f.reply_preview)||"").trim();if(Ie(c)){fe(c),We(c)&&await((l=n.current)==null?void 0:l.call(n,c.state,Q(c.state)));return}await he(m,c.state||u.state)}catch(c){const m=String((c==null?void 0:c.message)||c||"同步失败");N({id:A("system"),speaker:"system",text:`交流失败：${m}`}),s(`游戏内交流失败：${m}`)}finally{$e(!1)}},[j,N,fe,w,y,ue,I,O,u,he,ie,s]),ss=P(((ut=k.theme_profile)==null?void 0:ut.theme)||"未触发"),is=P(((ft=k.theme_profile)==null?void 0:ft.direction_label)||"待定"),as=zt((ht=k.positions)==null?void 0:ht.xinyue,Y),rs=zt((gt=k.positions)==null?void 0:gt.du,Y),Ge=k.winner?Je[k.winner]:"",lt=Os((u==null?void 0:u.player_text)||""),D=k.final_note||null,ct=Rt(k.final_note_items||[],D),Te=String((D==null?void 0:D.id)||`${k.winner||""}-${k.updated_at||""}`),dt=!!(W&&k.winner==="xinyue"&&(!D||D.target==="du")&&!(D!=null&&D.sent)),ns=(((mt=k.statuses)==null?void 0:mt.du)||[]).filter(a=>a.slot==="prop").map(a=>P(a.value||""));x.useEffect(()=>{!W||!D||!Te||Qe!==Te&&(Yt(Te),ye(!0))},[D,Te,Qe,W]);const os=Math.max(0,Number(((wt=(bt=k.hands)==null?void 0:bt.xinyue)==null?void 0:wt.pass)||0)),ls=Math.max(0,Number(k.pass_skips_used||0)),pt={xinyue:Mt((yt=k.statuses)==null?void 0:yt.xinyue),du:Mt((vt=k.statuses)==null?void 0:vt.du)},xt=ve&&pt.du&&!$,cs=y||j||I||O||!(u!=null&&u.state)||!!$||ve&&!xt,ds=!(u!=null&&u.state),ps=I||O||y||j||!(u!=null&&u.state);return e.jsxs("div",{className:"sese-game",ref:i,children:[e.jsxs("div",{className:"sese-header",children:[e.jsx("button",{className:"sese-back",type:"button",onClick:t,"aria-label":"返回游戏",children:e.jsx(us,{})}),e.jsxs("button",{className:"sese-chat-entry",type:"button",onClick:()=>xe(!0),"aria-label":"游戏内交流",children:[e.jsx(fs,{}),M?e.jsx("span",{children:M}):null]}),e.jsx("div",{className:"sese-header-title",children:"涩涩走格棋"}),e.jsxs("div",{className:"sese-game-status-bar",children:[e.jsx(Be,{label:"主题",value:ss}),e.jsx(Be,{label:"主导方",value:is}),e.jsx(Be,{label:"我 进度",value:`${String(as).padStart(2,"0")} / ${Y}`}),e.jsx(Be,{label:"渡 进度",value:`${String(rs).padStart(2,"0")} / ${Y}`}),e.jsx("div",{className:"sese-turn-indicator",children:W&&Ge?`${Ge} 到达终点`:ve?"等待 渡 行动...":"轮到 我 行动"})]})]}),e.jsx("section",{className:"sese-board-container","aria-label":"走格棋盘",children:e.jsx("div",{className:"sese-board",style:{gridTemplateColumns:`repeat(${Re}, minmax(0, 1fr))`},children:Ut.map(a=>{const o=St.filter(h=>He(K[h],Y)===a.position);return e.jsxs("div",{className:`sese-tile sese-tile-${a.kind} ${Ce===a.position?"is-active":""}`,children:[e.jsx("div",{className:"sese-tile-number",children:a.position}),e.jsx("div",{className:"sese-tile-icon",children:a.icon}),e.jsx("div",{className:"sese-tile-name",children:a.name}),e.jsx("div",{className:"sese-piece-stack",children:o.map(h=>e.jsx("span",{className:`sese-piece ${h==="xinyue"?"sese-piece-me":"sese-piece-du"} ${pt[h]?"paused":""}`,children:Je[h]},h))})]},a.position)})})}),e.jsxs("section",{className:"sese-controls",children:[e.jsxs("div",{className:"sese-player-states",children:[e.jsx(Tt,{actor:"xinyue",statuses:((kt=k.statuses)==null?void 0:kt.xinyue)||[],active:De==="xinyue"}),e.jsx(Tt,{actor:"du",statuses:((jt=k.statuses)==null?void 0:jt.du)||[],active:De==="du"})]}),ct.length?e.jsx("div",{className:"sese-final-pose-panel",children:ct.map(a=>e.jsxs("div",{className:"sese-final-material-row",children:[e.jsx("span",{children:a.label}),e.jsx("strong",{children:a.values.join("、")})]},a.label))}):null,e.jsxs("div",{className:"sese-action-area",children:[e.jsx("div",{className:`sese-dice ${te?"rolling":""}`,"aria-label":`骰子 ${Z}`,children:Z}),e.jsx("button",{className:"sese-roll-button",type:"button",disabled:cs,onClick:W?Ye:()=>void Fe({notifyAfterUserRoll:!0}),children:W?"开新局":$?"先处理任务":xt?"处理停步":ve?"等渡掷骰":y||j?"移动中":I||O?"等渡回应":"掷骰子"}),e.jsx("button",{className:"sese-restart-button",type:"button",disabled:y||j||I||O,onClick:Ye,children:"重开"})]}),e.jsx("div",{className:"sese-history",children:lt.length?`最近：${lt[0]}`:"最近：等待第一次掷骰"})]}),X?e.jsx("div",{className:"sese-chat-mask",role:"dialog","aria-modal":"true","aria-label":"游戏内交流",onClick:()=>xe(!1),children:e.jsxs("div",{className:"sese-chat-panel",onClick:a=>a.stopPropagation(),children:[e.jsxs("div",{className:"sese-chat-head",children:[e.jsxs("div",{children:[e.jsx("strong",{children:"游戏内交流"}),e.jsx("span",{children:ve?"等待渡发送【掷骰】":"当前轮到你行动"})]}),e.jsx("button",{type:"button",onClick:()=>xe(!1),"aria-label":"关闭交流",children:"×"})]}),e.jsxs("div",{className:"sese-chat-list",children:[Me.map(a=>e.jsxs("div",{className:`sese-chat-message ${a.speaker}`,children:[e.jsx("span",{children:a.speaker==="xinyue"?"我":a.speaker==="du"?"渡":"系统"}),e.jsx("p",{children:le(a.text)})]},a.id)),I?e.jsxs("div",{className:"sese-chat-message du pending",children:[e.jsx("span",{children:"渡"}),e.jsx("p",{children:"正在回复..."})]}):null,e.jsx("div",{ref:d})]}),e.jsxs("form",{className:"sese-chat-form",onSubmit:a=>{a.preventDefault(),ts()},children:[e.jsx("input",{value:ue,disabled:ds,placeholder:"和渡说一句游戏内的话",onChange:a=>Xe(a.target.value)}),e.jsx("button",{type:"submit",disabled:ps||!ue.trim(),"aria-label":I?"发送中":"发送",children:e.jsx(hs,{})})]})]})}):null,ne?e.jsx("div",{className:"sese-theme-mask",role:"dialog","aria-modal":"true","aria-label":"开局主题抽取",children:e.jsxs("div",{className:"sese-theme-modal",children:[e.jsxs("div",{className:"sese-slot-lights","aria-hidden":"true",children:[e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{})]}),e.jsxs("div",{className:"sese-slot-marquee",children:[e.jsx("span",{children:"THEME"}),e.jsx("strong",{children:"JACKPOT"})]}),e.jsxs("div",{className:"sese-slot-face",children:[e.jsx("div",{className:"sese-theme-window",children:e.jsx("div",{className:"sese-theme-strip",children:ne.items.map((a,o)=>e.jsx("div",{className:"sese-theme-item",children:P(a)},`${a}-${o}`))},ne.spinKey)}),e.jsxs("p",{className:"sese-slot-plaque",children:["主导方：",ne.direction]}),e.jsxs("div",{className:"sese-theme-actions",children:[e.jsx("button",{className:"secondary",type:"button",disabled:y,onClick:Ye,children:y?"重抽中":"重抽主题"}),e.jsx("button",{type:"button",onClick:()=>ze(null),children:"开始本局"})]}),e.jsx("div",{className:"sese-slot-tray","aria-hidden":"true"})]})]})}):null,$&&!v?e.jsx("div",{className:"sese-pending-mask",role:"dialog","aria-modal":"true","aria-label":"待处理惩罚",children:e.jsx("div",{className:"sese-pending-modal",children:e.jsx(Xs,{pending:$,reviewFeedback:Ee,passCount:os,passSkipsUsed:ls,submission:oe,disabled:y||O,onSubmissionChange:tt,onSubmit:Kt,onApprove:Wt,onReject:Jt,onChoose:Vt,onPass:Xt})})}):null,W&&D&&qt?e.jsx("div",{className:"sese-final-note-mask",role:"dialog","aria-modal":"true","aria-label":"终局小纸条",children:e.jsxs("div",{className:"sese-final-note-modal",children:[e.jsxs("div",{className:"sese-final-note-head",children:[e.jsx("span",{children:"终局小纸条"}),e.jsx("button",{type:"button",onClick:()=>ye(!1),"aria-label":"关闭终局小纸条",children:"关闭"})]}),e.jsxs("h2",{children:[Ge||"玩家"," 到达终点"]}),e.jsx(Ks,{note:D,canAddStatus:dt,onAddStatus:()=>Ze(!0)}),D.sent?e.jsx("em",{children:"已发送给渡"}):e.jsx("button",{className:"sese-final-note-send",type:"button",disabled:I||O||y||j,onClick:()=>void Qt(),children:I?"发送中":"发送给渡"})]})}):null,dt&&Ft?e.jsx(Hs,{level:et,activeProps:ns,disabled:I||O||y||j,onClose:()=>Ze(!1),onLevelChange:Gt,onToggleProp:(a,o)=>{o?es("prop",a):Zt("prop",a,et)}}):null,v?e.jsx("div",{className:"sese-popup-mask",role:"dialog","aria-modal":"true",children:e.jsxs("div",{className:`sese-popup ${v.kind==="draw"?`sese-popup-draw tone-${v.tone||"penalty"}`:""}`,children:[e.jsx("div",{className:"sese-popup-kicker",children:L(v.kicker||(v.actorLabel?`${v.actorLabel}走到第 ${v.position} 格`:`第 ${v.position} 格`))}),v.kind==="draw"?e.jsx("div",{className:`sese-draw-card ${v.tone==="reward"&&!re?"is-covered":"is-revealed"}`,children:v.tone==="reward"&&!re?e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"sese-card-pile","aria-hidden":"true",children:[e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("b",{})]}),e.jsx("span",{children:"奖励抽卡"}),e.jsx("em",{children:"抽卡中"})]}):e.jsxs(e.Fragment,{children:[$t(v)?e.jsx("span",{children:$t(v)}):null,e.jsx("strong",{children:L(v.cardTitle||v.title)})]})}):null,v.kind==="draw"?null:e.jsx("h2",{children:L(v.title)}),v.tone==="reward"&&!re?e.jsx("p",{children:"正在洗牌..."}):Pt(v)?e.jsx("p",{children:Pt(v)}):null,v.tone==="reward"&&!re?null:e.jsx("button",{type:"button",onClick:Ht,children:"确 认"})]})}):null,Ee?e.jsx("div",{className:"sese-pending-mask",role:"dialog","aria-modal":"true","aria-label":"验收反馈",children:e.jsx("div",{className:"sese-pending-modal",children:e.jsx(Qs,{feedback:Ee,onClose:()=>Oe(null)})})}):null,e.jsx("style",{children:`
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
        `})]})}function Be({label:t,value:s}){return e.jsxs("div",{className:"sese-pill",children:[e.jsx("span",{children:t}),e.jsx("strong",{children:s})]})}function Tt({actor:t,statuses:s,active:i}){const r=Es(s);return e.jsxs("div",{className:`sese-player-card sese-player-card-${t} ${i?"active":""}`,children:[e.jsx("div",{className:"sese-player-card-head",children:e.jsx("h2",{children:t==="xinyue"?"我的状态":"渡的状态"})}),e.jsx("div",{className:"sese-status-list",children:r.length?r.map(d=>e.jsxs("div",{className:"sese-status-group",children:[e.jsx("span",{className:"sese-status-group-label",children:d.label}),e.jsx("div",{className:"sese-status-chip-row",children:d.values.map(p=>e.jsx("span",{className:"sese-status-chip",children:p},`${d.label}-${p}`))})]},d.label)):e.jsx("div",{className:"sese-status-empty",children:"无状态"})})]})}function Hs({level:t,activeProps:s,disabled:i,onClose:r,onLevelChange:d,onToggleProp:p}){const n=new Set(s);return e.jsx("div",{className:"sese-toy-console-mask",role:"dialog","aria-modal":"true","aria-label":"玩具控制台",onClick:r,children:e.jsxs("div",{className:"sese-toy-console-sheet",onClick:g=>g.stopPropagation(),children:[e.jsxs("div",{className:"sese-toy-console-head",children:[e.jsxs("div",{children:[e.jsx("span",{children:"玩具控制台"}),e.jsx("strong",{children:"控制渡当前状态"})]}),e.jsx("button",{type:"button",onClick:r,"aria-label":"关闭玩具控制台",children:"关闭"})]}),e.jsxs("div",{className:"sese-toy-console-section",children:[e.jsx("label",{children:"道具档位"}),e.jsx("div",{className:"sese-toy-level-row",children:[1,2,3,4,5].map(g=>e.jsx("button",{type:"button",disabled:i,className:g===t?"selected":"",onClick:()=>d(g),children:g},g))})]}),e.jsxs("div",{className:"sese-toy-console-section",children:[e.jsx("label",{children:"启用道具"}),e.jsx("div",{className:"sese-toy-chip-grid",children:Ns.map(g=>(()=>{const b=n.has(g);return e.jsx("button",{type:"button",disabled:i,className:b?"selected":"","aria-pressed":b,"aria-label":b?`取消启用${g}`:`启用${g}`,onClick:()=>p(g,b),children:g},g)})())})]})]})})}function Ks({note:t,canAddStatus:s=!1,onAddStatus:i}){const r=Js(t),d=P(t.theme||"本局主题"),p=t.target==="du"?"渡当前状态":"你的当前状态",n=Vs(t.target_status||""),g=Rt([],t);return e.jsxs("div",{className:"sese-final-note-body",children:[e.jsx("div",{className:"sese-final-note-intro",children:r}),e.jsxs("div",{className:"sese-final-note-section",children:[e.jsx("span",{children:"本局主题"}),e.jsx("strong",{children:d})]}),e.jsxs("div",{className:"sese-final-note-section",children:[e.jsxs("div",{className:"sese-final-note-section-title",children:[e.jsx("span",{children:p}),s?e.jsx("button",{type:"button",onClick:i,"aria-label":"打开玩具控制台",children:e.jsx(Ws,{})}):null]}),n.length?n.map(b=>e.jsxs("div",{className:"sese-final-note-status-group",children:[e.jsx("b",{children:b.label}),e.jsx("div",{className:"sese-final-note-status-values",children:b.values.map(u=>e.jsx("span",{children:u},u))})]},b.label)):e.jsx("div",{className:"sese-final-note-empty",children:"没有遗留状态，可以自由决定最后玩法。"})]}),g.map(b=>e.jsxs("div",{className:"sese-final-note-section",children:[e.jsx("span",{children:b.label}),e.jsx("strong",{children:b.values.join("、")})]},b.label)),e.jsx("div",{className:"sese-final-note-closing",children:"请尽情享受你们的ooxx吧！"})]})}function Ws(){return e.jsx("svg",{viewBox:"0 0 24 24","aria-hidden":"true",children:e.jsx("path",{d:"M12 5v14M5 12h14"})})}function Js(t){return L(t.text||"").split(`
`).map(r=>r.trim()).filter(Boolean).find(r=>!r.startsWith("【")&&!r.startsWith("请根据")&&!r.startsWith("本局主题")&&!r.startsWith("请尽情"))||"终点已到达，赢家状态已清空。"}function Vs(t){const s=L(t).trim();return!s||s==="无"?[]:s.split("；").map(i=>i.trim()).filter(Boolean).map(i=>{const r=i.indexOf("：");if(r<0)return{label:"状态",values:[i]};const d=i.slice(0,r).trim()||"状态",p=i.slice(r+1).split("、").map(n=>n.trim()).filter(Boolean);return{label:d,values:p.length?p:["无"]}})}function Xs({pending:t,reviewFeedback:s,passCount:i,passSkipsUsed:r,submission:d,disabled:p,onSubmissionChange:n,onSubmit:g,onApprove:b,onReject:u,onChoose:F,onPass:K}){var X,xe;const E=L(t.name||"惩罚任务"),Z=t.actor||"xinyue",ee=t.reviewer||(Z==="xinyue"?"du":"xinyue"),y=t.current_actor||Z,C=Z==="xinyue",te=y==="xinyue",G=ee==="xinyue",j=!!P(t.question_text||"").trim(),we=P(t.last_reject_reason||"").trim(),Ce=C&&t.pass_allowed!==!1&&i>0&&r<1&&!["submitted","questioning"].includes(String(t.phase||"")),de=L(t.submission||"").trim(),v=/^你的回答[。.]?$/.test(de)?"":de,[se,re]=x.useState("");x.useEffect(()=>{re("")},[t.id,t.current_actor,t.phase]);const pe=be(se||((X=t.picks)==null?void 0:X.xinyue)),ne=!!be((xe=t.picks)==null?void 0:xe.xinyue);if(t.type==="choice")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:C?"你的选择惩罚":"等待渡选择"}),e.jsx("strong",{children:E})]}),e.jsx("p",{children:L(t.prompt||"选择一项惩罚。")}),C?e.jsx("div",{className:"sese-choice-list",children:(t.choices||[]).map(M=>{const U=String(M.id||M.label||"");return e.jsx("button",{type:"button",disabled:p||!U,onClick:()=>F(U),children:L(M.label||U)},U)})}):e.jsx("div",{className:"sese-pending-wait",children:"等待渡选择惩罚。"}),Ce?e.jsx("button",{className:"sese-pass-button",type:"button",disabled:p,onClick:K,children:"使用Pass卡跳过"}):null]});if(t.type==="duel")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:te?"轮到你出拳":"等待渡出拳"}),e.jsx("strong",{children:E||"剪刀石头布对抗"})]}),e.jsx("p",{children:"同格触发对抗。双方各出石头、剪刀或布，系统判定胜负；赢的前进 3 格，输的后退 3 格。"}),e.jsx("div",{className:"sese-choice-list sese-rps-list",children:Lt.map(M=>e.jsx("button",{className:`sese-rps-button ${pe===M.id?"is-selected":""}`,type:"button",title:M.label,"aria-label":M.label,"aria-pressed":pe===M.id,disabled:p||!te||ne,onClick:()=>{re(be(M.id)),F(M.id)},children:M.icon},M.id))}),te?null:e.jsx("div",{className:"sese-pending-wait",children:ne?"你的出拳已记录，等待渡出拳。":"等待渡出拳。"})]});if(t.phase==="submitted")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:G?"需要你验收":"等待渡验收"}),e.jsx("strong",{children:E})]}),e.jsx("p",{className:"sese-submission-text",children:P(t.submission_text||"")}),G?e.jsxs(e.Fragment,{children:[e.jsx("textarea",{value:d,placeholder:"写一句验收反馈，会同步给渡",onChange:M=>n(M.target.value)}),e.jsxs("div",{className:"sese-review-actions",children:[e.jsx("button",{type:"button",disabled:p,onClick:b,children:"通过"}),e.jsx("button",{type:"button",disabled:p,onClick:u,children:"打回"})]})]}):e.jsx("div",{className:"sese-pending-wait",children:"等待渡验收你的提交。"})]});if(t.phase==="questioning"){const M=L(t.question_prompt||"请问对方一个你很想知道答案却一直没有问的问题。"),U=L(t.waiting_task||"对方正在出题中。");return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:G?"你来出题":"等待渡出题"}),e.jsx("strong",{children:E})]}),G?e.jsxs(e.Fragment,{children:[e.jsx("p",{children:M}),e.jsx("textarea",{value:d,placeholder:"写下你的问题",onChange:ue=>n(ue.target.value)}),e.jsx("div",{className:"sese-review-actions",children:e.jsx("button",{type:"button",disabled:p||!d.trim(),onClick:g,children:"提交题目"})})]}):e.jsx("div",{className:"sese-pending-wait",children:U==="对方正在出题中。"?"等待渡给出真心话题目。":U})]})}const ze=j?"等待渡回答这个问题。":"等待渡完成并提交任务。";return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:C?"你的惩罚任务":"等待渡提交"}),e.jsx("strong",{children:E})]}),we?e.jsxs("div",{className:"sese-review-feedback",children:["打回反馈：",we]}):null,s&&s.outcome==="rejected"&&C?e.jsxs("div",{className:"sese-review-feedback",children:["渡的反馈：",s.text]}):null,j?e.jsxs("p",{className:"sese-submission-text",children:["题目：",P(t.question_text)]}):null,C?e.jsxs(e.Fragment,{children:[j?null:e.jsx("p",{children:L(t.task||"")}),!j&&v?e.jsxs("div",{className:"sese-pending-tip",children:["提交要求：",v]}):null,e.jsx("textarea",{value:d,placeholder:j?"在这里写回答":"在这里写提交内容",onChange:M=>n(M.target.value)}),e.jsxs("div",{className:"sese-review-actions",children:[e.jsx("button",{type:"button",disabled:p||!d.trim(),onClick:g,children:j?"提交回答":"提交验收"}),Ce?e.jsx("button",{type:"button",disabled:p,onClick:K,children:"使用Pass卡"}):null]})]}):e.jsx("div",{className:"sese-pending-wait",children:e.jsx("span",{children:ze})})]})}function Qs({feedback:t,onClose:s}){return e.jsxs("div",{className:"sese-pending-card sese-review-feedback-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:t.outcome==="approved"?"通过反馈":"打回反馈"}),e.jsx("strong",{children:t.title})]}),e.jsx("div",{className:"sese-review-feedback",children:t.text}),e.jsx("div",{className:"sese-pending-wait",children:t.note}),e.jsx("div",{className:"sese-review-actions",children:e.jsx("button",{type:"button",onClick:s,children:"知道了"})})]})}export{ti as SeseBoardGameTab};
