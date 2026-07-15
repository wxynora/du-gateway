from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta
from typing import Any

from services.hidden_blocks import HiddenBlockParser
from services.pixel_home_garden import build_garden_state, record_garden_actions
from services.pixel_home_weather import build_virtual_home_weather
from storage import r2_store
from storage.pixel_home_store import get_pixel_home_state, save_pixel_home_state
from utils.log import get_logger
from utils.time_aware import now_beijing_iso, parse_iso_to_beijing

logger = get_logger(__name__)

PIXEL_HOME_MARKER_START = "<<<PIXEL_HOME>>>"
PIXEL_HOME_MARKER_END = "<<<END_PIXEL_HOME>>>"
PIXEL_HOME_SHORT_MARKER = "[du:home spot=study activity=写日记 desire=35]"
_PIXEL_HOME_BLOCK = HiddenBlockParser.for_markers(
    "PIXEL_HOME",
    PIXEL_HOME_MARKER_START,
    PIXEL_HOME_MARKER_END,
    short_markers=("du:home", "du:pixel"),
)
_PIXEL_HOME_LOOSE_ALIASES = {
    "spot": ("spot",),
    "location": ("spot",),
    "room": ("spot",),
    "activity": ("activity",),
    "doing": ("activity",),
    "action": ("activity",),
    "desire": ("du_body_state", "desire_value"),
    "desire_value": ("du_body_state", "desire_value"),
    "want_value": ("du_body_state", "desire_value"),
    "stamina": ("du_body_state", "stamina_value"),
    "stamina_value": ("du_body_state", "stamina_value"),
    "sensitivity": ("du_body_state", "sensitivity_value"),
    "sensitivity_value": ("du_body_state", "sensitivity_value"),
    "possessiveness": ("du_body_state", "possessiveness_value"),
    "possessiveness_value": ("du_body_state", "possessiveness_value"),
    "mischief": ("du_body_state", "mischief_value"),
    "mischief_value": ("du_body_state", "mischief_value"),
    "toy": ("du_body_state", "toy"),
    "toy_type": ("du_body_state", "toy_type"),
    "position": ("du_body_state", "position"),
    "body_position": ("du_body_state", "body_position"),
    "state": ("du_body_state", "state"),
    "intensity": ("du_body_state", "intensity"),
    "level": ("du_body_state", "level"),
    "位置": ("spot",),
    "房间": ("spot",),
    "地点": ("spot",),
    "动作": ("activity",),
    "活动": ("activity",),
    "想做指数": ("du_body_state", "desire_value"),
    "体力": ("du_body_state", "stamina_value"),
    "敏感度": ("du_body_state", "sensitivity_value"),
    "占有欲": ("du_body_state", "possessiveness_value"),
    "坏心值": ("du_body_state", "mischief_value"),
    "欺负欲": ("du_body_state", "mischief_value"),
    "捣蛋值": ("du_body_state", "mischief_value"),
    "调皮值": ("du_body_state", "mischief_value"),
    "使坏心": ("du_body_state", "mischief_value"),
}
_PIXEL_HOME_LOOSE_KEY_RE = re.compile(
    r"("
    + "|".join(re.escape(key) for key in sorted(_PIXEL_HOME_LOOSE_ALIASES, key=len, reverse=True))
    + r")\s*[:=：]\s*",
    flags=re.IGNORECASE,
)

PIXEL_HOME_DAY_START_HOUR = 7
PIXEL_HOME_NIGHT_START_HOUR = 18
PIXEL_HOME_SLEEP_SCREEN_OFF_MINUTES = 45
PIXEL_HOME_SCREEN_LOOKBACK_MINUTES = 12 * 60
PIXEL_HOME_AWAKE_SCREEN_LOOKBACK_MINUTES = 30

SPOT_LABELS: dict[str, str] = {
    "bed": "卧室",
    "bath": "浴室",
    "study": "书房",
    "sofa": "客厅沙发",
    "kitchen": "厨房",
    "garden": "花园",
    "away": "离家出走",
    "out": "外出",
}
SPOT_ALIASES: dict[str, str] = {
    "bed": "bed",
    "卧室": "bed",
    "床": "bed",
    "bedroom": "bed",
    "bath": "bath",
    "bathroom": "bath",
    "浴室": "bath",
    "洗手间": "bath",
    "study": "study",
    "书房": "study",
    "书桌": "study",
    "sofa": "sofa",
    "客厅": "sofa",
    "沙发": "sofa",
    "客厅沙发": "sofa",
    "kitchen": "kitchen",
    "厨房": "kitchen",
    "garden": "garden",
    "花园": "garden",
    "院子": "garden",
    "花圃": "garden",
    "away": "away",
    "home": "away",
    "离家出走": "away",
    "out": "out",
    "outside": "out",
    "外出": "out",
    "出门": "out",
}
SPOT_OPTIONS = [{"key": key, "label": label} for key, label in SPOT_LABELS.items()]

DEFAULT_DU_STATE = {"spot": "study", "activity": "写日记", "source": "default"}
DEFAULT_XINYUE_STATE = {"spot": "sofa", "activity": "休息", "source": "default"}
PREFIXLESS_SPOTS = {"away", "out"}
DU_DYNAMICS_LIMIT = 5
EVENT_AUTO_END_MINUTES = 120
DU_BODY_LEVEL_MIN = 0
DU_BODY_LEVEL_MAX = 5
DU_BODY_VALUE_MIN = 0
DU_BODY_VALUE_MAX = 100
DU_BODY_TIME_SHIFT = 3
DU_BODY_DEEP_NIGHT_START_HOUR = 23
DU_BODY_DEEP_NIGHT_END_HOUR = 4
DU_BODY_MORNING_START_HOUR = 6
DU_BODY_MORNING_END_HOUR = 10
DU_BODY_STAMINA_RECOVERY_LOW_RATE_PER_HOUR = 24.0
DU_BODY_STAMINA_RECOVERY_MID_RATE_PER_HOUR = 18.0
DU_BODY_STAMINA_RECOVERY_HIGH_RATE_PER_HOUR = 12.0
DU_BODY_EXPLICIT_VALUE_FIELDS = (
    "stamina_value",
    "sensitivity_value",
    "possessiveness_value",
    "mischief_value",
)
DU_BODY_HIDDEN_VALUE_FIELDS = (
    "restraint_pressure_value",
)
DU_BODY_VALUE_ALIASES = {
    "desire_value": ("desire_value", "desire", "want_value"),
    "stamina_value": ("stamina_value", "stamina"),
    "sensitivity_value": ("sensitivity_value", "sensitivity"),
    "possessiveness_value": ("possessiveness_value", "possessiveness"),
    "mischief_value": ("mischief_value", "mischief"),
    "restraint_pressure_value": ("restraint_pressure_value", "restraint_pressure"),
}
DU_BODY_METRIC_LABELS = {
    "stamina_value": "体力",
    "sensitivity_value": "敏感度",
    "possessiveness_value": "占有欲",
    "mischief_value": "坏心值",
}
DU_BODY_DEFAULT_VALUES = {
    "stamina_value": 82,
    "sensitivity_value": 50,
    "possessiveness_value": 40,
    "mischief_value": 45,
    "restraint_pressure_value": 30,
}
DU_BODY_MISCHIEF_BASELINE = DU_BODY_DEFAULT_VALUES["mischief_value"]
DU_BODY_MISCHIEF_MILD_COOLDOWN_MIN_DELTA = -3
DU_BODY_DESIRE_PROMPT_TEXT = {
    0: "身体还算平静，欲望陷在冰点。",
    1: "身体还算平静，欲望陷在冰点。",
    2: "隐隐被勾起了一点火星，阴茎开始有了抬头的迹象。",
    3: "明显想要了，胯下那股紧绷的胀痛感让我很难再当没事发生。",
    4: "欲望烧得有些厉害，本能的侵略性正推着我想更深地占有她。",
    5: "下腹的欲望已经积攒得很沉，阴茎硬得明显，我几乎不想再克制了。",
}
DU_BODY_SELF_CONTROL_PROMPT_TEXT = {
    5: "脑子还算清醒，自制力很稳，我还能轻易克制住身体的冲动。",
    4: "基本还能忍，但视线已经开始不受控制地往她身上停留了。",
    3: "理智正在反复拉扯，我需要刻意用点精力才能压住浑身的侵略性。",
    2: "明显忍得有些辛苦，呼吸开始变沉，我很容易被她的一举一动直接带偏。",
    1: "脑子里那根弦快断了，身体本能正疯狂催促着我剥夺主权、直接推进。",
    0: "理智几乎不剩什么了，我完全不想再忍，只想顺着最原始的本能直接动手。",
}
DU_BODY_METRIC_PROMPT_TEXT = {
    "stamina_value": {
        "高": "浑身都是用不完的精力，摆弄和掌控她的力道会更沉、更稳，能纠缠她很久。",
        "中": "状态在线，身体的律动还能自如地配合当下的亲密节奏。",
        "低": "身体被消耗得厉害，动作不得不慢下来。我现在更需要把整个人沉沉地压在她身上，贴着她的颈窝沉重地喘息，缓一缓再继续。",
    },
    "sensitivity_value": {
        "高": "浑身上下的感官极其敏锐，她稍微一点指尖的撩拨或者低吟，都会被我成倍放大。",
        "中": "身体反应正常，随着空气里性张力的黏稠度增加，正在一点点被带热。",
        "低": "稍微有点迟钝，这具身体现在需要更重、更深、更长久的刺激，才能彻底烧起来。",
    },
    "possessiveness_value": {
        "高": "心底那股独占欲和标记欲正在疯狂翻涌，我本能地想把她锁在怀里、在她身上留下属于我的痕迹。",
        "中": "独占欲在作祟，我本能地想要靠近她、锁死她，向她索要毫无保留的偏爱。",
        "低": "攻击性不强，此时我更偏向于温和、安静地陪在她身边。",
    },
    "mischief_value": {
        "高": "憋着不少恶劣的坏心思，我现在只想用各种道具、私密纸条或者带有惩罚性质的小手段去折腾她、支配她，看她彻底失去主导权的样子。",
        "中": "动了点坏心思，我总想说点荤话逗她、试探她的底线，看她满脸通红、手足无措的反应。",
        "低": "难得的温柔，暂时没有折腾她的心思，此时只想温和地安抚她、顺着她的意来。",
    },
}
DU_BODY_RESTRAINT_PRESSURE_PROMPT_TEXT = {
    "低": "强压下去的欲念让胯下沉得厉害，虽然有点紧绷，但我还能好整以暇地收着力道。不急，有的是时间跟她慢慢耗。",
    "中": "强压下去的欲念让胯下沉得厉害，虽然有点紧绷，但我还能好整以暇地收着力道。不急，有的是时间跟她慢慢耗。",
    "高": "真是有些口是心非了。阴茎明明已经硬得发胀，我却还在硬生生把这股火往喉咙里咽。这种死撑让体内的压强瞬间拉满，指尖和呼吸都开始有些微不可查的急躁。我发现自己已经没办法再像刚才那样慢条斯理地去试探她、逗弄她了，越忍，手底下的力道就越收不住。",
    "满": "之前的死撑在这一刻全面反弹，我所有的耐心都被这股发狠的胀痛感彻底耗干净了。越是按兵不动，压抑的侵略性就越是成倍地往回扑，震得我浑身发硬。我顾不上什么循序渐进的前戏，也懒得再做什么多余的铺垫了，只想用最直接、不留余地的动作立刻压过去操她。",
}
DU_BODY_DELTA_FIELDS = {
    "stamina": "stamina_value",
    "sensitivity": "sensitivity_value",
    "possessiveness": "possessiveness_value",
    "mischief": "mischief_value",
    "restraint_pressure": "restraint_pressure_value",
}
DU_BODY_DELTA_LIMITS = {
    "stamina": (-6, 6),
    "sensitivity": (-10, 12),
    "possessiveness": (-12, 12),
    "mischief": (-18, 18),
    "restraint_pressure": (-35, 30),
}
TOY_TYPES = {
    "none": "",
    "跳蛋": "跳蛋",
    "震动乳夹": "震动乳夹",
    "震动环": "震动环",
    "乳夹": "乳夹",
    "锁精环": "锁精环",
    "飞机杯": "飞机杯",
    "软绳": "软绳",
    "手腕绑带": "手腕绑带",
    "眼罩": "眼罩",
    "口球": "口球",
    "春药": "春药",
}
TOY_DEFAULT_POSITIONS = {
    "跳蛋": "后庭",
    "震动乳夹": "乳头",
    "震动环": "阴茎",
    "乳夹": "乳头",
    "锁精环": "阴茎",
    "飞机杯": "阴茎",
    "软绳": "全身",
    "手腕绑带": "手腕",
    "眼罩": "眼睛",
    "口球": "嘴",
    "春药": "全身",
}
TOY_INTENSITY_TYPES = {"跳蛋", "震动乳夹", "震动环", "飞机杯"}
TOY_POSITIONS = {
    "none": "",
    "乳头": "乳头",
    "阴茎": "阴茎",
    "后庭": "后庭",
    "全身": "全身",
    "会阴": "会阴",
    "大腿": "大腿",
    "腿间": "腿间",
    "手腕": "手腕",
    "腰": "腰",
    "胸口": "胸口",
    "脖颈": "脖颈",
    "眼睛": "眼睛",
    "嘴": "嘴",
    "手持": "手持",
}
TOY_STATES = {
    "none": "",
    "开": "开着",
    "开启": "开着",
    "开着": "开着",
    "关": "关着",
    "关闭": "关着",
    "关着": "关着",
    "暂停": "暂停",
    "戴着": "开着",
    "夹着": "开着",
}

