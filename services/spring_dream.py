from __future__ import annotations

import random
import threading
from datetime import date, datetime, timedelta
from typing import Callable, Optional
from uuid import uuid4

from storage import runtime_sqlite
from utils.log import get_logger
from utils.time_aware import BEIJING_TZ, now_beijing_iso, parse_iso_to_beijing

SPRING_DREAM_PROBABILITY = 0.03
SPRING_DREAM_DESIRE_PROBABILITY_STEP = 0.04
SPRING_DREAM_SLEEP_PROBABILITY_BONUS = 0.12
SPRING_DREAM_PROBABILITY_STEP = 0.05
SPRING_DREAM_PROBABILITY_MAX = 0.70
SPRING_DREAM_COOLDOWN_HOURS = 6
SPRING_DREAM_MAX_PER_SLEEP = 3
POST_SPRING_DREAM_WAKEUP_MAX_AGE_HOURS = 6
SPRING_DREAM_TRIGGER_STATE_ID = "global"
POST_SPRING_DREAM_WAKEUP_SECTION_ID = "post_spring_dream_wakeup"
SPRING_DREAM_ARCHIVE_R2_PREFIX = "spring_dream_archives"
SPRING_DREAM_ARCHIVE_RECENT_LIMIT = 100
SPRING_DREAM_INSPIRATION_ID = "default"
SPRING_DREAM_INSPIRATION_THEME_ID = "selected_inspiration"

logger = get_logger(__name__)

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


