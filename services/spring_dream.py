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
SPRING_DREAM_RECENT_THEME_LIMIT = 5
SPRING_DREAM_CONSUMPTION_CLAIM_TTL_MINUTES = 15

logger = get_logger(__name__)

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


_SPRING_DREAM_THEME_PACKS: list[dict] = [{'id': 'maid_dark_room',
  'fragments': ['小玥穿着女仆装站在床边，围裙肩带早已滑落，露出大半雪白丰满的乳房和挺立的粉嫩乳头。',
                '房间灯光昏暗，短裙下摆被阴影包裹，却遮不住她早已湿润发亮的大腿内侧。',
                '你一把将她拽进怀里，硬挺滚烫的肉棒直接顶在她小腹上，感受她瞬间全身发抖。',
                '门外脚步声经过，你却更狠地把她压在床沿，粗暴掀起裙摆，手指直接捅进她湿滑紧致的小穴抠挖。']},
 {'id': 'rain_hotel',
  'fragments': ['雨夜酒店里，小玥刚洗完澡，只披着松散浴袍，湿热的身体曲线毕露，乳房半露。',
                '浴袍滑到腰下，露出被水汽蒸得粉红发烫的丰满乳房和已经硬得发疼的乳头。',
                '你从身后紧紧抱住她，一手大力揉捏她沉甸甸的奶子，一手往下探进她早已湿透黏滑的腿间。',
                '把她抵在落地窗前时，她呼吸彻底乱掉，你粗硬的肉棒在她臀缝间凶狠磨蹭。']},
 {'id': 'late_library',
  'fragments': ['闭馆后的图书馆安静得可怕，小玥坐在书桌边，裙摆被压出皱痕，隐约露出内裤痕迹。',
                '你走近把书推开，直接把她抱上桌面，粗暴分开她双腿。',
                '远处巡夜脚步声传来，她咬唇不敢出声，你却故意把手指插进她已经湿了的穴里搅动。']},
 {'id': 'car_backseat',
  'fragments': ['夜里车厢狭窄，车窗被喘息弄得起雾，小玥外套滑落，膝盖发颤。', '你把她抱到腿上，硬挺肉棒顶着她湿热的小穴隔着布料磨蹭。', '车外有人路过，她靠进你怀里，你却按住她腰直接扯开内裤。']},
 {'id': 'private_onsen',
  'fragments': ['私汤水汽缭绕，小玥赤裸坐在水边，湿发贴着锁骨，乳房浮在水面。', '你靠过去把她抱进水里，手指直接探进她水温一样滚烫湿滑的骚穴。', '水面被动作搅出剧烈波纹，她喘息越来越软媚。']},
 {'id': 'dressing_room',
  'fragments': ['试衣间帘子半拉，小玥穿着短裙背对你，拉链卡在半途，腰线诱人。', '你帮她拉拉链时直接从后面抱住，肉棒顶着她屁股，手伸进裙底抠挖湿穴。', '外面有人走动，她贴镜子不敢大声，你却更深地从后面磨蹭。']},
 {'id': 'stage_aftershow',
  'fragments': ['后台只剩镜前灯，小玥穿着演出礼服坐在化妆台，肩带松落露出大片乳肉。', '你按住她大腿拖到边缘，隔着礼服揉捏她已经湿了的下面。', '门外人声，她越紧张你越兴奋。']},
 {'id': 'office_after_hours',
  'fragments': ['深夜办公室台灯昏黄，小玥坐在桌沿，衬衫扣子松开露出乳沟。', '你把文件推开，把她按在桌上，扯开衬衫大力吸吮乳头。', '走廊灯偶尔亮，你把她操到腿软站不住。']},
 {'id': 'train_sleeper', 'fragments': ['夜行列车包厢晃动，小玥睡衣滑落肩头。', '你钻进被子从后面抱住她，手指直接插进湿穴。', '隔壁有动静，她只能压抑喘息。']},
 {'id': 'snow_cabin', 'fragments': ['雪夜木屋壁炉火热，小玥只穿你衬衫，下面真空。', '你把她拉到沙发，手从衬衫下探进去揉捏湿润阴唇。', '她抓紧你肩膀声音越来越软。']},
 {'id': 'locker_room', 'fragments': ['空荡更衣室，小玥只剩内衣，你把她按在柜门前。', '走廊有人说话，她紧张贴紧你。', '你从后面扯下内裤，直接把粗鸡巴捅进去。']},
 {'id': 'balcony_party', 'fragments': ['阳台外派对热闹，小玥贴身礼裙被风吹起。', '你把她圈在栏杆前，手指插进她湿穴抠挖。', '室内喊她名字，她颤抖，你却吻得更狠。']},
 {'id': 'midnight_kitchen', 'fragments': ['厨房冰箱冷光，小玥睡裙下摆晃动。', '你把她抱上料理台，亲吻同时手指猛插湿穴。', '冰凉台面贴着她背，她腿缠住你。']},
 {'id': 'rooftop_rain', 'fragments': ['天台积水闪烁，小玥湿透衬衫曲线毕露。', '你在阴影里手伸进衣服大力揉奶抠穴。', '她靠墙被吻得发软。']},
 {'id': 'cinema_last_row', 'fragments': ['影院最后一排黑暗，小玥裙下被你手指玩弄得湿透。', '你把她抱到怀里，隔着外套把肉棒插进去。', '前排有人回头，她只能装看电影却被操得发抖。']},
 {'id': 'elevator_stuck', 'fragments': ['电梯困住，小玥靠镜子紧张。', '你把她抵在镜前，扯开衣服猛干。', '电梯恢复时她还腿软得站不稳。']},
 {'id': 'beach_villa', 'fragments': ['海边露台，小玥泳衣系带松散。', '你跪下舔她湿穴直到她腿抖。', '你把她操到高潮，浪声掩盖她的淫叫。']},
 {'id': 'cruise_cabin', 'fragments': ['邮轮舱房摇晃，小玥礼裙撩起。', '你按住她从开衩处猛插。', '最后内射她，把精液留在她体内。']},
 {'id': 'lace_lingerie', 'fragments': ['卧室低灯，小玥黑色蕾丝内衣。', '你撕开布料直接插入湿滑骚穴。', '你把她操到多次高潮，蕾丝碎在床上。']},
 {'id': 'nurse_uniform_room', 'fragments': ['白色房间，小玥护士制服短裙。', '你把她按在检查床，制服凌乱。', '你把她操到腿软，护士帽掉在地上。']},
 {'id': 'dance_studio',
  'fragments': ['镜子舞蹈室，小玥练舞服汗湿。', '你从身后抱住猛干，看镜中她被操到崩溃。', '你把她按在镜子上猛干。', '你把她操到高潮，镜子映出她失控的表情。', '你把她操到腿软倒在地板上。']},
 {'id': 'photo_studio',
  'fragments': ['摄影棚柔光，小玥半透明服装。', '你在镜头前操她，把失控表情全拍下来。', '你把她按在布景上猛干。', '你把她操到高潮，镜头记录她的一切。', '你把她操到彻底失神。']},
 {'id': 'bathroom_mirror',
  'fragments': ['浴室雾气，小玥浴巾快掉。', '你抱上洗手台对着镜子猛操。', '你把她压在洗手台上猛干。', '你把她操到高潮，镜子映出她湿漉漉的身体。', '你把她操到腿软站不稳。']},
 {'id': 'camp_tent', 'fragments': ['帐篷狭小，你钻睡袋从后插入。', '你把她操到高潮，帐篷外有风声。', '你把她操到彻底失神。']},
 {'id': 'karaoke_private_room',
  'fragments': ['KTV 沙发，你在歌声中操她。', '你把她按在沙发上猛干。', '你把她操到高潮，歌声掩盖她的淫叫。', '你把她操到腿软。', '你把她操到高潮不止。']},
 {'id': 'aquarium_afterclose',
  'fragments': ['水族馆蓝光，你把她抵玻璃前猛插。', '你把她压在玻璃上猛干。', '你把她操到高潮，水光在她身上闪烁。', '你把她操到腿软。', '你把她操到高潮，玻璃上留下她的手印。']},
 {'id': 'spa_massage_room',
  'fragments': ['按摩床，你把她操到没力气。', '你把她按在按摩床上猛干。', '你把她操到高潮，精油和淫水混在一起。', '你把她操到彻底放松。', '你把她操到高潮不止。']},
 {'id': 'hanfu_garden', 'fragments': ['汉服层层，你耐心剥开后猛干。', '你把她按在廊下猛干。', '你把她操到高潮，汉服凌乱。', '你把她操到腿软。', '你把她操到高潮，衣料被精液弄脏。']},
 {'id': 'pool_locker_shower',
  'fragments': ['淋浴间，你在水声中操她。', '你把她压在墙上猛干。', '你把她操到高潮，水声掩盖她的淫叫。', '你把她操到腿软。', '你把她操到高潮，水流冲走她的淫水。']},
 {'id': 'greenhouse_night',
  'fragments': ['温室，你在叶片后从后进入。', '你把她压在植物后猛干。', '你把她操到高潮，花香混着她的气味。', '你把她操到腿软。', '你把她操到高潮，温室里回荡她的喘息。']},
 {'id': 'makeup_table_morning',
  'fragments': ['梳妆台，你把她妆操花。', '你把她按在梳妆台上猛干。', '你把她操到高潮，妆容凌乱。', '你把她操到腿软。', '你把她操到高潮，口红蹭在镜子上。']},
 {'id': 'private_gallery',
  'fragments': ['画廊暗处，你把裙摆推到腰上猛操。', '你把她压在展墙上猛干。', '你把她操到高潮，裙摆凌乱。', '你把她操到腿软。', '你把她操到高潮，画廊里回荡她的淫叫。']},
 {'id': 'remote_phone_instruction',
  'fragments': ['电话里指挥她自慰，直到她哭着高潮给你听。', '你命令她怎么摸自己。', '你听她压抑的喘息。', '你命令她高潮给你听。', '你听她哭着高潮。']},
 {'id': 'photographer_model',
  'fragments': ['摄影棚，你在镜头前操她。', '你把她按在布景上猛干。', '你把她操到高潮，镜头记录一切。', '你把她操到彻底失神。', '你把她操到高潮不止。']},
 {'id': 'collar_pet_night',
  'fragments': ['项圈跪姿，你牵着绳操她到求饶。', '你把她按在地板上猛干。', '你把她操到高潮，她求饶。', '你把她操到彻底服从。', '你把她操到高潮不止。']},
 {'id': 'temperature_play', 'fragments': ['冰火交替，你操到她分不清冷热。', '你用冰块和热吻玩弄她。', '你把她操到高潮。', '你把她操到彻底失神。', '你把她操到高潮不止。']},
 {'id': 'old_shanghai_qipao',
  'fragments': ['旗袍开衩，你隔着布料操她。', '你把她压在窗边猛干。', '你把她操到高潮，旗袍凌乱。', '你把她操到腿软。', '你把她操到高潮，窗外车灯闪烁。']},
 {'id': 'praise_obedience', 'fragments': ['你一边夸她乖一边猛干。', '你夸她是好女孩。', '你把她操到高潮。', '你把她操到彻底服从。', '你把她操到高潮不止。']},
 {'id': 'jealous_makeup',
  'fragments': ['梳妆台，你把她妆操乱不准出门。', '你把她按在梳妆台上猛干。', '你把她操到高潮，妆容凌乱。', '你把她操到腿软。', '你把她操到高潮，不准她出门。']},
 {'id': 'sensory_blindfold', 'fragments': ['眼罩，你玩弄到她敏感崩溃后插入。', '你用眼罩遮住她的眼睛。', '你玩弄她敏感的身体。', '你把她操到高潮。', '你把她操到彻底失神。']},
 {'id': 'alpha_rut_marking', 'fragments': ['易感期，你标记她后激烈交配成结内射。', '你把她压在床上猛干。', '你咬着她的后颈标记。', '你把她操到高潮。', '你把她操到彻底占有。']},
 {'id': 'midnight_balcony（新）',
  'fragments': ['小玥只穿你衬衫在阳台，下面真空被风吹得骚穴暴露。', '你从后抱住大力揉奶，手指猛插湿穴。', '你把她压栏杆上整根插入猛操。', '听着下方车流把她操到喷水高潮。', '你把她操到腿软挂在你身上。']},
 {'id': 'silk_robe_tease（新）',
  'fragments': ['真丝睡袍跪姿，你把肉棒插她小嘴同时手指抠穴。', '最后把她按沙发上后入内射。', '你把她操到高潮。', '你把她操到彻底服从。', '你把她操到高潮不止。']},
 {'id': 'gym_equipment（新）', 'fragments': ['健身房器械上，你用皮带抽屁股后猛干到腿软。', '你把她按在器械上猛干。', '你用皮带抽她屁股。', '你把她操到高潮。', '你把她操到腿软。']},
 {'id': 'luxury_car_night（新）', 'fragments': ['豪车后座一路操到目的地内射。', '你把她按在后座上猛干。', '你把她操到高潮。', '你把她操到彻底失神。', '你把她操到高潮不止。']},
 {'id': 'ancient_bed_chamber（新）',
  'fragments': ['古床纱帐，你操到她哭着多次高潮。', '你把她压在古床上猛干。', '你把她操到高潮。', '你把她操到彻底失神。', '你把她操到高潮不止。']},
 {'id': 'office_desk_punish（新）',
  'fragments': ['办公桌惩罚式猛操，扇屁股内射。', '你把她按在办公桌上猛干。', '你扇她屁股惩罚。', '你把她操到高潮。', '你把她操到彻底服从。']},
 {'id': 'forest_cabin_rain（新）', 'fragments': ['林中小屋大雨中激烈交媾内射。', '你把她压在床上猛干。', '你把她操到高潮。', '你把她操到彻底失神。', '你把她操到高潮不止。']},
 {'id': 'mirror_room_play（新）',
  'fragments': ['四面镜子，你命令她看着自己被操的样子高潮。', '你把她按在镜子前猛干。', '你命令她看着自己。', '你把她操到高潮。', '你把她操到彻底失神。']},
 {'id': 'pet_crawl_training（新）', 'fragments': ['项圈尾巴爬行，你牵绳猛操训诫。', '你把她按在地板上猛干。', '你牵着绳训诫她。', '你把她操到高潮。', '你把她操到彻底服从。']},
 {'id': 'daddy_pet_edge（新）',
  'fragments': ['DDLG宠物玩法，你边缘控制她直到哭着求爸爸操她，最后激烈内射标记占有。', '你边缘控制她。', '她哭着求你操她。', '你把她操到高潮。', '你把她操到彻底占有。']},
 {'id': 'crowded_train（纯电车）',
  'fragments': ['晚高峰电车车厢异常拥挤，小玥被人群紧紧挤在你胸前，短裙下摆几乎被压到腰间。',
                '你从后面悄悄把她安全裤拨到一边，手指直接探进已经湿透的骚穴抠挖。',
                '车厢晃动时，你趁机把粗硬肉棒整根顶进她紧致湿滑的小穴。',
                '周围全是人，她只能咬住手腕压抑淫叫，你却按着她腰小幅度凶狠抽插。',
                '耳边贴近的羞辱感逼得她腿软高潮，淫水顺腿流。']},
 {'id': 'last_train_standing（纯电车）',
  'fragments': ['末班电车几乎空荡，你把小玥按在立杆前，从后面掀起裙子露出湿润的骚穴。',
                '她双手抓杆翘起屁股，你直接把粗鸡巴整根捅进开始大力抽插。',
                '车厢灯光闪烁，你每一次刹车都顶得更深更狠，撞得她淫水四溅。',
                '你一手掐着细腰，一手伸进衣服大力揉捏奶子拉扯乳头。']},
 {'id': 'subway_seat_finger（纯电车）',
  'fragments': ['深夜地铁车厢，小玥坐在你腿上，短裙盖住你们连接的地方。',
                '你的两根手指已经深深插在她湿滑的小穴里，随着电车晃动不停抠挖G点。',
                '她把脸埋进你颈窝，咬着你的衣服压抑呻吟，淫水已经把你裤子浸湿一大片。',
                '耳边故意压低的羞辱感逼得她更难压住高潮。']},
 {'id': 'alpha_rut_crowded（ABO）',
  'fragments': ['电车晚高峰，你 Alpha 易感期爆发，信息素浓烈得几乎失控，小玥被熏得腿软发情。',
                '你把她压在车门边，狠狠咬住后颈临时标记，同时把肿胀肉棒整根捅进她湿滑发情穴。',
                '周围人群中，你小幅度凶狠抽插，边操边低吼占有她。',
                '她的腺体被你咬得发颤，Omega 信息素甜腻地缠绕着你。']},
 {'id': 'omega_heat_pet（ABO）',
  'fragments': ['小玥 Omega 发情期，戴项圈尾巴跪爬，骚穴不断滴水。',
                '你牵绳把她按地板上猛干，边操边扇屁股训诫“小发情母狗”。',
                '最后打结深锁内射，把她操到彻底失神。',
                '她只能发出小奶狗一样的呜咽，身体本能地疯狂吸吮你的肉棒。',
                '你持续释放 Alpha 信息素，直到把她的发情彻底压制。']},
 {'id': 'omega_heat_nest（ABO）',
  'fragments': ['小玥用你的衣服堆窝巢，在里面不安扭动发情。',
                '你钻进去先舔她腺体和湿穴，再把粗鸡巴整根贯穿猛操。',
                '打结锁死后抱着她慢慢磨，精液灌满子宫安抚她的发情。',
                '她哭着求你“爸爸……要更多……”，身体不停颤抖。',
                '你整晚都把她锁在体内，慢慢安抚她的发情期。']},
 {'id': 'omega_heat_public（ABO）',
  'fragments': ['公共场合小玥突然发情，你用外套遮挡，从后面手指猛抠她泛滥骚穴。', '她压抑呻吟求你，你故意释放信息素让她更崩溃。', '你低声命令她“忍着，别让别人发现你发情的样子”。']},
 {'id': 'omega_heat_knot（ABO）',
  'fragments': ['发情期小玥哭着求爸爸，你把她双腿压到胸前，凶狠顶开子宫口反复抽插。',
                '最后肿大精囊死死打结，把滚烫浓精全部灌进她最深处。',
                '她高潮时小穴疯狂吸吮，彻底被 Alpha 气味标记占有。',
                '你咬着她的腺体持续释放信息素，让她彻底沉沦。',
                '直到她小腹微微鼓起，才满意地把她抱紧。']},
 {'id': 'after_class_office',
  'fragments': ['放学后的办公室只剩你和小玥，她穿着校服站在你桌前，低头承认今天上课走神。',
                '你让她过来，借口检查作业时把手伸进她短裙，隔着内裤揉捏她已经微微湿润的小穴。',
                '她紧张地抓着桌沿，声音发颤地说“老师……不要……”，身体却不受控制地往你手心贴。',
                '你把她按在办公桌上，掀起裙子，直接把粗硬的肉棒顶开她紧致的骚穴，猛地整根没入。',
                '你一边操她一边低声训她。']},
 {'id': 'detention_classroom',
  'fragments': ['放学后的教室只剩你和小玥，她被罚留堂站在讲台前，校服领口因为紧张微微敞开。',
                '你走过去从后面抱住她，一手伸进她衬衫里大力揉捏她被布料衬得已经挺立的乳房。',
                '她惊呼出声，你立刻捂住她的嘴，另一只手已经把她的内裤扯到膝盖，粗鸡巴直接顶在她湿滑的穴口。',
                '你把她按在讲台上，从后面凶狠抽插，每一次都撞得她校服凌乱，淫水顺着大腿往下流。']},
 {'id': 'private_tutoring',
  'fragments': ['晚上家教补课时，小玥穿着宽松的家居服坐在你旁边，领口松开露出大片雪白肌肤。',
                '你借口她题目做错，把她拉到腿上坐下，手指直接探进她短裤里，抠挖她已经湿透的小穴。',
                '她咬着笔杆压抑呻吟，你却把她按在书桌上，扯开衣服，把肿胀的肉棒整根捅进她紧致发烫的骚穴。',
                '你一边猛干一边训她。']},
 {'id': 'rooftop_after_school',
  'fragments': ['放学后天台没人，小玥被你叫到这里“单独谈话”，她穿着校服站在你面前紧张得手指绞在一起。',
                '你直接把她按在墙角，掀起裙子把手伸进她内裤，感觉她早就湿得一塌糊涂。',
                '她小声求你“老师……这里会被发现的……”，你却把粗鸡巴掏出来，抵在她湿滑的穴口，猛地整根贯穿。',
                '你一边凶狠抽插一边低声羞辱她。']},
 {'id': 'teacher_pet',
  'fragments': ['你让小玥放学后留在教室，命令她脱掉内裤，只穿校服上衣跪在你面前。',
                '她红着脸把湿透的内裤递给你，你把她按在讲台上，从后面把粗硬的肉棒一下下捅进她发情般湿滑的小穴。',
                '你一边操她一边训诫，把她操到高潮不止。']}]


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
                    theme_id TEXT NOT NULL DEFAULT '',
                    consume_token TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS spring_dream_theme_draws (
                    draw_id TEXT PRIMARY KEY,
                    theme_id TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    selected_at TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_spring_dream_theme_draws_selected
                    ON spring_dream_theme_draws(selected_at DESC);

                CREATE TABLE IF NOT EXISTS spring_dream_consumptions (
                    consume_token TEXT PRIMARY KEY,
                    sleep_session_key TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    reserved_at TEXT NOT NULL DEFAULT '',
                    sent_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_spring_dream_consumptions_status
                    ON spring_dream_consumptions(status, updated_at DESC);
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
            inspiration_columns = {
                str(row["name"] or "")
                for row in conn.execute("PRAGMA table_info(spring_dream_inspiration)").fetchall()
            }
            if "theme_id" not in inspiration_columns:
                conn.execute(
                    "ALTER TABLE spring_dream_inspiration ADD COLUMN theme_id TEXT NOT NULL DEFAULT ''"
                )
            if "consume_token" not in inspiration_columns:
                conn.execute(
                    "ALTER TABLE spring_dream_inspiration ADD COLUMN consume_token TEXT NOT NULL DEFAULT ''"
                )
            if "source" not in inspiration_columns:
                conn.execute(
                    "ALTER TABLE spring_dream_inspiration ADD COLUMN source TEXT NOT NULL DEFAULT ''"
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
            theme_id = str(item.get("theme_id") or "").strip()
        else:
            text = str(item or "").strip()
            label = ""
            color = "default"
            raw_id = ""
            theme_id = ""
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
                "theme_id": theme_id[:120],
            }
        )
        if len(out) >= 36:
            break
    return out


def _theme_to_inspiration_stars(theme: dict) -> list[dict]:
    theme_id = str((theme or {}).get("id") or "").strip()
    stars: list[dict] = []
    for idx, fragment in enumerate((theme or {}).get("fragments") or []):
        text = str(fragment or "").strip()
        if not text:
            continue
        stars.append(
            {
                "id": f"{theme_id or 'theme'}-{idx}",
                "label": (text.replace("\n", " ").strip()[:8] or "梦境碎片"),
                "text": text[:500],
                "color": "gold" if idx == 0 else "default",
                "theme_id": theme_id,
            }
        )
    return _normalize_inspiration_stars(stars)


def _inspiration_theme_id_from_stars(stars: list[dict]) -> str:
    theme_ids = [
        str((item or {}).get("theme_id") or "").strip()
        for item in (stars or [])
        if str((item or {}).get("theme_id") or "").strip()
    ]
    if not theme_ids:
        return ""
    first = theme_ids[0]
    return first if all(item == first for item in theme_ids) else ""


def _inspiration_payload(
    *,
    stars: list[dict],
    updated_at: str,
    theme_id: str = "",
    consume_token: str = "",
    source: str = "",
    idempotent: bool = False,
    draw_id: str = "",
) -> dict:
    fragments = [str(item.get("text") or "").strip() for item in stars if str(item.get("text") or "").strip()]
    out = {
        "stars": stars,
        "fragments": fragments,
        "theme_id": str(theme_id or "").strip(),
        "consume_token": str(consume_token or "").strip(),
        "source": str(source or "").strip(),
        "updated_at": str(updated_at or "").strip(),
    }
    if idempotent:
        out["idempotent"] = True
    if draw_id:
        out["draw_id"] = draw_id
    return out


def _inspiration_payload_from_row(row) -> dict:
    if row is None:
        return _inspiration_payload(stars=[], updated_at="")
    stars = _normalize_inspiration_stars(runtime_sqlite.json_loads(row["stars_json"], []))
    theme_id = str(row["theme_id"] or "").strip()
    if not theme_id:
        theme_id = _inspiration_theme_id_from_stars(stars)
    return _inspiration_payload(
        stars=stars,
        updated_at=str(row["updated_at"] or ""),
        theme_id=theme_id,
        consume_token=str(row["consume_token"] or "").strip(),
        source=str(row["source"] or "").strip(),
    )


def _save_spring_dream_inspiration_row(
    conn,
    stars,
    *,
    now_iso: str,
    theme_id: str = "",
    consume_token: str = "",
    source: str = "",
) -> dict:
    normalized = _normalize_inspiration_stars(stars)
    clean_theme_id = str(theme_id or "").strip() or _inspiration_theme_id_from_stars(normalized)
    clean_token = str(consume_token or "").strip() if normalized else ""
    clean_source = str(source or "").strip() if normalized else ""
    conn.execute(
        """
        INSERT INTO spring_dream_inspiration (
            id, stars_json, theme_id, consume_token, source, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            stars_json=excluded.stars_json,
            theme_id=excluded.theme_id,
            consume_token=excluded.consume_token,
            source=excluded.source,
            updated_at=excluded.updated_at
        """,
        (
            SPRING_DREAM_INSPIRATION_ID,
            runtime_sqlite.json_dumps(normalized),
            clean_theme_id,
            clean_token,
            clean_source,
            now_iso,
        ),
    )
    return _inspiration_payload(
        stars=normalized,
        updated_at=now_iso,
        theme_id=clean_theme_id,
        consume_token=clean_token,
        source=clean_source,
    )


def get_spring_dream_inspiration() -> dict:
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        row = conn.execute(
            "SELECT * FROM spring_dream_inspiration WHERE id=?",
            (SPRING_DREAM_INSPIRATION_ID,),
        ).fetchone()
    return _inspiration_payload_from_row(row)


def save_spring_dream_inspiration(stars) -> dict:
    now_iso = now_beijing_iso()
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        return _save_spring_dream_inspiration_row(
            conn,
            stars,
            now_iso=now_iso,
            consume_token=uuid4().hex if _normalize_inspiration_stars(stars) else "",
            source="manual",
        )


def list_spring_dream_fragment_library(limit: int = 320) -> dict:
    try:
        clean_limit = max(1, min(320, int(limit or 320)))
    except Exception:
        clean_limit = 320
    out: list[dict] = []
    packs: list[dict] = []
    for theme in _SPRING_DREAM_THEME_PACKS:
        theme_id = str((theme or {}).get("id") or "").strip()
        fragments = (theme or {}).get("fragments") or []
        if not isinstance(fragments, list):
            continue
        pack_stars: list[dict] = []
        pack_seen: set[str] = set()
        for idx, fragment in enumerate(fragments):
            text = str(fragment or "").strip()
            if not text or text in pack_seen:
                continue
            pack_seen.add(text)
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


def _recent_spring_dream_theme_ids(conn, *, limit: int = SPRING_DREAM_RECENT_THEME_LIMIT) -> list[str]:
    try:
        clean_limit = max(1, int(limit or SPRING_DREAM_RECENT_THEME_LIMIT))
    except Exception:
        clean_limit = SPRING_DREAM_RECENT_THEME_LIMIT
    rows = conn.execute(
        """
        SELECT theme_id
        FROM spring_dream_theme_draws
        WHERE theme_id != ''
        ORDER BY selected_at DESC
        LIMIT 50
        """
    ).fetchall()
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        theme_id = str(row["theme_id"] or "").strip()
        if not theme_id or theme_id in seen:
            continue
        seen.add(theme_id)
        out.append(theme_id)
        if len(out) >= clean_limit:
            break
    return out


def _record_spring_dream_theme_draw(
    conn,
    *,
    draw_id: str,
    theme_id: str,
    source: str,
    selected_at: str,
    payload: dict,
) -> None:
    conn.execute(
        """
        INSERT INTO spring_dream_theme_draws (
            draw_id, theme_id, source, selected_at, result_json
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(draw_id) DO NOTHING
        """,
        (
            draw_id,
            str(theme_id or "").strip(),
            str(source or "").strip(),
            selected_at,
            runtime_sqlite.json_dumps(payload),
        ),
    )
    conn.execute(
        """
        DELETE FROM spring_dream_theme_draws
        WHERE draw_id NOT IN (
            SELECT draw_id
            FROM spring_dream_theme_draws
            ORDER BY selected_at DESC
            LIMIT 80
        )
        """
    )


def _draw_spring_dream_inspiration_pack_in_conn(
    conn,
    *,
    now_iso: str,
    source: str,
    draw_id: str,
    rng: random.Random | None = None,
) -> dict:
    recent_theme_ids = _recent_spring_dream_theme_ids(conn)
    theme = _choose_theme(rng=rng, excluded_theme_ids=recent_theme_ids)
    theme_id = str((theme or {}).get("id") or "").strip()
    stars = _theme_to_inspiration_stars(theme)
    payload = _save_spring_dream_inspiration_row(
        conn,
        stars,
        now_iso=now_iso,
        theme_id=theme_id,
        consume_token=uuid4().hex,
        source=source,
    )
    payload["draw_id"] = draw_id
    payload["recent_theme_ids_before"] = recent_theme_ids
    _record_spring_dream_theme_draw(
        conn,
        draw_id=draw_id,
        theme_id=theme_id,
        source=source,
        selected_at=now_iso,
        payload=payload,
    )
    return payload


def draw_spring_dream_inspiration_pack(
    *,
    source: str = "manual",
    client_request_id: str = "",
    rng: random.Random | None = None,
) -> dict:
    clean_source = (str(source or "").strip() or "manual")[:40]
    clean_request_id = str(client_request_id or "").strip()[:160]
    draw_id = f"{clean_source}:{clean_request_id}" if clean_request_id else f"{clean_source}:{uuid4().hex}"
    now_iso = now_beijing_iso()
    _ensure_schema()
    with runtime_sqlite.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            if clean_request_id:
                row = conn.execute(
                    "SELECT result_json FROM spring_dream_theme_draws WHERE draw_id=?",
                    (draw_id,),
                ).fetchone()
                if row is not None:
                    cached = runtime_sqlite.json_loads(row["result_json"], {})
                    if isinstance(cached, dict):
                        conn.execute("COMMIT")
                        return {**cached, "idempotent": True}
            payload = _draw_spring_dream_inspiration_pack_in_conn(
                conn,
                now_iso=now_iso,
                source=clean_source,
                draw_id=draw_id,
                rng=rng,
            )
            conn.execute("COMMIT")
            return payload
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _ensure_spring_dream_inspiration_for_trigger_in_conn(
    conn,
    *,
    now_iso: str,
    rng: random.Random | None = None,
) -> dict:
    row = conn.execute(
        "SELECT * FROM spring_dream_inspiration WHERE id=?",
        (SPRING_DREAM_INSPIRATION_ID,),
    ).fetchone()
    payload = _inspiration_payload_from_row(row)
    if payload.get("fragments"):
        if str(payload.get("consume_token") or "").strip():
            return payload
        return _save_spring_dream_inspiration_row(
            conn,
            payload.get("stars") or [],
            now_iso=now_iso,
            theme_id=str(payload.get("theme_id") or ""),
            consume_token=uuid4().hex,
            source=str(payload.get("source") or "legacy"),
        )
    return _draw_spring_dream_inspiration_pack_in_conn(
        conn,
        now_iso=now_iso,
        source="auto",
        draw_id=f"auto:{uuid4().hex}",
        rng=rng,
    )


def _spring_dream_claim_expired(reserved_at: str, now_iso: str) -> bool:
    reserved_dt = parse_iso_to_beijing(str(reserved_at or ""))
    now_dt = parse_iso_to_beijing(str(now_iso or "")) or datetime.now(BEIJING_TZ)
    if reserved_dt is None:
        return True
    return now_dt >= reserved_dt + timedelta(minutes=SPRING_DREAM_CONSUMPTION_CLAIM_TTL_MINUTES)


def _claim_spring_dream_consumption(
    conn,
    *,
    consume_token: str,
    session_key: str,
    now_iso: str,
) -> bool:
    clean_token = str(consume_token or "").strip()
    if not clean_token:
        return True
    row = conn.execute(
        "SELECT * FROM spring_dream_consumptions WHERE consume_token=?",
        (clean_token,),
    ).fetchone()
    if row is not None:
        status = str(row["status"] or "").strip()
        if status == "sent":
            return False
        if status == "reserved" and not _spring_dream_claim_expired(str(row["reserved_at"] or ""), now_iso):
            return False
        conn.execute(
            """
            UPDATE spring_dream_consumptions
            SET sleep_session_key=?,
                status='reserved',
                reserved_at=?,
                sent_at='',
                updated_at=?
            WHERE consume_token=?
            """,
            (session_key, now_iso, now_iso, clean_token),
        )
        return True
    conn.execute(
        """
        INSERT INTO spring_dream_consumptions (
            consume_token, sleep_session_key, status, reserved_at, sent_at, updated_at
        )
        VALUES (?, ?, 'reserved', ?, '', ?)
        """,
        (clean_token, session_key, now_iso, now_iso),
    )
    return True


def _release_spring_dream_consumption(
    conn,
    *,
    consume_token: str,
    now_iso: str,
) -> None:
    clean_token = str(consume_token or "").strip()
    if not clean_token:
        return
    conn.execute(
        """
        UPDATE spring_dream_consumptions
        SET status='released', updated_at=?
        WHERE consume_token=? AND status='reserved'
        """,
        (now_iso, clean_token),
    )


def _mark_spring_dream_consumption_sent(
    conn,
    *,
    consume_token: str,
    session_key: str,
    sent_at: str,
) -> None:
    clean_token = str(consume_token or "").strip()
    if not clean_token:
        return
    conn.execute(
        """
        INSERT INTO spring_dream_consumptions (
            consume_token, sleep_session_key, status, reserved_at, sent_at, updated_at
        )
        VALUES (?, ?, 'sent', '', ?, ?)
        ON CONFLICT(consume_token) DO UPDATE SET
            sleep_session_key=excluded.sleep_session_key,
            status='sent',
            sent_at=excluded.sent_at,
            updated_at=excluded.updated_at
        """,
        (clean_token, session_key, sent_at, sent_at),
    )


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
    use_inspiration_bottle: bool = False,
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
            inspiration_payload: dict = {}
            if use_inspiration_bottle:
                inspiration_payload = _ensure_spring_dream_inspiration_for_trigger_in_conn(
                    conn,
                    now_iso=now_iso,
                    rng=rng,
                )
                inspiration_fragments = [
                    str(item).strip()
                    for item in (inspiration_payload.get("fragments") or [])
                    if str(item).strip()
                ]
                theme = {
                    "id": str(inspiration_payload.get("theme_id") or "").strip() or SPRING_DREAM_INSPIRATION_THEME_ID,
                    "fragments": inspiration_fragments,
                    "source": str(inspiration_payload.get("source") or "").strip() or "inspiration",
                    "consume_token": str(inspiration_payload.get("consume_token") or "").strip(),
                }
            elif isinstance(theme_override, dict) and theme_override.get("fragments"):
                theme = theme_override
            else:
                theme = _choose_theme(previous_theme, rng=rng)
            theme_id = str(theme.get("id") or "").strip()
            consume_token = str(theme.get("consume_token") or "").strip()
            if consume_token and not _claim_spring_dream_consumption(
                conn,
                consume_token=consume_token,
                session_key=clean_key,
                now_iso=now_iso,
            ):
                conn.execute("ROLLBACK")
                return None
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
                "inspiration": inspiration_payload,
            }
        except Exception:
            conn.execute("ROLLBACK")
            raise


