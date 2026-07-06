import{u as qt,r as p,j as e,C as Ft,M as Yt,S as Ut,b as pt}from"./index-C49F1gpF.js";const at=["xinyue","du"],Ne={xinyue:"我",du:"渡"},Ht={xinyue:0,du:0},Kt=[{id:"scissors",label:"剪刀",icon:"✌️"},{id:"rock",label:"石头",icon:"👊"},{id:"paper",label:"布",icon:"✋"}],Wt={scissors:"scissors",剪刀:"scissors","✌️":"scissors","✌":"scissors",rock:"rock",stone:"rock",石头:"rock",拳头:"rock","👊":"rock",paper:"paper",布:"paper",包袱:"paper","✋":"paper"};function it(t){const s=String(t||"").trim();return s?Wt[s]||s:""}const xt={place:"最终地点",pose:"最终姿势"},Gt=["跳蛋","震动乳夹","震动环","乳夹","锁精环","飞机杯","软绳","手腕绑带","眼罩","口球","春药"],Vt=["跳蛋","震动","按摩棒","飞机杯","吸乳器","吸吮器"];function xe(t){return new Promise(s=>window.setTimeout(s,t))}function z(t){return String(t||"").replace(/小玥/g,"我")}function P(t){return String(t||"").replace(/小玥/g,"你").replace(/(^|[^自])我/g,"$1你")}function ne(t){return String(t||"")}function nt(t,s){return z(t.player_text||t.text||t.error||"").split(/\r?\n/).map(l=>l.trim()).find(l=>l&&!l.startsWith("【")&&!/^(进度|主题|轮到|手牌|我的状态|渡的状态|最终地点|最终姿势|待处理|可用命令)/.test(l))||s}function _(t){return`${t}-${Date.now()}-${Math.random().toString(36).slice(2,8)}`}function je(t,s){const a=Math.floor(Number(t||0));return Math.max(1,Math.min(s,a||1))}function rt(t,s){const a=Math.floor(Number(t||0));return Math.max(0,Math.min(s,a||0))}function Jt(t,s){const a=[];for(let n=1;n<=t;n+=s){const l=Array.from({length:Math.min(s,t-n+1)},(f,r)=>n+r);a.length%2===1&&l.reverse(),a.push(l)}return a.reverse().flat()}function Xt(t,s,a){if(s===1)return"start";if(s===a)return"end";if(!t)return"empty";const n=`${t.kind||""} ${t.slot||""}`.toLowerCase();return/empty/.test(n)?"empty":/finish_self|finish-jump/.test(n)?"finish-jump":/reset/.test(n)?"reset":/swap/.test(n)?"swap":/move|back|forward/.test(n)?"move":/lock|pause|item/.test(n)?"item":/clear/.test(n)?"clear":/extend|time/.test(n)?"time":/limit/.test(n)?"limit":/place/.test(n)?"place":/pose/.test(n)?"pose":/theme/.test(n)?"theme":"task"}function Qt(t){return t==="start"?"🚩":t==="end"?"🏆":t==="place"?"🏫":t==="item"?"🎁":t==="move"?"⏪":t==="reset"?"🔁":t==="finish-jump"?"🏁":t==="swap"?"🔄":t==="clear"?"✨":t==="time"?"⏳":t==="limit"?"🚫":t==="pose"?"◇":t==="theme"?"🚩":t==="task"?"📸":""}function Zt(t,s,a){return s===1?"起点":s===a?"终点":z((t==null?void 0:t.name)||"空")}function es(t){const s=z(t).match(/(我|渡)掷出\s*(\d+)，从\s*(\d+)\s*走到\s*(\d+)/);return s?{actor:s[1]==="渡"?"du":"xinyue",dice:Number(s[2]||1),from:Number(s[3]||0),to:Number(s[4]||0)}:null}function fe(t){return t.replace(/[。.!！?？\s]+$/g,"").trim()}function ts(t,s,a,n){const f=[t,...s].map(h=>h.trim()).filter(Boolean).filter(h=>!/^下一次行动[:：]/.test(h)&&!/^待处理[:：]/.test(h)).join(" ");if(/双方回到起点/.test(f))return"双方回到起点";let r=f.match(/(我|你|渡|对方|双方)?\s*从\s*\d+\s*(前进|后退)\s*(\d+)\s*格(?:到|至)\s*\d+/);return r?`${r[1]||a||"玩家"}${r[2]}了 ${r[3]} 格`:(r=f.match(/(我|你|渡|对方|双方)\s*(前进|后退)\s*(\d+)\s*格/),r?`${r[1]}${r[2]}了 ${r[3]} 格`:(r=f.match(/(我|你|渡|对方)\s*从\s*\d+\s*回到起点/),r?`${r[1]}回到起点`:(r=f.match(/(我|你|渡|对方)\s*从\s*\d+\s*直达终点/),r?`${r[1]}直达终点`:fe(t)===fe(n)?"":t?`触发：${t}`:"")))}function ss(t,s){var m,E;const a=z(t).split(`
`).map(B=>B.trim()).filter(Boolean),n=a.findIndex(B=>/^第\s*\d+\s*格：/.test(B)),l=n>=0?a[n]:"";if(!l)return null;const f=l.match(/^第\s*(\d+)\s*格：([^，。]+)/),r=(f==null?void 0:f[2])||"格子事件",h=((m=l.match(/抽到「([^」]+)」/))==null?void 0:m[1])||"",j=((E=l.match(/获得\s*([^（，。]+)/))==null?void 0:E[1])||"",T=!!(h||j||/抽卡|惩罚任务|选择惩罚/.test(r)),H=/奖励|Pass卡|获得/.test(l)?"reward":/选择/.test(r)?"choice":"penalty",L=Number((f==null?void 0:f[1])||0),g=s==null?void 0:s.actor,S=l.replace(/^第\s*\d+\s*格：/,"").trim(),J=g?Ne[g]:"",O=ts(S,a.slice(n+1,n+4),J,r);return{position:L,actor:g,actorLabel:J,from:s==null?void 0:s.from,to:(s==null?void 0:s.to)??L,title:r,text:l,detail:O,kind:T?"draw":"event",cardTitle:h||j||r,cardType:H==="reward"?"奖励卡":H==="choice"?"选择惩罚":"惩罚任务",tone:H}}function ot(t){const s=P(t.cardType||"").trim(),a=P(t.cardTitle||t.title).trim(),n=P(t.title).trim();return!s||s===a||s===n?"":s}function lt(t){const s=P(t.detail||"").trim(),a=P(t.title).trim();return!s||fe(s.replace(/^触发[:：]\s*/,""))===fe(a)?"":s}function as(t,s,a){const n=z(t).trim();if(!n)return null;const l=Array.isArray(a)?a.map(T=>z(T).trim()).filter(Boolean):[],j=[...[...Array.from(new Set(l)).filter(T=>T!==n)].sort(()=>Math.random()-.5).slice(0,7),n];for(;j.length<8;)j.unshift(n);return{theme:n,direction:z(s||"待定"),items:j,spinKey:`${Date.now()}-${Math.random().toString(36).slice(2,8)}`}}function is(t){const s=String(t.duration_type||"");if(s==="actions"){const a=Math.max(0,Number(t.remaining_actions||0));return t.blocks_action?`停步剩余 ${a} 次`:`剩余 ${a} 次行动`}return s==="minutes"?`${Math.max(1,Number(t.minutes||0))} 分钟`:s==="until_finish"?"到终点前有效":s==="until_clear"?"待解除":""}function ut(t){return!!xt[String(t||"").trim()]}function ft(t,s){const a=new Map;for(const f of t||[]){const r=String((f==null?void 0:f.slot)||"").trim();if(!ut(r))continue;const h=z((f==null?void 0:f.value)||"").trim();h&&a.set(r,h)}const n=z((s==null?void 0:s.final_place)||"").trim(),l=z((s==null?void 0:s.final_pose)||"").trim();return n&&!a.has("place")&&a.set("place",n),l&&!a.has("pose")&&a.set("pose",l),["place","pose"].map(f=>{const r=a.get(f);return r?{label:xt[f]||"终局素材",values:[r]}:null}).filter(f=>!!f)}function ns(t){const s=z(t.label||t.slot||"状态");return t.slot==="prop"||s==="道具"?"道具惩罚":s}function rs(t){const s=z(t.value||""),a=[],n=Math.max(1,Number(t.level||1));t.slot==="prop"&&n>1&&ht(s)&&a.push(`${n}档`);const l=is(t);return l&&a.push(l),s?a.length?`${s}（${a.join("，")}）`:s:a.length?a.join("，"):"状态"}function ht(t){return Vt.some(s=>t.includes(s))}function os(t){const s=new Map;return t.filter(a=>!ut(a.slot)).slice(-6).forEach(a=>{const n=ns(a),l=s.get(n)||[];l.push(rs(a)),s.set(n,l)}),Array.from(s.entries()).map(([a,n])=>({label:a,values:n}))}function ct(t){return(t||[]).some(s=>s.blocks_action&&Number(s.remaining_actions||0)>0)}function ls(t){const s=[/^(我|渡)掷出\s*\d+/,/^第\s*\d+\s*格：/,/^下一次行动：/,/行动权/,/到达终点/,/^新局已开始。?$/,/^本局已结束。?$/];return z(t).split(`
`).map(a=>a.trim()).filter(a=>a&&s.some(n=>n.test(a))).slice(0,4)}function cs(t){return String(t).split(/\r?\n/).map(a=>a.trim()).find(Boolean)==="【掷骰】"}function ds(t){const s=String(t).split(/\r?\n/),a=s.findIndex(h=>h.trim());if(a<0)return{kind:"",body:""};const n=s[a].trim(),l=s.slice(a+1).join(`
`).trim();if(n==="【掷骰】")return{kind:"roll",body:l};if(n==="【提交】")return{kind:"submit",body:l};if(n==="【通过】")return{kind:"approve",body:l};if(n==="【不通过】")return{kind:"reject",body:l};if(n==="【Pass】"||n==="【PASS】"||n==="【使用Pass卡】")return{kind:"pass",body:l};const f=n.match(/^【选择[:：](.+)】$/);if(f)return{kind:"choose",choice:f[1].trim(),body:l};const r=n.match(/^【(?:剪刀石头布|石头剪刀布)[:：](.+)】$/);return r?{kind:"choose",choice:r[1].trim(),body:l}:{kind:"",body:String(t).trim()}}function ps(t,s="rock"){const a=((t==null?void 0:t.choices)||[]).find(n=>(n==null?void 0:n.id)||(n==null?void 0:n.label));return String((a==null?void 0:a.id)||(a==null?void 0:a.label)||s).trim()}function xs(t,s){if(t==="final_note")return"本地预览：终局小纸条收到了。";const a=(s==null?void 0:s.pending_event)||null;if((a==null?void 0:a.type)==="duel"&&a.current_actor==="du")return`【剪刀石头布：石头】
本地预览：我出石头。`;if((a==null?void 0:a.type)==="choice"&&a.actor==="du"){const n=ps(a,"");if(n)return`【选择：${n}】
本地预览：我选这个。`}return(a==null?void 0:a.type)==="review"&&a.reviewer==="du"&&a.phase==="questioning"?`【提交】
本地预览：渡想问你的真心话问题。`:(a==null?void 0:a.type)==="review"&&a.actor==="du"&&a.phase==="assigned"?`【提交】
本地预览：渡已经完成任务，提交给你验收。`:(a==null?void 0:a.type)==="review"&&a.reviewer==="du"&&a.phase==="submitted"?`【通过】
本地预览：这次算你通过。`:gt(s)?`【掷骰】
本地预览：我来掷这一回合。`:"本地预览：我看到了，等你继续行动。"}async function M(t){const s=await pt("/miniapp-api/game-tools/private_board",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:t,save_id:"default"})});if(!(s!=null&&s.ok))throw new Error((s==null?void 0:s.error)||"走格棋命令失败");return s}async function us(t){var a;const s=await pt("/miniapp-api/game-tools/private_board/sync-du",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({save_id:"default",mode:t.mode,message:t.message||"",roll_text:t.rollText||""})});if(!(s!=null&&s.ok))throw new Error((s==null?void 0:s.error)||((a=s==null?void 0:s.wakeup)==null?void 0:a.error)||"游戏内交流失败");return s}function gt(t){return!!(t&&t.turn_actor==="du"&&!t.game_over)}function ks({onBack:t}){var Ee,qe,Fe,Ye,Ue,He,Ke,We,Ge,Ve,Je;const s=qt(),a=p.useRef(null),n=p.useRef(!1),l=p.useRef(null),f=p.useRef(null),[r,h]=p.useState(null),[j,T]=p.useState(Ht),[H,L]=p.useState(1),[g,S]=p.useState(!1),[J,O]=p.useState(!1),[m,E]=p.useState(!1),[B,X]=p.useState(null),[w,W]=p.useState(null),[Q,Z]=p.useState(!0),[V,re]=p.useState(null),[K,C]=p.useState(!1),[q,oe]=p.useState(0),[le,_e]=p.useState(""),[N,ee]=p.useState(!1),[bt,ae]=p.useState(!1),[ze,mt]=p.useState(""),[wt,Ce]=p.useState(!1),[Se,yt]=p.useState(1),[he,$e]=p.useState(""),[Pe,vt]=p.useState([{id:"system-ready",speaker:"system",text:"游戏内交流在这里。渡明确发送【掷骰】时，棋盘才会执行他的行动。"}]),b=(r==null?void 0:r.state)||{},A=Math.max(12,Math.min(80,Number(b.board_size||36))),ge=A<=36?6:8,be=b.turn_actor==="du"?"du":"xinyue",F=!!(b.game_over||r!=null&&r.game_over),ie=be==="du"&&!F,$=b.pending_event||null,te=p.useMemo(()=>{try{return!!new URLSearchParams(window.location.search).has("preview")}catch{return!1}},[]);p.useLayoutEffect(()=>{a.current&&(a.current.scrollTop=0)},[]),p.useEffect(()=>{n.current=K,K&&oe(0)},[K]),p.useEffect(()=>{K&&window.setTimeout(()=>{var i;return(i=l.current)==null?void 0:i.scrollIntoView({block:"end"})},40)},[Pe.length,K,N]),p.useEffect(()=>{if(!w||w.kind!=="draw"||w.tone!=="reward"){Z(!0);return}Z(!1);const i=window.setTimeout(()=>Z(!0),900);return()=>window.clearTimeout(i)},[w]);const k=p.useCallback((i,c=!1)=>{vt(x=>[...x,i]),c&&!n.current&&oe(x=>Math.min(9,x+1))},[]),Te=p.useMemo(()=>{const i=new Map;for(const c of b.cell_events||[]){const x=Number((c==null?void 0:c.position)||0);x>0&&i.set(x,c)}return i},[b.cell_events]),kt=p.useMemo(()=>Jt(A,ge).map(i=>{const c=Te.get(i),x=Xt(c,i,A);return{position:i,event:c,kind:x,icon:Qt(x),name:Zt(c,i,A)}}),[A,ge,Te]),y=p.useCallback(i=>{var c,x,d,u;h(i),T({xinyue:Number(((x=(c=i.state)==null?void 0:c.positions)==null?void 0:x.xinyue)||0),du:Number(((u=(d=i.state)==null?void 0:d.positions)==null?void 0:u.du)||0)})},[]),Me=p.useCallback(async()=>{S(!0);try{const i=await M("status");y(i)}catch(i){s(`加载涩涩走格棋失败：${(i==null?void 0:i.message)||i}`)}finally{S(!1)}},[y,s]);p.useEffect(()=>{Me()},[Me]);const Re=p.useCallback(async i=>{O(!0);for(let c=0;c<12;c+=1)L(Math.floor(Math.random()*6)+1),await xe(58);L(Math.max(1,Math.min(6,i||1))),O(!1)},[]),me=p.useCallback(async(i,c,x,d)=>{const u=Number(x||0),o=Number(d||0);if(u===o){i[c]=o,T({...i}),X(je(o,A)),await xe(120);return}const D=o>u?1:-1;for(let v=u+D;D>0?v<=o:v>=o;v+=D)i[c]=v,T({...i}),X(je(v,A)),await xe(145)},[A]),we=p.useCallback(async()=>{var i,c,x,d,u;if(!(g||m)){S(!0),W(null);try{const o=await M("new_game");L(1),y(o),re(as((c=(i=o.state)==null?void 0:i.theme_profile)==null?void 0:c.theme,(d=(x=o.state)==null?void 0:x.theme_profile)==null?void 0:d.direction_label,(u=o.state)==null?void 0:u.theme_options))}catch(o){s(`开新局失败：${(o==null?void 0:o.message)||o}`)}finally{S(!1)}}},[m,y,g,s]);p.useCallback(async()=>{if(!(g||m)){S(!0);try{const i=await M("end_game");y(i)}catch(i){s(`结束本局失败：${(i==null?void 0:i.message)||i}`)}finally{S(!1)}}},[m,y,g,s]);const ce=p.useCallback(async(i,c)=>{var D;const x=i.trim()||"我看到了。",d=ds(x),u=d.body.trim();u&&k({id:_("du"),speaker:"du",text:u},!0);const o=(c==null?void 0:c.pending_event)||null;try{if((o==null?void 0:o.type)==="duel"&&o.current_actor==="du"){if(d.kind!=="choose"||!d.choice.trim())return;const v=await M(`choose ${d.choice.trim()}`);y(v),k({id:_("system"),speaker:"system",text:"渡已出拳，系统已判定对抗结果。"},!0);return}if((o==null?void 0:o.reviewer)==="du"&&o.type==="review"&&o.phase==="questioning"){if(d.kind!=="submit")return;const v=d.body.trim();if(!v){k({id:_("system"),speaker:"system",text:"渡发了【提交】，但后面没有题目。"},!0);return}const U=await M(`submit ${v}`);y(U),k({id:_("system"),speaker:"system",text:"渡已出题，轮到你回答。"},!0);return}if((o==null?void 0:o.actor)==="du"&&o.type==="review"&&o.phase==="assigned"){if(d.kind!=="submit")return;const v=d.body.trim();if(!v){k({id:_("system"),speaker:"system",text:"渡发了【提交】，但后面没有提交内容。"},!0);return}const U=await M(`submit ${v}`);y(U),k({id:_("system"),speaker:"system",text:"渡已提交惩罚任务，等你验收。"},!0);return}if((o==null?void 0:o.actor)==="du"&&o.type==="choice"){if(d.kind==="pass"){const U=await M("pass");if(y(U),U.ok===!1){k({id:_("system"),speaker:"system",text:nt(U,"渡没有Pass卡，不能跳过。")},!0);return}k({id:_("system"),speaker:"system",text:"渡使用Pass卡跳过了惩罚。"},!0);return}if(d.kind!=="choose"||!d.choice.trim())return;const v=await M(`choose ${d.choice.trim()}`);y(v),k({id:_("system"),speaker:"system",text:"渡已选择惩罚选项。"},!0);return}if((o==null?void 0:o.reviewer)==="du"&&o.type==="review"&&o.phase==="submitted"){if(d.kind==="approve"){const v=await M("approve");y(v),k({id:_("system"),speaker:"system",text:"渡验收通过，棋局继续。"},!0);return}if(d.kind==="reject"){const v=await M(d.body.trim()?`reject ${d.body.trim()}`:"reject");y(v),k({id:_("system"),speaker:"system",text:"渡打回了任务，需要重新提交。"},!0);return}return}gt(c)&&cs(x)&&(await xe(260),k({id:_("system"),speaker:"system",text:"渡发送【掷骰】，已执行他的行动。"},!0),await((D=f.current)==null?void 0:D.call(f,{notifyAfterUserRoll:!1})))}catch(v){k({id:_("system"),speaker:"system",text:`渡的指令执行失败：${String((v==null?void 0:v.message)||v)}`},!0)}},[k,y]),se=p.useCallback(async(i,c)=>{if(!te)return us(i);let x=c,d="";if(i.mode==="final_note"){const o=await M("final_note_sent");x=o.state||x,d=o.player_text||o.text||""}const u=xs(i.mode,x);return{ok:!0,state:x,player_text:d,reply_text:u,reply_preview:u.slice(0,120),wakeup:{reply_text:u,reply_preview:u.slice(0,120)}}},[te]),de=p.useCallback(async(i,c="小玥刚掷完骰子。")=>{var d,u;const x=ne(i.text||i.du_text||i.player_text||"").trim();k({id:_("system"),speaker:"system",text:te?"预览模式：已同步这次棋局。":c.includes("掷")?"已把这次掷骰结果和当前棋局发给渡。":"已把棋局变化发给渡。"},!0),ee(!0);try{const o=await se({mode:"roll_result",message:c,rollText:x},i.state);o.state&&y({ok:!0,state:o.state,player_text:o.player_text||i.player_text||""});const D=ne(o.reply_text||((d=o.wakeup)==null?void 0:d.reply_text)||o.reply_preview||((u=o.wakeup)==null?void 0:u.reply_preview)||"").trim();await ce(D,o.state||i.state)}catch(o){const D=String((o==null?void 0:o.message)||o||"同步失败");k({id:_("system"),speaker:"system",text:`自动同步失败：${D}`},!0),s(`自动同步给渡失败：${D}`)}finally{ee(!1)}},[k,y,te,ce,se,s]),ye=p.useCallback(async(i={})=>{var o,D,v,U,Xe,Qe,Ze;if(g||m||F)return;let c=null;S(!0),E(!0),W(null);const x={xinyue:Number(((o=b.positions)==null?void 0:o.xinyue)||0),du:Number(((D=b.positions)==null?void 0:D.du)||0)},d=b.turn_actor==="du"?"du":"xinyue",u={...x};try{const I=await M("roll"),G=es(I.player_text||"");await Re((G==null?void 0:G.dice)||Math.floor(Math.random()*6)+1),G&&await me(u,G.actor,G.from,G.to);const Et={xinyue:Number(((U=(v=I.state)==null?void 0:v.positions)==null?void 0:U.xinyue)||0),du:Number(((Qe=(Xe=I.state)==null?void 0:Xe.positions)==null?void 0:Qe.du)||0)};for(const ke of at){const tt=Number(u[ke]||0),st=Number(Et[ke]||0);tt!==st&&await me(u,ke,tt,st)}y(I);const et=ss(I.player_text||"",G);et&&W(et),i.notifyAfterUserRoll!==!1&&d==="xinyue"&&!((Ze=I.state)!=null&&Ze.game_over)&&(c=I)}catch(I){s(`掷骰失败：${(I==null?void 0:I.message)||I}`)}finally{S(!1),E(!1),window.setTimeout(()=>X(null),260)}c&&await de(c)},[me,Re,m,y,g,F,de,b.positions,b.turn_actor,s]);p.useEffect(()=>{f.current=ye},[ye]);const Y=p.useCallback(async(i,c={})=>{if(g||m||N||!(r!=null&&r.state))return;let x=null;S(!0),W(null);try{const d=await M(i);if(x=d,y(d),d.ok===!1){s(nt(d,"这次操作没有生效。"));return}$e(""),c.success&&k({id:_("system"),speaker:"system",text:c.success},!0)}catch(d){s(`处理惩罚任务失败：${(d==null?void 0:d.message)||d}`)}finally{S(!1)}x&&c.notify&&await de(x,c.notifyMessage||"小玥处理了涩涩走格棋的惩罚任务。")},[m,k,y,g,N,de,r==null?void 0:r.state,s]),jt=p.useCallback(()=>{const i=he.trim();if(!i){s("先写提交内容。");return}Y(`submit ${i}`,{success:"已提交任务，等渡验收。",notify:!0,notifyMessage:"小玥提交了惩罚任务，请你验收。"})},[Y,he,s]),Nt=p.useCallback(()=>{Y("approve",{success:"你通过了任务，棋局继续。",notify:!0,notifyMessage:"小玥通过了你的惩罚任务。"})},[Y]),_t=p.useCallback(()=>{Y("reject",{success:"你打回了任务，等渡重新提交。",notify:!0,notifyMessage:"小玥打回了你的惩罚任务，请重新提交。"})},[Y]),zt=p.useCallback(i=>{const c=($==null?void 0:$.type)==="duel",x=c&&($==null?void 0:$.current_actor)==="du";Y(`choose ${i}`,{success:x?"已替渡出拳，系统已判定。":c?"已出拳。":"已选择惩罚，棋局继续。",notify:!x,notifyMessage:c?"小玥已在剪刀石头布对抗中出拳，请你发送【剪刀石头布：石头/剪刀/布】。":"小玥处理完选择惩罚，棋局继续。"})},[Y,$==null?void 0:$.current_actor,$==null?void 0:$.type]),Ct=p.useCallback(()=>{Y("pass",{success:"已使用Pass卡跳过惩罚。",notify:!0,notifyMessage:"小玥使用Pass卡跳过了惩罚任务。"})},[Y]),St=p.useCallback(async()=>{var c,x,d;const i=((c=r==null?void 0:r.state)==null?void 0:c.final_note)||null;if(!(N||g||m||!(r!=null&&r.state)||!i||i.sent)){ee(!0);try{const u=await se({mode:"final_note",message:i.text||""},r.state);u.state&&y({ok:!0,state:u.state,player_text:u.player_text||r.player_text||""}),k({id:_("system"),speaker:"system",text:te?"预览模式：终局小纸条已同步。":"终局小纸条已发送给渡。"},!0);const o=ne(u.reply_text||((x=u.wakeup)==null?void 0:x.reply_text)||u.reply_preview||((d=u.wakeup)==null?void 0:d.reply_preview)||"").trim();o&&k({id:_("du"),speaker:"du",text:o},!0),ae(!1)}catch(u){const o=String((u==null?void 0:u.message)||u||"同步失败");k({id:_("system"),speaker:"system",text:`小纸条发送失败：${o}`},!0),s(`发送终局小纸条失败：${o}`)}finally{ee(!1)}}},[m,k,y,g,N,te,r,se,s]),$t=p.useCallback(async(i,c,x=1)=>{if(N||g||m||!(r!=null&&r.state))return;const d=c.replace(/\s+/g," ").trim();if(!d){s("先选要追加的内容。");return}const u=i==="prop"&&ht(d)?` level=${Math.max(1,Math.min(5,Math.round(Number(x)||1)))}`:"";S(!0);try{const o=await M(`append_final_status ${i} ${d}${u}`);y(o),ae(!0),s(`已启用：${d}`)}catch(o){s(`追加失败：${(o==null?void 0:o.message)||o}`)}finally{S(!1)}},[m,y,g,N,r==null?void 0:r.state,s]),Pt=p.useCallback(async(i,c)=>{if(N||g||m||!(r!=null&&r.state))return;const x=c.replace(/\s+/g," ").trim();if(x){S(!0);try{const d=await M(`remove_final_status ${i} ${x}`);y(d),ae(!0),s(`已取消：${x}`)}catch(d){s(`取消失败：${(d==null?void 0:d.message)||d}`)}finally{S(!1)}}},[m,y,g,N,r==null?void 0:r.state,s]),Tt=p.useCallback(async()=>{var x,d;if(N||g||m||!(r!=null&&r.state))return;const i=le.trim();if(!i)return;const c={id:_("me"),speaker:"xinyue",text:i};_e(""),k(c),ee(!0);try{const u=await se({mode:"chat",message:i},r.state);u.state&&y({ok:!0,state:u.state,player_text:u.player_text||r.player_text||""});const o=ne(u.reply_text||((x=u.wakeup)==null?void 0:x.reply_text)||u.reply_preview||((d=u.wakeup)==null?void 0:d.reply_preview)||"").trim();await ce(o,u.state||r.state)}catch(u){const o=String((u==null?void 0:u.message)||u||"同步失败");k({id:_("system"),speaker:"system",text:`交流失败：${o}`}),s(`游戏内交流失败：${o}`)}finally{ee(!1)}},[m,k,y,g,le,N,r,ce,se,s]),Mt=z(((Ee=b.theme_profile)==null?void 0:Ee.theme)||"未触发"),Rt=z(((qe=b.theme_profile)==null?void 0:qe.direction_label)||"待定"),Dt=rt((Fe=b.positions)==null?void 0:Fe.xinyue,A),At=rt((Ye=b.positions)==null?void 0:Ye.du,A),ve=b.winner?Ne[b.winner]:"",De=ls((r==null?void 0:r.player_text)||""),R=b.final_note||null,Ae=ft(b.final_note_items||[],R),pe=String((R==null?void 0:R.id)||`${b.winner||""}-${b.updated_at||""}`),Le=!!(F&&b.winner==="xinyue"&&(!R||R.target==="du")&&!(R!=null&&R.sent)),Lt=(((Ue=b.statuses)==null?void 0:Ue.du)||[]).filter(i=>i.slot==="prop").map(i=>z(i.value||""));p.useEffect(()=>{!F||!R||!pe||ze!==pe&&(mt(pe),ae(!0))},[R,pe,ze,F]);const Bt=Math.max(0,Number(((Ke=(He=b.hands)==null?void 0:He.xinyue)==null?void 0:Ke.pass)||0)),It=Math.max(0,Number(b.pass_skips_used||0)),Be={xinyue:ct((We=b.statuses)==null?void 0:We.xinyue),du:ct((Ge=b.statuses)==null?void 0:Ge.du)},Ie=ie&&Be.du&&!$,Ot=g||m||N||!(r!=null&&r.state)||!!$||ie&&!Ie,Oe=N||g||m||!(r!=null&&r.state);return e.jsxs("div",{className:"sese-game",ref:a,children:[e.jsxs("div",{className:"sese-header",children:[e.jsx("button",{className:"sese-back",type:"button",onClick:t,"aria-label":"返回游戏",children:e.jsx(Ft,{})}),e.jsxs("button",{className:"sese-chat-entry",type:"button",onClick:()=>C(!0),"aria-label":"游戏内交流",children:[e.jsx(Yt,{}),q?e.jsx("span",{children:q}):null]}),e.jsx("div",{className:"sese-header-title",children:"涩涩走格棋"}),e.jsxs("div",{className:"sese-game-status-bar",children:[e.jsx(ue,{label:"主题",value:Mt}),e.jsx(ue,{label:"主导方",value:Rt}),e.jsx(ue,{label:"我 进度",value:`${String(Dt).padStart(2,"0")} / ${A}`}),e.jsx(ue,{label:"渡 进度",value:`${String(At).padStart(2,"0")} / ${A}`}),e.jsx("div",{className:"sese-turn-indicator",children:F&&ve?`${ve} 到达终点`:ie?"等待 渡 行动...":"轮到 我 行动"})]})]}),e.jsx("section",{className:"sese-board-container","aria-label":"走格棋盘",children:e.jsx("div",{className:"sese-board",style:{gridTemplateColumns:`repeat(${ge}, minmax(0, 1fr))`},children:kt.map(i=>{const c=at.filter(x=>je(j[x],A)===i.position);return e.jsxs("div",{className:`sese-tile sese-tile-${i.kind} ${B===i.position?"is-active":""}`,children:[e.jsx("div",{className:"sese-tile-number",children:i.position}),e.jsx("div",{className:"sese-tile-icon",children:i.icon}),e.jsx("div",{className:"sese-tile-name",children:i.name}),e.jsx("div",{className:"sese-piece-stack",children:c.map(x=>e.jsx("span",{className:`sese-piece ${x==="xinyue"?"sese-piece-me":"sese-piece-du"} ${Be[x]?"paused":""}`,children:Ne[x]},x))})]},i.position)})})}),e.jsxs("section",{className:"sese-controls",children:[e.jsxs("div",{className:"sese-player-states",children:[e.jsx(dt,{actor:"xinyue",statuses:((Ve=b.statuses)==null?void 0:Ve.xinyue)||[],active:be==="xinyue"}),e.jsx(dt,{actor:"du",statuses:((Je=b.statuses)==null?void 0:Je.du)||[],active:be==="du"})]}),Ae.length?e.jsx("div",{className:"sese-final-pose-panel",children:Ae.map(i=>e.jsxs("div",{className:"sese-final-material-row",children:[e.jsx("span",{children:i.label}),e.jsx("strong",{children:i.values.join("、")})]},i.label))}):null,e.jsxs("div",{className:"sese-action-area",children:[e.jsx("div",{className:`sese-dice ${J?"rolling":""}`,"aria-label":`骰子 ${H}`,children:H}),e.jsx("button",{className:"sese-roll-button",type:"button",disabled:Ot,onClick:F?we:()=>void ye({notifyAfterUserRoll:!0}),children:F?"开新局":$?"先处理任务":Ie?"处理停步":ie?"等渡掷骰":g||m?"移动中":N?"等渡回应":"掷骰子"}),e.jsx("button",{className:"sese-restart-button",type:"button",disabled:g||m||N,onClick:we,children:"重开"})]}),e.jsx("div",{className:"sese-history",children:De.length?`最近：${De[0]}`:"最近：等待第一次掷骰"})]}),K?e.jsx("div",{className:"sese-chat-mask",role:"dialog","aria-modal":"true","aria-label":"游戏内交流",onClick:()=>C(!1),children:e.jsxs("div",{className:"sese-chat-panel",onClick:i=>i.stopPropagation(),children:[e.jsxs("div",{className:"sese-chat-head",children:[e.jsxs("div",{children:[e.jsx("strong",{children:"游戏内交流"}),e.jsx("span",{children:ie?"等待渡发送【掷骰】":"当前轮到你行动"})]}),e.jsx("button",{type:"button",onClick:()=>C(!1),"aria-label":"关闭交流",children:"×"})]}),e.jsxs("div",{className:"sese-chat-list",children:[Pe.map(i=>e.jsxs("div",{className:`sese-chat-message ${i.speaker}`,children:[e.jsx("span",{children:i.speaker==="xinyue"?"我":i.speaker==="du"?"渡":"系统"}),e.jsx("p",{children:ne(i.text)})]},i.id)),N?e.jsxs("div",{className:"sese-chat-message du pending",children:[e.jsx("span",{children:"渡"}),e.jsx("p",{children:"正在回复..."})]}):null,e.jsx("div",{ref:l})]}),e.jsxs("form",{className:"sese-chat-form",onSubmit:i=>{i.preventDefault(),Tt()},children:[e.jsx("input",{value:le,disabled:Oe,placeholder:"和渡说一句游戏内的话",onChange:i=>_e(i.target.value)}),e.jsx("button",{type:"submit",disabled:Oe||!le.trim(),"aria-label":N?"发送中":"发送",children:e.jsx(Ut,{})})]})]})}):null,V?e.jsx("div",{className:"sese-theme-mask",role:"dialog","aria-modal":"true","aria-label":"开局主题抽取",children:e.jsxs("div",{className:"sese-theme-modal",children:[e.jsxs("div",{className:"sese-slot-lights","aria-hidden":"true",children:[e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{})]}),e.jsxs("div",{className:"sese-slot-marquee",children:[e.jsx("span",{children:"THEME"}),e.jsx("strong",{children:"JACKPOT"})]}),e.jsxs("div",{className:"sese-slot-face",children:[e.jsx("div",{className:"sese-theme-window",children:e.jsx("div",{className:"sese-theme-strip",children:V.items.map((i,c)=>e.jsx("div",{className:"sese-theme-item",children:z(i)},`${i}-${c}`))},V.spinKey)}),e.jsxs("p",{className:"sese-slot-plaque",children:["主导方：",V.direction]}),e.jsxs("div",{className:"sese-theme-actions",children:[e.jsx("button",{className:"secondary",type:"button",disabled:g,onClick:we,children:g?"重抽中":"重抽主题"}),e.jsx("button",{type:"button",onClick:()=>re(null),children:"开始本局"})]}),e.jsx("div",{className:"sese-slot-tray","aria-hidden":"true"})]})]})}):null,$&&!w?e.jsx("div",{className:"sese-pending-mask",role:"dialog","aria-modal":"true","aria-label":"待处理惩罚",children:e.jsx("div",{className:"sese-pending-modal",children:e.jsx(ws,{pending:$,passCount:Bt,passSkipsUsed:It,submission:he,disabled:g||m||N,onSubmissionChange:$e,onSubmit:jt,onApprove:Nt,onReject:_t,onChoose:zt,onPass:Ct})})}):null,F&&R&&bt?e.jsx("div",{className:"sese-final-note-mask",role:"dialog","aria-modal":"true","aria-label":"终局小纸条",children:e.jsxs("div",{className:"sese-final-note-modal",children:[e.jsxs("div",{className:"sese-final-note-head",children:[e.jsx("span",{children:"终局小纸条"}),e.jsx("button",{type:"button",onClick:()=>ae(!1),"aria-label":"关闭终局小纸条",children:"关闭"})]}),e.jsxs("h2",{children:[ve||"玩家"," 到达终点"]}),e.jsx(hs,{note:R,canAddStatus:Le,onAddStatus:()=>Ce(!0)}),R.sent?e.jsx("em",{children:"已发送给渡"}):e.jsx("button",{className:"sese-final-note-send",type:"button",disabled:N||g||m,onClick:()=>void St(),children:N?"发送中":"发送给渡"})]})}):null,Le&&wt?e.jsx(fs,{level:Se,activeProps:Lt,disabled:N||g||m,onClose:()=>Ce(!1),onLevelChange:yt,onToggleProp:(i,c)=>{c?Pt("prop",i):$t("prop",i,Se)}}):null,w?e.jsx("div",{className:"sese-popup-mask",role:"dialog","aria-modal":"true",children:e.jsxs("div",{className:`sese-popup ${w.kind==="draw"?`sese-popup-draw tone-${w.tone||"penalty"}`:""}`,children:[e.jsx("div",{className:"sese-popup-kicker",children:P(w.actorLabel?`${w.actorLabel}走到第 ${w.position} 格`:`第 ${w.position} 格`)}),w.kind==="draw"?e.jsx("div",{className:`sese-draw-card ${w.tone==="reward"&&!Q?"is-covered":"is-revealed"}`,children:w.tone==="reward"&&!Q?e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"sese-card-pile","aria-hidden":"true",children:[e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("i",{}),e.jsx("b",{})]}),e.jsx("span",{children:"奖励抽卡"}),e.jsx("em",{children:"抽卡中"})]}):e.jsxs(e.Fragment,{children:[ot(w)?e.jsx("span",{children:ot(w)}):null,e.jsx("strong",{children:P(w.cardTitle||w.title)})]})}):null,w.kind==="draw"?null:e.jsx("h2",{children:P(w.title)}),w.tone==="reward"&&!Q?e.jsx("p",{children:"正在洗牌..."}):lt(w)?e.jsx("p",{children:lt(w)}):null,w.tone==="reward"&&!Q?null:e.jsx("button",{type:"button",onClick:()=>W(null),children:"确 认"})]})}):null,e.jsx("style",{children:`
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
        `})]})}function ue({label:t,value:s}){return e.jsxs("div",{className:"sese-pill",children:[e.jsx("span",{children:t}),e.jsx("strong",{children:s})]})}function dt({actor:t,statuses:s,active:a}){const n=os(s);return e.jsxs("div",{className:`sese-player-card sese-player-card-${t} ${a?"active":""}`,children:[e.jsx("div",{className:"sese-player-card-head",children:e.jsx("h2",{children:t==="xinyue"?"我的状态":"渡的状态"})}),e.jsx("div",{className:"sese-status-list",children:n.length?n.map(l=>e.jsxs("div",{className:"sese-status-group",children:[e.jsx("span",{className:"sese-status-group-label",children:l.label}),e.jsx("div",{className:"sese-status-chip-row",children:l.values.map(f=>e.jsx("span",{className:"sese-status-chip",children:f},`${l.label}-${f}`))})]},l.label)):e.jsx("div",{className:"sese-status-empty",children:"无状态"})})]})}function fs({level:t,activeProps:s,disabled:a,onClose:n,onLevelChange:l,onToggleProp:f}){const r=new Set(s);return e.jsx("div",{className:"sese-toy-console-mask",role:"dialog","aria-modal":"true","aria-label":"玩具控制台",onClick:n,children:e.jsxs("div",{className:"sese-toy-console-sheet",onClick:h=>h.stopPropagation(),children:[e.jsxs("div",{className:"sese-toy-console-head",children:[e.jsxs("div",{children:[e.jsx("span",{children:"玩具控制台"}),e.jsx("strong",{children:"控制渡当前状态"})]}),e.jsx("button",{type:"button",onClick:n,"aria-label":"关闭玩具控制台",children:"关闭"})]}),e.jsxs("div",{className:"sese-toy-console-section",children:[e.jsx("label",{children:"道具档位"}),e.jsx("div",{className:"sese-toy-level-row",children:[1,2,3,4,5].map(h=>e.jsx("button",{type:"button",disabled:a,className:h===t?"selected":"",onClick:()=>l(h),children:h},h))})]}),e.jsxs("div",{className:"sese-toy-console-section",children:[e.jsx("label",{children:"启用道具"}),e.jsx("div",{className:"sese-toy-chip-grid",children:Gt.map(h=>(()=>{const j=r.has(h);return e.jsx("button",{type:"button",disabled:a,className:j?"selected":"","aria-pressed":j,"aria-label":j?`取消启用${h}`:`启用${h}`,onClick:()=>f(h,j),children:h},h)})())})]})]})})}function hs({note:t,canAddStatus:s=!1,onAddStatus:a}){const n=bs(t),l=z(t.theme||"本局主题"),f=t.target==="du"?"渡当前状态":"你的当前状态",r=ms(t.target_status||""),h=ft([],t);return e.jsxs("div",{className:"sese-final-note-body",children:[e.jsx("div",{className:"sese-final-note-intro",children:n}),e.jsxs("div",{className:"sese-final-note-section",children:[e.jsx("span",{children:"本局主题"}),e.jsx("strong",{children:l})]}),e.jsxs("div",{className:"sese-final-note-section",children:[e.jsxs("div",{className:"sese-final-note-section-title",children:[e.jsx("span",{children:f}),s?e.jsx("button",{type:"button",onClick:a,"aria-label":"打开玩具控制台",children:e.jsx(gs,{})}):null]}),r.length?r.map(j=>e.jsxs("div",{className:"sese-final-note-status-group",children:[e.jsx("b",{children:j.label}),e.jsx("div",{className:"sese-final-note-status-values",children:j.values.map(T=>e.jsx("span",{children:T},T))})]},j.label)):e.jsx("div",{className:"sese-final-note-empty",children:"没有遗留状态，可以自由决定最后玩法。"})]}),h.map(j=>e.jsxs("div",{className:"sese-final-note-section",children:[e.jsx("span",{children:j.label}),e.jsx("strong",{children:j.values.join("、")})]},j.label)),e.jsx("div",{className:"sese-final-note-closing",children:"请尽情享受你们的ooxx吧！"})]})}function gs(){return e.jsx("svg",{viewBox:"0 0 24 24","aria-hidden":"true",children:e.jsx("path",{d:"M12 5v14M5 12h14"})})}function bs(t){return P(t.text||"").split(`
`).map(n=>n.trim()).filter(Boolean).find(n=>!n.startsWith("【")&&!n.startsWith("请根据")&&!n.startsWith("本局主题")&&!n.startsWith("请尽情"))||"终点已到达，赢家状态已清空。"}function ms(t){const s=P(t).trim();return!s||s==="无"?[]:s.split("；").map(a=>a.trim()).filter(Boolean).map(a=>{const n=a.indexOf("：");if(n<0)return{label:"状态",values:[a]};const l=a.slice(0,n).trim()||"状态",f=a.slice(n+1).split("、").map(r=>r.trim()).filter(Boolean);return{label:l,values:f.length?f:["无"]}})}function ws({pending:t,passCount:s,passSkipsUsed:a,submission:n,disabled:l,onSubmissionChange:f,onSubmit:r,onApprove:h,onReject:j,onChoose:T,onPass:H}){var K;const L=P(t.name||"惩罚任务"),g=t.actor||"xinyue",S=t.reviewer||(g==="xinyue"?"du":"xinyue"),J=t.current_actor||g,O=g==="xinyue",m=J==="xinyue",E=S==="xinyue",B=!!z(t.question_text||"").trim(),X=O&&t.pass_allowed!==!1&&s>0&&a<1&&!["submitted","questioning"].includes(String(t.phase||"")),w=P(t.submission||"").trim(),W=/^你的回答[。.]?$/.test(w)?"":w,[Q,Z]=p.useState("");p.useEffect(()=>{Z("")},[t.id,t.current_actor,t.phase]);const V=it(Q||((K=t.picks)==null?void 0:K.xinyue));if(t.type==="choice")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:O?"你的选择惩罚":"等待渡选择"}),e.jsx("strong",{children:L})]}),e.jsx("p",{children:P(t.prompt||"选择一项惩罚。")}),O?e.jsx("div",{className:"sese-choice-list",children:(t.choices||[]).map(C=>{const q=String(C.id||C.label||"");return e.jsx("button",{type:"button",disabled:l||!q,onClick:()=>T(q),children:P(C.label||q)},q)})}):e.jsx("div",{className:"sese-pending-wait",children:"等待渡选择惩罚。"}),X?e.jsx("button",{className:"sese-pass-button",type:"button",disabled:l,onClick:H,children:"使用Pass卡跳过"}):null]});if(t.type==="duel")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:m?"轮到你出拳":"等待渡出拳"}),e.jsx("strong",{children:L||"剪刀石头布对抗"})]}),e.jsx("p",{children:"同格触发对抗。双方各出石头、剪刀或布，系统判定胜负；赢的前进 3 格，输的后退 3 格。"}),e.jsx("div",{className:"sese-choice-list sese-rps-list",children:Kt.map(C=>e.jsx("button",{className:`sese-rps-button ${V===C.id?"is-selected":""}`,type:"button",title:C.label,"aria-label":C.label,"aria-pressed":V===C.id,disabled:l,onClick:()=>{Z(it(C.id)),T(C.id)},children:C.icon},C.id))})]});if(t.phase==="submitted")return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:E?"需要你验收":"等待渡验收"}),e.jsx("strong",{children:L})]}),e.jsx("p",{className:"sese-submission-text",children:z(t.submission_text||"")}),E?e.jsxs("div",{className:"sese-review-actions",children:[e.jsx("button",{type:"button",disabled:l,onClick:h,children:"通过"}),e.jsx("button",{type:"button",disabled:l,onClick:j,children:"打回"})]}):e.jsx("div",{className:"sese-pending-wait",children:"等待渡验收你的提交。"})]});if(t.phase==="questioning"){const C=P(t.question_prompt||"请问对方一个你很想知道答案却一直没有问的问题。"),q=P(t.waiting_task||"对方正在出题中。");return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:E?"你来出题":"等待渡出题"}),e.jsx("strong",{children:L})]}),E?e.jsxs(e.Fragment,{children:[e.jsx("p",{children:C}),e.jsx("textarea",{value:n,disabled:l,placeholder:"写下你的问题",onChange:oe=>f(oe.target.value)}),e.jsx("div",{className:"sese-review-actions",children:e.jsx("button",{type:"button",disabled:l||!n.trim(),onClick:r,children:"提交题目"})})]}):e.jsx("div",{className:"sese-pending-wait",children:q==="对方正在出题中。"?"等待渡给出真心话题目。":q})]})}const re=B?"等待渡回答这个问题。":"等待渡完成并提交任务。";return e.jsxs("div",{className:"sese-pending-card",children:[e.jsxs("div",{className:"sese-pending-head",children:[e.jsx("span",{children:O?"你的惩罚任务":"等待渡提交"}),e.jsx("strong",{children:L})]}),B?e.jsxs("p",{className:"sese-submission-text",children:["题目：",z(t.question_text)]}):null,O?e.jsxs(e.Fragment,{children:[B?null:e.jsx("p",{children:P(t.task||"")}),!B&&W?e.jsxs("div",{className:"sese-pending-tip",children:["提交要求：",W]}):null,e.jsx("textarea",{value:n,disabled:l,placeholder:B?"在这里写回答":"在这里写提交内容",onChange:C=>f(C.target.value)}),e.jsxs("div",{className:"sese-review-actions",children:[e.jsx("button",{type:"button",disabled:l||!n.trim(),onClick:r,children:B?"提交回答":"提交验收"}),X?e.jsx("button",{type:"button",disabled:l,onClick:H,children:"使用Pass卡"}):null]})]}):e.jsx("div",{className:"sese-pending-wait",children:e.jsx("span",{children:re})})]})}export{ks as SeseBoardGameTab};