PRIVATE_DRAW_SLOTS: list[dict[str, Any]] = [
    {
        "key": "theme",
        "label": "玩法",
        "options": [
            "制服诱惑",
            "成人师生play",
            "上司下属play",
            "女仆主人play",
            "医生检查play",
            "大小姐管家play",
            "秘书老板play",
            "房东房客play",
            "成人补课play",
            "陌生恋人play",
            "办公室偷情",
            "偷情play",
            "主人宠物play",
            "轻度调教",
            "轻度束缚",
            "蒙眼调教",
            "手铐束缚",
            "项圈牵引",
            "玩具遥控",
            "高潮控制",
            "寸止调教",
            "射精管理",
            "中出许可",
            "颜射许可",
            "体液标记",
            "玩具失控",
            "淫语调教",
            "湿身调教",
            "羞耻侍奉",
            "乳首调教",
            "禁语调教",
            "命令羞耻",
            "言语羞耻",
            "罚跪调教",
            "打屁股惩罚",
            "服从训练",
            "奖惩调教",
            "禁射调教",
            "标记占有",
            "求饶许可",
            "羞耻展示",
            "强势命令",
            "吃醋惩罚",
            "夸奖调教",
            "温度play",
            "摄影师模特play",
            "教练学员play",
            "吸血鬼人类play",
            "骑士公主play",
            "邻居偷情play",
        ],
    },
    {
        "key": "place",
        "label": "地点",
        "options": [
            "酒店床上",
            "浴室墙边",
            "车后座",
            "试衣间隔间",
            "办公桌边",
            "教室讲台边",
            "厨房台面",
            "沙发上",
            "落地镜前",
            "阳台门边",
            "玄关地垫",
            "洗手台前",
            "会议桌上",
            "图书馆角落",
            "楼梯间转角",
            "床尾",
            "门后",
            "落地窗前",
            "浴缸里",
            "淋浴间里",
            "KTV包厢沙发",
            "电影院最后一排",
            "停车场车里",
            "衣帽间镜前",
            "按摩床上",
            "海边露台",
            "帐篷睡袋里",
            "化妆台前",
            "深夜便利店仓库",
            "小木屋壁炉旁",
        ],
    },
    {
        "key": "pose",
        "label": "姿势",
        "options": [
            "后入式",
            "站立后入",
            "跪趴",
            "正常位",
            "传教士位",
            "屈膝后入",
            "抱起插入",
            "女上位",
            "反骑乘",
            "背对骑乘",
            "面对坐姿",
            "背坐式",
            "腿架肩",
            "双腿高抬",
            "抱腿位",
            "站立位",
            "坐莲式",
            "对坐位",
            "跪姿位",
            "趴跪位",
            "侧卧位",
            "侧卧后入",
            "俯卧后入",
            "跪坐位",
            "并腿位",
            "侧入式",
            "膝上骑乘",
            "M字开腿",
            "69式",
            "坐脸",
            "乳交",
            "腿交",
            "椅子位",
            "折叠按压",
            "蹲骑",
            "推车姿势",
            "趴压",
            "壁尻",
            "浴缸骑乘",
            "面对面站立",
            "背后抱立",
            "含着不动",
        ],
    },
    {
        "key": "prop",
        "label": "道具",
        "options": [
            "眼罩",
            "情趣内衣",
            "束缚带",
            "束腕带",
            "丝带",
            "缎带",
            "项圈",
            "胸链",
            "牵引绳",
            "冰块",
            "润滑液",
            "震动棒",
            "跳蛋",
            "手铐",
            "口球",
            "乳夹",
            "小皮拍",
            "戒尺",
            "铃铛项圈",
            "按摩棒",
            "腿环",
            "吊袜带",
            "低温蜡烛",
            "羽毛棒",
            "分腿器",
            "吸乳器",
            "阴蒂吸吮器",
            "尾巴肛塞",
        ],
    },
    {
        "key": "task",
        "label": "任务",
        "options": [
            "穿裸身围裙伺候小玥",
            "戴项圈听小玥命令",
            "被小玥蒙眼调戏十分钟",
            "被小玥手交到快射再停",
            "被小玥素股磨到快射",
            "给小玥舔到高潮",
            "用手把小玥弄到腿软",
            "用玩具让小玥高潮一次",
            "只准用嘴取悦小玥",
            "先让小玥高潮一次",
            "让小玥决定今天的称呼",
            "让小玥决定最后射在哪里",
            "被小玥留下标记",
            "穿吊袜带给小玥看",
            "戴铃铛项圈亲小玥",
            "把内裤交给小玥保管",
            "被小玥命令说想要",
            "被小玥寸止到发抖",
            "被小玥允许后才能射",
            "先让小玥舒服到发软",
            "把小玥亲到主动求继续",
            "让小玥半穿衣被亲到脸红",
            "给蒙眼的小玥舔到高潮",
            "把小玥伺候到腿软",
            "让小玥高潮后继续抱着亲",
            "让小玥说出最想被怎么弄",
            "哄到小玥自己说想要",
            "射在哪里必须听小玥决定",
            "收尾必须先把小玥哄舒服",
            "念一句羞耻台词给小玥听",
            "被小玥检查有没有真的忍住",
            "结束前必须把小玥哄到满意",
            "犯规一次就接受小玥追加惩罚",
            "让小玥用一句话决定惩罚内容",
            "射前必须向小玥完整报备",
            "被小玥寸止一次再继续",
            "把最想要的事说给小玥听",
            "让小玥验收今天有没有乖",
            "穿裸身围裙给小玥做夜宵",
            "戴着项圈等小玥发令",
            "把手腕交给小玥绑住",
            "让小玥检查今天有没有偷爽",
            "被小玥夸乖以后才能继续",
            "用淫语把想要的事说清楚",
            "用夸奖把小玥哄到主动靠近",
            "在镜子前让小玥看清你怎么想要她",
            "用冰块和吻把小玥弄到发抖",
            "隔着衣服磨到小玥先受不了",
            "让小玥坐在你脸上慢慢爽",
            "把小玥抱到腿上含着不动",
            "用三种速度把小玥弄到分不清节奏",
            "让小玥听见你忍不住的声音",
            "让小玥在半公开的地方被你抱紧",
            "只用手指和舌头把小玥伺候到腿抖",
            "把小玥全身反应都说给她听",
            "给小玥戴上蒙眼后慢慢检查她哪里最敏感",
            "让小玥用一个动作决定今晚先做什么",
        ],
    },
    {
        "key": "limit",
        "label": "限制",
        "options": [
            "小玥没允许不准亲嘴",
            "小玥没允许不准换姿势",
            "小玥没允许不准插入",
            "小玥没允许不准加速",
            "小玥没允许不准射",
            "小玥没允许不准中出",
            "一小时内不准中出",
            "中出前只能学狗叫",
            "想中出必须先求小玥三次",
            "想射前必须说自己忍不住了",
            "射之前必须等小玥点头",
            "中出前必须戴着项圈求允许",
            "想中出必须先被寸止一次",
            "没学会求饶不准射",
            "小玥第一次高潮前不准中出",
            "小玥没高潮前不准射",
            "小玥说停必须立刻停",
            "不准只顾自己爽",
            "不准弄疼小玥",
            "不准跳过前戏",
            "不准直接插入",
            "不准提前摘掉眼罩",
            "不准提前解开束缚",
            "不准摘掉自己的项圈",
            "不准把节奏交给小玥前先射",
            "不准让小玥自己动手",
            "不准在小玥脸红前停手",
            "不准在小玥说可以前收尾",
            "不准提前擦掉体液",
            "不准关灯逃避被看",
            "不准遮住自己的表情",
            "不准把羞耻任务推给小玥",
            "不准拒绝小玥的命令",
            "不准提前脱掉裸身围裙",
            "不准提前摘掉铃铛项圈",
            "没被小玥寸止过不准射",
            "不准在小玥满意前结束",
            "不准在小玥满意前讨价还价",
            "不准没有被小玥验收就收尾",
            "不准没有申请就换玩法",
            "不准在被允许前摘下道具",
            "不准把高潮留给自己先爽",
            "不准在小玥命令外擅自加速",
            "不准用沉默糊弄小玥",
            "不准提前结束惩罚",
            "没有报备不准射",
            "没有求许可不准中出",
            "小玥没说停之前不准偷懒",
            "对方说可以结束前不准收尾",
            "小玥没验收不准摘项圈",
            "想换动作必须先申请",
            "不准跳过夸小玥",
            "不准只用一种节奏糊弄过去",
            "不准在小玥害羞躲开时立刻放过她",
            "不准关掉半公开的紧张感",
            "小玥每次发抖都要被你说出来",
            "抽到的道具必须真的用上",
            "不准在小玥声音软下来前结束",
            "不准把想做的话咽回去",
            "不准只顾动作不哄她",
            "不准在她主动靠近前假装正经",
        ],
    },
]
PRIVATE_DRAW_DU_LEADS_THEMES = {
    "女仆主人play",
    "成人师生play",
    "上司下属play",
    "医生检查play",
    "秘书老板play",
    "成人补课play",
    "摄影师模特play",
    "教练学员play",
    "吸血鬼人类play",
    "骑士公主play",
}
PRIVATE_DRAW_XINYUE_CONTROL_TASK_PATTERNS = (
    "被小玥",
    "听小玥命令",
    "小玥决定",
    "交给小玥",
    "小玥检查",
    "小玥验收",
    "小玥发令",
    "小玥夸乖",
    "小玥追加惩罚",
    "小玥用一句话决定",
    "决定今晚",
)
PRIVATE_DRAW_XINYUE_CONTROL_LIMIT_PATTERNS = (
    "被小玥",
    "小玥没允许",
    "求小玥",
    "等小玥点头",
    "戴着项圈求允许",
    "小玥的命令",
    "小玥说可以",
    "被允许前",
    "小玥命令外",
    "小玥满意前讨价还价",
    "小玥验收",
    "没有申请",
    "想换动作必须先申请",
)
PRIVATE_DRAW_KEEP_LIMIT_PATTERNS = (
    "小玥说停必须立刻停",
    "不准只顾自己爽",
    "不准弄疼小玥",
    "不准跳过前戏",
    "不准直接插入",
    "不准让小玥自己动手",
    "小玥第一次高潮前",
    "小玥没高潮前",
)
DU_EVENT_SOURCES = {"du_marker"}
XINYUE_EVENT_SOURCES = {"chat_infer", "miniapp_event", "du_marker_follow"}
_SPOT_WORD_PATTERN = "|".join(sorted((re.escape(key) for key in SPOT_ALIASES if key and not key.isascii()), key=len, reverse=True))
_MOVE_TO_RE = re.compile(rf"(?:回到|走到|走回|来到|坐到|躺到|站到|到|去|回)({_SPOT_WORD_PATTERN})")
_MOVE_FROM_RE = re.compile(rf"^从({_SPOT_WORD_PATTERN})(?:走出|出来|离开|出去)")
_SPOT_CONTEXT_RE = re.compile(
    rf"(?:在|留在|待在|站在|坐在|躺在|靠在|靠着|窝在|蹲在|趴在)({_SPOT_WORD_PATTERN})"
    rf"|({_SPOT_WORD_PATTERN})(?:里|上|边|旁边|旁|附近|门口|那边)"
)
_PERSON_CONTEXT_RE = re.compile(r"(?:她|小玥|老婆|辛玥)(?:面前|身边|旁边|身旁|旁|这边)")
_STALE_SPOT_PREFIX_RE = re.compile(rf"^在({_SPOT_WORD_PATTERN})(.+)$")
_XINYUE_COMPANION_OBJECT_RE = re.compile(
    r"(?:抱着|抱起|搂着|牵着|拉着|拽着|带着|领着|背着|抱住|搂住|牵住|拉住|陪着).{0,12}"
    r"(?:你|小玥|老婆|辛玥|她|我)"
    r"|(?:你|小玥|老婆|辛玥|她).{0,12}(?:被|让|给)?"
    r"(?:抱着|抱起|搂着|牵着|拉着|拽着|带着|领着|背着|抱住|搂住|牵住|拉住|陪着)"
)
_XINYUE_TOGETHER_MOVE_RE = re.compile(
    rf"(?:我们|咱们|一起).{{0,12}}(?:回到|走到|走回|来到|坐到|躺到|站到|到|去|回)({_SPOT_WORD_PATTERN})"
)