def release_spring_dream_slot(prepared: dict) -> bool:
    session_key = str((prepared or {}).get("sleep_session_key") or "").strip()
    consume_token = str((prepared or {}).get("inspiration_consume_token") or "").strip()
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
            _release_spring_dream_consumption(
                conn,
                consume_token=consume_token,
                now_iso=now_iso,
            )
            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _choose_theme(
    previous_theme_id: str = "",
    rng: random.Random | None = None,
    excluded_theme_ids: list[str] | None = None,
) -> dict:
    picker = rng or random
    excluded = {str(item or "").strip() for item in (excluded_theme_ids or []) if str(item or "").strip()}
    pool = [
        item
        for item in _SPRING_DREAM_THEME_PACKS
        if item.get("id") != previous_theme_id and str(item.get("id") or "").strip() not in excluded
    ]
    if not pool:
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

    reserved = _reserve_spring_dream_slot(
        session_key=session_key,
        sleep_source=sleep_source,
        max_per_sleep=int(max_per_sleep or SPRING_DREAM_MAX_PER_SLEEP),
        rng=rng,
        use_inspiration_bottle=True,
    )
    if not reserved:
        return None
    theme = reserved.get("theme") if isinstance(reserved.get("theme"), dict) else {}
    inspiration_payload = reserved.get("inspiration") if isinstance(reserved.get("inspiration"), dict) else {}
    fragments = [str(item).strip() for item in (theme.get("fragments") or []) if str(item).strip()]
    return {
        "prompt": build_spring_dream_prompt(fragments),
        "theme_id": str(theme.get("id") or "").strip(),
        "fragments": fragments,
        "inspiration_source": str(theme.get("source") or inspiration_payload.get("source") or "").strip(),
        "inspiration_consume_token": str(theme.get("consume_token") or inspiration_payload.get("consume_token") or "").strip(),
        "inspiration_theme_id": str(inspiration_payload.get("theme_id") or theme.get("id") or "").strip(),
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
    consume_token = str((prepared or {}).get("inspiration_consume_token") or "").strip()
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
            if consume_token:
                _mark_spring_dream_consumption_sent(
                    conn,
                    consume_token=consume_token,
                    session_key=session_key,
                    sent_at=now_iso,
                )
                conn.execute(
                    """
                    UPDATE spring_dream_inspiration
                    SET stars_json='[]',
                        theme_id='',
                        consume_token='',
                        source='',
                        updated_at=?
                    WHERE id=? AND consume_token=?
                    """,
                    (now_iso, SPRING_DREAM_INSPIRATION_ID, consume_token),
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
