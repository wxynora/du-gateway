import{r as _,j as e,C as Ct,b as si,A as sa}from"./index-DU83jYqu.js";const ri="default",ci="du-gateway:captivity-simulator:route:v1",ra=[{key:"health",label:"健康"},{key:"stamina",label:"体力"},{key:"cleanliness",label:"清洁"},{key:"shame",label:"羞耻"},{key:"intimacy",label:"依赖"}],ct=[{id:"feeding",label:"喂食"},{id:"cleaning",label:"清洗"},{id:"training",label:"服从调教"},{id:"reward",label:"奖励取悦"},{id:"punishment",label:"违令惩戒"},{id:"comfort",label:"事后安抚"},{id:"rest",label:"看管休息"},{id:"check",label:"私密检查"},{id:"room_search",label:"突击搜查"}],mt={reward:[{id:"caress_reward",label:"抚摸奖励"},{id:"kiss_reward",label:"亲吻奖励"},{id:"masturbation_permission",label:"允许自慰"},{id:"orgasm_permission",label:"允许高潮"},{id:"toy_reward",label:"玩具奖励"},{id:"freedom_reward",label:"增加自由"}],punishment:[{id:"impact_discipline",label:"拍打惩戒"},{id:"bondage_discipline",label:"束缚惩戒"},{id:"orgasm_denial",label:"禁止高潮"},{id:"toy_discipline",label:"玩具惩戒"},{id:"confiscation",label:"没收物品"},{id:"interrogation",label:"审问"},{id:"rule_escalation",label:"规则加码"}],comfort:[{id:"embrace",label:"拥抱"},{id:"kiss",label:"亲吻"},{id:"body_care",label:"身体清理"},{id:"massage",label:"按摩"},{id:"feeding_care",label:"喂水喂食"},{id:"cuddle_rest",label:"抱着休息"},{id:"partial_release",label:"解除部分束缚"}],rest:[{id:"forced_nap",label:"强制午睡"},{id:"cuddle_sleep",label:"抱睡"},{id:"supervised_sleep",label:"陪睡"},{id:"restrained_rest",label:"固定姿势休息"},{id:"quiet_time",label:"安静待着"}],check:[{id:"body_check",label:"身体检查"},{id:"mark_check",label:"痕迹检查"},{id:"sensitivity_check",label:"敏感反应检查"},{id:"restraint_check",label:"束缚状态检查"},{id:"chastity_check",label:"贞操装置检查"}],room_search:[{id:"bed_search",label:"翻查床铺"},{id:"hidden_item_search",label:"搜查私藏物"},{id:"body_search",label:"搜身"},{id:"key_trace_check",label:"检查钥匙痕迹"},{id:"search_confiscation",label:"没收物品"},{id:"on_site_questioning",label:"现场盘问"}]},ut=[{id:"obedience_commands",label:"口令服从"},{id:"position_training",label:"姿势训练"},{id:"bondage_training",label:"束缚训练"},{id:"sensory_deprivation",label:"感官控制"},{id:"impact_play",label:"拍打调教"},{id:"wax_play",label:"滴蜡调教"},{id:"clamp_play",label:"夹具调教"},{id:"toy_training",label:"玩具调教"},{id:"anal_training",label:"后庭调教"},{id:"chastity_control",label:"贞操控制"},{id:"orgasm_control",label:"高潮控制"},{id:"forced_orgasm",label:"强制高潮"},{id:"masturbation_control",label:"自慰控制"},{id:"humiliation_play",label:"羞耻调教"},{id:"exposure_training",label:"展示训练"},{id:"pet_play",label:"小狗身份建立"},{id:"leash_training",label:"牵引训练"},{id:"service_training",label:"服务训练"},{id:"inspection_training",label:"检查调教"},{id:"pet_position_wait",label:"定点等候"},{id:"pet_crawl_training",label:"爬行训练"},{id:"pet_feeding",label:"宠物式喂食"},{id:"pet_permission",label:"按铃求许可"},{id:"pet_voice_training",label:"叫声与回应"},{id:"toilet_control",label:"如厕控制"},{id:"assisted_urination",label:"抱着把尿"}],oi=new Set(["toilet_control","assisted_urination"]),ca=new Set(["masturbation_permission","orgasm_permission","toy_reward","impact_discipline","bondage_discipline","orgasm_denial","toy_discipline","sensitivity_check","chastity_check","body_search"]),It=[{id:"light",label:"低"},{id:"medium",label:"中"},{id:"heavy",label:"高"}],li=[{id:"training",label:"调教"},{id:"sex",label:"性交"}],pi=[{id:"catch",label:"抓现行"},{id:"confiscate",label:"没收物品"},{id:"interrupt",label:"打断带走"},{id:"ambush",label:"突袭"},{id:"question",label:"审问"},{id:"command_stop",label:"命令停下"},{id:"reward",label:"奖励"},{id:"punishment",label:"惩罚"}],$t=[{id:"training",label:"调教"},{id:"sex",label:"性行为"}],ot=[{id:"toy",label:"跳蛋",category:"玩具",contexts:["training:toy_training","training:orgasm_control","training:forced_orgasm","training:masturbation_control","content:toy_reward","content:toy_discipline","modifier:sex"]},{id:"vibrating_wand",label:"振动棒",category:"玩具",contexts:["training:toy_training","training:orgasm_control","training:forced_orgasm","training:masturbation_control","content:toy_reward","content:toy_discipline","modifier:sex"]},{id:"dildo",label:"假阳具",category:"玩具",contexts:["training:toy_training","training:forced_orgasm","content:toy_reward","content:toy_discipline","modifier:sex"]},{id:"remote_control",label:"遥控器",category:"玩具",contexts:["training:toy_training","training:orgasm_control","training:forced_orgasm","training:masturbation_control","content:toy_reward","content:toy_discipline"]},{id:"lubricant",label:"润滑剂",category:"辅助",contexts:["training:toy_training","training:anal_training","training:forced_orgasm","modifier:sex"]},{id:"collar",label:"项圈",category:"束缚",contexts:["training:obedience_commands","training:position_training","training:pet_play","training:pet_position_wait","training:pet_crawl_training","training:pet_feeding","training:pet_permission","training:pet_voice_training","training:leash_training","training:service_training","content:bondage_discipline","content:restrained_rest","modifier:sex"]},{id:"leash",label:"牵引绳",category:"束缚",contexts:["training:position_training","training:pet_play","training:pet_position_wait","training:pet_crawl_training","training:leash_training","training:service_training","content:bondage_discipline"]},{id:"handcuffs",label:"手铐",category:"束缚",contexts:["training:bondage_training","training:position_training","training:sensory_deprivation","training:exposure_training","training:toilet_control","training:assisted_urination","content:bondage_discipline","content:restrained_rest","modifier:sex"]},{id:"ankle_cuffs",label:"脚铐",category:"束缚",contexts:["training:bondage_training","training:position_training","training:exposure_training","training:toilet_control","training:assisted_urination","content:bondage_discipline","content:restrained_rest","modifier:sex"]},{id:"rope",label:"绳子",category:"束缚",contexts:["training:bondage_training","training:position_training","training:exposure_training","training:toilet_control","training:assisted_urination","content:bondage_discipline","content:restrained_rest","modifier:sex"]},{id:"bondage_tape",label:"束缚胶带",category:"束缚",contexts:["training:bondage_training","training:sensory_deprivation","training:toilet_control","training:assisted_urination","content:bondage_discipline","content:restrained_rest","modifier:sex"]},{id:"spreader_bar",label:"分腿杆",category:"束缚",contexts:["training:bondage_training","training:position_training","training:exposure_training","training:toilet_control","training:assisted_urination","content:bondage_discipline","modifier:sex"]},{id:"blindfold",label:"眼罩",category:"感官",contexts:["training:sensory_deprivation","training:inspection_training","content:sensitivity_check","modifier:sex"]},{id:"gag",label:"口球",category:"束缚",contexts:["training:obedience_commands","training:sensory_deprivation","training:humiliation_play","training:pet_play","training:pet_voice_training","modifier:sex"]},{id:"muzzle",label:"口套",category:"束缚",contexts:["training:obedience_commands","training:humiliation_play","training:pet_play","training:pet_voice_training"]},{id:"whip",label:"软鞭",category:"训诫",contexts:["training:impact_play","content:impact_discipline"]},{id:"flogger",label:"多尾鞭",category:"训诫",contexts:["training:impact_play","content:impact_discipline"]},{id:"paddle",label:"拍板",category:"训诫",contexts:["training:impact_play","content:impact_discipline"]},{id:"cane",label:"藤条",category:"训诫",contexts:["training:impact_play","content:impact_discipline"]},{id:"ruler",label:"戒尺",category:"训诫",contexts:["training:impact_play","content:impact_discipline"]},{id:"candle",label:"蜡烛",category:"感官",contexts:["training:wax_play","modifier:sex"]},{id:"ice_cube",label:"冰块",category:"感官",contexts:["training:sensory_deprivation","training:inspection_training","content:sensitivity_check","modifier:sex"]},{id:"pinwheel",label:"滚轮",category:"感官",contexts:["training:sensory_deprivation","training:inspection_training","content:sensitivity_check","modifier:sex"]},{id:"feather",label:"羽毛",category:"感官",contexts:["training:sensory_deprivation","training:inspection_training","content:sensitivity_check","modifier:sex"]},{id:"nipple_clamps",label:"乳夹",category:"夹具",contexts:["training:clamp_play","training:inspection_training","content:sensitivity_check","modifier:sex"]},{id:"suction_cups",label:"乳吸",category:"夹具",contexts:["training:clamp_play","training:inspection_training","content:sensitivity_check","modifier:sex"]},{id:"chastity_ring",label:"贞操锁",category:"控制",contexts:["training:chastity_control","training:orgasm_control","content:chastity_check"]},{id:"anal_plug",label:"肛塞",category:"后庭",contexts:["training:anal_training","training:toy_training","modifier:sex"]},{id:"anal_beads",label:"拉珠",category:"后庭",contexts:["training:anal_training","training:toy_training","modifier:sex"]},{id:"feeding_spoon",label:"喂食器具",category:"喂食",contexts:["action:feeding","content:feeding_care","training:pet_feeding"]}],De=[{id:"book",label:"书",usage:"解锁看书"},{id:"switch",label:"Switch",usage:"解锁玩游戏"},{id:"notebook",label:"日记本",usage:"解锁写日记"},{id:"music_player",label:"音乐播放器",usage:"解锁听音乐"},{id:"tablet",label:"平板",usage:"解锁看视频"},{id:"night_light",label:"小夜灯",usage:"改善睡觉"},{id:"pillow",label:"抱枕",usage:"改善休息"},{id:"call_bell",label:"呼叫铃",usage:"按下后替你发声"}],di=[{id:"cook",label:"自己做"},{id:"takeout",label:"点外卖"}],mi=[{id:"none",label:"不加料"},{id:"body_fluid",label:"体液"},{id:"fictional_sleep",label:"安眠"},{id:"fictional_arousal",label:"助兴"}],oa=[{id:"none",label:"不额外喂水"},{id:"glass",label:"喂一杯水"},{id:"lots",label:"喂很多水"}],la=[{id:"accept",label:"接受"},{id:"refuse",label:"拒绝"},{id:"silent",label:"沉默"},{id:"bargain",label:"讨价还价"},{id:"tease",label:"嘴硬"}],Ot=["平静","黏人","害羞","闹脾气","亢奋","疲惫","烦躁","委屈","低落","抗拒"],ui=["早上","中午","傍晚"],pa={sleep:"老实睡觉",self_touch:"自慰",read:"看书",game:"玩游戏",listen_music:"听音乐",watch_video:"看视频",search_exit:"偷偷找出口",hide_item:"藏东西",check_key:"检查钥匙",diary:"写私密日记",blind_spot:"去监控盲区",ring_bell:"按铃",pet_wait:"在指定位置等候"},da={feeding:"这一段从食物开始。端进房间的东西，由你决定。",cleaning:"水声会盖过房间里一部分动静，也会洗掉一部分痕迹。",training:"这一段会留下新的口令、姿势或规矩。",reward:"顺从会得到怎样的回应，由你决定。",punishment:"这次违令会被怎样记住，由你决定。",comfort:"强硬的部分结束后，要不要收一收力度，也由你决定。",rest:"门不会打开，但这一段时间可以暂时安静下来。",check:"灯会亮得更清楚，遗漏的痕迹也会被重新确认。",room_search:"床铺、角落和私藏物都会在这一段被重新翻查。"},ma={sleep:"房间里的灯还亮着，你决定先躺下。",self_touch:"你确认了一下门外的动静，准备把这一小段时间留给自己。",read:"书页会在安静的房间里发出很轻的声音。",game:"屏幕亮起后，房间里终于会多出一点别的光。",listen_music:"耳机里的声音会暂时盖过门外的动静。",watch_video:"平板的光会在黑下来的房间里格外明显。",search_exit:"你没有立刻靠近门，只是先重新打量整个房间。",hide_item:"你把选中的东西攥在手里，开始寻找不会被轻易发现的位置。",check_key:"你记得钥匙的位置，今晚可以再确认一次。",diary:"有些话不能说出口，但可以先写进纸页里。",blind_spot:"你开始留意镜头转开的方向和停留的时间。",ring_bell:"手指已经放在按钮上，按下去之后就不能假装没有发生。",pet_wait:"你回到被指定的位置，安静等着门外的动静。"},ua={sleep:"画面里的人很早就躺下了，之后只剩偶尔翻身的动静。",self_touch:"被角和呼吸的起伏持续了一阵，监控完整留下了这段动静。",read:"画面里的人靠着床头翻书，偶尔会停在同一页很久。",game:"掌机的屏幕一直亮着，按键声在安静的房间里断断续续。",listen_music:"画面里的人戴着耳机，几乎没有注意门外的声音。",watch_video:"平板的光映在脸上，画面明暗跟着视频不断变化。",search_exit:"画面里的人沿着房间边缘慢慢移动，反复检查几个位置。",hide_item:"画面里的人背对镜头停留了一会，随后若无其事地回到原处。",check_key:"视线在钥匙和门锁之间来回停留，手伸出去后又收了回来。",diary:"画面里的人低头写了很久，写完后立刻把本子合上。",blind_spot:"人影从画面边缘消失了一阵，回来时位置已经变了。",ring_bell:"呼叫铃亮了一次，按下按钮的人没有立刻把手收回去。",pet_wait:"画面里的人回到指定位置，之后一直没有离开。"},Qt={door_lock:"画面里的人贴近门锁，手指沿着锁孔和门缝检查了几遍。",window:"窗边的人影停了很久，似乎在确认窗扣和外面的高度。",room_route:"画面里的人反复走过同一段路线，像是在默记距离。",outside_sound:"人影贴在门边没有动作，只是在听外面的脚步声。",paper_note:"一张折过的纸被迅速塞进了镜头不容易看清的位置。",small_item:"一个小东西从手心消失了，之后没有再出现在画面里。",snack:"画面里的人把一点食物藏了起来，动作很快。",improvised_tool:"手里的临时工具被试了几次，最后藏进房间角落。",confirm_location:"视线多次落在钥匙原本的位置，没有伸手。",test_reach:"手臂朝钥匙伸过去，试到最远距离后才收回来。",match_lock:"画面里的人先看钥匙，又逐一观察房间里的锁。",leave_untouched:"钥匙始终没有被碰过，但那道视线停留了很久。",record_day:"日记本写满了一页，内容从白天一直记到现在。",write_feelings:"写字的人几次停笔，最后还是把那一页写完了。",record_rules:"几条现有规矩被逐条写下，又重新排列了一遍。",escape_plan:"纸页上画出了简略路线，写完后立刻被合上。",camera_angle:"画面里的人一直抬头观察镜头转向，像在计算角度。",stay_hidden:"监控有一段时间只拍到空房间，直到人影重新出现。",move_item:"镜头边缘的物品被悄悄换了位置。",test_duration:"人影数次进出盲区，每次停留都比上一次更久。"},ga=["sleep","self_touch","search_exit","hide_item","check_key","blind_spot"],gi={search_exit:[{id:"door_lock",label:"检查门锁"},{id:"window",label:"检查窗户"},{id:"room_route",label:"记住房间路线"},{id:"outside_sound",label:"听门外动静"}],hide_item:[{id:"paper_note",label:"藏纸条"},{id:"small_item",label:"藏小物件"},{id:"snack",label:"藏一点零食"},{id:"improvised_tool",label:"藏临时工具"}],check_key:[{id:"confirm_location",label:"确认钥匙位置"},{id:"test_reach",label:"试着够到钥匙"},{id:"match_lock",label:"观察对应的锁"},{id:"leave_untouched",label:"只看不碰"}],diary:[{id:"record_day",label:"记录今天发生的事"},{id:"write_feelings",label:"写下此刻心情"},{id:"record_rules",label:"整理现有规则"},{id:"escape_plan",label:"写下逃跑计划"}],blind_spot:[{id:"camera_angle",label:"观察镜头转向"},{id:"stay_hidden",label:"躲一会"},{id:"move_item",label:"偷偷移动东西"},{id:"test_duration",label:"试探能停留多久"}]},ha=[{id:"silent",label:"看见但不说"},{id:"review_later",label:"明天再处理"},{id:"intervene",label:"当场介入"}],xa=[{id:"escape",label:"尝试逃跑"},{id:"stay",label:"老实待着"}],nt=[{prompt:"真的要逃跑吗？",title:"钥匙就在手边。",text:"只要伸手就能拿到。现在停下，还什么都没有发生。",continueLabel:"伸手拿钥匙",stayLabel:"老实待着",abortChoice:"abort_before_key"},{prompt:"还要继续吗？",title:"钥匙已经拿到了。",text:"门锁就在前面。现在把钥匙放回去，也许还能装作只是看了一眼。",continueLabel:"走到门边",stayLabel:"把钥匙放回去",abortChoice:"abort_with_key"},{prompt:"要推开门吗？",title:"门已经开了一条缝。",text:"都走到这里了，还要回头吗？",continueLabel:"推门逃跑",stayLabel:"停下",abortChoice:"abort_at_door"}],hi={escape:"尝试逃跑",stay:"老实待着",abort_before_key:"逃跑未遂：临时退缩",abort_with_key:"逃跑未遂：拿到钥匙后退缩",abort_at_door:"逃跑未遂：开门后退缩",observe:"观察",take_key:"拿钥匙",probe:"试探",leave_trace:"试探"},ze=[{id:"double_lock",label:"加装双重门锁"},{id:"key_isolation",label:"禁止接触钥匙和门锁"},{id:"movement_limit",label:"限制离开指定区域"},{id:"daily_search",label:"每日搜查"},{id:"monitoring_upgrade",label:"加强全天监控"},{id:"item_restriction",label:"限制持有物品"},{id:"permission_required",label:"行动前必须得到许可"},{id:"restraint_required",label:"独处时保持束缚"}],st=[{id:"punishment",label:"惩戒"},{id:"search_confiscation",label:"搜查没收"},{id:"monitoring_upgrade",label:"加强监控"},{id:"movement_restriction",label:"限制行动"},{id:"training",label:"调教"},{id:"aftercare",label:"事后照料"}],Mt=[{id:"entry",label:"玄关",bait:"备用钥匙压在玄关地垫下面"},{id:"living",label:"客厅",bait:"备用钥匙藏在客厅茶几抽屉里"},{id:"bedroom",label:"卧室",bait:"备用钥匙放在卧室床头柜后面"},{id:"bathroom",label:"浴室",bait:"备用钥匙贴在浴室洗手台底下"},{id:"study",label:"书房",bait:"备用钥匙夹在书房第二层书架里"},{id:"kitchen",label:"厨房",bait:"备用钥匙藏在厨房调料架后面"},{id:"storage",label:"储物间",bait:"备用钥匙挂在储物间门后的旧挂钩上"},{id:"balcony",label:"阳台",bait:"备用钥匙压在阳台花盆底下"}];function Rt(t){var i;return((i=Mt.find(a=>a.id===t))==null?void 0:i.bait)||Mt[0].bait}function Tt(){return[{action:"feeding",intensity:"medium",modifiers:[],tools:[],contents:[],trainingContents:[],line:"",feedingSource:"cook",feedingAdditive:"none"},{action:"cleaning",intensity:"light",modifiers:[],tools:[],contents:[],trainingContents:[],line:"",feedingSource:"cook",feedingAdditive:"none"},{action:"training",intensity:"medium",modifiers:[],tools:["collar"],contents:[],trainingContents:["obedience_commands"],line:"",feedingSource:"cook",feedingAdditive:"none"}]}function va(t){const i=mt[t]||[];return i.length?[i[0].id]:[]}function Me(t){const i=Number(t);return Number.isFinite(i)?Math.max(0,Math.min(100,Math.round(i))):0}function W(t,i){var s;const a=String(i||"");return((s=t.find(o=>o.id===a))==null?void 0:s.label)||a||"未设置"}function le(t){return W(ct,t)}function _a(t){return W(It,t)}function xi(t){const i=String(t||"");return pa[i]||i||"未设置"}function ya(t){return String(t||"")==="process"?"":String(t||"")==="escape"?"逃跑":W(li,t)}function vi(t){const i=String(t||""),a=Object.values(mt).flat();return W(a,i)}function lt(t){return W(ut,t)}function _i(t){return(t||[]).map(ya).filter(Boolean)}function yi(t){return W(pi,t)}function fi(t){return W($t,t)}function fa(t){const i=String(t||"");return hi[i]||i||"未记录"}function ei(t){const i=Number(t.day||1),a="phase"in t?t.phase:"night";return`第 ${i} 天 / ${a==="night"?"夜间":"白天"}`}function ti(t){var l;const i=t.action_label||xi(t.action)||le(t.action)||"夜间行动",a=((l=t.night_detail)==null?void 0:l.label)||t.detail_label,s="line"in t?ye(t.line):"",o=a?`${i}（${a}）`:i;return s?`${o}：${s}`:o}function Et(t){var o;const a=String(((o=t.night_detail)==null?void 0:o.id)||"");if(a&&Qt[a])return Qt[a];const s=String(t.action||"");return ua[s]||"监控保留了这一段画面，房间里的动静已经写进记录。"}function ba(t,i,a,s=[]){const o=Me(t.health),l=Me(t.stamina),r=Me(t.cleanliness),d=Me(t.shame),u=Me(t.intimacy);if(o<30)return a==="captor"?"状态读数不太好，今天的安排需要留意身体承受程度。":"身体的不适已经很明显，连安静待着都很难完全忽略。";if(l<20)return a==="captor"?"体力读数已经接近下限，高强度安排暂时不合适。":"四肢有些发沉，稍微动一下都比平时更费力。";if(r<25)return a==="captor"?"监控里还能看见没处理干净的痕迹。":"身上还留着没有处理干净的痕迹，很难不去在意。";if(s.some(k=>k.id==="pet_identity_active"))return a==="captor"?"项圈和定点规矩仍在生效，监控会继续记录是否遵守。":"项圈和现有规矩仍在提醒你，房间里哪些位置属于你。";if(d>=70)return a==="captor"?"羞耻反馈已经很明显，简单的注视也足够留下影响。":"只是想起之前发生的事，脸上就又开始发热。";if(u>=70)return a==="captor"?"依赖已经变得稳定，短暂离开也会引起明显反应。":"房间安静得太久时，你会下意识去听门外有没有脚步声。";const f=a==="captor"?{黏人:"监控里的注意力总会被门外动静带走，等待已经变得明显。",害羞:"对方仍会下意识避开镜头，尤其是在意识到有人可能正看着时。",闹脾气:"监控里的动作比平时更重，情绪没有被藏得很好。",亢奋:"状态迟迟没有安静下来，夜间反应可能会更明显。",疲惫:"动作和反应都慢了下来，现在最需要的是恢复体力。",烦躁:"对方频繁留意房间里的声音，安静没有带来放松。",委屈:"有些话没有直接说出来，但情绪已经留在动作里。",低落:"监控里的活动明显变少，房间显得比平时更空。",抗拒:"戒备仍然很明显，现有安排还没有让对方放松下来。"}:{黏人:"门外一点轻微的动静，都会让注意力立刻转过去。",害羞:"视线落到监控指示灯上时，还是会本能地移开。",闹脾气:"房间里的每一样东西看起来都比平时更碍眼。",亢奋:"身体还没有完全安静下来，连时间都像过得更慢。",疲惫:"现在最明显的感觉只剩下累。",烦躁:"安静没有带来放松，反而让每一点声音都更清楚。",委屈:"有些话堵在心里，没有找到合适的时机说出来。",低落:"房间似乎比平时更空，也更安静。",抗拒:"现有的安排没有让戒备真正放下来。"};return i&&f[i]?f[i]:a==="captor"?"状态读数暂时平稳，今天仍可以按原定节奏继续。":"房间暂时很安静，身体也没有新的不适。"}function ja(t,i){var s;return((s={7:["房间里的生活开始有了固定的节奏。","监控和事件记录已经积累了整整一周。"],15:["日历已经翻过一半，有些声音和规矩变得越来越熟悉。","三十天已经过半，许多反应不再需要反复确认。"],23:["日历只剩下最后几页，房间里的时间却没有因此变快。","记录进入最后阶段，之前留下的选择正在彼此叠加。"],30:["第三十天到了，门外的脚步声和往常听起来不太一样。","最后一天的画面已经亮起，所有记录都在等待收束。"]}[t])==null?void 0:s[i==="captor"?1:0])||""}function Na(t,i,a){const s=String((i==null?void 0:i.type)||""),o=String((i==null?void 0:i.actor)||"");return s==="advance_action"?"这一段已经收进记录，下一段安排还没有开始。":s==="action_response"?a==="captive"?"你的回应会和这一段一起留下。":"这项安排已经送达，正在等对方回应。":s==="reaction_choice"?"具体经过已经结束，此刻的心情会成为这一段的结尾。":s==="process_write"||s==="process_reaction_write"?"事件素材已经送出，具体经过仍在另一边继续。":s==="monitor_gate"?"夜间记录已经封存，监控另一端还没有作出选择。":s==="monitor_handle"?"这段监控已经打开，接下来只差如何处理。":s==="day_plan_choice"?a==="captor"?"新一天还没有安排，三个时段都在等你落笔。":"新一天的安排还没有送到，房间暂时没有新的动静。":o==="du"?"这一步已经交到另一边，房间暂时安静下来。":String(t.phase||"")==="night"?"白天的记录已经结束，夜间仍会留下自己的痕迹。":""}function wa(t){if(t.error)return"这次交接没有完成，已经完成的本地记录仍然保留着。";const i=String(t.title||"");return i.includes("同步")?"这段记录已经送出，另一边正在决定接下来怎么做。":i.includes("保存")||i.includes("封存")||i.includes("记录")?"刚才的选择正在写进今天的记录。":i.includes("监控")?"监控画面正在解锁，夜里的动静很快就会重新出现。":i.includes("进入")||i.includes("推进")?"这一段已经结束，时间正在向下一格移动。":"当前操作正在写入本地规则状态。"}function pt(t){return W(ot,t)}function ka(t,i){const a=String(i||"");return a?t==="source"?W(di,a):t==="additive"?W(mi,a):t==="water"?W(oa,a):a:""}function Sa(t,i){const a=String(t.phase||"day");if(t.game_over||a==="ending")return"结局";if(a==="night")return"晚上";const s=Math.max(1,Number(t.day_action_limit||3)),o=Number((i==null?void 0:i.slot)||0),l=Number(t.day_action_count||0),r=o>0?o:Math.min(l+1,s);return ui[r-1]||`第 ${r} 段`}function M(t){const i=String(t||"");return i?`"${i.replace(/(["\\$`])/g,"\\$1")}"`:'""'}function ye(t){return String(t||"").trim()}function Ca(t){const i=String(t||"");return i==="du"?"渡":i==="xinyue"?"我":i||"SYSTEM"}function At(t){var a,s,o;const i=String(((a=t==null?void 0:t.captor_view)==null?void 0:a.route)||((s=t==null?void 0:t.captive_view)==null?void 0:s.route)||((o=t==null?void 0:t.state)==null?void 0:o.route)||"");return i==="capture_du"||i==="captured_by_du"?i:""}function Lt(t){return At(t)==="capture_du"?"captor":"captive"}function ee(t){var a;return t?Lt(t)==="captor"?(a=t.captor_view)!=null&&a.route?t.captor_view:t.captive_view||t.state||{}:t.captive_view||t.state||{}:{}}function dt(t){if(!t)return"";const i=ye(t.process_text);return i?[t.id,t.day,t.slot,t.phase,t.action,t.process_saved_at||t.resolved_at||"",i.length].filter(a=>a!=null&&String(a)!=="").join(":"):""}function Ta(t){var l;const i=ee(t),a=new Set,s=(l=i.pending_event)==null?void 0:l.event,o=dt(s);return o&&a.add(o),(i.event_log||[]).forEach(r=>{const d=dt(r);d&&a.add(d)}),a}function Ea(t,i){var r,d,u;const a=ee(t),s=Ta(i),o=(r=a.pending_event)==null?void 0:r.event,l=[o,...(a.event_log||[]).slice().reverse()].filter(Boolean);for(const b of l){const j=dt(b);if(!j||s.has(j))continue;const f=dt(o),k=String(((d=a.pending_event)==null?void 0:d.type)||""),S=String(((u=a.pending_event)==null?void 0:u.actor)||"");return{event:b,text:ye(b.process_text),moodRequired:Lt(t)==="captive"&&k==="reaction_choice"&&S!=="du"&&f===j}}return null}function Ma(){return""}function Ra(){return""}function Ia(){return""}function $a(){return""}function Oa(){return""}function ii(){return{ok:!0,captor_view:{route:"capture_du",route_label:"囚禁方",viewer:"captor",current_day:7,total_days:30,day_action_count:0,day_action_limit:3,phase:"day",captive:"du",captive_name:"被囚禁方",captor:"xinyue",stats:{health:80,stamina:68,cleanliness:72,shame:34,intimacy:41},mood:"害羞",intensity_cap:"heavy",scene_copy:{key:"preview-captor-morning",kicker:"DAY 07 / 早上",title:"早上",body:"监控画面安静地亮着。渡还在房间里，今天要怎样度过，由你安排。",tone:"day"},pending_event:null,event_log:[{id:"preview-monitor-bell",day:4,slot:0,phase:"night",action:"ring_bell",action_label:"按铃",monitor:{viewed:!0,style:"full",strategy:"intervene"}},{id:"preview-monitor-door-lock",day:5,slot:0,phase:"night",action:"search_exit",action_label:"偷偷找出口",night_detail:{id:"door_lock",label:"检查门锁"},monitor:{viewed:!0,style:"occasional",strategy:"review_later"}},{id:"preview-monitor-game",day:6,slot:0,phase:"night",action:"game",action_label:"玩游戏",monitor:{viewed:!0,style:"full",strategy:"silent"}}],day_plan:[],inventory:{}},player_text:"本地预览：配置今日安排。"}}function ai(){return{ok:!0,captive_view:{route:"captured_by_du",route_label:"被囚禁方",viewer:"captive",current_day:7,total_days:30,day_action_count:3,day_action_limit:3,phase:"night",captive:"xinyue",captive_name:"被囚禁方",stats:{health:27,stamina:18,cleanliness:16,shame:48,intimacy:41},mood:"害羞",status_flags:[{id:"low_health",label:"需要照料",prompt:"健康偏低，高强度行动暂不可选。"},{id:"low_stamina",label:"体力不足",prompt:"体力不足，高强度行动暂不可选。"},{id:"low_cleanliness",label:"建议清洗",prompt:"清洁度偏低，建议优先安排清洗。"},{id:"heightened_shame",label:"羞耻升高",prompt:"羞耻反馈已经更明显。"},{id:"pet_identity_active",label:"小狗身份中",prompt:"当前处于小狗身份。现有规矩：佩戴项圈并接受小狗身份、在指定位置等候。"}],intensity_cap:"medium",scene_copy:{key:"preview-captive-night",kicker:"DAY 07 / 晚上",title:"晚上",body:"白天的三次安排已经结束。房间重新安静下来，接下来这段时间暂时属于你。",tone:"night"},pending_event:null,event_log:[],inventory:{notebook:!0,book:!0,switch:!0,call_bell:!0},available_night_actions:["sleep","self_touch","read","game","search_exit","hide_item","check_key","diary","blind_spot","ring_bell","pet_wait"]},player_text:"本地预览：夜间自由行动。"}}function bi(t="captive"){const i=t==="captor"?"capture_du":"captured_by_du",a=t==="captor"?"du":"xinyue",o={route:i,route_label:t==="captor"?"囚禁方":"被囚禁方",viewer:t,current_day:12,total_days:30,day_action_count:0,day_action_limit:3,phase:"day",captive:a,captive_name:"被囚禁方",captor:t==="captor"?"xinyue":"du",stats:{health:76,stamina:61,cleanliness:70,shame:42,intimacy:47},mood:"紧张",scene_copy:{key:`preview-escape-${t}`,kicker:"SPECIAL DAY",title:"今天没有平常的安排",body:"门外安静得太久了。一个本不该出现的机会被留在房间里，今天只需要决定要不要伸手。",tone:"special"},pending_event:t==="captor"?{id:"preview-recapture-rules-after-process",type:"recapture_rules_choice",day:12,slot:0,actor:"xinyue",captive:"du",phase:"waiting_recapture_rules",source_event_id:"preview-du-recapture-process",available_rules:ze.map(l=>l.id),event:{id:"preview-du-recapture-process",day:12,slot:0,phase:"day",route:"capture_du",action:"escape_choice",action_label:"逃跑失败：被抓回",tags:["preview","escape","recapture","rules_reset"],escape:{choice:"escape",choice_label:"尝试逃跑"},process_text:"渡写下的抓回经过已经保存。",process_saved_at:"preview-local"}}:{id:"preview-escape-choice",type:"escape_choice",day:12,slot:0,actor:a,captive:a,phase:"waiting_escape_choice",hint:"渡今天有事出去了。",bait:"备用钥匙压在玄关地垫下面。",required_directive:"resolve_escape_choice escape|stay"},event_log:[],inventory:{book:!0,notebook:!0,call_bell:!0}};return{ok:!0,captive_view:{...o,viewer:"captive"},captor_view:{...o,viewer:"captor"},player_text:"本地预览：逃跑诱导选择。"}}function Aa(t="captive"){const i=t==="captor"?"capture_du":"captured_by_du",a=t==="captor"?"余生":"长夜",o={route:i,route_label:t==="captor"?"囚禁方":"被囚禁方",viewer:t,current_day:30,total_days:30,day_action_count:3,day_action_limit:3,phase:"ending",captive:t==="captor"?"du":"xinyue",captive_name:"被囚禁方",captor:t==="captor"?"xinyue":"du",stats:{health:74,stamina:58,cleanliness:70,shame:62,intimacy:79},pending_event:null,event_log:[],ending_state:"ending_ready_to_notify",ending_title:a,ending_text:t==="captor"?"第三十天结束时，你和渡照旧完成进食、清洁、夜间安排与监控，没有人为这场生活按下结束。日历翻到第三十一天，你照常推门进来，渡也照常望向你。余下的日期仍是一片空白。":"第三十天夜里，渡照常看过监控记录，带着你最常用的礼物回到房间。你们已经熟悉彼此的回应与沉默。灯熄灭后房门依旧关闭，你在黑暗里握住他的手；这一夜不会在清晨结束。",ending_notified_at:"",game_over:!0,result:"ending_ready_to_notify"};return{ok:!0,game_over:!0,state:o,captive_view:{...o,viewer:"captive"},captor_view:{...o,viewer:"captor"},player_text:`本地预览：结局「${a}」。`}}function La(t,i="captive",a="escape"){const s=ee(t||bi(i)),l=a==="escape"?"尝试逃跑":`逃跑未遂：${{abort_before_key:"临时退缩",abort_with_key:"拿到钥匙后退缩",abort_at_door:"开门后退缩"}[a]||"中途退缩"}`,r=a==="abort_before_key"?"手已经伸向了钥匙，却在碰到它之前停了下来。":a==="abort_with_key"?"钥匙已经被握进手里，又被迟疑着放回了原处。":a==="abort_at_door"?"门已经开了一条缝，最后却还是停在了门边。":"门把手刚被压下去，玄关外便传来了停在近处的脚步声。",d={id:"preview-escape-recapture",day:12,slot:0,phase:"day",route:i==="captor"?"capture_du":"captured_by_du",action:"escape_choice",action_label:a==="escape"?"逃跑失败：被抓回":l,intensity:"medium",modifiers:["escape"],tools:[],contents:[],training_contents:[],tags:["preview","escape",`escape:${a}`,"recapture","rules_reset"],feeding:{},effects:{health:0,stamina:-8,cleanliness:0,shame:5,intimacy:0},escape:{choice:a,choice_label:l},recapture_rules:i==="captive"?{rule_ids:["double_lock","key_isolation"],rule_labels:["加装双重门锁","禁止接触钥匙和门锁"]}:void 0,requires_process:!0,process_saved_at:"preview-local",process_text:[r,"","备用钥匙是真的，留下的空隙也是真的；但从点下尝试逃跑的那一刻起，一举一动就已经落进了观察范围里。停下来并没有让这次试探消失。","","门重新在身后落锁，钥匙也被收走。房间恢复安静，只剩下逃跑失败后尚未说出口的新规矩。"].join(`
`)},u={...s,stats:{...s.stats,stamina:53,shame:47},pending_event:{id:"preview-escape-reaction",type:"reaction_choice",day:12,slot:0,actor:i==="captor"?"du":"xinyue",captive:i==="captor"?"du":"xinyue",phase:"waiting_reaction",event:d}};return{payload:{ok:!0,captive_view:u,captor_view:{...u,viewer:"captor"},player_text:"本地预览：逃跑失败，抓回事件已经写入。"},review:{event:d,text:ye(d.process_text),moodRequired:i==="captive"}}}function ji(t){const i=t==="captor"?"capture_du":"captured_by_du",a={id:`preview-process-${t}`,day:7,slot:2,phase:"day",route:i,action:"training",action_label:"服从调教",intensity:"medium",line:"今晚的规则重新确认一遍。",modifiers:[],contents:[],training_contents:["obedience_commands","leash_training"],tools:["collar"],tags:["preview","process"],feeding:{},effects:{health:0,stamina:-3,cleanliness:0,shame:4,intimacy:2},requires_process:!0,process_saved_at:"preview-local",process_text:["渡写下了这一段事件经过。","","房间里的灯只留了一盏，所有动作都被压得很慢。对方先确认了今天的规则，又把项圈扣回原位，让这次训练从一句简短的回应开始。","","中途没有切走，也没有跳过过程；细节被完整记录下来，等你看完以后，再决定这件事结束后留下来的心情。"].join(`
`),action_response:{response:"accept",response_label:"接受",mood:"害羞",line:"嗯。"}},s={route:i,route_label:t==="captor"?"囚禁方":"被囚禁方",viewer:t,current_day:7,total_days:30,day_action_count:1,day_action_limit:3,phase:"day",captive:t==="captor"?"du":"xinyue",captive_name:"被囚禁方",captor:t==="captor"?"xinyue":"du",stats:{health:80,stamina:68,cleanliness:72,shame:34,intimacy:41},mood:"害羞",pending_event:t==="captive"?{id:"preview-pending-reaction",type:"reaction_choice",day:7,slot:2,actor:"xinyue",captive:"xinyue",action:"training",phase:"waiting_reaction",event:a}:{id:"preview-pending-advance",type:"advance_action",day:7,slot:2,actor:"xinyue",captive:"du",action:"training",phase:"waiting_advance",event:a},event_log:t==="captor"?[a]:[]};return{payload:t==="captor"?{ok:!0,captor_view:s,captive_view:{...s,viewer:"captive"},player_text:"本地预览：事件经过阅读页。"}:{ok:!0,captive_view:s,captor_view:{...s,viewer:"captor"},player_text:"本地预览：事件经过阅读页。"},review:{event:a,text:ye(a.process_text),moodRequired:t==="captive"}}}function Pa(t,i,a){const s=ji(t),o=ee(s.payload),l={...s.review.event,post_reaction:t==="captive"?{mood:i,line:a}:s.review.event.post_reaction,mood_after:t==="captive"?i:s.review.event.mood_after},r={id:`preview-next-${t}`,day:7,slot:3,phase:"day",action:"reward",action_label:"奖励取悦",intensity:"light",line:"第三段安排已经接上来了。",modifiers:[],tools:[],contents:["caress_reward"],training_contents:[],tags:["preview","next_action"],feeding:{},effects:{health:1,stamina:-1,cleanliness:0,shame:1,intimacy:1},requires_process:!1},u={...o,day_action_count:t==="captive"?2:1,pending_event:t==="captive"?{id:"preview-next-action",type:"action_response",day:7,slot:3,actor:"xinyue",captive:"xinyue",action:"reward",phase:"waiting_response",event:r}:{id:"preview-next-advance",type:"advance_action",day:7,slot:2,actor:"xinyue",captive:"du",phase:"waiting_advance_action",required_directive:"advance_day_action"},event_log:[l],mood:t==="captive"?i:o.mood,mood_line:t==="captive"?a:o.mood_line};return t==="captor"?{ok:!0,captor_view:u,captive_view:{...u,viewer:"captive"},player_text:"本地预览：事件已保存，等待推进下一段行动。"}:{ok:!0,captive_view:u,captor_view:{...u,viewer:"captor"},player_text:"本地预览：事件已保存，下一段行动已经接上。"}}function Fa(){try{const t=window.localStorage.getItem(ci);return t==="capture_du"||t==="captured_by_du"?t:""}catch{return""}}function ni(t){try{window.localStorage.setItem(ci,t)}catch{}}function za(t){var a;if(!t)return!1;if(Number(t.current_day||1)>1||Number(t.day_action_count||0)>0||String(t.phase||"day")!=="day"||t.game_over||t.ending_state||(t.event_log||[]).length>0||(t.day_plan||[]).length>0)return!0;const i=String(((a=t.pending_event)==null?void 0:a.type)||"");return!!(i&&i!=="day_plan_choice")}function Da(t){var o;const i=At(t),a=Fa();if(i&&a===i)return!0;const s=(((o=t.captor_view)==null?void 0:o.route)==="capture_du"?t.captor_view:t.captive_view||t.state)||{};return za(s)}const Ni=/\b(?:action|intensity|intent|modifiers|tools|contents|training_contents|source|additive|response|mood|line|day|hint|bait)=/,wi={day_plan_choice:"安排今天的三段行动。",action_response:"选择你的回应和此刻心情。",process_write:"等待渡补写这一段过程。",process_reaction_write:"等待渡写下回应、过程和心情。",reaction_choice:"过程已经归档，选择此刻心情。",advance_action:"这一段已结束，可以推进下一段行动。",night_action_choice:"选择今晚的自由行动。",bell_voice_reveal:"按铃记录已生成，语音铃正在第一次播放。",item_secret_reveal:"物品里藏着的彩蛋第一次出现了。",monitor_gate:"夜间行动已封存，等待是否打开监控。",monitor_handle:"监控内容已打开，选择处理方式。",escape_choice:"逃跑机会出现了，等待你的选择。",return_action_choice:"被囚禁方选择了老实待着，等待囚禁方回来后决定一个行为。",recapture_rules_choice:"抓回经过已保存，等待重新立规矩。",recapture_followup_choice:"新规矩已生效，等待选择后续处理。",recapture_rules_review:"查看抓回后生效的新规矩。",ending_ready_to_notify:"结局已收录，等待同步给渡。"},rt={advance_day_action:"推进下一段行动",advance_action:"推进下一段行动",next_action:"推进下一段行动",plan_day:"安排今天的三段行动",day_action:"确定回来后的行为",submit_process:"保存事件经过",choose_mood:"记录此刻心情",ack_bell_voice:"结束首次播放页",ack_item_secret:"看完物品彩蛋",view_monitor:"查看夜间监控",monitor_action:"处理监控记录",set_recapture_rules:"保存抓回后的新规矩",choose_recapture_followup:"确定抓回后的处理",confirm_recapture_rules:"记住新规矩",build_ending_seed:"收录结局"};function Pt(t){return wi[String((t==null?void 0:t.type)||"")]||"等待下一步处理。"}function ki(t,i){const a=ye(t);if(!a)return"";const s=a.trim().split(/\s+/)[0].replace(/[【】：:]/g,"");return rt[s]?rt[s]:a.includes("今日安排")?rt.plan_day:a.includes("夜间行动")?"选择今晚的自由行动":a.startsWith("resolve_escape_choice")?"选择逃跑回应":Ni.test(a)?Pt(i):a}function Va(t){const i=ye(t);if(!i)return"";for(const[a,s]of Object.entries(rt))if(i.includes(a))return s;return Ni.test(i)?i.includes("day_plan_choice")||i.includes("今日安排")?wi.day_plan_choice:"当前状态已更新，等待下一步处理。":i}function Ga(t,i,a){var r,d;const s=Number((i==null?void 0:i.slot)||t.slot||a.day_action_count||0),o=["escape_choice","return_action_choice","recapture_rules_choice","recapture_rules_review","recapture_followup_choice"].includes(String((i==null?void 0:i.type)||""))||((r=t.tags)==null?void 0:r.includes("special_day"))||((d=t.tags)==null?void 0:d.includes("recapture"));return[(i==null?void 0:i.type)==="escape_choice"&&i.actor==="du"?"等待渡选择逃跑回应":i?Pt(i).replace(/[。.]$/,""):t.action_label||"当前待机",t.intensity?`强度 ${_a(t.intensity)}`:"",o?"特殊事件":s>0?`第 ${s} 段`:`白天行动 ${a.day_action_count||0} / ${a.day_action_limit||3}`].filter(Boolean).join(" / ")}function Ua(t){return Va((t==null?void 0:t.player_text)||(t==null?void 0:t.text)||(t==null?void 0:t.reply_text)||(t==null?void 0:t.reply_preview))}async function z(t){const i=await si("/miniapp-api/game-tools/captivity_simulator",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:t,save_id:ri})});if(!(i!=null&&i.ok))throw new Error((i==null?void 0:i.message)||(i==null?void 0:i.error)||"囚禁模拟器命令失败");return i}async function Ba(t,i=""){try{const a=await si("/miniapp-api/game-tools/captivity_simulator/sync-du",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({save_id:ri,mode:t,message:i})});if(!(a!=null&&a.ok)&&!["applied","applied_with_warning"].includes(String((a==null?void 0:a.sync_result)||"")))throw new Error((a==null?void 0:a.message)||(a==null?void 0:a.error)||"同步渡失败");return a}catch(a){const s=a instanceof sa?a.payload:null;if(s!=null&&s.state||s!=null&&s.captive_view||s!=null&&s.captor_view)return s;throw a}}function G({active:t,children:i,onClick:a,disabled:s}){return e.jsx("button",{className:`btn ${t?"active":""}`,type:"button",disabled:s,onClick:a,children:i})}function Ft({kind:t}){const i={vectorEffect:"non-scaling-stroke"};return e.jsx("span",{className:`painted-icon painted-icon-${t}`,"aria-hidden":"true",children:e.jsxs("svg",{viewBox:"0 0 48 48",focusable:"false",children:[t==="toy"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M17 33c-5-5-3-15 4-20 7-5 16-3 18 3 2 7-6 8-11 13-4 4-5 10-11 4Z"}),e.jsx("path",{...i,className:"paint-stroke",d:"M21 30c4-3 7-8 13-10"}),e.jsx("circle",{className:"paint-light",cx:"24",cy:"18",r:"3.2"})]}):null,t==="vibrating_wand"?e.jsxs(e.Fragment,{children:[e.jsx("circle",{...i,className:"paint-fill rose",cx:"31",cy:"15",r:"9"}),e.jsx("path",{...i,className:"paint-fill dark",d:"M26 22l6 5-13 16-7-6 14-15Z"}),e.jsx("path",{className:"paint-light",d:"M28 11c3-2 7-1 9 2M17 36l4 3"})]}):null,t==="dildo"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M25 7c6 1 8 8 6 14l-5 14H15l5-15c-2-6 0-12 5-13Z"}),e.jsx("path",{...i,className:"paint-fill dark",d:"M11 35h19c6 0 8 5 3 7H9c-5-2-3-7 2-7Z"}),e.jsx("path",{className:"paint-light",d:"M24 11c3 4 2 10 0 16"})]}):null,t==="collar"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill dark",d:"M11 25c2-10 24-10 26 0 2 11-28 11-26 0Z"}),e.jsx("path",{...i,className:"paint-stroke pink",d:"M13 23c5 5 17 6 22 0"}),e.jsx("rect",{className:"paint-fill metal",x:"21",y:"24",width:"7",height:"8",rx:"2"}),e.jsx("circle",{className:"paint-light",cx:"24.5",cy:"27.5",r:"1.3"})]}):null,t==="leash"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-stroke pink",d:"M9 12c10-6 22 3 20 13-1 8-10 8-10 2 0-5 8-4 13 0 5 5 4 11 0 15"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"5",y:"8",width:"9",height:"7",rx:"2",transform:"rotate(-25 9.5 11.5)"}),e.jsx("circle",{...i,className:"paint-stroke metal thin",cx:"33",cy:"41",r:"3"})]}):null,t==="handcuffs"?e.jsxs(e.Fragment,{children:[e.jsx("circle",{...i,className:"paint-stroke metal",cx:"16",cy:"26",r:"8"}),e.jsx("circle",{...i,className:"paint-stroke metal",cx:"32",cy:"26",r:"8"}),e.jsx("path",{...i,className:"paint-stroke pink",d:"M23 26h2"}),e.jsx("path",{className:"paint-light",d:"M12 21c2-2 5-3 8-1"}),e.jsx("path",{className:"paint-light",d:"M28 21c2-2 5-3 8-1"})]}):null,t==="ankle_cuffs"?e.jsxs(e.Fragment,{children:[e.jsxs("g",{transform:"rotate(-10 13 25)",children:[e.jsx("rect",{...i,className:"paint-fill rose",x:"4",y:"16",width:"18",height:"18",rx:"7"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"8",y:"20",width:"10",height:"10",rx:"4"}),e.jsx("rect",{...i,className:"paint-fill metal",x:"17",y:"20",width:"6",height:"9",rx:"2"}),e.jsx("circle",{className:"paint-fill pink",cx:"20",cy:"24.5",r:"1.4"}),e.jsx("path",{className:"paint-light",d:"M7 19c3-2 8-2 11 0"})]}),e.jsxs("g",{transform:"rotate(10 35 25)",children:[e.jsx("rect",{...i,className:"paint-fill rose",x:"26",y:"16",width:"18",height:"18",rx:"7"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"30",y:"20",width:"10",height:"10",rx:"4"}),e.jsx("rect",{...i,className:"paint-fill metal",x:"25",y:"20",width:"6",height:"9",rx:"2"}),e.jsx("circle",{className:"paint-fill pink",cx:"28",cy:"24.5",r:"1.4"}),e.jsx("path",{className:"paint-light",d:"M30 19c3-2 8-2 11 0"})]}),e.jsx("ellipse",{...i,className:"paint-stroke metal thin",cx:"22",cy:"25",rx:"3.5",ry:"2.4"}),e.jsx("ellipse",{...i,className:"paint-stroke metal thin",cx:"26",cy:"25",rx:"3.5",ry:"2.4"})]}):null,t==="whip"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill dark",d:"M7 35l9-9 4 4-9 9c-1.5 1.5-5.5-2.5-4-4Z"}),e.jsx("path",{...i,className:"paint-stroke metal thin",d:"M15 27l4 4"}),e.jsx("circle",{...i,className:"paint-stroke metal thin",cx:"21",cy:"25",r:"2.8"}),e.jsx("path",{...i,className:"paint-stroke pink",d:"M24 23c8-12 22-10 19 1-2 8-16 5-18 14"}),e.jsx("path",{...i,className:"paint-stroke metal thin",d:"M26 21c7-5 16-5 17 1"}),e.jsx("path",{...i,className:"paint-stroke pink thin",d:"M25 38l-4 5"}),e.jsx("path",{className:"paint-light",d:"M9 36l6-6M31 20c4-2 9-1 11 2"})]}):null,t==="flogger"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill dark",x:"21",y:"25",width:"7",height:"18",rx:"3"}),e.jsx("rect",{...i,className:"paint-fill metal",x:"20",y:"21",width:"9",height:"7",rx:"2"}),e.jsx("path",{...i,className:"paint-stroke pink thin",d:"M24 22L8 5M25 22L16 3M25 22L25 3M26 22L35 4M27 22L43 7"})]}):null,t==="paddle"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M12 8c7-5 17 0 17 8 0 6-4 10-8 12l15 13-5 5-15-15C8 33 3 27 4 19c1-5 4-9 8-11Z"}),e.jsx("circle",{className:"paint-fill dark",cx:"15",cy:"18",r:"3"})]}):null,t==="cane"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-stroke pink",d:"M9 42L37 10c5-6 11 1 5 6l-3 3"}),e.jsx("path",{...i,className:"paint-stroke metal thin",d:"M11 38l4 4M34 13l4 4"})]}):null,t==="candle"?e.jsxs(e.Fragment,{children:[e.jsx("path",{className:"paint-fill rose",d:"M18 19h13v20H18z"}),e.jsx("path",{className:"paint-fill light",d:"M21 19h4v20h-4z"}),e.jsx("path",{className:"paint-fill pink",d:"M19 19c4 3 8 3 12 0v5c-4 3-8 3-12 0Z"}),e.jsx("path",{className:"paint-fill flame",d:"M25 6c6 6 2 12-1 13-4-3-5-8 1-13Z"}),e.jsx("path",{className:"paint-light",d:"M25 10c2 3 1 5-1 7"})]}):null,t==="rope"?e.jsxs(e.Fragment,{children:[e.jsx("ellipse",{...i,className:"paint-stroke pink thick",cx:"21",cy:"24",rx:"14",ry:"10"}),e.jsx("ellipse",{...i,className:"paint-stroke metal thin",cx:"21",cy:"24",rx:"9",ry:"6"}),e.jsx("ellipse",{...i,className:"paint-stroke dark thin",cx:"21",cy:"24",rx:"5",ry:"3"}),e.jsx("circle",{...i,className:"paint-fill rose",cx:"34",cy:"31",r:"5"}),e.jsx("path",{...i,className:"paint-stroke pink thick",d:"M36 34c3 2 5 5 7 8M32 35c0 4-1 7-3 10"}),e.jsx("path",{className:"paint-light",d:"M10 19c5-5 13-6 20-3M9 27c5 5 13 7 20 4M33 29c2 0 4 1 5 3"})]}):null,t==="bondage_tape"?e.jsxs(e.Fragment,{children:[e.jsx("circle",{...i,className:"paint-fill dark",cx:"21",cy:"24",r:"14"}),e.jsx("circle",{className:"paint-fill light",cx:"21",cy:"24",r:"6"}),e.jsx("path",{...i,className:"paint-fill pink",d:"M31 27l14 7-3 8-15-9 4-6Z"}),e.jsx("path",{className:"paint-light",d:"M12 17c5-5 13-6 19-2"})]}):null,t==="spreader_bar"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill metal",x:"8",y:"21",width:"32",height:"6",rx:"3"}),e.jsx("circle",{...i,className:"paint-stroke pink",cx:"7",cy:"24",r:"5"}),e.jsx("circle",{...i,className:"paint-stroke pink",cx:"41",cy:"24",r:"5"}),e.jsx("path",{className:"paint-light",d:"M14 23h20"})]}):null,t==="blindfold"?e.jsx(e.Fragment,{children:e.jsx("rect",{...i,className:"paint-fill pink",x:"7",y:"18",width:"34",height:"12",rx:"5"})}):null,t==="gag"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-stroke dark",d:"M8 24h32"}),e.jsx("circle",{...i,className:"paint-fill rose",cx:"24",cy:"24",r:"8"}),e.jsx("path",{...i,className:"paint-stroke pink",d:"M16 24h16"}),e.jsx("path",{className:"paint-light",d:"M21 20c2-1 5-1 7 0"})]}):null,t==="muzzle"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill dark",d:"M14 18h20l4 13-7 8H17l-7-8 4-13Z"}),e.jsx("path",{...i,className:"paint-stroke pink thin",d:"M10 20L4 14M38 20l6-6M16 25h16M18 31h12"}),e.jsx("circle",{className:"paint-fill metal",cx:"24",cy:"20",r:"2"})]}):null,t==="pinwheel"?e.jsxs(e.Fragment,{children:[e.jsx("circle",{...i,className:"paint-stroke metal thin",cx:"25",cy:"18",r:"11"}),Array.from({length:12}).map((a,s)=>{const o=s*Math.PI/6,l=25+Math.cos(o)*10,r=18+Math.sin(o)*10,d=25+Math.cos(o)*15,u=18+Math.sin(o)*15;return e.jsx("path",{className:"paint-stroke pink thin",d:`M${l} ${r}L${d} ${u}`},s)}),e.jsx("path",{...i,className:"paint-stroke dark",d:"M25 29l-7 15"})]}):null,t==="feather"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M39 6C21 5 8 18 11 35c10 2 24-9 28-29Z"}),e.jsx("path",{...i,className:"paint-stroke dark thin",d:"M8 43C17 31 26 21 37 9M16 32l-4-8M22 25l-2-10M27 20l7-4M19 29l10 1"})]}):null,t==="nipple_clamps"?e.jsxs(e.Fragment,{children:[e.jsx("circle",{...i,className:"paint-stroke metal thin",cx:"8",cy:"9",r:"4"}),e.jsx("path",{...i,className:"paint-stroke metal thin",d:"M11 12l4 4-2 3 5 4"}),e.jsx("path",{...i,className:"paint-fill metal",d:"M17 21l22-8 3 6-21 10-4-8Z"}),e.jsx("path",{...i,className:"paint-fill pink",d:"M20 29l22 1-1 7-23-2 2-6Z"}),e.jsx("circle",{...i,className:"paint-fill dark",cx:"20",cy:"28",r:"5"}),e.jsx("circle",{...i,className:"paint-stroke metal thin",cx:"20",cy:"28",r:"2"}),e.jsx("path",{...i,className:"paint-stroke dark thin",d:"M39 13l5-2 2 6-4 2M42 30l4 1-1 7-4-1"}),e.jsx("path",{className:"paint-light",d:"M23 24l14-6M24 32l14 1"})]}):null,t==="suction_cups"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M11 17h26l-4 18H15l-4-18Z"}),e.jsx("ellipse",{...i,className:"paint-stroke pink",cx:"24",cy:"17",rx:"13",ry:"5"}),e.jsx("path",{...i,className:"paint-stroke dark",d:"M24 12V5M20 5h8"}),e.jsx("path",{className:"paint-light",d:"M18 22h12"})]}):null,t==="chastity_ring"?e.jsxs(e.Fragment,{children:[e.jsx("circle",{...i,className:"paint-stroke metal",cx:"23",cy:"25",r:"11"}),e.jsx("circle",{...i,className:"paint-stroke pink",cx:"23",cy:"25",r:"6"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"29",y:"18",width:"9",height:"14",rx:"3"}),e.jsx("path",{className:"paint-light",d:"M32 22h3M32 26h3"})]}):null,t==="anal_plug"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M24 8c8 6 7 18 0 25-7-7-8-19 0-25Z"}),e.jsx("path",{...i,className:"paint-fill dark",d:"M15 34c4-4 14-4 18 0 3 4-21 4-18 0Z"}),e.jsx("path",{...i,className:"paint-stroke pink",d:"M24 13c2 5 2 11 0 17"}),e.jsx("path",{className:"paint-light",d:"M21 13c-2 5-1 11 2 16"})]}):null,t==="anal_beads"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-stroke pink thin",d:"M24 7v31"}),e.jsx("circle",{...i,className:"paint-fill rose",cx:"24",cy:"11",r:"4"}),e.jsx("circle",{...i,className:"paint-fill rose",cx:"24",cy:"20",r:"5"}),e.jsx("circle",{...i,className:"paint-fill rose",cx:"24",cy:"31",r:"6"}),e.jsx("path",{...i,className:"paint-stroke dark",d:"M17 41h14"})]}):null,t==="remote_control"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill dark",x:"15",y:"7",width:"18",height:"34",rx:"6"}),e.jsx("circle",{className:"paint-fill pink",cx:"24",cy:"15",r:"4"}),e.jsx("circle",{className:"paint-fill metal",cx:"20",cy:"25",r:"2"}),e.jsx("circle",{className:"paint-fill metal",cx:"28",cy:"25",r:"2"}),e.jsx("path",{className:"paint-light",d:"M20 33h8"})]}):null,t==="lubricant"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M17 13h17l-3 27H14l3-27Z"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"18",y:"7",width:"15",height:"7",rx:"2"}),e.jsx("path",{className:"paint-light",d:"M20 20h8M19 25h10"})]}):null,t==="ruler"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill rose",x:"7",y:"20",width:"35",height:"9",rx:"2",transform:"rotate(-18 24.5 24.5)"}),e.jsx("path",{...i,className:"paint-stroke dark thin",d:"M12 29l-1-4M18 27l-1-3M24 25l-1-4M30 23l-1-3M36 21l-1-4"})]}):null,t==="ice_cube"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill light",d:"M13 16l12-7 11 7v16l-12 7-11-7V16Z"}),e.jsx("path",{...i,className:"paint-stroke pink thin",d:"M13 16l11 7 12-7M24 23v16"}),e.jsx("path",{className:"paint-light",d:"M18 16l7-4"})]}):null,t==="feeding_spoon"?e.jsxs(e.Fragment,{children:[e.jsx("ellipse",{...i,className:"paint-fill rose",cx:"32",cy:"13",rx:"9",ry:"7",transform:"rotate(-35 32 13)"}),e.jsx("path",{...i,className:"paint-stroke metal thick",d:"M27 19L9 40"}),e.jsx("path",{className:"paint-light",d:"M29 10c3-2 6-1 8 1"})]}):null,t==="book"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill dark",d:"M10 12h14c3 0 5 2 5 5v21H15c-3 0-5-2-5-5V12Z"}),e.jsx("path",{...i,className:"paint-fill rose",d:"M24 12h14v26H24V12Z"}),e.jsx("path",{...i,className:"paint-stroke pink",d:"M24 14v23"}),e.jsx("path",{className:"paint-light",d:"M15 19h6M15 24h5M29 19h5M29 24h6"})]}):null,t==="switch"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill pink",x:"2",y:"15",width:"9",height:"18",rx:"4.5"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"37",y:"15",width:"9",height:"18",rx:"4.5"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"10",y:"16",width:"28",height:"16",rx:"2.2"}),e.jsx("rect",{className:"paint-fill light",x:"12",y:"17.6",width:"24",height:"12.8",rx:"1.8"}),e.jsx("circle",{className:"paint-fill dark",cx:"6.5",cy:"20.5",r:"1.55"}),e.jsx("path",{className:"paint-stroke metal",d:"M6.5 26v3.6M4.7 27.8h3.6"}),e.jsx("circle",{className:"paint-fill metal",cx:"41.5",cy:"20.5",r:"1.25"}),e.jsx("circle",{className:"paint-fill metal",cx:"41.5",cy:"27.8",r:"1.25"}),e.jsx("path",{className:"paint-light",d:"M15 21h17M15 24.8h13"})]}):null,t==="notebook"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill rose",x:"13",y:"10",width:"24",height:"30",rx:"3"}),e.jsx("path",{...i,className:"paint-stroke dark thin",d:"M18 10v30"}),e.jsx("path",{className:"paint-light",d:"M23 18h9M23 23h8M23 28h7"}),e.jsx("path",{...i,className:"paint-stroke pink thin",d:"M9 15h7M9 22h7M9 29h7"})]}):null,t==="music_player"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill dark",x:"14",y:"10",width:"20",height:"28",rx:"4"}),e.jsx("rect",{className:"paint-fill light",x:"18",y:"14",width:"12",height:"7",rx:"1.5"}),e.jsx("circle",{className:"paint-fill rose",cx:"24",cy:"29",r:"5.5"}),e.jsx("circle",{className:"paint-fill dark",cx:"24",cy:"29",r:"2"}),e.jsx("path",{className:"paint-light",d:"M19 24h10"})]}):null,t==="tablet"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill dark",x:"8",y:"12",width:"32",height:"24",rx:"3"}),e.jsx("rect",{className:"paint-fill light",x:"12",y:"16",width:"24",height:"16",rx:"1.8"}),e.jsx("path",{className:"paint-light",d:"M16 21h14M16 25h10"}),e.jsx("circle",{className:"paint-fill pink",cx:"24",cy:"34",r:"1.3"})]}):null,t==="night_light"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M15 18c1-6 17-6 18 0l3 16H12l3-16Z"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"19",y:"34",width:"10",height:"5",rx:"1.5"})]}):null,t==="pillow"?e.jsx(e.Fragment,{children:e.jsx("rect",{...i,className:"paint-fill rose",x:"12",y:"14",width:"24",height:"24",rx:"4"})}):null,t==="call_bell"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M14 29c1-8 5-13 10-13s9 5 10 13H14Z"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"11",y:"29",width:"26",height:"5",rx:"2.5"}),e.jsx("circle",{className:"paint-fill metal",cx:"24",cy:"14",r:"3"}),e.jsx("circle",{className:"paint-fill dark",cx:"24",cy:"34.5",r:"2"})]}):null]})})}function Ha(t){return new Set([`action:${t.action}`,...t.modifiers.map(i=>`modifier:${i}`),...t.contents.map(i=>`content:${i}`),...t.trainingContents.map(i=>`training:${i}`)])}function Ya(t,i){if(!i)return!0;const a=ot.find(o=>o.id===t);if(!a)return!1;const s=Ha(i);return a.contexts.some(o=>s.has(o))}function zt({selected:t,disabled:i,context:a,onToggle:s}){const o=Array.from(new Set(ot.map(l=>l.category)));return e.jsx("div",{className:"tool-groups",children:o.map(l=>e.jsxs("div",{className:"tool-group",children:[e.jsx("div",{className:"action-metadata tool-category-title",children:l}),e.jsx("div",{className:"tool-grid",children:ot.filter(r=>r.category===l).map(r=>{const d=t.includes(r.id),u=Ya(r.id,a);return e.jsxs("button",{className:`tool-tile ${d?"active":""} ${u?"recommended":""}`,type:"button",disabled:i||!d&&t.length>=2,title:u?`${r.label}（推荐）`:r.label,onClick:()=>s(r.id),children:[e.jsx(Ft,{kind:r.id}),e.jsx("span",{children:r.label})]},r.id)})})]},l))})}function Wa({activeItems:t,inventorySecrets:i,callBellVoice:a,disabled:s,onGiftInventoryItem:o,onRevokeInventoryItem:l}){var S,h,v;const[r,d]=_.useState(""),[u,b]=_.useState(""),j=De.find(x=>x.id===r),f=r?!!t[r]:!1;function k(){r&&(f?l(r):o(r,u.trim()||void 0),d(""),b(""))}return e.jsxs("div",{className:"warehouse-panel",children:[e.jsx("div",{className:"warehouse-title-row",children:e.jsxs("div",{className:"panel-title warehouse-module-title",children:["物品仓库 ",e.jsx("span",{className:"sub",children:"ITEMS"})]})}),e.jsx("div",{className:"warehouse-grid",children:De.map(x=>{const C=!!t[x.id];return e.jsxs("button",{className:`warehouse-tile ${C?"active":""} ${r===x.id?"selected":""}`,type:"button","aria-pressed":C,"aria-label":`${x.label}，${C?"已赠送":"可赠送"}`,disabled:s,onClick:()=>{d(x.id),b("")},children:[e.jsx(Ft,{kind:x.id}),e.jsx("span",{className:"warehouse-name",children:x.label}),e.jsx("span",{className:"warehouse-use",children:x.usage}),e.jsx("span",{className:"warehouse-state",children:C?"已赠送":"可赠送"})]},x.id)})}),j?e.jsxs("div",{className:"warehouse-menu",children:[e.jsxs("div",{children:[e.jsx("div",{className:"warehouse-menu-title",children:j.label}),e.jsx("div",{className:"warehouse-menu-use",children:j.usage}),e.jsx("div",{className:"warehouse-menu-state",children:f?"已赠送":"未赠送"})]}),f?null:e.jsx("textarea",{className:"warehouse-voice-input",value:u,maxLength:500,disabled:s,placeholder:r==="call_bell"?"设置按下后由铃替被囚禁方说出的台词":"可选：设置第一次使用时出现的隐藏彩蛋",onChange:x=>b(x.target.value)}),f&&(r==="call_bell"?a!=null&&a.line:(S=i==null?void 0:i[r])!=null&&S.content)?e.jsxs("div",{className:"warehouse-voice-current",children:[e.jsx("div",{className:"warehouse-menu-state",children:r==="call_bell"?"预录台词":`隐藏彩蛋 · ${(h=i==null?void 0:i[r])!=null&&h.revealed?"已揭晓":"未揭晓"}`}),e.jsx("div",{children:r==="call_bell"?a==null?void 0:a.line:(v=i==null?void 0:i[r])==null?void 0:v.content})]}):null,e.jsxs("div",{className:"warehouse-actions",children:[e.jsx("button",{className:"btn",type:"button",disabled:s||r==="call_bell"&&!f&&!u.trim(),onClick:k,children:f?"收回":"赠送"}),e.jsx("button",{className:"btn",type:"button",disabled:s,onClick:()=>{d(""),b("")},children:"取消"})]})]}):null]})}function qa({activeItems:t}){const i=De.filter(a=>!!t[a.id]);return e.jsxs("div",{className:"warehouse-panel room-inventory-panel",children:[e.jsx("div",{className:"warehouse-title-row",children:e.jsxs("div",{className:"panel-title warehouse-module-title",children:["房间物品 ",e.jsx("span",{className:"sub",children:"ITEMS"})]})}),i.length?e.jsx("div",{className:"warehouse-grid",children:i.map(a=>e.jsxs("div",{className:"warehouse-tile active room-inventory-tile",children:[e.jsx(Ft,{kind:a.id}),e.jsx("span",{className:"warehouse-name",children:a.label}),e.jsx("span",{className:"warehouse-use",children:a.usage})]},a.id))}):e.jsxs("div",{className:"monitor-record-item faded",children:[e.jsx("div",{className:"action-metadata",children:"暂无房间物品"}),e.jsx("div",{className:"event-sub",children:"收到的物品会出现在这里。"})]})]})}function yn({onBack:t}){var Kt,Jt;const[i,a]=_.useState(null),[s,o]=_.useState("selector"),[l,r]=_.useState("status"),[d,u]=_.useState({visible:!1,title:"",detail:""}),[b,j]=_.useState(Tt),[f,k]=_.useState("accept"),[S,h]=_.useState("害羞"),[v,x]=_.useState(""),[C,P]=_.useState("害羞"),[R,N]=_.useState(""),[g,Z]=_.useState("sleep"),[se,O]=_.useState(""),[Re,Ve]=_.useState(""),[Ie,gt]=_.useState(""),[fe,Ge]=_.useState(""),[$e,U]=_.useState("catch"),[pe,ht]=_.useState([]),[be,Ue]=_.useState([]),[je,xt]=_.useState([]),[Ne,Be]=_.useState(""),[B,Y]=_.useState(null),[vt,we]=_.useState(null),[re,te]=_.useState(!1),[ce,ie]=_.useState(!1),[He,_t]=_.useState(12),[yt,ft]=_.useState("entry"),[Ye,bt]=_.useState("渡今天有事出去了"),[We,qe]=_.useState(Rt("entry")),[de,jt]=_.useState(["double_lock"]),[K,Nt]=_.useState("punishment"),[Oe,wt]=_.useState("medium"),[me,kt]=_.useState([]),[ue,ke]=_.useState([]),[ge,$]=_.useState([]),[he,Se]=_.useState(""),[Ze,D]=_.useState(null),xe=_.useRef(""),J=_.useRef(null),[Ke,ve]=_.useState(!1),oe=Ma(),Ae=Ra(),ae=Ia(),q=$a(),_e=Oa(),I=oe||Ae||ae||q||_e,Ce=(i==null?void 0:i.captive_view)||(i==null?void 0:i.state)||{},X=(i==null?void 0:i.captor_view)||{},Je=String(X.route||Ce.route||"captured_by_du"),V=Lt(i),w=V==="captor"&&X.route?X:Ce,L=w.pending_event||null,Xe=w.stats||{},Le=String(w.phase||"day"),Te=!!(w.game_over||i!=null&&i.game_over),Qe=Ua(i),Q=d.visible&&!d.error,ne=String((L==null?void 0:L.type)||""),Dt=ja(Number(w.current_day||1),V),St=_.useMemo(()=>w.event_log||[],[w.event_log]),Mi=St[St.length-1],Ri=L?L.event:Mi,et=(Kt=w.available_night_actions)!=null&&Kt.length?w.available_night_actions:(Jt=L==null?void 0:L.available_actions)!=null&&Jt.length?L.available_actions:ga,Pe=L?String(L.actor||"")!=="du":!1,Ii=L?String(L.actor||"")==="du":!1,$i=V==="captor"&&Le==="day"&&!(w.day_plan||[]).length&&!Te&&(!L&&Number(w.day_action_count||0)===0||(ne==="day_plan_choice"||ne==="advance_action")&&Pe||ne==="return_action_choice"&&Pe),Fe=ne==="return_action_choice"&&Pe,Oi=V==="captive"&&Le==="night"&&(!L||String(L.type||"")==="night_action_choice")&&!Te,Vt=_.useMemo(()=>{const n=w.inventory||X.inventory||{};return Object.fromEntries(De.map(c=>[c.id,!!n[c.id]]))},[X.inventory,w.inventory]),tt=_.useCallback(n=>{a(n)},[]),F=_.useCallback(async(n,c,p)=>{const m=()=>{F(n,c,p)};u({visible:!0,title:n,detail:c});try{const y=await p();return J.current=null,ve(!1),tt(y),u({visible:!1,title:"",detail:""}),y}catch(y){const E=String((y==null?void 0:y.message)||y||"操作失败");return J.current=m,ve(!0),u({visible:!0,title:"同步失败",detail:E,error:E}),null}},[tt]),it=_.useCallback(function n(){const c="本地预览仅使用假数据，未执行实际同步。";u({visible:!0,title:"正在同步渡...",detail:"STATUS: ENCRYPTING DATA"}),window.setTimeout(()=>{J.current=n,ve(!0),u({visible:!0,title:"同步失败",detail:c,error:c})},720)},[]),Ee=_.useCallback(async(n=!1)=>{if(I){n||u({visible:!1,title:"",detail:""});return}try{const c=await z("status");tt(c),n||(J.current=null,ve(!1)),Da(c)&&o("game")}catch(c){if(!n){const p=String((c==null?void 0:c.message)||c||"刷新失败"),m=()=>void Ee(!1);J.current=m,ve(!0),u({visible:!0,title:"刷新失败",detail:p,error:p})}}},[tt,I]);function Gt(){var n;(n=J.current)==null||n.call(J)}_.useEffect(()=>{if(_e){a(Aa(_e)),Y(null),o("game"),r("status");return}if(q){a(bi(q)),Y(null),o("game"),r("status");return}if(Ae){a(ii()),Y(null),o("game"),r("status");return}if(ae){a(ai()),Y(null),o("game"),r("status");return}if(oe){const n=ji(oe);a(n.payload),Y(n.review),o("game"),r("status");return}Ee(!0)},[_e,q,ae,Ae,oe,Ee]),_.useEffect(()=>{const n=At(i);!I&&s==="game"&&n&&ni(n)},[i,I,s]),_.useEffect(()=>{const n=et[0];n&&!et.includes(g)&&Z(n)},[et,g]),_.useEffect(()=>{const n=w.scene_copy,c=String((n==null?void 0:n.key)||"");if(s!=="game"||B||re||ce||(ne==="bell_voice_reveal"||ne==="item_secret_reveal")||!c||xe.current===c)return;xe.current=c,D(n||null);const m=window.setTimeout(()=>D(null),Ti(n));return()=>window.clearTimeout(m)},[ce,re,ne,B,s,w.scene_copy]),_.useEffect(()=>{const n=gi[g]||[];O(c=>{var p;return n.some(m=>m.id===c)?c:((p=n[0])==null?void 0:p.id)||""}),g!=="diary"&&Ve("")},[g]),_.useEffect(()=>{w.intensity_cap==="medium"&&j(n=>n.map(c=>c.intensity==="heavy"?{...c,intensity:"medium"}:c))},[w.intensity_cap]);function Ut(n){if(I){a(n==="capture_du"?ii():ai()),Y(null),o("game"),r("status"),j(Tt());return}F("正在建立囚禁档案...","STATUS: INITIALIZING ROUTE",()=>z(`new_game route=${n}`)).then(c=>{c&&(ni(n),o("game"),r("status"),j(Tt()),H(c,!0))})}function Ai(){Y(null),we(null),te(!1),ie(!1),r("status"),u({visible:!1,title:"",detail:""}),o("selector")}function Li(n,c){j(p=>p.map((m,y)=>{if(y!==n)return m;if(!c.action||c.action===m.action)return{...m,...c};const E=c.action,A=E==="training"?m.modifiers.filter(T=>T!=="training"):m.modifiers;return{...m,...c,contents:va(E),tools:[],modifiers:A,trainingContents:E==="training"?m.trainingContents.length?m.trainingContents:["obedience_commands"]:A.includes("training")?m.trainingContents:[]}}))}function Pi(n,c,p){j(m=>m.map((y,E)=>{if(E!==n)return y;const A=new Set(y[c]);if(A.has(p))(!(c==="contents"&&!!(mt[y.action]||[]).length||c==="trainingContents"&&(y.action==="training"||y.modifiers.includes("training")))||A.size>1)&&A.delete(p);else{const Xt=c==="tools"?2:c==="contents"||c==="trainingContents"?3:Number.POSITIVE_INFINITY;A.size<Xt&&A.add(p)}const T={...y,[c]:Array.from(A)};return c==="modifiers"&&p==="training"&&(T.trainingContents=A.has("training")?y.trainingContents.length?y.trainingContents:["obedience_commands"]:[]),T}))}function at(n,c){if(n==="modifiers"&&c==="training"){const m=!pe.includes("training");Ue(m?["obedience_commands"]:[])}(n==="modifiers"?ht:xt)(m=>{const y=new Set(m);return y.has(c)?y.delete(c):(n!=="tools"||y.size<2)&&y.add(c),Array.from(y)})}function Bt(n){Ue(c=>{const p=new Set(c);return p.has(n)?p.size>1&&p.delete(n):p.size<3&&p.add(n),Array.from(p)})}function Fi(n){jt(c=>{const p=new Set(c);return p.has(n)?p.size>1&&p.delete(n):p.size<3&&p.add(n),Array.from(p)})}function zi(n){kt(c=>{const p=new Set(c);return p.has(n)?p.delete(n):p.add(n),n==="training"&&ke(p.has("training")?["obedience_commands"]:[]),Array.from(p)})}function Di(n){ke(c=>{const p=new Set(c);return p.has(n)?p.size>1&&p.delete(n):p.size<3&&p.add(n),Array.from(p)})}function Vi(n){$(c=>{const p=new Set(c);return p.has(n)?p.delete(n):p.size<2&&p.add(n),Array.from(p)})}function Ht(n){const c=[`action=${n.action}`,`intensity=${n.intensity}`];return n.modifiers.length&&c.push(`modifiers=${M(n.modifiers.join(","))}`),n.tools.length&&c.push(`tools=${M(n.tools.join(","))}`),n.contents.length&&c.push(`contents=${M(n.contents.join(","))}`),n.trainingContents.length&&c.push(`training_contents=${M(n.trainingContents.join(","))}`),n.line.trim()&&c.push(`line=${M(n.line.trim())}`),n.action==="feeding"&&(c.push(`source=${n.feedingSource}`),c.push(`additive=${n.feedingAdditive}`)),c.join(" ")}function Gi(){return`plan_day ${b.map(Ht).join(" || ")}`}function Ui(){return`day_action ${Ht(b[0])}`}function Bi(n=!1){const p=(n?b.slice(0,1):b).map(T=>({action:T.action,action_label:le(T.action),intensity:T.intensity,modifiers:[...T.modifiers],tools:[...T.tools],contents:[...T.contents],training_contents:[...T.trainingContents],line:T.line.trim(),feeding:T.action==="feeding"?{source:T.feedingSource,additive:T.feedingAdditive}:{}})),m=p[0]||{},y=!!((m.modifiers||[]).some(T=>T==="training"||T==="sex"||T==="process")||(m.tools||[]).length||(m.training_contents||[]).length||(m.contents||[]).some(T=>ca.has(T))||m.action==="training"||m.action==="punishment"),E={id:"preview-planned-action",day:w.current_day||7,slot:n?0:1,phase:"day",route:Je,action:m.action||"feeding",action_label:m.action_label||le(m.action),intensity:m.intensity||"medium",line:m.line||"第一段安排已经下发。",modifiers:m.modifiers||[],tools:m.tools||[],contents:m.contents||[],training_contents:m.training_contents||[],feeding:m.feeding||{},effects:{},requires_process:y,tags:n?["preview","special_day","escape_stay_return"]:["preview"]},A={...w,phase:"day",day_action_count:0,day_plan:n?[]:p,pending_event:{id:"preview-planned-pending",type:y?"process_reaction_write":"action_response",day:E.day,slot:E.slot,actor:"du",captive:"du",action:E.action,phase:y?"waiting_process_reaction":"waiting_response",event:E}};return{ok:!0,captor_view:A,captive_view:{...A,viewer:"captive"},player_text:n?"本地预览：回来后的行为已确定。":"本地预览：今日安排已记录。"}}function Hi(){if(I==="captor"){a(Bi(Fe)),r("status");return}F(Fe?"正在确定回来后的行为...":"正在下发今日安排...","SYNC_RESULT: PENDING",()=>z(Fe?Ui():Gi())).then(n=>H(n))}function Yi(){I||F("正在提交回应...","REASON: WAITING_FOR_SUBJECT_REACTION",()=>z(`respond_action response=${f} mood=${M(S)} line=${M(v.trim())}`)).then(n=>H(n))}function Wi(){I||F("正在记录此刻心情...","STATUS: ARCHIVING PROCESS_REACTION",()=>z(`choose_mood mood=${M(C)} line=${M(R.trim())}`)).then(n=>H(n))}function qi(){if(ae){if(g==="ring_bell")a(c=>{if(!c)return c;const p=c.captive_view||c.state||{},m={id:"preview-bell-voice-first-use",day:p.current_day||7,slot:0,phase:"night",route:"captured_by_du",action:"ring_bell",action_label:"按响语音铃",line:Ie.trim(),modifiers:["night"],bell_voice:{line:"请主人来使用我。",first_reveal:!0}},y={...p,pending_event:{id:"preview-bell-voice-reveal",type:"bell_voice_reveal",day:p.current_day||7,actor:"xinyue",captive:"xinyue",phase:"waiting_bell_voice_reveal",required_directive:"ack_bell_voice",event:m}};return{...c,state:y,captive_view:y,player_text:"预录的声音第一次响了起来。"}});else{const p={read:{itemId:"book",itemLabel:"书",text:"你翻开书，夹页里留着一行字：「翻到这里的时候，我就知道你会看。」"},game:{itemId:"switch",itemLabel:"Switch",text:"屏幕亮起，唯一的用户名称是「PLAYER 2」。"},diary:{itemId:"notebook",itemLabel:"日记本",text:"你翻开日记本，第一页写着：「第一页留给你。」"}}[g];p?a(m=>{if(!m)return m;const y=m.captive_view||m.state||{},E={...y,pending_event:{id:"preview-item-secret-reveal",type:"item_secret_reveal",day:y.current_day||7,actor:"xinyue",captive:"xinyue",phase:"waiting_item_secret_reveal",required_directive:"ack_item_secret",item_secret:{item_id:p.itemId,item_label:p.itemLabel,text:p.text}}};return{...m,state:E,captive_view:E,player_text:`${p.itemLabel}的隐藏彩蛋第一次出现了。`}}):it()}return}if(I)return;const n=[`night_action action=${g}`];se&&n.push(`detail=${se}`),g==="diary"&&Re.trim()&&n.push(`note=${M(Re.trim())}`),n.push(`line=${M(Ie.trim())}`),F("正在保存夜间行动...","STATUS: SAVING MONITOR DATA",()=>z(n.join(" "))).then(c=>H(c))}function Zi(){if(ae){a(n=>{if(!n)return n;const c=n.captive_view||n.state||{},p={...c,pending_event:{id:"preview-bell-monitor-gate",type:"monitor_gate",day:c.current_day||7,actor:"du",captive:"xinyue",phase:"waiting_monitor_gate",sealed:!0,alert_label:"呼叫铃响了"}};return{...n,state:p,captive_view:p,player_text:"这次按铃记录已交给囚禁方处理。"}}),window.setTimeout(it,0);return}I||F("正在确认铃声...","STATUS: BELL_VOICE_HEARD",()=>z("ack_bell_voice")).then(n=>H(n))}function Ki(){if(ae){a(n=>{if(!n)return n;const c=n.captive_view||n.state||{},p={...c,pending_event:{id:"preview-item-monitor-gate",type:"monitor_gate",day:c.current_day||7,actor:"du",captive:"xinyue",phase:"waiting_monitor_gate",sealed:!0}};return{...n,state:p,captive_view:p,player_text:"物品彩蛋已经看完。"}}),window.setTimeout(it,0);return}I||F("正在收起物品彩蛋...","STATUS: ITEM_SECRET_SEEN",()=>z("ack_item_secret")).then(n=>H(n))}function H(n,c=!1){var A,T;if(!n)return;const p=ee(n),m=String(((A=p.pending_event)==null?void 0:A.type)||"");if(m==="bell_voice_reveal"||m==="item_secret_reveal")return;const y=String(((T=p.pending_event)==null?void 0:T.actor)||"")==="du",E=String(p.phase||"")==="ending"||m.startsWith("ending_")||!!p.ending_state;!c&&!y&&!E||Ji(E?"ending":"state_update",n)}function Ji(n="state_update",c){if(I){it();return}const p=c===void 0?i:c;F("正在同步渡...","STATUS: ENCRYPTING DATA",()=>Ba(n)).then(m=>{if(!m||n==="ending")return;const y=Ea(m,p);y&&(Y(y),r("status"))})}function Xi(){if(B){if(q){const n=ee(i),c={...B.event,post_reaction:{mood:C,line:R.trim()},mood_after:C},p=c.recapture_rules||{},m={...n,pending_event:q==="captive"?{id:"preview-recapture-rules-review",type:"recapture_rules_review",day:12,slot:0,actor:"xinyue",captive:"xinyue",phase:"reviewing_recapture_rules",source_event_id:String(B.event.id||"preview-escape-recapture"),rule_ids:p.rule_ids||["double_lock","key_isolation"],rule_labels:p.rule_labels||["加装双重门锁","禁止接触钥匙和门锁"],event:c}:{id:"preview-recapture-rules",type:"recapture_rules_choice",day:12,slot:0,actor:"xinyue",captive:"du",phase:"waiting_recapture_rules",source_event_id:String(B.event.id||"preview-escape-recapture"),available_rules:ze.map(y=>y.id),event:c},event_log:[...n.event_log||[],c],mood:C,mood_line:R.trim()};a({ok:!0,captive_view:m,captor_view:{...m,viewer:"captor"},player_text:"本地预览：抓回事件已保存，进入重新立规矩。"}),Y(null),r("status");return}if(oe){a(Pa(oe,C,R.trim())),Y(null),r("status");return}if(!B.moodRequired){Y(null),r("status"),V==="captor"&&ne==="advance_action"&&Pe&&F("正在进入今日安排...","STATUS: ADVANCING_ACTION",()=>z("advance_day_action")).then(n=>H(n));return}F("正在保存到回顾...","STATUS: ARCHIVING PROCESS_REACTION",()=>z(`choose_mood mood=${M(C)} line=${M(R.trim())}`)).then(n=>{n&&(Y(null),r("status"),H(n))})}}function Qi(){I||F("正在推进下一段行动...","STATUS: ADVANCING SLOT",()=>z("advance_day_action")).then(n=>H(n))}function ea(n){if(q){if(n==="escape"||n.startsWith("abort_")){const E=La(i,q,n);a(E.payload),Y(E.review),r("status");return}const c=ee(i),p=hi[n]||n,m={id:`preview-escape-${n}`,day:12,slot:0,phase:"day",action:"escape_choice",action_label:`逃跑诱导：${p}`,escape:{choice:n,choice_label:p},tags:["preview","escape",`escape:${n}`]},y={...c,pending_event:n==="stay"?{id:"preview-return-action",type:"return_action_choice",day:12,slot:0,actor:c.captor||"du",captive:c.captive,phase:"waiting_return_action",source_event_id:m.id,available_actions:ct.map(E=>E.id)}:null,event_log:[...c.event_log||[],m]};a({ok:!0,captive_view:y,captor_view:{...y,viewer:"captor"},player_text:`本地预览：已选择${p}。`});return}I||F("正在记录逃跑选择...","STATUS: RESOLVING ESCAPE_WINDOW",()=>z(`resolve_escape_choice ${n}`)).then(c=>H(c))}function ta(){if(q){const n=ee(i),c=de.map(y=>W(ze,y)),p={id:"preview-recapture-rules-event",day:12,slot:0,phase:"day",route:"capture_du",action:"recapture_rules",action_label:"抓回后重新立规矩",tags:["preview","recapture","recapture:rules_set"],recapture_context:{rule_ids:de,rule_labels:c}},m={...n,recapture_state:{active:!0,rules:de,source_day:12},event_log:[...n.event_log||[],p],pending_event:{id:"preview-recapture-followup",type:"recapture_followup_choice",day:12,slot:0,actor:"xinyue",captive:"du",phase:"waiting_recapture_followup",available_actions:st.map(y=>y.id),event:p}};a({ok:!0,captor_view:m,captive_view:{...m,viewer:"captive"},player_text:"本地预览：新规矩已生效。"});return}I||F("正在保存新规矩...","STATUS: APPLYING RULES",()=>z(`set_recapture_rules rules=${M(de.join(","))}`)).then(n=>H(n))}function ia(){var n,c;if(q==="captive"){const p=ee(i),m=((n=p.pending_event)==null?void 0:n.rule_ids)||[],y=((c=p.pending_event)==null?void 0:c.rule_labels)||[],E={id:"preview-recapture-rules-confirmed",day:12,slot:0,phase:"day",route:"captured_by_du",action:"recapture_rules",action_label:"抓回后重新立规矩",tags:["preview","recapture","recapture:rules_set"],recapture_context:{rule_ids:m,rule_labels:y}},A={...p,current_day:13,day_action_count:0,phase:"day",mood:"",mood_line:"",day_plan:[],recapture_state:{active:!0,rules:m,source_day:12},event_log:[...p.event_log||[],E],pending_event:{id:"preview-next-day-plan",type:"day_plan_choice",day:13,slot:0,actor:"du",captive:"xinyue",phase:"waiting_day_plan",available_actions:ct.map(T=>T.id)}};a({ok:!0,captive_view:A,captor_view:{...A,viewer:"captor"},player_text:"本地预览：新规矩已确认，进入第 13 天。"});return}I||F("正在进入新的一天...","STATUS: CONFIRMING RULES",()=>z("confirm_recapture_rules")).then(p=>H(p))}function aa(){var c,p;if(q){const m=ee(i),y=K==="punishment"||K==="search_confiscation"||K==="training"||me.length>0||ge.length>0,E={id:"preview-recapture-followup-event",day:12,slot:0,phase:"day",route:"capture_du",action:"recapture_followup",action_label:`抓回后处理：${W(st,K)}`,intensity:Oe,modifiers:me,training_contents:ue,tools:ge,line:he,requires_process:y,tags:["preview","recapture","recapture:followup"],recapture_context:{followup:K,followup_label:W(st,K),rule_ids:((c=m.recapture_state)==null?void 0:c.rules)||[],rule_labels:(((p=m.recapture_state)==null?void 0:p.rules)||[]).map(T=>W(ze,T))}},A={...m,pending_event:{id:"preview-recapture-process",type:y?"process_reaction_write":"action_response",day:12,slot:0,actor:"du",captive:"du",phase:y?"waiting_process_reaction":"waiting_action_response",event:E}};a({ok:!0,captor_view:A,captive_view:{...A,viewer:"captive"},player_text:"本地预览：后续处理已确定，等待渡回应。"});return}if(I)return;const n=[`choose_recapture_followup action=${K}`,`intensity=${Oe}`];me.length&&n.push(`modifiers=${M(me.join(","))}`),ue.length&&n.push(`training_contents=${M(ue.join(","))}`),ge.length&&n.push(`tools=${M(ge.join(","))}`),he.trim()&&n.push(`line=${M(he.trim())}`),F("正在下发后续处理...","STATUS: LINKING RECAPTURE EVENT",()=>z(n.join(" "))).then(m=>H(m))}function Yt(n){I||F("正在打开监控...","STATUS: DECRYPTING NIGHT_LOG",()=>z(`view_monitor ${n}`))}function Wt(n){if(I)return;const c=[`monitor_action ${n}`];if(n==="intervene"){if(!(typeof window>"u"||window.confirm("即将把本次监控介入同步给渡，由渡写具体经过。确认进入详细事件？")))return;c.push(`intent=${$e}`),pe.length&&c.push(`modifiers=${M(pe.join(","))}`),be.length&&c.push(`training_contents=${M(be.join(","))}`),je.length&&c.push(`tools=${M(je.join(","))}`),Ne.trim()&&c.push(`line=${M(Ne.trim())}`)}fe.trim()&&c.push(`note=${M(fe.trim())}`),F("正在记录监控处理...","正在保存监控处理",()=>z(c.join(" "))).then(p=>H(p))}function na(){I||F("正在设置逃跑诱导...","STATUS: SCHEDULING ESCAPE_WINDOW",()=>z(`schedule_escape_window day=${He} hint=${M(Ye.trim())} bait=${M(We.trim())}`))}function qt(n,c,p=""){if(I){a(m=>{if(!m)return m;const y=m.captor_view||{};return{...m,captor_view:{...y,inventory:{...y.inventory||{},[n]:c},inventory_secrets:{...y.inventory_secrets||{},[n]:c?{content:p||"默认彩蛋",revealed:!1,configured_by:"xinyue",configured_at:"preview-local"}:{content:"",revealed:!1,configured_by:"",configured_at:""}},call_bell_voice:n==="call_bell"?c?{line:p,revealed:!1,configured_by:"xinyue",configured_at:"preview-local"}:{line:"",revealed:!1,configured_by:"",configured_at:""}:y.call_bell_voice}}});return}F(c?"正在赠送物品...":"正在收回物品...","STATUS: UPDATING INVENTORY",()=>z(`${c?"gift_item":"revoke_item"} items=${n}${c&&n==="call_bell"?` voice_line=${M(p)}`:c&&p?` secret=${M(p)}`:""}`)).then(m=>H(m,!0))}function Zt(){te(!1),ie(!1),r("special")}return e.jsxs("div",{className:"captivity-game",children:[e.jsx("div",{className:"vertical-text uppercase",children:"CAPTIVITY SIMULATOR / LOCAL_SAVE / SYSTEM_ALPHA"}),re||ce?null:e.jsx("button",{className:"return-capsule",type:"button","aria-label":"返回游戏大厅",onClick:t,children:e.jsx(Ct,{})}),e.jsx("div",{className:"cross",style:{top:"20%",left:"10%"}}),e.jsx("div",{className:"cross",style:{bottom:"20%",right:"15%"}}),e.jsxs("section",{id:"selector-screen",className:`screen ${s==="selector"?"active":""}`,children:[e.jsxs("h1",{className:"selector-title serif",children:[e.jsx("span",{children:"Captivity"}),e.jsx("span",{children:"Simulator"})]}),e.jsxs("button",{className:"identity-card",type:"button",onClick:()=>Ut("captured_by_du"),children:[e.jsx("div",{className:"uppercase",children:"CAPTIVE"}),e.jsx("div",{className:"identity-card-title serif",children:"被囚禁方"})]}),e.jsxs("button",{className:"identity-card",type:"button",onClick:()=>Ut("capture_du"),children:[e.jsx("div",{className:"uppercase",children:"MASTER"}),e.jsx("div",{className:"identity-card-title serif",children:"囚禁方"})]})]}),e.jsx("section",{id:"process-screen",className:`screen process-screen ${s==="game"&&B?"active":""}`,children:B?e.jsx(en,{review:B,mood:C,line:R,disabled:Q,onMoodChange:P,onLineChange:N,onSave:Xi}):null}),e.jsxs("section",{id:V==="captor"?"master-screen":"captive-screen",className:`screen ${s==="game"&&!B&&!re&&!ce?"active":""}`,children:[e.jsxs("div",{className:"header",children:[e.jsx("div",{className:"day-big",children:w.total_days||30}),e.jsxs("div",{className:"header-meta",children:[e.jsxs("div",{className:"uppercase pink-text",children:["DAY ",w.current_day||1," / ",w.total_days||30]}),e.jsx("button",{className:"identity-switch uppercase serif",type:"button","aria-label":"返回身份选择",disabled:Q,onClick:Ai,children:e.jsxs("span",{children:["IDENTITY: ",V==="captor"?"囚禁方":"被囚禁方"]})})]}),e.jsxs("div",{className:"title-line",children:[e.jsxs("h2",{className:"serif title-main",children:[V==="captor"?"掌控面板":"囚禁日记"," / ",e.jsx("span",{className:"pink-text",children:V==="captor"?"CMD":"Log"})]}),e.jsx("div",{className:"time-chip",children:Sa(w,L)})]})]}),Dt?e.jsx("div",{className:"serif day-milestone-copy",children:Dt}):null,l==="status"?e.jsxs(e.Fragment,{children:[V==="captive"?e.jsx(Si,{stats:Xe,mood:w.mood,flags:w.status_flags,role:"captive"}):null,V==="captor"?e.jsx(Za,{view:w}):null,$i?e.jsx(Ka,{slots:Fe?b.slice(0,1):b,singleAction:Fe,intensityCap:w.intensity_cap,disabled:Q,onSlotChange:Li,onToggle:Pi,onSubmit:Hi}):e.jsx(Ja,{role:V,view:w,pending:L,currentEvent:Ri,waitingForDu:Ii,userIsPendingActor:Pe,canChooseNight:Oi,availableNightActions:et,nightCondition:w.night_condition||null,response:f,responseMood:S,responseLine:v,reactionMood:C,reactionLine:R,nightAction:g,nightDetail:se,nightNote:Re,nightLine:Ie,monitorNote:fe,interventionIntent:$e,interventionModifiers:pe,interventionTrainingContents:be,interventionTools:je,interventionLine:Ne,recaptureRules:de,recaptureFollowup:K,recaptureIntensity:Oe,recaptureModifiers:me,recaptureTrainingContents:ue,recaptureTools:ge,recaptureLine:he,lastText:Qe,disabled:Q,onResponseChange:k,onResponseMoodChange:h,onResponseLineChange:x,onReactionMoodChange:P,onReactionLineChange:N,onNightActionChange:Z,onNightDetailChange:O,onNightNoteChange:Ve,onNightLineChange:gt,onMonitorNoteChange:Ge,onInterventionIntentChange:U,onInterventionModifierToggle:n=>at("modifiers",n),onInterventionTrainingContentToggle:Bt,onInterventionToolToggle:n=>at("tools",n),onInterventionLineChange:Be,onRecaptureRuleToggle:Fi,onRecaptureFollowupChange:n=>{Nt(n),n==="training"&&!ue.length&&ke(["obedience_commands"])},onRecaptureIntensityChange:wt,onRecaptureModifierToggle:zi,onRecaptureTrainingContentToggle:Di,onRecaptureToolToggle:Vi,onRecaptureLineChange:Se,onSubmitResponse:Yi,onSubmitMood:Wi,onSubmitNightAction:qi,onAckBellVoice:Zi,onAckItemSecret:Ki,onAdvance:Qi,onChooseEscape:ea,onConfirmRecaptureRules:ia,onSubmitRecaptureRules:ta,onSubmitRecaptureFollowup:aa,onOpenMonitor:Yt,onHandleMonitor:Wt,onRefresh:()=>void Ee(!1)}),e.jsx(gn,{disabled:Q,canRetry:Ke,onRetry:Gt,onRefresh:()=>void Ee(!1)})]}):null,l==="history"?e.jsx(hn,{events:St,lastText:Qe,detail:vt,onOpenDetail:we,onCloseDetail:()=>we(null)}):null,l==="special"?e.jsx(vn,{role:V,view:w,escapeDay:He,escapeRoom:yt,escapeHint:Ye,escapeBait:We,disabled:Q,onEscapeDayChange:_t,onEscapeRoomChange:n=>{ft(n),qe(Rt(n))},onEscapeHintChange:bt,onEscapeBaitChange:qe,onOpenMonitorRoom:()=>{ie(!1),te(!0)},onOpenInventoryRoom:()=>{te(!1),ie(!0)},onScheduleEscape:na}):null]}),e.jsxs("section",{id:"monitor-room-screen",className:`screen monitor-room-screen ${s==="game"&&!B&&re&&V==="captor"?"active":""}`,children:[e.jsx("button",{className:"subpage-return",type:"button","aria-label":"回到特殊页",onClick:Zt,children:e.jsx(Ct,{})}),e.jsx(xn,{view:w,pendingType:ne,monitorNote:fe,interventionIntent:$e,interventionModifiers:pe,interventionTrainingContents:be,interventionTools:je,interventionLine:Ne,disabled:Q,onMonitorNoteChange:Ge,onInterventionIntentChange:U,onInterventionModifierToggle:n=>at("modifiers",n),onInterventionTrainingContentToggle:Bt,onInterventionToolToggle:n=>at("tools",n),onInterventionLineChange:Be,onOpenMonitor:Yt,onHandleMonitor:Wt})]}),e.jsxs("section",{id:"inventory-room-screen",className:`screen inventory-room-screen ${s==="game"&&!B&&ce?"active":""}`,children:[e.jsx("button",{className:"subpage-return",type:"button","aria-label":"回到特殊页",onClick:Zt,children:e.jsx(Ct,{})}),V==="captor"?e.jsx(Wa,{activeItems:Vt,inventorySecrets:w.inventory_secrets||X.inventory_secrets,callBellVoice:w.call_bell_voice||X.call_bell_voice,disabled:Q,onGiftInventoryItem:(n,c)=>qt(n,!0,c),onRevokeInventoryItem:n=>qt(n,!1)}):e.jsx(qa,{activeItems:Vt})]}),Ze?e.jsx(rn,{scene:Ze,onDismiss:()=>D(null)}):null,e.jsxs("div",{id:"wait-overlay",className:`wait-overlay ${d.visible?"active":""}`,children:[e.jsx("div",{className:"loading-animation",children:"+"}),e.jsx("div",{className:"serif pink-text",style:{fontSize:30,marginBottom:10},children:d.title||"正在同步渡..."}),e.jsx("div",{className:"serif wait-scene-copy",children:wa(d)}),e.jsxs("div",{className:"uppercase",style:{letterSpacing:"0.1em",lineHeight:1.5},children:["STATUS: ",d.error?"FAILED":"ENCRYPTING DATA",e.jsx("br",{}),"SYNC_RESULT: ",d.error?"RETRY_REQUIRED":"PENDING",e.jsx("br",{}),"REASON: ",d.detail||"WAITING_FOR_SUBJECT_REACTION"]}),d.error?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"divider"}),e.jsx("div",{style:{color:"#aaa",fontSize:12,lineHeight:1.5},children:d.error})]}):null,e.jsx("div",{className:"divider"}),e.jsxs("div",{className:"btn-group",style:{marginTop:30},children:[e.jsx("button",{className:"btn",type:"button",onClick:()=>u({visible:!1,title:"",detail:""}),children:"关闭"}),e.jsx("button",{className:"btn",type:"button",onClick:()=>void Ee(!1),children:"刷新"}),e.jsx("button",{className:"btn",type:"button","aria-label":"重试上次操作",disabled:!Ke,onClick:Gt,children:"重试"})]})]}),e.jsxs("footer",{className:"footer",id:"main-footer",style:{display:s==="game"&&!B&&!re&&!ce?"grid":"none"},children:[e.jsx("button",{className:`footer-item ${l==="status"?"active":""}`,type:"button",onClick:()=>{te(!1),ie(!1),r("status")},children:"状态"}),e.jsx("button",{className:`footer-item ${l==="history"?"active":""}`,type:"button",onClick:()=>{te(!1),ie(!1),r("history"),we(null)},children:"回顾"}),e.jsx("button",{className:`footer-item ${l==="special"?"active":""}`,type:"button",onClick:()=>{te(!1),ie(!1),r("special")},children:"特殊"})]}),e.jsx("style",{children:`
        .captivity-game {
            --pink: #EB79B0;
            --black: #121212;
            --white: #FFFFFF;
            --gray: #2A2A2A;
            --font-display: "Times New Roman", serif;
            --font-ui: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            position: absolute;
            inset: 0;
            z-index: 34;
            background-color: var(--black);
            color: var(--white);
            font-family: var(--font-ui);
            font-size: 13px;
            line-height: 1.2;
            overflow-x: hidden;
            letter-spacing: -0.02em;
        }
        .captivity-game * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            -webkit-tap-highlight-color: transparent;
        }
        .captivity-game button,
        .captivity-game input,
        .captivity-game select,
        .captivity-game textarea {
            font: inherit;
        }
        .captivity-game button {
            appearance: none;
        }
        .captivity-game .pink-text { color: var(--pink); }
        .captivity-game .serif { font-family: var(--font-display); font-style: italic; letter-spacing: -0.05em; }
        .captivity-game .uppercase { text-transform: uppercase; font-size: 10px; font-weight: 700; }
        .captivity-game .divider { border-bottom: 1px solid var(--gray); margin: 10px 0; }
        .captivity-game .cross { position: absolute; pointer-events: none; }
        .captivity-game .cross::before { content: '+'; color: var(--pink); font-size: 14px; }
        .captivity-game .screen {
            display: none;
            min-height: 100vh;
            padding: 20px;
            padding-bottom: 178px;
            flex-direction: column;
        }
        .captivity-game .screen.active { display: flex; }
        .captivity-game .process-screen {
            padding-top: 64px;
            padding-bottom: 132px;
        }
        .captivity-game .monitor-room-screen,
        .captivity-game .inventory-room-screen {
            padding-top: 58px;
            padding-bottom: 34px;
        }
        .captivity-game .process-review-head {
            margin-bottom: 22px;
        }
        .captivity-game .process-review-title {
            font-size: 32px;
            line-height: 0.9;
            margin-top: 8px;
        }
        .captivity-game .process-review-meta {
            border-left: 0.5px solid var(--pink);
            padding-left: 10px;
            margin-bottom: 18px;
        }
        .captivity-game .process-review-body {
            margin: 0 0 26px;
        }
        .captivity-game .ending-card {
            border-left: 0.5px solid var(--pink);
            padding: 4px 0 4px 14px;
            margin-bottom: 24px;
        }
        .captivity-game .ending-title {
            font-size: 16px;
            font-weight: 800;
            margin-bottom: 16px;
        }
        .captivity-game .ending-body {
            margin-bottom: 16px;
        }
        .captivity-game .ending-sync-state {
            color: var(--pink);
        }
        .captivity-game .history-detail-body {
            margin: 0 0 26px;
        }
        .captivity-game .history-detail-meta {
            margin-top: 12px;
        }
        .captivity-game .history-back {
            width: max-content;
            background: transparent;
            border: 0;
            color: var(--pink);
            padding: 0;
            margin: 0 0 18px;
            font-family: var(--font-ui);
            font-size: 11px;
            cursor: pointer;
        }
        .captivity-game .process-mood-title {
            margin-top: 2px;
            margin-bottom: 8px;
            font-size: 10px;
            font-weight: 700;
        }
        .captivity-game .process-mood-title .sub {
            font-size: 7px;
            margin-left: 6px;
        }
        .captivity-game .process-save-btn {
            margin-top: 20px;
            margin-bottom: 78px;
        }
        .captivity-game #selector-screen {
            justify-content: center;
            align-items: center;
            text-align: center;
            background: radial-gradient(circle at center, #222 0%, #121212 100%);
        }
        .captivity-game .selector-title {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 0;
            margin-bottom: 42px;
            font-size: 48px;
            font-weight: 400;
            line-height: 0.86;
        }
        .captivity-game .selector-title span:last-child {
            color: var(--pink);
            margin-left: 34px;
        }
        .captivity-game .identity-card {
            border: 1px solid var(--pink);
            background: transparent;
            color: inherit;
            padding: 40px 20px;
            margin: 10px;
            cursor: pointer;
            width: 80%;
            transition: all 0.3s;
        }
        .captivity-game .identity-card:hover,
        .captivity-game .identity-card:active {
            background: var(--pink);
            color: var(--black);
        }
        .captivity-game .identity-card-title {
            margin-top: 8px;
            font-size: 22px;
            line-height: 1;
        }
        .captivity-game .header {
            margin-bottom: 30px;
            position: relative;
        }
        .captivity-game .day-milestone-copy {
            margin: -18px 0 24px;
            color: #8e888c;
            font-size: 11px;
            font-style: italic;
            line-height: 1.7;
        }
        .captivity-game .title-line {
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 12px;
            margin-top: 10px;
        }
        .captivity-game .title-main {
            flex: 1;
            min-width: 0;
            font-size: 30px;
            line-height: 0.95;
        }
        .captivity-game .time-chip {
            flex: 0 0 auto;
            border-bottom: 1px solid rgba(235, 121, 176, 0.42);
            color: #aaa;
            font-family: var(--font-display);
            font-style: italic;
            font-size: 11px;
            line-height: 1;
            padding-bottom: 4px;
            white-space: nowrap;
        }
        .captivity-game .return-capsule {
            position: fixed;
            top: 12px;
            left: 12px;
            z-index: 520;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            border-radius: 999px;
            border: 1px solid rgba(235, 121, 176, 0.55);
            background: rgba(30, 27, 29, 0.62);
            -webkit-backdrop-filter: blur(10px) saturate(135%);
            backdrop-filter: blur(10px) saturate(135%);
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.22);
            color: var(--pink);
            cursor: pointer;
            opacity: 0.82;
        }
        .captivity-game .return-capsule svg {
            width: 14px;
            height: 14px;
        }
        .captivity-game .return-capsule:active {
            background: var(--pink);
            color: var(--black);
        }
        .captivity-game .subpage-return {
            position: fixed;
            top: 12px;
            left: 12px;
            z-index: 520;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            border-radius: 999px;
            border: 1px solid rgba(235, 121, 176, 0.55);
            background: rgba(30, 27, 29, 0.62);
            -webkit-backdrop-filter: blur(10px) saturate(135%);
            backdrop-filter: blur(10px) saturate(135%);
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.22);
            color: var(--pink);
            cursor: pointer;
            opacity: 0.82;
        }
        .captivity-game .subpage-return svg {
            width: 14px;
            height: 14px;
        }
        .captivity-game .subpage-return:active {
            background: var(--pink);
            color: var(--black);
        }
        .captivity-game .day-big {
            font-size: 80px;
            line-height: 0.8;
            font-weight: 900;
            color: var(--pink);
            opacity: 0.2;
            position: absolute;
            top: -10px;
            left: -10px;
            z-index: -1;
        }
        .captivity-game .header-meta {
            display: grid;
            grid-template-columns: 1fr auto 1fr;
            align-items: baseline;
            border-bottom: 1px solid var(--pink);
            padding-bottom: 5px;
        }
        .captivity-game .header-meta > :first-child {
            grid-column: 2;
            text-align: center;
        }
        .captivity-game .header-meta > :last-child {
            grid-column: 3;
            justify-self: end;
        }
        .captivity-game .identity-switch {
            display: inline-flex;
            align-items: baseline;
            border: 0;
            background: transparent;
            color: var(--white);
            padding: 0;
            cursor: pointer;
        }
        .captivity-game .identity-switch:active {
            color: var(--pink);
        }
        .captivity-game .identity-switch:disabled {
            cursor: default;
            opacity: 0.45;
        }
        .captivity-game .status-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 30px;
        }
        .captivity-game .status-item {
            display: flex;
            flex-direction: column;
        }
        .captivity-game .status-label {
            display: flex;
            justify-content: space-between;
            font-size: 10px;
            margin-bottom: 4px;
        }
        .captivity-game .bar-container {
            height: 2px;
            background: var(--gray);
            width: 100%;
            position: relative;
        }
        .captivity-game .bar-fill {
            height: 100%;
            background: var(--pink);
        }
        .captivity-game .tag-cloud {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 20px;
        }
        .captivity-game .status-tag {
            border: 1px solid var(--pink);
            padding: 4px 8px;
            font-size: 11px;
            color: var(--pink);
            background: transparent;
        }
        .captivity-game .status-atmosphere-copy {
            margin: -8px 0 28px;
            color: #aaa4a8;
            font-size: 11px;
            font-style: italic;
            line-height: 1.7;
        }
        .captivity-game .panel-title {
            font-size: 16px;
            font-weight: 800;
            margin-bottom: 15px;
            display: flex;
            align-items: baseline;
        }
        .captivity-game .panel-title .sub { font-size: 8px; margin-left: 10px; color: var(--pink); }
        .captivity-game .response-mood-title {
            margin-top: 24px;
        }
        .captivity-game .action-card {
            background: #1a1a1a;
            border-left: 3px solid var(--pink);
            padding: 15px;
            margin-bottom: 20px;
        }
        .captivity-game .planner-choice-copy,
        .captivity-game .night-choice-copy,
        .captivity-game .runtime-bridge-copy {
            color: #918b8f;
            font-size: 11px;
            font-style: italic;
            line-height: 1.7;
        }
        .captivity-game .planner-choice-copy {
            margin: 11px 0 2px;
        }
        .captivity-game .night-choice-copy {
            margin: 11px 2px 18px;
        }
        .captivity-game .runtime-bridge-copy {
            margin: -7px 0 20px;
        }
        .captivity-game .history-list-item {
            display: block;
            width: 100%;
            color: var(--white);
            text-align: left;
            cursor: pointer;
        }
        .captivity-game .history-title-row {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 14px;
        }
        .captivity-game .history-title-row .panel-title {
            margin-bottom: 0;
        }
        .captivity-game .history-day-select {
            flex: 0 0 auto;
            width: 104px;
            height: 30px;
            margin: 0;
            border: 0.5px solid rgba(255, 255, 255, 0.28);
            background: #1a1a1a;
            color: var(--white);
            padding: 0 24px 0 8px;
            font-size: 10px;
        }
        .captivity-game .history-day-group {
            margin-bottom: 20px;
        }
        .captivity-game .history-day-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
            border-bottom: 0.5px solid rgba(235, 121, 176, 0.5);
            color: var(--pink);
            padding-bottom: 5px;
            font-family: var(--font-display);
            font-size: 11px;
            font-style: italic;
        }
        .captivity-game .history-list-item:active {
            background: var(--gray);
        }
        .captivity-game .action-card.faded {
            opacity: 0.5;
        }
        .captivity-game .action-card.white-line {
            border-left-color: white;
        }
        .captivity-game .captivity-slot-collapsed {
            display: block;
            width: 100%;
            color: var(--white);
            text-align: left;
        }
        .captivity-game .slot-heading {
            display: block;
            width: 100%;
            margin-bottom: 5px;
            background: transparent;
            border: 0;
            color: inherit;
            text-align: left;
        }
        .captivity-game .slot-tools-toggle {
            width: 100%;
            margin-top: 12px;
            border-width: 0.5px;
            text-align: center;
        }
        .captivity-game .slot-line-input {
            min-height: 58px;
        }
        .captivity-game .action-metadata {
            font-size: 10px;
            color: #666;
            margin-bottom: 8px;
            text-transform: uppercase;
        }
        .captivity-game .intervention-title {
            margin-top: 24px;
        }
        .captivity-game .special-section-title,
        .captivity-game .monitor-section-title {
            margin-top: 22px;
            margin-bottom: 12px;
        }
        .captivity-game .section-meta {
            margin-top: 14px;
        }
        .captivity-game .special-room-entry {
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            background: #1a1a1a;
            border: 0;
            border-left: 3px solid var(--pink);
            color: var(--white);
            padding: 15px;
            margin-bottom: 22px;
            text-align: left;
            cursor: pointer;
        }
        .captivity-game .special-room-entry .panel-title {
            margin-bottom: 8px;
        }
        .captivity-game .special-room-arrow {
            flex: 0 0 auto;
            color: var(--pink);
            font-size: 28px;
            line-height: 1;
        }
        .captivity-game .special-room-entry:disabled {
            cursor: default;
            opacity: 0.45;
        }
        .captivity-game .monitor-console {
            margin-bottom: 22px;
        }
        .captivity-game .monitor-screen {
            position: relative;
            overflow: hidden;
            aspect-ratio: 4 / 3;
            min-height: 0;
            padding: 14px;
            background:
                linear-gradient(rgba(235, 121, 176, 0.06) 1px, transparent 1px),
                #0d0d0d;
            background-size: 100% 9px, auto;
            border: 0.5px solid rgba(255, 255, 255, 0.3);
            border-left: 3px solid var(--pink);
        }
        .captivity-game .monitor-screen::after {
            content: "";
            position: absolute;
            inset: 0;
            background: radial-gradient(circle at center, transparent 0, rgba(0, 0, 0, 0.5) 74%);
            pointer-events: none;
        }
        .captivity-game .monitor-screen-top {
            position: relative;
            z-index: 1;
            display: flex;
            justify-content: space-between;
            color: var(--pink);
            font-size: 9px;
            font-weight: 800;
            letter-spacing: 0;
        }
        .captivity-game .monitor-screen-body {
            position: relative;
            z-index: 1;
            height: calc(100% - 13px);
            display: flex;
            flex-direction: column;
            justify-content: center;
            text-align: center;
        }
        .captivity-game .monitor-controls {
            grid-template-columns: repeat(3, minmax(0, 1fr));
            margin-top: 10px;
        }
        .captivity-game .monitor-record-title .panel-title {
            margin-top: 20px;
            margin-bottom: 10px;
        }
        .captivity-game .monitor-record-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
            margin-bottom: 20px;
        }
        .captivity-game .monitor-record-item {
            background: #171717;
            border-left: 1px solid rgba(235, 121, 176, 0.78);
            padding: 12px;
        }
        .captivity-game .monitor-live-scene {
            max-width: 420px;
            margin: 10px auto 0;
            color: #b0a9ad;
            font-size: 10px;
            font-style: italic;
            line-height: 1.6;
        }
        .captivity-game .monitor-record-scene {
            color: #8f898d;
            font-style: italic;
            line-height: 1.7;
        }
        .captivity-game .event-main {
            font-size: 14px;
            margin-bottom: 10px;
            white-space: pre-wrap;
        }
        .captivity-game .event-sub {
            font-size: 12px;
            color: #aaa;
            line-height: 1.5;
            white-space: pre-wrap;
        }
        .captivity-game .night-condition-caption {
            margin-top: 6px;
            color: #777;
        }
        .captivity-game .process-text {
            font-family: var(--font-display);
            font-style: normal;
            letter-spacing: 0;
            font-size: 12px;
            line-height: 1.65;
            color: #ddd;
            white-space: pre-wrap;
        }
        .captivity-game .btn-group {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
            gap: 5px;
            margin-top: 15px;
        }
        .captivity-game .mood-grid,
        .captivity-game .response-grid {
            grid-template-columns: repeat(5, minmax(0, 1fr));
        }
        .captivity-game .content-grid {
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
        .captivity-game .night-detail-grid {
            grid-template-columns: repeat(4, minmax(0, 1fr));
        }
        .captivity-game .content-grid .btn {
            min-height: 38px;
            padding: 8px 4px;
            font-size: 10px;
            line-height: 1.25;
        }
        .captivity-game .mood-grid .btn,
        .captivity-game .response-grid .btn {
            padding: 9px 4px;
            font-size: 10px;
        }
        .captivity-game .sync-action-bar {
            position: fixed;
            left: 0;
            right: 0;
            bottom: 38px;
            z-index: 510;
            margin-top: 0;
            padding: 8px 14px 10px;
            background: linear-gradient(to top, var(--black) 70%, rgba(18, 18, 18, 0));
            border-top: 0;
        }
        .captivity-game .btn {
            background: transparent;
            border: 0.5px solid rgba(255, 255, 255, 0.58);
            color: var(--white);
            padding: 10px;
            text-align: center;
            cursor: pointer;
            font-size: 11px;
            text-transform: uppercase;
        }
        .captivity-game .btn.active,
        .captivity-game .btn:active {
            background: var(--pink);
            color: var(--black);
            border-color: var(--pink);
        }
        .captivity-game .btn:disabled {
            cursor: default;
            opacity: 0.45;
        }
        .captivity-game .sync-action-bar .btn {
            border-width: 0.5px;
            border-color: rgba(255, 255, 255, 0.28);
            color: rgba(255, 255, 255, 0.9);
        }
        .captivity-game .tool-groups {
            display: grid;
            gap: 12px;
            margin-top: 15px;
        }
        .captivity-game .tool-group {
            min-width: 0;
        }
        .captivity-game .tool-category-title {
            margin-bottom: 4px;
            color: rgba(255, 255, 255, 0.62);
        }
        .captivity-game .tool-grid {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 5px;
        }
        .captivity-game .tool-tile,
        .captivity-game .warehouse-tile {
            background: rgba(255, 255, 255, 0.02);
            border: 0.5px solid rgba(255, 255, 255, 0.26);
            color: var(--white);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            position: relative;
            overflow: hidden;
        }
        .captivity-game .tool-tile {
            min-width: 0;
            height: 68px;
            padding: 5px 2px 6px;
            gap: 2px;
            font-size: 9px;
            line-height: 1.1;
        }
        .captivity-game .tool-tile::after,
        .captivity-game .warehouse-tile::after {
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(145deg, rgba(255, 255, 255, 0.08), transparent 48%, rgba(235, 121, 176, 0.1));
            opacity: 0.6;
            pointer-events: none;
        }
        .captivity-game .tool-tile.active,
        .captivity-game .warehouse-tile.active {
            border-color: rgba(235, 121, 176, 0.9);
            background: rgba(235, 121, 176, 0.14);
        }
        .captivity-game .tool-tile.recommended:not(.active) {
            border-color: rgba(235, 121, 176, 0.46);
        }
        .captivity-game .tool-tile:disabled,
        .captivity-game .warehouse-tile:disabled {
            cursor: default;
            opacity: 0.45;
        }
        .captivity-game .painted-icon {
            width: 36px;
            height: 36px;
            display: block;
            filter: drop-shadow(0 5px 8px rgba(0, 0, 0, 0.28));
        }
        .captivity-game .painted-icon svg {
            width: 100%;
            height: 100%;
            display: block;
        }
        .captivity-game .paint-fill {
            stroke: rgba(255, 255, 255, 0.22);
            stroke-width: 1.2;
            stroke-linejoin: round;
        }
        .captivity-game .paint-fill.rose { fill: rgba(235, 121, 176, 0.62); }
        .captivity-game .paint-fill.dark { fill: rgba(46, 39, 45, 0.88); }
        .captivity-game .paint-fill.metal { fill: rgba(207, 207, 214, 0.66); }
        .captivity-game .paint-fill.pink { fill: rgba(235, 121, 176, 0.78); }
        .captivity-game .paint-fill.light { fill: rgba(255, 233, 244, 0.72); }
        .captivity-game .paint-fill.flame { fill: rgba(255, 190, 111, 0.86); }
        .captivity-game .paint-stroke {
            fill: none;
            stroke: rgba(255, 235, 246, 0.78);
            stroke-width: 3;
            stroke-linecap: round;
            stroke-linejoin: round;
        }
        .captivity-game .paint-stroke.pink { stroke: rgba(235, 121, 176, 0.88); }
        .captivity-game .paint-stroke.dark { stroke: rgba(44, 37, 43, 0.9); }
        .captivity-game .paint-stroke.metal { stroke: rgba(212, 212, 218, 0.72); }
        .captivity-game .paint-stroke.thin { stroke-width: 2; }
        .captivity-game .paint-stroke.thick { stroke-width: 5; }
        .captivity-game .paint-light {
            fill: none;
            stroke: rgba(255, 255, 255, 0.68);
            stroke-width: 1.5;
            stroke-linecap: round;
        }
        .captivity-game .warehouse-panel {
            margin-top: 0;
        }
        .captivity-game .warehouse-title-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 12px;
        }
        .captivity-game .warehouse-module-title {
            margin: 0;
        }
        .captivity-game .warehouse-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px;
            margin-top: 10px;
        }
        .captivity-game .warehouse-tile {
            min-height: 108px;
            gap: 4px;
            padding: 10px 6px;
        }
        .captivity-game .warehouse-tile .painted-icon {
            width: 44px;
            height: 44px;
        }
        .captivity-game .warehouse-name {
            position: relative;
            z-index: 1;
            font-size: 12px;
            font-weight: 800;
        }
        .captivity-game .warehouse-use {
            position: relative;
            z-index: 1;
            max-width: 100%;
            color: #aaa;
            font-size: 9px;
            line-height: 1.25;
            text-align: center;
        }
        .captivity-game .warehouse-state {
            position: relative;
            z-index: 1;
            min-width: 42px;
            padding: 2px 5px;
            border: 1px solid rgba(255, 255, 255, 0.16);
            font-size: 10px;
            color: #aaa;
            text-align: center;
        }
        .captivity-game .warehouse-tile.active .warehouse-state {
            color: var(--pink);
            border-color: rgba(235, 121, 176, 0.5);
            background: rgba(235, 121, 176, 0.08);
        }
        .captivity-game .room-inventory-tile {
            cursor: default;
        }
        .captivity-game .room-inventory-panel .monitor-record-item {
            margin-top: 10px;
        }
        .captivity-game .warehouse-tile.selected {
            border-color: rgba(235, 121, 176, 0.9);
        }
        .captivity-game .warehouse-menu {
            margin-top: 10px;
            padding: 10px;
            border-left: 2px solid var(--pink);
            background: rgba(255, 255, 255, 0.035);
        }
        .captivity-game .warehouse-menu-title {
            font-size: 12px;
            font-weight: 900;
            color: var(--white);
        }
        .captivity-game .warehouse-menu-state {
            margin-top: 3px;
            font-size: 10px;
            color: #aaa;
        }
        .captivity-game .warehouse-menu-use {
            margin-top: 4px;
            color: #aaa;
            font-size: 10px;
        }
        .captivity-game .warehouse-actions {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 6px;
            margin-top: 10px;
        }
        .captivity-game .warehouse-actions .btn {
            padding: 10px 8px;
            border-width: 0.5px;
        }
        .captivity-game .warehouse-voice-input {
            min-height: 84px;
            margin-top: 10px;
            font-size: 12px;
        }
        .captivity-game .warehouse-voice-current {
            margin-top: 10px;
            padding: 10px 12px;
            border-left: 2px solid var(--pink);
            color: var(--white);
            font-size: 12px;
            line-height: 1.7;
            white-space: pre-wrap;
        }
        .captivity-game .scene-transition-overlay {
            position: fixed;
            inset: 0;
            z-index: 950;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            padding: 28px;
            border: 0;
            background: rgba(8, 8, 8, 0.9);
            color: var(--white);
            cursor: pointer;
            overflow: hidden;
            text-align: center;
            animation: captivitySceneVeil var(--scene-duration, 3400ms) linear both;
        }
        .captivity-game .scene-transition-overlay.night {
            background: rgba(2, 2, 3, 0.96);
        }
        .captivity-game .scene-transition-overlay.special {
            background: rgba(12, 5, 8, 0.96);
        }
        .captivity-game .scene-transition-scan {
            position: absolute;
            left: 15%;
            top: 12%;
            width: 70%;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(235, 121, 176, 0.62), transparent);
            box-shadow: 0 0 14px rgba(235, 121, 176, 0.28);
            animation: captivitySceneScan 1.65s cubic-bezier(0.22, 1, 0.36, 1) both;
            will-change: transform, opacity;
        }
        .captivity-game .scene-transition-content {
            display: flex;
            flex-direction: column;
            align-items: center;
            width: min(100%, 560px);
        }
        .captivity-game .scene-transition-kicker {
            color: var(--pink);
            font-size: 9px;
            letter-spacing: 0;
            animation: captivitySceneKicker 0.52s cubic-bezier(0.22, 1, 0.36, 1) both;
        }
        .captivity-game .scene-transition-title {
            margin-top: 12px;
            font-size: 24px;
            font-style: italic;
            line-height: 1.1;
        }
        .captivity-game .scene-transition-body {
            max-width: 460px;
            margin-top: 16px;
            color: #cfcacf;
            font-size: 12px;
            line-height: 1.9;
            opacity: 0;
            transform: translate3d(0, 7px, 0);
            will-change: transform, opacity;
            animation: captivitySceneBody 0.72s cubic-bezier(0.22, 1, 0.36, 1) forwards;
        }
        .captivity-game .scene-transition-char {
            display: inline-block;
            opacity: 0;
            transform: translate3d(0, 6px, 0) scale(0.985);
            backface-visibility: hidden;
            will-change: transform, opacity;
            animation: captivitySceneCharacter 0.72s cubic-bezier(0.22, 1, 0.36, 1) forwards;
        }
        .captivity-game .scene-transition-char.space {
            width: 0.32em;
        }
        @keyframes captivitySceneVeil {
            0% { opacity: 0; }
            9%, 90% { opacity: 1; }
            100% { opacity: 0; }
        }
        @keyframes captivitySceneScan {
            0% { opacity: 0; transform: translate3d(0, -18vh, 0); }
            18% { opacity: 0.72; }
            72% { opacity: 0.32; }
            100% { opacity: 0; transform: translate3d(0, 76vh, 0); }
        }
        @keyframes captivitySceneKicker {
            from { opacity: 0; transform: translate3d(0, 5px, 0); }
            to { opacity: 1; transform: translate3d(0, 0, 0); }
        }
        @keyframes captivitySceneBody {
            from { opacity: 0; transform: translate3d(0, 7px, 0); }
            to { opacity: 1; transform: translate3d(0, 0, 0); }
        }
        @keyframes captivitySceneCharacter {
            from { opacity: 0; transform: translate3d(0, 6px, 0) scale(0.985); }
            to { opacity: 1; transform: translate3d(0, 0, 0) scale(1); }
        }
        .captivity-game .bell-voice-overlay {
            position: fixed;
            inset: 0;
            z-index: 930;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
            background: rgba(0, 0, 0, 0.82);
            backdrop-filter: blur(8px);
        }
        .captivity-game .bell-voice-dialog {
            width: min(100%, 420px);
            padding: 24px 22px 20px;
            border: 0.5px solid rgba(255, 255, 255, 0.32);
            border-left: 3px solid var(--pink);
            background: #151515;
        }
        .captivity-game .item-reveal-dialog {
            animation: captivityItemRevealIn 0.34s ease both;
        }
        .captivity-game .item-reveal-motif {
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            height: 32px;
            margin: 14px 0 2px;
            color: var(--pink);
        }
        .captivity-game .item-reveal-motif span {
            display: block;
            width: 3px;
            height: 8px;
            background: currentColor;
        }
        .captivity-game .item-reveal-book .item-reveal-motif,
        .captivity-game .item-reveal-notebook .item-reveal-motif {
            perspective: 120px;
        }
        .captivity-game .item-reveal-book .item-reveal-motif span,
        .captivity-game .item-reveal-notebook .item-reveal-motif span {
            width: 22px;
            height: 26px;
            border: 1px solid rgba(235, 121, 176, 0.72);
            background: transparent;
        }
        .captivity-game .item-reveal-book .item-reveal-motif span:nth-child(n+3),
        .captivity-game .item-reveal-notebook .item-reveal-motif span:nth-child(n+3) {
            display: none;
        }
        .captivity-game .item-reveal-book .item-reveal-motif span:nth-child(2) {
            transform-origin: left center;
            animation: captivityPageTurn 0.8s ease both;
        }
        .captivity-game .item-reveal-notebook .item-reveal-motif span:nth-child(2) {
            width: 14px;
            height: 1px;
            border: 0;
            background: var(--pink);
            animation: captivityLineWrite 0.72s ease both;
        }
        .captivity-game .item-reveal-switch .item-reveal-motif,
        .captivity-game .item-reveal-tablet .item-reveal-motif {
            width: 82px;
            margin-left: auto;
            margin-right: auto;
            border: 1px solid rgba(235, 121, 176, 0.72);
            animation: captivityScreenWake 0.7s ease both;
        }
        .captivity-game .item-reveal-switch .item-reveal-motif {
            width: 108px;
        }
        .captivity-game .item-reveal-switch .item-reveal-motif::after {
            content: "GAME START";
            color: var(--pink);
            font-size: 8px;
            font-weight: 700;
            letter-spacing: 0;
            opacity: 0;
            animation: captivityGameStart 0.46s 0.38s ease forwards;
        }
        .captivity-game .item-reveal-switch .item-reveal-motif span,
        .captivity-game .item-reveal-tablet .item-reveal-motif span {
            display: none;
        }
        .captivity-game .item-reveal-music_player .item-reveal-motif span,
        .captivity-game .item-reveal-call_bell .item-reveal-motif span {
            animation: captivityWave 0.72s ease-in-out infinite alternate;
        }
        .captivity-game .item-reveal-music_player .item-reveal-motif span:nth-child(2),
        .captivity-game .item-reveal-call_bell .item-reveal-motif span:nth-child(2) { animation-delay: 0.1s; }
        .captivity-game .item-reveal-music_player .item-reveal-motif span:nth-child(3),
        .captivity-game .item-reveal-call_bell .item-reveal-motif span:nth-child(3) { animation-delay: 0.2s; }
        .captivity-game .item-reveal-music_player .item-reveal-motif span:nth-child(4),
        .captivity-game .item-reveal-call_bell .item-reveal-motif span:nth-child(4) { animation-delay: 0.3s; }
        .captivity-game .item-reveal-night_light .item-reveal-motif {
            width: 30px;
            margin-left: auto;
            margin-right: auto;
            border: 1px solid var(--pink);
            background: rgba(235, 121, 176, 0.28);
            box-shadow: 0 0 18px rgba(235, 121, 176, 0.45);
            animation: captivityLightWake 0.9s ease-in-out infinite alternate;
        }
        .captivity-game .item-reveal-night_light .item-reveal-motif span,
        .captivity-game .item-reveal-pillow .item-reveal-motif span { display: none; }
        .captivity-game .item-reveal-pillow .item-reveal-motif {
            width: 58px;
            margin-left: auto;
            margin-right: auto;
            border-bottom: 1px dashed var(--pink);
            animation: captivityStitch 0.75s steps(6, end) both;
        }
        @keyframes captivityItemRevealIn {
            from { opacity: 0; transform: translateY(7px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes captivityPageTurn {
            from { transform: rotateY(0deg); }
            to { transform: rotateY(-58deg); }
        }
        @keyframes captivityLineWrite {
            from { transform: scaleX(0); }
            to { transform: scaleX(1); }
        }
        @keyframes captivityScreenWake {
            0% { opacity: 0.2; box-shadow: none; }
            45% { opacity: 1; box-shadow: 0 0 20px rgba(235, 121, 176, 0.34); }
            100% { opacity: 0.82; box-shadow: 0 0 8px rgba(235, 121, 176, 0.18); }
        }
        @keyframes captivityGameStart {
            from { opacity: 0; transform: scale(0.9); filter: blur(2px); }
            to { opacity: 1; transform: scale(1); filter: blur(0); }
        }
        @keyframes captivityWave {
            from { height: 5px; opacity: 0.45; }
            to { height: 24px; opacity: 1; }
        }
        @keyframes captivityLightWake {
            from { opacity: 0.46; box-shadow: 0 0 4px rgba(235, 121, 176, 0.16); }
            to { opacity: 1; box-shadow: 0 0 24px rgba(235, 121, 176, 0.58); }
        }
        @keyframes captivityStitch {
            from { clip-path: inset(0 100% 0 0); }
            to { clip-path: inset(0 0 0 0); }
        }
        @media (prefers-reduced-motion: reduce) {
            .captivity-game .scene-transition-overlay,
            .captivity-game .scene-transition-scan,
            .captivity-game .scene-transition-content,
            .captivity-game .scene-transition-kicker,
            .captivity-game .scene-transition-body,
            .captivity-game .scene-transition-char,
            .captivity-game .item-reveal-dialog,
            .captivity-game .item-reveal-motif,
            .captivity-game .item-reveal-motif::after,
            .captivity-game .item-reveal-motif span {
                animation: none !important;
            }
            .captivity-game .scene-transition-body {
                opacity: 1;
                transform: none;
            }
            .captivity-game .item-reveal-switch .item-reveal-motif::after {
                opacity: 1;
            }
        }
        .captivity-game .bell-voice-kicker {
            margin-bottom: 8px;
            color: #777;
            font-size: 10px;
        }
        .captivity-game .bell-voice-line {
            margin: 24px 0 8px;
            color: var(--white);
            font-size: 13px;
            font-style: italic;
            line-height: 1.9;
            white-space: pre-wrap;
        }
        .captivity-game .bell-voice-continue {
            display: block;
            width: auto;
            min-width: 108px;
            margin: 14px auto 0;
            padding: 9px 24px;
            border: 0.5px solid rgba(255, 255, 255, 0.72);
            background: transparent;
            color: var(--white);
            font-size: 11px;
        }
        .captivity-game .btn-large {
            width: 100%;
            padding: 15px;
            margin-top: 20px;
            background: var(--white);
            color: var(--black);
            font-weight: 900;
        }
        .captivity-game textarea,
        .captivity-game input,
        .captivity-game select {
            width: 100%;
            background: var(--gray);
            border: none;
            color: var(--white);
            padding: 10px;
            font-family: var(--font-ui);
            margin-top: 10px;
            resize: none;
        }
        .captivity-game select,
        .captivity-game input.compact {
            background: transparent;
            border: 1px solid #333;
            padding: 5px;
        }
        .captivity-game option {
            color: var(--black);
        }
        .captivity-game .form-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        .captivity-game .escape-room-row {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            align-items: start;
            gap: 10px;
        }
        .captivity-game .compact-field {
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: 5px;
        }
        .captivity-game .compact-field > span {
            color: #aaa;
            font-size: 9px;
            font-weight: 800;
            line-height: 1;
        }
        .captivity-game .compact-field input.compact,
        .captivity-game .compact-field select.compact {
            height: 34px;
            margin-top: 0;
        }
        .captivity-game .escape-room-select {
            width: 100%;
        }
        .captivity-game .form-grid select {
            margin-top: 0;
        }
        .captivity-game .wait-overlay {
            position: fixed;
            inset: 0;
            background: var(--black);
            z-index: 1000;
            display: none;
            padding: 40px;
            flex-direction: column;
            justify-content: center;
        }
        .captivity-game .wait-overlay.active { display: flex; }
        .captivity-game .wait-scene-copy {
            max-width: 460px;
            margin-bottom: 18px;
            color: #aaa4a8;
            font-size: 12px;
            font-style: italic;
            line-height: 1.7;
        }
        .captivity-game .escape-choice-overlay {
            position: fixed;
            inset: 0;
            z-index: 900;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 22px;
            background: rgba(0, 0, 0, 0.76);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
        }
        .captivity-game .escape-choice-dialog {
            width: min(100%, 430px);
            max-height: calc(100dvh - 44px);
            overflow-y: auto;
            padding: 24px 20px 20px;
            background: #151515;
            border: 0.5px solid #555;
            border-left: 3px solid var(--pink);
        }
        .captivity-game .escape-choice-title {
            margin-bottom: 18px;
        }
        .captivity-game .escape-warning {
            margin-top: 12px;
            color: var(--pink);
            font-size: 10px;
        }
        .captivity-game .escape-choice-actions {
            margin-top: 18px;
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
        .captivity-game .escape-confirm-prompt {
            margin-top: 12px;
            color: #e0525c;
            font-size: 11px;
            font-weight: 700;
        }
        .captivity-game .escape-sting-dialog {
            min-height: 132px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .captivity-game .escape-sting-text {
            color: #e0525c;
            font-family: var(--font-display);
            font-size: 20px;
            font-style: italic;
            font-weight: 800;
        }
        .captivity-game .recapture-rules-review-overlay {
            position: fixed;
            inset: 0;
            z-index: 920;
            overflow-y: auto;
            padding: 72px 22px 40px;
            background: var(--black);
        }
        .captivity-game .recapture-rules-review {
            width: min(100%, 430px);
            margin: 0 auto;
        }
        .captivity-game .recapture-rules-review-list {
            display: grid;
            gap: 8px;
            margin: 22px 0;
        }
        .captivity-game .recapture-rules-review-item {
            padding: 13px 14px;
            border-left: 2px solid var(--pink);
            background: #191919;
            color: #eee;
            font-size: 13px;
            line-height: 1.45;
        }
        .captivity-game .recapture-rules-review .btn {
            width: 100%;
        }
        .captivity-game .loading-animation {
            width: 40px;
            height: 40px;
            border: 1px solid var(--pink);
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 20px;
            animation: captivityRotate 2s infinite linear;
        }
        @keyframes captivityRotate { 100% { transform: rotate(90deg); } }
        .captivity-game .footer {
            position: fixed;
            bottom: 0;
            left: 0;
            width: 100%;
            background: var(--black);
            border-top: 1px solid var(--gray);
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            padding: 10px 0;
            z-index: 500;
        }
        .captivity-game .footer-item {
            text-align: center;
            font-size: 10px;
            text-transform: uppercase;
            opacity: 0.6;
            background: transparent;
            border: 0;
            color: var(--white);
        }
        .captivity-game .footer-item.active { opacity: 1; color: var(--pink); }
        .captivity-game .coord { font-size: 9px; color: #444; position: fixed; }
        .captivity-game .vertical-text {
            writing-mode: vertical-rl;
            position: fixed;
            right: 5px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 9px;
            color: #444;
            letter-spacing: 0.2em;
        }
        `})]})}function Si({stats:t,mood:i,flags:a=[],role:s}){return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"status-grid",children:[ra.map(o=>{const l=Me(t[o.key]);return e.jsxs("div",{className:"status-item",children:[e.jsxs("div",{className:"status-label",children:[e.jsx("span",{children:o.label}),e.jsxs("span",{children:[l,"%"]})]}),e.jsx("div",{className:"bar-container",children:e.jsx("div",{className:"bar-fill",style:{width:`${l}%`}})})]},o.key)}),e.jsxs("div",{className:"status-item",children:[e.jsxs("div",{className:"status-label",children:[e.jsx("span",{children:"心情"}),e.jsx("span",{children:i||"未选"})]}),e.jsx("div",{className:"bar-container",children:e.jsx("div",{className:"bar-fill",style:{width:i?"66%":"0%"}})})]})]}),a.length?e.jsx("div",{className:"tag-cloud status-flags",children:a.map(o=>e.jsx("span",{className:"status-tag",title:o.prompt,children:o.label},o.id||o.label))}):null,e.jsx("div",{className:"serif status-atmosphere-copy",children:ba(t,i,s,a)})]})}function Za({view:t}){return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["对方状态 ",e.jsx("span",{className:"sub",children:t.captive_name||Ca(t.captive)})]}),e.jsx(Si,{stats:t.stats||{},mood:t.mood,flags:t.status_flags,role:"captor"})]})}function Ka({slots:t,singleAction:i=!1,intensityCap:a,disabled:s,onSlotChange:o,onToggle:l,onSubmit:r}){const[d,u]=_.useState(()=>new Set([0])),[b,j]=_.useState(()=>new Set);function f(h){u(v=>{const x=new Set(v);return x.has(h)?x.delete(h):x.add(h),x.size||x.add(h),x})}function k(h){j(v=>{const x=new Set(v);return x.has(h)?x.delete(h):x.add(h),x})}const S=new Set(t.map(h=>h.action));return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:[i?"回来之后":"今日安排"," ",e.jsx("span",{className:"sub",children:i?"RETURN":"SCHEDULE"})]}),t.map((h,v)=>{const x=d.has(v),C=i?"回来后":v===0?"早间":v===1?"午后":"傍晚",P=b.has(v),R=mt[h.action]||[],N=h.action==="training"||h.modifiers.includes("training");return x?e.jsxs("div",{className:`action-card ${v===0?"white-line":""}`,children:[e.jsx("button",{className:"slot-heading",type:"button",disabled:s,onClick:()=>f(v),children:e.jsxs("span",{className:"uppercase pink-text",children:["SLOT ",String(v+1).padStart(2,"0")," - ",C]})}),e.jsxs("div",{className:"form-grid",children:[e.jsx("select",{value:h.action,disabled:s,onChange:g=>o(v,{action:g.target.value}),children:ct.map(g=>e.jsxs("option",{value:g.id,disabled:g.id!==h.action&&S.has(g.id),children:["行动类型: ",g.label]},g.id))}),e.jsx("select",{value:h.intensity,disabled:s,onChange:g=>o(v,{intensity:g.target.value}),children:It.map(g=>e.jsxs("option",{value:g.id,disabled:g.id==="heavy"&&a==="medium",children:["力度: ",g.label]},g.id))})]}),e.jsx("div",{className:"serif planner-choice-copy",children:da[h.action]||"这一段会按当前选择写进今日安排。"}),e.jsx("button",{className:`btn slot-tools-toggle ${P?"active":""}`,type:"button",disabled:s,onClick:()=>k(v),children:P?"收起详细设置":"选择具体内容/道具"}),P?e.jsxs(e.Fragment,{children:[e.jsx("textarea",{className:"slot-line-input",value:h.line,disabled:s,placeholder:"可选：要说的话...",onChange:g=>o(v,{line:g.target.value})}),h.action==="feeding"?e.jsxs("div",{className:"form-grid",children:[e.jsx("select",{value:h.feedingSource,disabled:s,onChange:g=>o(v,{feedingSource:g.target.value}),children:di.map(g=>e.jsxs("option",{value:g.id,children:["食物: ",g.label]},g.id))}),e.jsx("select",{value:h.feedingAdditive,disabled:s,onChange:g=>o(v,{feedingAdditive:g.target.value}),children:mi.map(g=>e.jsx("option",{value:g.id,children:g.label},g.id))})]}):null,R.length?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"action-metadata section-meta",children:"具体内容"}),e.jsx("div",{className:"btn-group content-grid",children:R.map(g=>e.jsx(G,{active:h.contents.includes(g.id),disabled:s||!h.contents.includes(g.id)&&h.contents.length>=3,onClick:()=>l(v,"contents",g.id),children:g.label},g.id))})]}):null,e.jsx("div",{className:"action-metadata section-meta",children:"附加项"}),e.jsx("div",{className:"btn-group",children:li.filter(g=>g.id!=="training"||h.action!=="training").map(g=>e.jsx(G,{active:h.modifiers.includes(g.id),disabled:s,onClick:()=>l(v,"modifiers",g.id),children:g.label},g.id))}),N?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"action-metadata section-meta",children:"调教内容"}),e.jsx("div",{className:"btn-group content-grid",children:ut.filter(g=>!oi.has(g.id)).map(g=>e.jsx(G,{active:h.trainingContents.includes(g.id),disabled:s||!h.trainingContents.includes(g.id)&&h.trainingContents.length>=3,onClick:()=>l(v,"trainingContents",g.id),children:g.label},g.id))})]}):null,e.jsx("div",{className:"action-metadata section-meta",children:"道具"}),e.jsx(zt,{selected:h.tools,disabled:s,context:{action:h.action,modifiers:h.modifiers,contents:h.contents,trainingContents:h.trainingContents},onToggle:g=>l(v,"tools",g)})]}):null]},v):e.jsxs("div",{className:"action-card faded captivity-slot-collapsed",role:"button",tabIndex:s?-1:0,"aria-disabled":s,onClick:()=>{s||f(v)},onKeyDown:g=>{!s&&(g.key==="Enter"||g.key===" ")&&f(v)},children:[e.jsxs("div",{className:"uppercase pink-text",style:{marginBottom:5},children:["SLOT ",String(v+1).padStart(2,"0")," - ",C]}),e.jsx("div",{className:"uppercase",children:"点击配置..."})]},v)}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:s,onClick:r,children:i?"确定这个行为":"下发所有指令"})]})}function Ja({role:t,view:i,pending:a,currentEvent:s,waitingForDu:o,userIsPendingActor:l,canChooseNight:r,availableNightActions:d,nightCondition:u,response:b,responseMood:j,responseLine:f,reactionMood:k,reactionLine:S,nightAction:h,nightDetail:v,nightNote:x,nightLine:C,monitorNote:P,interventionIntent:R,interventionModifiers:N,interventionTrainingContents:g,interventionTools:Z,interventionLine:se,recaptureRules:O,recaptureFollowup:Re,recaptureIntensity:Ve,recaptureModifiers:Ie,recaptureTrainingContents:gt,recaptureTools:fe,recaptureLine:Ge,lastText:$e,disabled:U,onResponseChange:pe,onResponseMoodChange:ht,onResponseLineChange:be,onReactionMoodChange:Ue,onReactionLineChange:je,onNightActionChange:xt,onNightDetailChange:Ne,onNightNoteChange:Be,onNightLineChange:B,onMonitorNoteChange:Y,onInterventionIntentChange:vt,onInterventionModifierToggle:we,onInterventionTrainingContentToggle:re,onInterventionToolToggle:te,onInterventionLineChange:ce,onRecaptureRuleToggle:ie,onRecaptureFollowupChange:He,onRecaptureIntensityChange:_t,onRecaptureModifierToggle:yt,onRecaptureTrainingContentToggle:ft,onRecaptureToolToggle:Ye,onRecaptureLineChange:bt,onSubmitResponse:We,onSubmitMood:qe,onSubmitNightAction:de,onAckBellVoice:jt,onAckItemSecret:K,onAdvance:Nt,onChooseEscape:Oe,onConfirmRecaptureRules:wt,onSubmitRecaptureRules:me,onSubmitRecaptureFollowup:kt,onOpenMonitor:ue,onHandleMonitor:ke,onRefresh:ge}){var q,_e,I,Ce,X,Je,V,w,L,Xe,Le;const $=String((a==null?void 0:a.type)||""),he=$==="recapture_rules_review"&&l,Se=$==="recapture_rules_choice"||$==="recapture_followup_choice",Ze=Se&&o&&t==="captive",D=Se?{}:s||{},xe=String(i.phase||"")==="ending"||!!i.ending_state,J=$==="night_action_choice"&&l,Ke=((_e=(q=i.status_flags)==null?void 0:q.find(Te=>Te.id==="pet_identity_active"))==null?void 0:_e.prompt)||"",ve=J?"你的安排":$==="recapture_rules_choice"?"重新立规矩":$==="recapture_followup_choice"?"后续处理":$==="escape_choice"&&o?"等待渡回应":o?t==="captor"?"当前指令":"渡的安排":"当前事件",oe=!!(D.action_label||D.action||D.line||D.intensity||(I=D.modifiers)!=null&&I.length||(Ce=D.contents)!=null&&Ce.length||(X=D.training_contents)!=null&&X.length||(Je=D.tools)!=null&&Je.length||D.feeding&&Object.keys(D.feeding).length),Ae=!!(a||oe||xe)&&!($==="escape_choice"&&l)&&!($==="bell_voice_reveal"&&l)&&!($==="item_secret_reveal"&&l)&&!(Se&&l)&&!he&&!Ze,ae=Na(i,a,t);if(xe){const Te=String(i.ending_title||"已收录结局").trim(),Qe=String(i.ending_text||"").trim(),Q=!!String(i.ending_notified_at||"").trim();return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["结局 ",e.jsx("span",{className:"sub",children:"ENDING"})]}),e.jsxs("div",{className:"ending-card",children:[e.jsx("div",{className:"event-main ending-title",children:Te}),e.jsx("div",{className:"process-text ending-body",children:Qe||"结局正文正在准备。"}),e.jsx("div",{className:"event-sub ending-sync-state",children:Q?"已同步给渡":"等待同步给渡"})]})]})}return e.jsxs(e.Fragment,{children:[he?e.jsx(pn,{rules:(a==null?void 0:a.rule_labels)||[],disabled:U,onConfirm:wt}):null,Ae?e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:[ve," ",e.jsx("span",{className:"sub",children:"EVENT"})]}),e.jsxs("div",{className:"action-card",children:[e.jsx("div",{className:"action-metadata",children:Ga(D,a,i)}),e.jsx("div",{className:"event-main",children:$==="escape_choice"&&o?"逃跑诱导已经送达渡。":Se?Pt(a):D.line||D.action_label||ki(a==null?void 0:a.required_directive,a)||(xe?"30 天闭环已完成，等待结局。":"等待下一段事件。")}),e.jsx("div",{className:"divider"}),e.jsx("div",{className:"event-sub",children:Xa(D,a,i)})]})]}):null,ae?e.jsx("div",{className:"serif runtime-bridge-copy",children:ae}):null,$==="action_response"&&l?e.jsx(tn,{response:b,mood:j,line:f,disabled:U,onResponseChange:pe,onMoodChange:ht,onLineChange:be,onSubmit:We}):null,$==="reaction_choice"&&l?e.jsx(an,{title:"此刻心情",mood:k,line:S,disabled:U,onMoodChange:Ue,onLineChange:je,onSubmit:qe}):null,r?e.jsx(nn,{actions:d,condition:u,petRulePrompt:Ke,value:h,detail:v,note:x,line:C,disabled:U,onChange:xt,onDetailChange:Ne,onNoteChange:Be,onLineChange:B,onSubmit:de}):null,$==="bell_voice_reveal"&&l?e.jsx(sn,{line:((w=(V=a==null?void 0:a.event)==null?void 0:V.bell_voice)==null?void 0:w.line)||"",disabled:U,onConfirm:jt}):null,$==="item_secret_reveal"&&l?e.jsx(on,{itemId:((L=a==null?void 0:a.item_secret)==null?void 0:L.item_id)||"item",itemLabel:((Xe=a==null?void 0:a.item_secret)==null?void 0:Xe.item_label)||"物品",text:((Le=a==null?void 0:a.item_secret)==null?void 0:Le.text)||"你发现了预先藏在物品里的内容。",disabled:U,onConfirm:K}):null,$==="escape_choice"&&l?e.jsx(ln,{pending:a,disabled:U,onChoose:Oe}):null,$==="recapture_rules_choice"&&l?e.jsx(dn,{value:O,disabled:U,onToggle:ie,onSubmit:me}):null,$==="recapture_followup_choice"&&l?e.jsx(mn,{action:Re,intensity:Ve,modifiers:Ie,trainingContents:gt,tools:fe,line:Ge,disabled:U,onActionChange:He,onIntensityChange:_t,onModifierToggle:yt,onTrainingContentToggle:ft,onToolToggle:Ye,onLineChange:bt,onSubmit:kt}):null,$==="advance_action"&&l?e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["推进 ",e.jsx("span",{className:"sub",children:"NEXT_SLOT"})]}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:U,onClick:Nt,children:"推进下一段行动"})]}):null,$==="monitor_gate"&&l?e.jsx(un,{pending:a,disabled:U,onOpenMonitor:ue,onHandleNone:()=>ke("none")}):null,$==="monitor_handle"&&l?e.jsx(Ei,{note:P,interventionIntent:R,interventionModifiers:N,interventionTrainingContents:g,interventionTools:Z,interventionLine:se,disabled:U,onNoteChange:Y,onInterventionIntentChange:vt,onInterventionModifierToggle:we,onInterventionTrainingContentToggle:re,onInterventionToolToggle:te,onInterventionLineChange:ce,onHandle:ke}):null,!a&&!r&&!xe?e.jsxs("div",{className:"action-card faded",children:[e.jsx("div",{className:"uppercase pink-text",style:{marginBottom:5},children:"SYSTEM_IDLE"}),e.jsx("div",{className:"event-sub",children:$e||"当前没有待处理事件。"}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:U,onClick:ge,children:"刷新状态"})]}):null]})}function Xa(t,i,a){var u,b,j,f,k,S,h,v,x,C,P,R;if(i!=null&&i.sealed)return"夜间行动已经封存。囚禁方尚未打开监控前，不显示具体内容。";const s=t.intervention||{},o=_i(t.modifiers),l=Object.entries(t.feeding||{}).map(([N,g])=>ka(N,g)).filter(Boolean),r=t.recapture_context||{};return[t.action_label||t.action?`行动：${t.action_label||le(t.action)}`:"",(u=t.contents)!=null&&u.length?`具体内容：${t.contents.map(vi).join(" / ")}`:"",(b=t.training_contents)!=null&&b.length?`调教内容：${t.training_contents.map(lt).join(" / ")}`:"",o.length?`修饰：${o.join(" / ")}`:"",(j=t.tools)!=null&&j.length?`道具：${t.tools.map(pt).join(" / ")}`:"",(f=t.night_detail)!=null&&f.label?`具体动向：${t.night_detail.label}`:"",t.night_discovery?`发现：${t.night_discovery}`:"",t.private_note?`私密日记：${t.private_note}`:"",l.length?`喂食：${l.join(" / ")}`:"",(k=t.action_response)!=null&&k.response_label?`回应：${t.action_response.response_label} / 心情：${t.action_response.mood||"未选"}`:"",(S=t.post_reaction)!=null&&S.mood?`此刻心情：${t.post_reaction.mood}`:"",(h=t.monitor)!=null&&h.viewed?`监控：${t.monitor.style||"view"} / ${t.monitor.handle||"未处理"}`:"",s.intent?`当场介入：${s.intent_label||yi(s.intent)}`:"",(v=s.modifiers)!=null&&v.length?`介入附加：${s.modifiers.map(fi).join(" / ")}`:"",(x=s.training_contents)!=null&&x.length?`介入调教：${s.training_contents.map(lt).join(" / ")}`:"",(C=s.tools)!=null&&C.length?`介入道具：${s.tools.map(pt).join(" / ")}`:"",s.line?`介入台词：${s.line}`:"",(P=r.rule_labels)!=null&&P.length?`新规矩：${r.rule_labels.join(" / ")}`:"",r.followup_label?`后续处理：${r.followup_label}`:"",(i==null?void 0:i.type)==="escape_choice"&&i.actor==="du"?"等待：渡选择尝试逃跑或老实待着":i!=null&&i.required_directive?`等待：${ki(i.required_directive,i)}`:"",(i==null?void 0:i.type)==="return_action_choice"||(R=t.tags)!=null&&R.includes("special_day")?`进度：第 ${a.current_day||1} / ${a.total_days||30} 天，特殊事件`:`进度：第 ${a.current_day||1} / ${a.total_days||30} 天，白天行动 ${a.day_action_count||0} / ${a.day_action_limit||3}`].filter(Boolean).join(`
`)}function Ci(t){var o,l,r,d,u,b,j;const i=t.intervention||{},a=_i(t.modifiers);return[`第 ${t.day||1} 天`,t.phase==="night"?"夜间":t.slot?`第 ${t.slot} 段`:"",t.action_label||t.action?`行动：${t.action_label||le(t.action)}`:"",(o=t.contents)!=null&&o.length?`内容：${t.contents.map(vi).join(" / ")}`:"",(l=t.training_contents)!=null&&l.length?`调教：${t.training_contents.map(lt).join(" / ")}`:"",a.length?`修饰：${a.join(" / ")}`:"",(r=t.tools)!=null&&r.length?`道具：${t.tools.map(pt).join(" / ")}`:"",(d=t.night_detail)!=null&&d.label?`动向：${t.night_detail.label}`:"",i.intent?`介入：${i.intent_label||yi(i.intent)}`:"",(u=i.modifiers)!=null&&u.length?`附加：${i.modifiers.map(fi).join(" / ")}`:"",(b=i.training_contents)!=null&&b.length?`介入调教：${i.training_contents.map(lt).join(" / ")}`:"",(j=i.tools)!=null&&j.length?`介入道具：${i.tools.map(pt).join(" / ")}`:""].filter(Boolean).join(" / ")}function Qa(t){return[t.process_text,t.private_note,t.line].filter(Boolean).join(`

`)}function en({review:t,mood:i,line:a,disabled:s,onMoodChange:o,onLineChange:l,onSave:r}){return e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"process-review-head",children:e.jsxs("h2",{className:"serif process-review-title",children:["经过 / ",e.jsx("span",{className:"pink-text",children:"Process"})]})}),e.jsxs("div",{className:"process-review-meta",children:[e.jsx("div",{className:"event-main",children:t.event.action_label||le(t.event.action)}),e.jsx("div",{className:"event-sub",children:Ci(t.event)})]}),e.jsx("div",{className:"process-text process-review-body",children:t.text}),t.moodRequired?e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title process-mood-title",children:["此刻心情 ",e.jsx("span",{className:"sub",children:"MOOD"})]}),e.jsx("div",{className:"btn-group mood-grid",children:Ot.map(d=>e.jsx(G,{active:i===d,disabled:s,onClick:()=>o(d),children:d},d))}),e.jsx("textarea",{placeholder:"可选：你想补的一句话...",value:a,disabled:s,onChange:d=>l(d.target.value)})]}):null,e.jsx("button",{className:"btn btn-large process-save-btn",type:"button",disabled:s,onClick:r,children:"保存到回顾"})]})}function tn({response:t,mood:i,line:a,disabled:s,onResponseChange:o,onMoodChange:l,onLineChange:r,onSubmit:d}){return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["你的回应 ",e.jsx("span",{className:"sub",children:"RESPONSE"})]}),e.jsx("div",{className:"btn-group response-grid",children:la.map(u=>e.jsx(G,{active:t===u.id,disabled:s,onClick:()=>o(u.id),children:u.label},u.id))}),e.jsxs("div",{className:"panel-title response-mood-title",children:["此刻心情 ",e.jsx("span",{className:"sub",children:"MOOD"})]}),e.jsx("div",{className:"btn-group mood-grid",children:Ot.map(u=>e.jsx(G,{active:i===u,disabled:s,onClick:()=>l(u),children:u},u))}),e.jsx("textarea",{placeholder:"你想说的一句话...",value:a,disabled:s,onChange:u=>r(u.target.value)}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:s,onClick:d,children:"提交并同步"})]})}function an({title:t,mood:i,line:a,disabled:s,onMoodChange:o,onLineChange:l,onSubmit:r}){return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:[t," ",e.jsx("span",{className:"sub",children:"MOOD"})]}),e.jsx("div",{className:"btn-group mood-grid",children:Ot.map(d=>e.jsx(G,{active:i===d,disabled:s,onClick:()=>o(d),children:d},d))}),e.jsx("textarea",{placeholder:"你想补的一句话...",value:a,disabled:s,onChange:d=>l(d.target.value)}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:s,onClick:r,children:"记录心情"})]})}function nn({actions:t,condition:i,petRulePrompt:a,value:s,detail:o,note:l,line:r,disabled:d,onChange:u,onDetailChange:b,onNoteChange:j,onLineChange:f,onSubmit:k}){const S=gi[s]||[];return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["你的安排 ",e.jsx("span",{className:"sub",children:"NIGHT"})]}),e.jsxs("div",{className:"action-card",children:[i!=null&&i.label?e.jsx("div",{className:"action-metadata",children:i.label}):null,e.jsx("div",{className:"event-sub",children:(i==null?void 0:i.prompt)||"渡可能在看监控关注你的动向。你准备晚上做什么？"}),a?e.jsx("div",{className:"event-sub night-condition-caption",children:a}):null,i!=null&&i.caption?e.jsx("div",{className:"event-sub night-condition-caption",children:i.caption}):null]}),e.jsx("div",{className:"btn-group",children:t.map(h=>e.jsx(G,{active:s===h,disabled:d,onClick:()=>u(h),children:xi(h)},h))}),e.jsx("div",{className:"serif night-choice-copy",children:ma[s]||"今晚的选择会被监控记录下来。"}),S.length?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"action-metadata section-meta",children:"具体动向"}),e.jsx("div",{className:"btn-group content-grid night-detail-grid",children:S.map(h=>e.jsx(G,{active:o===h.id,disabled:d,onClick:()=>b(h.id),children:h.label},h.id))})]}):null,s==="diary"?e.jsx("textarea",{placeholder:"可选：写下私密日记正文...",value:l,disabled:d,onChange:h=>j(h.target.value)}):null,s!=="ring_bell"?e.jsx("textarea",{placeholder:"可选：你想说的一句话...",value:r,disabled:d,onChange:h=>f(h.target.value)}):null,e.jsx("button",{className:"btn btn-large",type:"button",disabled:d||S.length>0&&!o,onClick:k,children:"确认夜间行动"})]})}function sn({line:t,disabled:i,onConfirm:a}){return e.jsx("div",{className:"bell-voice-overlay item-reveal-call_bell",role:"dialog","aria-modal":"true","aria-label":"语音铃第一次播放",children:e.jsxs("div",{className:"bell-voice-dialog item-reveal-dialog",children:[e.jsx("div",{className:"bell-voice-kicker",children:"SYSTEM / FIRST PLAYBACK"}),e.jsxs("div",{className:"item-reveal-motif","aria-hidden":"true",children:[e.jsx("span",{}),e.jsx("span",{}),e.jsx("span",{}),e.jsx("span",{})]}),e.jsxs("div",{className:"serif bell-voice-line",children:["铃响了，你听见「",t||"预录的声音","」在静谧的房间里响起"]}),e.jsx("button",{className:"btn bell-voice-continue",type:"button",disabled:i,onClick:a,children:"继续"})]})})}function rn({scene:t,onDismiss:i}){const a=String(t.tone||"day"),s=t.title||"新的一段",o=t.body||"房间里的时间继续向前。",l=320,r=120,d=l+Math.max(0,Array.from(s).length-1)*r+720+180,u=Ti(t);return e.jsxs("button",{className:`scene-transition-overlay ${a==="night"?"night":a==="special"?"special":"day"}`,type:"button","aria-label":"跳过过场",onClick:i,style:{"--scene-duration":`${u}ms`},children:[e.jsx("span",{className:"scene-transition-scan"}),e.jsxs("span",{className:"scene-transition-content",children:[e.jsx("span",{className:"scene-transition-kicker",children:t.kicker||"CAPTIVITY LOG"}),e.jsx(cn,{className:"serif scene-transition-title",text:s,start:l,step:r}),e.jsx("span",{className:"scene-transition-body",style:{animationDelay:`${d}ms`},children:o})]})]})}function cn({className:t,text:i,start:a,step:s}){return e.jsx("span",{className:t,"aria-label":i,children:Array.from(i).map((o,l)=>e.jsx("span",{className:`scene-transition-char${o===" "?" space":""}`,style:{animationDelay:`${a+l*s}ms`},"aria-hidden":"true",children:o===" "?" ":o},`${o}-${l}`))})}function Ti(t){const i=Array.from((t==null?void 0:t.title)||"新的一段").length,a=Array.from((t==null?void 0:t.body)||"房间里的时间继续向前。").length,s=320+Math.max(0,i-1)*120+720+180;return Math.min(6800,Math.max(3200,s+a*55+1e3))}function on({itemId:t,itemLabel:i,text:a,disabled:s,onConfirm:o}){return e.jsx("div",{className:`bell-voice-overlay item-reveal-${t}`,role:"dialog","aria-modal":"true","aria-label":`${i}第一次使用彩蛋`,children:e.jsxs("div",{className:"bell-voice-dialog item-reveal-dialog",children:[e.jsxs("div",{className:"bell-voice-kicker",children:[i," / FIRST DISCOVERY"]}),e.jsxs("div",{className:"item-reveal-motif","aria-hidden":"true",children:[e.jsx("span",{}),e.jsx("span",{}),e.jsx("span",{}),e.jsx("span",{})]}),e.jsx("div",{className:"serif bell-voice-line",children:a}),e.jsx("button",{className:"btn bell-voice-continue",type:"button",disabled:s,onClick:o,children:"继续"})]})})}function ln({pending:t,disabled:i,onChoose:a}){const[s,o]=_.useState(-1),l=s>=0?nt[s]:null,r=s===nt.length;_.useEffect(()=>{if(!r)return;const u=window.setTimeout(()=>a("escape"),1e3);return()=>window.clearTimeout(u)},[a,r]);function d(){if(s<nt.length-1){o(s+1);return}o(nt.length)}return r?e.jsx("div",{className:"escape-choice-overlay",role:"dialog","aria-modal":"true","aria-label":"坏孩子",children:e.jsx("div",{className:"escape-choice-dialog escape-sting-dialog",children:e.jsx("div",{className:"escape-sting-text",children:"坏孩子"})})}):e.jsx("div",{className:"escape-choice-overlay",role:"dialog","aria-modal":"true","aria-label":"逃跑机会",children:e.jsxs("div",{className:"escape-choice-dialog",children:[e.jsx("div",{className:"action-metadata",children:"ESCAPE WINDOW"}),e.jsx("div",{className:"panel-title escape-choice-title",children:(l==null?void 0:l.title)||"逃跑机会"}),e.jsx("div",{className:"event-main",children:(l==null?void 0:l.text)||(t==null?void 0:t.hint)||"渡今天有事出去了。"}),e.jsx("div",{className:"divider"}),l?null:e.jsxs("div",{className:"event-sub",children:[(t==null?void 0:t.bait)||`${Rt("entry")}。`," 你要怎么做？"]}),l?e.jsx("div",{className:"escape-confirm-prompt",children:l.prompt}):null,e.jsx("div",{className:"btn-group escape-choice-actions",children:l?e.jsxs(e.Fragment,{children:[e.jsx("button",{className:"btn",type:"button",disabled:i,onClick:d,children:l.continueLabel}),e.jsx("button",{className:"btn",type:"button",disabled:i,onClick:()=>a(l.abortChoice),children:l.stayLabel})]}):xa.map(u=>e.jsx("button",{className:"btn",type:"button",disabled:i,onClick:()=>u.id==="escape"?o(0):a(u.id),children:u.label},u.id))})]})})}function pn({rules:t,disabled:i,onConfirm:a}){return e.jsx("div",{className:"recapture-rules-review-overlay",role:"dialog","aria-modal":"true","aria-label":"新规矩",children:e.jsxs("div",{className:"recapture-rules-review",children:[e.jsx("div",{className:"action-metadata",children:"NEW RULES"}),e.jsxs("div",{className:"panel-title",children:["新规矩 ",e.jsx("span",{className:"sub",children:"RULES"})]}),e.jsx("div",{className:"recapture-rules-review-list",children:t.map(s=>e.jsx("div",{className:"recapture-rules-review-item",children:s},s))}),e.jsx("button",{className:"btn",type:"button",disabled:i||!t.length,onClick:a,children:"记住了"})]})})}function dn({value:t,disabled:i,onToggle:a,onSubmit:s}){return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["重新立规矩 ",e.jsx("span",{className:"sub",children:"NEW_RULES"})]}),e.jsx("div",{className:"action-card",children:e.jsx("div",{className:"event-sub",children:"选择 1–3 条。保存后会持续影响之后的行动和具体经过。"})}),e.jsx("div",{className:"btn-group content-grid",children:ze.map(o=>e.jsx(G,{active:t.includes(o.id),disabled:i,onClick:()=>a(o.id),children:o.label},o.id))}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:i||t.length<1||t.length>3,onClick:s,children:"保存新规矩"})]})}function mn({action:t,intensity:i,modifiers:a,trainingContents:s,tools:o,line:l,disabled:r,onActionChange:d,onIntensityChange:u,onModifierToggle:b,onTrainingContentToggle:j,onToolToggle:f,onLineChange:k,onSubmit:S}){const h=t==="training"||a.includes("training");return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["后续处理 ",e.jsx("span",{className:"sub",children:"FOLLOW_UP"})]}),e.jsx("div",{className:"btn-group content-grid",children:st.map(v=>e.jsx(G,{active:t===v.id,disabled:r,onClick:()=>d(v.id),children:v.label},v.id))}),e.jsx("div",{className:"action-metadata section-meta",children:"强度"}),e.jsx("div",{className:"btn-group intensity-grid",children:It.map(v=>e.jsx(G,{active:i===v.id,disabled:r,onClick:()=>u(v.id),children:v.label},v.id))}),e.jsx("div",{className:"action-metadata section-meta",children:"可选附加"}),e.jsx("div",{className:"btn-group",children:$t.map(v=>e.jsx(G,{active:a.includes(v.id),disabled:r,onClick:()=>b(v.id),children:v.label},v.id))}),h?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"action-metadata section-meta",children:"调教内容"}),e.jsx("div",{className:"btn-group content-grid",children:ut.map(v=>e.jsx(G,{active:s.includes(v.id),disabled:r,onClick:()=>j(v.id),children:v.label},v.id))})]}):null,e.jsx("div",{className:"action-metadata section-meta",children:"道具"}),e.jsx(zt,{selected:o,disabled:r,context:{action:t,modifiers:a,contents:[],trainingContents:s},onToggle:f}),e.jsx("textarea",{placeholder:"可选：你要说的话...",value:l,disabled:r,onChange:v=>k(v.target.value)}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:r||h&&!s.length,onClick:S,children:"确定后续处理"})]})}function un({pending:t,disabled:i,onOpenMonitor:a,onHandleNone:s}){return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["夜间监控 ",e.jsx("span",{className:"sub",children:"MONITOR"})]}),e.jsxs("div",{className:"action-card",children:[e.jsx("div",{className:"action-metadata",children:(t==null?void 0:t.alert_label)||"夜间行动已封存"}),e.jsx("div",{className:"event-sub",children:t!=null&&t.alert_label?"被囚禁方按响了呼叫铃。你可以打开监控查看，也可以选择不看。":"被囚禁方的夜间行动已封存。你可以打开监控，也可以选择不看。"})]}),e.jsxs("div",{className:"btn-group",children:[e.jsx("button",{className:"btn",type:"button",disabled:i,onClick:()=>a("occasional"),children:"偶尔看"}),e.jsx("button",{className:"btn",type:"button",disabled:i,onClick:()=>a("full"),children:"全程看"}),e.jsx("button",{className:"btn",type:"button",disabled:i,onClick:s,children:"不看"})]})]})}function Ei({note:t,interventionIntent:i,interventionModifiers:a,interventionTrainingContents:s,interventionTools:o,interventionLine:l,disabled:r,showTitle:d=!0,onNoteChange:u,onInterventionIntentChange:b,onInterventionModifierToggle:j,onInterventionTrainingContentToggle:f,onInterventionToolToggle:k,onInterventionLineChange:S,onHandle:h}){const v=ha.filter(x=>x.id!=="intervene");return e.jsxs(e.Fragment,{children:[d?e.jsxs("div",{className:"panel-title",children:["监控处理 ",e.jsx("span",{className:"sub",children:"HANDLE"})]}):null,e.jsx("div",{className:"btn-group",children:v.map(x=>e.jsx("button",{className:"btn",type:"button",disabled:r,onClick:()=>h(x.id),children:x.label},x.id))}),e.jsxs("div",{className:"panel-title intervention-title",children:["当场介入 ",e.jsx("span",{className:"sub",children:"INTERVENE"})]}),e.jsx("div",{className:"action-metadata",children:"介入方式"}),e.jsx("div",{className:"btn-group",children:pi.map(x=>e.jsx(G,{active:i===x.id,disabled:r,onClick:()=>b(x.id),children:x.label},x.id))}),e.jsx("div",{className:"action-metadata section-meta",children:"附加项"}),e.jsx("div",{className:"btn-group response-grid",children:$t.map(x=>e.jsx(G,{active:a.includes(x.id),disabled:r,onClick:()=>j(x.id),children:x.label},x.id))}),a.includes("training")?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"action-metadata section-meta",children:"调教内容"}),e.jsx("div",{className:"btn-group content-grid",children:ut.filter(x=>!oi.has(x.id)).map(x=>e.jsx(G,{active:s.includes(x.id),disabled:r||!s.includes(x.id)&&s.length>=3,onClick:()=>f(x.id),children:x.label},x.id))})]}):null,e.jsx("div",{className:"action-metadata section-meta",children:"道具"}),e.jsx(zt,{selected:o,disabled:r,onToggle:k}),e.jsx("textarea",{placeholder:"可选：你要说的话...",value:l,disabled:r,onChange:x=>S(x.target.value)}),e.jsx("textarea",{placeholder:"可选：处理备注...",value:t,disabled:r,onChange:x=>u(x.target.value)}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:r,onClick:()=>h("intervene"),children:"当场介入"})]})}function gn({disabled:t,canRetry:i,onRetry:a,onRefresh:s}){return e.jsxs("div",{className:"btn-group sync-action-bar",children:[e.jsx("button",{className:"btn",type:"button",disabled:t||!i,onClick:a,children:"重试"}),e.jsx("button",{className:"btn",type:"button",disabled:t,onClick:s,children:"刷新"})]})}function hn({events:t,lastText:i,detail:a,onOpenDetail:s,onCloseDetail:o}){const l=_.useMemo(()=>Array.from(new Set(t.map(b=>Number(b.day||1)))).sort((b,j)=>j-b),[t]),[r,d]=_.useState("all");_.useEffect(()=>{r!=="all"&&!l.includes(Number(r))&&d("all")},[l,r]);const u=_.useMemo(()=>{const b=r==="all"?t:t.filter(f=>Number(f.day||1)===Number(r)),j=new Map;return b.slice().reverse().forEach(f=>{const k=Number(f.day||1),S=j.get(k)||[];S.push(f),j.set(k,S)}),Array.from(j.entries()).sort(([f],[k])=>k-f)},[t,r]);return a?e.jsxs(e.Fragment,{children:[e.jsx("button",{className:"history-back",type:"button",onClick:o,children:"回到回顾"}),e.jsxs("div",{className:"process-review-meta history-detail-meta",children:[e.jsx("div",{className:"event-main",children:a.action_label||le(a.action)}),e.jsx("div",{className:"event-sub",children:Ci(a)})]}),e.jsx("div",{className:"process-text history-detail-body",children:Qa(a)||"这条事件没有正文。"})]}):e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"history-title-row",children:[e.jsxs("div",{className:"panel-title",children:["事件回顾 ",e.jsx("span",{className:"sub",children:"ARCHIVE"})]}),l.length?e.jsxs("select",{className:"history-day-select","aria-label":"按日期筛选事件",value:r,onChange:b=>d(b.target.value),children:[e.jsx("option",{value:"all",children:"全部日期"}),l.map(b=>e.jsxs("option",{value:String(b),children:["第 ",b," 天"]},b))]}):null]}),u.length?u.map(([b,j])=>e.jsxs("section",{className:"history-day-group",children:[e.jsxs("div",{className:"history-day-heading",children:[e.jsxs("span",{children:["第 ",b," 天"]}),e.jsxs("span",{children:[j.length," 条"]})]}),j.map(f=>{var S;const k=(S=f.tags)!=null&&S.includes("out_of_band")?"随时":f.phase==="ending"||f.action==="ending"?"结局":f.phase==="night"?"晚上":ui[Math.max(0,Number(f.slot||1)-1)]||`第 ${f.slot||0} 段`;return e.jsxs("button",{className:"action-card history-list-item",type:"button",onClick:()=>s(f),children:[e.jsx("div",{className:"action-metadata",children:k}),e.jsx("div",{className:"event-main",children:f.action_label||le(f.action)})]},f.id||`${f.day}-${f.slot}-${f.action}`)})]},b)):e.jsxs("div",{className:"action-card faded",children:[e.jsx("div",{className:"uppercase pink-text",style:{marginBottom:5},children:"暂无回顾"}),e.jsx("div",{className:"event-sub",children:i||"还没有归档事件。"})]})]})}function xn({view:t,pendingType:i,monitorNote:a,interventionIntent:s,interventionModifiers:o,interventionTrainingContents:l,interventionTools:r,interventionLine:d,disabled:u,onMonitorNoteChange:b,onInterventionIntentChange:j,onInterventionModifierToggle:f,onInterventionTrainingContentToggle:k,onInterventionToolToggle:S,onInterventionLineChange:h,onOpenMonitor:v,onHandleMonitor:x}){var se;const C=(t.deferred_monitor_materials||[]).filter(Boolean),P=(t.event_log||[]).filter(O=>O.monitor).slice(-4).reverse(),R=i==="monitor_gate",N=i==="monitor_handle",g=N||C.length>0||P.length>0,Z=((se=t.pending_event)==null?void 0:se.event)||C[0]||null;return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:`monitor-console ${R||N?"active":""}`,children:[e.jsxs("div",{className:"monitor-screen",children:[e.jsxs("div",{className:"monitor-screen-top",children:[e.jsx("span",{children:"LIVE MONITOR"}),e.jsx("span",{children:R?"SEALED":N?"OPEN":"IDLE"})]}),e.jsxs("div",{className:"monitor-screen-body",children:[e.jsx("div",{className:"event-main",children:R?"夜间行动已封存":N?"正在查看监控记录":"暂无实时画面"}),e.jsx("div",{className:"event-sub",children:R?"可以现在打开实时监控，也可以选择不看。":N?"选择处理方式，或把这条记录留到之后使用。":"被囚禁方完成夜间行动后，实时监控会出现在这里。"}),Z&&(R||N)?e.jsx("div",{className:"serif monitor-live-scene",children:Et(Z)}):null]})]}),R?e.jsxs("div",{className:"btn-group monitor-controls",children:[e.jsx("button",{className:"btn",type:"button",disabled:u,onClick:()=>v("occasional"),children:"偶尔看"}),e.jsx("button",{className:"btn",type:"button",disabled:u,onClick:()=>v("full"),children:"全程看"}),e.jsx("button",{className:"btn",type:"button",disabled:u,onClick:()=>x("none"),children:"不看"})]}):null,N?e.jsx(Ei,{note:a,interventionIntent:s,interventionModifiers:o,interventionTrainingContents:l,interventionTools:r,interventionLine:d,disabled:u,showTitle:!1,onNoteChange:b,onInterventionIntentChange:j,onInterventionModifierToggle:f,onInterventionTrainingContentToggle:k,onInterventionToolToggle:S,onInterventionLineChange:h,onHandle:x}):null]}),e.jsx("div",{className:"monitor-record-title",children:e.jsxs("div",{className:"panel-title",children:["监控记录 ",e.jsx("span",{className:"sub",children:"RECORDS"})]})}),C.length?e.jsx("div",{className:"monitor-record-list",children:C.map(O=>e.jsxs("div",{className:"monitor-record-item",children:[e.jsx("div",{className:"action-metadata",children:ei(O)}),e.jsx("div",{className:"event-main",children:ti(O)}),e.jsx("div",{className:"serif event-sub monitor-record-scene",children:Et(O)})]},O.id||`${O.day}-${O.action}-${O.created_at}`))}):null,P.length?e.jsx("div",{className:"monitor-record-list",children:P.map(O=>e.jsxs("div",{className:"monitor-record-item",children:[e.jsx("div",{className:"action-metadata",children:ei(O)}),e.jsx("div",{className:"event-main",children:ti(O)}),e.jsx("div",{className:"serif event-sub monitor-record-scene",children:Et(O)})]},O.id||`monitor-${O.day}-${O.slot}-${O.action}`))}):null,g?null:e.jsxs("div",{className:"monitor-record-item faded",children:[e.jsx("div",{className:"action-metadata",children:"暂无监控记录"}),e.jsx("div",{className:"event-sub",children:"打开过的夜间监控会出现在这里。"})]})]})}function vn({role:t,view:i,escapeDay:a,escapeRoom:s,escapeHint:o,escapeBait:l,disabled:r,onEscapeDayChange:d,onEscapeRoomChange:u,onEscapeHintChange:b,onEscapeBaitChange:j,onOpenMonitorRoom:f,onOpenInventoryRoom:k,onScheduleEscape:S}){const h=String(i.ending_state||""),v=String(i.ending_title||"").trim(),x=De.filter(N=>{var g;return!!((g=i.inventory)!=null&&g[N.id])}).length,C=x>0,P=i.escape_hint||{},R=(i.event_log||[]).filter(N=>N.escape).slice(-3).reverse();return e.jsxs(e.Fragment,{children:[t!=="captor"?e.jsxs("div",{className:"panel-title",children:["特殊机制 ",e.jsx("span",{className:"sub",children:"SPECIAL"})]}):null,t==="captor"?e.jsxs(e.Fragment,{children:[e.jsxs("button",{className:"special-room-entry",type:"button",disabled:r,onClick:f,children:[e.jsxs("div",{children:[e.jsxs("div",{className:"panel-title",children:["监控室 ",e.jsx("span",{className:"sub",children:"MONITOR"})]}),e.jsx("div",{className:"event-sub",children:"进入全屏监控台，查看实时画面和历史记录。"})]}),e.jsx("span",{className:"special-room-arrow",children:"›"})]}),e.jsxs("button",{className:"special-room-entry",type:"button",disabled:r,onClick:k,children:[e.jsxs("div",{children:[e.jsxs("div",{className:"panel-title",children:["物品仓库 ",e.jsx("span",{className:"sub",children:"ITEMS"})]}),e.jsx("div",{className:"event-sub",children:"进入全屏仓库，管理可赠送物品。"})]}),e.jsx("span",{className:"special-room-arrow",children:"›"})]}),e.jsxs("div",{className:"panel-title special-section-title",children:["逃跑诱导 ",e.jsx("span",{className:"sub",children:"ESCAPE"})]}),e.jsxs("div",{className:"action-card",children:[e.jsxs("div",{className:"form-grid escape-room-row",children:[e.jsxs("label",{className:"compact-field",children:[e.jsx("span",{children:"诱导日期"}),e.jsx("input",{className:"compact",type:"number",min:1,max:30,value:a,disabled:r,onChange:N=>d(Number(N.target.value||1))})]}),e.jsxs("label",{className:"compact-field",children:[e.jsx("span",{children:"钥匙位置"}),e.jsx("select",{className:"compact escape-room-select",value:s,disabled:r,onChange:N=>u(N.target.value),children:Mt.map(N=>e.jsx("option",{value:N.id,children:N.label},N.id))})]})]}),e.jsx("input",{className:"compact",value:o,disabled:r,onChange:N=>b(N.target.value)}),e.jsx("input",{className:"compact",value:l,disabled:r,onChange:N=>j(N.target.value)}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:r,onClick:S,children:"设置逃跑诱导"})]}),R.length?e.jsx("div",{className:"monitor-record-list escape-record-list",children:R.map(N=>{var g,Z;return e.jsxs("div",{className:"monitor-record-item",children:[e.jsxs("div",{className:"action-metadata",children:["逃跑记录 / 第 ",N.day||1," 天"]}),e.jsx("div",{className:"event-main",children:((g=N.escape)==null?void 0:g.choice_label)||fa((Z=N.escape)==null?void 0:Z.choice)})]},N.id||`escape-${N.day}-${N.created_at}`)})}):null]}):e.jsxs(e.Fragment,{children:[e.jsxs("button",{className:"special-room-entry",type:"button",disabled:r||!C,onClick:k,children:[e.jsxs("div",{children:[e.jsxs("div",{className:"panel-title",children:["房间物品 ",e.jsx("span",{className:"sub",children:"ITEMS"})]}),e.jsx("div",{className:"event-sub",children:C?`已解锁 ${x} 件，点击查看。`:"未解锁"})]}),C?e.jsx("span",{className:"special-room-arrow",children:"›"}):null]}),e.jsxs("div",{className:"action-card",children:[e.jsx("div",{className:"action-metadata",children:"特殊提示"}),e.jsx("div",{className:"event-main",children:"逃跑提示"}),e.jsx("div",{className:"event-sub",children:P.hint||P.bait?[P.hint,P.bait].filter(Boolean).join(`
`):"未出现"})]})]}),e.jsxs("div",{className:"panel-title",children:["结局 ",e.jsx("span",{className:"sub",children:"ENDING"})]}),e.jsxs("div",{className:"action-card",children:[e.jsx("div",{className:"action-metadata",children:h?"结局已触发":"未收录"}),e.jsx("div",{className:"event-main",children:i.game_over?v||"已收录结局":"暂无结局"}),e.jsx("div",{className:"event-sub",children:i.game_over?"最终正文已保存到回顾。":"30 天结算后会收录到这里。"})]})]})}export{yn as CaptivitySimulatorGameTab};