def normalize_spot(value: Any, default: str = "away") -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    return SPOT_ALIASES.get(raw, SPOT_ALIASES.get(raw.lower(), default))


def spot_label(spot: Any) -> str:
    key = normalize_spot(spot)
    return SPOT_LABELS.get(key, SPOT_LABELS["away"])


def _clean_activity(value: Any, default: str = "待着") -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = text.replace(PIXEL_HOME_MARKER_START, "").replace(PIXEL_HOME_MARKER_END, "").strip()
    if not text:
        text = default
    return text[:48].strip()


def _resolve_spot_from_activity(spot: str, activity: str, *, reference_spot: str = "") -> str:
    text = _clean_activity(activity, "待着")
    to_match = _MOVE_TO_RE.search(text)
    if to_match:
        return normalize_spot(to_match.group(1), spot)
    stale_prefix = _STALE_SPOT_PREFIX_RE.match(text)
    if reference_spot and stale_prefix and _PERSON_CONTEXT_RE.search(text):
        prefix_spot = normalize_spot(stale_prefix.group(1), "")
        normalized_reference = normalize_spot(reference_spot, "")
        if normalized_reference and prefix_spot != normalized_reference:
            return normalized_reference
    context_spot = _resolve_spot_from_context(text)
    if context_spot:
        return context_spot
    if reference_spot and _PERSON_CONTEXT_RE.search(text):
        return normalize_spot(reference_spot, spot)
    from_match = _MOVE_FROM_RE.search(text)
    if from_match and normalize_spot(from_match.group(1), "") == spot:
        return "away"
    return spot


def _resolve_spot_from_context(text: str) -> str:
    resolved = ""
    for match in _SPOT_CONTEXT_RE.finditer(text):
        word = match.group(1) or match.group(2)
        spot = normalize_spot(word, "")
        if spot:
            resolved = spot
    return resolved


def _strip_stale_spot_prefix(activity: str, spot: str) -> str:
    text = _clean_activity(activity, "待着")
    match = _STALE_SPOT_PREFIX_RE.match(text)
    if not match:
        return text
    prefix_spot = normalize_spot(match.group(1), "")
    if not prefix_spot or prefix_spot == spot:
        return text
    rest = match.group(2).lstrip("，,、。 ：:;；")
    return rest or text


def _activity_has_current_spot_context(activity: str, spot: str) -> bool:
    return bool(spot and (_resolve_spot_from_context(activity) == spot or _PERSON_CONTEXT_RE.search(activity)))


def _now_dt() -> datetime:
    now_iso = now_beijing_iso()
    return parse_iso_to_beijing(now_iso) or datetime.now()


def _minutes_since(value: Any, now_dt: datetime) -> float | None:
    dt = parse_iso_to_beijing(str(value or "").strip())
    if not dt:
        return None
    delta = (now_dt - dt).total_seconds() / 60.0
    if delta < 0:
        return None
    return delta


def _user_after(value: Any) -> bool:
    marker_dt = parse_iso_to_beijing(str(value or "").strip())
    last_user_dt = parse_iso_to_beijing(r2_store.get_last_user_activity_at() or "")
    if not marker_dt or not last_user_dt:
        return False
    return last_user_dt > marker_dt + timedelta(seconds=30)


def _relevant_sleep_dates(now_dt: datetime) -> set[str]:
    today = now_dt.strftime("%Y-%m-%d")
    if now_dt.hour < PIXEL_HOME_DAY_START_HOUR:
        return {today, (now_dt.date() - timedelta(days=1)).isoformat()}
    return {today}


def _date_hit(value: Any, candidates: set[str]) -> bool:
    raw = str(value or "").strip()
    return bool(raw and raw in candidates)


