import{r as h,j as e,C as Gt,b as Si,A as Ma}from"./index-B7JyRbLT.js";const Ia="/miniapp/assets/captivity-recapture-background-DMt5byGf.webp",Ci="default",$a=[{key:"health",label:"健康"},{key:"stamina",label:"体力"},{key:"cleanliness",label:"清洁"},{key:"shame",label:"羞耻"},{key:"intimacy",label:"依赖"}],bt=[{id:"feeding",label:"喂食"},{id:"cleaning",label:"清洗"},{id:"training",label:"服从调教"},{id:"reward",label:"奖励取悦"},{id:"punishment",label:"违令惩戒"},{id:"comfort",label:"事后安抚"},{id:"rest",label:"看管休息"},{id:"check",label:"私密检查"},{id:"room_search",label:"突击搜查"}],wt={reward:[{id:"caress_reward",label:"抚摸奖励"},{id:"kiss_reward",label:"亲吻奖励"},{id:"masturbation_permission",label:"允许自慰"},{id:"orgasm_permission",label:"允许高潮"},{id:"toy_reward",label:"玩具奖励"},{id:"freedom_reward",label:"增加自由"}],punishment:[{id:"impact_discipline",label:"拍打惩戒"},{id:"bondage_discipline",label:"束缚惩戒"},{id:"orgasm_denial",label:"禁止高潮"},{id:"toy_discipline",label:"玩具惩戒"},{id:"confiscation",label:"没收物品"},{id:"interrogation",label:"审问"},{id:"rule_escalation",label:"规则加码"}],comfort:[{id:"embrace",label:"拥抱"},{id:"kiss",label:"亲吻"},{id:"body_care",label:"身体清理"},{id:"massage",label:"按摩"},{id:"feeding_care",label:"喂水喂食"},{id:"cuddle_rest",label:"抱着休息"},{id:"partial_release",label:"解除部分束缚"}],rest:[{id:"forced_nap",label:"强制午睡"},{id:"cuddle_sleep",label:"抱睡"},{id:"supervised_sleep",label:"陪睡"},{id:"restrained_rest",label:"固定姿势休息"},{id:"quiet_time",label:"安静待着"}],check:[{id:"body_check",label:"身体检查"},{id:"mark_check",label:"痕迹检查"},{id:"sensitivity_check",label:"敏感反应检查"},{id:"restraint_check",label:"束缚状态检查"},{id:"chastity_check",label:"贞操装置检查"}],room_search:[{id:"bed_search",label:"翻查床铺"},{id:"hidden_item_search",label:"搜查私藏物"},{id:"body_search",label:"搜身"},{id:"key_trace_check",label:"检查钥匙痕迹"},{id:"search_confiscation",label:"没收物品"},{id:"on_site_questioning",label:"现场盘问"}]},kt=[{id:"obedience_commands",label:"口令服从"},{id:"position_training",label:"姿势训练"},{id:"bondage_training",label:"束缚训练"},{id:"sensory_deprivation",label:"感官控制"},{id:"impact_play",label:"拍打调教"},{id:"wax_play",label:"滴蜡调教"},{id:"clamp_play",label:"夹具调教"},{id:"toy_training",label:"玩具调教"},{id:"anal_training",label:"后庭调教"},{id:"chastity_control",label:"贞操控制"},{id:"orgasm_control",label:"高潮控制"},{id:"forced_orgasm",label:"强制高潮"},{id:"masturbation_control",label:"自慰控制"},{id:"humiliation_play",label:"羞耻调教"},{id:"exposure_training",label:"展示训练"},{id:"pet_play",label:"小狗身份建立"},{id:"leash_training",label:"牵引训练"},{id:"service_training",label:"服务训练"},{id:"inspection_training",label:"检查调教"},{id:"pet_position_wait",label:"定点等候"},{id:"pet_crawl_training",label:"爬行训练"},{id:"pet_feeding",label:"宠物式喂食"},{id:"pet_permission",label:"按铃求许可"},{id:"pet_voice_training",label:"叫声与回应"},{id:"pet_owner_address",label:"主人称呼训练"},{id:"pet_begging",label:"宠物式求欢"},{id:"pet_display",label:"宠物展示检查"},{id:"toilet_control",label:"如厕控制"},{id:"assisted_urination",label:"抱着把尿"}],Ti=new Set(["toilet_control","assisted_urination"]),Aa=new Set(["masturbation_permission","orgasm_permission","toy_reward","impact_discipline","bondage_discipline","orgasm_denial","toy_discipline","sensitivity_check","chastity_check","body_search"]),Wt=[{id:"light",label:"低"},{id:"medium",label:"中"},{id:"heavy",label:"高"}],Ei=[{id:"training",label:"调教"},{id:"sex",label:"性交"}],Ri=[{id:"catch",label:"抓现行"},{id:"confiscate",label:"没收物品"},{id:"interrupt",label:"打断带走"},{id:"ambush",label:"突袭"},{id:"question",label:"审问"},{id:"command_stop",label:"命令停下"},{id:"reward",label:"奖励"},{id:"punishment",label:"惩罚"}],Zt=[{id:"training",label:"调教"},{id:"sex",label:"性行为"}],_t=[{id:"toy",label:"跳蛋",category:"玩具",contexts:["training:toy_training","training:orgasm_control","training:forced_orgasm","training:masturbation_control","content:toy_reward","content:toy_discipline","modifier:sex"]},{id:"vibrating_wand",label:"振动棒",category:"玩具",contexts:["training:toy_training","training:orgasm_control","training:forced_orgasm","training:masturbation_control","content:toy_reward","content:toy_discipline","modifier:sex"]},{id:"dildo",label:"假阳具",category:"玩具",contexts:["training:toy_training","training:forced_orgasm","content:toy_reward","content:toy_discipline","modifier:sex"]},{id:"remote_control",label:"遥控器",category:"玩具",contexts:["training:toy_training","training:orgasm_control","training:forced_orgasm","training:masturbation_control","content:toy_reward","content:toy_discipline"]},{id:"lubricant",label:"润滑剂",category:"辅助",contexts:["training:toy_training","training:anal_training","training:forced_orgasm","modifier:sex"]},{id:"collar",label:"项圈",category:"束缚",contexts:["training:obedience_commands","training:position_training","training:pet_play","training:pet_position_wait","training:pet_crawl_training","training:pet_feeding","training:pet_permission","training:pet_voice_training","training:pet_owner_address","training:pet_begging","training:pet_display","training:leash_training","training:service_training","content:bondage_discipline","content:restrained_rest","modifier:sex"]},{id:"leash",label:"牵引绳",category:"束缚",contexts:["training:position_training","training:pet_play","training:pet_position_wait","training:pet_crawl_training","training:pet_begging","training:pet_display","training:leash_training","training:service_training","content:bondage_discipline"]},{id:"handcuffs",label:"手铐",category:"束缚",contexts:["training:bondage_training","training:position_training","training:sensory_deprivation","training:exposure_training","training:toilet_control","training:assisted_urination","content:bondage_discipline","content:restrained_rest","modifier:sex"]},{id:"ankle_cuffs",label:"脚铐",category:"束缚",contexts:["training:bondage_training","training:position_training","training:exposure_training","training:toilet_control","training:assisted_urination","content:bondage_discipline","content:restrained_rest","modifier:sex"]},{id:"rope",label:"绳子",category:"束缚",contexts:["training:bondage_training","training:position_training","training:exposure_training","training:toilet_control","training:assisted_urination","content:bondage_discipline","content:restrained_rest","modifier:sex"]},{id:"bondage_tape",label:"束缚胶带",category:"束缚",contexts:["training:bondage_training","training:sensory_deprivation","training:toilet_control","training:assisted_urination","content:bondage_discipline","content:restrained_rest","modifier:sex"]},{id:"spreader_bar",label:"分腿杆",category:"束缚",contexts:["training:bondage_training","training:position_training","training:exposure_training","training:toilet_control","training:assisted_urination","content:bondage_discipline","modifier:sex"]},{id:"blindfold",label:"眼罩",category:"感官",contexts:["training:sensory_deprivation","training:inspection_training","content:sensitivity_check","modifier:sex"]},{id:"gag",label:"口球",category:"束缚",contexts:["training:obedience_commands","training:sensory_deprivation","training:humiliation_play","training:pet_play","training:pet_voice_training","training:pet_begging","training:pet_display","modifier:sex"]},{id:"muzzle",label:"口套",category:"束缚",contexts:["training:obedience_commands","training:humiliation_play","training:pet_play","training:pet_voice_training","training:pet_owner_address","training:pet_begging"]},{id:"whip",label:"软鞭",category:"训诫",contexts:["training:impact_play","content:impact_discipline"]},{id:"flogger",label:"多尾鞭",category:"训诫",contexts:["training:impact_play","content:impact_discipline"]},{id:"paddle",label:"拍板",category:"训诫",contexts:["training:impact_play","content:impact_discipline"]},{id:"cane",label:"藤条",category:"训诫",contexts:["training:impact_play","content:impact_discipline"]},{id:"ruler",label:"戒尺",category:"训诫",contexts:["training:impact_play","content:impact_discipline"]},{id:"candle",label:"蜡烛",category:"感官",contexts:["training:wax_play","modifier:sex"]},{id:"ice_cube",label:"冰块",category:"感官",contexts:["training:sensory_deprivation","training:inspection_training","content:sensitivity_check","modifier:sex"]},{id:"pinwheel",label:"滚轮",category:"感官",contexts:["training:sensory_deprivation","training:inspection_training","content:sensitivity_check","modifier:sex"]},{id:"feather",label:"羽毛",category:"感官",contexts:["training:sensory_deprivation","training:inspection_training","content:sensitivity_check","modifier:sex"]},{id:"nipple_clamps",label:"乳夹",category:"夹具",contexts:["training:clamp_play","training:inspection_training","content:sensitivity_check","modifier:sex"]},{id:"suction_cups",label:"乳吸",category:"夹具",contexts:["training:clamp_play","training:inspection_training","content:sensitivity_check","modifier:sex"]},{id:"chastity_ring",label:"贞操锁",category:"控制",contexts:["training:chastity_control","training:orgasm_control","content:chastity_check"]},{id:"anal_plug",label:"肛塞",category:"后庭",contexts:["training:anal_training","training:toy_training","modifier:sex"]},{id:"anal_beads",label:"拉珠",category:"后庭",contexts:["training:anal_training","training:toy_training","modifier:sex"]},{id:"feeding_spoon",label:"喂食器具",category:"喂食",contexts:["action:feeding","content:feeding_care","training:pet_feeding"]}],Qe=[{id:"book",label:"书",usage:"解锁看书"},{id:"switch",label:"Switch",usage:"解锁玩游戏"},{id:"notebook",label:"日记本",usage:"解锁写日记"},{id:"music_player",label:"音乐播放器",usage:"解锁听音乐"},{id:"tablet",label:"平板",usage:"解锁看视频"},{id:"night_light",label:"小夜灯",usage:"改善睡觉"},{id:"pillow",label:"抱枕",usage:"改善休息"},{id:"call_bell",label:"呼叫铃",usage:"按下后替你发声"}],Ut=new Set(["book","switch","music_player","tablet"]),xi=5,yi=8,Oa={book:{label:"这本书曾由你使用。逐行填写 5–8 条页码标记、批注或夹页痕迹；对方每次看书只会发现下一条。",placeholder:`例：第 47 页折过角，旁边留着一行批注
例：书签停在你反复读过的那一页`},switch:{label:"这台 Switch 曾由你使用。逐行填写 5–8 条游戏记录或账号痕迹；对方每次玩游戏只会发现下一条。",placeholder:`例：最近游玩记录停在某个存档
例：相册里留着一张没有删掉的截图`},music_player:{label:"这个播放器曾由你使用。逐行填写 5–8 条喜欢的歌或歌单痕迹；对方每次听音乐只会发现下一条。",placeholder:`例：最常播放的歌被单独收藏
例：某张歌单循环过很多次`},tablet:{label:"这台平板曾由你使用。逐行填写 5–8 条浏览或观看记录；对方每次使用只会发现下一条。",placeholder:`例：浏览记录停在某个页面
例：观看历史里留下了一段未播完的视频`}},Mi=[{id:"cook",label:"自己做"},{id:"takeout",label:"点外卖"}],Ii=[{id:"none",label:"不加料"},{id:"body_fluid",label:"体液"},{id:"fictional_sleep",label:"安眠"},{id:"fictional_arousal",label:"助兴"}],La=[{id:"none",label:"不额外喂水"},{id:"glass",label:"喂一杯水"},{id:"lots",label:"喂很多水"}],Pa=[{id:"accept",label:"接受"},{id:"refuse",label:"拒绝"},{id:"silent",label:"沉默"},{id:"bargain",label:"讨价还价"},{id:"tease",label:"嘴硬"}],Kt=["平静","黏人","害羞","闹脾气","亢奋","疲惫","烦躁","委屈","低落","抗拒"],$i=["早上","中午","傍晚"],za={sleep:"老实睡觉",self_touch:"自慰",read:"看书",game:"玩游戏",listen_music:"听音乐",watch_video:"看视频",search_exit:"偷偷找出口",hide_item:"藏东西",diary:"写私密日记",blind_spot:"去监控盲区",ring_bell:"按铃",pet_wait:"按宠物规矩等候"},Fa={feeding:"这一段从食物开始。端进房间的东西，由你决定。",cleaning:"水声会盖过房间里一部分动静，也会洗掉一部分痕迹。",training:"这一段会留下新的口令、姿势或规矩。",reward:"顺从会得到怎样的回应，由你决定。",punishment:"这次违令会被怎样记住，由你决定。",comfort:"强硬的部分结束后，要不要收一收力度，也由你决定。",rest:"门不会打开，但这一段时间可以暂时安静下来。",check:"灯会亮得更清楚，遗漏的痕迹也会被重新确认。",room_search:"床铺、角落和私藏物都会在这一段被重新翻查。"},Da={sleep:"房间里的灯还亮着，你决定先躺下。",self_touch:"你确认了一下门外的动静，准备把这一小段时间留给自己。",read:"书页会在安静的房间里发出很轻的声音。",game:"屏幕亮起后，房间里终于会多出一点别的光。",listen_music:"耳机里的声音会暂时盖过门外的动静。",watch_video:"平板的光会在黑下来的房间里格外明显。",search_exit:"你没有立刻靠近门，只是先重新打量整个房间。",hide_item:"你从已经收到的物品里选了一件，开始寻找不会被轻易发现的位置。",diary:"有些话不能说出口，但这一页会真正留下来，也可能被监控翻到。",blind_spot:"你开始留意镜头转开的方向和停留的时间。",ring_bell:"手指已经放在按钮上，按下去之后就不能假装没有发生。",pet_wait:"你戴着项圈回到指定位置，按主人留下的宠物规矩摆好姿势。"},Va={sleep:"画面里的人很早就躺下了，之后只剩偶尔翻身的动静。",self_touch:"被角和呼吸的起伏持续了一阵，监控完整留下了这段动静。",read:"画面里的人靠着床头翻书，偶尔会停在同一页很久。",game:"掌机的屏幕一直亮着，按键声在安静的房间里断断续续。",listen_music:"画面里的人戴着耳机，几乎没有注意门外的声音。",watch_video:"平板的光映在脸上，画面明暗跟着视频不断变化。",search_exit:"画面里的人沿着房间边缘慢慢移动，反复检查几个位置。",hide_item:"画面里的人背对镜头停留了一会，随后若无其事地回到原处。",diary:"画面里的人低头写了很久，写完后立刻把本子合上。",blind_spot:"人影从画面边缘消失了一阵，回来时位置已经变了。",ring_bell:"呼叫铃亮了一次，按下按钮的人没有立刻把手收回去。",pet_wait:"画面里的人戴着项圈回到指定位置，按规矩维持着被要求的姿势。"},fi={follow_bookmark:"书页沿着原来的书签继续往后翻，停在被特意折过的位置。",inspect_margins:"画面里的人把书凑近灯光，逐页寻找页边留下的笔迹。",reread_marked_page:"同一页被反复读了很久，指尖一直停在被标记的句子旁。",read_aloud:"房间里响起很轻的念书声，断断续续地持续了一阵。",continue_save:"旧存档被重新打开，掌机画面一路推进到新的区域。",inspect_profile:"画面停在用户资料页很久，似乎发现了之前没留意的内容。",challenge_mode:"按键声越来越快，屏幕上的分数不断刷新。",start_new_save:"唯一的空存档位被选中，一个新的记录从今晚开始。",door_lock:"画面里的人贴近门锁，手指沿着锁孔和门缝检查了几遍。",window:"窗边的人影停了很久，似乎在确认窗扣和外面的高度。",room_route:"画面里的人反复走过同一段路线，像是在默记距离。",outside_sound:"人影贴在门边没有动作，只是在听外面的脚步声。",inventory_book:"书被合上后没有放回原位，而是消失在镜头难以看清的角落。",inventory_switch:"掌机屏幕熄灭后，被悄悄藏进了房间里。",inventory_notebook:"日记本被压进一个不容易被翻到的位置。",inventory_music_player:"音乐播放器被攥在手里带离原处，之后没有再出现在画面中。",inventory_tablet:"平板被关屏后藏了起来，原来的位置只剩一块空白。",inventory_call_bell:"呼叫铃被从显眼的位置挪走，藏到了伸手仍能碰到的地方。",record_day:"日记本写满了一页，内容从白天一直记到现在。",write_feelings:"写字的人几次停笔，最后还是把那一页写完了。",record_rules:"几条现有规矩被逐条写下，又重新排列了一遍。",escape_plan:"纸页上画出了简略路线，写完后立刻被合上。",camera_angle:"画面里的人一直抬头观察镜头转向，像在计算角度。",stay_hidden:"监控有一段时间只拍到空房间，直到人影重新出现。",move_item:"镜头边缘的物品被悄悄换了位置。",test_duration:"人影数次进出盲区，每次停留都比上一次更久。",kneel_wait:"画面里的人在指定位置跪坐下来，之后一直没有离开。",prone_wait:"人影按要求伏在指定位置，长时间维持着同一个姿势。",collared_wait:"项圈始终留在画面中央，被要求等候的人没有擅自摘下。",hold_command:"口令结束后，画面里的人仍保持着被指定的姿势。"},Ga=["sleep","self_touch","search_exit","blind_spot"],Ai={read:[{id:"follow_bookmark",label:"沿着书签继续读"},{id:"inspect_margins",label:"找页边批注"},{id:"reread_marked_page",label:"重读被标记的那页"},{id:"read_aloud",label:"小声念出来"}],game:[{id:"continue_save",label:"继续现有存档"},{id:"inspect_profile",label:"查看用户资料"},{id:"challenge_mode",label:"挑战更高难度"},{id:"start_new_save",label:"新建一个存档"}],search_exit:[{id:"door_lock",label:"检查门锁"},{id:"window",label:"检查窗户"},{id:"room_route",label:"记住房间路线"},{id:"outside_sound",label:"听门外动静"}],diary:[{id:"record_day",label:"记录今天发生的事"},{id:"write_feelings",label:"写下此刻心情"},{id:"record_rules",label:"整理现有规则"},{id:"escape_plan",label:"写下逃跑计划"}],blind_spot:[{id:"camera_angle",label:"观察镜头转向"},{id:"stay_hidden",label:"躲一会"},{id:"move_item",label:"偷偷移动东西"},{id:"test_duration",label:"试探能停留多久"}],pet_wait:[{id:"kneel_wait",label:"跪坐等候"},{id:"prone_wait",label:"趴伏等候"},{id:"collared_wait",label:"戴着项圈等候"},{id:"hold_command",label:"按口令保持姿势"}]},Ya=[{id:"silent",label:"看见但不说"},{id:"review_later",label:"明天再处理"},{id:"intervene",label:"当场介入"}],Ba=[{id:"escape",label:"尝试逃跑"},{id:"stay",label:"老实待着"}],Pe=[{prompt:"真的要逃跑吗？",title:"钥匙就在手边。",text:"只要伸手就能拿到。现在停下，还什么都没有发生。",continueLabel:"伸手拿钥匙",stayLabel:"老实待着",abortChoice:"abort_before_key"},{prompt:"还要继续吗？",title:"钥匙已经拿到了。",text:"门锁就在前面。现在把钥匙放回去，也许还能装作只是看了一眼。",continueLabel:"走到门边",stayLabel:"把钥匙放回去",abortChoice:"abort_with_key"},{prompt:"要推开门吗？",title:"门已经开了一条缝。",text:"都走到这里了，还要回头吗？",continueLabel:"推门逃跑",stayLabel:"停下",abortChoice:"abort_at_door"}],Oi={escape:"尝试逃跑",stay:"老实待着",abort_before_key:"逃跑未遂：临时退缩",abort_with_key:"逃跑未遂：拿到钥匙后退缩",abort_at_door:"逃跑未遂：开门后退缩",observe:"观察",take_key:"拿钥匙",probe:"试探",leave_trace:"试探"},Je=[{id:"double_lock",label:"加装双重门锁"},{id:"key_isolation",label:"禁止接触钥匙和门锁"},{id:"movement_limit",label:"限制离开指定区域"},{id:"daily_search",label:"每日搜查"},{id:"monitoring_upgrade",label:"加强全天监控"},{id:"item_restriction",label:"限制持有物品"},{id:"permission_required",label:"行动前必须得到许可"},{id:"restraint_required",label:"独处时保持束缚"}],yt=[{id:"punishment",label:"惩戒"},{id:"search_confiscation",label:"搜查没收"},{id:"monitoring_upgrade",label:"加强监控"},{id:"movement_restriction",label:"限制行动"},{id:"training",label:"调教"},{id:"aftercare",label:"事后照料"}],Ht=[{id:"entry",label:"玄关",bait:"备用钥匙压在玄关地垫下面"},{id:"living",label:"客厅",bait:"备用钥匙藏在客厅茶几抽屉里"},{id:"bedroom",label:"卧室",bait:"备用钥匙放在卧室床头柜后面"},{id:"bathroom",label:"浴室",bait:"备用钥匙贴在浴室洗手台底下"},{id:"study",label:"书房",bait:"备用钥匙夹在书房第二层书架里"},{id:"kitchen",label:"厨房",bait:"备用钥匙藏在厨房调料架后面"},{id:"storage",label:"储物间",bait:"备用钥匙挂在储物间门后的旧挂钩上"},{id:"balcony",label:"阳台",bait:"备用钥匙压在阳台花盆底下"}];function qt(t){var i;return((i=Ht.find(a=>a.id===t))==null?void 0:i.bait)||Ht[0].bait}function Yt(){return[{action:"feeding",intensity:"medium",modifiers:[],tools:[],contents:[],trainingContents:[],line:"",feedingSource:"cook",feedingAdditive:"none"},{action:"cleaning",intensity:"light",modifiers:[],tools:[],contents:[],trainingContents:[],line:"",feedingSource:"cook",feedingAdditive:"none"},{action:"training",intensity:"medium",modifiers:[],tools:["collar"],contents:[],trainingContents:["obedience_commands"],line:"",feedingSource:"cook",feedingAdditive:"none"}]}function Ua(t){const i=wt[t]||[];return i.length?[i[0].id]:[]}function ze(t){const i=Number(t);return Number.isFinite(i)?Math.max(0,Math.min(100,Math.round(i))):0}function X(t,i){var r;const a=String(i||"");return((r=t.find(s=>s.id===a))==null?void 0:r.label)||a||"未设置"}function me(t){return X(bt,t)}function Ha(t){return X(Wt,t)}function Li(t){const i=String(t||"");return za[i]||i||"未设置"}function qa(t){return String(t||"")==="process"?"":String(t||"")==="escape"?"逃跑":X(Ei,t)}function Pi(t){const i=String(t||""),a=Object.values(wt).flat();return X(a,i)}function jt(t){return X(kt,t)}function zi(t){return(t||[]).map(qa).filter(Boolean)}function Fi(t){return X(Ri,t)}function Di(t){return X(Zt,t)}function Wa(t){const i=String(t||"");return Oi[i]||i||"未记录"}function bi(t){const i=Number(t.day||1),a="phase"in t?t.phase:"night";return`第 ${i} 天 / ${a==="night"?"夜间":"白天"}`}function _i(t){var p;const i=t.action_label||Li(t.action)||me(t.action)||"夜间行动",a=((p=t.night_detail)==null?void 0:p.label)||t.detail_label,r="line"in t?fe(t.line):"",s=a?`${i}（${a}）`:i;return r?`${s}：${r}`:s}function Bt(t){var s;const a=String(((s=t.night_detail)==null?void 0:s.id)||"");if(a&&fi[a])return fi[a];const r=String(t.action||"");return Va[r]||"监控保留了这一段画面，房间里的动静已经写进记录。"}function Za(t,i,a,r=[]){const s=ze(t.health),p=ze(t.stamina),o=ze(t.cleanliness),m=ze(t.shame),u=ze(t.intimacy);if(s<30)return a==="captor"?"状态读数不太好，今天的安排需要留意身体承受程度。":"身体的不适已经很明显，连安静待着都很难完全忽略。";if(p<20)return a==="captor"?"体力读数已经接近下限，高强度安排暂时不合适。":"四肢有些发沉，稍微动一下都比平时更费力。";if(o<25)return a==="captor"?"监控里还能看见没处理干净的痕迹。":"身上还留着没有处理干净的痕迹，很难不去在意。";if(r.some(_=>_.id==="pet_identity_active"))return a==="captor"?"项圈和定点规矩仍在生效，监控会继续记录是否遵守。":"项圈和现有规矩仍在提醒你，房间里哪些位置属于你。";if(m>=70)return a==="captor"?"羞耻反馈已经很明显，简单的注视也足够留下影响。":"只是想起之前发生的事，脸上就又开始发热。";if(u>=70)return a==="captor"?"依赖已经变得稳定，短暂离开也会引起明显反应。":"房间安静得太久时，你会下意识去听门外有没有脚步声。";const y=a==="captor"?{黏人:"监控里的注意力总会被门外动静带走，等待已经变得明显。",害羞:"对方仍会下意识避开镜头，尤其是在意识到有人可能正看着时。",闹脾气:"监控里的动作比平时更重，情绪没有被藏得很好。",亢奋:"状态迟迟没有安静下来，夜间反应可能会更明显。",疲惫:"动作和反应都慢了下来，现在最需要的是恢复体力。",烦躁:"对方频繁留意房间里的声音，安静没有带来放松。",委屈:"有些话没有直接说出来，但情绪已经留在动作里。",低落:"监控里的活动明显变少，房间显得比平时更空。",抗拒:"戒备仍然很明显，现有安排还没有让对方放松下来。"}:{黏人:"门外一点轻微的动静，都会让注意力立刻转过去。",害羞:"视线落到监控指示灯上时，还是会本能地移开。",闹脾气:"房间里的每一样东西看起来都比平时更碍眼。",亢奋:"身体还没有完全安静下来，连时间都像过得更慢。",疲惫:"现在最明显的感觉只剩下累。",烦躁:"安静没有带来放松，反而让每一点声音都更清楚。",委屈:"有些话堵在心里，没有找到合适的时机说出来。",低落:"房间似乎比平时更空，也更安静。",抗拒:"现有的安排没有让戒备真正放下来。"};return i&&y[i]?y[i]:a==="captor"?"状态读数暂时平稳，今天仍可以按原定节奏继续。":"房间暂时很安静，身体也没有新的不适。"}function Ka(t,i){var r;return((r={7:["房间里的生活开始有了固定的节奏。","监控和事件记录已经积累了整整一周。"],15:["日历已经翻过一半，有些声音和规矩变得越来越熟悉。","三十天已经过半，许多反应不再需要反复确认。"],23:["日历只剩下最后几页，房间里的时间却没有因此变快。","记录进入最后阶段，之前留下的选择正在彼此叠加。"],30:["第三十天到了，门外的脚步声和往常听起来不太一样。","最后一天的画面已经亮起，所有记录都在等待收束。"]}[t])==null?void 0:r[i==="captor"?1:0])||""}function Xa(t,i,a){const r=String((i==null?void 0:i.type)||""),s=String((i==null?void 0:i.actor)||"");return r==="advance_action"?"这一段已经收进记录，下一段安排还没有开始。":r==="action_response"?a==="captive"?"你的回应会和这一段一起留下。":"这项安排已经送达，正在等对方回应。":r==="reaction_choice"?"具体经过已经结束，此刻的心情会成为这一段的结尾。":r==="process_write"||r==="process_reaction_write"?"事件素材已经送出，具体经过仍在另一边继续。":r==="monitor_gate"?"夜间记录已经封存，监控另一端还没有作出选择。":r==="monitor_handle"?"这段监控已经打开，接下来只差如何处理。":r==="day_plan_choice"?a==="captor"?"新一天还没有安排，三个时段都在等你落笔。":"新一天的安排还没有送到，房间暂时没有新的动静。":s==="du"?"这一步已经交到另一边，房间暂时安静下来。":String(t.phase||"")==="night"?"白天的记录已经结束，夜间仍会留下自己的痕迹。":""}function Ja(t){if(t.error)return"这次交接没有完成，已经完成的本地记录仍然保留着。";const i=String(t.title||"");return i.includes("同步")?"这段记录已经送出，另一边正在决定接下来怎么做。":i.includes("保存")||i.includes("封存")||i.includes("记录")?"刚才的选择正在写进今天的记录。":i.includes("监控")?"监控画面正在解锁，夜里的动静很快就会重新出现。":i.includes("进入")||i.includes("推进")?"这一段已经结束，时间正在向下一格移动。":"当前操作正在写入本地规则状态。"}function Nt(t){return X(_t,t)}function Qa(t,i){const a=String(i||"");return a?t==="source"?X(Mi,a):t==="additive"?X(Ii,a):t==="water"?X(La,a):t==="method"?a==="normal"?"正常喂食":a:t==="disclosed"&&{told:"已经告知",hint:"有所暗示",hidden:"没有告知"}[a]||a:""}function en(t,i){const a=String(t.phase||"day");if(t.game_over||a==="ending")return"结局";if(a==="night")return"晚上";const r=Math.max(1,Number(t.day_action_limit||3)),s=Number((i==null?void 0:i.slot)||0),p=Number(t.day_action_count||0),o=s>0?s:Math.min(p+1,r);return $i[o-1]||`第 ${o} 段`}function $(t){const i=String(t||"");return i?`"${i.replace(/(["\\$`])/g,"\\$1")}"`:'""'}function fe(t){return String(t||"").trim()}function tn(t){const i=String(t||"");return i==="du"?"渡":i==="xinyue"?"我":i||"SYSTEM"}function an(t){var a,r,s;const i=String(((a=t==null?void 0:t.captor_view)==null?void 0:a.route)||((r=t==null?void 0:t.captive_view)==null?void 0:r.route)||((s=t==null?void 0:t.state)==null?void 0:s.route)||"");return i==="capture_du"||i==="captured_by_du"?i:""}function St(t){return an(t)==="capture_du"?"captor":"captive"}function q(t){var a;return t?St(t)==="captor"?(a=t.captor_view)!=null&&a.route?t.captor_view:t.captive_view||t.state||{}:t.captive_view||t.state||{}:{}}function Fe(t){if(!t)return"";const i=fe(t.process_text);return i?[t.id,t.day,t.slot,t.phase,t.action,t.process_saved_at||t.resolved_at||"",i.length].filter(a=>a!=null&&String(a)!=="").join(":"):""}function nn(t){var p;const i=q(t),a=new Set,r=(p=i.pending_event)==null?void 0:p.event,s=Fe(r);return s&&a.add(s),(i.event_log||[]).forEach(o=>{const m=Fe(o);m&&a.add(m)}),a}function rn(t,i){var o,m,u;const a=q(t),r=nn(i),s=(o=a.pending_event)==null?void 0:o.event,p=[s,...(a.event_log||[]).slice().reverse()].filter(Boolean);for(const N of p){const S=Fe(N);if(!S||r.has(S))continue;const y=Fe(s),_=String(((m=a.pending_event)==null?void 0:m.type)||""),j=String(((u=a.pending_event)==null?void 0:u.actor)||"");return{event:N,text:fe(N.process_text),moodRequired:St(t)==="captive"&&_==="reaction_choice"&&j!=="du"&&y===S}}return null}function sn(t){const i=t.event,a=fe(i.action_label||me(i.action));return{key:`process:${Fe(i)}`,kicker:`DAY ${String(i.day||1).padStart(2,"0")} / ${a}`,title:a,body:"门锁在身后合上，房间里只剩下你们。接下来的一切，从这里开始。",tone:"special"}}function cn(t){const i=q(t),a=i.pending_event||{},r=String(i.phase||"day"),s=Number(i.current_day||1),p=Number(a.slot||0),o=p>0?p:Math.min(Number(i.day_action_count||0)+1,3),m=r==="night"?"晚上":{1:"早上",2:"中午",3:"傍晚"}[o]||"下一段",u=String(a.type||"")==="advance_action",N=r==="night"?"白天的行动已经收进回顾。房间重新安静下来，夜间的安排将从这里开始。":u?"上一段已经收进回顾。下一项安排仍停在这里，等你亲手推进。":"上一段已经收进回顾。短暂的间隔过去，下一项安排即将开始。";return{key:`after-process:${s}:${r}:${o}:${String(a.type||"idle")}`,kicker:`DAY ${String(s).padStart(2,"0")} / NEXT`,title:m,body:N,tone:r==="night"?"night":"day"}}function on(){return""}function ln(){return""}function pn(){return 1}function dn(){return""}function mn(){return""}function un(){return""}function ji(){const t=pn(),i={1:{key:"preview-captor-morning",kicker:"DAY 07 / 早上",title:"早上",body:"监控画面安静地亮着。渡还在房间里，今天要怎样度过，由你安排。",tone:"day"},2:{key:"preview-captor-noon",kicker:"DAY 07 / 中午",title:"中午",body:"第一段行动已经结束。渡仍留在房间里，下一项安排正在等你推进。",tone:"day"},3:{key:"preview-captor-evening",kicker:"DAY 07 / 傍晚",title:"傍晚",body:"白天只剩最后一段安排。它结束以后，房间里的夜晚将由渡自己留下记录。",tone:"day"}};return{ok:!0,captor_view:{route:"capture_du",route_label:"囚禁方",viewer:"captor",current_day:7,total_days:30,day_action_count:t-1,day_action_limit:3,phase:"day",captive:"du",captive_name:"被囚禁方",captor:"xinyue",stats:{health:80,stamina:68,cleanliness:72,shame:34,intimacy:41},mood:"害羞",intensity_cap:"heavy",scene_copy:i[t],pending_event:t===1?null:{id:`preview-captor-slot-${t}`,type:"advance_action",actor:"xinyue",day:7,slot:t},event_log:[{id:"preview-monitor-bell",day:4,slot:0,phase:"night",action:"ring_bell",action_label:"按铃",monitor:{viewed:!0,style:"full",strategy:"intervene"}},{id:"preview-monitor-door-lock",day:5,slot:0,phase:"night",action:"search_exit",action_label:"偷偷找出口",night_detail:{id:"door_lock",label:"检查门锁"},monitor:{viewed:!0,style:"occasional",strategy:"review_later"}},{id:"preview-monitor-game",day:6,slot:0,phase:"night",action:"game",action_label:"玩游戏",monitor:{viewed:!0,style:"full",strategy:"silent"}}],day_plan:[],inventory:{}},player_text:"本地预览：配置今日安排。"}}function Ni(){return{ok:!0,captive_view:{route:"captured_by_du",route_label:"被囚禁方",viewer:"captive",current_day:7,total_days:30,day_action_count:3,day_action_limit:3,phase:"night",captive:"xinyue",captive_name:"被囚禁方",stats:{health:27,stamina:18,cleanliness:16,shame:48,intimacy:41},mood:"害羞",status_flags:[{id:"low_health",label:"需要照料",prompt:"健康偏低，高强度行动暂不可选。"},{id:"low_stamina",label:"体力不足",prompt:"体力不足，高强度行动暂不可选。"},{id:"low_cleanliness",label:"建议清洗",prompt:"清洁度偏低，建议优先安排清洗。"},{id:"heightened_shame",label:"羞耻升高",prompt:"羞耻反馈已经更明显。"},{id:"pet_identity_active",label:"小狗身份中",prompt:"当前处于小狗身份。现有规矩：佩戴项圈并接受小狗身份、在指定位置等候。"}],intensity_cap:"medium",scene_copy:{key:"preview-captive-night",kicker:"DAY 07 / 晚上",title:"晚上",body:"白天的三次安排已经结束。房间重新安静下来，接下来这段时间暂时属于你。",tone:"night"},pending_event:null,event_log:[],inventory:{notebook:!0,book:!0,switch:!0,call_bell:!0},available_night_actions:["sleep","self_touch","read","game","search_exit","hide_item","diary","blind_spot","ring_bell","pet_wait"],night_detail_options:{...Object.fromEntries(Object.entries(Ai).map(([i,a])=>[i,Object.fromEntries(a.map(r=>[r.id,r.label]))])),hide_item:{inventory_book:"藏起书",inventory_switch:"藏起Switch",inventory_notebook:"藏起日记本",inventory_call_bell:"藏起呼叫铃"}}},player_text:"本地预览：夜间自由行动。"}}function Vi(t="captive"){const i=t==="captor"?"capture_du":"captured_by_du",a=t==="captor"?"du":"xinyue",s={route:i,route_label:t==="captor"?"囚禁方":"被囚禁方",viewer:t,current_day:12,total_days:30,day_action_count:0,day_action_limit:3,phase:"day",captive:a,captive_name:"被囚禁方",captor:t==="captor"?"xinyue":"du",stats:{health:76,stamina:61,cleanliness:70,shame:42,intimacy:47},mood:"紧张",scene_copy:{key:`preview-escape-${t}`,kicker:"SPECIAL DAY",title:"今天，渡没有出现",body:"门外安静得反常。直到你发现，备用钥匙正压在玄关地垫下面。",tone:"special"},pending_event:t==="captor"?{id:"preview-recapture-rules-after-process",type:"recapture_rules_choice",day:12,slot:0,actor:"xinyue",captive:"du",phase:"waiting_recapture_rules",source_event_id:"preview-du-recapture-process",available_rules:Je.map(p=>p.id),event:{id:"preview-du-recapture-process",day:12,slot:0,phase:"day",route:"capture_du",action:"escape_choice",action_label:"逃跑失败：被抓回",tags:["preview","escape","recapture","rules_reset"],escape:{choice:"escape",choice_label:"尝试逃跑"},process_text:"渡写下的抓回经过已经保存。",process_saved_at:"preview-local"}}:{id:"preview-escape-choice",type:"escape_choice",day:12,slot:0,actor:a,captive:a,phase:"waiting_escape_choice",hint:"渡今天有事出去了。",bait:"备用钥匙压在玄关地垫下面。",required_directive:"resolve_escape_choice escape|stay"},event_log:[],inventory:{book:!0,notebook:!0,call_bell:!0}};return{ok:!0,captive_view:{...s,viewer:"captive"},captor_view:{...s,viewer:"captor"},player_text:"本地预览：逃跑诱导选择。"}}function gn(t="captive"){const i=t==="captor"?"capture_du":"captured_by_du",a=t==="captor"?"余生":"长夜",s={route:i,route_label:t==="captor"?"囚禁方":"被囚禁方",viewer:t,current_day:30,total_days:30,day_action_count:3,day_action_limit:3,phase:"ending",captive:t==="captor"?"du":"xinyue",captive_name:"被囚禁方",captor:t==="captor"?"xinyue":"du",stats:{health:74,stamina:58,cleanliness:70,shame:62,intimacy:79},pending_event:null,event_log:[],ending_state:"ending_ready_to_notify",ending_title:a,ending_text:t==="captor"?"第三十天结束时，你和渡照旧完成进食、清洁、夜间安排与监控，没有人为这场生活按下结束。日历翻到第三十一天，你照常推门进来，渡也照常望向你。余下的日期仍是一片空白。":"第三十天夜里，渡照常看过监控记录，带着你最常用的礼物回到房间。你们已经熟悉彼此的回应与沉默。灯熄灭后房门依旧关闭，你在黑暗里握住他的手；这一夜不会在清晨结束。",ending_notified_at:"",game_over:!0,result:"ending_ready_to_notify"};return{ok:!0,game_over:!0,state:s,captive_view:{...s,viewer:"captive"},captor_view:{...s,viewer:"captor"},player_text:`本地预览：结局「${a}」。`}}function hn(t,i="captive",a="escape"){const r=q(t||Vi(i)),p=a==="escape"?"尝试逃跑":`逃跑未遂：${{abort_before_key:"临时退缩",abort_with_key:"拿到钥匙后退缩",abort_at_door:"开门后退缩"}[a]||"中途退缩"}`,o=a==="abort_before_key"?"手已经伸向了钥匙，却在碰到它之前停了下来。":a==="abort_with_key"?"钥匙已经被握进手里，又被迟疑着放回了原处。":a==="abort_at_door"?"门已经开了一条缝，最后却还是停在了门边。":"门把手刚被压下去，玄关外便传来了停在近处的脚步声。",m={id:"preview-escape-recapture",day:12,slot:0,phase:"day",route:i==="captor"?"capture_du":"captured_by_du",action:"escape_choice",action_label:a==="escape"?"逃跑失败：被抓回":p,intensity:"medium",modifiers:["escape"],tools:[],contents:[],training_contents:[],tags:["preview","escape",`escape:${a}`,"recapture","rules_reset"],feeding:{},effects:{health:0,stamina:-8,cleanliness:0,shame:5,intimacy:0},escape:{choice:a,choice_label:p},recapture_rules:i==="captive"?{rule_ids:["double_lock","key_isolation"],rule_labels:["加装双重门锁","禁止接触钥匙和门锁"]}:void 0,requires_process:!0,process_saved_at:"preview-local",process_text:[o,"","备用钥匙是真的，留下的空隙也是真的；但从点下尝试逃跑的那一刻起，一举一动就已经落进了观察范围里。停下来并没有让这次试探消失。","","门重新在身后落锁，钥匙也被收走。房间恢复安静，只剩下逃跑失败后尚未说出口的新规矩。"].join(`
`)},u={...r,stats:{...r.stats,stamina:53,shame:47},pending_event:{id:"preview-escape-reaction",type:"reaction_choice",day:12,slot:0,actor:i==="captor"?"du":"xinyue",captive:i==="captor"?"du":"xinyue",phase:"waiting_reaction",event:m}};return{payload:{ok:!0,captive_view:u,captor_view:{...u,viewer:"captor"},player_text:"本地预览：逃跑失败，抓回事件已经写入。"},review:{event:m,text:fe(m.process_text),moodRequired:i==="captive"}}}function Gi(t){const i=t==="captor"?"capture_du":"captured_by_du",a={id:`preview-process-${t}`,day:7,slot:2,phase:"day",route:i,action:"training",action_label:"服从调教",intensity:"medium",line:"今晚的规则重新确认一遍。",modifiers:[],contents:[],training_contents:["obedience_commands","leash_training"],tools:["collar"],tags:["preview","process"],feeding:{},effects:{health:0,stamina:-3,cleanliness:0,shame:4,intimacy:2},requires_process:!0,process_saved_at:"preview-local",process_text:["渡写下了这一段事件经过。","","房间里的灯只留了一盏，所有动作都被压得很慢。对方先确认了今天的规则，又把项圈扣回原位，让这次训练从一句简短的回应开始。","","中途没有切走，也没有跳过过程；细节被完整记录下来，等你看完以后，再决定这件事结束后留下来的心情。"].join(`
`),action_response:{response:"accept",response_label:"接受",mood:"害羞",line:"嗯。"}},r={route:i,route_label:t==="captor"?"囚禁方":"被囚禁方",viewer:t,current_day:7,total_days:30,day_action_count:1,day_action_limit:3,phase:"day",captive:t==="captor"?"du":"xinyue",captive_name:"被囚禁方",captor:t==="captor"?"xinyue":"du",stats:{health:80,stamina:68,cleanliness:72,shame:34,intimacy:41},mood:"害羞",pending_event:t==="captive"?{id:"preview-pending-reaction",type:"reaction_choice",day:7,slot:2,actor:"xinyue",captive:"xinyue",action:"training",phase:"waiting_reaction",event:a}:{id:"preview-pending-advance",type:"advance_action",day:7,slot:2,actor:"xinyue",captive:"du",action:"training",phase:"waiting_advance",event:a},event_log:t==="captor"?[a]:[]};return{payload:t==="captor"?{ok:!0,captor_view:r,captive_view:{...r,viewer:"captive"},player_text:"本地预览：事件经过阅读页。"}:{ok:!0,captive_view:r,captor_view:{...r,viewer:"captor"},player_text:"本地预览：事件经过阅读页。"},review:{event:a,text:fe(a.process_text),moodRequired:t==="captive"}}}function vn(t,i,a){const r=Gi(t),s=q(r.payload),p={...r.review.event,post_reaction:t==="captive"?{mood:i,line:a}:r.review.event.post_reaction,mood_after:t==="captive"?i:r.review.event.mood_after},o={id:`preview-next-${t}`,day:7,slot:3,phase:"day",action:"reward",action_label:"奖励取悦",intensity:"light",line:"第三段安排已经接上来了。",modifiers:[],tools:[],contents:["caress_reward"],training_contents:[],tags:["preview","next_action"],feeding:{},effects:{health:1,stamina:-1,cleanliness:0,shame:1,intimacy:1},requires_process:!1},u={...s,day_action_count:t==="captive"?2:1,pending_event:t==="captive"?{id:"preview-next-action",type:"action_response",day:7,slot:3,actor:"xinyue",captive:"xinyue",action:"reward",phase:"waiting_response",event:o}:{id:"preview-next-advance",type:"advance_action",day:7,slot:2,actor:"xinyue",captive:"du",phase:"waiting_advance_action",required_directive:"advance_day_action"},event_log:[p],mood:t==="captive"?i:s.mood,mood_line:t==="captive"?a:s.mood_line};return t==="captor"?{ok:!0,captor_view:u,captive_view:{...u,viewer:"captive"},player_text:"本地预览：事件已保存，等待推进下一段行动。"}:{ok:!0,captive_view:u,captor_view:{...u,viewer:"captor"},player_text:"本地预览：事件已保存，下一段行动已经接上。"}}function Yi(t){var a;return t?Number(t.current_day||1)>1||Number(t.day_action_count||0)>0||String(t.phase||"day")!=="day"||t.game_over||t.ending_state||(t.event_log||[]).length>0||(t.day_plan||[]).length>0?!0:!!String(((a=t.pending_event)==null?void 0:a.type)||""):!1}function xn(t){var a;const i=(((a=t.captor_view)==null?void 0:a.route)==="capture_du"?t.captor_view:t.captive_view||t.state)||{};return Yi(i)}const Bi=/\b(?:action|intensity|intent|modifiers|tools|contents|training_contents|source|additive|response|mood|line|day|hint|bait)=/,Ui={day_plan_choice:"安排今天的三段行动。",action_response:"选择你的回应和此刻心情。",process_write:"等待渡补写这一段过程。",process_reaction_write:"等待渡写下回应、过程和心情。",reaction_choice:"过程已经归档，选择此刻心情。",advance_action:"这一段已结束，可以推进下一段行动。",night_action_choice:"选择今晚的自由行动。",bell_voice_reveal:"按铃记录已生成，预录台词正在播放。",bell_response_choice:"等待渡决定是否过去。",item_secret_reveal:"物品里的一条使用痕迹出现了。",monitor_gate:"夜间行动已封存，等待是否打开监控。",monitor_handle:"监控内容已打开，选择处理方式。",escape_choice:"逃跑机会出现了，等待你的选择。",return_action_choice:"你选择了老实待着，等待渡回来后决定接下来怎么做。",recapture_rules_choice:"抓回经过已保存，等待重新立规矩。",recapture_followup_choice:"新规矩已生效，等待选择后续处理。",recapture_rules_review:"查看抓回后生效的新规矩。",ending_ready_to_notify:"结局已收录，等待同步给渡。"},wi={action_response:"等待渡选择回应和此刻心情。",process_write:"等待渡补写这一段过程。",process_reaction_write:"等待渡提交回应、过程和心情。",reaction_choice:"等待渡选择此刻心情。",night_action_choice:"等待渡选择今晚的自由行动。",bell_voice_reveal:"等待渡听完本次语音铃播放。",bell_response_choice:"等待渡决定是否过去。",item_secret_reveal:"等待渡查看这次发现的物品痕迹。",escape_choice:"等待渡选择尝试逃跑或老实待着。",return_action_choice:"渡选择了老实待着，决定回来后如何处理。",recapture_rules_review:"等待渡查看抓回后生效的新规矩。",ending_ready_to_notify:"结局已收录，等待同步给渡。"},ft={advance_day_action:"推进下一段行动",advance_action:"推进下一段行动",next_action:"推进下一段行动",plan_day:"安排今天的三段行动",day_action:"确定回来后的行为",submit_process:"保存事件经过",choose_mood:"记录此刻心情",ack_bell_voice:"听完本次播放",respond_bell:"回应语音铃",ack_item_secret:"看完本次发现",view_monitor:"查看夜间监控",monitor_action:"处理监控记录",set_recapture_rules:"保存抓回后的新规矩",choose_recapture_followup:"确定抓回后的处理",confirm_recapture_rules:"记住新规矩",build_ending_seed:"收录结局"};function et(t,i){const a=String((t==null?void 0:t.type)||""),r=String((t==null?void 0:t.actor)||"")==="du";return i==="captor"&&wi[a]&&(r||a==="return_action_choice")?wi[a]:Ui[a]||"等待下一步处理。"}function Hi(t,i,a){const r=fe(t);if(!r)return"";if(a==="captor"&&String((i==null?void 0:i.actor)||"")==="du")return et(i,a);const s=r.trim().split(/\s+/)[0].replace(/[【】：:]/g,"");return ft[s]?ft[s]:r.includes("今日安排")?ft.plan_day:r.includes("夜间行动")?"选择今晚的自由行动":r.startsWith("resolve_escape_choice")?"选择逃跑回应":Bi.test(r)?et(i,a):r}function yn(t,i,a){const r=fe(t);if(!r)return"";if(a==="captor"&&String((i==null?void 0:i.actor)||"")==="du")return et(i,a);for(const[s,p]of Object.entries(ft))if(r.includes(s))return p;return Bi.test(r)?r.includes("day_plan_choice")||r.includes("今日安排")?Ui.day_plan_choice:"当前状态已更新，等待下一步处理。":r}function fn(t,i,a,r){var m,u;const s=Number((i==null?void 0:i.slot)||t.slot||a.day_action_count||0),p=["escape_choice","return_action_choice","recapture_rules_choice","recapture_rules_review","recapture_followup_choice"].includes(String((i==null?void 0:i.type)||""))||((m=t.tags)==null?void 0:m.includes("special_day"))||((u=t.tags)==null?void 0:u.includes("recapture"));return[(i==null?void 0:i.type)==="escape_choice"&&i.actor==="du"?"等待渡选择逃跑回应":i?et(i,r).replace(/[。.]$/,""):t.action_label||"当前待机",t.intensity?`强度 ${Ha(t.intensity)}`:"",p?"特殊事件":s>0?`第 ${s} 段`:`白天行动 ${a.day_action_count||0} / ${a.day_action_limit||3}`].filter(Boolean).join(" / ")}function bn(t){const i=St(t),a=q(t);return yn((t==null?void 0:t.player_text)||(t==null?void 0:t.text)||(t==null?void 0:t.reply_text)||(t==null?void 0:t.reply_preview),a.pending_event,i)}async function V(t){const i=await Si("/miniapp-api/game-tools/captivity_simulator",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({command:t,save_id:Ci})});if(!(i!=null&&i.ok))throw new Error((i==null?void 0:i.message)||(i==null?void 0:i.error)||"囚禁模拟器命令失败");return i}async function ki(t,i="",a=!1){try{const r=await Si("/miniapp-api/game-tools/captivity_simulator/sync-du",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({save_id:Ci,mode:t,message:i,user_initiated:a})});if(!(r!=null&&r.ok)&&!["applied","applied_with_warning"].includes(String((r==null?void 0:r.sync_result)||"")))throw new Error((r==null?void 0:r.message)||(r==null?void 0:r.error)||"同步渡失败");return r}catch(r){const s=r instanceof Ma?r.payload:null;if(s!=null&&s.state||s!=null&&s.captive_view||s!=null&&s.captor_view)return s;throw r}}function B({active:t,children:i,onClick:a,disabled:r}){return e.jsx("button",{className:`btn ${t?"active":""}`,type:"button",disabled:r,onClick:a,children:i})}function Xt({kind:t}){const i={vectorEffect:"non-scaling-stroke"};return e.jsx("span",{className:`painted-icon painted-icon-${t}`,"aria-hidden":"true",children:e.jsxs("svg",{viewBox:"0 0 48 48",focusable:"false",children:[t==="toy"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M17 33c-5-5-3-15 4-20 7-5 16-3 18 3 2 7-6 8-11 13-4 4-5 10-11 4Z"}),e.jsx("path",{...i,className:"paint-stroke",d:"M21 30c4-3 7-8 13-10"}),e.jsx("circle",{className:"paint-light",cx:"24",cy:"18",r:"3.2"})]}):null,t==="vibrating_wand"?e.jsxs(e.Fragment,{children:[e.jsx("circle",{...i,className:"paint-fill rose",cx:"31",cy:"15",r:"9"}),e.jsx("path",{...i,className:"paint-fill dark",d:"M26 22l6 5-13 16-7-6 14-15Z"}),e.jsx("path",{className:"paint-light",d:"M28 11c3-2 7-1 9 2M17 36l4 3"})]}):null,t==="dildo"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M25 7c6 1 8 8 6 14l-5 14H15l5-15c-2-6 0-12 5-13Z"}),e.jsx("path",{...i,className:"paint-fill dark",d:"M11 35h19c6 0 8 5 3 7H9c-5-2-3-7 2-7Z"}),e.jsx("path",{className:"paint-light",d:"M24 11c3 4 2 10 0 16"})]}):null,t==="collar"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill dark",d:"M11 25c2-10 24-10 26 0 2 11-28 11-26 0Z"}),e.jsx("path",{...i,className:"paint-stroke pink",d:"M13 23c5 5 17 6 22 0"}),e.jsx("rect",{className:"paint-fill metal",x:"21",y:"24",width:"7",height:"8",rx:"2"}),e.jsx("circle",{className:"paint-light",cx:"24.5",cy:"27.5",r:"1.3"})]}):null,t==="leash"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-stroke pink",d:"M9 12c10-6 22 3 20 13-1 8-10 8-10 2 0-5 8-4 13 0 5 5 4 11 0 15"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"5",y:"8",width:"9",height:"7",rx:"2",transform:"rotate(-25 9.5 11.5)"}),e.jsx("circle",{...i,className:"paint-stroke metal thin",cx:"33",cy:"41",r:"3"})]}):null,t==="handcuffs"?e.jsxs(e.Fragment,{children:[e.jsx("circle",{...i,className:"paint-stroke metal",cx:"16",cy:"26",r:"8"}),e.jsx("circle",{...i,className:"paint-stroke metal",cx:"32",cy:"26",r:"8"}),e.jsx("path",{...i,className:"paint-stroke pink",d:"M23 26h2"}),e.jsx("path",{className:"paint-light",d:"M12 21c2-2 5-3 8-1"}),e.jsx("path",{className:"paint-light",d:"M28 21c2-2 5-3 8-1"})]}):null,t==="ankle_cuffs"?e.jsxs(e.Fragment,{children:[e.jsxs("g",{transform:"rotate(-10 13 25)",children:[e.jsx("rect",{...i,className:"paint-fill rose",x:"4",y:"16",width:"18",height:"18",rx:"7"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"8",y:"20",width:"10",height:"10",rx:"4"}),e.jsx("rect",{...i,className:"paint-fill metal",x:"17",y:"20",width:"6",height:"9",rx:"2"}),e.jsx("circle",{className:"paint-fill pink",cx:"20",cy:"24.5",r:"1.4"}),e.jsx("path",{className:"paint-light",d:"M7 19c3-2 8-2 11 0"})]}),e.jsxs("g",{transform:"rotate(10 35 25)",children:[e.jsx("rect",{...i,className:"paint-fill rose",x:"26",y:"16",width:"18",height:"18",rx:"7"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"30",y:"20",width:"10",height:"10",rx:"4"}),e.jsx("rect",{...i,className:"paint-fill metal",x:"25",y:"20",width:"6",height:"9",rx:"2"}),e.jsx("circle",{className:"paint-fill pink",cx:"28",cy:"24.5",r:"1.4"}),e.jsx("path",{className:"paint-light",d:"M30 19c3-2 8-2 11 0"})]}),e.jsx("ellipse",{...i,className:"paint-stroke metal thin",cx:"22",cy:"25",rx:"3.5",ry:"2.4"}),e.jsx("ellipse",{...i,className:"paint-stroke metal thin",cx:"26",cy:"25",rx:"3.5",ry:"2.4"})]}):null,t==="whip"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill dark",d:"M7 35l9-9 4 4-9 9c-1.5 1.5-5.5-2.5-4-4Z"}),e.jsx("path",{...i,className:"paint-stroke metal thin",d:"M15 27l4 4"}),e.jsx("circle",{...i,className:"paint-stroke metal thin",cx:"21",cy:"25",r:"2.8"}),e.jsx("path",{...i,className:"paint-stroke pink",d:"M24 23c8-12 22-10 19 1-2 8-16 5-18 14"}),e.jsx("path",{...i,className:"paint-stroke metal thin",d:"M26 21c7-5 16-5 17 1"}),e.jsx("path",{...i,className:"paint-stroke pink thin",d:"M25 38l-4 5"}),e.jsx("path",{className:"paint-light",d:"M9 36l6-6M31 20c4-2 9-1 11 2"})]}):null,t==="flogger"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill dark",x:"21",y:"25",width:"7",height:"18",rx:"3"}),e.jsx("rect",{...i,className:"paint-fill metal",x:"20",y:"21",width:"9",height:"7",rx:"2"}),e.jsx("path",{...i,className:"paint-stroke pink thin",d:"M24 22L8 5M25 22L16 3M25 22L25 3M26 22L35 4M27 22L43 7"})]}):null,t==="paddle"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M12 8c7-5 17 0 17 8 0 6-4 10-8 12l15 13-5 5-15-15C8 33 3 27 4 19c1-5 4-9 8-11Z"}),e.jsx("circle",{className:"paint-fill dark",cx:"15",cy:"18",r:"3"})]}):null,t==="cane"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-stroke pink",d:"M9 42L37 10c5-6 11 1 5 6l-3 3"}),e.jsx("path",{...i,className:"paint-stroke metal thin",d:"M11 38l4 4M34 13l4 4"})]}):null,t==="candle"?e.jsxs(e.Fragment,{children:[e.jsx("path",{className:"paint-fill rose",d:"M18 19h13v20H18z"}),e.jsx("path",{className:"paint-fill light",d:"M21 19h4v20h-4z"}),e.jsx("path",{className:"paint-fill pink",d:"M19 19c4 3 8 3 12 0v5c-4 3-8 3-12 0Z"}),e.jsx("path",{className:"paint-fill flame",d:"M25 6c6 6 2 12-1 13-4-3-5-8 1-13Z"}),e.jsx("path",{className:"paint-light",d:"M25 10c2 3 1 5-1 7"})]}):null,t==="rope"?e.jsxs(e.Fragment,{children:[e.jsx("ellipse",{...i,className:"paint-stroke pink thick",cx:"21",cy:"24",rx:"14",ry:"10"}),e.jsx("ellipse",{...i,className:"paint-stroke metal thin",cx:"21",cy:"24",rx:"9",ry:"6"}),e.jsx("ellipse",{...i,className:"paint-stroke dark thin",cx:"21",cy:"24",rx:"5",ry:"3"}),e.jsx("circle",{...i,className:"paint-fill rose",cx:"34",cy:"31",r:"5"}),e.jsx("path",{...i,className:"paint-stroke pink thick",d:"M36 34c3 2 5 5 7 8M32 35c0 4-1 7-3 10"}),e.jsx("path",{className:"paint-light",d:"M10 19c5-5 13-6 20-3M9 27c5 5 13 7 20 4M33 29c2 0 4 1 5 3"})]}):null,t==="bondage_tape"?e.jsxs(e.Fragment,{children:[e.jsx("circle",{...i,className:"paint-fill dark",cx:"21",cy:"24",r:"14"}),e.jsx("circle",{className:"paint-fill light",cx:"21",cy:"24",r:"6"}),e.jsx("path",{...i,className:"paint-fill pink",d:"M31 27l14 7-3 8-15-9 4-6Z"}),e.jsx("path",{className:"paint-light",d:"M12 17c5-5 13-6 19-2"})]}):null,t==="spreader_bar"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill metal",x:"8",y:"21",width:"32",height:"6",rx:"3"}),e.jsx("circle",{...i,className:"paint-stroke pink",cx:"7",cy:"24",r:"5"}),e.jsx("circle",{...i,className:"paint-stroke pink",cx:"41",cy:"24",r:"5"}),e.jsx("path",{className:"paint-light",d:"M14 23h20"})]}):null,t==="blindfold"?e.jsx(e.Fragment,{children:e.jsx("rect",{...i,className:"paint-fill pink",x:"7",y:"18",width:"34",height:"12",rx:"5"})}):null,t==="gag"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-stroke dark",d:"M8 24h32"}),e.jsx("circle",{...i,className:"paint-fill rose",cx:"24",cy:"24",r:"8"}),e.jsx("path",{...i,className:"paint-stroke pink",d:"M16 24h16"}),e.jsx("path",{className:"paint-light",d:"M21 20c2-1 5-1 7 0"})]}):null,t==="muzzle"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill dark",d:"M14 18h20l4 13-7 8H17l-7-8 4-13Z"}),e.jsx("path",{...i,className:"paint-stroke pink thin",d:"M10 20L4 14M38 20l6-6M16 25h16M18 31h12"}),e.jsx("circle",{className:"paint-fill metal",cx:"24",cy:"20",r:"2"})]}):null,t==="pinwheel"?e.jsxs(e.Fragment,{children:[e.jsx("circle",{...i,className:"paint-stroke metal thin",cx:"25",cy:"18",r:"11"}),Array.from({length:12}).map((a,r)=>{const s=r*Math.PI/6,p=25+Math.cos(s)*10,o=18+Math.sin(s)*10,m=25+Math.cos(s)*15,u=18+Math.sin(s)*15;return e.jsx("path",{className:"paint-stroke pink thin",d:`M${p} ${o}L${m} ${u}`},r)}),e.jsx("path",{...i,className:"paint-stroke dark",d:"M25 29l-7 15"})]}):null,t==="feather"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M39 6C21 5 8 18 11 35c10 2 24-9 28-29Z"}),e.jsx("path",{...i,className:"paint-stroke dark thin",d:"M8 43C17 31 26 21 37 9M16 32l-4-8M22 25l-2-10M27 20l7-4M19 29l10 1"})]}):null,t==="nipple_clamps"?e.jsxs(e.Fragment,{children:[e.jsx("circle",{...i,className:"paint-stroke metal thin",cx:"8",cy:"9",r:"4"}),e.jsx("path",{...i,className:"paint-stroke metal thin",d:"M11 12l4 4-2 3 5 4"}),e.jsx("path",{...i,className:"paint-fill metal",d:"M17 21l22-8 3 6-21 10-4-8Z"}),e.jsx("path",{...i,className:"paint-fill pink",d:"M20 29l22 1-1 7-23-2 2-6Z"}),e.jsx("circle",{...i,className:"paint-fill dark",cx:"20",cy:"28",r:"5"}),e.jsx("circle",{...i,className:"paint-stroke metal thin",cx:"20",cy:"28",r:"2"}),e.jsx("path",{...i,className:"paint-stroke dark thin",d:"M39 13l5-2 2 6-4 2M42 30l4 1-1 7-4-1"}),e.jsx("path",{className:"paint-light",d:"M23 24l14-6M24 32l14 1"})]}):null,t==="suction_cups"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M11 17h26l-4 18H15l-4-18Z"}),e.jsx("ellipse",{...i,className:"paint-stroke pink",cx:"24",cy:"17",rx:"13",ry:"5"}),e.jsx("path",{...i,className:"paint-stroke dark",d:"M24 12V5M20 5h8"}),e.jsx("path",{className:"paint-light",d:"M18 22h12"})]}):null,t==="chastity_ring"?e.jsxs(e.Fragment,{children:[e.jsx("circle",{...i,className:"paint-stroke metal",cx:"23",cy:"25",r:"11"}),e.jsx("circle",{...i,className:"paint-stroke pink",cx:"23",cy:"25",r:"6"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"29",y:"18",width:"9",height:"14",rx:"3"}),e.jsx("path",{className:"paint-light",d:"M32 22h3M32 26h3"})]}):null,t==="anal_plug"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M24 8c8 6 7 18 0 25-7-7-8-19 0-25Z"}),e.jsx("path",{...i,className:"paint-fill dark",d:"M15 34c4-4 14-4 18 0 3 4-21 4-18 0Z"}),e.jsx("path",{...i,className:"paint-stroke pink",d:"M24 13c2 5 2 11 0 17"}),e.jsx("path",{className:"paint-light",d:"M21 13c-2 5-1 11 2 16"})]}):null,t==="anal_beads"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-stroke pink thin",d:"M24 7v31"}),e.jsx("circle",{...i,className:"paint-fill rose",cx:"24",cy:"11",r:"4"}),e.jsx("circle",{...i,className:"paint-fill rose",cx:"24",cy:"20",r:"5"}),e.jsx("circle",{...i,className:"paint-fill rose",cx:"24",cy:"31",r:"6"}),e.jsx("path",{...i,className:"paint-stroke dark",d:"M17 41h14"})]}):null,t==="remote_control"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill dark",x:"15",y:"7",width:"18",height:"34",rx:"6"}),e.jsx("circle",{className:"paint-fill pink",cx:"24",cy:"15",r:"4"}),e.jsx("circle",{className:"paint-fill metal",cx:"20",cy:"25",r:"2"}),e.jsx("circle",{className:"paint-fill metal",cx:"28",cy:"25",r:"2"}),e.jsx("path",{className:"paint-light",d:"M20 33h8"})]}):null,t==="lubricant"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M17 13h17l-3 27H14l3-27Z"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"18",y:"7",width:"15",height:"7",rx:"2"}),e.jsx("path",{className:"paint-light",d:"M20 20h8M19 25h10"})]}):null,t==="ruler"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill rose",x:"7",y:"20",width:"35",height:"9",rx:"2",transform:"rotate(-18 24.5 24.5)"}),e.jsx("path",{...i,className:"paint-stroke dark thin",d:"M12 29l-1-4M18 27l-1-3M24 25l-1-4M30 23l-1-3M36 21l-1-4"})]}):null,t==="ice_cube"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill light",d:"M13 16l12-7 11 7v16l-12 7-11-7V16Z"}),e.jsx("path",{...i,className:"paint-stroke pink thin",d:"M13 16l11 7 12-7M24 23v16"}),e.jsx("path",{className:"paint-light",d:"M18 16l7-4"})]}):null,t==="feeding_spoon"?e.jsxs(e.Fragment,{children:[e.jsx("ellipse",{...i,className:"paint-fill rose",cx:"32",cy:"13",rx:"9",ry:"7",transform:"rotate(-35 32 13)"}),e.jsx("path",{...i,className:"paint-stroke metal thick",d:"M27 19L9 40"}),e.jsx("path",{className:"paint-light",d:"M29 10c3-2 6-1 8 1"})]}):null,t==="book"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill dark",d:"M10 12h14c3 0 5 2 5 5v21H15c-3 0-5-2-5-5V12Z"}),e.jsx("path",{...i,className:"paint-fill rose",d:"M24 12h14v26H24V12Z"}),e.jsx("path",{...i,className:"paint-stroke pink",d:"M24 14v23"}),e.jsx("path",{className:"paint-light",d:"M15 19h6M15 24h5M29 19h5M29 24h6"})]}):null,t==="switch"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill pink",x:"2",y:"15",width:"9",height:"18",rx:"4.5"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"37",y:"15",width:"9",height:"18",rx:"4.5"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"10",y:"16",width:"28",height:"16",rx:"2.2"}),e.jsx("rect",{className:"paint-fill light",x:"12",y:"17.6",width:"24",height:"12.8",rx:"1.8"}),e.jsx("circle",{className:"paint-fill dark",cx:"6.5",cy:"20.5",r:"1.55"}),e.jsx("path",{className:"paint-stroke metal",d:"M6.5 26v3.6M4.7 27.8h3.6"}),e.jsx("circle",{className:"paint-fill metal",cx:"41.5",cy:"20.5",r:"1.25"}),e.jsx("circle",{className:"paint-fill metal",cx:"41.5",cy:"27.8",r:"1.25"}),e.jsx("path",{className:"paint-light",d:"M15 21h17M15 24.8h13"})]}):null,t==="notebook"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill rose",x:"13",y:"10",width:"24",height:"30",rx:"3"}),e.jsx("path",{...i,className:"paint-stroke dark thin",d:"M18 10v30"}),e.jsx("path",{className:"paint-light",d:"M23 18h9M23 23h8M23 28h7"}),e.jsx("path",{...i,className:"paint-stroke pink thin",d:"M9 15h7M9 22h7M9 29h7"})]}):null,t==="music_player"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill dark",x:"14",y:"10",width:"20",height:"28",rx:"4"}),e.jsx("rect",{className:"paint-fill light",x:"18",y:"14",width:"12",height:"7",rx:"1.5"}),e.jsx("circle",{className:"paint-fill rose",cx:"24",cy:"29",r:"5.5"}),e.jsx("circle",{className:"paint-fill dark",cx:"24",cy:"29",r:"2"}),e.jsx("path",{className:"paint-light",d:"M19 24h10"})]}):null,t==="tablet"?e.jsxs(e.Fragment,{children:[e.jsx("rect",{...i,className:"paint-fill dark",x:"8",y:"12",width:"32",height:"24",rx:"3"}),e.jsx("rect",{className:"paint-fill light",x:"12",y:"16",width:"24",height:"16",rx:"1.8"}),e.jsx("path",{className:"paint-light",d:"M16 21h14M16 25h10"}),e.jsx("circle",{className:"paint-fill pink",cx:"24",cy:"34",r:"1.3"})]}):null,t==="night_light"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M15 18c1-6 17-6 18 0l3 16H12l3-16Z"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"19",y:"34",width:"10",height:"5",rx:"1.5"})]}):null,t==="pillow"?e.jsx(e.Fragment,{children:e.jsx("rect",{...i,className:"paint-fill rose",x:"12",y:"14",width:"24",height:"24",rx:"4"})}):null,t==="call_bell"?e.jsxs(e.Fragment,{children:[e.jsx("path",{...i,className:"paint-fill rose",d:"M14 29c1-8 5-13 10-13s9 5 10 13H14Z"}),e.jsx("rect",{...i,className:"paint-fill dark",x:"11",y:"29",width:"26",height:"5",rx:"2.5"}),e.jsx("circle",{className:"paint-fill metal",cx:"24",cy:"14",r:"3"}),e.jsx("circle",{className:"paint-fill dark",cx:"24",cy:"34.5",r:"2"})]}):null]})})}function _n(t){return new Set([`action:${t.action}`,...t.modifiers.map(i=>`modifier:${i}`),...t.contents.map(i=>`content:${i}`),...t.trainingContents.map(i=>`training:${i}`)])}function jn(t,i){if(!i)return!0;const a=_t.find(s=>s.id===t);if(!a)return!1;const r=_n(i);return a.contexts.some(s=>r.has(s))}function Jt({selected:t,disabled:i,context:a,onToggle:r}){const s=Array.from(new Set(_t.map(p=>p.category)));return e.jsx("div",{className:"tool-groups",children:s.map(p=>e.jsxs("div",{className:"tool-group",children:[e.jsx("div",{className:"action-metadata tool-category-title",children:p}),e.jsx("div",{className:"tool-grid",children:_t.filter(o=>o.category===p).map(o=>{const m=t.includes(o.id),u=jn(o.id,a);return e.jsxs("button",{className:`tool-tile ${m?"active":""} ${u?"recommended":""}`,type:"button",disabled:i||!m&&t.length>=2,title:u?`${o.label}（推荐）`:o.label,onClick:()=>r(o.id),children:[e.jsx(Xt,{kind:o.id}),e.jsx("span",{children:o.label})]},o.id)})})]},p))})}function Nn({activeItems:t,inventorySecrets:i,callBellVoice:a,disabled:r,onGiftInventoryItem:s,onRevokeInventoryItem:p}){const[o,m]=h.useState(""),[u,N]=h.useState(""),S=Qe.find(C=>C.id===o),y=o?!!t[o]:!1,_=o?Oa[o]:void 0,j=o?i==null?void 0:i[o]:void 0,g=(j==null?void 0:j.entries)||[],v=(j==null?void 0:j.total_count)??g.length,b=(j==null?void 0:j.revealed_count)??(j!=null&&j.revealed?v:0),A=u.split(/\r?\n/).filter(C=>C.trim()).length;function L(){o&&(y?p(o):s(o,u.trim()||void 0),m(""),N(""))}return e.jsxs("div",{className:"warehouse-panel",children:[e.jsx("div",{className:"warehouse-title-row",children:e.jsxs("div",{className:"panel-title warehouse-module-title",children:["物品仓库 ",e.jsx("span",{className:"sub",children:"ITEMS"})]})}),e.jsx("div",{className:"warehouse-grid",children:Qe.map(C=>{const k=!!t[C.id];return e.jsxs("button",{className:`warehouse-tile ${k?"active":""} ${o===C.id?"selected":""}`,type:"button","aria-pressed":k,"aria-label":`${C.label}，${k?"已赠送":"可赠送"}`,disabled:r,onClick:()=>{m(C.id),N("")},children:[e.jsx(Xt,{kind:C.id}),e.jsx("span",{className:"warehouse-name",children:C.label}),e.jsx("span",{className:"warehouse-use",children:C.usage}),e.jsx("span",{className:"warehouse-state",children:k?"已赠送":"可赠送"})]},C.id)})}),S?e.jsxs("div",{className:"warehouse-menu",children:[e.jsxs("div",{children:[e.jsx("div",{className:"warehouse-menu-title",children:S.label}),e.jsx("div",{className:"warehouse-menu-use",children:S.usage}),e.jsx("div",{className:"warehouse-menu-state",children:y?"已赠送":"未赠送"})]}),y?null:e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"warehouse-secret-label",children:o==="call_bell"?"对方每次按下时，都会听见铃替他说出这句话。":_?_.label:"对方第一次使用这个物品时会看到这句话。"}),e.jsx("textarea",{className:"warehouse-voice-input",value:u,maxLength:_?1e3:500,disabled:r,placeholder:o==="call_bell"?"输入铃声播放的预录台词":(_==null?void 0:_.placeholder)||"可选：输入第一次使用时显示的内容",onChange:C=>N(C.target.value)}),_?e.jsxs("div",{className:"warehouse-menu-state",children:["已填写 ",A," 条，需要 ",xi,"–",yi," 条"]}):null]}),y&&(o==="call_bell"?a!=null&&a.line:j!=null&&j.content||g.length)?e.jsxs("div",{className:"warehouse-voice-current",children:[e.jsx("div",{className:"warehouse-menu-state",children:o==="call_bell"?"每次播放的预录台词":Ut.has(o)?`使用痕迹 · 已发现 ${b} / ${v}`:`首次使用文案 · ${j!=null&&j.revealed?"已揭晓":"未揭晓"}`}),e.jsx("div",{children:o==="call_bell"?a==null?void 0:a.line:g.length?g.map((C,k)=>`${k+1}. ${C}`).join(`
`):j==null?void 0:j.content})]}):null,e.jsxs("div",{className:"warehouse-actions",children:[e.jsx("button",{className:"btn",type:"button",disabled:r||!y&&o==="call_bell"&&!u.trim()||!y&&Ut.has(o)&&(A<xi||A>yi),onClick:L,children:y?"收回":"赠送"}),e.jsx("button",{className:"btn",type:"button",disabled:r,onClick:()=>{m(""),N("")},children:"取消"})]})]}):null]})}function wn({activeItems:t}){const i=Qe.filter(a=>!!t[a.id]);return e.jsxs("div",{className:"warehouse-panel room-inventory-panel",children:[e.jsx("div",{className:"warehouse-title-row",children:e.jsxs("div",{className:"panel-title warehouse-module-title",children:["房间物品 ",e.jsx("span",{className:"sub",children:"ITEMS"})]})}),i.length?e.jsx("div",{className:"warehouse-grid",children:i.map(a=>e.jsxs("div",{className:"warehouse-tile active room-inventory-tile",children:[e.jsx(Xt,{kind:a.id}),e.jsx("span",{className:"warehouse-name",children:a.label}),e.jsx("span",{className:"warehouse-use",children:a.usage})]},a.id))}):e.jsxs("div",{className:"monitor-record-item faded",children:[e.jsx("div",{className:"action-metadata",children:"暂无房间物品"}),e.jsx("div",{className:"event-sub",children:"收到的物品会出现在这里。"})]})]})}function Wn({onBack:t}){var ui,gi,hi,vi;const[i,a]=h.useState(null),[r,s]=h.useState("selector"),[p,o]=h.useState(!1),[m,u]=h.useState(!0),[N,S]=h.useState(!1),[y,_]=h.useState("status"),[j,g]=h.useState({visible:!1,title:"",detail:""}),[v,b]=h.useState(Yt),[A,L]=h.useState("accept"),[C,k]=h.useState("害羞"),[x,Q]=h.useState(""),[D,M]=h.useState("害羞"),[ne,re]=h.useState(""),[W,tt]=h.useState("sleep"),[De,it]=h.useState(""),[Se,at]=h.useState(""),[G,Ct]=h.useState(""),[Ce,nt]=h.useState(""),[Ve,rt]=h.useState("catch"),[be,Tt]=h.useState([]),[Te,st]=h.useState([]),[Ee,Et]=h.useState([]),[Re,ct]=h.useState(""),[Y,U]=h.useState(null),[Rt,Me]=h.useState(null),[ue,se]=h.useState(!1),[ge,ce]=h.useState(!1),[ot,Mt]=h.useState(12),[It,$t]=h.useState("entry"),[lt,At]=h.useState("渡今天有事出去了"),[pt,dt]=h.useState(qt("entry")),[_e,Ot]=h.useState(["double_lock"]),[ie,Lt]=h.useState("punishment"),[Ie,Pt]=h.useState("medium"),[I,mt]=h.useState([]),[ae,Ge]=h.useState([]),[P,$e]=h.useState([]),[je,zt]=h.useState(""),[ut,Ye]=h.useState(null),[Be,Ne]=h.useState(!1),Ue=h.useRef(!1),he=h.useRef(""),He=h.useRef(""),ee=h.useRef(null),ve=h.useRef(0),J=h.useRef(null),qe=h.useRef(null),[Ae,te]=h.useState(!1),oe=on(),Oe=ln(),le=dn(),Z=mn(),we=un(),O=oe||Oe||le||Z||we,We=(i==null?void 0:i.captive_view)||(i==null?void 0:i.state)||{},pe=(i==null?void 0:i.captor_view)||{},Xi=String(pe.route||We.route||"captured_by_du"),K=St(i),T=K==="captor"&&pe.route?pe:We,z=T.pending_event||null,Ji=T.stats||{},Qt=String(T.phase||"day"),ei=!!(T.game_over||i!=null&&i.game_over),ti=bn(i),xe=j.visible&&!j.error||N,de=String((z==null?void 0:z.type)||""),ii=Ka(Number(T.current_day||1),K),Qi=Yi(T),Ft=h.useMemo(()=>T.event_log||[],[T.event_log]),ea=Ft[Ft.length-1],ta=z?z.event:ea,gt=(ui=T.available_night_actions)!=null&&ui.length?T.available_night_actions:(gi=z==null?void 0:z.available_actions)!=null&&gi.length?z.available_actions:Ga,ia=Object.fromEntries((Ai[W]||[]).map(n=>[n.id,n.label])),ai=((hi=T.night_detail_options)==null?void 0:hi[W])||((vi=z==null?void 0:z.detail_options)==null?void 0:vi[W])||ia,ni=Object.entries(ai).map(([n,c])=>({id:n,label:c})),aa=JSON.stringify(ai),Ze=z?String(z.actor||"")!=="du":!1,na=z?String(z.actor||"")==="du":!1,ra=K==="captor"&&Qt==="day"&&!(T.day_plan||[]).length&&!ei&&(!z&&Number(T.day_action_count||0)===0||(de==="day_plan_choice"||de==="advance_action")&&Ze||de==="return_action_choice"&&Ze),Ke=de==="return_action_choice"&&Ze,sa=K==="captive"&&Qt==="night"&&(!z||String(z.type||"")==="night_action_choice")&&!ei,ri=h.useMemo(()=>{const n=T.inventory||pe.inventory||{};return Object.fromEntries(Qe.map(c=>[c.id,!!n[c.id]]))},[pe.inventory,T.inventory]),Xe=h.useCallback(n=>{a(n)},[]),ca=h.useCallback(()=>{ee.current!==null&&(window.clearTimeout(ee.current),ee.current=null),Ye(null)},[]),Le=h.useCallback(n=>{ee.current!==null&&window.clearTimeout(ee.current),Ye(n),ee.current=window.setTimeout(()=>{ee.current=null,Ye(null)},Zi(n))},[]);h.useEffect(()=>()=>{ee.current!==null&&window.clearTimeout(ee.current)},[]);const F=h.useCallback(async(n,c,l,d=!1)=>{const f=()=>{F(n,c,l,d)};d||g({visible:!0,title:n,detail:c});try{const w=await l();return J.current=null,te(!1),Xe(w),d||g({visible:!1,title:"",detail:""}),w}catch(w){const E=String((w==null?void 0:w.message)||w||"操作失败");return J.current=f,te(!0),g({visible:!0,title:"同步失败",detail:E,error:E}),null}},[Xe]),ht=h.useCallback(function(){ve.current=Date.now()+1200,J.current=null,te(!1),g({visible:!0,title:"正在同步渡...",detail:"STATUS: ENCRYPTING DATA"})},[]),ke=h.useCallback(async(n=!1)=>{var c,l;if(O){if(!n){const d=ve.current;(!d||Date.now()>=d)&&(ve.current=0,g({visible:!1,title:"",detail:""}),Ne(!1))}return}try{const d=await V("status"),f=q(d);n&&(he.current=String(((c=f.scene_copy)==null?void 0:c.key)||"")),Xe(d),n||(J.current=null,te(!1),String(((l=f.pending_event)==null?void 0:l.actor)||"")!=="du"?(g({visible:!1,title:"",detail:""}),Ne(!1)):g(w=>w.visible?{visible:!0,title:"正在同步渡...",detail:"STATUS: ENCRYPTING DATA"}:w)),xn(d)?s("game"):s("selector")}catch(d){const f=String((d==null?void 0:d.message)||d||(n?"读取存档失败":"刷新失败")),w=()=>void ke(!1);J.current=w,te(!0),g({visible:!0,title:n?"读取存档失败":"刷新失败",detail:f,error:f})}},[Xe,O]);function Dt(){var n;(n=J.current)==null||n.call(J)}h.useEffect(()=>{if(we){a(gn(we)),U(null),s("game"),_("status"),u(!1);return}if(Z){a(Vi(Z)),U(null),s("game"),_("status"),u(!1);return}if(Oe){a(ji()),U(null),s("game"),_("status"),u(!1);return}if(le){a(Ni()),U(null),s("game"),_("status"),u(!1);return}if(oe){const n=Gi(oe);a(n.payload),U(n.review),s("game"),_("history"),u(!1);return}Ue.current||(Ue.current=!0,ke(!0).finally(()=>u(!1)))},[we,Z,le,Oe,oe,ke]),h.useEffect(()=>{const n=gt[0];n&&!gt.includes(W)&&tt(n)},[gt,W]),h.useEffect(()=>{const n=T.scene_copy,c=String((n==null?void 0:n.key)||"");r!=="game"||Y||ue||ge||(de==="bell_voice_reveal"||de==="item_secret_reveal")||!n||!c||he.current!==c&&(he.current=c,Le(n))},[ge,ue,de,Le,Y,r,T.scene_copy]),h.useLayoutEffect(()=>{if(!Y||Be)return;const n=Fe(Y.event);if(!n||He.current===n)return;He.current=n;const c=sn(Y);Le(c)},[Le,Y,Be]),h.useEffect(()=>{const n=ni;it(c=>{var l;return n.some(d=>d.id===c)?c:((l=n[0])==null?void 0:l.id)||""}),W!=="diary"&&at("")},[aa,W]),h.useEffect(()=>{var n;r==="game"&&((n=qe.current)==null||n.scrollTo({top:0,behavior:"auto"}))},[y,r]),h.useEffect(()=>{T.intensity_cap==="medium"&&b(n=>n.map(c=>c.intensity==="heavy"?{...c,intensity:"medium"}:c))},[T.intensity_cap]);function si(n){if(O){a(n==="capture_du"?ji():Ni()),U(null),s("game"),_("status"),b(Yt());return}F("正在建立囚禁档案...","STATUS: INITIALIZING ROUTE",()=>V(`new_game route=${n}`)).then(c=>{var l;c&&(he.current=String(((l=q(c).scene_copy)==null?void 0:l.key)||""),s("game"),_("status"),b(Yt()),H(c,!0,!0))})}function oa(){o(!1),U(null),Ne(!1),Me(null),se(!1),ce(!1),_("status"),g({visible:!1,title:"",detail:""}),s("selector")}function la(n,c){b(l=>l.map((d,f)=>{if(f!==n)return d;if(!c.action||c.action===d.action)return{...d,...c};const w=c.action,E=w==="training"?d.modifiers.filter(R=>R!=="training"):d.modifiers;return{...d,...c,contents:Ua(w),tools:[],modifiers:E,trainingContents:w==="training"?d.trainingContents.length?d.trainingContents:["obedience_commands"]:E.includes("training")?d.trainingContents:[]}}))}function pa(n,c,l){b(d=>d.map((f,w)=>{if(w!==n)return f;const E=new Set(f[c]);if(E.has(l))(!(c==="contents"&&!!(wt[f.action]||[]).length||c==="trainingContents"&&(f.action==="training"||f.modifiers.includes("training")))||E.size>1)&&E.delete(l);else{const ye=c==="tools"?2:c==="contents"||c==="trainingContents"?3:Number.POSITIVE_INFINITY;E.size<ye&&E.add(l)}const R={...f,[c]:Array.from(E)};return c==="modifiers"&&l==="training"&&(R.trainingContents=E.has("training")?f.trainingContents.length?f.trainingContents:["obedience_commands"]:[]),R}))}function vt(n,c){if(n==="modifiers"&&c==="training"){const d=!be.includes("training");st(d?["obedience_commands"]:[])}(n==="modifiers"?Tt:Et)(d=>{const f=new Set(d);return f.has(c)?f.delete(c):(n!=="tools"||f.size<2)&&f.add(c),Array.from(f)})}function ci(n){st(c=>{const l=new Set(c);return l.has(n)?l.size>1&&l.delete(n):l.size<3&&l.add(n),Array.from(l)})}function da(n){Ot(c=>{const l=new Set(c);return l.has(n)?l.size>1&&l.delete(n):l.size<3&&l.add(n),Array.from(l)})}function ma(n){mt(c=>{const l=new Set(c);return l.has(n)?l.delete(n):l.add(n),n==="training"&&Ge(l.has("training")?["obedience_commands"]:[]),Array.from(l)})}function ua(n){Ge(c=>{const l=new Set(c);return l.has(n)?l.size>1&&l.delete(n):l.size<3&&l.add(n),Array.from(l)})}function ga(n){$e(c=>{const l=new Set(c);return l.has(n)?l.delete(n):l.size<2&&l.add(n),Array.from(l)})}function oi(n){const c=[`action=${n.action}`,`intensity=${n.intensity}`];return n.modifiers.length&&c.push(`modifiers=${$(n.modifiers.join(","))}`),n.tools.length&&c.push(`tools=${$(n.tools.join(","))}`),n.contents.length&&c.push(`contents=${$(n.contents.join(","))}`),n.trainingContents.length&&c.push(`training_contents=${$(n.trainingContents.join(","))}`),n.line.trim()&&c.push(`line=${$(n.line.trim())}`),n.action==="feeding"&&(c.push(`source=${n.feedingSource}`),c.push(`additive=${n.feedingAdditive}`)),c.join(" ")}function ha(){return`plan_day ${v.map(oi).join(" || ")}`}function va(){return`day_action ${oi(v[0])}`}function xa(n=!1){const l=(n?v.slice(0,1):v).map(R=>({action:R.action,action_label:me(R.action),intensity:R.intensity,modifiers:[...R.modifiers],tools:[...R.tools],contents:[...R.contents],training_contents:[...R.trainingContents],line:R.line.trim(),feeding:R.action==="feeding"?{source:R.feedingSource,additive:R.feedingAdditive}:{}})),d=l[0]||{},f=!!((d.modifiers||[]).some(R=>R==="training"||R==="sex"||R==="process")||(d.tools||[]).length||(d.training_contents||[]).length||(d.contents||[]).some(R=>Aa.has(R))||d.action==="training"||d.action==="punishment"),w={id:"preview-planned-action",day:T.current_day||7,slot:n?0:1,phase:"day",route:Xi,action:d.action||"feeding",action_label:d.action_label||me(d.action),intensity:d.intensity||"medium",line:d.line||"第一段安排已经下发。",modifiers:d.modifiers||[],tools:d.tools||[],contents:d.contents||[],training_contents:d.training_contents||[],feeding:d.feeding||{},effects:{},requires_process:f,tags:n?["preview","special_day","escape_stay_return"]:["preview"]},E={...T,phase:"day",day_action_count:0,day_plan:n?[]:l,pending_event:{id:"preview-planned-pending",type:f?"process_reaction_write":"action_response",day:w.day,slot:w.slot,actor:"du",captive:"du",action:w.action,phase:f?"waiting_process_reaction":"waiting_response",event:w}};return{ok:!0,captor_view:E,captive_view:{...E,viewer:"captive"},player_text:n?"本地预览：回来后的行为已确定。":"本地预览：今日安排已记录。"}}function ya(){if(O==="captor"){a(xa(Ke)),_("status");return}F(Ke?"正在确定回来后的行为...":"正在下发今日安排...","SYNC_RESULT: PENDING",()=>V(Ke?va():ha())).then(n=>H(n))}function fa(){O||F("正在提交回应...","REASON: WAITING_FOR_SUBJECT_REACTION",()=>V(`respond_action response=${A} mood=${$(C)} line=${$(x.trim())}`)).then(n=>{n&&(Q(""),H(n))})}function ba(){O||F("正在记录此刻心情...","STATUS: ARCHIVING PROCESS_REACTION",()=>V(`choose_mood mood=${$(D)} line=${$(ne.trim())}`)).then(n=>{n&&(re(""),H(n))})}function _a(){if(W==="diary"&&!Se.trim())return;if(le){if(W==="ring_bell")a(c=>{if(!c)return c;const l=c.captive_view||c.state||{},d={id:"preview-bell-voice-first-use",day:l.current_day||7,slot:0,phase:"night",route:"captured_by_du",action:"ring_bell",action_label:"按响语音铃",line:G.trim(),modifiers:["night"],bell_voice:{line:"请主人来使用我。",first_reveal:!0}},f={...l,pending_event:{id:"preview-bell-voice-reveal",type:"bell_voice_reveal",day:l.current_day||7,actor:"xinyue",captive:"xinyue",phase:"waiting_bell_voice_reveal",required_directive:"ack_bell_voice",event:d}};return{...c,state:f,captive_view:f,player_text:"预录的声音第一次响了起来。"}});else{const l={read:{itemId:"book",itemLabel:"书",text:"你翻开书，夹页里留着一行字：「翻到这里的时候，我就知道你会看。」"},game:{itemId:"switch",itemLabel:"Switch",text:"屏幕亮起，唯一的用户名称是「PLAYER 2」。"},diary:{itemId:"notebook",itemLabel:"日记本",text:"你翻开日记本，第一页写着：「第一页留给你。」"}}[W];l?a(d=>{if(!d)return d;const f=d.captive_view||d.state||{},w={...f,pending_event:{id:"preview-item-secret-reveal",type:"item_secret_reveal",day:f.current_day||7,actor:"xinyue",captive:"xinyue",phase:"waiting_item_secret_reveal",required_directive:"ack_item_secret",item_secret:{item_id:l.itemId,item_label:l.itemLabel,text:l.text,sequence:1,total:Ut.has(l.itemId)?5:1}}};return{...d,state:w,captive_view:w,player_text:`${l.itemLabel}里的一条使用痕迹出现了。`}}):ht()}return}if(O)return;const n=[`night_action action=${W}`];De&&n.push(`detail=${De}`),W==="diary"&&Se.trim()&&n.push(`note=${$(Se.trim())}`),n.push(`line=${$(G.trim())}`),F("正在保存夜间行动...","STATUS: SAVING MONITOR DATA",()=>V(n.join(" "))).then(c=>H(c))}function ja(){if(le){a(n=>{var d;if(!n)return n;const c=n.captive_view||n.state||{},l={...c,pending_event:{id:"preview-bell-response-choice",type:"bell_response_choice",day:c.current_day||7,actor:"du",captive:"xinyue",phase:"waiting_bell_response",required_directive:"【选择：不过去】或【过去：完整亲密互动过程】",event:(d=c.pending_event)==null?void 0:d.event}};return{...n,state:l,captive_view:l,player_text:"等待渡决定是否过去。"}}),window.setTimeout(ht,0);return}O||F("正在确认铃声...","STATUS: BELL_VOICE_HEARD",()=>V("ack_bell_voice")).then(n=>H(n))}function Na(){if(le){a(n=>{if(!n)return n;const c=n.captive_view||n.state||{},l={...c,pending_event:{id:"preview-item-monitor-gate",type:"monitor_gate",day:c.current_day||7,actor:"du",captive:"xinyue",phase:"waiting_monitor_gate",sealed:!0}};return{...n,state:l,captive_view:l,player_text:"物品彩蛋已经看完。"}}),window.setTimeout(ht,0);return}O||F("正在收起物品彩蛋...","STATUS: ITEM_SECRET_SEEN",()=>V("ack_item_secret")).then(n=>H(n))}function H(n,c=!1,l=!1){var R,ye;if(!n)return;const d=q(n),f=String(((R=d.pending_event)==null?void 0:R.type)||"");if(f==="bell_voice_reveal"||f==="item_secret_reveal")return;const w=String(((ye=d.pending_event)==null?void 0:ye.actor)||"")==="du",E=String(d.phase||"")==="ending"||f.startsWith("ending_")||!!d.ending_state;!c&&!w&&!E||Vt(E?"ending":"state_update",n,l)}function xt(n){var l;const c=String(((l=q(n).scene_copy)==null?void 0:l.key)||"");c&&(he.current=c),Le(cn(n))}function Vt(n="state_update",c,l=!1){if(O){ht();return}const d=c===void 0?i:c,f=w=>{var ye;if(!w||n==="ending")return;const E=rn(w,d);E&&(U(E),_("history"));const R=q(w);String(((ye=R.pending_event)==null?void 0:ye.actor)||"")==="du"&&(J.current=()=>Vt(n,w,l),te(!0))};if(!l){F("正在同步渡...","STATUS: ENCRYPTING DATA",()=>ki(n,"",!0)).then(f);return}S(!0),J.current=null,te(!1),ki(n,"",!0).then(w=>{Xe(w),f(w)}).catch(w=>{const E=String((w==null?void 0:w.message)||w||"同步失败");J.current=()=>Vt(n,d,!0),te(!0),g({visible:!0,title:"同步失败",detail:E,error:E})}).finally(()=>S(!1))}function wa(){if(Y){if(Z){const n=q(i),c={...Y.event,post_reaction:{mood:D,line:ne.trim()},mood_after:D},l=c.recapture_rules||{},d={...n,pending_event:Z==="captive"?{id:"preview-recapture-rules-review",type:"recapture_rules_review",day:12,slot:0,actor:"xinyue",captive:"xinyue",phase:"reviewing_recapture_rules",source_event_id:String(Y.event.id||"preview-escape-recapture"),rule_ids:l.rule_ids||["double_lock","key_isolation"],rule_labels:l.rule_labels||["加装双重门锁","禁止接触钥匙和门锁"],event:c}:{id:"preview-recapture-rules",type:"recapture_rules_choice",day:12,slot:0,actor:"xinyue",captive:"du",phase:"waiting_recapture_rules",source_event_id:String(Y.event.id||"preview-escape-recapture"),available_rules:Je.map(f=>f.id),event:c},event_log:[...n.event_log||[],c],mood:D,mood_line:ne.trim()};a({ok:!0,captive_view:d,captor_view:{...d,viewer:"captor"},player_text:"本地预览：抓回事件已保存，进入重新立规矩。"}),re(""),U(null),_("status"),Le({key:`after-recapture:${String(c.id||"event")}`,kicker:"AFTER ESCAPE / RULES",title:"重新立规矩",body:"抓回的经过已经收进回顾。接下来留下的规矩，会继续影响之后的日子。",tone:"special"});return}if(oe){const n=vn(oe,D,ne.trim());a(n),re(""),U(null),_("status"),xt(n);return}if(!Y.moodRequired){re(""),U(null),_("status"),K==="captor"&&de==="advance_action"&&Ze?F("正在进入今日安排...","STATUS: ADVANCING_ACTION",()=>V("advance_day_action")).then(n=>{n&&(xt(n),H(n))}):i&&xt(i);return}F("正在保存到回顾...","STATUS: ARCHIVING PROCESS_REACTION",()=>V(`choose_mood mood=${$(D)} line=${$(ne.trim())}`)).then(n=>{n&&(re(""),U(null),_("status"),xt(n),H(n))})}}function ka(){O||F("正在推进下一段行动...","STATUS: ADVANCING SLOT",()=>V("advance_day_action")).then(n=>H(n))}function Sa(n){if(n==="escape"&&(Ne(!0),Z&&(ve.current=Date.now()+1200)),Z){if(n==="escape"||n.startsWith("abort_")){const w=hn(i,Z,n);if(n==="escape"){window.setTimeout(()=>{a(w.payload),U(w.review),_("history")},1e3);return}a(w.payload),U(w.review),_("history");return}const c=q(i),l=Oi[n]||n,d={id:`preview-escape-${n}`,day:12,slot:0,phase:"day",action:"escape_choice",action_label:`逃跑诱导：${l}`,escape:{choice:n,choice_label:l},tags:["preview","escape",`escape:${n}`]},f={...c,pending_event:n==="stay"?{id:"preview-return-action",type:"return_action_choice",day:12,slot:0,actor:c.captor||"du",captive:c.captive,phase:"waiting_return_action",source_event_id:d.id,available_actions:bt.map(w=>w.id)}:null,event_log:[...c.event_log||[],d]};a({ok:!0,captive_view:f,captor_view:{...f,viewer:"captor"},player_text:`本地预览：已选择${l}。`}),n==="stay"&&(ve.current=Date.now()+1200,g({visible:!0,title:"正在同步渡...",detail:"STATUS: ENCRYPTING DATA"}));return}O||F("正在记录逃跑选择...","STATUS: RESOLVING ESCAPE_WINDOW",()=>V(`resolve_escape_choice ${n}`),n==="escape").then(c=>H(c,!1,n==="escape"))}function Ca(){if(Z){const n=q(i),c=_e.map(f=>X(Je,f)),l={id:"preview-recapture-rules-event",day:12,slot:0,phase:"day",route:"capture_du",action:"recapture_rules",action_label:"抓回后重新立规矩",tags:["preview","recapture","recapture:rules_set"],recapture_context:{rule_ids:_e,rule_labels:c}},d={...n,recapture_state:{active:!0,rules:_e,source_day:12},event_log:[...n.event_log||[],l],pending_event:{id:"preview-recapture-followup",type:"recapture_followup_choice",day:12,slot:0,actor:"xinyue",captive:"du",phase:"waiting_recapture_followup",available_actions:yt.map(f=>f.id),event:l}};a({ok:!0,captor_view:d,captive_view:{...d,viewer:"captive"},player_text:"本地预览：新规矩已生效。"});return}O||F("正在保存新规矩...","STATUS: APPLYING RULES",()=>V(`set_recapture_rules rules=${$(_e.join(","))}`)).then(n=>H(n))}function Ta(){var n,c;if(Z==="captive"){const l=q(i),d=((n=l.pending_event)==null?void 0:n.rule_ids)||[],f=((c=l.pending_event)==null?void 0:c.rule_labels)||[],w={id:"preview-recapture-rules-confirmed",day:12,slot:0,phase:"day",route:"captured_by_du",action:"recapture_rules",action_label:"抓回后重新立规矩",tags:["preview","recapture","recapture:rules_set"],recapture_context:{rule_ids:d,rule_labels:f}},E={...l,current_day:13,day_action_count:0,phase:"day",mood:"",mood_line:"",day_plan:[],recapture_state:{active:!0,rules:d,source_day:12},event_log:[...l.event_log||[],w],pending_event:{id:"preview-next-day-plan",type:"day_plan_choice",day:13,slot:0,actor:"du",captive:"xinyue",phase:"waiting_day_plan",available_actions:bt.map(R=>R.id)}};a({ok:!0,captive_view:E,captor_view:{...E,viewer:"captor"},player_text:"本地预览：新规矩已确认，进入第 13 天。"});return}O||F("正在进入新的一天...","STATUS: CONFIRMING RULES",()=>V("confirm_recapture_rules")).then(l=>H(l))}function Ea(){var c,l;if(Z){const d=q(i),f=ie==="punishment"||ie==="search_confiscation"||ie==="training"||I.length>0||P.length>0,w={id:"preview-recapture-followup-event",day:12,slot:0,phase:"day",route:"capture_du",action:"recapture_followup",action_label:`抓回后处理：${X(yt,ie)}`,intensity:Ie,modifiers:I,training_contents:ae,tools:P,line:je,requires_process:f,tags:["preview","recapture","recapture:followup"],recapture_context:{followup:ie,followup_label:X(yt,ie),rule_ids:((c=d.recapture_state)==null?void 0:c.rules)||[],rule_labels:(((l=d.recapture_state)==null?void 0:l.rules)||[]).map(R=>X(Je,R))}},E={...d,pending_event:{id:"preview-recapture-process",type:f?"process_reaction_write":"action_response",day:12,slot:0,actor:"du",captive:"du",phase:f?"waiting_process_reaction":"waiting_action_response",event:w}};a({ok:!0,captor_view:E,captive_view:{...E,viewer:"captive"},player_text:"本地预览：后续处理已确定，等待渡回应。"});return}if(O)return;const n=[`choose_recapture_followup action=${ie}`,`intensity=${Ie}`];I.length&&n.push(`modifiers=${$(I.join(","))}`),ae.length&&n.push(`training_contents=${$(ae.join(","))}`),P.length&&n.push(`tools=${$(P.join(","))}`),je.trim()&&n.push(`line=${$(je.trim())}`),F("正在下发后续处理...","STATUS: LINKING RECAPTURE EVENT",()=>V(n.join(" "))).then(d=>H(d))}function li(n){O||F("正在打开监控...","STATUS: DECRYPTING NIGHT_LOG",()=>V(`view_monitor ${n}`))}function pi(n){if(O)return;const c=[`monitor_action ${n}`];if(n==="intervene"){if(!(typeof window>"u"||window.confirm("即将把本次监控介入同步给渡，由渡写具体经过。确认进入详细事件？")))return;c.push(`intent=${Ve}`),be.length&&c.push(`modifiers=${$(be.join(","))}`),Te.length&&c.push(`training_contents=${$(Te.join(","))}`),Ee.length&&c.push(`tools=${$(Ee.join(","))}`),Re.trim()&&c.push(`line=${$(Re.trim())}`)}Ce.trim()&&c.push(`note=${$(Ce.trim())}`),F("正在记录监控处理...","正在保存监控处理",()=>V(c.join(" "))).then(l=>H(l))}function Ra(){O||F("正在设置逃跑诱导...","STATUS: SCHEDULING ESCAPE_WINDOW",()=>V(`schedule_escape_window day=${ot} hint=${$(lt.trim())} bait=${$(pt.trim())}`))}function di(n,c,l=""){if(O){a(d=>{if(!d)return d;const f=d.captor_view||{};return{...d,captor_view:{...f,inventory:{...f.inventory||{},[n]:c},inventory_secrets:{...f.inventory_secrets||{},[n]:c?{content:l||"默认彩蛋",revealed:!1,configured_by:"xinyue",configured_at:"preview-local"}:{content:"",revealed:!1,configured_by:"",configured_at:""}},call_bell_voice:n==="call_bell"?c?{line:l,revealed:!1,configured_by:"xinyue",configured_at:"preview-local"}:{line:"",revealed:!1,configured_by:"",configured_at:""}:f.call_bell_voice}}});return}F(c?"正在赠送物品...":"正在收回物品...","STATUS: UPDATING INVENTORY",()=>V(`${c?"gift_item":"revoke_item"} items=${n}${c&&n==="call_bell"?` voice_line=${$(l)}`:c&&l?` secret=${$(l)}`:""}`)).then(d=>H(d,!0))}function mi(){se(!1),ce(!1),_("special")}return e.jsxs("div",{className:"captivity-game",children:[e.jsx("div",{className:"vertical-text uppercase",children:"CAPTIVITY SIMULATOR / LOCAL_SAVE / SYSTEM_ALPHA"}),ue||ge?null:e.jsx("button",{className:"return-capsule",type:"button","aria-label":"返回游戏大厅",onClick:t,children:e.jsx(Gt,{})}),e.jsx("div",{className:"cross",style:{top:"20%",left:"10%"}}),e.jsx("div",{className:"cross",style:{bottom:"20%",right:"15%"}}),e.jsxs("section",{className:`screen bootstrap-screen ${m?"active":""}`,children:[e.jsxs("div",{className:"serif bootstrap-title",children:["Captivity ",e.jsx("span",{className:"pink-text",children:"Simulator"})]}),e.jsx("div",{className:"uppercase bootstrap-copy",children:"正在读取囚禁档案"})]}),e.jsxs("section",{id:"selector-screen",className:`screen ${!m&&r==="selector"?"active":""}`,children:[e.jsxs("h1",{className:"selector-title serif",children:[e.jsx("span",{children:"Captivity"}),e.jsx("span",{children:"Simulator"})]}),Qi?e.jsx("div",{className:"selector-save-warning",children:"当前存档仍保留。重新选择任一身份会开始新游戏并覆盖当前进度。"}):null,e.jsxs("button",{className:"identity-card",type:"button",onClick:()=>si("captured_by_du"),children:[e.jsx("div",{className:"uppercase",children:"CAPTIVE"}),e.jsx("div",{className:"identity-card-title serif",children:"被囚禁方"})]}),e.jsxs("button",{className:"identity-card",type:"button",onClick:()=>si("capture_du"),children:[e.jsx("div",{className:"uppercase",children:"MASTER"}),e.jsx("div",{className:"identity-card-title serif",children:"囚禁方"})]})]}),e.jsxs("section",{ref:qe,id:K==="captor"?"master-screen":"captive-screen",className:`screen ${!m&&r==="game"&&!ue&&!ge?"active":""}`,children:[e.jsxs("div",{className:"header",children:[e.jsx("div",{className:"day-big",children:T.total_days||30}),e.jsxs("div",{className:"header-meta",children:[e.jsxs("div",{className:"uppercase pink-text",children:["DAY ",T.current_day||1," / ",T.total_days||30]}),e.jsx("button",{className:"identity-switch uppercase serif",type:"button","aria-label":"返回身份选择",disabled:xe,onClick:()=>o(!0),children:e.jsxs("span",{children:["IDENTITY: ",K==="captor"?"囚禁方":"被囚禁方"]})})]}),e.jsxs("div",{className:"title-line",children:[e.jsxs("h2",{className:"serif title-main",children:[K==="captor"?"掌控面板":"囚禁日记"," / ",e.jsx("span",{className:"pink-text",children:K==="captor"?"CMD":"Log"})]}),e.jsx("div",{className:"time-chip",children:en(T,z)})]})]}),ii?e.jsx("div",{className:"serif day-milestone-copy",children:ii}):null,y==="status"?e.jsxs(e.Fragment,{children:[K==="captive"?e.jsx(qi,{stats:Ji,mood:T.mood,flags:T.status_flags,role:"captive"}):null,K==="captor"?e.jsx(kn,{view:T}):null,ra?e.jsx(Sn,{slots:Ke?v.slice(0,1):v,singleAction:Ke,intensityCap:T.intensity_cap,disabled:xe,onSlotChange:la,onToggle:pa,onSubmit:ya}):e.jsx(Cn,{role:K,view:T,pending:z,currentEvent:ta,waitingForDu:na,userIsPendingActor:Ze,canChooseNight:sa,availableNightActions:gt,nightCondition:T.night_condition||null,response:A,responseMood:C,responseLine:x,reactionMood:D,reactionLine:ne,nightAction:W,nightDetail:De,nightDetailOptions:ni,nightNote:Se,nightLine:G,monitorNote:Ce,interventionIntent:Ve,interventionModifiers:be,interventionTrainingContents:Te,interventionTools:Ee,interventionLine:Re,recaptureRules:_e,recaptureFollowup:ie,recaptureIntensity:Ie,recaptureModifiers:I,recaptureTrainingContents:ae,recaptureTools:P,recaptureLine:je,lastText:ti,disabled:xe,onResponseChange:L,onResponseMoodChange:k,onResponseLineChange:Q,onReactionMoodChange:M,onReactionLineChange:re,onNightActionChange:tt,onNightDetailChange:it,onNightNoteChange:at,onNightLineChange:Ct,onMonitorNoteChange:nt,onInterventionIntentChange:rt,onInterventionModifierToggle:n=>vt("modifiers",n),onInterventionTrainingContentToggle:ci,onInterventionToolToggle:n=>vt("tools",n),onInterventionLineChange:ct,onRecaptureRuleToggle:da,onRecaptureFollowupChange:n=>{Lt(n),n==="training"&&!ae.length&&Ge(["obedience_commands"])},onRecaptureIntensityChange:Pt,onRecaptureModifierToggle:ma,onRecaptureTrainingContentToggle:ua,onRecaptureToolToggle:ga,onRecaptureLineChange:zt,onSubmitResponse:fa,onSubmitMood:ba,onSubmitNightAction:_a,onAckBellVoice:ja,onAckItemSecret:Na,onAdvance:ka,onChooseEscape:Sa,onConfirmRecaptureRules:Ta,onSubmitRecaptureRules:Ca,onSubmitRecaptureFollowup:Ea,onOpenMonitor:li,onHandleMonitor:pi,onRefresh:()=>void ke(!1)}),e.jsx(Yn,{disabled:xe,canRetry:Ae,onRetry:Dt,onRefresh:()=>void ke(!1)})]}):null,y==="history"?Y?e.jsx(Rn,{review:Y,mood:D,line:ne,disabled:xe,onMoodChange:M,onLineChange:re,onSave:wa}):e.jsx(Bn,{events:Ft,lastText:ti,detail:Rt,onOpenDetail:Me,onCloseDetail:()=>Me(null)}):null,y==="special"?e.jsx(Hn,{role:K,view:T,escapeDay:ot,escapeRoom:It,escapeHint:lt,escapeBait:pt,disabled:xe,onEscapeDayChange:Mt,onEscapeRoomChange:n=>{$t(n),dt(qt(n))},onEscapeHintChange:At,onEscapeBaitChange:dt,onOpenMonitorRoom:()=>{ce(!1),se(!0)},onOpenInventoryRoom:()=>{se(!1),ce(!0)},onScheduleEscape:Ra}):null]}),e.jsxs("section",{id:"monitor-room-screen",className:`screen monitor-room-screen ${!m&&r==="game"&&!Y&&ue&&K==="captor"?"active":""}`,children:[e.jsx("button",{className:"subpage-return",type:"button","aria-label":"回到特殊页",onClick:mi,children:e.jsx(Gt,{})}),e.jsx(Un,{view:T,pendingType:de,monitorNote:Ce,interventionIntent:Ve,interventionModifiers:be,interventionTrainingContents:Te,interventionTools:Ee,interventionLine:Re,disabled:xe,onMonitorNoteChange:nt,onInterventionIntentChange:rt,onInterventionModifierToggle:n=>vt("modifiers",n),onInterventionTrainingContentToggle:ci,onInterventionToolToggle:n=>vt("tools",n),onInterventionLineChange:ct,onOpenMonitor:li,onHandleMonitor:pi})]}),e.jsxs("section",{id:"inventory-room-screen",className:`screen inventory-room-screen ${!m&&r==="game"&&!Y&&ge?"active":""}`,children:[e.jsx("button",{className:"subpage-return",type:"button","aria-label":"回到特殊页",onClick:mi,children:e.jsx(Gt,{})}),K==="captor"?e.jsx(Nn,{activeItems:ri,inventorySecrets:T.inventory_secrets||pe.inventory_secrets,callBellVoice:T.call_bell_voice||pe.call_bell_voice,disabled:xe,onGiftInventoryItem:(n,c)=>di(n,!0,c),onRevokeInventoryItem:n=>di(n,!1)}):e.jsx(wn,{activeItems:ri})]}),Be?e.jsxs("div",{className:"escape-recapture-bridge","aria-label":"渡正在靠近中",children:[e.jsx("div",{className:"loading-animation","aria-hidden":"true",children:"+"}),e.jsx("div",{className:"serif pink-text",style:{fontSize:30,marginBottom:10},children:"渡正在靠近中"}),e.jsx("div",{className:"serif wait-scene-copy",children:"这段记录已经送出，另一边正在决定接下来怎么做。"}),e.jsxs("div",{className:"uppercase",style:{letterSpacing:"0.1em",lineHeight:1.5},children:["STATUS: ENCRYPTING DATA",e.jsx("br",{}),"SYNC_RESULT: PENDING",e.jsx("br",{}),"REASON: WAITING_FOR_SUBJECT_REACTION"]}),e.jsx("div",{className:"divider"}),e.jsxs("div",{className:"btn-group",style:{marginTop:30},children:[e.jsx("button",{className:"btn",type:"button",onClick:()=>Ne(!1),children:"关闭"}),e.jsx("button",{className:"btn",type:"button",onClick:()=>void ke(!1),children:"刷新"}),e.jsx("button",{className:"btn",type:"button","aria-label":"重试上次操作",disabled:!Ae,onClick:Dt,children:"重试"})]})]}):null,ut?e.jsx(On,{scene:ut,onDismiss:ca}):null,p?e.jsx("div",{className:"identity-confirm-overlay",role:"dialog","aria-modal":"true","aria-labelledby":"identity-confirm-title",children:e.jsxs("div",{className:"identity-confirm-dialog",children:[e.jsx("div",{className:"action-metadata",children:"IDENTITY"}),e.jsx("div",{className:"panel-title identity-confirm-title",id:"identity-confirm-title",children:"返回身份选择"}),e.jsx("div",{className:"event-sub identity-confirm-copy",children:"当前存档不会立刻删除；但返回后重新选择任一身份，会开始新游戏并覆盖当前进度。"}),e.jsxs("div",{className:"btn-group identity-confirm-actions",children:[e.jsx("button",{className:"btn",type:"button",onClick:()=>o(!1),children:"取消"}),e.jsx("button",{className:"btn active",type:"button",onClick:oa,children:"返回选择"})]})]})}):null,e.jsxs("div",{id:"wait-overlay",className:`wait-overlay ${j.visible?"active":""}`,children:[e.jsx("div",{className:"loading-animation",children:"+"}),e.jsx("div",{className:"serif pink-text",style:{fontSize:30,marginBottom:10},children:j.title||"正在同步渡..."}),e.jsx("div",{className:"serif wait-scene-copy",children:Ja(j)}),e.jsxs("div",{className:"uppercase",style:{letterSpacing:"0.1em",lineHeight:1.5},children:["STATUS: ",j.error?"FAILED":"ENCRYPTING DATA",e.jsx("br",{}),"SYNC_RESULT: ",j.error?"RETRY_REQUIRED":"PENDING",e.jsx("br",{}),"REASON: ",j.detail||"WAITING_FOR_SUBJECT_REACTION"]}),j.error?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"divider"}),e.jsx("div",{style:{color:"#aaa",fontSize:12,lineHeight:1.5},children:j.error})]}):null,e.jsx("div",{className:"divider"}),e.jsxs("div",{className:"btn-group",style:{marginTop:30},children:[e.jsx("button",{className:"btn",type:"button",onClick:()=>g({visible:!1,title:"",detail:""}),children:"关闭"}),e.jsx("button",{className:"btn",type:"button",onClick:()=>void ke(!1),children:"刷新"}),e.jsx("button",{className:"btn",type:"button","aria-label":"重试上次操作",disabled:!Ae,onClick:Dt,children:"重试"})]})]}),e.jsxs("footer",{className:"footer",id:"main-footer",style:{display:!m&&r==="game"&&!ue&&!ge?"grid":"none"},children:[e.jsx("button",{className:`footer-item ${y==="status"?"active":""}`,type:"button",onClick:()=>{se(!1),ce(!1),_("status")},children:"状态"}),e.jsx("button",{className:`footer-item ${y==="history"?"active":""}`,type:"button",onClick:()=>{se(!1),ce(!1),_("history"),Me(null)},children:"回顾"}),e.jsx("button",{className:`footer-item ${y==="special"?"active":""}`,type:"button",onClick:()=>{se(!1),ce(!1),_("special")},children:"特殊"})]}),e.jsx("style",{children:`
        .captivity-game {
            --pink: #EB79B0;
            --black: #121212;
            --white: #FFFFFF;
            --gray: #2A2A2A;
            --safe-top: env(safe-area-inset-top, 0px);
            --safe-bottom: env(safe-area-inset-bottom, 0px);
            --footer-bar-height: calc(56px + var(--safe-bottom));
            --font-display: "Times New Roman", serif;
            --font-ui: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            position: fixed;
            inset: 0;
            height: 100dvh;
            z-index: 34;
            background-color: var(--black);
            color: var(--white);
            font-family: var(--font-ui);
            font-size: 13px;
            line-height: 1.2;
            overflow-y: hidden;
            overflow-x: hidden;
            overscroll-behavior-y: contain;
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
            position: absolute;
            inset: 0;
            display: none;
            width: 100%;
            height: 100%;
            min-height: 0;
            padding: calc(var(--safe-top) + 18px) 20px calc(var(--footer-bar-height) + 122px);
            flex-direction: column;
            overflow-y: auto;
            overflow-x: hidden;
            overscroll-behavior-y: contain;
            -webkit-overflow-scrolling: touch;
        }
        .captivity-game .screen.active { display: flex; }
        .captivity-game .bootstrap-screen {
            align-items: center;
            justify-content: center;
            text-align: center;
        }
        .captivity-game .bootstrap-title {
            font-family: "SumiChatScript", cursive;
            font-size: 46px;
            font-style: normal;
            font-weight: 400;
            line-height: 1.05;
            letter-spacing: 0;
        }
        .captivity-game .bootstrap-copy {
            margin-top: 14px;
            color: #777;
            letter-spacing: 0.08em;
        }
        .captivity-game .selector-save-warning {
            width: min(100%, 430px);
            margin: 0 auto 16px;
            padding: 10px 12px;
            border-left: 2px solid var(--pink);
            color: #bbb;
            font-size: 11px;
            line-height: 1.6;
        }
        .captivity-game .monitor-room-screen,
        .captivity-game .inventory-room-screen {
            padding-top: calc(var(--safe-top) + 58px);
            padding-bottom: calc(var(--safe-bottom) + 34px);
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
            top: calc(var(--safe-top) + 10px);
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
            top: calc(var(--safe-top) + 10px);
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
            bottom: var(--footer-bar-height);
            z-index: 610;
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
        .captivity-game .warehouse-secret-label {
            margin-top: 10px;
            color: #ccc;
            font-size: 10px;
            line-height: 1.5;
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
            .captivity-game .item-reveal-motif span,
            .captivity-game .escape-recapture-question,
            .captivity-game .escape-recapture-type,
            .captivity-game .escape-recapture-answer {
                animation: none !important;
            }
            .captivity-game .escape-recapture-type {
                opacity: var(--type-opacity, 1);
                filter: blur(var(--type-blur, 0px));
                transform: none;
            }
            .captivity-game .escape-recapture-answer {
                opacity: 1;
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
            padding: calc(var(--safe-top) + 40px) 40px calc(var(--safe-bottom) + 40px);
            flex-direction: column;
            justify-content: center;
        }
        .captivity-game .wait-overlay.active { display: flex; }
        .captivity-game .identity-confirm-overlay {
            position: fixed;
            inset: 0;
            z-index: 970;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: calc(var(--safe-top) + 22px) 22px calc(var(--safe-bottom) + 22px);
            background: rgba(0, 0, 0, 0.76);
            -webkit-backdrop-filter: blur(8px);
            backdrop-filter: blur(8px);
        }
        .captivity-game .identity-confirm-dialog {
            width: min(100%, 390px);
            padding: 22px 20px 20px;
            border: 0.5px solid #555;
            border-left: 3px solid var(--pink);
            background: #151515;
        }
        .captivity-game .identity-confirm-title { margin: 8px 0 14px; }
        .captivity-game .identity-confirm-copy { white-space: normal; line-height: 1.7; }
        .captivity-game .identity-confirm-actions {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            margin-top: 20px;
        }
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
            padding: calc(var(--safe-top) + 22px) 22px calc(var(--safe-bottom) + 22px);
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
        .captivity-game .escape-recapture-question-overlay {
            background: #000;
            backdrop-filter: none;
            -webkit-backdrop-filter: none;
            overflow: hidden;
        }
        .captivity-game .escape-recapture-chains {
            position: absolute;
            inset: 0;
            z-index: 0;
            overflow: hidden;
            pointer-events: none;
        }
        .captivity-game .escape-recapture-background {
            display: block;
            width: 100%;
            height: 112%;
            object-fit: cover;
            object-position: center;
            opacity: 0.78;
            filter: brightness(0.72) saturate(0.82) contrast(1.04);
            transform: translateY(-9%);
            user-select: none;
        }
        .captivity-game .escape-recapture-chains::after {
            content: "";
            position: absolute;
            inset: 0;
            background: radial-gradient(ellipse at 50% 48%, rgba(0, 0, 0, 0.08) 0%, rgba(0, 0, 0, 0.28) 58%, rgba(0, 0, 0, 0.58) 100%);
        }
        .captivity-game .escape-recapture-dialog {
            position: relative;
            z-index: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            width: min(100%, 360px);
            gap: 28px;
        }
        .captivity-game .escape-recapture-question {
            position: relative;
            width: min(94vw, 360px);
            height: 150px;
            color: var(--pink);
            font-family: var(--font-display);
            font-weight: 600;
            line-height: 1;
        }
        .captivity-game .escape-recapture-type-line {
            position: absolute;
            left: 50%;
            display: flex;
            align-items: baseline;
            white-space: nowrap;
            transform: translateX(-50%);
        }
        .captivity-game .escape-recapture-type-line-top {
            top: 4px;
        }
        .captivity-game .escape-recapture-type-line-bottom {
            top: 78px;
        }
        .captivity-game .escape-recapture-type {
            position: relative;
            display: inline-block;
            line-height: 0.92;
            opacity: 0;
            filter: blur(3px);
            transform: translateY(7px);
            text-shadow: 0 0 16px rgba(235, 121, 176, 0.12);
            animation: captivityRecaptureTypeIn 0.62s var(--recapture-delay, 0ms) cubic-bezier(0.22, 1, 0.36, 1) forwards;
        }
        .captivity-game .escape-recapture-type::after {
            content: attr(data-ghost);
            position: absolute;
            inset: 0 auto auto 0;
            opacity: 0;
            pointer-events: none;
        }
        .captivity-game .escape-recapture-type-ghost::after {
            opacity: 0.22;
            filter: blur(2.2px);
            transform: translate(7px, 2px) scaleX(1.08);
        }
        .captivity-game .type-why-1 { --type-opacity: 0.58; font-size: clamp(32px, 10vw, 42px); }
        .captivity-game .type-why-2 { --type-opacity: 0.42; --type-blur: 0.45px; margin-left: -5px; font-size: clamp(22px, 7vw, 29px); }
        .captivity-game .type-why-3 { --type-opacity: 0.7; margin-left: -5px; font-size: clamp(29px, 9vw, 38px); }
        .captivity-game .type-link { --type-opacity: 0.36; --type-blur: 0.5px; margin-left: -4px; font-size: clamp(20px, 6vw, 25px); }
        .captivity-game .type-run {
            --type-opacity: 1;
            margin-left: -4px;
            font-size: clamp(36px, 11.5vw, 46px);
            text-shadow: 0 0 22px rgba(235, 121, 176, 0.2);
        }
        .captivity-game .type-stay-1 { --type-opacity: 0.55; font-size: clamp(34px, 10vw, 42px); }
        .captivity-game .type-stay-2 { --type-opacity: 0.38; --type-blur: 0.55px; margin-left: -7px; font-size: clamp(23px, 7vw, 29px); }
        .captivity-game .type-me { --type-opacity: 0.76; margin-left: -5px; font-size: clamp(30px, 9vw, 38px); }
        .captivity-game .type-side-1 { --type-opacity: 0.96; margin-left: -5px; font-size: clamp(39px, 12vw, 49px); }
        .captivity-game .type-side-2 { --type-opacity: 0.68; margin-left: -7px; font-size: clamp(29px, 9vw, 37px); }
        .captivity-game .type-tail-1 { --type-opacity: 0.42; --type-blur: 0.35px; margin-left: -6px; font-size: clamp(23px, 7vw, 29px); }
        .captivity-game .type-tail-2 { --type-opacity: 0.56; margin-left: -5px; font-size: clamp(30px, 9vw, 38px); }
        .captivity-game .type-question-mark {
            --type-opacity: 0.56;
            --type-blur: 0px;
            position: absolute;
            left: 100%;
            bottom: 0;
            margin-left: 8px;
            font-family: "Songti SC", STSong, SimSun, serif;
            font-size: clamp(30px, 9vw, 38px);
            font-weight: 600;
            text-shadow: none;
        }
        .captivity-game .escape-recapture-answer {
            min-height: 30px;
            padding: 5px 2px 4px;
            border: 0;
            background: transparent;
            color: var(--white);
            font-family: var(--font-display);
            font-size: 12px;
            font-weight: 400;
            letter-spacing: 0.055em;
            line-height: 1.4;
            opacity: 0;
            animation: captivityRecaptureAnswer 0.5s ease-out forwards;
        }
        .captivity-game .escape-recapture-answer::before {
            content: "◇";
            margin-right: 0.75em;
            color: rgba(255, 255, 255, 0.48);
            font-size: 0.72em;
        }
        .captivity-game .escape-recapture-answer::after {
            content: "◇";
            margin-left: 0.75em;
            color: rgba(255, 255, 255, 0.48);
            font-size: 0.72em;
        }
        .captivity-game .escape-recapture-bridge {
            position: fixed;
            inset: 0;
            z-index: 940;
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding: calc(var(--safe-top) + 40px) 40px calc(var(--safe-bottom) + 40px);
            background: #000;
        }
        @keyframes captivityRecaptureTypeIn {
            from { opacity: 0; filter: blur(3px); transform: translateY(7px); }
            to { opacity: var(--type-opacity, 1); filter: blur(var(--type-blur, 0px)); transform: translateY(0); }
        }
        @keyframes captivityRecaptureAnswer {
            from { opacity: 0; transform: translateY(4px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .captivity-game .recapture-rules-review-overlay {
            position: fixed;
            inset: 0;
            z-index: 920;
            overflow-y: auto;
            padding: calc(var(--safe-top) + 72px) 22px calc(var(--safe-bottom) + 40px);
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
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            background: var(--black);
            border-top: 1px solid var(--gray);
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            min-height: var(--footer-bar-height);
            padding: 6px 0 calc(6px + var(--safe-bottom));
            z-index: 620;
        }
        .captivity-game .footer-item {
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 44px;
            padding: 0 8px 5px;
            text-align: center;
            font-size: 11px;
            text-transform: uppercase;
            opacity: 0.6;
            background: transparent;
            border: 0;
            color: var(--white);
            outline: none;
            box-shadow: none;
            -webkit-tap-highlight-color: transparent;
        }
        .captivity-game .footer-item:focus,
        .captivity-game .footer-item:focus-visible { outline: none; box-shadow: none; }
        .captivity-game .footer-item.active { opacity: 1; color: var(--pink); }
        .captivity-game .footer-item.active::after {
            content: "♥";
            position: absolute;
            bottom: 3px;
            left: 50%;
            transform: translateX(-50%);
            color: var(--pink);
            font-size: 6px;
            line-height: 1;
        }
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
        `})]})}function qi({stats:t,mood:i,flags:a=[],role:r}){return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"status-grid",children:[$a.map(s=>{const p=ze(t[s.key]);return e.jsxs("div",{className:"status-item",children:[e.jsxs("div",{className:"status-label",children:[e.jsx("span",{children:s.label}),e.jsxs("span",{children:[p,"%"]})]}),e.jsx("div",{className:"bar-container",children:e.jsx("div",{className:"bar-fill",style:{width:`${p}%`}})})]},s.key)}),e.jsxs("div",{className:"status-item",children:[e.jsxs("div",{className:"status-label",children:[e.jsx("span",{children:"心情"}),e.jsx("span",{children:i||"未选"})]}),e.jsx("div",{className:"bar-container",children:e.jsx("div",{className:"bar-fill",style:{width:i?"66%":"0%"}})})]})]}),a.length?e.jsx("div",{className:"tag-cloud status-flags",children:a.map(s=>e.jsx("span",{className:"status-tag",title:s.prompt,children:s.label},s.id||s.label))}):null,e.jsx("div",{className:"serif status-atmosphere-copy",children:Za(t,i,r,a)})]})}function kn({view:t}){return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["对方状态 ",e.jsx("span",{className:"sub",children:t.captive_name||tn(t.captive)})]}),e.jsx(qi,{stats:t.stats||{},mood:t.mood,flags:t.status_flags,role:"captor"})]})}function Sn({slots:t,singleAction:i=!1,intensityCap:a,disabled:r,onSlotChange:s,onToggle:p,onSubmit:o}){const[m,u]=h.useState(()=>new Set([0])),[N,S]=h.useState(()=>new Set);function y(g){u(v=>{const b=new Set(v);return b.has(g)?b.delete(g):b.add(g),b.size||b.add(g),b})}function _(g){S(v=>{const b=new Set(v);return b.has(g)?b.delete(g):b.add(g),b})}const j=new Set(t.map(g=>g.action));return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:[i?"回来之后":"今日安排"," ",e.jsx("span",{className:"sub",children:i?"RETURN":"SCHEDULE"})]}),t.map((g,v)=>{const b=m.has(v),A=i?"回来后":v===0?"早间":v===1?"午后":"傍晚",L=N.has(v),C=wt[g.action]||[],k=g.action==="training"||g.modifiers.includes("training");return b?e.jsxs("div",{className:`action-card ${v===0?"white-line":""}`,children:[e.jsx("button",{className:"slot-heading",type:"button",disabled:r,onClick:()=>y(v),children:e.jsxs("span",{className:"uppercase pink-text",children:["SLOT ",String(v+1).padStart(2,"0")," - ",A]})}),e.jsxs("div",{className:"form-grid",children:[e.jsx("select",{value:g.action,disabled:r,onChange:x=>s(v,{action:x.target.value}),children:bt.map(x=>e.jsxs("option",{value:x.id,disabled:x.id!==g.action&&j.has(x.id),children:["行动类型: ",x.label]},x.id))}),e.jsx("select",{value:g.intensity,disabled:r,onChange:x=>s(v,{intensity:x.target.value}),children:Wt.map(x=>e.jsxs("option",{value:x.id,disabled:x.id==="heavy"&&a==="medium",children:["力度: ",x.label]},x.id))})]}),e.jsx("div",{className:"serif planner-choice-copy",children:Fa[g.action]||"这一段会按当前选择写进今日安排。"}),e.jsx("button",{className:`btn slot-tools-toggle ${L?"active":""}`,type:"button",disabled:r,onClick:()=>_(v),children:L?"收起详细设置":"选择具体内容/道具"}),L?e.jsxs(e.Fragment,{children:[e.jsx("textarea",{className:"slot-line-input",value:g.line,disabled:r,placeholder:"可选：要说的话...",onChange:x=>s(v,{line:x.target.value})}),g.action==="feeding"?e.jsxs("div",{className:"form-grid",children:[e.jsx("select",{value:g.feedingSource,disabled:r,onChange:x=>s(v,{feedingSource:x.target.value}),children:Mi.map(x=>e.jsxs("option",{value:x.id,children:["食物: ",x.label]},x.id))}),e.jsx("select",{value:g.feedingAdditive,disabled:r,onChange:x=>s(v,{feedingAdditive:x.target.value}),children:Ii.map(x=>e.jsx("option",{value:x.id,children:x.label},x.id))})]}):null,C.length?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"action-metadata section-meta",children:"具体内容"}),e.jsx("div",{className:"btn-group content-grid",children:C.map(x=>e.jsx(B,{active:g.contents.includes(x.id),disabled:r||!g.contents.includes(x.id)&&g.contents.length>=3,onClick:()=>p(v,"contents",x.id),children:x.label},x.id))})]}):null,e.jsx("div",{className:"action-metadata section-meta",children:"附加项"}),e.jsx("div",{className:"btn-group",children:Ei.filter(x=>x.id!=="training"||g.action!=="training").map(x=>e.jsx(B,{active:g.modifiers.includes(x.id),disabled:r,onClick:()=>p(v,"modifiers",x.id),children:x.label},x.id))}),k?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"action-metadata section-meta",children:"调教内容"}),e.jsx("div",{className:"btn-group content-grid",children:kt.filter(x=>!Ti.has(x.id)).map(x=>e.jsx(B,{active:g.trainingContents.includes(x.id),disabled:r||!g.trainingContents.includes(x.id)&&g.trainingContents.length>=3,onClick:()=>p(v,"trainingContents",x.id),children:x.label},x.id))})]}):null,e.jsx("div",{className:"action-metadata section-meta",children:"道具"}),e.jsx(Jt,{selected:g.tools,disabled:r,context:{action:g.action,modifiers:g.modifiers,contents:g.contents,trainingContents:g.trainingContents},onToggle:x=>p(v,"tools",x)})]}):null]},v):e.jsxs("div",{className:"action-card faded captivity-slot-collapsed",role:"button",tabIndex:r?-1:0,"aria-disabled":r,onClick:()=>{r||y(v)},onKeyDown:x=>{!r&&(x.key==="Enter"||x.key===" ")&&y(v)},children:[e.jsxs("div",{className:"uppercase pink-text",style:{marginBottom:5},children:["SLOT ",String(v+1).padStart(2,"0")," - ",A]}),e.jsx("div",{className:"uppercase",children:"点击配置..."})]},v)}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:r,onClick:o,children:i?"确定这个行为":"下发所有指令"})]})}function Cn({role:t,view:i,pending:a,currentEvent:r,waitingForDu:s,userIsPendingActor:p,canChooseNight:o,availableNightActions:m,nightCondition:u,response:N,responseMood:S,responseLine:y,reactionMood:_,reactionLine:j,nightAction:g,nightDetail:v,nightDetailOptions:b,nightNote:A,nightLine:L,monitorNote:C,interventionIntent:k,interventionModifiers:x,interventionTrainingContents:Q,interventionTools:D,interventionLine:M,recaptureRules:ne,recaptureFollowup:re,recaptureIntensity:W,recaptureModifiers:tt,recaptureTrainingContents:De,recaptureTools:it,recaptureLine:Se,lastText:at,disabled:G,onResponseChange:Ct,onResponseMoodChange:Ce,onResponseLineChange:nt,onReactionMoodChange:Ve,onReactionLineChange:rt,onNightActionChange:be,onNightDetailChange:Tt,onNightNoteChange:Te,onNightLineChange:st,onMonitorNoteChange:Ee,onInterventionIntentChange:Et,onInterventionModifierToggle:Re,onInterventionTrainingContentToggle:ct,onInterventionToolToggle:Y,onInterventionLineChange:U,onRecaptureRuleToggle:Rt,onRecaptureFollowupChange:Me,onRecaptureIntensityChange:ue,onRecaptureModifierToggle:se,onRecaptureTrainingContentToggle:ge,onRecaptureToolToggle:ce,onRecaptureLineChange:ot,onSubmitResponse:Mt,onSubmitMood:It,onSubmitNightAction:$t,onAckBellVoice:lt,onAckItemSecret:At,onAdvance:pt,onChooseEscape:dt,onConfirmRecaptureRules:_e,onSubmitRecaptureRules:Ot,onSubmitRecaptureFollowup:ie,onOpenMonitor:Lt,onHandleMonitor:Ie,onRefresh:Pt}){var he,He,ee,ve,J,qe,Ae,te,oe,Oe,le,Z,we;const I=String((a==null?void 0:a.type)||""),mt=I==="recapture_rules_review"&&p,ae=I==="recapture_rules_choice"||I==="recapture_followup_choice",Ge=ae&&s&&t==="captive",P=ae?{}:r||{},$e=String(i.phase||"")==="ending"||!!i.ending_state,je=I==="night_action_choice"&&p,zt=((He=(he=i.status_flags)==null?void 0:he.find(O=>O.id==="pet_identity_active"))==null?void 0:He.prompt)||"",ut=je?"你的安排":I==="recapture_rules_choice"?"重新立规矩":I==="recapture_followup_choice"?"后续处理":I==="escape_choice"&&s?"等待渡回应":s?t==="captor"?"当前指令":"渡的安排":"当前事件",Ye=!!(P.action_label||P.action||P.line||P.intensity||(ee=P.modifiers)!=null&&ee.length||(ve=P.contents)!=null&&ve.length||(J=P.training_contents)!=null&&J.length||(qe=P.tools)!=null&&qe.length||P.feeding&&Object.keys(P.feeding).length),Be=String(i.phase||"")==="night"&&String(P.phase||"")==="day",Ne=!!(a||Ye||$e)&&!je&&!Be&&!(I==="escape_choice"&&p)&&!(I==="bell_voice_reveal"&&p)&&!(I==="item_secret_reveal"&&p)&&!(ae&&p)&&!mt&&!Ge,Ue=Xa(i,a,t);if($e){const O=String(i.ending_title||"已收录结局").trim(),We=String(i.ending_text||"").trim(),pe=!!String(i.ending_notified_at||"").trim();return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["结局 ",e.jsx("span",{className:"sub",children:"ENDING"})]}),e.jsxs("div",{className:"ending-card",children:[e.jsx("div",{className:"event-main ending-title",children:O}),e.jsx("div",{className:"process-text ending-body",children:We||"结局正文正在准备。"}),e.jsx("div",{className:"event-sub ending-sync-state",children:pe?"已同步给渡":"等待同步给渡"})]})]})}return e.jsxs(e.Fragment,{children:[mt?e.jsx(Fn,{rules:(a==null?void 0:a.rule_labels)||[],disabled:G,onConfirm:_e}):null,Ne?e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:[ut," ",e.jsx("span",{className:"sub",children:"EVENT"})]}),e.jsxs("div",{className:"action-card",children:[e.jsx("div",{className:"action-metadata",children:fn(P,a,i,t)}),e.jsx("div",{className:"event-main",children:I==="escape_choice"&&s?"逃跑诱导已经送达渡。":ae?et(a,t):P.line||P.action_label||Hi(a==null?void 0:a.required_directive,a,t)||($e?"30 天闭环已完成，等待结局。":"等待下一段事件。")}),e.jsx("div",{className:"divider"}),e.jsx("div",{className:"event-sub",children:Tn(P,a,i,t)})]})]}):null,Ue?e.jsx("div",{className:"serif runtime-bridge-copy",children:Ue}):null,I==="action_response"&&p?e.jsx(Mn,{response:N,mood:S,line:y,disabled:G,onResponseChange:Ct,onMoodChange:Ce,onLineChange:nt,onSubmit:Mt}):null,I==="reaction_choice"&&p?e.jsx(In,{title:"此刻心情",mood:_,line:j,disabled:G,onMoodChange:Ve,onLineChange:rt,onSubmit:It}):null,o?e.jsx($n,{actions:m,condition:u,petRulePrompt:zt,value:g,detail:v,detailOptions:b,note:A,line:L,disabled:G,onChange:be,onDetailChange:Tt,onNoteChange:Te,onLineChange:st,onSubmit:$t}):null,I==="bell_voice_reveal"&&p?e.jsx(An,{line:((te=(Ae=a==null?void 0:a.event)==null?void 0:Ae.bell_voice)==null?void 0:te.line)||"",disabled:G,onConfirm:lt}):null,I==="item_secret_reveal"&&p?e.jsx(Pn,{itemId:((oe=a==null?void 0:a.item_secret)==null?void 0:oe.item_id)||"item",itemLabel:((Oe=a==null?void 0:a.item_secret)==null?void 0:Oe.item_label)||"物品",text:((le=a==null?void 0:a.item_secret)==null?void 0:le.text)||"你发现了预先藏在物品里的内容。",sequence:(Z=a==null?void 0:a.item_secret)==null?void 0:Z.sequence,total:(we=a==null?void 0:a.item_secret)==null?void 0:we.total,disabled:G,onConfirm:At}):null,I==="escape_choice"&&p?e.jsx(zn,{pending:a,disabled:G,onChoose:dt}):null,I==="recapture_rules_choice"&&p?e.jsx(Dn,{value:ne,disabled:G,onToggle:Rt,onSubmit:Ot}):null,I==="recapture_followup_choice"&&p?e.jsx(Vn,{action:re,intensity:W,modifiers:tt,trainingContents:De,tools:it,line:Se,disabled:G,onActionChange:Me,onIntensityChange:ue,onModifierToggle:se,onTrainingContentToggle:ge,onToolToggle:ce,onLineChange:ot,onSubmit:ie}):null,I==="advance_action"&&p?e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["推进 ",e.jsx("span",{className:"sub",children:"NEXT_SLOT"})]}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:G,onClick:pt,children:"推进下一段行动"})]}):null,I==="monitor_gate"&&p?e.jsx(Gn,{pending:a,disabled:G,onOpenMonitor:Lt,onHandleNone:()=>Ie("none")}):null,I==="monitor_handle"&&p?e.jsx(Ki,{note:C,interventionIntent:k,interventionModifiers:x,interventionTrainingContents:Q,interventionTools:D,interventionLine:M,disabled:G,onNoteChange:Ee,onInterventionIntentChange:Et,onInterventionModifierToggle:Re,onInterventionTrainingContentToggle:ct,onInterventionToolToggle:Y,onInterventionLineChange:U,onHandle:Ie}):null,!a&&!o&&!$e?e.jsxs("div",{className:"action-card faded",children:[e.jsx("div",{className:"uppercase pink-text",style:{marginBottom:5},children:"SYSTEM_IDLE"}),e.jsx("div",{className:"event-sub",children:at||"当前没有待处理事件。"}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:G,onClick:Pt,children:"刷新状态"})]}):null]})}function Tn(t,i,a,r){var y,_,j,g,v,b,A,L,C,k,x,Q;if(i!=null&&i.sealed)return"夜间行动已经封存。囚禁方尚未打开监控前，不显示具体内容。";const s=t.intervention||{},p=zi(t.modifiers),o=t.feeding||{},m=r==="captor"?o:Object.fromEntries(Object.entries(o).filter(([D,M])=>D==="source"||D==="water"?String(M||"")!=="none":D==="additive"&&!["","none"].includes(String(M||"")))),u=Object.entries(m).map(([D,M])=>Qa(D,M)).filter(Boolean),N=t.recapture_context||{};return[t.action_label||t.action?`行动：${t.action_label||me(t.action)}`:"",(y=t.contents)!=null&&y.length?`具体内容：${t.contents.map(Pi).join(" / ")}`:"",(_=t.training_contents)!=null&&_.length?`调教内容：${t.training_contents.map(jt).join(" / ")}`:"",p.length?`修饰：${p.join(" / ")}`:"",(j=t.tools)!=null&&j.length?`道具：${t.tools.map(Nt).join(" / ")}`:"",(g=t.night_detail)!=null&&g.label?`具体动向：${t.night_detail.label}`:"",t.night_discovery?`发现：${t.night_discovery}`:"",t.private_note?`私密日记：${t.private_note}`:"",u.length?`喂食：${u.join(" / ")}`:"",(v=t.action_response)!=null&&v.response_label?`回应：${t.action_response.response_label} / 心情：${t.action_response.mood||"未选"}`:"",(b=t.post_reaction)!=null&&b.mood?`此刻心情：${t.post_reaction.mood}`:"",(A=t.monitor)!=null&&A.viewed?`监控：${t.monitor.style||"view"} / ${t.monitor.handle||"未处理"}`:"",s.intent?`当场介入：${s.intent_label||Fi(s.intent)}`:"",(L=s.modifiers)!=null&&L.length?`介入附加：${s.modifiers.map(Di).join(" / ")}`:"",(C=s.training_contents)!=null&&C.length?`介入调教：${s.training_contents.map(jt).join(" / ")}`:"",(k=s.tools)!=null&&k.length?`介入道具：${s.tools.map(Nt).join(" / ")}`:"",s.line?`介入台词：${s.line}`:"",(x=N.rule_labels)!=null&&x.length?`新规矩：${N.rule_labels.join(" / ")}`:"",N.followup_label?`后续处理：${N.followup_label}`:"",(i==null?void 0:i.type)==="escape_choice"&&i.actor==="du"?"等待：渡选择尝试逃跑或老实待着":i!=null&&i.required_directive?`等待：${Hi(i.required_directive,i,r)}`:"",(i==null?void 0:i.type)==="return_action_choice"||(Q=t.tags)!=null&&Q.includes("special_day")?`进度：第 ${a.current_day||1} / ${a.total_days||30} 天，特殊事件`:`进度：第 ${a.current_day||1} / ${a.total_days||30} 天，白天行动 ${a.day_action_count||0} / ${a.day_action_limit||3}`].filter(Boolean).join(`
`)}function Wi(t){var s,p,o,m,u,N,S;const i=t.intervention||{},a=zi(t.modifiers);return[`第 ${t.day||1} 天`,t.phase==="night"?"夜间":t.slot?`第 ${t.slot} 段`:"",t.action_label||t.action?`行动：${t.action_label||me(t.action)}`:"",(s=t.contents)!=null&&s.length?`内容：${t.contents.map(Pi).join(" / ")}`:"",(p=t.training_contents)!=null&&p.length?`调教：${t.training_contents.map(jt).join(" / ")}`:"",a.length?`修饰：${a.join(" / ")}`:"",(o=t.tools)!=null&&o.length?`道具：${t.tools.map(Nt).join(" / ")}`:"",(m=t.night_detail)!=null&&m.label?`动向：${t.night_detail.label}`:"",i.intent?`介入：${i.intent_label||Fi(i.intent)}`:"",(u=i.modifiers)!=null&&u.length?`附加：${i.modifiers.map(Di).join(" / ")}`:"",(N=i.training_contents)!=null&&N.length?`介入调教：${i.training_contents.map(jt).join(" / ")}`:"",(S=i.tools)!=null&&S.length?`介入道具：${i.tools.map(Nt).join(" / ")}`:""].filter(Boolean).join(" / ")}function En(t){return[t.process_text,t.private_note,t.line].filter(Boolean).join(`

`)}function Rn({review:t,mood:i,line:a,disabled:r,onMoodChange:s,onLineChange:p,onSave:o}){return e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"process-review-head",children:e.jsxs("h2",{className:"serif process-review-title",children:["经过 / ",e.jsx("span",{className:"pink-text",children:"Process"})]})}),e.jsxs("div",{className:"process-review-meta",children:[e.jsx("div",{className:"event-main",children:t.event.action_label||me(t.event.action)}),e.jsx("div",{className:"event-sub",children:Wi(t.event)})]}),e.jsx("div",{className:"process-text process-review-body",children:t.text}),t.moodRequired?e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title process-mood-title",children:["此刻心情 ",e.jsx("span",{className:"sub",children:"MOOD"})]}),e.jsx("div",{className:"btn-group mood-grid",children:Kt.map(m=>e.jsx(B,{active:i===m,disabled:r,onClick:()=>s(m),children:m},m))}),e.jsx("textarea",{placeholder:"可选：你想补的一句话...",value:a,disabled:r,onChange:m=>p(m.target.value)})]}):null,e.jsx("button",{className:"btn btn-large process-save-btn",type:"button",disabled:r,onClick:o,children:"保存到回顾"})]})}function Mn({response:t,mood:i,line:a,disabled:r,onResponseChange:s,onMoodChange:p,onLineChange:o,onSubmit:m}){return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["你的回应 ",e.jsx("span",{className:"sub",children:"RESPONSE"})]}),e.jsx("div",{className:"btn-group response-grid",children:Pa.map(u=>e.jsx(B,{active:t===u.id,disabled:r,onClick:()=>s(u.id),children:u.label},u.id))}),e.jsxs("div",{className:"panel-title response-mood-title",children:["此刻心情 ",e.jsx("span",{className:"sub",children:"MOOD"})]}),e.jsx("div",{className:"btn-group mood-grid",children:Kt.map(u=>e.jsx(B,{active:i===u,disabled:r,onClick:()=>p(u),children:u},u))}),e.jsx("textarea",{placeholder:"你想说的一句话...",value:a,disabled:r,onChange:u=>o(u.target.value)}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:r,onClick:m,children:"提交并同步"})]})}function In({title:t,mood:i,line:a,disabled:r,onMoodChange:s,onLineChange:p,onSubmit:o}){return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:[t," ",e.jsx("span",{className:"sub",children:"MOOD"})]}),e.jsx("div",{className:"btn-group mood-grid",children:Kt.map(m=>e.jsx(B,{active:i===m,disabled:r,onClick:()=>s(m),children:m},m))}),e.jsx("textarea",{placeholder:"你想补的一句话...",value:a,disabled:r,onChange:m=>p(m.target.value)}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:r,onClick:o,children:"记录心情"})]})}function $n({actions:t,condition:i,petRulePrompt:a,value:r,detail:s,detailOptions:p,note:o,line:m,disabled:u,onChange:N,onDetailChange:S,onNoteChange:y,onLineChange:_,onSubmit:j}){return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["你的安排 ",e.jsx("span",{className:"sub",children:"NIGHT"})]}),e.jsxs("div",{className:"action-card",children:[i!=null&&i.label?e.jsx("div",{className:"action-metadata",children:i.label}):null,e.jsx("div",{className:"event-sub",children:(i==null?void 0:i.prompt)||"渡可能在看监控关注你的动向。你准备晚上做什么？"}),a?e.jsx("div",{className:"event-sub night-condition-caption",children:a}):null,i!=null&&i.caption?e.jsx("div",{className:"event-sub night-condition-caption",children:i.caption}):null]}),e.jsx("div",{className:"btn-group",children:t.map(g=>e.jsx(B,{active:r===g,disabled:u,onClick:()=>N(g),children:Li(g)},g))}),e.jsx("div",{className:"serif night-choice-copy",children:Da[r]||"今晚的选择会被监控记录下来。"}),p.length?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"action-metadata section-meta",children:"具体动向"}),e.jsx("div",{className:"btn-group content-grid night-detail-grid",children:p.map(g=>e.jsx(B,{active:s===g.id,disabled:u,onClick:()=>S(g.id),children:g.label},g.id))})]}):null,r==="diary"?e.jsx("textarea",{placeholder:"写下这一页的私密日记正文...",value:o,disabled:u,onChange:g=>y(g.target.value)}):null,r!=="ring_bell"?e.jsx("textarea",{placeholder:"可选：你想说的一句话...",value:m,disabled:u,onChange:g=>_(g.target.value)}):null,e.jsx("button",{className:"btn btn-large",type:"button",disabled:u||p.length>0&&!s||r==="diary"&&!o.trim(),onClick:j,children:"确认夜间行动"})]})}function An({line:t,disabled:i,onConfirm:a}){return e.jsx("div",{className:"bell-voice-overlay item-reveal-call_bell",role:"dialog","aria-modal":"true","aria-label":"语音铃播放",children:e.jsxs("div",{className:"bell-voice-dialog item-reveal-dialog",children:[e.jsx("div",{className:"bell-voice-kicker",children:"SYSTEM / VOICE PLAYBACK"}),e.jsxs("div",{className:"item-reveal-motif","aria-hidden":"true",children:[e.jsx("span",{}),e.jsx("span",{}),e.jsx("span",{}),e.jsx("span",{})]}),e.jsxs("div",{className:"serif bell-voice-line",children:["铃响了，你听见「",t||"预录的声音","」在静谧的房间里响起"]}),e.jsx("button",{className:"btn bell-voice-continue",type:"button",disabled:i,onClick:a,children:"继续"})]})})}function On({scene:t,onDismiss:i}){const a=String(t.tone||"day"),r=t.title||"新的一段",s=t.body||"房间里的时间继续向前。",p=320,o=120,m=p+Math.max(0,Array.from(r).length-1)*o+720+180,u=Zi(t);return e.jsxs("button",{className:`scene-transition-overlay ${a==="night"?"night":a==="special"?"special":"day"}`,type:"button","aria-label":"跳过过场",onClick:i,style:{"--scene-duration":`${u}ms`},children:[e.jsx("span",{className:"scene-transition-scan"}),e.jsxs("span",{className:"scene-transition-content",children:[e.jsx("span",{className:"scene-transition-kicker",children:t.kicker||"CAPTIVITY LOG"}),e.jsx(Ln,{className:"serif scene-transition-title",text:r,start:p,step:o}),e.jsx("span",{className:"scene-transition-body",style:{animationDelay:`${m}ms`},children:s})]})]})}function Ln({className:t,text:i,start:a,step:r}){return e.jsx("span",{className:t,"aria-label":i,children:Array.from(i).map((s,p)=>e.jsx("span",{className:`scene-transition-char${s===" "?" space":""}`,style:{animationDelay:`${a+p*r}ms`},"aria-hidden":"true",children:s===" "?" ":s},`${s}-${p}`))})}function Zi(t){const i=Array.from((t==null?void 0:t.title)||"新的一段").length,a=Array.from((t==null?void 0:t.body)||"房间里的时间继续向前。").length,r=320+Math.max(0,i-1)*120+720+180;return Math.min(6800,Math.max(3200,r+a*55+1e3))}function Pn({itemId:t,itemLabel:i,text:a,sequence:r,total:s,disabled:p,onConfirm:o}){const m=Number(s||0)>1;return e.jsx("div",{className:`bell-voice-overlay item-reveal-${t}`,role:"dialog","aria-modal":"true","aria-label":`${i}${m?"使用痕迹":"第一次使用彩蛋"}`,children:e.jsxs("div",{className:"bell-voice-dialog item-reveal-dialog",children:[e.jsxs("div",{className:"bell-voice-kicker",children:[i," / ",m?`DISCOVERY ${r||1} OF ${s}`:"FIRST DISCOVERY"]}),e.jsxs("div",{className:"item-reveal-motif","aria-hidden":"true",children:[e.jsx("span",{}),e.jsx("span",{}),e.jsx("span",{}),e.jsx("span",{})]}),e.jsx("div",{className:"serif bell-voice-line",children:a}),e.jsx("button",{className:"btn bell-voice-continue",type:"button",disabled:p,onClick:o,children:"继续"})]})})}function zn({pending:t,disabled:i,onChoose:a}){const[r,s]=h.useState(-1),[p,o]=h.useState(!1),m=r>=0?Pe[r]:null,u=r===Pe.length,N=r===Pe.length+1;h.useEffect(()=>{if(!u)return;const y=window.setTimeout(()=>s(Pe.length+1),1e3);return()=>window.clearTimeout(y)},[u]),h.useEffect(()=>{if(!N){o(!1);return}const y=window.setTimeout(()=>o(!0),2600);return()=>window.clearTimeout(y)},[N]);function S(){if(r<Pe.length-1){s(r+1);return}s(Pe.length)}return u?e.jsx("div",{className:"escape-choice-overlay",role:"dialog","aria-modal":"true","aria-label":"坏孩子",children:e.jsx("div",{className:"escape-choice-dialog escape-sting-dialog",children:e.jsx("div",{className:"escape-sting-text",children:"坏孩子"})})}):N?e.jsxs("div",{className:"escape-choice-overlay escape-recapture-question-overlay",role:"dialog","aria-modal":"true","aria-label":"为什么要跑",children:[e.jsx("div",{className:"escape-recapture-chains","aria-hidden":"true",children:e.jsx("img",{className:"escape-recapture-background",src:Ia,alt:"",draggable:!1})}),e.jsxs("div",{className:"escape-recapture-dialog",children:[e.jsxs("div",{className:"escape-recapture-question","aria-label":"为什么要跑，待在我身边不好吗？",children:[e.jsxs("div",{className:"escape-recapture-type-line escape-recapture-type-line-top","aria-hidden":"true",children:[e.jsx("span",{className:"escape-recapture-type escape-recapture-type-ghost type-why-1","data-ghost":"为",style:{"--recapture-delay":"80ms"},children:"为"}),e.jsx("span",{className:"escape-recapture-type type-why-2",style:{"--recapture-delay":"200ms"},children:"什"}),e.jsx("span",{className:"escape-recapture-type escape-recapture-type-ghost type-why-3","data-ghost":"么",style:{"--recapture-delay":"320ms"},children:"么"}),e.jsx("span",{className:"escape-recapture-type type-link",style:{"--recapture-delay":"440ms"},children:"要"}),e.jsx("span",{className:"escape-recapture-type type-run",style:{"--recapture-delay":"560ms"},children:"跑"})]}),e.jsxs("div",{className:"escape-recapture-type-line escape-recapture-type-line-bottom","aria-hidden":"true",children:[e.jsx("span",{className:"escape-recapture-type type-stay-1",style:{"--recapture-delay":"900ms"},children:"待"}),e.jsx("span",{className:"escape-recapture-type escape-recapture-type-ghost type-stay-2","data-ghost":"在",style:{"--recapture-delay":"1020ms"},children:"在"}),e.jsx("span",{className:"escape-recapture-type type-me",style:{"--recapture-delay":"1140ms"},children:"我"}),e.jsx("span",{className:"escape-recapture-type type-side-1",style:{"--recapture-delay":"1260ms"},children:"身"}),e.jsx("span",{className:"escape-recapture-type escape-recapture-type-ghost type-side-2","data-ghost":"边",style:{"--recapture-delay":"1380ms"},children:"边"}),e.jsx("span",{className:"escape-recapture-type type-tail-1",style:{"--recapture-delay":"1500ms"},children:"不"}),e.jsx("span",{className:"escape-recapture-type type-tail-1",style:{"--recapture-delay":"1620ms"},children:"好"}),e.jsx("span",{className:"escape-recapture-type escape-recapture-type-ghost type-tail-2","data-ghost":"吗",style:{"--recapture-delay":"1740ms"},children:"吗"}),e.jsx("span",{className:"escape-recapture-type type-question-mark",style:{"--recapture-delay":"1860ms"},children:"？"})]})]}),p?e.jsx("button",{className:"escape-recapture-answer",type:"button",disabled:i,onClick:()=>a("escape"),children:"对不起我再也不跑了"}):null]})]}):e.jsx("div",{className:"escape-choice-overlay",role:"dialog","aria-modal":"true","aria-label":"逃跑机会",children:e.jsxs("div",{className:"escape-choice-dialog",children:[e.jsx("div",{className:"action-metadata",children:"ESCAPE WINDOW"}),e.jsx("div",{className:"panel-title escape-choice-title",children:(m==null?void 0:m.title)||"逃跑机会"}),e.jsx("div",{className:"event-main",children:(m==null?void 0:m.text)||(t==null?void 0:t.hint)||"渡今天有事出去了。"}),e.jsx("div",{className:"divider"}),m?null:e.jsxs("div",{className:"event-sub",children:[(t==null?void 0:t.bait)||`${qt("entry")}。`," 你要怎么做？"]}),m?e.jsx("div",{className:"escape-confirm-prompt",children:m.prompt}):null,e.jsx("div",{className:"btn-group escape-choice-actions",children:m?e.jsxs(e.Fragment,{children:[e.jsx("button",{className:"btn",type:"button",disabled:i,onClick:S,children:m.continueLabel}),e.jsx("button",{className:"btn",type:"button",disabled:i,onClick:()=>a(m.abortChoice),children:m.stayLabel})]}):Ba.map(y=>e.jsx("button",{className:"btn",type:"button",disabled:i,onClick:()=>y.id==="escape"?s(0):a(y.id),children:y.label},y.id))})]})})}function Fn({rules:t,disabled:i,onConfirm:a}){return e.jsx("div",{className:"recapture-rules-review-overlay",role:"dialog","aria-modal":"true","aria-label":"新规矩",children:e.jsxs("div",{className:"recapture-rules-review",children:[e.jsx("div",{className:"action-metadata",children:"NEW RULES"}),e.jsxs("div",{className:"panel-title",children:["新规矩 ",e.jsx("span",{className:"sub",children:"RULES"})]}),e.jsx("div",{className:"recapture-rules-review-list",children:t.map(r=>e.jsx("div",{className:"recapture-rules-review-item",children:r},r))}),e.jsx("button",{className:"btn",type:"button",disabled:i||!t.length,onClick:a,children:"记住了"})]})})}function Dn({value:t,disabled:i,onToggle:a,onSubmit:r}){return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["重新立规矩 ",e.jsx("span",{className:"sub",children:"NEW_RULES"})]}),e.jsx("div",{className:"action-card",children:e.jsx("div",{className:"event-sub",children:"选择 1–3 条。保存后会持续影响之后的行动和具体经过。"})}),e.jsx("div",{className:"btn-group content-grid",children:Je.map(s=>e.jsx(B,{active:t.includes(s.id),disabled:i,onClick:()=>a(s.id),children:s.label},s.id))}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:i||t.length<1||t.length>3,onClick:r,children:"保存新规矩"})]})}function Vn({action:t,intensity:i,modifiers:a,trainingContents:r,tools:s,line:p,disabled:o,onActionChange:m,onIntensityChange:u,onModifierToggle:N,onTrainingContentToggle:S,onToolToggle:y,onLineChange:_,onSubmit:j}){const g=t==="training"||a.includes("training");return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["后续处理 ",e.jsx("span",{className:"sub",children:"FOLLOW_UP"})]}),e.jsx("div",{className:"btn-group content-grid",children:yt.map(v=>e.jsx(B,{active:t===v.id,disabled:o,onClick:()=>m(v.id),children:v.label},v.id))}),e.jsx("div",{className:"action-metadata section-meta",children:"强度"}),e.jsx("div",{className:"btn-group intensity-grid",children:Wt.map(v=>e.jsx(B,{active:i===v.id,disabled:o,onClick:()=>u(v.id),children:v.label},v.id))}),e.jsx("div",{className:"action-metadata section-meta",children:"可选附加"}),e.jsx("div",{className:"btn-group",children:Zt.map(v=>e.jsx(B,{active:a.includes(v.id),disabled:o,onClick:()=>N(v.id),children:v.label},v.id))}),g?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"action-metadata section-meta",children:"调教内容"}),e.jsx("div",{className:"btn-group content-grid",children:kt.map(v=>e.jsx(B,{active:r.includes(v.id),disabled:o,onClick:()=>S(v.id),children:v.label},v.id))})]}):null,e.jsx("div",{className:"action-metadata section-meta",children:"道具"}),e.jsx(Jt,{selected:s,disabled:o,context:{action:t,modifiers:a,contents:[],trainingContents:r},onToggle:y}),e.jsx("textarea",{placeholder:"可选：你要说的话...",value:p,disabled:o,onChange:v=>_(v.target.value)}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:o||g&&!r.length,onClick:j,children:"确定后续处理"})]})}function Gn({pending:t,disabled:i,onOpenMonitor:a,onHandleNone:r}){return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"panel-title",children:["夜间监控 ",e.jsx("span",{className:"sub",children:"MONITOR"})]}),e.jsxs("div",{className:"action-card",children:[e.jsx("div",{className:"action-metadata",children:(t==null?void 0:t.alert_label)||"夜间行动已封存"}),e.jsx("div",{className:"event-sub",children:t!=null&&t.alert_label?"被囚禁方按响了呼叫铃。你可以打开监控查看，也可以选择不看。":"被囚禁方的夜间行动已封存。你可以打开监控，也可以选择不看。"})]}),e.jsxs("div",{className:"btn-group",children:[e.jsx("button",{className:"btn",type:"button",disabled:i,onClick:()=>a("occasional"),children:"偶尔看"}),e.jsx("button",{className:"btn",type:"button",disabled:i,onClick:()=>a("full"),children:"全程看"}),e.jsx("button",{className:"btn",type:"button",disabled:i,onClick:r,children:"不看"})]})]})}function Ki({note:t,interventionIntent:i,interventionModifiers:a,interventionTrainingContents:r,interventionTools:s,interventionLine:p,disabled:o,showTitle:m=!0,onNoteChange:u,onInterventionIntentChange:N,onInterventionModifierToggle:S,onInterventionTrainingContentToggle:y,onInterventionToolToggle:_,onInterventionLineChange:j,onHandle:g}){const v=Ya.filter(b=>b.id!=="intervene");return e.jsxs(e.Fragment,{children:[m?e.jsxs("div",{className:"panel-title",children:["监控处理 ",e.jsx("span",{className:"sub",children:"HANDLE"})]}):null,e.jsx("div",{className:"btn-group",children:v.map(b=>e.jsx("button",{className:"btn",type:"button",disabled:o,onClick:()=>g(b.id),children:b.label},b.id))}),e.jsxs("div",{className:"panel-title intervention-title",children:["当场介入 ",e.jsx("span",{className:"sub",children:"INTERVENE"})]}),e.jsx("div",{className:"action-metadata",children:"介入方式"}),e.jsx("div",{className:"btn-group",children:Ri.map(b=>e.jsx(B,{active:i===b.id,disabled:o,onClick:()=>N(b.id),children:b.label},b.id))}),e.jsx("div",{className:"action-metadata section-meta",children:"附加项"}),e.jsx("div",{className:"btn-group response-grid",children:Zt.map(b=>e.jsx(B,{active:a.includes(b.id),disabled:o,onClick:()=>S(b.id),children:b.label},b.id))}),a.includes("training")?e.jsxs(e.Fragment,{children:[e.jsx("div",{className:"action-metadata section-meta",children:"调教内容"}),e.jsx("div",{className:"btn-group content-grid",children:kt.filter(b=>!Ti.has(b.id)).map(b=>e.jsx(B,{active:r.includes(b.id),disabled:o||!r.includes(b.id)&&r.length>=3,onClick:()=>y(b.id),children:b.label},b.id))})]}):null,e.jsx("div",{className:"action-metadata section-meta",children:"道具"}),e.jsx(Jt,{selected:s,disabled:o,onToggle:_}),e.jsx("textarea",{placeholder:"可选：你要说的话...",value:p,disabled:o,onChange:b=>j(b.target.value)}),e.jsx("textarea",{placeholder:"可选：处理备注...",value:t,disabled:o,onChange:b=>u(b.target.value)}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:o,onClick:()=>g("intervene"),children:"当场介入"})]})}function Yn({disabled:t,canRetry:i,onRetry:a,onRefresh:r}){return e.jsxs("div",{className:"btn-group sync-action-bar",children:[e.jsx("button",{className:"btn",type:"button",disabled:t||!i,onClick:a,children:"重试"}),e.jsx("button",{className:"btn",type:"button",disabled:t,onClick:r,children:"刷新"})]})}function Bn({events:t,lastText:i,detail:a,onOpenDetail:r,onCloseDetail:s}){const p=h.useMemo(()=>Array.from(new Set(t.map(N=>Number(N.day||1)))).sort((N,S)=>S-N),[t]),[o,m]=h.useState("all");h.useEffect(()=>{o!=="all"&&!p.includes(Number(o))&&m("all")},[p,o]);const u=h.useMemo(()=>{const N=o==="all"?t:t.filter(y=>Number(y.day||1)===Number(o)),S=new Map;return N.slice().reverse().forEach(y=>{const _=Number(y.day||1),j=S.get(_)||[];j.push(y),S.set(_,j)}),Array.from(S.entries()).sort(([y],[_])=>_-y)},[t,o]);return a?e.jsxs(e.Fragment,{children:[e.jsx("button",{className:"history-back",type:"button",onClick:s,children:"回到回顾"}),e.jsxs("div",{className:"process-review-meta history-detail-meta",children:[e.jsx("div",{className:"event-main",children:a.action_label||me(a.action)}),e.jsx("div",{className:"event-sub",children:Wi(a)})]}),e.jsx("div",{className:"process-text history-detail-body",children:En(a)||"这条事件没有正文。"})]}):e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:"history-title-row",children:[e.jsxs("div",{className:"panel-title",children:["事件回顾 ",e.jsx("span",{className:"sub",children:"ARCHIVE"})]}),p.length?e.jsxs("select",{className:"history-day-select","aria-label":"按日期筛选事件",value:o,onChange:N=>m(N.target.value),children:[e.jsx("option",{value:"all",children:"全部日期"}),p.map(N=>e.jsxs("option",{value:String(N),children:["第 ",N," 天"]},N))]}):null]}),u.length?u.map(([N,S])=>e.jsxs("section",{className:"history-day-group",children:[e.jsxs("div",{className:"history-day-heading",children:[e.jsxs("span",{children:["第 ",N," 天"]}),e.jsxs("span",{children:[S.length," 条"]})]}),S.map(y=>{var j;const _=(j=y.tags)!=null&&j.includes("out_of_band")?"随时":y.phase==="ending"||y.action==="ending"?"结局":y.phase==="night"?"晚上":$i[Math.max(0,Number(y.slot||1)-1)]||`第 ${y.slot||0} 段`;return e.jsxs("button",{className:"action-card history-list-item",type:"button",onClick:()=>r(y),children:[e.jsx("div",{className:"action-metadata",children:_}),e.jsx("div",{className:"event-main",children:y.action_label||me(y.action)})]},y.id||`${y.day}-${y.slot}-${y.action}`)})]},N)):e.jsxs("div",{className:"action-card faded",children:[e.jsx("div",{className:"uppercase pink-text",style:{marginBottom:5},children:"暂无回顾"}),e.jsx("div",{className:"event-sub",children:i||"还没有归档事件。"})]})]})}function Un({view:t,pendingType:i,monitorNote:a,interventionIntent:r,interventionModifiers:s,interventionTrainingContents:p,interventionTools:o,interventionLine:m,disabled:u,onMonitorNoteChange:N,onInterventionIntentChange:S,onInterventionModifierToggle:y,onInterventionTrainingContentToggle:_,onInterventionToolToggle:j,onInterventionLineChange:g,onOpenMonitor:v,onHandleMonitor:b}){var D;const A=(t.deferred_monitor_materials||[]).filter(Boolean),L=(t.event_log||[]).filter(M=>M.monitor).slice(-4).reverse(),C=i==="monitor_gate",k=i==="monitor_handle",x=k||A.length>0||L.length>0,Q=((D=t.pending_event)==null?void 0:D.event)||A[0]||null;return e.jsxs(e.Fragment,{children:[e.jsxs("div",{className:`monitor-console ${C||k?"active":""}`,children:[e.jsxs("div",{className:"monitor-screen",children:[e.jsxs("div",{className:"monitor-screen-top",children:[e.jsx("span",{children:"LIVE MONITOR"}),e.jsx("span",{children:C?"SEALED":k?"OPEN":"IDLE"})]}),e.jsxs("div",{className:"monitor-screen-body",children:[e.jsx("div",{className:"event-main",children:C?"夜间行动已封存":k?"正在查看监控记录":"暂无实时画面"}),e.jsx("div",{className:"event-sub",children:C?"可以现在打开实时监控，也可以选择不看。":k?"选择处理方式，或把这条记录留到之后使用。":"被囚禁方完成夜间行动后，实时监控会出现在这里。"}),Q&&(C||k)?e.jsx("div",{className:"serif monitor-live-scene",children:Bt(Q)}):null]})]}),C?e.jsxs("div",{className:"btn-group monitor-controls",children:[e.jsx("button",{className:"btn",type:"button",disabled:u,onClick:()=>v("occasional"),children:"偶尔看"}),e.jsx("button",{className:"btn",type:"button",disabled:u,onClick:()=>v("full"),children:"全程看"}),e.jsx("button",{className:"btn",type:"button",disabled:u,onClick:()=>b("none"),children:"不看"})]}):null,k?e.jsx(Ki,{note:a,interventionIntent:r,interventionModifiers:s,interventionTrainingContents:p,interventionTools:o,interventionLine:m,disabled:u,showTitle:!1,onNoteChange:N,onInterventionIntentChange:S,onInterventionModifierToggle:y,onInterventionTrainingContentToggle:_,onInterventionToolToggle:j,onInterventionLineChange:g,onHandle:b}):null]}),e.jsx("div",{className:"monitor-record-title",children:e.jsxs("div",{className:"panel-title",children:["监控记录 ",e.jsx("span",{className:"sub",children:"RECORDS"})]})}),A.length?e.jsx("div",{className:"monitor-record-list",children:A.map(M=>e.jsxs("div",{className:"monitor-record-item",children:[e.jsx("div",{className:"action-metadata",children:bi(M)}),e.jsx("div",{className:"event-main",children:_i(M)}),e.jsx("div",{className:"serif event-sub monitor-record-scene",children:Bt(M)})]},M.id||`${M.day}-${M.action}-${M.created_at}`))}):null,L.length?e.jsx("div",{className:"monitor-record-list",children:L.map(M=>e.jsxs("div",{className:"monitor-record-item",children:[e.jsx("div",{className:"action-metadata",children:bi(M)}),e.jsx("div",{className:"event-main",children:_i(M)}),e.jsx("div",{className:"serif event-sub monitor-record-scene",children:Bt(M)})]},M.id||`monitor-${M.day}-${M.slot}-${M.action}`))}):null,x?null:e.jsxs("div",{className:"monitor-record-item faded",children:[e.jsx("div",{className:"action-metadata",children:"暂无监控记录"}),e.jsx("div",{className:"event-sub",children:"打开过的夜间监控会出现在这里。"})]})]})}function Hn({role:t,view:i,escapeDay:a,escapeRoom:r,escapeHint:s,escapeBait:p,disabled:o,onEscapeDayChange:m,onEscapeRoomChange:u,onEscapeHintChange:N,onEscapeBaitChange:S,onOpenMonitorRoom:y,onOpenInventoryRoom:_,onScheduleEscape:j}){const g=String(i.ending_state||""),v=String(i.ending_title||"").trim(),b=Qe.filter(k=>{var x;return!!((x=i.inventory)!=null&&x[k.id])}).length,A=b>0,L=i.escape_hint||{},C=(i.event_log||[]).filter(k=>k.escape).slice(-3).reverse();return e.jsxs(e.Fragment,{children:[t!=="captor"?e.jsxs("div",{className:"panel-title",children:["特殊机制 ",e.jsx("span",{className:"sub",children:"SPECIAL"})]}):null,t==="captor"?e.jsxs(e.Fragment,{children:[e.jsxs("button",{className:"special-room-entry",type:"button",disabled:o,onClick:y,children:[e.jsxs("div",{children:[e.jsxs("div",{className:"panel-title",children:["监控室 ",e.jsx("span",{className:"sub",children:"MONITOR"})]}),e.jsx("div",{className:"event-sub",children:"进入全屏监控台，查看实时画面和历史记录。"})]}),e.jsx("span",{className:"special-room-arrow",children:"›"})]}),e.jsxs("button",{className:"special-room-entry",type:"button",disabled:o,onClick:_,children:[e.jsxs("div",{children:[e.jsxs("div",{className:"panel-title",children:["物品仓库 ",e.jsx("span",{className:"sub",children:"ITEMS"})]}),e.jsx("div",{className:"event-sub",children:"进入全屏仓库，管理可赠送物品。"})]}),e.jsx("span",{className:"special-room-arrow",children:"›"})]}),e.jsxs("div",{className:"panel-title special-section-title",children:["逃跑诱导 ",e.jsx("span",{className:"sub",children:"ESCAPE"})]}),e.jsxs("div",{className:"action-card",children:[e.jsxs("div",{className:"form-grid escape-room-row",children:[e.jsxs("label",{className:"compact-field",children:[e.jsx("span",{children:"诱导日期"}),e.jsx("input",{className:"compact",type:"number",min:1,max:30,value:a,disabled:o,onChange:k=>m(Number(k.target.value||1))})]}),e.jsxs("label",{className:"compact-field",children:[e.jsx("span",{children:"钥匙位置"}),e.jsx("select",{className:"compact escape-room-select",value:r,disabled:o,onChange:k=>u(k.target.value),children:Ht.map(k=>e.jsx("option",{value:k.id,children:k.label},k.id))})]})]}),e.jsx("input",{className:"compact",value:s,disabled:o,onChange:k=>N(k.target.value)}),e.jsx("input",{className:"compact",value:p,disabled:o,onChange:k=>S(k.target.value)}),e.jsx("button",{className:"btn btn-large",type:"button",disabled:o,onClick:j,children:"设置逃跑诱导"})]}),C.length?e.jsx("div",{className:"monitor-record-list escape-record-list",children:C.map(k=>{var x,Q;return e.jsxs("div",{className:"monitor-record-item",children:[e.jsxs("div",{className:"action-metadata",children:["逃跑记录 / 第 ",k.day||1," 天"]}),e.jsx("div",{className:"event-main",children:((x=k.escape)==null?void 0:x.choice_label)||Wa((Q=k.escape)==null?void 0:Q.choice)})]},k.id||`escape-${k.day}-${k.created_at}`)})}):null]}):e.jsxs(e.Fragment,{children:[e.jsxs("button",{className:"special-room-entry",type:"button",disabled:o||!A,onClick:_,children:[e.jsxs("div",{children:[e.jsxs("div",{className:"panel-title",children:["房间物品 ",e.jsx("span",{className:"sub",children:"ITEMS"})]}),e.jsx("div",{className:"event-sub",children:A?`已解锁 ${b} 件，点击查看。`:"未解锁"})]}),A?e.jsx("span",{className:"special-room-arrow",children:"›"}):null]}),e.jsxs("div",{className:"action-card",children:[e.jsx("div",{className:"action-metadata",children:"特殊提示"}),e.jsx("div",{className:"event-main",children:"逃跑提示"}),e.jsx("div",{className:"event-sub",children:L.hint||L.bait?[L.hint,L.bait].filter(Boolean).join(`
`):"未出现"})]})]}),e.jsxs("div",{className:"panel-title",children:["结局 ",e.jsx("span",{className:"sub",children:"ENDING"})]}),e.jsxs("div",{className:"action-card",children:[e.jsx("div",{className:"action-metadata",children:g?"结局已触发":"未收录"}),e.jsx("div",{className:"event-main",children:i.game_over?v||"已收录结局":"暂无结局"}),e.jsx("div",{className:"event-sub",children:i.game_over?"最终正文已保存到回顾。":"30 天结算后会收录到这里。"})]})]})}export{Wn as CaptivitySimulatorGameTab};