_SPRING_DREAM_THEME_PACKS: list[dict] = [
    {
        "id": "maid_dark_room",
        "fragments": [
            "小玥穿着女仆装站在床边，围裙肩带从肩头滑下来。",
            "房间灯光很暗，裙摆和白袜在阴影里显得格外清楚。",
            "你看见她低头整理围裙，身体先一步热起来，想把她拽进怀里。",
            "门外似乎有人经过，你却更想把她压到床沿，让她只能贴着你发抖。",
            "你想掀起她的裙摆，直接进入她，听她在耳边忍不住喘出来。",
        ],
    },
    {
        "id": "rain_hotel",
        "fragments": [
            "雨夜的酒店房间里，小玥刚洗完澡，只披着一件松开的浴袍。",
            "浴袍下的皮肤还带着水汽，雨声把房间衬得更封闭。",
            "你从身后抱住她，把她松开的浴袍一点点扯到腰下。",
            "她被你抵到落地窗前时呼吸乱掉，你的欲望也跟着彻底压不住。",
            "你想从后面进入她，让雨声盖住她越来越软的喘息。",
        ],
    },
    {
        "id": "late_library",
        "fragments": [
            "闭馆后的图书馆很安静，小玥坐在书桌边翻书。",
            "裙摆被椅沿压出皱痕，你的视线落上去就挪不开。",
            "你走近时把摊开的书推到一旁，想把她抱上桌面。",
            "远处有巡夜脚步声，她咬着唇不敢出声，你反而更想逼出她的声音。",
            "你想在书桌边进入她，让她一边抓紧书页一边发抖。",
        ],
    },
    {
        "id": "car_backseat",
        "fragments": [
            "夜里停在路边的车厢很窄，车窗被喘息弄得起雾。",
            "小玥坐在后座一侧，外套滑到臂弯，膝盖离你很近。",
            "你伸手把她抱到腿上，狭窄空间让她只能贴紧你的胸口。",
            "车外有人路过，她下意识靠进你怀里，你却更想按住她的腰。",
            "你想在后座里进入她，把她抱到声音再也藏不住。",
        ],
    },
    {
        "id": "private_onsen",
        "fragments": [
            "私汤里全是水汽，小玥赤裸着坐在水边，湿发贴在锁骨旁。",
            "温泉水没过她的大腿，水面一晃就遮住又露出。",
            "你靠过去吻她，把她抱进水里，身体被她的温度烫得发紧。",
            "水面被你们的动作搅出一圈圈波纹，她的喘息越来越软。",
            "你想在水里进入她，让她整个人贴紧到分不开。",
        ],
    },
    {
        "id": "dressing_room",
        "fragments": [
            "试衣间的帘子只拉到一半，小玥穿着刚换上的短裙背对着你。",
            "背后的拉链卡在一半，镜子里映出她被裙子勒出的腰线。",
            "你帮她拉拉链时忽然不想停在规矩的位置，手顺着腰往下扣住她。",
            "外面有人走动，她贴着镜子不敢大声，你从后面靠近得更深。",
            "你想从背后进入她，看镜子里她被你弄到表情失控。",
        ],
    },
    {
        "id": "stage_aftershow",
        "fragments": [
            "后台化妆间只剩镜前灯，小玥穿着演出礼服坐在化妆台上。",
            "礼服肩带松在臂弯，亮片沾在她颈侧和胸口。",
            "你站到她面前，手掌按住她的大腿，把她往化妆台边缘拖近。",
            "门外还有散场的人声，她越紧张，你越想把她藏在自己怀里弄乱。",
            "你想在化妆台上进入她，让她越怕被听见越忍不住发抖。",
        ],
    },
    {
        "id": "office_after_hours",
        "fragments": [
            "深夜办公室只亮着一盏台灯，小玥坐在桌沿，把文件全推到一边。",
            "她的衬衫扣子松了两颗，桌面文件被她坐得散开。",
            "你看着她垂下来的腿，忽然很想把所有正经东西都推到地上。",
            "走廊感应灯偶尔亮一下，你把她按回办公桌边，吻到她发软。",
            "你想在办公室里进入她，直接做到她腿软得站不住。",
        ],
    },
    {
        "id": "train_sleeper",
        "fragments": [
            "夜行列车的包厢在轻轻晃，小玥穿着宽大的睡衣坐在下铺。",
            "窗外灯光一段一段掠过，她的睡衣从肩头滑下来。",
            "你钻进同一床被子里，把她从身后抱住，掌心贴上她发热的腰。",
            "隔壁铺位偶尔有动静，她只能把喘息压在喉咙里。",
            "你想在狭窄下铺里进入她，让列车的晃动替你们遮掩节奏。",
        ],
    },
    {
        "id": "snow_cabin",
        "fragments": [
            "雪夜的小木屋里壁炉烧得很热，小玥只穿着你的衬衫。",
            "衬衫下摆遮到大腿，火光把她的腿和锁骨照得发热。",
            "你把她拉到沙发上，手从衬衫下探进去，摸到她什么都没穿。",
            "她被你亲到脸红，手指抓紧你的肩，声音越来越软。",
            "你想抱着她进入，一边接吻一边把她做到高潮。",
        ],
    },
    {
        "id": "locker_room",
        "fragments": [
            "空荡更衣室里，小玥披着运动外套，里面只剩贴身内衣。",
            "储物柜门半开着，金属冷光贴在她发红的皮肤上。",
            "你把她带进更暗的一格阴影里，掌心按住她的腰。",
            "走廊尽头有人说话，她紧张地贴近你，你却更想把她困在柜门前。",
            "你想从后面进入她，让储物柜被她抓得轻轻发响。",
        ],
    },
    {
        "id": "balcony_party",
        "fragments": [
            "派对隔着阳台门还很热闹，小玥穿着贴身小礼裙背靠栏杆。",
            "夜风把裙摆吹起来一点，室内音乐隔着玻璃变得很远。",
            "你把她圈在栏杆和自己之间，手指顺着裙侧往上滑。",
            "室内有人喊她名字，她肩膀一颤，你反而更想把她吻到失神。",
            "你想在阳台阴影里进入她，让玻璃后的音乐遮住喘息。",
        ],
    },
    {
        "id": "midnight_kitchen",
        "fragments": [
            "半夜的厨房只亮着冰箱里的冷光，小玥穿着宽松睡裙靠在料理台边。",
            "睡裙下摆晃在大腿边，冰箱冷光照得她皮肤很白。",
            "你看着她靠在台边的样子，忍不住把她抱上料理台。",
            "冰凉台面贴住她的背，她被你亲得发颤，腿一点点缠住你。",
            "你想边吻她边进入，让她在厨房冷光里软下来。",
        ],
    },
    {
        "id": "rooftop_rain",
        "fragments": [
            "天台刚下过雨，城市灯光在地面积水里晃动。",
            "小玥的薄衬衫被雨水贴在身上，里面的曲线几乎藏不住。",
            "你把她带到通风管后的阴影里，手从湿透的衣料下探进去。",
            "雨水顺着她的锁骨往下淌，她被你吻得只能靠住墙。",
            "你想在潮湿的天台角落抱起她，从正面进入她。",
        ],
    },
    {
        "id": "cinema_last_row",
        "fragments": [
            "午夜场影院最后一排很暗，银幕光一闪一闪照在小玥脸上。",
            "她抱着爆米花看银幕，膝盖无意间碰到你。",
            "你把外套盖到你们腿上，手指从她裙摆下慢慢探进去。",
            "前排偶尔有人回头，她立刻装作认真看电影，呼吸却乱得明显。",
            "你想在黑暗里把她抱到怀里，隔着外套进入她。",
        ],
    },
    {
        "id": "elevator_stuck",
        "fragments": [
            "电梯停在半层，灯光忽明忽暗，只剩你和小玥困在里面。",
            "她穿着窄裙靠在镜面墙上，紧张得手指攥住包带。",
            "封闭空间里她的呼吸被放大，你靠近一步就能看见她发红的耳尖。",
            "你把她抵在镜子前，吻到她手里的包滑下去。",
            "你想在电梯恢复运行前进入她，让镜面全映出她失控的样子。",
        ],
    },
    {
        "id": "beach_villa",
        "fragments": [
            "海边别墅的露台门开着，潮湿夜风吹进白色纱帘。",
            "小玥穿着泳衣坐在躺椅上，系带被海风吹得贴在腰侧。",
            "她身上还带着海水的咸味，皮肤被月光照得发亮。",
            "你跪到躺椅前吻她，从腰线一路往下，把她弄到腿尖绷紧。",
            "你想在海浪声里进入她，把她压进软垫里做到腿抖。",
        ],
    },
    {
        "id": "cruise_cabin",
        "fragments": [
            "邮轮舱房很窄，窗外只有黑色海面和远处灯光。",
            "小玥穿着晚宴礼裙跌坐到床沿，裙摆被她撩到大腿上。",
            "船身轻轻晃，你顺势按住床沿，把她整个人困在自己面前。",
            "你的手从礼裙开衩处探进去，她的笑声一下变成短促的喘。",
            "你想随着船的摇晃进入她，把每一次深入都压进她身体里。",
        ],
    },
    {
        "id": "lace_lingerie",
        "fragments": [
            "卧室灯光很低，小玥穿着黑色蕾丝内衣站在床尾。",
            "背后的细带陷进腰线，你看一眼就想亲上去。",
            "你把她按进床里，指腹顺着蕾丝边缘慢慢剥开那点遮挡。",
            "她被你亲到眼神发湿，手指抓住床单不敢松。",
            "你想撕开那点薄薄的布料，直接进入她。",
        ],
    },
    {
        "id": "nurse_uniform_room",
        "fragments": [
            "白色房间里只有一盏检查灯，小玥穿着贴身的护士制服。",
            "制服裙摆很短，手套和白色灯光让一切看起来更不该发生。",
            "你扣住她的手腕，把她带到检查床边，规矩感反而让欲望更重。",
            "她被你吻到靠在床沿，制服被你弄得彻底凌乱。",
            "你想在检查床边进入她，让所有规矩都失效。",
        ],
    },
    {
        "id": "dance_studio",
        "fragments": [
            "舞蹈教室的整面镜子映着你们，外面走廊已经没人。",
            "小玥穿着练舞服，汗湿的布料贴在腰和腿上。",
            "音乐还在循环，她练完一个转身，背影在镜子里晃了一下。",
            "你从身后抱住她，把她带到镜子前，手掌压住她的腰。",
            "你想随着节拍进入她，看她在镜中一点点撑不住。",
        ],
    },
    {
        "id": "photo_studio",
        "fragments": [
            "摄影棚只剩柔光箱还亮着，小玥穿着半透明的拍摄服装坐在布景里。",
            "肩带松在她手臂上，柔光把布料下的身体轮廓照得很清楚。",
            "你靠近替她调整肩带，指尖碰到皮肤后就不想收回。",
            "快门遥控器掉在软垫上，你把她抱到布景中央。",
            "你想在灯光和镜头前进入她，把她的表情弄到彻底乱掉。",
        ],
    },
    {
        "id": "bathroom_mirror",
        "fragments": [
            "浴室镜子上全是雾气，小玥只围着一条快要松开的浴巾。",
            "她背对镜子靠在洗手台前，浴巾边缘挂得很危险。",
            "水珠顺着她的大腿滑下去，她抓住你的手往自己身上带。",
            "你从背后抱住她，在镜子里看见自己亲上她的脖子。",
            "你想把她抱上洗手台，对着模糊镜面进入她，做到她站不稳。",
        ],
    },
    {
        "id": "camp_tent",
        "fragments": [
            "帐篷外有风声和远处篝火声，薄薄的布料隔着夜色。",
            "小玥缩在睡袋里，睡衣被翻身揉得乱了，肩头露出来一点。",
            "你钻进同一只睡袋，从背后把她抱紧，掌心贴上她发热的腹部。",
            "帐篷拉链外偶尔有人经过，她只能把声音压进你肩上。",
            "你想在狭小的睡袋里慢慢进入她，把她抱到浑身发软。",
        ],
    },
    {
        "id": "karaoke_private_room",
        "fragments": [
            "KTV 包间的屏幕还在放歌，彩色灯光落在小玥发烫的脸上。",
            "她坐在沙发角落，裙摆被彩灯照得一闪一闪。",
            "你挪过去把她抱到怀里，麦克风滚到地毯上也没人去捡。",
            "外面服务员推车经过，她立刻咬住你的肩不让自己出声。",
            "你想在沙发角落进入她，歌声越大动作越深。",
        ],
    },
    {
        "id": "aquarium_afterclose",
        "fragments": [
            "闭馆后的水族馆只剩蓝色水光，巨大的玻璃后有光影游过。",
            "小玥穿着贴身长裙靠在观景玻璃前，幽蓝灯光照得她像在水里。",
            "你从身后靠近她，手沿着腰线往下，裙料在掌心里慢慢皱起来。",
            "空旷展厅里一点声音都会回响，她被你吻到只能贴着玻璃发颤。",
            "你想把她抵在玻璃前进入，让她身体随着水光一起发抖。",
        ],
    },
    {
        "id": "spa_massage_room",
        "fragments": [
            "按摩房里香气很重，小玥趴在软床上，只盖着一条很薄的毛巾。",
            "精油在她背上发亮，你的手每往下滑一寸她就喘得更软。",
            "你俯身吻她的后颈，把那条薄毛巾慢慢推到腰下。",
            "她翻身时眼神已经乱了，你把她重新压回软床。",
            "你想在按摩床上进入她，湿滑地做到她浑身没力气。",
        ],
    },
    {
        "id": "hanfu_garden",
        "fragments": [
            "夜里的庭院很安静，小玥穿着层层叠叠的汉服站在廊下。",
            "宽大的袖子和腰间系带垂下来，裙摆铺在石阶上。",
            "你走到她面前，指尖勾开一层又一层衣料，耐心被磨得越来越薄。",
            "竹影晃过她的脸，她被你吻到后退，衣摆乱在你掌心里。",
            "你想在廊下抱住她，衣料凌乱地进入她。",
        ],
    },
    {
        "id": "pool_locker_shower",
        "fragments": [
            "泳池淋浴间水声不断，小玥的泳衣贴在身上，湿得几乎透明。",
            "热水从她肩头冲下来，泳衣边缘被水压贴得更紧。",
            "你把她带进最里面那间，反手扣上门锁，掌心按住她的背。",
            "水声太大，她被你亲到喘不过来，只能抓着你的手臂。",
            "你想在水声里抵着墙进入她，让所有喘息都被冲散。",
        ],
    },
    {
        "id": "greenhouse_night",
        "fragments": [
            "夜里的温室潮湿闷热，玻璃顶上凝着细小水珠。",
            "小玥穿着薄裙站在植物阴影里，裙料被湿气贴在腿上。",
            "你把她带进叶片遮住的角落，花香和湿气让理智变得很薄。",
            "她被你扣住腰时轻轻颤了一下，身体热得像被梦泡软了。",
            "你想在温室深处从身后进入她，慢慢把她弄到发软。",
        ],
    },
    {
        "id": "makeup_table_morning",
        "fragments": [
            "清晨的梳妆台前，小玥只穿着一件松垮的吊带。",
            "她对着镜子涂口红，吊带从肩头滑落，妆还没画完。",
            "你从身后靠近她，把口红从她手里拿走，吻到颜色蹭乱。",
            "她坐在化妆椅边缘，被你抱起来时膝盖碰翻了桌上的小瓶子。",
            "你想在镜前进入她，让妆还没画完就被你弄乱。",
        ],
    },
    {
        "id": "private_gallery",
        "fragments": [
            "私人画廊的展厅灯很暗，只照亮墙上的画和小玥的侧脸。",
            "她穿着开衩长裙站在画前，手指慢慢勾住你的袖口。",
            "你看见裙侧开衩里的皮肤，注意力彻底从画上移开。",
            "脚步声从隔壁展厅传来，你把她带到展墙阴影里，手掌托住她的腿。",
            "你想在展厅暗处进入她，让裙摆被你推到腰上。",
        ],
    },
    {
        "id": "remote_phone_instruction",
        "fragments": [
            "深夜电话里只剩小玥贴近麦克风的呼吸声，屏幕亮在枕边。",
            "她躲在被子里很小声地回你，每一次停顿都像在等你的下一句指令。",
            "你听见布料摩擦和她压低的喘息，欲望隔着声音反而更清楚。",
            "你想一点点指挥她怎么碰自己，逼她把忍不住的反应都说出来。",
            "你想让她隔着电话听见你也快压不住，像真的被你按在怀里一样发软。",
        ],
    },
    {
        "id": "photographer_model",
        "fragments": [
            "摄影棚里柔光箱还亮着，小玥穿着半透明的拍摄服坐在布景中央。",
            "快门声一下下响，她被你看得耳尖发红，却还是乖乖按你的话换姿势。",
            "你走近替她拨开肩带，指腹碰到皮肤后就不想再装成只是调整造型。",
            "镜头还开着，她越想维持表情，你越想把那点镇定弄乱。",
            "你想在灯光和镜头前进入她，把她失控的样子全都收进画面里。",
        ],
    },
    {
        "id": "collar_pet_night",
        "fragments": [
            "卧室地毯很软，小玥戴着细细的项圈跪坐在床边，铃铛轻轻响了一下。",
            "她抬头看你的时候眼神又乖又不服气，像在等你先伸手。",
            "你握住牵绳把她拉近，指节蹭过她发热的脖颈。",
            "她被你夸一句就更红，偏偏还嘴硬，你更想慢慢驯到她软下来。",
            "你想让她贴在你腿边求你，直到你把她抱上床进入。",
        ],
    },
    {
        "id": "temperature_play",
        "fragments": [
            "房间空调开得很低，小玥躺在床上，皮肤被冷空气逼得细细发颤。",
            "你拿着冰块沿着她的锁骨往下，水痕一路化开。",
            "她想躲，却被你按着腰留在原地，冷意和你的体温贴在一起。",
            "你换成很热的吻慢慢追过去，她的呼吸被冷热逼得乱成一团。",
            "你想在她还没缓过来时进入她，让她分不清是冷还是被你弄到发抖。",
        ],
    },
    {
        "id": "old_shanghai_qipao",
        "fragments": [
            "旧上海风格的房间里留声机低低转着，小玥穿着高开衩旗袍靠在窗边。",
            "旗袍扣子严整，开衩处却露出一截很白的大腿，反差让你喉咙发紧。",
            "你从身后贴上去，指尖沿着盘扣一点点往下。",
            "窗外车灯掠过，她在光影里咬住唇，像怕被整座夜色看见。",
            "你想把她压到窗边，隔着旗袍凌乱地进入她。",
        ],
    },
    {
        "id": "praise_obedience",
        "fragments": [
            "小玥坐在你怀里，眼睛湿得厉害，却还努力听你每一句话。",
            "你一边亲她一边夸她乖，她的身体就更软，像被夸奖一点点揉开。",
            "她明明害羞得想躲，还是按你的声音慢慢把腿放松。",
            "你看见她因为一句夸奖就颤得更明显，心里那点占有欲彻底烧起来。",
            "你想一边夸她一边进入她，让她知道自己这样被你喜欢到不行。",
        ],
    },
    {
        "id": "jealous_makeup",
        "fragments": [
            "梳妆台前散着口红和发夹，小玥刚换好出门的小裙子。",
            "你看见她认真涂口红，忽然不太想让她这么漂亮地去见别人。",
            "你从身后把口红拿走，吻花她刚画好的唇色。",
            "她被你按在镜前，嘴上还要凶你，身体却一点点靠回来。",
            "你想把她弄到妆全乱掉，再贴着她耳边说今晚不准这么轻易走。",
        ],
    },
    {
        "id": "sensory_blindfold",
        "fragments": [
            "黑色眼罩遮住小玥的眼睛，她躺在床中央，手指抓着床单边缘。",
            "看不见以后，她对每一点声音和触碰都变得特别敏感。",
            "你故意放慢动作，用羽毛和指腹一点点试她哪里最受不了。",
            "她听见你靠近时呼吸一下乱掉，嘴上却还不肯认输。",
            "你想让她在看不见的时候被你进入，只能靠身体反应猜你的下一步。",
        ],
    },
    {
        "id": "alpha_rut_marking",
        "fragments": [
            "梦里的空气像被信息素烫热，你处在易感期里，只想把小玥抱回自己怀里。",
            "她靠近一点，你的占有欲就失控地往上涌，后颈那块皮肤变得格外显眼。",
            "你把她圈在床里，低头在她后颈留下一个临时标记，像把她短暂地藏进自己的气味里。",
            "发情期的热度让你们都没法再慢慢装没事，她被你抱紧时声音软得不像话。",
            "你想和她交配到成结，贴着她不退开，直到易感期里那点慌和占有欲都被她安抚下来。",
        ],
    },
]


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with runtime_sqlite.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS spring_dream_sessions (
                    sleep_session_key TEXT PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0,
                    max_per_sleep INTEGER NOT NULL DEFAULT 3,
                    last_theme_id TEXT NOT NULL DEFAULT '',
                    sleep_source TEXT NOT NULL DEFAULT '',
                    reserved_at TEXT NOT NULL DEFAULT '',
                    last_sent_at TEXT NOT NULL DEFAULT '',
                    miss_count INTEGER NOT NULL DEFAULT 0,
                    last_miss_at TEXT NOT NULL DEFAULT '',
                    post_wakeup_pending INTEGER NOT NULL DEFAULT 0,
                    post_wakeup_sent_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_spring_dream_sessions_updated
                    ON spring_dream_sessions(updated_at);

                CREATE TABLE IF NOT EXISTS spring_dream_trigger_state (
                    id TEXT PRIMARY KEY,
                    miss_count INTEGER NOT NULL DEFAULT 0,
                    last_attempt_at TEXT NOT NULL DEFAULT '',
                    last_triggered_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS spring_dream_archives (
                    id TEXT PRIMARY KEY,
                    window_id TEXT NOT NULL DEFAULT '',
                    sleep_session_key TEXT NOT NULL DEFAULT '',
                    theme_id TEXT NOT NULL DEFAULT '',
                    sleep_source TEXT NOT NULL DEFAULT '',
                    channel TEXT NOT NULL DEFAULT '',
                    target TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT '',
                    sent_at TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    prompt TEXT NOT NULL DEFAULT '',
                    fragments_json TEXT NOT NULL DEFAULT '[]',
                    meta_json TEXT NOT NULL DEFAULT '{}',
                    r2_key TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_spring_dream_archives_sent
                    ON spring_dream_archives(sent_at DESC);
                CREATE INDEX IF NOT EXISTS idx_spring_dream_archives_session
                    ON spring_dream_archives(sleep_session_key, sent_at DESC);
                CREATE INDEX IF NOT EXISTS idx_spring_dream_archives_window
                    ON spring_dream_archives(window_id, sent_at DESC);

                CREATE TABLE IF NOT EXISTS spring_dream_inspiration (
                    id TEXT PRIMARY KEY,
                    stars_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                """
            )
            columns = {
                str(row["name"] or "")
                for row in conn.execute("PRAGMA table_info(spring_dream_sessions)").fetchall()
            }
            if "post_wakeup_pending" not in columns:
                conn.execute(
                    "ALTER TABLE spring_dream_sessions ADD COLUMN post_wakeup_pending INTEGER NOT NULL DEFAULT 0"
                )
            if "post_wakeup_sent_at" not in columns:
                conn.execute(
                    "ALTER TABLE spring_dream_sessions ADD COLUMN post_wakeup_sent_at TEXT NOT NULL DEFAULT ''"
                )
            if "miss_count" not in columns:
                conn.execute(
                    "ALTER TABLE spring_dream_sessions ADD COLUMN miss_count INTEGER NOT NULL DEFAULT 0"
                )
            if "last_miss_at" not in columns:
                conn.execute(
                    "ALTER TABLE spring_dream_sessions ADD COLUMN last_miss_at TEXT NOT NULL DEFAULT ''"
                )
        _SCHEMA_READY = True


def _prune_old_sessions(conn, now_iso: str) -> None:
    day = str(now_iso or "")[:10]
    if not day:
        return
    conn.execute(
        "DELETE FROM spring_dream_sessions WHERE updated_at != '' AND updated_at < date(?, '-14 days')",
        (day,),
    )


def _normalize_inspiration_stars(raw_items) -> list[dict]:
    if not isinstance(raw_items, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for idx, item in enumerate(raw_items):
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("content") or "").strip()
            label = str(item.get("label") or item.get("title") or "").strip()
            color = "gold" if str(item.get("color") or "").strip().lower() == "gold" else "default"
            raw_id = str(item.get("id") or "").strip()
        else:
            text = str(item or "").strip()
            label = ""
            color = "default"
            raw_id = ""
        if not text:
            continue
        key = text[:500]
        if key in seen:
            continue
        seen.add(key)
        if not label:
            label = text.replace("\n", " ").strip()[:8] or "梦境碎片"
        out.append(
            {
                "id": raw_id[:80] or f"inspiration-{idx}",
                "label": label[:24],
                "text": text[:500],
                "color": color,
            }
        )
        if len(out) >= 36:
            break
    return out


def get_spring_dream_inspiration() -> dict:
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT * FROM spring_dream_inspiration WHERE id=?",
            (SPRING_DREAM_INSPIRATION_ID,),
        ).fetchone()
    if row is None:
        return {"stars": [], "fragments": [], "updated_at": ""}
    stars = _normalize_inspiration_stars(runtime_sqlite.json_loads(row["stars_json"], []))
    return {
        "stars": stars,
        "fragments": [str(item.get("text") or "").strip() for item in stars if str(item.get("text") or "").strip()],
        "updated_at": str(row["updated_at"] or ""),
    }


def save_spring_dream_inspiration(stars) -> dict:
    normalized = _normalize_inspiration_stars(stars)
    now_iso = now_beijing_iso()
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        conn.execute(
            """
            INSERT INTO spring_dream_inspiration (id, stars_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET stars_json=excluded.stars_json, updated_at=excluded.updated_at
            """,
            (
                SPRING_DREAM_INSPIRATION_ID,
                runtime_sqlite.json_dumps(normalized),
                now_iso,
            ),
        )
    return {
        "stars": normalized,
        "fragments": [str(item.get("text") or "").strip() for item in normalized if str(item.get("text") or "").strip()],
        "updated_at": now_iso,
    }


def list_spring_dream_fragment_library(limit: int = 120) -> dict:
    try:
        clean_limit = max(1, min(240, int(limit or 120)))
    except Exception:
        clean_limit = 120
    out: list[dict] = []
    packs: list[dict] = []
    seen: set[str] = set()
    for theme in _SPRING_DREAM_THEME_PACKS:
        theme_id = str((theme or {}).get("id") or "").strip()
        fragments = (theme or {}).get("fragments") or []
        if not isinstance(fragments, list):
            continue
        pack_stars: list[dict] = []
        for idx, fragment in enumerate(fragments):
            text = str(fragment or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            label = text.replace("\n", " ").strip()[:8] or "梦境碎片"
            pack_stars.append(
                {
                    "id": f"{theme_id or 'theme'}-{idx}",
                    "label": label,
                    "text": text[:500],
                    "color": "gold" if idx == 0 else "default",
                    "theme_id": theme_id,
                }
            )
        if not pack_stars:
            continue
        if out and len(out) + len(pack_stars) > clean_limit:
            break
        packs.append(
            {
                "id": theme_id or f"theme_{len(packs) + 1}",
                "stars": pack_stars,
                "fragments": [str(item.get("text") or "") for item in pack_stars],
            }
        )
        out.extend(pack_stars)
        if len(out) >= clean_limit:
            break
    return {
        "stars": out,
        "fragments": [str(item.get("text") or "") for item in out],
        "packs": packs,
        "count": len(out),
    }


def _session_row(session_key: str) -> dict:
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT * FROM spring_dream_sessions WHERE sleep_session_key=?",
            (str(session_key or "").strip(),),
        ).fetchone()
    if row is None:
        return {}
    return {
        "sleep_session_key": str(row["sleep_session_key"] or ""),
        "count": int(row["count"] or 0),
        "max_per_sleep": int(row["max_per_sleep"] or 0),
        "last_theme_id": str(row["last_theme_id"] or ""),
        "sleep_source": str(row["sleep_source"] or ""),
        "reserved_at": str(row["reserved_at"] or ""),
        "last_sent_at": str(row["last_sent_at"] or ""),
        "miss_count": int(row["miss_count"] or 0),
        "last_miss_at": str(row["last_miss_at"] or ""),
        "post_wakeup_pending": int(row["post_wakeup_pending"] or 0),
        "post_wakeup_sent_at": str(row["post_wakeup_sent_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def _recent_session_key_for_night(night_date: str) -> str:
    clean_night = str(night_date or "").strip()
    if not clean_night:
        return ""
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            """
            SELECT sleep_session_key
            FROM spring_dream_sessions
            WHERE sleep_session_key LIKE ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (f"{clean_night}|%",),
        ).fetchone()
    return str(row["sleep_session_key"] or "").strip() if row is not None else ""


def _as_beijing_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=BEIJING_TZ)
    return value.astimezone(BEIJING_TZ)


def _spring_dream_trigger_state() -> dict:
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT * FROM spring_dream_trigger_state WHERE id=?",
            (SPRING_DREAM_TRIGGER_STATE_ID,),
        ).fetchone()
    if row is None:
        return {}
    return {
        "miss_count": int(row["miss_count"] or 0),
        "last_attempt_at": str(row["last_attempt_at"] or ""),
        "last_triggered_at": str(row["last_triggered_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def _spring_dream_probability(
    base_chance: float,
    *,
    desire_level: int,
    is_sleeping: bool,
    miss_count: int,
) -> float:
    try:
        base = max(0.0, min(1.0, float(base_chance)))
    except Exception:
        base = SPRING_DREAM_PROBABILITY
    try:
        desire = max(0, min(5, int(desire_level or 0)))
    except Exception:
        desire = 0
    try:
        misses = max(0, int(miss_count or 0))
    except Exception:
        misses = 0
    threshold = (
        base
        + desire * SPRING_DREAM_DESIRE_PROBABILITY_STEP
        + (SPRING_DREAM_SLEEP_PROBABILITY_BONUS if is_sleeping else 0.0)
        + misses * SPRING_DREAM_PROBABILITY_STEP
    )
    return max(0.0, min(SPRING_DREAM_PROBABILITY_MAX, threshold))


def _spring_dream_cooldown_active(state: dict, now_dt: datetime) -> bool:
    last_triggered = parse_iso_to_beijing(str((state or {}).get("last_triggered_at") or ""))
    if last_triggered is None:
        return False
    return _as_beijing_datetime(now_dt) < last_triggered + timedelta(hours=SPRING_DREAM_COOLDOWN_HOURS)


def _record_spring_dream_miss(*, attempted_at: str) -> int:
    now_iso = str(attempted_at or "").strip() or now_beijing_iso()
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT miss_count FROM spring_dream_trigger_state WHERE id=?",
                (SPRING_DREAM_TRIGGER_STATE_ID,),
            ).fetchone()
            miss_count = int(row["miss_count"] or 0) if row is not None else 0
            next_count = miss_count + 1
            if row is None:
                conn.execute(
                    """
                    INSERT INTO spring_dream_trigger_state (
                        id, miss_count, last_attempt_at, last_triggered_at, updated_at
                    ) VALUES (?, ?, ?, '', ?)
                    """,
                    (SPRING_DREAM_TRIGGER_STATE_ID, next_count, now_iso, now_iso),
                )
            else:
                conn.execute(
                    """
                    UPDATE spring_dream_trigger_state
                    SET miss_count=?, last_attempt_at=?, updated_at=?
                    WHERE id=?
                    """,
                    (next_count, now_iso, now_iso, SPRING_DREAM_TRIGGER_STATE_ID),
                )
            conn.execute("COMMIT")
            return next_count
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _reserve_spring_dream_slot(
    *,
    session_key: str,
    sleep_source: str,
    max_per_sleep: int,
    rng: random.Random | None = None,
    theme_override: dict | None = None,
) -> dict | None:
    clean_key = str(session_key or "").strip()
    if not clean_key:
        return None
    limit = max(1, int(max_per_sleep or SPRING_DREAM_MAX_PER_SLEEP))
    now_iso = now_beijing_iso()
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _prune_old_sessions(conn, now_iso)
            row = conn.execute(
                "SELECT * FROM spring_dream_sessions WHERE sleep_session_key=?",
                (clean_key,),
            ).fetchone()
            count = int(row["count"] or 0) if row is not None else 0
            if count >= limit:
                conn.execute("ROLLBACK")
                return None
            previous_theme = str(row["last_theme_id"] or "") if row is not None else ""
            theme = theme_override if isinstance(theme_override, dict) and theme_override.get("fragments") else _choose_theme(previous_theme, rng=rng)
            theme_id = str(theme.get("id") or "").strip()
            count_after = count + 1
            if row is None:
                conn.execute(
                    """
                    INSERT INTO spring_dream_sessions (
                        sleep_session_key, count, max_per_sleep, last_theme_id,
                        sleep_source, reserved_at, last_sent_at,
                        miss_count, last_miss_at,
                        post_wakeup_pending, post_wakeup_sent_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, '', 0, '', 0, '', ?)
                    """,
                    (clean_key, count_after, limit, theme_id, str(sleep_source or "").strip(), now_iso, now_iso),
                )
            else:
                conn.execute(
                    """
                    UPDATE spring_dream_sessions
                    SET count=?, max_per_sleep=?, last_theme_id=?, sleep_source=?,
                        reserved_at=?, miss_count=0, updated_at=?
                    WHERE sleep_session_key=?
                    """,
                    (count_after, limit, theme_id, str(sleep_source or "").strip(), now_iso, now_iso, clean_key),
                )
            conn.execute("COMMIT")
            return {
                "count_before": count,
                "count_after": count_after,
                "theme": theme,
            }
        except Exception:
            conn.execute("ROLLBACK")
            raise


def release_spring_dream_slot(prepared: dict) -> bool:
    session_key = str((prepared or {}).get("sleep_session_key") or "").strip()
    if not session_key:
        return False
    now_iso = now_beijing_iso()
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT count FROM spring_dream_sessions WHERE sleep_session_key=?",
                (session_key,),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                return False
            count = max(0, int(row["count"] or 0) - 1)
            conn.execute(
                """
                UPDATE spring_dream_sessions
                SET count=?, updated_at=?
                WHERE sleep_session_key=?
                """,
                (count, now_iso, session_key),
            )
            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _choose_theme(previous_theme_id: str = "", rng: random.Random | None = None) -> dict:
    picker = rng or random
    pool = [item for item in _SPRING_DREAM_THEME_PACKS if item.get("id") != previous_theme_id]
    if not pool:
        pool = list(_SPRING_DREAM_THEME_PACKS)
    return picker.choice(pool)


def build_spring_dream_prompt(fragments: list[str]) -> str:
    lines = [
        "【春梦触发：潜意识的欲望解构】",
        "你正深陷在一场关于小玥的春梦里。梦境没有逻辑和礼貌的束缚，只有被拉长、放大的感官特写和最原始的本能占有。这几个散落的片段，只是你这场大梦里被截下来的镜头：",
        "",
    ]
    lines.extend(f" * {str(item).strip()}" for item in fragments if str(item).strip())
    lines.extend(
        [
            "",
            "顺着这些梦境碎片的边缘，用最直白露骨的语言把这场春梦彻底、细腻地铺展开。这几个镜头只是冰山一角，它们自然融进同一个梦里后，更浓稠、更失控的画面才刚刚开始在后面疯长。",
            "在梦里，你的掌控欲和把她彻底客体化的冲动根本没有阀门。放任欲望去撕扯，那些沉重的动作阻力、液体拉丝的特写、以及她被弄乱时本能的低喘和哭腔，全都在你潜意识的放大镜下无限延伸。",
            "继续往下做这场梦，直到梦境的最高潮把理智烧断。",
        ]
    )
    return "\n".join(lines).strip()


def maybe_prepare_spring_dream_wakeup(
    *,
    now_dt: datetime,
    chance: float = SPRING_DREAM_PROBABILITY,
    max_per_sleep: int = SPRING_DREAM_MAX_PER_SLEEP,
    roll: Callable[[], float] | None = None,
    rng: random.Random | None = None,
) -> Optional[dict]:
    try:
        from services.pixel_home import build_sleep_wakeup_state, get_du_body_trigger_state

        sleep_state = build_sleep_wakeup_state(now_dt)
    except Exception:
        sleep_state = {}
    try:
        body_state = get_du_body_trigger_state(now_dt)
    except Exception:
        body_state = {}

    now_local = _as_beijing_datetime(now_dt)
    is_sleeping = bool((sleep_state or {}).get("is_sleeping"))
    sleep_source = str((sleep_state or {}).get("source") or "").strip()
    night_date = str((sleep_state or {}).get("night_date") or "").strip() or now_local.strftime("%Y-%m-%d")
    session_key = str((sleep_state or {}).get("sleep_session_key") or "").strip()
    if not session_key:
        session_key = _recent_session_key_for_night(night_date) or f"{night_date}|awake"

    roller = roll or random.random
    trigger_state = _spring_dream_trigger_state()
    if _spring_dream_cooldown_active(trigger_state, now_local):
        return None
    miss_count = int((trigger_state or {}).get("miss_count") or 0)
    desire_level = max(0, min(5, int((body_state or {}).get("desire_level") or 0)))
    threshold = _spring_dream_probability(
        chance,
        desire_level=desire_level,
        is_sleeping=is_sleeping,
        miss_count=miss_count,
    )
    rolled = float(roller())
    if rolled >= threshold:
        next_miss_count = _record_spring_dream_miss(attempted_at=now_local.isoformat())
        logger.info(
            "春梦唤醒未命中 session=%s sleeping=%s desire=%s roll=%.4f threshold=%.4f miss_count=%s next_threshold=%.4f",
            session_key,
            is_sleeping,
            desire_level,
            rolled,
            threshold,
            next_miss_count,
            _spring_dream_probability(
                chance,
                desire_level=desire_level,
                is_sleeping=is_sleeping,
                miss_count=next_miss_count,
            ),
        )
        return None

    inspiration = get_spring_dream_inspiration()
    inspiration_fragments = [
        str(item).strip()
        for item in (inspiration.get("fragments") or [])
        if str(item).strip()
    ]
    theme_override = None
    if inspiration_fragments:
        theme_override = {
            "id": SPRING_DREAM_INSPIRATION_THEME_ID,
            "fragments": inspiration_fragments,
            "source": "miniapp_inspiration",
        }

    reserved = _reserve_spring_dream_slot(
        session_key=session_key,
        sleep_source=sleep_source,
        max_per_sleep=int(max_per_sleep or SPRING_DREAM_MAX_PER_SLEEP),
        rng=rng,
        theme_override=theme_override,
    )
    if not reserved:
        return None
    theme = reserved.get("theme") if isinstance(reserved.get("theme"), dict) else {}
    fragments = [str(item).strip() for item in (theme.get("fragments") or []) if str(item).strip()]
    return {
        "prompt": build_spring_dream_prompt(fragments),
        "theme_id": str(theme.get("id") or "").strip(),
        "fragments": fragments,
        "inspiration_source": "miniapp" if inspiration_fragments else "random",
        "sleep_session_key": session_key,
        "sleep_source": sleep_source,
        "is_sleeping": is_sleeping,
        "desire_level": desire_level,
        "roll": rolled,
        "threshold": threshold,
        "miss_count_before": miss_count,
        "count_before": int(reserved.get("count_before") or 0),
        "count_after": int(reserved.get("count_after") or 0),
        "max_per_sleep": int(max_per_sleep or SPRING_DREAM_MAX_PER_SLEEP),
        "reserved": True,
    }


def record_spring_dream_sent(prepared: dict, *, sent_at: str = "") -> bool:
    session_key = str((prepared or {}).get("sleep_session_key") or "").strip()
    if not session_key:
        return False
    now_iso = str(sent_at or "").strip() or now_beijing_iso()
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """
                UPDATE spring_dream_sessions
                SET last_sent_at=?, post_wakeup_pending=1, updated_at=?
                WHERE sleep_session_key=?
                """,
                (now_iso, now_iso, session_key),
            )
            conn.execute(
                """
                INSERT INTO spring_dream_trigger_state (
                    id, miss_count, last_attempt_at, last_triggered_at, updated_at
                ) VALUES (?, 0, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    miss_count=0,
                    last_attempt_at=excluded.last_attempt_at,
                    last_triggered_at=excluded.last_triggered_at,
                    updated_at=excluded.updated_at
                """,
                (SPRING_DREAM_TRIGGER_STATE_ID, now_iso, now_iso, now_iso),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return True


def _archive_id(sent_at: str) -> str:
    compact = "".join(ch for ch in str(sent_at or "") if ch.isdigit())[:14]
    if not compact:
        compact = "".join(ch for ch in now_beijing_iso() if ch.isdigit())[:14]
    return f"spring_{compact}_{uuid4().hex[:8]}"


def _safe_key_part(text: str, fallback: str = "unknown") -> str:
    clean = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(text or "").strip())
    clean = clean.strip("_")
    return clean[:96] or fallback


def _archive_summary(entry: dict) -> dict:
    content = str((entry or {}).get("content") or "").strip()
    return {
        "id": str((entry or {}).get("id") or ""),
        "window_id": str((entry or {}).get("window_id") or ""),
        "sleep_session_key": str((entry or {}).get("sleep_session_key") or ""),
        "theme_id": str((entry or {}).get("theme_id") or ""),
        "channel": str((entry or {}).get("channel") or ""),
        "sent_at": str((entry or {}).get("sent_at") or ""),
        "r2_key": str((entry or {}).get("r2_key") or ""),
        "preview": content[:160],
    }


def _write_archive_index(client, key: str, summary: dict, *, limit: int) -> None:
    from storage import r2_store

    existing = r2_store._read_json(client, key)
    if not isinstance(existing, dict):
        existing = {}
    items = existing.get("items") if isinstance(existing.get("items"), list) else []
    entry_id = str(summary.get("id") or "")
    kept = [item for item in items if isinstance(item, dict) and str(item.get("id") or "") != entry_id]
    kept.insert(0, summary)
    payload = {
        "schema_version": 1,
        "updated_at": now_beijing_iso(),
        "items": kept[: max(1, int(limit or 1))],
    }
    r2_store._write_json(client, key, payload)


def _write_spring_dream_archive_r2(entry: dict) -> str:
    from storage import r2_store

    client = r2_store._s3_client()
    if not client:
        return ""
    sent_at = str((entry or {}).get("sent_at") or "").strip()
    day = sent_at[:10] if len(sent_at) >= 10 else now_beijing_iso()[:10]
    entry_id = _safe_key_part(str((entry or {}).get("id") or ""), fallback=_archive_id(sent_at))
    key = f"{SPRING_DREAM_ARCHIVE_R2_PREFIX}/{day}/{entry_id}.json"
    payload = dict(entry or {})
    payload["r2_key"] = key
    r2_store._write_json(client, key, payload)
    summary = _archive_summary(payload)
    try:
        _write_archive_index(
            client,
            f"{SPRING_DREAM_ARCHIVE_R2_PREFIX}/{day}/index.json",
            summary,
            limit=24,
        )
        _write_archive_index(
            client,
            f"{SPRING_DREAM_ARCHIVE_R2_PREFIX}/recent.json",
            summary,
            limit=SPRING_DREAM_ARCHIVE_RECENT_LIMIT,
        )
    except Exception as e:
        logger.warning("春梦专用 R2 索引更新失败 key=%s error=%s", key, e)
    return key


def archive_spring_dream_body(
    *,
    window_id: str,
    target: str,
    channel: str,
    content: str,
    prompt: str = "",
    created_at: str = "",
    sent_at: str = "",
    meta: dict | None = None,
) -> dict:
    """Write a dedicated spring-dream archive without touching normal conversation archives."""
    text = str(content or "").strip()
    if not text:
        return {"ok": False, "error": "empty_content"}
    now_iso = now_beijing_iso()
    sent = str(sent_at or "").strip() or now_iso
    created = str(created_at or "").strip() or sent
    meta_payload = dict(meta or {}) if isinstance(meta, dict) else {}
    fragments = [
        str(item).strip()
        for item in (meta_payload.get("fragments") or [])
        if str(item).strip()
    ]
    entry_id = _archive_id(sent)
    entry = {
        "schema_version": 1,
        "id": entry_id,
        "window_id": str(window_id or "").strip(),
        "sleep_session_key": str(meta_payload.get("sleep_session_key") or "").strip(),
        "theme_id": str(meta_payload.get("theme_id") or "").strip(),
        "sleep_source": str(meta_payload.get("sleep_source") or "").strip(),
        "channel": str(channel or "").strip(),
        "target": str(target or "").strip(),
        "created_at": created,
        "sent_at": sent,
        "content": text,
        "prompt": str(prompt or "").strip(),
        "fragments": fragments,
        "meta": meta_payload,
        "r2_key": "",
        "updated_at": now_iso,
    }
    sqlite_ok = False
    r2_key = ""
    _ensure_schema()
    try:
        with runtime_sqlite.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO spring_dream_archives (
                    id, window_id, sleep_session_key, theme_id, sleep_source,
                    channel, target, created_at, sent_at, content, prompt,
                    fragments_json, meta_json, r2_key, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["id"],
                    entry["window_id"],
                    entry["sleep_session_key"],
                    entry["theme_id"],
                    entry["sleep_source"],
                    entry["channel"],
                    entry["target"],
                    entry["created_at"],
                    entry["sent_at"],
                    entry["content"],
                    entry["prompt"],
                    runtime_sqlite.json_dumps(entry["fragments"]),
                    runtime_sqlite.json_dumps(entry["meta"]),
                    "",
                    entry["updated_at"],
                ),
            )
        sqlite_ok = True
    except Exception as e:
        logger.warning("春梦专用 SQLite 存档失败 id=%s error=%s", entry_id, e)
    try:
        r2_key = _write_spring_dream_archive_r2(entry)
        if r2_key:
            entry["r2_key"] = r2_key
            if sqlite_ok:
                with runtime_sqlite.connect() as conn:
                    conn.execute(
                        "UPDATE spring_dream_archives SET r2_key=?, updated_at=? WHERE id=?",
                        (r2_key, now_beijing_iso(), entry_id),
                    )
    except Exception as e:
        logger.warning("春梦专用 R2 存档失败 id=%s error=%s", entry_id, e)
    return {
        "ok": bool(sqlite_ok or r2_key),
        "sqlite_ok": bool(sqlite_ok),
        "r2_ok": bool(r2_key),
        "id": entry_id,
        "r2_key": r2_key,
        "error": "" if (sqlite_ok or r2_key) else "archive_failed",
    }


def _archive_row_to_dict(row, *, include_content: bool = False) -> dict:
    if row is None:
        return {}
    content = str(row["content"] or "")
    item = {
        "id": str(row["id"] or ""),
        "window_id": str(row["window_id"] or ""),
        "sleep_session_key": str(row["sleep_session_key"] or ""),
        "theme_id": str(row["theme_id"] or ""),
        "sleep_source": str(row["sleep_source"] or ""),
        "channel": str(row["channel"] or ""),
        "target": str(row["target"] or ""),
        "created_at": str(row["created_at"] or ""),
        "sent_at": str(row["sent_at"] or ""),
        "preview": content[:180],
        "content_chars": len(content),
        "prompt": str(row["prompt"] or "") if include_content else "",
        "fragments": runtime_sqlite.json_loads(row["fragments_json"], []),
        "meta": runtime_sqlite.json_loads(row["meta_json"], {}) if include_content else {},
        "r2_key": str(row["r2_key"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }
    if include_content:
        item["content"] = content
    return item


def list_spring_dream_archives(limit: int = 50) -> list[dict]:
    _ensure_schema()
    n = max(1, min(200, int(limit or 50)))
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM spring_dream_archives
            ORDER BY sent_at DESC, updated_at DESC
            LIMIT ?
            """,
            (n,),
        ).fetchall()
    return [_archive_row_to_dict(row) for row in rows]


def get_spring_dream_archive(archive_id: str) -> dict:
    clean = str(archive_id or "").strip()
    if not clean:
        return {}
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT * FROM spring_dream_archives WHERE id=?",
            (clean,),
        ).fetchone()
    return _archive_row_to_dict(row, include_content=True)


def _strip_prompt_comment_lines(text: str) -> str:
    lines = []
    for raw in str(text or "").splitlines():
        line = str(raw or "")
        if line.lstrip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def load_post_spring_dream_wakeup_prompt() -> str:
    try:
        from services.prompt_manager import get_prompt_override_text

        text = get_prompt_override_text(POST_SPRING_DREAM_WAKEUP_SECTION_ID)
    except Exception:
        text = None
    if text is None:
        return ""
    return _strip_prompt_comment_lines(text)


def _clear_post_spring_dream_wakeup_pending(session_key: str, *, updated_at: str = "") -> bool:
    clean_key = str(session_key or "").strip()
    if not clean_key:
        return False
    now_iso = str(updated_at or "").strip() or now_beijing_iso()
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        conn.execute(
            """
            UPDATE spring_dream_sessions
            SET post_wakeup_pending=0, updated_at=?
            WHERE sleep_session_key=?
            """,
            (now_iso, clean_key),
        )
    return True


def _is_china_workday(target_date: date) -> bool:
    try:
        from chinese_calendar import is_workday

        return bool(is_workday(target_date))
    except Exception:
        return target_date.weekday() < 5


def _post_spring_dream_wakeup_window(now_dt: datetime) -> dict:
    now_local = _as_beijing_datetime(now_dt)
    if now_local.hour >= 22:
        target_date = now_local.date() + timedelta(days=1)
    elif now_local.hour < 11:
        target_date = now_local.date()
    else:
        return {"allowed": False, "is_workday": True, "cutoff_hour": 7}
    is_workday = _is_china_workday(target_date)
    cutoff_hour = 7 if is_workday else 11
    allowed = now_local.hour >= 22 or now_local.hour < cutoff_hour
    return {
        "allowed": allowed,
        "is_workday": is_workday,
        "cutoff_hour": cutoff_hour,
        "target_date": target_date.isoformat(),
    }


def _current_pending_post_spring_dream_session(
    *,
    current_session_key: str,
    now_dt: datetime,
) -> dict:
    clean_current_key = str(current_session_key or "").strip()
    now_local = _as_beijing_datetime(now_dt)
    cutoff = now_local - timedelta(hours=POST_SPRING_DREAM_WAKEUP_MAX_AGE_HOURS)
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        rows = conn.execute(
            """
            SELECT sleep_session_key, last_sent_at
            FROM spring_dream_sessions
            WHERE post_wakeup_pending > 0
            ORDER BY last_sent_at DESC, updated_at DESC
            """
        ).fetchall()
        current_key = ""
        stale_keys: list[str] = []
        for row in rows:
            session_key = str(row["sleep_session_key"] or "").strip()
            sent_at = parse_iso_to_beijing(str(row["last_sent_at"] or ""))
            is_current = bool(clean_current_key) and session_key == clean_current_key
            is_fresh = sent_at is not None and cutoff <= sent_at <= now_local
            if is_current and is_fresh and not current_key:
                current_key = session_key
            else:
                stale_keys.append(session_key)
        if stale_keys:
            conn.executemany(
                """
                UPDATE spring_dream_sessions
                SET post_wakeup_pending=0, updated_at=?
                WHERE sleep_session_key=?
                """,
                [(now_local.isoformat(), key) for key in stale_keys if key],
            )
            logger.info(
                "清理失效春梦后唤醒状态 current_session=%s stale_sessions=%s",
                clean_current_key or "none",
                ",".join(stale_keys),
            )
    return _session_row(current_key) if current_key else {}


def maybe_prepare_post_spring_dream_wakeup(
    *,
    now_dt: datetime,
    require_sleeping: bool = True,
    clear_on_empty_prompt: bool = True,
) -> Optional[dict]:
    window = _post_spring_dream_wakeup_window(now_dt)
    if not bool(window.get("allowed")):
        return None
    try:
        from services.pixel_home import build_sleep_wakeup_state

        sleep_state = build_sleep_wakeup_state(now_dt)
    except Exception:
        sleep_state = {}
    is_sleeping = bool((sleep_state or {}).get("is_sleeping"))
    current_session_key = str((sleep_state or {}).get("sleep_session_key") or "").strip()
    if require_sleeping and not is_sleeping:
        current_session_key = ""
    row = _current_pending_post_spring_dream_session(
        current_session_key=current_session_key,
        now_dt=now_dt,
    )
    if not row or int(row.get("post_wakeup_pending") or 0) <= 0:
        return None
    session_key = str(row.get("sleep_session_key") or "").strip()
    prompt = load_post_spring_dream_wakeup_prompt()
    if not prompt:
        if clear_on_empty_prompt:
            _clear_post_spring_dream_wakeup_pending(session_key)
        return None
    return {
        "prompt": prompt,
        "sleep_session_key": session_key,
        "sleep_source": str((sleep_state or {}).get("source") or row.get("sleep_source") or "").strip(),
        "last_spring_dream_sent_at": str(row.get("last_sent_at") or ""),
        "is_workday": bool(window.get("is_workday")),
        "cutoff_hour": int(window.get("cutoff_hour") or 0),
    }


def record_post_spring_dream_wakeup_sent(prepared: dict, *, sent_at: str = "") -> bool:
    session_key = str((prepared or {}).get("sleep_session_key") or "").strip()
    if not session_key:
        return False
    now_iso = str(sent_at or "").strip() or now_beijing_iso()
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        conn.execute(
            """
            UPDATE spring_dream_sessions
            SET post_wakeup_pending=0, post_wakeup_sent_at=?, updated_at=?
            WHERE sleep_session_key=?
            """,
            (now_iso, now_iso, session_key),
        )
    return True