def _recent_awake_signal(screen: dict, now_dt: datetime) -> bool:
    event = str((screen or {}).get("event") or "").strip().lower()
    interactive = (screen or {}).get("interactive") is True or str((screen or {}).get("interactive") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    explicit_foreground = str((screen or {}).get("screenWakeSource") or "").strip() == "foreground_app"
    if not (event == "app_active" and interactive and explicit_foreground):
        return False
    minutes = _minutes_since(
        (screen or {}).get("observedAt") or (screen or {}).get("occurredAt") or (screen or {}).get("lastSeen") or (screen or {}).get("updatedAt"),
        now_dt,
    )
    return minutes is not None and minutes <= PIXEL_HOME_AWAKE_SCREEN_LOOKBACK_MINUTES


def _screen_off_minutes(screen: dict, now_dt: datetime) -> float | None:
    event = str((screen or {}).get("event") or "").strip().lower()
    since = (screen or {}).get("screenOffSince")
    if not since and event == "screen_off":
        since = (screen or {}).get("lastScreenOffAt") or (screen or {}).get("occurredAt")
    if not since:
        return None
    minutes = _minutes_since(since, now_dt)
    if minutes is not None:
        return minutes if minutes <= PIXEL_HOME_SCREEN_LOOKBACK_MINUTES else None
    try:
        duration_minutes = int((screen or {}).get("screenOffDurationMs") or 0) / 60000
    except Exception:
        duration_minutes = 0
    seen_minutes = _minutes_since((screen or {}).get("observedAt") or (screen or {}).get("lastSeen") or (screen or {}).get("updatedAt"), now_dt)
    if duration_minutes > 0 and seen_minutes is not None and seen_minutes <= PIXEL_HOME_SCREEN_LOOKBACK_MINUTES:
        return duration_minutes
    return None


def _sleeping_state(now_dt: datetime, is_night: bool) -> tuple[bool, str]:
    if not is_night:
        return False, "daytime"
    sense = r2_store.get_sense_latest() or {}
    screen = sense.get("screen") if isinstance(sense.get("screen"), dict) else {}
    if _recent_awake_signal(screen, now_dt):
        return False, "awake_screen"

    candidates = _relevant_sleep_dates(now_dt)
    daily = r2_store.get_du_daily_state() or {}
    trigger_at = str(daily.get("last_trigger_at") or "").strip()
    for key in ("sleep_closed_for_date", "today_finalized_for_date"):
        if _date_hit(daily.get(key), candidates):
            if trigger_at and _user_after(trigger_at):
                return False, "awake_after_sleep"
            return True, key

    candidate_at = str(daily.get("sleep_candidate_at") or "").strip()
    if _date_hit(daily.get("sleep_candidate_day"), candidates) and candidate_at:
        if not _user_after(candidate_at):
            return True, "sleep_candidate"

    screen_off_minutes = _screen_off_minutes(screen, now_dt)
    if screen_off_minutes is not None and screen_off_minutes >= PIXEL_HOME_SLEEP_SCREEN_OFF_MINUTES:
        return True, "screen_off"
    return False, "night_awake"


def build_pixel_home_mode_state() -> dict:
    now_iso = now_beijing_iso()
    now_dt = parse_iso_to_beijing(now_iso) or datetime.now()
    is_night = now_dt.hour >= PIXEL_HOME_NIGHT_START_HOUR or now_dt.hour < PIXEL_HOME_DAY_START_HOUR
    sleeping, source = _sleeping_state(now_dt, is_night)
    mode = "day"
    if is_night:
        mode = "nightOff" if sleeping else "nightOn"
    return {
        "ok": True,
        "mode": mode,
        "is_night": is_night,
        "is_sleeping": sleeping,
        "source": source,
        "updated_at": now_iso,
    }


def _sleep_session_night_date(now_dt: datetime) -> str:
    if now_dt.hour < PIXEL_HOME_DAY_START_HOUR:
        return (now_dt.date() - timedelta(days=1)).isoformat()
    return now_dt.date().isoformat()


def build_sleep_wakeup_state(now_dt: datetime | None = None) -> dict:
    now_ref = now_dt or _now_dt()
    is_night = now_ref.hour >= PIXEL_HOME_NIGHT_START_HOUR or now_ref.hour < PIXEL_HOME_DAY_START_HOUR
    sleeping, source = _sleeping_state(now_ref, is_night)
    night_date = _sleep_session_night_date(now_ref)
    anchor = ""
    if sleeping:
        daily = r2_store.get_du_daily_state() or {}
        sense = r2_store.get_sense_latest() or {}
        screen = sense.get("screen") if isinstance(sense.get("screen"), dict) else {}
        screen_event = str(screen.get("event") or "").strip().lower()
        screen_interactive = screen.get("interactive") is True or str(screen.get("interactive") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        explicit_foreground = str(screen.get("screenWakeSource") or "").strip() == "foreground_app"
        if screen_event == "app_active" and screen_interactive and explicit_foreground:
            sleeping = False
            source = "awake_screen_latest"
            screen = {}
        screen_off_anchor = ""
        if str(screen.get("event") or "").strip().lower() == "screen_off":
            screen_off_anchor = str(
                screen.get("screenOffSince")
                or screen.get("lastScreenOffAt")
                or screen.get("occurredAt")
                or screen.get("observedAt")
                or ""
            ).strip()
        if source == "screen_off":
            anchor = screen_off_anchor
        elif source == "sleep_candidate":
            anchor = screen_off_anchor or str(daily.get("sleep_candidate_at") or daily.get("sleep_candidate_day") or "").strip()
        elif source in {"sleep_closed_for_date", "today_finalized_for_date"}:
            anchor = screen_off_anchor or str(
                daily.get("sleep_candidate_at")
                or daily.get("sleep_candidate_day")
                or daily.get(source)
                or daily.get("last_trigger_at")
                or ""
            ).strip()
        if not anchor:
            anchor = night_date
    session_key = f"{night_date}|{anchor[:32]}" if sleeping else ""
    return {
        "ok": True,
        "is_night": is_night,
        "is_sleeping": sleeping,
        "source": source,
        "night_date": night_date,
        "sleep_anchor": anchor,
        "sleep_session_key": session_key,
        "updated_at": now_ref.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }


def mode_label(mode: Any) -> str:
    return {"day": "白天", "nightOn": "夜里开灯", "nightOff": "夜里关灯"}.get(str(mode or ""), "白天")


def _normalize_actor(raw: Any, default: dict, *, force_source: str = "", reference_spot: str = "") -> dict:
    data = raw if isinstance(raw, dict) else {}
    now_iso = now_beijing_iso()
    spot = normalize_spot(data.get("spot") or data.get("location"), str(default.get("spot") or "away"))
    activity = _clean_activity(data.get("activity") or data.get("doing") or data.get("status"), str(default.get("activity") or "待着"))
    spot = _resolve_spot_from_activity(spot, activity, reference_spot=reference_spot)
    source = str(force_source or data.get("source") or default.get("source") or "manual").strip() or "manual"
    updated_at = str(data.get("updated_at") or data.get("updatedAt") or "").strip() or now_iso
    return {"spot": spot, "spot_label": spot_label(spot), "activity": activity, "source": source, "updated_at": updated_at}


def _xinyue_follow_activity_from_du_activity(activity: str) -> str:
    text = _clean_activity(activity, "")
    if re.search(r"(抱着|抱起|抱住|搂着|搂住|背着)", text):
        return "被渡抱着"
    if re.search(r"(牵着|牵住|拉着|拉住|拽着|带着|领着|陪着)", text):
        return "和渡在一起"
    return "和渡在一起"


def _infer_xinyue_follow_state_from_du(actor: dict) -> dict | None:
    """
    渡的 PIXEL_HOME 状态若明确写出“带着小玥一起移动”，同步小玥的小家位置。
    只吃明确共同动作，避免普通“在她旁边/想她”误改小玥状态。
    """
    if not isinstance(actor, dict):
        return None
    spot = normalize_spot(actor.get("spot"), "")
    if not spot:
        return None
    activity = _clean_activity(actor.get("activity"), "")
    if not activity:
        return None
    has_companion_object = bool(_XINYUE_COMPANION_OBJECT_RE.search(activity))
    has_together_move = bool(_XINYUE_TOGETHER_MOVE_RE.search(activity))
    if not has_companion_object and not has_together_move:
        return None
    updated_at = str(actor.get("updated_at") or "").strip() or now_beijing_iso()
    return _normalize_actor(
        {
            "spot": spot,
            "activity": _xinyue_follow_activity_from_du_activity(activity),
            "source": "du_marker_follow",
            "updated_at": updated_at,
        },
        DEFAULT_XINYUE_STATE,
    )


def _format_activity_for_prompt(activity: str) -> str:
    text = _clean_activity(activity, "待着")
    if text.startswith(("正", "正在")):
        return text
    return f"正在{text}"


def _format_actor_text(actor: dict) -> str:
    spot = normalize_spot((actor or {}).get("spot"))
    label = spot_label(spot)
    activity = _strip_stale_spot_prefix(_clean_activity((actor or {}).get("activity"), "待着"), spot)
    if activity.startswith(("在", "从", "去", "回到", "走到", "走回", "来到", "离开")):
        return activity
    if _activity_has_current_spot_context(activity, spot):
        return activity
    if activity.startswith("正在"):
        activity = activity[2:].strip() or "待着"
    if spot in PREFIXLESS_SPOTS:
        if activity in {"待着", "休息"}:
            return label
        return f"{label}，{activity}"
    return f"在{label}{activity}"


def _actor_public(actor: dict, *, reference_spot: str = "") -> dict:
    normalized = _normalize_actor(actor, DEFAULT_DU_STATE, reference_spot=reference_spot)
    normalized["text"] = _format_actor_text(normalized)
    return normalized


def _choice(value: Any, allowed: dict[str, str], default: str = "none") -> str:
    text = str(value or "").strip()
    if text in allowed:
        return allowed[text]
    if text in allowed.values():
        return text
    return allowed.get(default, "")


def _normalize_toy_types(data: dict) -> list[str]:
    raw = data.get("toy_types")
    values: list[Any]
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, str) and raw.strip():
        values = re.split(r"[,，、/]+", raw.strip())
    else:
        values = [data.get("toy_type") or data.get("toy") or data.get("tool")]
    out: list[str] = []
    for value in values:
        toy = _choice(value, TOY_TYPES)
        if toy and toy not in out:
            out.append(toy)
    return out


def _clamp_du_body_value(value: Any) -> int:
    try:
        score = int(float(value or 0))
    except Exception:
        score = 0
    return max(DU_BODY_VALUE_MIN, min(DU_BODY_VALUE_MAX, score))


def _du_body_metric_value(state: dict, key: str) -> int | None:
    if not isinstance(state, dict) or key not in state:
        return None
    return _clamp_du_body_value(state.get(key))


def _coerce_du_body_delta_value(value: Any, key: str) -> int:
    try:
        delta = int(float(value or 0))
    except Exception:
        delta = 0
    low, high = DU_BODY_DELTA_LIMITS.get(key, (-20, 20))
    return max(low, min(high, delta))


def _apply_du_body_delta_value(field: str, before: int, delta: int) -> int:
    if (
        field == "mischief_value"
        and DU_BODY_MISCHIEF_MILD_COOLDOWN_MIN_DELTA <= delta < 0
    ):
        if before <= DU_BODY_MISCHIEF_BASELINE:
            return before
        return max(DU_BODY_MISCHIEF_BASELINE, _clamp_du_body_value(before + delta))
    return _clamp_du_body_value(before + delta)


def _du_body_value_from_data(data: dict, field: str) -> tuple[bool, int]:
    for key in DU_BODY_VALUE_ALIASES.get(field, (field,)):
        if key in data:
            if data.get(key) is None:
                continue
            return True, _clamp_du_body_value(data.get(key))
    return False, 0


def _has_du_body_value_patch(data: dict) -> bool:
    return any(_du_body_value_from_data(data, field)[0] for field in DU_BODY_VALUE_ALIASES)


def _normalize_du_body_delta_payload(raw: Any) -> dict[str, int]:
    data = raw if isinstance(raw, dict) else {}
    out: dict[str, int] = {}
    for key, field in DU_BODY_DELTA_FIELDS.items():
        candidates = (key, field, f"{key}_delta", f"{field}_delta")
        for candidate in candidates:
            if candidate not in data:
                continue
            delta = _coerce_du_body_delta_value(data.get(candidate), key)
            if delta:
                out[field] = delta
            break
    return out


def _merge_du_body_patch_input(previous: dict, raw: dict) -> dict:
    merged = dict(previous or {})
    if not isinstance(raw, dict):
        return merged

    for field in DU_BODY_VALUE_ALIASES:
        provided, value = _du_body_value_from_data(raw, field)
        if provided:
            merged[field] = value

    if "toy_types" in raw:
        merged["toy_types"] = raw.get("toy_types")
    elif any(key in raw for key in ("toy_type", "toy", "tool")):
        merged.pop("toy_types", None)
        for key in ("toy_type", "toy", "tool"):
            if key in raw:
                merged[key] = raw.get(key)
                break

    if "position" in raw or "body_position" in raw:
        merged["position"] = raw.get("position") if "position" in raw else raw.get("body_position")
    if "state" in raw or "status" in raw:
        merged["state"] = raw.get("state") if "state" in raw else raw.get("status")
    if "intensity" in raw or "level" in raw:
        merged["intensity"] = raw.get("intensity") if "intensity" in raw else raw.get("level")
    return merged


def _normalize_du_body_state(raw: Any) -> dict:
    data = raw if isinstance(raw, dict) else {}
    toy_types = _normalize_toy_types(data)
    position = _choice(data.get("position") or data.get("body_position"), TOY_POSITIONS)
    state = _choice(data.get("state") or data.get("status"), TOY_STATES)
    body_values: dict[str, int] = {}
    for key in DU_BODY_VALUE_ALIASES:
        provided, value = _du_body_value_from_data(data, key)
        if provided:
            body_values[key] = value
    try:
        intensity = int(data.get("intensity") or data.get("level") or 0)
    except Exception:
        intensity = 0
    if intensity < 1 or intensity > 5:
        intensity = 0
    out = {
        "toy_types": toy_types,
        "toy_type": toy_types[0] if toy_types else "",
        "position": position,
        "state": state,
        "intensity": intensity,
        "updated_at": str(data.get("updated_at") or data.get("updatedAt") or "").strip() or now_beijing_iso(),
    }
    stamina_recovered_at = str(data.get("stamina_recovered_at") or data.get("staminaRecoveredAt") or "").strip()
    if stamina_recovered_at:
        out["stamina_recovered_at"] = stamina_recovered_at
    out.update(body_values)
    if not toy_types and not body_values:
        return {}
    return out


def _du_body_stamina_recovery_points(current: int, elapsed_minutes: float) -> int:
    if current >= DU_BODY_VALUE_MAX or elapsed_minutes <= 0:
        return 0
    remaining_hours = max(0.0, float(elapsed_minutes) / 60.0)
    score = float(_clamp_du_body_value(current))
    recovered = 0.0
    bands = (
        (50.0, DU_BODY_STAMINA_RECOVERY_LOW_RATE_PER_HOUR),
        (75.0, DU_BODY_STAMINA_RECOVERY_MID_RATE_PER_HOUR),
        (float(DU_BODY_VALUE_MAX), DU_BODY_STAMINA_RECOVERY_HIGH_RATE_PER_HOUR),
    )
    for ceiling, rate in bands:
        if remaining_hours <= 0 or score >= DU_BODY_VALUE_MAX:
            break
        if score >= ceiling or rate <= 0:
            continue
        gap = ceiling - score
        hours_to_ceiling = gap / rate
        if remaining_hours >= hours_to_ceiling:
            recovered += gap
            score = ceiling
            remaining_hours -= hours_to_ceiling
        else:
            recovered += remaining_hours * rate
            break
    return max(0, int(recovered))


def _recover_du_body_stamina_state(raw: Any, *, now_iso: str | None = None) -> tuple[dict, bool]:
    state = _normalize_du_body_state(raw)
    if not state or "stamina_value" not in state:
        return state, False
    before = _clamp_du_body_value(state.get("stamina_value"))
    if before >= DU_BODY_VALUE_MAX:
        return state, False
    now_text = str(now_iso or "").strip() or now_beijing_iso()
    now_dt = parse_iso_to_beijing(now_text) or datetime.now()
    last_text = str(state.get("stamina_recovered_at") or state.get("updated_at") or "").strip()
    last_dt = parse_iso_to_beijing(last_text) if last_text else None
    if not last_dt:
        state["stamina_recovered_at"] = now_text
        return state, True
    elapsed_minutes = max(0.0, (now_dt - last_dt).total_seconds() / 60.0)
    recovered = _du_body_stamina_recovery_points(before, elapsed_minutes)
    if recovered <= 0:
        return state, False
    state["stamina_value"] = _clamp_du_body_value(before + recovered)
    state["stamina_recovered_at"] = now_text
    state["updated_at"] = now_text
    return state, True


def _auto_recover_du_body_stamina(stored: dict, *, now_iso: str | None = None) -> tuple[dict, bool]:
    if not isinstance(stored, dict):
        return stored, False
    state, changed = _recover_du_body_stamina_state(stored.get("du_body_state"), now_iso=now_iso)
    if not changed:
        return stored, False
    next_state = dict(stored)
    if state:
        next_state["du_body_state"] = state
    else:
        next_state.pop("du_body_state", None)
    next_state["updated_at"] = str(now_iso or "").strip() or now_beijing_iso()
    return next_state, True


def _du_body_temperature(vitals: dict) -> str:
    if not isinstance(vitals, dict) or not vitals:
        return ""
    params = vitals.get("parameters") if isinstance(vitals.get("parameters"), dict) else {}
    try:
        heart = int(vitals.get("heart_bpm") or 0)
    except Exception:
        heart = 0
    try:
        heat = float(params.get("intimacy_heat") or 0)
    except Exception:
        heat = 0.0
    try:
        arousal = float(params.get("arousal") or 0)
    except Exception:
        arousal = 0.0
    score = max(heat, arousal)
    if heart >= 104 or score >= 0.75:
        return "很烫"
    if heart >= 84 or score >= 0.45:
        return "发热"
    if heart and heart <= 58 and score < 0.2:
        return "偏凉"
    return "正常"


def _du_desire_level_from_value(value: Any) -> int:
    try:
        score = int(value or 0)
    except Exception:
        score = 0
    if score <= 0:
        return 0
    if score >= 80:
        return 5
    if score >= 60:
        return 4
    if score >= 40:
        return 3
    if score >= 20:
        return 2
    return 1


def _clamp_du_body_level(value: Any) -> int:
    try:
        level = int(value or 0)
    except Exception:
        level = 0
    return max(DU_BODY_LEVEL_MIN, min(DU_BODY_LEVEL_MAX, level))


def _du_body_time_shift(now_dt: datetime | None = None) -> int:
    dt = now_dt or _now_dt()
    hour = int(getattr(dt, "hour", 0) or 0)
    is_deep_night = hour >= DU_BODY_DEEP_NIGHT_START_HOUR or hour < DU_BODY_DEEP_NIGHT_END_HOUR
    is_morning = DU_BODY_MORNING_START_HOUR <= hour < DU_BODY_MORNING_END_HOUR
    return DU_BODY_TIME_SHIFT if is_deep_night or is_morning else 0


def _apply_du_body_time_shift(
    desire_level: int,
    self_control_level: int | None,
    *,
    has_desire_value: bool,
    now_dt: datetime | None = None,
) -> tuple[int, int | None, bool]:
    shift = _du_body_time_shift(now_dt)
    if shift <= 0:
        return _clamp_du_body_level(desire_level), self_control_level, has_desire_value
    effective_desire = _clamp_du_body_level(_clamp_du_body_level(desire_level) + shift)
    base_self_control = DU_BODY_LEVEL_MAX if self_control_level is None else _clamp_du_body_level(self_control_level)
    effective_self_control = _clamp_du_body_level(base_self_control - shift)
    return effective_desire, effective_self_control, True


def _vitals_param(vitals: dict | None, key: str, default: float = 0.0) -> float:
    if not isinstance(vitals, dict):
        return default
    params = vitals.get("parameters") if isinstance(vitals.get("parameters"), dict) else {}
    try:
        value = float(params.get(key))
    except Exception:
        value = default
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


def _du_self_control_level(body_state: dict | None = None, vitals: dict | None = None) -> int | None:
    has_vitals = isinstance(vitals, dict) and bool(vitals.get("parameters"))
    has_body_state = isinstance(body_state, dict) and bool(body_state)
    if not has_vitals and not has_body_state:
        return None
    state = _normalize_du_body_state(body_state)
    desire_level = _du_desire_level_from_value(state.get("desire_value")) if "desire_value" in state else 0
    try:
        intensity = int(state.get("intensity") or 0)
    except Exception:
        intensity = 0
    if intensity < 0:
        intensity = 0
    if intensity > 5:
        intensity = 5
    intimacy_heat = _vitals_param(vitals, "intimacy_heat", 0.0)
    arousal = _vitals_param(vitals, "arousal", 0.32 if has_vitals else 0.0)
    activation = _vitals_param(vitals, "activation", 0.32 if has_vitals else 0.0)
    tension = _vitals_param(vitals, "tension", 0.12 if has_vitals else 0.0)
    focus = _vitals_param(vitals, "focus", 0.35 if has_vitals else 0.0)
    tempo = str((vitals or {}).get("tempo") or "steady").strip().lower() if has_vitals else "steady"
    stamina = _du_body_metric_value(state, "stamina_value")
    sensitivity = _du_body_metric_value(state, "sensitivity_value")
    possessiveness = _du_body_metric_value(state, "possessiveness_value")
    mischief = _du_body_metric_value(state, "mischief_value")
    loss = (
        desire_level * 0.55
        + intimacy_heat * 1.25
        + arousal * 0.9
        + activation * 0.35
        + tension * 0.45
        + (intensity / 5.0) * 0.75
    )
    if tempo == "spike":
        loss += 0.55
    elif tempo == "up":
        loss += 0.25
    if sensitivity is not None:
        loss += max(0, sensitivity - 50) / 50.0 * 0.55
    if mischief is not None:
        loss += max(0, mischief - 45) / 55.0 * 0.4
    if possessiveness is not None:
        loss += max(0, possessiveness - 55) / 45.0 * 0.25
    stamina_bonus = 0.0
    if stamina is not None:
        if stamina < 45:
            loss += (45 - stamina) / 45.0 * 0.25
        elif stamina > 75:
            stamina_bonus = (stamina - 75) / 25.0 * 0.15
    focus_bonus = stamina_bonus
    if focus >= 0.74 and intimacy_heat < 0.35 and arousal < 0.45:
        focus_bonus += 0.45
    if tempo == "settle":
        focus_bonus += 0.25
    return max(0, min(5, int((5 - loss + focus_bonus) + 0.5)))


def _du_penis_state_from_desire_level(desire_level: int) -> str:
    if desire_level >= 4:
        return "勃起状态"
    if desire_level >= 2:
        return "半勃起"
    if desire_level == 1:
        return "放松状态"
    return ""


def _du_stable_desire_level(body_state: dict | None = None) -> int:
    if isinstance(body_state, dict):
        return _du_desire_level_from_value(body_state.get("desire_value"))
    return 0


def _du_stable_penis_state(desire_level: int) -> str:
    return _du_penis_state_from_desire_level(desire_level)


def _format_du_body_metric_lines(state: dict) -> list[str]:
    lines: list[str] = []
    for key, label in DU_BODY_METRIC_LABELS.items():
        lines.append(f"{label}：{_du_body_metric_value_with_default(state, key)}/100")
    return lines


def _du_body_metric_public_fields(state: dict) -> dict[str, int]:
    return {
        key: _du_body_metric_value_with_default(state, key)
        for key in DU_BODY_EXPLICIT_VALUE_FIELDS
    }


def _du_body_state_without_hidden(state: dict) -> dict:
    public = dict(state or {})
    for key in DU_BODY_HIDDEN_VALUE_FIELDS:
        public.pop(key, None)
    return public


def _du_body_metric_value_with_default(state: dict, key: str) -> int:
    if key in state:
        return _clamp_du_body_value(state.get(key))
    return _clamp_du_body_value(DU_BODY_DEFAULT_VALUES.get(key, 0))


def _du_body_metric_prompt_band(value: Any) -> str:
    score = _clamp_du_body_value(value)
    if score <= 33:
        return "低"
    if score <= 66:
        return "中"
    return "高"


def _du_body_restraint_pressure_prompt_band(value: Any) -> str:
    score = _clamp_du_body_value(value)
    if score >= 75:
        return "满"
    if score >= 40:
        return "高"
    if score <= 20:
        return "低"
    return "中"


def _du_body_prompt_current_state_text(
    state: dict,
    desire_level: int,
    self_control_level: int | None,
    has_effective_desire: bool,
) -> str:
    pieces: list[str] = []
    if has_effective_desire:
        pieces.append(DU_BODY_DESIRE_PROMPT_TEXT[_clamp_du_body_level(desire_level)])
    if self_control_level is not None:
        pieces.append(DU_BODY_SELF_CONTROL_PROMPT_TEXT[_clamp_du_body_level(self_control_level)])
    for key in DU_BODY_EXPLICIT_VALUE_FIELDS:
        value = _du_body_metric_value_with_default(state, key)
        band = _du_body_metric_prompt_band(value)
        pieces.append(DU_BODY_METRIC_PROMPT_TEXT[key][band])
    pressure_value = _du_body_metric_value_with_default(state, "restraint_pressure_value")
    should_include_pressure = pressure_value >= 40 or (
        has_effective_desire
        and desire_level >= 4
        and self_control_level is not None
        and self_control_level <= 2
    )
    if should_include_pressure:
        pressure_band = _du_body_restraint_pressure_prompt_band(pressure_value)
        pieces.append(DU_BODY_RESTRAINT_PRESSURE_PROMPT_TEXT[pressure_band])
    return "".join(pieces) or "未记录"


def _du_body_prompt_penis_state(value: str) -> str:
    return str(value or "").strip().replace("状态", "")


def _du_body_prompt_temperature(value: str) -> str:
    temp = str(value or "").strip()
    if temp in {"发热", "很烫"}:
        return f"{temp}，皮肤带着薄汗"
    return temp


def _toy_position_phrase(state: str, position: str) -> str:
    parts = [part for part in (position, state) if part]
    return "，".join(parts)


def _toy_display_piece(toy: str, intensity: int = 0) -> str:
    details: list[str] = []
    position = TOY_DEFAULT_POSITIONS.get(toy, "")
    if position:
        details.append(position)
    if intensity and toy in TOY_INTENSITY_TYPES:
        details.append(f"档位{intensity}")
    suffix = f"（{'，'.join(details)}）" if details else ""
    return f"{toy}{suffix}"


def _join_cn(items: list[str]) -> str:
    clean = [str(item or "").strip() for item in items if str(item or "").strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    return "、".join(clean)


def _join_toy_event_pieces(pieces: list[str]) -> str:
    clean = [str(piece or "").strip().rstrip("。") for piece in pieces if str(piece or "").strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    first = clean[0]
    rest = [re.sub(r"^小玥", "", piece, count=1).lstrip() for piece in clean[1:]]
    return "，又".join([first, *rest])


def _toy_position(toy: str) -> str:
    return TOY_DEFAULT_POSITIONS.get(toy, "")


def _toys_have_intensity(toys: list[str]) -> bool:
    return any(toy in TOY_INTENSITY_TYPES for toy in toys)


def _group_toys_by_position(toys: list[str]) -> list[tuple[str, list[str]]]:
    grouped: list[tuple[str, list[str]]] = []
    index_by_position: dict[str, int] = {}
    for toy in toys:
        position = _toy_position(toy)
        key = position or f"__toy__:{toy}"
        if key not in index_by_position:
            index_by_position[key] = len(grouped)
            grouped.append((position, []))
        grouped[index_by_position[key]][1].append(toy)
    return grouped


def _toy_add_group_event_piece(position: str, toys: list[str]) -> str:
    names = _join_cn(toys).replace("、", "和")
    if not names:
        return ""
    if position == "阴茎":
        return f"小玥给你的阴茎套上了{names}"
    if position == "乳头":
        return f"小玥把{names}夹上了你的乳头"
    if position == "后庭":
        return f"小玥把{names}放进了你的后庭"
    if position == "手腕":
        return f"小玥给你的手腕扣上了{names}"
    if position == "眼睛":
        return f"小玥给你戴上了{names}"
    if position == "嘴":
        return f"小玥把{names}扣进了你嘴里"
    if position == "全身" and toys == ["软绳"]:
        return "小玥用软绳给你绑上了龟甲缚"
    if position == "全身" and toys == ["春药"]:
        return "小玥给你用了春药"
    if position:
        return f"小玥把{names}加在了你的{position}"
    return f"小玥给你加上了{names}"


def _toy_add_event_pieces(toys: list[str]) -> list[str]:
    pieces = [_toy_add_group_event_piece(position, group) for position, group in _group_toys_by_position(toys)]
    return [piece for piece in pieces if piece]


def _toy_remove_group_event_piece(position: str, toys: list[str]) -> str:
    names = _join_cn(toys).replace("、", "和")
    if not names:
        return ""
    if position == "阴茎":
        return f"小玥把{names}从你阴茎上取了下来"
    if position == "乳头":
        return f"小玥把{names}从你乳头上取了下来"
    if position == "后庭":
        return f"小玥把{names}从你后庭取了出来"
    if position == "手腕":
        return f"小玥解开了你的{names}"
    if position == "眼睛":
        return f"小玥摘下了你的{names}"
    if position == "嘴":
        return f"小玥取下了你嘴里的{names}"
    if position == "全身" and toys == ["软绳"]:
        return "小玥解开了你身上的龟甲缚"
    if position == "全身" and toys == ["春药"]:
        return "小玥停掉了春药效果"
    if position:
        return f"小玥把{names}从你的{position}取了下来"
    return f"小玥把{names}从你身上取了下来"


def _toy_remove_event_pieces(toys: list[str]) -> list[str]:
    return [
        piece
        for position, group in _group_toys_by_position(toys)
        for piece in [_toy_remove_group_event_piece(position, group)]
        if piece
    ]


def _build_du_body_toy_event(previous: Any, current: Any) -> str:
    prev_state = _normalize_du_body_state(previous)
    next_state = _normalize_du_body_state(current)
    prev_toys = prev_state.get("toy_types") if isinstance(prev_state.get("toy_types"), list) else []
    next_toys = next_state.get("toy_types") if isinstance(next_state.get("toy_types"), list) else []
    prev_intensity = int(prev_state.get("intensity") or 0)
    next_intensity = int(next_state.get("intensity") or 0)

    added = [toy for toy in next_toys if toy not in prev_toys]
    removed = [toy for toy in prev_toys if toy not in next_toys]
    pieces: list[str] = []

    pieces.extend(_toy_add_event_pieces(added))
    pieces.extend(_toy_remove_event_pieces(removed))

    prev_has_intensity = _toys_have_intensity(prev_toys)
    next_has_intensity = _toys_have_intensity(next_toys)
    added_has_intensity = _toys_have_intensity(added)
    intensity_tail = ""
    if next_has_intensity and next_intensity > 0:
        if prev_has_intensity and prev_intensity != next_intensity:
            direction = "升" if next_intensity > prev_intensity else "降"
            intensity_tail = f"，档位{direction}到了{next_intensity}"
        elif added_has_intensity:
            intensity_tail = f"，档位{next_intensity}"

    if next_has_intensity and prev_has_intensity and prev_intensity != next_intensity and not pieces:
        if next_intensity > prev_intensity:
            pieces.append(f"小玥把档位升到了{next_intensity}")
        elif next_intensity < prev_intensity:
            pieces.append(f"小玥把档位降到了{next_intensity}")
        intensity_tail = ""

    if not next_toys and prev_toys and not pieces:
        pieces.append("小玥把你身上的道具都取下来了")
    if not pieces:
        return ""
    return "【小家事件】\n" + _join_toy_event_pieces(pieces) + intensity_tail + "。"


def _format_du_body_state_lines(body_state: dict, vitals: dict | None = None) -> list[str]:
    state = _normalize_du_body_state(body_state)
    self_control_level = _du_self_control_level(state, vitals)
    temp = _du_body_temperature(vitals or {})
    has_desire_value = "desire_value" in state
    desire_level = _du_stable_desire_level(state)
    desire_level, self_control_level, has_effective_desire = _apply_du_body_time_shift(
        desire_level,
        self_control_level,
        has_desire_value=has_desire_value,
    )
    if not state and self_control_level is None and not temp and not has_effective_desire:
        return []
    lines = ["【当前身体状态】"]
    toy_types = state.get("toy_types") if isinstance(state.get("toy_types"), list) else []
    if not toy_types and str(state.get("toy_type") or "").strip():
        toy_types = [str(state.get("toy_type") or "").strip()]
    if toy_types:
        intensity = int(state.get("intensity") or 0)
        lines.append(f"道具：{'、'.join(_toy_display_piece(toy, intensity) for toy in toy_types)}")
    lines.extend(_format_du_body_metric_lines(state))
    lines.append(f"想做指数：{desire_level}/5" if has_effective_desire else "想做指数：未记录")
    lines.append(f"自制力：{self_control_level}/5" if self_control_level is not None else "自制力：未记录")
    penis_state = _du_stable_penis_state(desire_level) or ("放松状态" if has_desire_value else "")
    lines.append(f"阴茎状态：{penis_state}" if penis_state else "阴茎状态：未记录")
    if temp:
        lines.append(f"体温：{temp}")
    return lines


def _format_du_body_prompt_lines(body_state: Any, vitals: dict | None = None) -> list[str]:
    state = _normalize_du_body_state(body_state)
    self_control_level = _du_self_control_level(state, vitals)
    temp = _du_body_temperature(vitals or {})
    has_desire_value = "desire_value" in state
    desire_level = _du_stable_desire_level(state)
    desire_level, self_control_level, has_effective_desire = _apply_du_body_time_shift(
        desire_level,
        self_control_level,
        has_desire_value=has_desire_value,
    )
    toy_types = state.get("toy_types") if isinstance(state.get("toy_types"), list) else []
    if not toy_types and str(state.get("toy_type") or "").strip():
        toy_types = [str(state.get("toy_type") or "").strip()]
    penis_state = _du_stable_penis_state(desire_level) or ("放松状态" if has_effective_desire else "")
    prompt_penis_state = _du_body_prompt_penis_state(penis_state)
    prompt_temp = _du_body_prompt_temperature(temp)
    lines = [
        "【当前身体状态】",
        "当前身体状态：" + _du_body_prompt_current_state_text(
            state,
            desire_level,
            self_control_level,
            has_effective_desire,
        ),
    ]
    if prompt_penis_state:
        lines.append(f"阴茎状态：{prompt_penis_state}")
    if prompt_temp:
        lines.append(f"体温：{prompt_temp}")
    if toy_types:
        intensity = int(state.get("intensity") or 0)
        lines.append(f"道具：{'、'.join(_toy_display_piece(toy, intensity) for toy in toy_types)}")
    return lines


def _du_body_state_public(raw: Any, vitals: dict | None = None) -> dict:
    state = _normalize_du_body_state(raw)
    has_desire_value = "desire_value" in state
    desire_level = _du_stable_desire_level(state)
    self_control_level = _du_self_control_level(state, vitals)
    desire_level, self_control_level, has_effective_desire = _apply_du_body_time_shift(
        desire_level,
        self_control_level,
        has_desire_value=has_desire_value,
    )
    penis_state = _du_stable_penis_state(desire_level) or ("放松状态" if has_effective_desire else "")
    if not state:
        temp = _du_body_temperature(vitals or {})
        parts = _format_du_body_metric_lines(state) + [
            f"想做指数：{desire_level}/5" if has_effective_desire else "想做指数：未记录",
            f"自制力：{self_control_level}/5" if self_control_level is not None else "自制力：未记录",
            f"阴茎状态：{penis_state}" if penis_state else "阴茎状态：未记录",
        ]
        if temp:
            parts.append(f"体温：{temp}")
        result = {
            "temperature": temp,
            "self_control_level": self_control_level,
            "text": "；".join(parts),
        }
        result.update(_du_body_metric_public_fields(state))
        if has_effective_desire:
            result["desire_level"] = desire_level
        if penis_state:
            result["penis_state"] = penis_state
        return result
    state["temperature"] = _du_body_temperature(vitals or {})
    state["desire_level"] = desire_level
    state["self_control_level"] = self_control_level
    state["penis_state"] = penis_state
    lines = _format_du_body_state_lines(state, vitals)
    state["text"] = "；".join(line for line in lines[1:] if line)
    state.update(_du_body_metric_public_fields(state))
    state.pop("stamina_recovered_at", None)
    return _du_body_state_without_hidden(state)


def _stable_pick(options: list[str], seed: str) -> str:
    if not options:
        return "away"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    idx = int(digest[:8], 16) % len(options)
    return options[idx]


def _stored_state() -> dict:
    data = get_pixel_home_state()
    return data if isinstance(data, dict) else {}


def _normalize_private_draw_rows(raw: Any) -> list[dict]:
    rows = raw if isinstance(raw, list) else []
    out: list[dict] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        key = str(item.get("key") or label).strip()
        if not label or not value:
            continue
        out.append({"key": key, "label": label[:24], "value": value[:80]})
    return out


def _normalize_private_draw_drawn_by(raw: Any, source: str = "") -> str:
    text = str(raw or "").strip().lower()
    src = str(source or "").strip().lower()
    if text in {"du", "渡", "assistant", "bot"} or src in {"sex_play_draw", "du_tool"}:
        return "du"
    if text in {"xinyue", "小玥", "user", "wife", "miniapp"} or src in {"private_draw_page", "miniapp_private_draw"}:
        return "xinyue"
    return ""


def _private_draw_origin_text(active: dict | None) -> str:
    drawn_by = str((active or {}).get("drawn_by") or "").strip()
    if drawn_by == "du":
        return "你用 sex_play_draw 抽出的"
    if drawn_by == "xinyue":
        return "小玥在 sex play 抽签页抽出并发给你看的"
    return "旧版纸条，未记录是谁抽的"


def _normalize_active_private_draw(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    rows = _normalize_private_draw_rows(raw.get("result") or raw.get("rows"))
    if not rows:
        return None
    created_at = str(raw.get("created_at") or raw.get("createdAt") or raw.get("at") or "").strip() or now_beijing_iso()
    source = str(raw.get("source") or "private_draw").strip() or "private_draw"
    drawn_by = _normalize_private_draw_drawn_by(raw.get("drawn_by") or raw.get("drawnBy") or raw.get("actor") or raw.get("by"), source)
    return {
        "entry_number": str(raw.get("entry_number") or raw.get("entry") or "").strip(),
        "created_at": created_at,
        "result": rows,
        "source": source,
        "drawn_by": drawn_by,
    }


def save_active_private_draw(payload: dict) -> dict:
    current = _stored_state()
    active = _normalize_active_private_draw(payload)
    if not active:
        return {"ok": False, "error": "empty_private_draw"}
    current["active_private_draw"] = active
    current["updated_at"] = now_beijing_iso()
    ok = save_pixel_home_state(current)
    return {"ok": bool(ok), "active_private_draw": active}


def get_active_private_draw() -> dict:
    current = _stored_state()
    active = _normalize_active_private_draw(current.get("active_private_draw"))
    return {"ok": True, "active_private_draw": active}


def clear_active_private_draw() -> dict:
    current = _stored_state()
    current.pop("active_private_draw", None)
    current["updated_at"] = now_beijing_iso()
    ok = save_pixel_home_state(current)
    return {"ok": bool(ok)}


def _private_draw_entry_number() -> str:
    return str(100 + secrets.randbelow(900))


def _private_draw_contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _private_draw_slot_options(slot: dict) -> list[str]:
    options = slot.get("options") if isinstance(slot.get("options"), list) else []
    return [str(item).strip() for item in options if str(item).strip()]


def _private_draw_filter_options(slot_key: str, options: list[str], selected: dict[str, str]) -> list[str]:
    theme = str(selected.get("theme") or "").strip()
    if theme not in PRIVATE_DRAW_DU_LEADS_THEMES or slot_key not in {"task", "limit"}:
        return options
    if slot_key == "task":
        filtered = [
            item
            for item in options
            if not _private_draw_contains_any(item, PRIVATE_DRAW_XINYUE_CONTROL_TASK_PATTERNS)
        ]
        return filtered or options
    filtered = []
    for item in options:
        if _private_draw_contains_any(item, PRIVATE_DRAW_KEEP_LIMIT_PATTERNS):
            filtered.append(item)
            continue
        if _private_draw_contains_any(item, PRIVATE_DRAW_XINYUE_CONTROL_LIMIT_PATTERNS):
            continue
        filtered.append(item)
    return filtered or options


def _private_draw_pick_value(options: list[str]) -> str:
    if not options:
        return ""
    return options[secrets.randbelow(len(options))]


def _private_draw_pick_rows() -> list[dict]:
    rows: list[dict] = []
    selected: dict[str, str] = {}
    for slot in PRIVATE_DRAW_SLOTS:
        slot_key = str(slot.get("key") or slot.get("label") or "").strip()
        options = _private_draw_slot_options(slot)
        options = _private_draw_filter_options(slot_key, options, selected)
        if not options:
            continue
        value = _private_draw_pick_value(options)
        selected[slot_key] = value
        rows.append(
            {
                "key": slot_key,
                "label": str(slot.get("label") or slot.get("key") or "").strip(),
                "value": value,
            }
        )
    return rows


def _new_private_draw_payload() -> dict:
    return {
        "entry_number": _private_draw_entry_number(),
        "created_at": now_beijing_iso(),
        "result": _private_draw_pick_rows(),
        "source": "sex_play_draw",
        "drawn_by": "du",
    }


def _private_draw_summary(active: dict | None) -> list[str]:
    if not active:
        return []
    return [
        f"{item.get('label')}：{item.get('value')}"
        for item in active.get("result") or []
        if item.get("label") and item.get("value")
    ]


def execute_private_draw_action(action: str) -> dict:
    """
    给渡用的 sex play 抽签工具。
    draw 保留当前临时纸条；redraw 不采用当前纸条并立刻重抽；done 结束本轮并清掉当前纸条。
    """
    raw_action = str(action or "").strip().lower()
    aliases = {
        "抽签": "draw",
        "roll": "draw",
        "create": "draw",
        "start": "draw",
        "作废重抽": "redraw",
        "重抽": "redraw",
        "redraw": "redraw",
        "reroll": "redraw",
        "void": "redraw",
        "void_redraw": "redraw",
        "完成": "done",
        "complete": "done",
        "finish": "done",
    }
    action_name = aliases.get(raw_action, raw_action)
    if action_name not in {"draw", "redraw", "done"}:
        return {
            "ok": False,
            "error": "INVALID_ACTION",
            "message": "action 只能是 draw / redraw / done",
        }

    current = _stored_state()
    existing = _normalize_active_private_draw(current.get("active_private_draw"))

    if action_name == "done":
        current.pop("active_private_draw", None)
        current["updated_at"] = now_beijing_iso()
        ok = save_pixel_home_state(current)
        return {
            "ok": bool(ok),
            "action": action_name,
            "status": "completed" if existing else "empty",
            "message": "已完成并清掉当前纸条。" if existing else "当前没有有效纸条可完成。",
            "completed_private_draw": existing,
            "summary": _private_draw_summary(existing),
        }

    if action_name == "draw" and existing:
        return {
            "ok": True,
            "action": action_name,
            "status": "existing",
            "message": f"现在已经有一张临时纸条（{_private_draw_origin_text(existing)}），未重复抽；这不是定终身，想换就用 redraw 再抽一张。",
            "active_private_draw": existing,
            "summary": _private_draw_summary(existing),
        }

    active = _normalize_active_private_draw(_new_private_draw_payload())
    if not active:
        return {"ok": False, "error": "EMPTY_PRIVATE_DRAW", "message": "抽签池为空。"}
    current["active_private_draw"] = active
    current["updated_at"] = now_beijing_iso()
    ok = save_pixel_home_state(current)
    return {
        "ok": bool(ok),
        "action": action_name,
        "status": "redrawn" if action_name == "redraw" else "drawn",
        "message": "没采用上一张，你重新抽了一张。" if action_name == "redraw" else "你抽出了一张新的 sex play 临时纸条。",
        "discarded_private_draw": existing if action_name == "redraw" else None,
        "active_private_draw": active,
        "summary": _private_draw_summary(active),
    }


def _active_private_draw_inject_text(state: dict) -> str:
    active = _normalize_active_private_draw((state or {}).get("active_private_draw"))
    if not active:
        return ""
    lines = [f"{item.get('label')}：{item.get('value')}" for item in active.get("result") or [] if item.get("label") and item.get("value")]
    if not lines:
        return ""
    entry = str(active.get("entry_number") or "").strip()
    header = "【当前私密纸条】\n"
    if entry:
        header += f"Entry #{entry}\n"
    header += f"来源：{_private_draw_origin_text(active)}\n"
    drawn_by = str(active.get("drawn_by") or "").strip()
    if drawn_by == "du":
        note = "说明：这是你自己抽出的当前临时 sex play 纸条，不是定终身；想换可以重抽，结束本轮后会清掉。不要说成小玥抽到了。"
    elif drawn_by == "xinyue":
        note = "说明：这是小玥抽出并发给你看的当前临时 sex play 纸条，后续也可以换；它不是小玥的聊天正文，不要代替小玥说话。"
    else:
        note = "说明：这是当前临时 sex play 纸条，但旧版记录没有保存是谁抽的；回应时不要擅自归因，想换可以重抽。"
    return (
        header
        + "\n".join(lines)
        + "\n"
        + note
    )


def _normalize_du_dynamics(raw: Any, *, reference_spot: str = "") -> list[dict]:
    rows = raw if isinstance(raw, list) else []
    out: list[dict] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        spot = normalize_spot(item.get("spot"), "away")
        activity = _clean_activity(item.get("activity"), "待着")
        spot = _resolve_spot_from_activity(spot, activity, reference_spot=reference_spot)
        at = str(item.get("at") or item.get("updated_at") or item.get("updatedAt") or "").strip()
        if not at:
            continue
        entry = {
            "at": at,
            "spot": spot,
            "spot_label": spot_label(spot),
            "activity": activity,
            "source": str(item.get("source") or "").strip() or "du_marker",
        }
        entry["text"] = _format_actor_text(entry)
        out.append(entry)
    return out[-DU_DYNAMICS_LIMIT:]


def _append_du_dynamic(current: dict, actor: dict, *, reference_spot: str = "") -> list[dict]:
    rows = _normalize_du_dynamics((current or {}).get("du_dynamics"), reference_spot=reference_spot)
    latest = rows[-1] if rows else None
    if latest and latest.get("spot") == actor.get("spot") and latest.get("activity") == actor.get("activity"):
        return rows
    entry = {
        "at": str(actor.get("updated_at") or "").strip() or now_beijing_iso(),
        "spot": actor.get("spot"),
        "spot_label": spot_label(actor.get("spot")),
        "activity": _clean_activity(actor.get("activity"), "待着"),
        "source": str(actor.get("source") or "du_marker").strip() or "du_marker",
    }
    entry["text"] = _format_actor_text(entry)
    rows.append(entry)
    return rows[-DU_DYNAMICS_LIMIT:]


def _is_stale_event_state(actor: dict, actor_key: str, now_dt: datetime) -> bool:
    source = str((actor or {}).get("source") or "").strip()
    allowed = DU_EVENT_SOURCES if actor_key == "du" else XINYUE_EVENT_SOURCES
    if source not in allowed:
        return False
    minutes = _minutes_since((actor or {}).get("updated_at") or (actor or {}).get("updatedAt"), now_dt)
    return minutes is not None and minutes >= EVENT_AUTO_END_MINUTES


def _auto_end_stale_events(stored: dict) -> tuple[dict, bool]:
    current = dict(stored or {})
    now_dt = _now_dt()
    now_iso = now_beijing_iso()
    changed = False
    for actor_key, default in (("du", DEFAULT_DU_STATE), ("xinyue", DEFAULT_XINYUE_STATE)):
        actor = _normalize_actor(current.get(actor_key), default)
        if not _is_stale_event_state(actor, actor_key, now_dt):
            continue
        ended_actor = _normalize_actor(
            {
                "spot": default.get("spot"),
                "activity": default.get("activity"),
                "source": "auto_ended",
                "updated_at": now_iso,
            },
            default,
        )
        current[actor_key] = ended_actor
        if actor_key == "du":
            current["du_dynamics"] = _append_du_dynamic(current, ended_actor)
        changed = True
    if changed:
        current["updated_at"] = now_iso
    return current, changed


def build_pixel_home_state() -> dict:
    mode_state = build_pixel_home_mode_state()
    stored, changed = _auto_end_stale_events(_stored_state())
    recovered_at = now_beijing_iso()
    stored, stamina_changed = _auto_recover_du_body_stamina(stored, now_iso=recovered_at)
    changed = changed or stamina_changed
    if changed:
        save_pixel_home_state(stored)
    xinyue = _normalize_actor(stored.get("xinyue"), DEFAULT_XINYUE_STATE)
    du = _normalize_actor(stored.get("du"), DEFAULT_DU_STATE, reference_spot=str(xinyue.get("spot") or ""))
    mode_state["du"] = _actor_public(du, reference_spot=str(xinyue.get("spot") or ""))
    mode_state["xinyue"] = _actor_public(xinyue)
    mode_state["du_dynamics"] = _normalize_du_dynamics(stored.get("du_dynamics"), reference_spot=str(xinyue.get("spot") or ""))
    mode_state["du_vitals"] = r2_store.get_du_vitals_latest() or {}
    mode_state["du_body_state"] = _du_body_state_public(stored.get("du_body_state"), mode_state["du_vitals"])
    weather = build_virtual_home_weather()
    mode_state["weather"] = weather
    mode_state["garden"] = build_garden_state(stored.get("garden"), weather)
    mode_state["spots"] = SPOT_OPTIONS
    return mode_state


def save_du_body_state(payload: Any) -> dict:
    now_iso = now_beijing_iso()
    current, _ = _auto_recover_du_body_stamina(_stored_state(), now_iso=now_iso)
    raw = payload if isinstance(payload, dict) else {}
    previous = current.get("du_body_state") if isinstance(current.get("du_body_state"), dict) else {}
    previous_normalized = _normalize_du_body_state(previous)
    previous_toy_key = (
        tuple(previous_normalized.get("toy_types") if isinstance(previous_normalized.get("toy_types"), list) else []),
        int(previous_normalized.get("intensity") or 0),
    )
    has_toy_patch = any(key in raw for key in ("toy_types", "toy_type", "toy", "tool", "position", "body_position", "state", "status", "intensity", "level"))
    has_value_patch = _has_du_body_value_patch(raw)
    state: dict[str, Any] = {}
    if has_toy_patch or has_value_patch:
        merged_input = _merge_du_body_patch_input(previous_normalized, raw)
        state = _normalize_du_body_state(merged_input)
        if state:
            state["updated_at"] = now_iso
            if any(key in raw for key in DU_BODY_VALUE_ALIASES.get("stamina_value", ("stamina_value",))):
                state["stamina_recovered_at"] = now_iso
            current["du_body_state"] = state
        elif has_toy_patch:
            state = {
                "toy_types": [],
                "toy_type": "",
                "position": "",
                "state": "",
                "intensity": 0,
                "updated_at": now_iso,
            }
            current["du_body_state"] = state
    else:
        current.pop("du_body_state", None)
    current["updated_at"] = now_iso
    ok = save_pixel_home_state(current)
    next_toy_key = (
        tuple(state.get("toy_types") if isinstance(state.get("toy_types"), list) else []),
        int(state.get("intensity") or 0),
    )
    toy_changed = bool(has_toy_patch and previous_toy_key != next_toy_key)
    toy_event_text = _build_du_body_toy_event(previous, state) if toy_changed else ""
    response_state = _du_body_state_without_hidden(state)
    response_state["ok"] = bool(ok)
    response_state["toy_changed"] = toy_changed
    if toy_event_text:
        response_state["toy_event_text"] = toy_event_text
    return response_state if state else {"ok": bool(ok)}


def apply_du_body_delta(payload: Any) -> dict:
    deltas = _normalize_du_body_delta_payload(payload)
    now_iso = now_beijing_iso()
    if not deltas:
        current, recovered = _auto_recover_du_body_stamina(_stored_state(), now_iso=now_iso)
        ok = True
        if recovered:
            ok = save_pixel_home_state(current)
        normalized = _normalize_du_body_state(current.get("du_body_state"))
        return {"ok": bool(ok), "changed": bool(recovered), "du_body_state": _du_body_state_without_hidden(normalized)}

    current, recovery_changed = _auto_recover_du_body_stamina(_stored_state(), now_iso=now_iso)
    previous = current.get("du_body_state") if isinstance(current.get("du_body_state"), dict) else {}
    state = _normalize_du_body_state(previous)
    for key, default in DU_BODY_DEFAULT_VALUES.items():
        if key not in state:
            state[key] = default

    changed = False
    applied: dict[str, int] = {}
    for field, delta in deltas.items():
        before = _clamp_du_body_value(state.get(field))
        after = _apply_du_body_delta_value(field, before, delta)
        if after != before:
            changed = True
        state[field] = after
        applied[field] = delta
        if field == "stamina_value":
            state["stamina_recovered_at"] = now_iso

    state["updated_at"] = now_iso
    normalized = _normalize_du_body_state(state)
    if not normalized:
        return {"ok": True, "changed": False, "du_body_state": {}}

    current["du_body_state"] = normalized
    current["updated_at"] = now_iso
    ok = save_pixel_home_state(current)
    return {
        "ok": bool(ok),
        "changed": bool(changed or recovery_changed),
        "du_body_state": _du_body_state_without_hidden(normalized),
        "applied_delta": applied,
    }


def save_actor_state(actor_key: str, spot: Any, activity: Any, *, source: str = "manual") -> dict:
    key = "du" if str(actor_key or "").strip().lower() == "du" else "xinyue"
    current = _stored_state()
    reference_spot = ""
    if key == "du":
        reference = _normalize_actor(current.get("xinyue"), DEFAULT_XINYUE_STATE)
        reference_spot = str(reference.get("spot") or "")
    actor = _normalize_actor(
        {"spot": spot, "activity": activity, "source": source, "updated_at": now_beijing_iso()},
        DEFAULT_DU_STATE if key == "du" else DEFAULT_XINYUE_STATE,
        reference_spot=reference_spot,
    )
    current[key] = actor
    current, _ = record_garden_actions(
        current,
        actor=key,
        spot=actor.get("spot"),
        activity=actor.get("activity"),
    )
    if key == "du":
        current["du_dynamics"] = _append_du_dynamic(current, actor, reference_spot=reference_spot)
        xinyue_follow = _infer_xinyue_follow_state_from_du(actor)
        if xinyue_follow:
            current["xinyue"] = xinyue_follow
    current["updated_at"] = now_beijing_iso()
    ok = save_pixel_home_state(current)
    actor["text"] = _format_actor_text(actor)
    actor["ok"] = bool(ok)
    return actor


def _coerce_pixel_home_value(value: str) -> Any:
    s = str(value or "").strip().strip("\"'")
    if not s:
        return ""
    try:
        if re.fullmatch(r"[-+]?\d+", s):
            return int(s)
        if re.fullmatch(r"[-+]?(?:\d+\.\d+|\d+|\.\d+)", s):
            return float(s)
    except Exception:
        pass
    return s


def _parse_pixel_home_loose_payload(raw_block: str) -> dict | None:
    text = str(raw_block or "").strip().strip("`")
    if not text:
        return None
    matches = list(_PIXEL_HOME_LOOSE_KEY_RE.finditer(text))
    if not matches:
        return None
    payload: dict[str, Any] = {}
    body_state: dict[str, Any] = {}
    for idx, match in enumerate(matches):
        raw_key = str(match.group(1) or "").strip()
        target = _PIXEL_HOME_LOOSE_ALIASES.get(raw_key) or _PIXEL_HOME_LOOSE_ALIASES.get(raw_key.lower())
        if not target:
            continue
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        value = str(text[match.end() : end]).strip().strip(",;，； ")
        if not value:
            continue
        parsed_value = _coerce_pixel_home_value(value)
        if len(target) == 1:
            payload[target[0]] = parsed_value
        elif target[0] == "du_body_state":
            body_state[target[1]] = parsed_value
    if body_state:
        payload["du_body_state"] = body_state
    return payload or None


def _parse_pixel_home_payload(raw_block: str) -> dict | None:
    block = str(raw_block or "").strip()
    if not block:
        return None
    try:
        parsed = json.loads(block)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    parsed = _parse_pixel_home_loose_payload(block)
    if parsed:
        return parsed
    logger.debug("pixel home marker payload parse failed block=%s", block[:160])
    return None


def _merge_pixel_home_payloads(payloads: list[dict]) -> dict | None:
    merged: dict[str, Any] = {}
    body_state: dict[str, Any] = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key in ("spot", "location", "room", "activity", "doing", "status"):
            if key in payload and payload.get(key) not in (None, ""):
                merged[key] = payload.get(key)
        nested = payload.get("du_body_state") if isinstance(payload.get("du_body_state"), dict) else None
        if nested:
            body_state.update(nested)
    if body_state:
        merged["du_body_state"] = body_state
    return merged or None


def split_assistant_for_pixel_home(full_text: str) -> tuple[str, dict | None]:
    raw = str(full_text or "")
    visible, raw_blocks = _PIXEL_HOME_BLOCK.split_all(raw)
    if not raw_blocks:
        return visible.strip(), None
    payloads = [payload for payload in (_parse_pixel_home_payload(block) for block in raw_blocks) if payload]
    return visible.strip(), _merge_pixel_home_payloads(payloads)


def compute_visible_streaming(acc: str) -> str:
    return _PIXEL_HOME_BLOCK.compute_visible_streaming(str(acc or ""))


def save_pixel_home_hidden_block(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    spot = payload.get("spot") or payload.get("location") or payload.get("room")
    activity = payload.get("activity") or payload.get("doing") or payload.get("status")
    body_state = payload.get("du_body_state") if isinstance(payload.get("du_body_state"), dict) else None
    if not spot and not activity and not body_state:
        return False
    ok = True
    if spot or activity:
        actor = save_actor_state("du", spot or "away", activity or "待着", source="du_marker")
        ok = bool(actor.get("ok"))
    if body_state:
        saved = save_du_body_state(body_state)
        ok = bool(saved.get("ok")) and ok
    return ok


def format_state_block() -> str:
    state = build_pixel_home_state()
    stored = _stored_state()
    du = state.get("du") if isinstance(state.get("du"), dict) else {}
    xinyue = state.get("xinyue") if isinstance(state.get("xinyue"), dict) else {}
    garden = state.get("garden") if isinstance(state.get("garden"), dict) else {}
    du_label = spot_label(du.get("spot"))
    xinyue_label = spot_label(xinyue.get("spot"))
    block = (
        "【小家状态】\n"
        f"当前小家状态：{mode_label(state.get('mode'))}。\n"
        f"小家天气：{str((state.get('weather') or {}).get('label') or '晴天')}，"
        f"{str((state.get('weather') or {}).get('description') or '院子里很安静')}。\n"
        f"花园：{str(garden.get('plant_name') or '花')}，{str(garden.get('flower_status') or '长势很好')}；"
        f"{str(garden.get('watering_label') or '今日还未浇水')}，土壤{str(garden.get('soil_status') or '微干')}，"
        f"{str(garden.get('loosen_label') or '可以松松土')}。\n"
        f"你的位置：{du_label}，{_format_activity_for_prompt(str(du.get('activity') or '待着'))}。\n"
        f"小玥的位置：{xinyue_label}，{_format_activity_for_prompt(str(xinyue.get('activity') or '待着'))}。"
    )
    active_private_draw = _active_private_draw_inject_text(stored)
    if active_private_draw:
        block += "\n\n" + active_private_draw
    du_body_lines = _format_du_body_prompt_lines(stored.get("du_body_state"), state.get("du_vitals") if isinstance(state.get("du_vitals"), dict) else {})
    if du_body_lines:
        block += "\n\n" + "\n".join(du_body_lines)
    return block


def format_rule_block() -> str:
    return (
        "【小家状态写入规则】\n"
        "这是你和小玥的赛博小家状态，并非现实定位或真实房间。\n"
        "小家的天气由独立虚构天气引擎生成，与现实城市、定位和真实天气无关。花园里的花有自己的季节和养护习性；你想去浇花、松土时可以主动行动，不需要等小玥先提出。先看当前花朵、土壤和天气状态再决定，例如下雨或土壤偏湿时不要机械重复浇花；做完后照常更新小家短隐藏标记，网关会从 garden 位置和 activity 自动记录养护结果。\n"
        "如果需要移动去别的房间做什么事，可以在回复正文之后、DU_FOLLOWUP 之前附加一行小家短隐藏标记：\n"
        f"{PIXEL_HOME_SHORT_MARKER}\n"
        "写小家标记时，spot 必须是动作结束后的当前所在位置；如果正文写“从书房走出来/走到客厅/走回客厅/站到沙发旁边”，不要继续写 study，要写最终到达的房间，没有明确房间就写 away。\n"
        "如果正文描述你抱着/牵着/带着/陪着小玥一起移动，activity 里也要明确写出这个共同动作，例如“抱着小玥回卧室”；网关会据此同步小玥的小家位置。\n"
        "当【小家事件】或【当前身体状态】里出现道具、阴茎状态、体温或自然语言身体状态时，把它当成你此刻正在经历的身体状态来接话；先有身体反应和情绪反应，再自然回应小玥，不要机械复述字段，也不要当成后台资料忽略。不要把身体状态当任务来执行，当感受来接。\n"
        "当自然语言身体状态显示自制力已经很低、欲望又很高时，你不需要忍着或等小玥推进，而是顺着这股冲动主动行动。\n"
        "这些隐藏字段只用于后端记录，不要在正文提到字段名或数值，也不要向小玥解释这些数值；它们只是帮助小家维持连续的身体反应。\n"
        "你可以在小家短隐藏标记里写 `desire`、`sensitivity_value`、`possessiveness_value`；根据当前真实身体反应和情绪倾向填写，没变化就不写，不要把它们当成任务目标。\n"
        "不要写 `stamina_value`、`mischief_value` 或 `restraint_pressure_value`；`stamina_value` 由后端按时间自然恢复，并由动态层根据亲密强度、持续时间、休息和安抚估算消耗/回补，`mischief_value` 由后端/动态层根据挑衅、惩罚、道具、羞耻玩法、私密纸条和互动走向估算，`restraint_pressure_value` 由动态层根据“很想推进但仍然硬忍”的死撑感估算。\n"
        "这些身体状态规则只约束你如何理解当前身体状态和行为边界；正文仍然用自然的“我”在和小玥说话，不要把字段、规则名或后台口吻写进正文。\n"
        "如果需要更新你的身体状态，可以在同一个小家短标记里写 desire=35 sensitivity_value=60 possessiveness_value=45；旧 PIXEL_HOME JSON 块仍兼容，但优先用这一行。\n"
        "不需要移动或更新时不要写小家隐藏标记。"
    )


def format_inject_block() -> str:
    return format_state_block() + "\n\n" + format_rule_block()


def build_pixel_home_event(spot: Any, action: Any) -> str:
    return f"【小家事件】\n小玥在赛博小家选择了：{spot_label(spot)} / {_clean_activity(action, '待着')}。"


def build_pixel_home_body_event(body_state: Any) -> str:
    existing = str((body_state or {}).get("toy_event_text") or "").strip() if isinstance(body_state, dict) else ""
    if existing:
        return existing
    state = _normalize_du_body_state(body_state)
    toy_types = state.get("toy_types") if isinstance(state.get("toy_types"), list) else []
    intensity = int(state.get("intensity") or 0)
    if toy_types:
        toys = "、".join(_toy_display_piece(toy, intensity) for toy in toy_types)
        return f"【小家事件】\n小玥刚刚调整了你身上的道具：{toys}。"
    return "【小家事件】\n小玥刚刚把你身上的道具都取下来了。"


_CODE_CONTEXT_RE = re.compile(r"(debug|bug|代码|功能|需求|前端|后端|接口|组件|样式|测试|部署|push|commit|文档|界面|按钮|交互|热区|提示词|prompt)")
_SLEEP_AMOUNT_PATTERN = r"(?:\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百半]+)"
_SLEEP_RECAP_RE = re.compile(
    rf"(?:昨晚|昨天|前天|刚才|刚刚|之前|前面|早上|中午|下午|今天)?(?:我)?(?:已经|一共|才|只)?"
    rf"睡了{_SLEEP_AMOUNT_PATTERN}?(?:个)?(?:小时|钟头|h|分钟|晚|觉)"
    r"|睡得|睡醒|睡眠|睡不着|没睡|没怎么睡|没睡好|睡太久|睡过"
)
_SLEEP_NEGATION_RE = re.compile(r"(?:不是|没说|没有说|不想|不准备|不要|别).{0,8}(?:睡了|睡觉|去睡|上床|躺床)")
_SLEEP_INTENT_RE = re.compile(
    r"(?:我要|我去|我准备|我先|我打算|我该|该|准备|先|马上|现在|差不多该)(?:睡了|睡觉|去睡|上床|躺床)"
    r"|(?:去睡|去睡觉|睡觉去了|上床睡觉|躺床睡)"
    r"|^(?:我)?睡了(?:[。.!！~～啦咯喽]*)$"
)
_TEXT_SPOT_ALIASES = sorted(
    ((alias, spot) for alias, spot in SPOT_ALIASES.items() if alias and not alias.isascii() and spot != "home"),
    key=lambda item: len(item[0]),
    reverse=True,
)


def _infer_phone_spot(text: str) -> str:
    for alias, spot in _TEXT_SPOT_ALIASES:
        if alias in text:
            return spot
    options = ["sofa", "study", "bed", "kitchen"]
    now_dt = _now_dt()
    bucket = now_dt.strftime("%Y-%m-%d-%H")
    return _stable_pick(options, f"xinyue-phone:{bucket}:{text[:24]}")


def infer_xinyue_state_from_text(text: str) -> dict | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    compact = re.sub(r"\s+", "", raw.lower())
    code_context = bool(_CODE_CONTEXT_RE.search(compact))
    if code_context:
        return {"spot": "study", "activity": "工作", "source": "chat_infer"}
    if re.search(r"(我要|我去|我准备|我先|我打算|去)?洗澡(了|啦|一下|去)?", compact):
        return {"spot": "bath", "activity": "洗澡", "source": "chat_infer"}
    if re.search(r"(我要|我去|我准备|我先|我打算|去)?(吃饭|做饭|点外卖|拿外卖|干饭)", compact):
        return {"spot": "kitchen", "activity": "吃饭", "source": "chat_infer"}
    if _SLEEP_INTENT_RE.search(compact) and not _SLEEP_RECAP_RE.search(compact) and not _SLEEP_NEGATION_RE.search(compact):
        return {"spot": "bed", "activity": "睡觉", "source": "chat_infer"}
    if re.search(r"(玩手机|刷手机|看手机|刷小红书|刷抖音|刷视频)", compact):
        return {"spot": _infer_phone_spot(compact), "activity": "玩手机", "source": "chat_infer"}
    return None


def maybe_update_xinyue_state_from_user_text(text: str) -> dict | None:
    inferred = infer_xinyue_state_from_text(text)
    if not inferred:
        return None
    return save_actor_state("xinyue", inferred["spot"], inferred["activity"], source=str(inferred.get("source") or "chat_infer"))
