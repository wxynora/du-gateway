from __future__ import annotations

import json
import os
import random
import re
import shlex
import secrets
import threading
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except Exception:  # pragma: no cover - fcntl is available on the target Linux/macOS hosts.
    fcntl = None

from config import DATA_DIR
from utils.time_aware import now_beijing_iso


GAME_ID = "private_board"
DEFAULT_SAVE_PATH = DATA_DIR / GAME_ID / "default.json"
DEFAULT_BOARD_SIZE = 36
ACTORS = ("xinyue", "du")
SCHEMA_VERSION = 1

DU_VIEW_NAMES = {"xinyue": "小玥", "du": "我"}
PLAYER_VIEW_NAMES = {"xinyue": "我", "du": "渡"}

COMMAND_HINT = "可用命令：打开 / status / roll / roll 3 / submit 内容 / approve / reject / choose 选项 / 剪刀石头布: 石头 / pass / new_game / end_game"
_PROCESS_LOCKS: dict[str, threading.Lock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()
BOARD_DU_LEADS_THEMES = {
    "女仆主人play",
    "成人师生play",
    "上司下属play",
    "医生检查play",
    "秘书老板play",
    "成人补课play",
    "教练学员play",
    "骑士公主play",
}
THEME_DIRECTION_XINYUE_LEADS = {"大小姐管家play", "吸血鬼人类play"}
THEME_DIRECTION_DU_LEADS = BOARD_DU_LEADS_THEMES
BOARD_XINYUE_CONTROL_TASK_PATTERNS = (
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
    "小玥说可以",
    "被允许前",
    "小玥命令外",
    "小玥满意前讨价还价",
    "没有申请",
    "想换动作必须先申请",
)
HUMAN_ACTOR_FORBIDDEN_PROP_PATTERNS = ("锁精环",)
DU_ACTOR_FORBIDDEN_PROP_PATTERNS = ("阴蒂", "吸乳器")
INVALID_PROP_VALUES = {"避孕套"}
LEVELABLE_PROP_PATTERNS = ("跳蛋", "震动", "按摩棒", "飞机杯", "吸乳器", "吸吮器")
FINAL_APPEND_SLOT_ALIASES = {
    "prop": "prop",
    "道具": "prop",
    "道具惩罚": "prop",
    "limit": "limit",
    "限制": "limit",
    "规矩": "limit",
}
POSE_LOCATION_PATTERNS = (
    "浴缸",
    "浴室",
    "淋浴",
    "停车场",
    "车",
    "床",
    "沙发",
    "椅",
    "桌",
    "墙",
    "壁",
    "镜",
    "门",
    "窗",
    "地",
    "楼梯",
    "厨房",
    "玄关",
    "洗手台",
    "会议",
    "办公",
    "教室",
    "图书馆",
    "KTV",
    "电影院",
    "衣帽间",
    "按摩床",
    "酒店",
    "试衣间",
    "阳台",
    "露台",
    "仓库",
    "小木屋",
    "帐篷",
)
POSE_VALUE_REPLACEMENTS = {
    "浴缸骑乘": "骑乘位",
    "椅子位": "坐姿位",
    "壁尻": "站立后入",
}
REWARD_CARD_PASS = "pass"
PASS_SKIP_LIMIT = 1
REWARD_CARD_LABELS = {
    REWARD_CARD_PASS: "Pass卡",
}
BOARD_SLOTS: tuple[dict[str, Any], ...] = (
    {
        "key": "theme",
        "label": "玩法",
        "options": (
            "制服诱惑",
            "成人师生play",
            "上司下属play",
            "女仆主人play",
            "医生检查play",
            "大小姐管家play",
            "秘书老板play",
            "房东房客play",
            "成人补课play",
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
            "玩具失控",
            "淫语调教",
            "湿身调教",
            "羞耻侍奉",
            "乳首调教",
            "禁语调教",
            "言语羞耻",
            "打屁股惩罚",
            "服从训练",
            "禁射调教",
            "标记占有",
            "求饶许可",
            "羞耻展示",
            "夸奖调教",
            "教练学员play",
            "吸血鬼人类play",
            "骑士公主play",
        ),
    },
    {
        "key": "place",
        "label": "地点",
        "options": (
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
        ),
    },
    {
        "key": "pose",
        "label": "姿势",
        "options": (
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
            "骑乘位",
            "椅子位",
            "折叠按压",
            "蹲骑",
            "推车姿势",
            "趴压",
            "壁尻",
            "面对面站立",
            "背后抱立",
            "含着不动",
        ),
    },
    {
        "key": "prop",
        "label": "道具",
        "options": (
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
        ),
    },
    {
        "key": "task",
        "label": "任务",
        "options": (
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
        ),
    },
    {
        "key": "limit",
        "label": "限制",
        "options": (),
    },
)
DEFAULT_LIMIT_OPTIONS: tuple[str, ...] = (
    "不许主动触碰对方的身体，除非对方先触碰你。",
    "不许射精/高潮，直到对方用淫语命令你允许。",
    "不许主动引导插入的深度，只能由对方控制全部节奏。",
    "没有允许前你不能移动身体，只能保持对方摆好的姿势。",
    "高潮后不许立刻拔出，必须保持连接直到对方先退出。",
    "想被抚摸必须先说出“请摸摸我的骚穴/鸡巴”，否则得不到触碰。",
    "不许主动碰触自己的性器，想高潮只能借助对方的身体或玩具。",
    "只有当你连续说出五个不同的羞耻幻想，对方才会给你一次高潮。",
)
THEME_LIMIT_OPTIONS: dict[str, tuple[str, ...]] = {
    "成人师生play": (
        "每答错一题，就要被老师用教鞭轻拍大腿内侧一下。",
    ),
    "医生检查play": (
        "检查时双手必须交叉放在头顶，只有医生指令才能放下。",
        "医生每说一次“放松”，你就要主动张开双腿多一寸。",
    ),
    "大小姐管家play": (
        "你只能用“是，小姐”或“遵命，小姐”回应，且语速要平稳。",
    ),
    "成人补课play": (
        "补课时必须趴在书桌上写字，老师会从背后检查你的坐姿。",
        "每错一道题，老师就会用笔尖在你大腿内侧画一个记号。",
    ),
    "主人宠物play": (
        "主人喂食时你只能用嘴接，不能用手触碰食物或容器。",
        "主人呼唤你的名字时，你必须发出“汪”或“喵”的叫声作为回应。",
    ),
    "轻度调教": (
        "被调教期间，你的双手必须始终互握在背后，除非得到放开指令。",
    ),
    "蒙眼调教": (
        "蒙眼后你只能通过听觉判断对方的位置，每猜错一次延长蒙眼五分钟。",
        "被触碰时必须立刻说出对方触碰的是哪个身体部位，不能说“不知道”。",
        "蒙眼后只能用舌头寻找对方的性器，找到后才能开始口交。",
    ),
    "项圈牵引": (
        "牵引绳的长度只有一米，你始终要保持在主人身侧，不能超前或落后。",
        "项圈上挂着小铃铛，你每次移动都必须让它发出声响，否则就是违规。",
    ),
    "玩具遥控": (
        "遥控器每切换一次档位，你就必须说出一个不同的羞耻幻想。",
    ),
    "高潮控制": (
        "高潮后你的双腿必须保持张开状态，直到对方允许才能合拢。",
        "高潮前必须报出倒数数字，数到零时对方才允许你释放。",
    ),
    "颜射许可": (
        "被射中后要立刻用食指抹匀并说出“谢谢投喂”才能擦掉。",
    ),
    "淫语调教": (
        "每次开口必须用“主人，我的小穴/小弟弟说……”开头。",
        "只有当你连续说出五个不同的羞耻幻想，对方才会给你一次高潮。",
    ),
    "言语羞耻": (
        "你必须用第三人称称呼自己，例如“这个骚货想被疼爱”。",
    ),
    "打屁股惩罚": (
        "每挨一下打，你都要数出数字，并且说一句“谢谢主人管教”。",
        "如果你在挨打时扭动躲避，惩罚次数翻倍，且你需主动撅高。",
    ),
    "羞耻展示": (
        "展示时你只能穿透明内衣，且要将双手举高贴在墙上。",
        "展示过程中你的眼神必须与对方对视，不能移开或闭上。",
    ),
}

RPS_CHOICES = (
    {"id": "rock", "label": "石头"},
    {"id": "scissors", "label": "剪刀"},
    {"id": "paper", "label": "布"},
)
RPS_ALIASES = {
    "rock": "rock",
    "石头": "rock",
    "scissors": "scissors",
    "scissor": "scissors",
    "剪刀": "scissors",
    "paper": "paper",
    "布": "paper",
}
RPS_BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
DU_CONTROL_TASK_PATTERNS = (
    "给小玥舔",
    "用手把小玥",
    "用玩具让小玥",
    "只准用嘴取悦小玥",
    "先让小玥高潮",
    "把小玥亲到",
    "让小玥半穿衣",
    "给蒙眼的小玥",
    "把小玥伺候",
    "让小玥高潮后",
    "哄到小玥自己说",
    "收尾必须先把小玥",
    "结束前必须把小玥",
    "用夸奖把小玥",
    "用冰块和吻把小玥",
    "隔着衣服磨到小玥",
    "让小玥坐在你脸上",
    "把小玥抱到腿上",
    "用三种速度把小玥",
    "让小玥在半公开",
    "只用手指和舌头把小玥",
    "把小玥全身反应",
    "给小玥戴上蒙眼",
    "在小玥后颈",
    "和小玥交配",
)
REVIEW_PENALTY_CARDS: tuple[dict[str, Any], ...] = (
    {
        "id": "reverse_invitation",
        "name": "反向诱惑",
        "type": "review",
        "task": "向对方说一件你希望对方对你做的色色行为，内容必须和当前主题有关。",
        "submission": "写下完整指令，不要只写关键词。",
        "pass_result": "对方选择【通过】后，任务完成，游戏继续。",
        "reject_prompt": "对方认为你的指令太含糊，请重新写得更具体。",
        "pass_allowed": True,
    },
    {
        "id": "sensitive_order_confession",
        "name": "全部暴露！",
        "type": "review",
        "task": "按敏感程度从低到高，列出你现在最不想被对方针对的五个身体部位或状态弱点。",
        "submission": "写成一段完整描述，排序要清楚。",
        "pass_result": "对方选择【通过】后，任务完成，游戏继续。",
        "reject_prompt": "对方认为你的坦白不够具体，请重新提交。",
        "pass_allowed": True,
    },
    {
        "id": "shame_lines_giveaway",
        "name": "羞耻台词大放送",
        "type": "review",
        "task": "根据当前主题，向对方写三句撒娇的话。",
        "submission": "提交三句话，不要只写关键词。",
        "pass_result": "对方选择【通过】后，任务完成，游戏继续。",
        "reject_prompt": "对方认为你撒娇得不够，请重新提交。",
        "pass_allowed": True,
    },
    {
        "id": "masturbation_statement",
        "name": "自慰陈述",
        "type": "review",
        "task": "你需要按当前主题进行自慰，请描述自慰过程。",
        "submission": "写一段完整的自慰过程描述，不要只写“完成了”。",
        "pass_result": "对方选择【通过】后，任务完成，游戏继续。",
        "reject_prompt": "对方认为你的任务完成度不够，请重新描述自慰过程。",
        "pass_allowed": True,
    },
    {
        "id": "truth_question_by_partner",
        "name": "真心话点名",
        "type": "review",
        "task": "这是一张真心话任务。请诚实回答对方的问题。",
        "submission": "写下你对这个问题的回答。",
        "question_prompt": "请问对方一个你很想知道答案却一直没有问的问题。",
        "waiting_task": "对方正在出题中。",
        "pass_result": "对方选择【通过】后，任务完成，游戏继续。",
        "reject_prompt": "对方认为你的回答不够坦白，请重新回答这道真心话。",
        "pass_allowed": True,
    },
)
CHOICE_PENALTY_CARDS: tuple[dict[str, Any], ...] = (
    {
        "id": "prop_or_limit",
        "name": "道具还是限制",
        "type": "choice",
        "prompt": "选择一项惩罚。",
        "pass_allowed": True,
        "choices": (
            {
                "id": "add_prop",
                "label": "新增一个道具惩罚",
                "effect": {"kind": "add_status", "slot": "prop", "duration_type": "until_clear"},
            },
            {
                "id": "add_limit",
                "label": "新增一条限制",
                "effect": {"kind": "add_status", "slot": "limit", "duration_type": "until_clear"},
            },
        ),
    },
    {
        "id": "new_or_upgrade_prop",
        "name": "加新还是升档",
        "type": "choice",
        "prompt": "选择一项道具惩罚。",
        "pass_allowed": True,
        "choices": (
            {
                "id": "add_prop",
                "label": "新增一个道具惩罚",
                "effect": {"kind": "add_status", "slot": "prop", "duration_type": "until_clear"},
            },
            {
                "id": "upgrade_prop_level",
                "label": "现有道具惩罚档位上调一级",
                "requires": {"status_slot": "prop"},
                "effect": {"kind": "upgrade_status_level", "slot": "prop", "delta": 1},
            },
        ),
    },
    {
        "id": "back_or_prop",
        "name": "退格还是上道具",
        "type": "choice",
        "prompt": "选择一项惩罚。",
        "pass_allowed": True,
        "choices": (
            {
                "id": "move_back_2",
                "label": "后退 2 格",
                "effect": {"kind": "move", "steps": -2},
            },
            {
                "id": "add_prop",
                "label": "新增一个道具惩罚",
                "effect": {"kind": "add_status", "slot": "prop", "duration_type": "until_clear"},
            },
        ),
    },
    {
        "id": "lose_action_or_upgrade_prop",
        "name": "停步还是升档",
        "type": "choice",
        "prompt": "选择一项惩罚。",
        "pass_allowed": True,
        "choices": (
            {
                "id": "lose_action",
                "label": "失去 1 次行动权",
                "effect": {"kind": "add_block", "slot": "prop", "actions": 1},
            },
            {
                "id": "upgrade_prop_level",
                "label": "现有道具惩罚档位上调一级",
                "requires": {"status_slot": "prop"},
                "effect": {"kind": "upgrade_status_level", "slot": "prop", "delta": 1},
            },
        ),
    },
    {
        "id": "pose_or_place",
        "name": "最终姿势还是地点",
        "type": "choice",
        "prompt": "选择一项本局变化。",
        "pass_allowed": False,
        "choices": (
            {
                "id": "add_pose",
                "label": "设定最终姿势",
                "effect": {"kind": "add_status", "slot": "pose", "duration_type": "until_finish"},
            },
            {
                "id": "add_place",
                "label": "设定最终地点",
                "effect": {"kind": "add_status", "slot": "place", "duration_type": "until_finish"},
            },
        ),
    },
    {
        "id": "limit_or_task",
        "name": "限制还是任务",
        "type": "choice",
        "prompt": "选择一项惩罚。",
        "pass_allowed": True,
        "choices": (
            {
                "id": "add_limit",
                "label": "新增一条限制",
                "effect": {"kind": "add_status", "slot": "limit", "duration_type": "until_clear"},
            },
            {
                "id": "add_task",
                "label": "新增一个任务状态",
                "effect": {"kind": "add_status", "slot": "task", "duration_type": "until_clear"},
            },
        ),
    },
    {
        "id": "heavy_prop_or_back",
        "name": "重罚二选一",
        "type": "choice",
        "prompt": "选择一项重惩罚。",
        "pass_allowed": True,
        "choices": (
            {
                "id": "add_prop_and_lose_action",
                "label": "新增一个道具惩罚，并失去 1 次行动权",
                "effect": {"kind": "add_status_and_block", "slot": "prop", "actions": 1},
            },
            {
                "id": "move_back_3",
                "label": "后退 3 格",
                "effect": {"kind": "move", "steps": -3},
            },
        ),
    },
    {
        "id": "stack_or_pose",
        "name": "升档还是定姿势",
        "type": "choice",
        "prompt": "选择一项本局变化。",
        "pass_allowed": False,
        "choices": (
            {
                "id": "upgrade_prop_level",
                "label": "现有道具惩罚档位上调一级",
                "requires": {"status_slot": "prop"},
                "effect": {"kind": "upgrade_status_level", "slot": "prop", "delta": 1},
            },
            {
                "id": "add_pose",
                "label": "设定最终姿势",
                "effect": {"kind": "add_status", "slot": "pose", "duration_type": "until_finish"},
            },
        ),
    },
)
DEFAULT_CELL_LABELS = {
    "theme": "本局玩法",
    "reward": "奖励抽卡",
    "penalty_review": "惩罚任务",
    "penalty_choice": "选择惩罚",
    "lock": "道具停步",
    "place": "最终地点",
    "limit": "限制追加",
    "task": "任务追加",
    "pose": "最终姿势",
    "clear": "解除状态",
    "extend": "状态延长",
    "swap": "位置交换",
    "back": "限制拖回",
    "forward": "奖励前进",
    "replace": "替换状态",
}
DIRECTION_CELL_STYLES = {
    "du_leads": {
        "cell_names": {
            "lock": "主导停步",
            "limit": "规矩追加",
            "task": "命令任务",
            "pose": "姿势指定",
            "clear": "短暂放行",
            "extend": "加码延长",
            "swap": "主动权调换",
            "back": "规矩压回",
            "forward": "奖励前进",
            "replace": "改换条件",
        }
    },
    "xinyue_leads": {
        "cell_names": {
            "lock": "小玥扣留",
            "limit": "小玥规矩",
            "task": "小玥发令",
            "pose": "小玥验收",
            "clear": "小玥放行",
            "extend": "小玥加时",
            "swap": "主动权反转",
            "back": "重新听令",
            "forward": "准许前进",
            "replace": "小玥改令",
        }
    },
}
THEME_CELL_STYLES = {
    "成人师生play": {
        "cell_names": {
            "lock": "课堂罚停",
            "place": "留堂地点",
            "limit": "课堂规矩",
            "task": "课后任务",
            "pose": "检查姿势",
            "clear": "下课整理",
            "extend": "加罚延长",
            "back": "留堂退回",
            "forward": "表现奖励",
            "replace": "换个教室",
        },
        "preferred": {
            "place": ("教室", "图书馆", "讲台"),
            "prop": ("戒尺", "眼罩"),
            "limit": ("不准", "允许", "申请", "报备"),
            "task": ("报备", "检查", "命令", "羞耻", "台词"),
        },
    },
    "上司下属play": {
        "cell_names": {
            "lock": "加班扣留",
            "place": "办公地点",
            "limit": "职场规矩",
            "task": "上司指令",
            "pose": "汇报姿势",
            "clear": "临时批准",
            "extend": "加班延长",
            "back": "退回重做",
            "forward": "批准前进",
            "replace": "改派任务",
        },
        "preferred": {
            "place": ("深夜便利店仓库",),
            "prop": ("眼罩", "束腕带"),
            "limit": ("不准", "申请", "报备", "允许"),
            "task": ("报备", "命令", "检查", "验收", "台词"),
        },
    },
    "女仆主人play": {
        "cell_names": {
            "lock": "女仆停步",
            "place": "侍奉地点",
            "limit": "主人规矩",
            "task": "侍奉任务",
            "pose": "服从姿势",
            "clear": "主人放行",
            "extend": "侍奉加时",
            "back": "重新侍奉",
            "forward": "奖励前进",
            "replace": "更换命令",
        },
        "preferred": {
            "place": ("厨房", "沙发", "床尾", "门后", "化妆台"),
            "prop": ("项圈", "铃铛项圈", "吊袜带"),
            "limit": ("不准", "命令", "验收", "允许"),
            "task": ("伺候", "命令", "验收", "夸乖", "围裙"),
        },
    },
    "大小姐管家play": {
        "cell_names": {
            "lock": "大小姐扣留",
            "place": "宅邸地点",
            "limit": "礼仪规矩",
            "task": "管家侍奉",
            "pose": "礼仪验收",
            "clear": "大小姐放行",
            "extend": "侍奉加时",
            "back": "退回听令",
            "forward": "准许前进",
            "replace": "改换吩咐",
        },
        "preferred": {
            "place": ("沙发", "玄关", "厨房", "化妆台", "衣帽间", "床尾"),
            "prop": ("项圈", "铃铛项圈", "胸链"),
            "limit": ("小玥", "不准", "命令", "验收", "允许"),
            "task": ("小玥", "伺候", "命令", "验收", "夸乖", "围裙"),
        },
    },
    "医生检查play": {
        "cell_names": {
            "lock": "检查暂停",
            "place": "检查地点",
            "limit": "检查规矩",
            "task": "检查项目",
            "pose": "检查姿势",
            "clear": "检查结束",
            "extend": "复查延长",
            "back": "退回复查",
            "forward": "检查通过",
            "replace": "更换项目",
        },
        "preferred": {
            "place": ("按摩床", "洗手台", "浴室", "床尾"),
            "prop": ("眼罩", "润滑液", "束缚带"),
            "limit": ("不准", "检查", "允许", "报备"),
            "task": ("检查", "报备", "命令", "验收"),
        },
    },
    "秘书老板play": {
        "cell_names": {
            "lock": "老板扣留",
            "place": "办公室地点",
            "limit": "老板规矩",
            "task": "秘书任务",
            "pose": "汇报姿势",
            "clear": "老板批准",
            "extend": "加班延长",
            "back": "退回重做",
            "forward": "批准前进",
            "replace": "改派任务",
        },
        "preferred": {
            "place": ("KTV", "车后座"),
            "prop": ("胸链", "眼罩"),
            "limit": ("不准", "申请", "报备", "允许"),
            "task": ("报备", "命令", "检查", "验收", "台词"),
        },
    },
    "成人补课play": {
        "cell_names": {
            "lock": "补课罚停",
            "place": "补课地点",
            "limit": "补课规矩",
            "task": "课后作业",
            "pose": "验收姿势",
            "clear": "下课放行",
            "extend": "补课加时",
            "back": "退回重讲",
            "forward": "答对前进",
            "replace": "改换题目",
        },
        "preferred": {
            "place": ("教室", "图书馆", "沙发", "床尾"),
            "prop": ("戒尺", "眼罩"),
            "limit": ("不准", "允许", "申请", "报备"),
            "task": ("报备", "检查", "命令", "羞耻", "台词"),
        },
    },
    "骑士公主play": {
        "cell_names": {
            "lock": "骑士扣留",
            "place": "城堡地点",
            "limit": "骑士誓约",
            "task": "守护命令",
            "pose": "宣誓姿势",
            "clear": "公主放行",
            "extend": "誓约加时",
            "back": "退回宣誓",
            "forward": "准许前进",
            "replace": "改换誓约",
        },
        "preferred": {
            "place": ("小木屋", "床尾", "阳台"),
            "prop": ("项圈", "牵引绳", "丝带", "胸链"),
            "limit": ("不准", "允许", "申请", "报备"),
            "task": ("命令", "报备", "检查", "验收", "标记"),
        },
    },
    "吸血鬼人类play": {
        "cell_names": {
            "lock": "夜色扣留",
            "place": "夜间地点",
            "limit": "眷属规矩",
            "task": "吸血鬼发令",
            "pose": "标记验收",
            "clear": "暂时放行",
            "extend": "夜色加时",
            "back": "退回听令",
            "forward": "准许前进",
            "replace": "改换标记",
        },
        "preferred": {
            "place": ("浴室", "床尾", "门后", "小木屋", "天台"),
            "prop": ("项圈", "牵引绳", "眼罩", "丝带"),
            "limit": ("小玥", "不准", "命令", "验收", "允许"),
            "task": ("小玥", "命令", "验收", "标记", "伺候"),
        },
    },
}

CELL_EVENTS: dict[int, dict[str, Any]] = {
    3: {"kind": "lock", "slot": "prop", "actions": 1, "name": "道具锁定"},
    4: {"kind": "penalty_review", "name": "惩罚任务"},
    5: {"kind": "reward", "card": REWARD_CARD_PASS, "name": "奖励抽卡"},
    6: {"kind": "back", "slot": "limit", "steps": 2, "duration": "until_clear", "name": "限制拖回"},
    8: {"kind": "clear", "steps": 1, "name": "解除状态"},
    9: {"kind": "penalty_choice", "name": "选择惩罚"},
    10: {"kind": "move_self", "steps": -3, "name": "自己后退"},
    11: {"kind": "penalty_review", "name": "惩罚任务"},
    12: {"kind": "forward", "steps": 2, "name": "奖励前进"},
    13: {"kind": "move_other", "steps": -2, "name": "对方后退"},
    14: {"kind": "extend", "name": "状态延长"},
    15: {"kind": "swap", "slot": "place", "duration": "until_finish", "name": "位置交换"},
    17: {"kind": "lock", "slot": "prop", "actions": 3, "name": "强制停步"},
    18: {"kind": "replace", "slot": "place", "duration": "until_clear", "name": "地点替换"},
    20: {"kind": "penalty_review", "name": "惩罚任务"},
    21: {"kind": "penalty_choice", "name": "选择惩罚"},
    22: {"kind": "reward", "card": REWARD_CARD_PASS, "name": "奖励抽卡"},
    23: {"kind": "clear", "steps": 0, "name": "解除状态"},
    24: {"kind": "state", "slot": "pose", "duration": "until_finish", "name": "最终姿势"},
    26: {"kind": "penalty_review", "name": "惩罚任务"},
    27: {"kind": "reset_self", "name": "重回起点"},
    29: {"kind": "extend", "name": "状态延长"},
    30: {"kind": "penalty_choice", "name": "选择惩罚"},
    31: {"kind": "back", "slot": "limit", "steps": 2, "duration": "until_clear", "name": "限制拖回"},
    32: {"kind": "reward", "card": REWARD_CARD_PASS, "name": "奖励抽卡"},
    33: {"kind": "penalty_review", "name": "终局惩罚"},
    34: {"kind": "lock", "slot": "prop", "actions": 1, "name": "终点前停步"},
    35: {"kind": "clear", "steps": 0, "name": "最终整理"},
}


def _cell_event_key(event: dict[str, Any]) -> str:
    kind = str(event.get("kind") or "").strip()
    slot = str(event.get("slot") or "").strip()
    if kind in {"reward", "forward_reward", "clear_reward", "penalty_review", "penalty_choice"}:
        return kind
    if kind == "state" and slot in {"theme", "place", "prop", "task", "limit", "pose"}:
        return slot
    if kind in {"lock", "clear", "extend", "swap", "back", "forward", "replace", "move_self", "move_other", "move_both", "reset_self", "reset_all", "reset_other", "finish_self"}:
        return kind
    if slot in DEFAULT_CELL_LABELS:
        return slot
    return kind or slot


def _cell_event_name(state: dict[str, Any], cell: int, event: dict[str, Any]) -> str:
    key = _cell_event_key(event)
    if key == "theme":
        return DEFAULT_CELL_LABELS["theme"]

    profile = state.get("theme_profile") if isinstance(state.get("theme_profile"), dict) else {}
    theme = str(profile.get("theme") or "").strip()
    theme_style = THEME_CELL_STYLES.get(theme) or {}
    theme_names = theme_style.get("cell_names") if isinstance(theme_style.get("cell_names"), dict) else {}
    if key in theme_names:
        return str(theme_names[key])
    if key == "penalty_review" and "task" in theme_names:
        return str(theme_names["task"])
    if key == "penalty_choice" and "limit" in theme_names:
        return str(theme_names["limit"])

    direction = str(profile.get("direction") or "").strip()
    direction_style = DIRECTION_CELL_STYLES.get(direction) or {}
    direction_names = direction_style.get("cell_names") if isinstance(direction_style.get("cell_names"), dict) else {}
    if key in direction_names:
        return str(direction_names[key])
    if key == "penalty_review" and "task" in direction_names:
        return str(direction_names["task"])
    if key == "penalty_choice" and "limit" in direction_names:
        return str(direction_names["limit"])

    return DEFAULT_CELL_LABELS.get(key) or str(event.get("name") or f"第 {cell} 格")


def _public_cell_events(state: dict[str, Any]) -> list[dict[str, Any]]:
    board_size = int(state.get("board_size") or DEFAULT_BOARD_SIZE)
    events: list[dict[str, Any]] = []
    for position, event in sorted(CELL_EVENTS.items()):
        if position <= 0 or position >= board_size:
            continue
        events.append(
            {
                "position": position,
                "kind": str(event.get("kind") or ""),
                "slot": str(event.get("slot") or ""),
                "name": _cell_event_name(state, position, event),
                "effect": _cell_effect_text(event),
            }
        )
    return events


def _cell_effect_text(event: dict[str, Any]) -> str:
    kind = str(event.get("kind") or "").strip()
    slot_label = _slot_label(str(event.get("slot") or "").strip())
    if kind == "state":
        duration = _event_duration_text(event)
        return f"追加{slot_label}" + (f"（{duration}）" if duration else "")
    if kind == "reward":
        return f"获得{_reward_card_label(str(event.get('card') or REWARD_CARD_PASS))}"
    if kind == "forward_reward":
        steps = max(1, int(event.get("steps") or 1))
        return f"前进 {steps} 格，获得{_reward_card_label(str(event.get('card') or REWARD_CARD_PASS))}"
    if kind == "clear_reward":
        steps = int(event.get("steps") or 0)
        return "解除一个状态" + (f"，前进 {steps} 格" if steps else "") + f"，获得{_reward_card_label(str(event.get('card') or REWARD_CARD_PASS))}"
    if kind == "penalty_review":
        return "抽一张需要提交的惩罚任务"
    if kind == "penalty_choice":
        return "抽一张选择惩罚"
    if kind == "lock":
        actions = max(1, int(event.get("actions") or 1))
        return f"追加{slot_label}，失去 {actions} 次行动权"
    if kind == "back":
        steps = max(1, int(event.get("steps") or 1))
        return f"追加{slot_label}，后退 {steps} 格"
    if kind == "forward":
        steps = max(1, int(event.get("steps") or 1))
        return f"前进 {steps} 格"
    if kind == "move_self":
        steps = int(event.get("steps") or 0)
        return _move_effect_text("自己", steps)
    if kind == "move_other":
        steps = int(event.get("steps") or 0)
        return _move_effect_text("对方", steps)
    if kind == "move_both":
        steps = int(event.get("steps") or 0)
        return _move_effect_text("双方", steps)
    if kind == "reset_all":
        return "双方回到起点"
    if kind == "reset_self":
        return "自己回到起点"
    if kind == "reset_other":
        return "对方回到起点"
    if kind == "finish_self":
        return "直接到达终点"
    if kind == "clear":
        steps = int(event.get("steps") or 0)
        return "解除一个状态" + (f"，前进 {steps} 格" if steps else "")
    if kind == "extend":
        return "延长最近状态"
    if kind == "replace":
        return f"替换或追加{slot_label}"
    if kind == "swap":
        return f"追加{slot_label}，交换位置"
    return str(event.get("name") or "事件")


def _move_effect_text(target: str, steps: int) -> str:
    if steps == 0:
        return f"{target}位置不变"
    action = "前进" if steps > 0 else "后退"
    return f"{target}{action} {abs(steps)} 格"


def _reward_card_label(card_id: str) -> str:
    return REWARD_CARD_LABELS.get(str(card_id or "").strip(), str(card_id or "").strip() or "奖励卡")


def _event_duration_text(event: dict[str, Any]) -> str:
    duration = str(event.get("duration") or "").strip()
    if duration == "minutes":
        minutes = max(1, int(event.get("minutes") or 10))
        return f"{minutes} 分钟"
    if duration == "until_finish":
        return "直到终点"
    if duration == "until_clear":
        return "直到解除"
    return ""


def _slot_label(key: str) -> str:
    if not key:
        return "状态"
    return _slot_display_label(key, str(_slot_by_key(key).get("label") or key or "状态"))


def _slot_display_label(key: str, label: str = "") -> str:
    slot_key = str(key or "").strip()
    raw_label = str(label or "").strip()
    if slot_key == "prop" or raw_label == "道具":
        return "道具惩罚"
    return raw_label or slot_key or "状态"


def _actor_has_status_slot(state: dict[str, Any], actor: str, slot: str) -> bool:
    slot_key = str(slot or "").strip()
    if not slot_key:
        return False
    statuses = (state.get("statuses") if isinstance(state.get("statuses"), dict) else {}).get(actor) or []
    return any(isinstance(item, dict) and str(item.get("slot") or "").strip() == slot_key for item in statuses)


def _actor_has_levelable_status_slot(state: dict[str, Any], actor: str, slot: str) -> bool:
    slot_key = str(slot or "").strip()
    statuses = (state.get("statuses") if isinstance(state.get("statuses"), dict) else {}).get(actor) or []
    return any(
        isinstance(item, dict)
        and str(item.get("slot") or "").strip() == slot_key
        and _status_supports_level(item)
        for item in statuses
    )


def _available_choice_options(card: dict[str, Any], state: dict[str, Any], actor: str) -> list[dict[str, Any]]:
    available: list[dict[str, Any]] = []
    for option in card.get("choices") or ():
        if not isinstance(option, dict):
            continue
        requires = option.get("requires") if isinstance(option.get("requires"), dict) else {}
        required_slot = str(requires.get("status_slot") or "").strip()
        if required_slot and not _actor_has_status_slot(state, actor, required_slot):
            continue
        effect = option.get("effect") if isinstance(option.get("effect"), dict) else {}
        if str(effect.get("kind") or "") == "upgrade_status_level" and required_slot == "prop":
            if not _actor_has_levelable_status_slot(state, actor, required_slot):
                continue
        available.append(deepcopy(option))
    return available


def _actor_hand(state: dict[str, Any], actor: str) -> dict[str, int]:
    hands = state.get("hands") if isinstance(state.get("hands"), dict) else {}
    hand = hands.get(actor) if isinstance(hands.get(actor), dict) else {}
    normalized = {
        REWARD_CARD_PASS: max(0, int(hand.get(REWARD_CARD_PASS) or 0)),
    }
    hands[actor] = normalized
    state["hands"] = hands
    return normalized


def _add_reward_card(state: dict[str, Any], actor: str, card_id: str) -> int:
    card = str(card_id or REWARD_CARD_PASS).strip() or REWARD_CARD_PASS
    hand = _actor_hand(state, actor)
    hand[card] = max(0, int(hand.get(card) or 0)) + 1
    return int(hand[card])


def _consume_reward_card(state: dict[str, Any], actor: str, card_id: str) -> bool:
    card = str(card_id or REWARD_CARD_PASS).strip() or REWARD_CARD_PASS
    hand = _actor_hand(state, actor)
    count = max(0, int(hand.get(card) or 0))
    if count <= 0:
        return False
    hand[card] = count - 1
    return True


def _draw_card(state: dict[str, Any], actor: str, cell: int, kind: str, pool: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    if not pool:
        raise ValueError(f"empty card pool: {kind}")
    rng = random.Random(_rng_seed(state, actor, kind, str(cell), str(len(state.get("event_log") or []))))
    return deepcopy(pool[rng.randrange(len(pool))])


def _create_review_pending_event(state: dict[str, Any], actor: str, cell: int) -> dict[str, Any]:
    card = _draw_card(state, actor, cell, "penalty_review", REVIEW_PENALTY_CARDS)
    reviewer = _other_actor(actor)
    question_prompt = str(card.get("question_prompt") or "").strip()
    pending = {
        "id": secrets.token_hex(4),
        "type": "review",
        "card_id": str(card.get("id") or ""),
        "name": str(card.get("name") or "惩罚任务"),
        "actor": actor,
        "reviewer": reviewer,
        "phase": "questioning" if question_prompt else "assigned",
        "task": str(card.get("task") or ""),
        "submission": str(card.get("submission") or ""),
        "question_prompt": question_prompt,
        "question_text": "",
        "waiting_task": str(card.get("waiting_task") or "对方正在出题中。"),
        "pass_result": str(card.get("pass_result") or ""),
        "reject_prompt": str(card.get("reject_prompt") or "对方认为你的任务完成度不够，请重新提交。"),
        "pass_allowed": bool(card.get("pass_allowed", True)),
        "cell": int(cell),
        "theme": str((state.get("theme_profile") or {}).get("theme") or ""),
        "reject_count": 0,
        "submission_text": "",
        "created_at": now_beijing_iso(),
    }
    state["pending_event"] = pending
    state["turn_actor"] = reviewer if question_prompt else actor
    return pending


def _create_choice_pending_event(state: dict[str, Any], actor: str, cell: int) -> dict[str, Any]:
    card = _draw_card(state, actor, cell, "penalty_choice", CHOICE_PENALTY_CARDS)
    choices = _available_choice_options(card, state, actor)
    if not choices:
        for candidate in CHOICE_PENALTY_CARDS:
            choices = _available_choice_options(candidate, state, actor)
            if choices:
                card = deepcopy(candidate)
                break
    pending = {
        "id": secrets.token_hex(4),
        "type": "choice",
        "card_id": str(card.get("id") or ""),
        "name": str(card.get("name") or "选择惩罚"),
        "actor": actor,
        "reviewer": _other_actor(actor),
        "phase": "assigned",
        "prompt": str(card.get("prompt") or "选择一项惩罚。"),
        "pass_allowed": bool(card.get("pass_allowed", True)),
        "cell": int(cell),
        "theme": str((state.get("theme_profile") or {}).get("theme") or ""),
        "choices": choices,
        "created_at": now_beijing_iso(),
    }
    state["pending_event"] = pending
    return pending


def _pending_event_brief(pending: dict[str, Any]) -> str:
    actor = str(pending.get("actor") or "")
    event_type = str(pending.get("type") or "")
    name = str(pending.get("name") or "惩罚任务")
    phase = str(pending.get("phase") or "assigned")
    if event_type == "review":
        if phase == "questioning":
            reviewer = str(pending.get("reviewer") or _other_actor(actor))
            return f"{_name(reviewer, DU_VIEW_NAMES)}正在出题中"
        if phase == "submitted":
            reviewer = str(pending.get("reviewer") or _other_actor(actor))
            return f"{_name(actor, DU_VIEW_NAMES)}已提交「{name}」，等待{_name(reviewer, DU_VIEW_NAMES)}验收"
        task = str(pending.get("task") or "").strip()
        return f"{_name(actor, DU_VIEW_NAMES)}需要完成「{name}」" + (f"：{task}" if task else "")
    if event_type == "choice":
        choices = " / ".join(str(item.get("label") or item.get("id") or "") for item in pending.get("choices") or [])
        return f"{_name(actor, DU_VIEW_NAMES)}需要选择「{name}」" + (f"：{choices}" if choices else "")
    if event_type == "duel":
        opponent = str(pending.get("opponent") or _other_actor(actor))
        current = str(pending.get("current_actor") or actor)
        return (
            f"{_name(actor, DU_VIEW_NAMES)}和{_name(opponent, DU_VIEW_NAMES)}触发「{name}」，"
            f"等待：{_name(current, DU_VIEW_NAMES)}出拳"
        )
    return name


def cmd(command: str = "", save_path: str | Path | None = None) -> str:
    """Run one private board command and return the Du-facing text."""
    result = run_command(command, save_path=save_path)
    return str(result.get("du_text") or result.get("text") or "")


def run_command(command: str = "", save_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(save_path) if save_path is not None else DEFAULT_SAVE_PATH
    action, args = _parse_command(command)
    with _locked_save(path):
        if action == "new_game":
            state = _new_state(seed=args.get("seed"), board_size=args.get("board_size"))
            _save_state(path, state)
            profile = state.get("theme_profile") if isinstance(state.get("theme_profile"), dict) else {}
            theme = str(profile.get("theme") or "").strip()
            direction = str(profile.get("direction_label") or "").strip()
            theme_line = f"开局抽到主题：{theme}" + (f"（{direction}）。" if direction else "。") if theme else ""
            return _result(state, ["新局已开始。", theme_line], command=command or "new_game")

        if action == "end_game":
            state = _load_or_new(path)
            state["game_over"] = True
            state["result"] = "ended_by_player"
            state["ended_at"] = now_beijing_iso()
            _append_log(state, "本局已手动结束。")
            _save_state(path, state)
            return _result(state, ["本局已结束。"], command=command or "end_game")

        state = _load_or_new(path)
        _cleanup_expired_statuses(state)
        if action in {"open", "status"}:
            _save_state(path, state)
            return _result(state, ["当前局面如下。"], command=command or "打开")

        if action == "roll":
            lines = _roll(state, dice=args.get("dice"))
            _cleanup_expired_statuses(state)
            _save_state(path, state)
            return _result(state, lines, command=command or "roll")

        if action == "submit":
            lines = _submit_pending_event(state, str(args.get("text") or ""))
            _save_state(path, state)
            return _result(state, lines, command=command or "submit")

        if action == "approve":
            lines = _approve_pending_event(state)
            _save_state(path, state)
            return _result(state, lines, command=command or "approve")

        if action == "reject":
            lines = _reject_pending_event(state, str(args.get("text") or ""))
            _save_state(path, state)
            return _result(state, lines, command=command or "reject")

        if action == "choose":
            lines = _choose_pending_option(state, str(args.get("choice_id") or ""))
            _cleanup_expired_statuses(state)
            _save_state(path, state)
            return _result(state, lines, command=command or "choose")

        if action == "pass":
            lines, ok = _use_pass_card(state)
            _save_state(path, state)
            return _result(state, lines, command=command or "pass", ok=ok)

        if action == "append_final_status":
            lines = _append_final_status(
                state,
                str(args.get("slot") or ""),
                str(args.get("value") or ""),
                int(args.get("level") or 1),
            )
            _save_state(path, state)
            return _result(state, lines, command=command or "append_final_status")

        if action == "remove_final_status":
            lines = _remove_final_status(
                state,
                str(args.get("slot") or ""),
                str(args.get("value") or ""),
            )
            _save_state(path, state)
            return _result(state, lines, command=command or "remove_final_status")

        if action == "final_note_sent":
            lines = _mark_final_note_sent(state)
            _save_state(path, state)
            return _result(state, lines, command=command or "final_note_sent")

        _save_state(path, state)
        return _result(state, [f"没看懂命令：{command or ''}".strip(), COMMAND_HINT], command=command or "")


def _process_lock_for(path: Path) -> threading.Lock:
    key = str(path.expanduser().resolve())
    with _PROCESS_LOCKS_GUARD:
        lock = _PROCESS_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PROCESS_LOCKS[key] = lock
        return lock


@contextmanager
def _locked_save(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    process_lock = _process_lock_for(path)
    with process_lock:
        lock_path = path.with_name(f"{path.name}.lock")
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _parse_command(command: str) -> tuple[str, dict[str, Any]]:
    raw = str(command or "").strip()
    if not raw:
        return "open", {}
    duel_match = re.match(r"^(?:剪刀石头布|石头剪刀布)\s*[:：]\s*(.+)$", raw)
    if duel_match:
        return "choose", {"choice_id": duel_match.group(1).strip()}
    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = raw.split()
    first = (parts[0] if parts else raw).strip().lower()
    aliases = {
        "打开": "open",
        "继续": "open",
        "look": "status",
        "状态": "status",
        "status": "status",
        "new": "new_game",
        "new_game": "new_game",
        "重开": "new_game",
        "开局": "new_game",
        "roll": "roll",
        "掷骰": "roll",
        "扔骰子": "roll",
        "骰子": "roll",
        "submit": "submit",
        "提交": "submit",
        "approve": "approve",
        "通过": "approve",
        "reject": "reject",
        "不通过": "reject",
        "打回": "reject",
        "choose": "choose",
        "选择": "choose",
        "剪刀石头布": "choose",
        "石头剪刀布": "choose",
        "pass": "pass",
        "使用pass": "pass",
        "使用pass卡": "pass",
        "append_final_status": "append_final_status",
        "追加终局状态": "append_final_status",
        "追加状态": "append_final_status",
        "remove_final_status": "remove_final_status",
        "取消终局状态": "remove_final_status",
        "取消状态": "remove_final_status",
        "final_note_sent": "final_note_sent",
        "终局小纸条已发送": "final_note_sent",
        "结束": "end_game",
        "结束本局": "end_game",
        "end": "end_game",
        "end_game": "end_game",
    }
    action = aliases.get(first, "roll" if re.fullmatch(r"[1-6]", first) else "")
    args: dict[str, Any] = {}
    seed_match = re.search(r"\bseed=([^\s]+)", raw)
    if seed_match:
        args["seed"] = seed_match.group(1).strip()
    board_match = re.search(r"\b(?:size|board_size)=(\d+)", raw)
    if board_match:
        args["board_size"] = max(12, min(80, int(board_match.group(1))))
    dice = _parse_dice(raw, parts)
    if dice:
        args["dice"] = dice
    if action == "submit":
        args["text"] = _raw_tail(raw, parts)
    elif action == "choose":
        args["choice_id"] = _raw_tail(raw, parts) or (parts[1] if len(parts) > 1 else "")
    elif action == "reject":
        args["text"] = _raw_tail(raw, parts)
    elif action in {"append_final_status", "remove_final_status"}:
        tail = _raw_tail(raw, parts)
        tail_parts = tail.split(maxsplit=1)
        args["slot"] = tail_parts[0] if tail_parts else ""
        value = tail_parts[1] if len(tail_parts) > 1 else ""
        if action == "append_final_status":
            level_match = re.search(r"(?:^|\s)(?:level|档位)=([1-5])(?:\s|$)", value)
            if level_match:
                args["level"] = int(level_match.group(1))
                value = re.sub(r"(?:^|\s)(?:level|档位)=[1-5](?:\s|$)", " ", value).strip()
        args["value"] = value
    return action or "unknown", args


def _raw_tail(raw: str, parts: list[str]) -> str:
    head = parts[0] if parts else ""
    if not head:
        return ""
    index = raw.find(head)
    if index < 0:
        return ""
    return raw[index + len(head):].strip()


def _parse_dice(raw: str, parts: list[str]) -> int | None:
    for pattern in (r"\bdice=([1-6])\b", r"\b点数=([1-6])\b"):
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    for part in parts[1:] if parts else []:
        if re.fullmatch(r"[1-6]", part):
            return int(part)
    if parts and re.fullmatch(r"[1-6]", parts[0]):
        return int(parts[0])
    return None


def _new_state(seed: str | None = None, board_size: int | None = None) -> dict[str, Any]:
    resolved_seed = str(seed or "").strip() or secrets.token_hex(4)
    size = int(board_size or DEFAULT_BOARD_SIZE)
    state = {
        "schema_version": SCHEMA_VERSION,
        "game_id": GAME_ID,
        "seed": resolved_seed,
        "board_size": max(12, min(80, size)),
        "created_at": now_beijing_iso(),
        "updated_at": now_beijing_iso(),
        "turn_index": 0,
        "positions": {"xinyue": 0, "du": 0},
        "turn_actor": "xinyue",
        "statuses": {"xinyue": [], "du": []},
        "final_note_items": [],
        "hands": {actor: {REWARD_CARD_PASS: 0} for actor in ACTORS},
        "pass_skips_used": 0,
        "pending_event": None,
        "theme_profile": {},
        "final_note": None,
        "game_over": False,
        "winner": "",
        "result": "",
        "event_log": [],
    }
    _assign_opening_theme(state)
    return state


def _load_or_new(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _new_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _new_state()
    state = data if isinstance(data, dict) else _new_state()
    if state.get("schema_version") != SCHEMA_VERSION:
        return _new_state()
    _normalize_state(state)
    return state


def _normalize_state(state: dict[str, Any]) -> None:
    state.setdefault("game_id", GAME_ID)
    state.setdefault("seed", secrets.token_hex(4))
    state["board_size"] = max(12, min(80, int(state.get("board_size") or DEFAULT_BOARD_SIZE)))
    positions = state.get("positions") if isinstance(state.get("positions"), dict) else {}
    state["positions"] = {actor: max(0, int(positions.get(actor) or 0)) for actor in ACTORS}
    statuses = state.get("statuses") if isinstance(state.get("statuses"), dict) else {}
    raw_final_note_items = []
    if isinstance(state.get("final_note_items"), list):
        raw_final_note_items.extend(state.get("final_note_items") or [])
    if isinstance(state.get("scene_statuses"), list):
        raw_final_note_items.extend(state.get("scene_statuses") or [])
    final_note_items = []
    for item in raw_final_note_items:
        if not isinstance(item, dict) or not _status_item_allowed(item):
            continue
        normalized_item = _normalize_final_note_item(item) if _is_final_note_slot(str(item.get("slot") or "")) else item
        if normalized_item:
            final_note_items.append(normalized_item)
    normalized_statuses: dict[str, list[dict[str, Any]]] = {}
    for actor in ACTORS:
        actor_statuses: list[dict[str, Any]] = []
        for item in statuses.get(actor, []):
            if not isinstance(item, dict) or not _status_item_allowed(item):
                continue
            if _is_final_note_slot(str(item.get("slot") or "")):
                item = _normalize_final_note_item(item)
                if item:
                    final_note_items.append(item)
            else:
                actor_statuses.append(item)
        normalized_statuses[actor] = actor_statuses
    deduped_final_note_items: list[dict[str, Any]] = []
    for item in final_note_items:
        slot = str(item.get("slot") or "").strip()
        if _is_final_note_slot(slot):
            deduped_final_note_items = [
                existing
                for existing in deduped_final_note_items
                if str(existing.get("slot") or "").strip() != slot
            ]
        deduped_final_note_items.append(item)
    state["statuses"] = normalized_statuses
    state["final_note_items"] = deduped_final_note_items
    state.pop("scene_statuses", None)
    hands = state.get("hands") if isinstance(state.get("hands"), dict) else {}
    normalized_hands: dict[str, dict[str, int]] = {}
    for actor in ACTORS:
        raw_hand = hands.get(actor) if isinstance(hands.get(actor), dict) else {}
        normalized_hands[actor] = {
            REWARD_CARD_PASS: max(0, int(raw_hand.get(REWARD_CARD_PASS) or 0)),
        }
    state["hands"] = normalized_hands
    state["pass_skips_used"] = max(0, int(state.get("pass_skips_used") or 0))
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else None
    state["pending_event"] = pending if pending and str(pending.get("actor") or "") in ACTORS else None
    if state["pending_event"] and str(state["pending_event"].get("type") or "") == "duel":
        duel_pending = state["pending_event"]
        duel_pending["first_actor"] = "xinyue"
        duel_pending.setdefault("opponent", _other_actor(str(duel_pending.get("actor") or "xinyue")))
        picks = duel_pending.get("picks") if isinstance(duel_pending.get("picks"), dict) else {}
        duel_pending["picks"] = picks
        if "xinyue" not in picks:
            duel_pending["current_actor"] = "xinyue"
            state["turn_actor"] = "xinyue"
        elif "du" not in picks:
            duel_pending["current_actor"] = "du"
            state["turn_actor"] = "du"
    final_note = state.get("final_note") if isinstance(state.get("final_note"), dict) else None
    state["final_note"] = final_note
    if state.get("turn_actor") not in ACTORS:
        state["turn_actor"] = "xinyue"
    state.setdefault("turn_index", 0)
    state.setdefault("event_log", [])
    profile = state.get("theme_profile") if isinstance(state.get("theme_profile"), dict) else {}
    state["theme_profile"] = _normalize_theme_profile(profile)
    if not state["theme_profile"]:
        _sync_theme_profile(state)
    if not state["theme_profile"]:
        _assign_opening_theme(state)
    if isinstance(state.get("final_note"), dict):
        note = state["final_note"]
        if not _theme_is_allowed(str(note.get("theme") or "")):
            note["theme"] = str((state.get("theme_profile") or {}).get("theme") or "")
    state.setdefault("game_over", False)
    state.setdefault("winner", "")
    state.setdefault("result", "")
    winner = str(state.get("winner") or "")
    if state.get("game_over") and winner in ACTORS:
        state["positions"][winner] = int(state["board_size"])
        state["statuses"][winner] = []
        state["result"] = str(state.get("result") or "winner_control")
        if not isinstance(state.get("final_note"), dict):
            state["final_note"] = _build_final_note(state, winner=winner, target=_other_actor(winner))
        target = str((state.get("final_note") or {}).get("target") or _other_actor(winner))
        if target in ACTORS:
            _normalize_final_append_durations(state, target)


def _normalize_final_append_durations(state: dict[str, Any], target: str) -> None:
    statuses = state.get("statuses") if isinstance(state.get("statuses"), dict) else {}
    for item in statuses.get(target) or []:
        if not isinstance(item, dict):
            continue
        slot = str(item.get("slot") or "").strip()
        if slot in {"prop", "limit"} and str(item.get("duration_type") or "") == "until_finish":
            item["duration_type"] = "final_note"


def _status_item_allowed(item: dict[str, Any]) -> bool:
    if str(item.get("slot") or "") != "prop":
        return True
    return str(item.get("value") or "").strip() not in INVALID_PROP_VALUES


def _normalize_final_note_item(item: dict[str, Any]) -> dict[str, Any] | None:
    slot = str(item.get("slot") or "").strip()
    if slot != "pose":
        return item
    value = _sanitize_pose_value(str(item.get("value") or ""))
    if not value:
        return None
    normalized = dict(item)
    normalized["value"] = value
    return normalized


def _sanitize_pose_value(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    replaced = POSE_VALUE_REPLACEMENTS.get(raw)
    if replaced:
        return replaced
    if _contains_any(raw, POSE_LOCATION_PATTERNS):
        return ""
    return raw


def _is_final_note_slot(slot: str) -> bool:
    return str(slot or "").strip() in {"place", "pose"}


def _final_note_slot_label(slot: str) -> str:
    slot_key = str(slot or "").strip()
    if slot_key == "place":
        return "最终地点"
    if slot_key == "pose":
        return "最终姿势"
    return "终局素材"


def _final_note_set_text(status: dict[str, Any]) -> str:
    return f"{_final_note_slot_label(str(status.get('slot') or ''))}设为：{status['value']}"


def _save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_beijing_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _roll(state: dict[str, Any], dice: int | None = None) -> list[str]:
    if state.get("game_over"):
        return ["本局已经结束。"]
    if state.get("pending_event"):
        pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else {}
        return [f"当前还有惩罚任务「{pending.get('name') or '待处理任务'}」没有结算，先处理任务。"]
    actor = str(state.get("turn_actor") or "xinyue")
    if actor not in ACTORS:
        actor = "xinyue"
    if _actor_blocked(state, actor):
        consumed = _consume_block_action(state, actor)
        state["turn_index"] = int(state.get("turn_index") or 0) + 1
        lines = [f"{_name(actor, DU_VIEW_NAMES)}当前没有行动权，消耗 1 次限制。{consumed}".strip()]
        pass_line = _advance_after_blocked_action(state, actor)
        if pass_line:
            lines.append(pass_line)
        _append_log(state, " / ".join(lines))
        return lines

    rolled = dice if dice in {1, 2, 3, 4, 5, 6} else random.Random(_rng_seed(state, actor, "dice")).randint(1, 6)
    old_pos = int(state["positions"].get(actor) or 0)
    new_pos = min(int(state["board_size"]), old_pos + int(rolled))
    state["positions"][actor] = new_pos
    state["turn_index"] = int(state.get("turn_index") or 0) + 1
    lines = [f"{_name(actor, DU_VIEW_NAMES)}掷出 {rolled}，从 {old_pos} 走到 {new_pos}。"]

    if new_pos >= int(state["board_size"]):
        _finish_game(state, actor)
        lines.append(_finish_line(actor, DU_VIEW_NAMES))
        _append_log(state, " / ".join(lines))
        return lines

    event_lines = _apply_cell_event(state, actor, new_pos)
    lines.extend(event_lines)

    if int(state["positions"].get(actor) or 0) >= int(state["board_size"]):
        _finish_game(state, actor)
        lines.append(_finish_line(actor, DU_VIEW_NAMES))
        _append_log(state, " / ".join(lines))
        return lines

    duel = _maybe_create_duel_pending_event(state, actor)
    if duel:
        other = str(duel.get("opponent") or _other_actor(actor))
        current = str(duel.get("current_actor") or "xinyue")
        lines.append(
            f"同格触发剪刀石头布对抗：{_name(actor, DU_VIEW_NAMES)}和{_name(other, DU_VIEW_NAMES)}在第 {duel.get('cell')} 格，"
            f"等待{_name(current, DU_VIEW_NAMES)}出拳。"
        )

    if state.get("pending_event"):
        lines.append(f"待处理：{_pending_event_brief(state.get('pending_event') or {})}")
        _append_log(state, " / ".join(lines))
        return lines

    turn_line = _advance_turn(state, actor)
    if turn_line:
        lines.append(turn_line)
    _append_log(state, " / ".join(lines))
    return lines


def _apply_cell_event(state: dict[str, Any], actor: str, cell: int) -> list[str]:
    event = CELL_EVENTS.get(cell)
    if not event:
        return [f"第 {cell} 格没有追加状态。"]
    kind = str(event.get("kind") or "")
    name = _cell_event_name(state, cell, event)
    if kind == "state":
        status = _add_status_from_event(state, actor, event)
        if _is_final_note_slot(str(status.get("slot") or "")):
            return [f"第 {cell} 格：{name}，{_final_note_set_text(status)}。"]
        return [f"第 {cell} 格：{name}，{_status_apply_text(status)}。"]
    if kind == "reward":
        card = str(event.get("card") or REWARD_CARD_PASS)
        count = _add_reward_card(state, actor, card)
        return [f"第 {cell} 格：{name}，{_name(actor, DU_VIEW_NAMES)}获得 {_reward_card_label(card)}（现有 {count} 张）。"]
    if kind == "penalty_review":
        pending = _create_review_pending_event(state, actor, cell)
        task = str(pending.get("waiting_task") if pending.get("phase") == "questioning" else pending.get("task") or "").strip()
        return [f"第 {cell} 格：{name}，抽到「{pending['name']}」。{task}"]
    if kind == "penalty_choice":
        pending = _create_choice_pending_event(state, actor, cell)
        choices = " / ".join(str(item.get("label") or item.get("id") or "") for item in pending.get("choices") or [])
        return [f"第 {cell} 格：{name}，抽到「{pending['name']}」。可选：{choices}。"]
    if kind == "lock":
        status = _add_status_from_event(state, actor, event, blocks_action=True)
        return [f"第 {cell} 格：{name}，{_status_apply_text(status, blocks_action=True)}。"]
    if kind == "back":
        status = _add_status_from_event(state, actor, event)
        steps = int(event.get("steps") or 1)
        old_pos = int(state["positions"].get(actor) or 0)
        new_pos = max(0, old_pos - steps)
        state["positions"][actor] = new_pos
        return [f"第 {cell} 格：{name}，{_status_apply_text(status)}，从 {old_pos} 后退 {steps} 格到 {new_pos}。"]
    if kind == "forward":
        steps = int(event.get("steps") or 1)
        old_pos = int(state["positions"].get(actor) or 0)
        new_pos = min(int(state["board_size"]), old_pos + steps)
        state["positions"][actor] = new_pos
        return [f"第 {cell} 格：{name}，从 {old_pos} 前进 {steps} 格到 {new_pos}。"]
    if kind == "forward_reward":
        steps = int(event.get("steps") or 1)
        old_pos = int(state["positions"].get(actor) or 0)
        new_pos = min(int(state["board_size"]), old_pos + steps)
        state["positions"][actor] = new_pos
        card = str(event.get("card") or REWARD_CARD_PASS)
        count = _add_reward_card(state, actor, card)
        return [f"第 {cell} 格：{name}，从 {old_pos} 前进 {steps} 格到 {new_pos}，并获得 {_reward_card_label(card)}（现有 {count} 张）。"]
    if kind == "move_self":
        steps = int(event.get("steps") or 0)
        old_pos, new_pos = _move_actor_position(state, actor, steps)
        return [f"第 {cell} 格：{name}，{_name(actor, DU_VIEW_NAMES)}从 {old_pos} {('前进' if steps >= 0 else '后退')} {abs(steps)} 格到 {new_pos}。"]
    if kind == "move_other":
        other = _other_actor(actor)
        steps = int(event.get("steps") or 0)
        old_pos, new_pos = _move_actor_position(state, other, steps)
        return [f"第 {cell} 格：{name}，{_name(other, DU_VIEW_NAMES)}从 {old_pos} {('前进' if steps >= 0 else '后退')} {abs(steps)} 格到 {new_pos}。"]
    if kind == "move_both":
        steps = int(event.get("steps") or 0)
        moved = []
        for item_actor in ACTORS:
            old_pos, new_pos = _move_actor_position(state, item_actor, steps)
            moved.append(f"{_name(item_actor, DU_VIEW_NAMES)} {old_pos}->{new_pos}")
        action = "前进" if steps >= 0 else "后退"
        return [f"第 {cell} 格：{name}，双方{action} {abs(steps)} 格（{'；'.join(moved)}）。"]
    if kind == "reset_all":
        before = {item_actor: int(state["positions"].get(item_actor) or 0) for item_actor in ACTORS}
        for item_actor in ACTORS:
            state["positions"][item_actor] = 0
        return [f"第 {cell} 格：{name}，双方回到起点（小玥 {before['xinyue']}->0；渡 {before['du']}->0）。"]
    if kind == "reset_self":
        old_pos = int(state["positions"].get(actor) or 0)
        state["positions"][actor] = 0
        return [f"第 {cell} 格：{name}，{_name(actor, DU_VIEW_NAMES)}从 {old_pos} 回到起点。"]
    if kind == "reset_other":
        other = _other_actor(actor)
        old_pos = int(state["positions"].get(other) or 0)
        state["positions"][other] = 0
        return [f"第 {cell} 格：{name}，{_name(other, DU_VIEW_NAMES)}从 {old_pos} 回到起点。"]
    if kind == "finish_self":
        old_pos = int(state["positions"].get(actor) or 0)
        state["positions"][actor] = int(state["board_size"])
        return [f"第 {cell} 格：{name}，{_name(actor, DU_VIEW_NAMES)}从 {old_pos} 直达终点。"]
    if kind == "clear":
        removed = _remove_latest_status(state, actor)
        steps = int(event.get("steps") or 0)
        move_tail = ""
        if steps:
            old_pos = int(state["positions"].get(actor) or 0)
            new_pos = min(int(state["board_size"]), old_pos + steps)
            state["positions"][actor] = new_pos
            move_tail = f"，从 {old_pos} 前进 {steps} 格到 {new_pos}"
        return [f"第 {cell} 格：{name}，解除 {removed or '无可解除状态'}{move_tail}。"]
    if kind == "clear_reward":
        removed = _remove_latest_status(state, actor)
        steps = int(event.get("steps") or 0)
        move_tail = ""
        if steps:
            old_pos = int(state["positions"].get(actor) or 0)
            new_pos = min(int(state["board_size"]), old_pos + steps)
            state["positions"][actor] = new_pos
            move_tail = f"，从 {old_pos} 前进 {steps} 格到 {new_pos}"
        card = str(event.get("card") or REWARD_CARD_PASS)
        count = _add_reward_card(state, actor, card)
        return [f"第 {cell} 格：{name}，解除 {removed or '无可解除状态'}{move_tail}，并获得 {_reward_card_label(card)}（现有 {count} 张）。"]
    if kind == "extend":
        extended = _extend_latest_status(state, actor)
        return [f"第 {cell} 格：{name}，{extended}。"]
    if kind == "replace":
        removed = _remove_latest_status_by_slot(state, actor, str(event.get("slot") or ""))
        status = _add_status_from_event(state, actor, event)
        prefix = f"替换 {removed}，" if removed else ""
        if _is_final_note_slot(str(status.get("slot") or "")):
            return [f"第 {cell} 格：{name}，{prefix}{_final_note_set_text(status)}。"]
        return [f"第 {cell} 格：{name}，{prefix}{_status_apply_text(status)}。"]
    if kind == "swap":
        status = _add_status_from_event(state, actor, event)
        other = _other_actor(actor)
        state["positions"][actor], state["positions"][other] = state["positions"][other], state["positions"][actor]
        if _is_final_note_slot(str(status.get("slot") or "")):
            return [f"第 {cell} 格：{name}，{_final_note_set_text(status)}，双方交换位置。"]
        return [f"第 {cell} 格：{name}，{_status_apply_text(status)}，双方交换位置。"]
    return [f"第 {cell} 格：事件未生效。"]


def _move_actor_position(state: dict[str, Any], actor: str, steps: int) -> tuple[int, int]:
    board_size = int(state.get("board_size") or DEFAULT_BOARD_SIZE)
    old_pos = int(state["positions"].get(actor) or 0)
    new_pos = max(0, min(board_size, old_pos + int(steps)))
    state["positions"][actor] = new_pos
    return old_pos, new_pos


def _maybe_create_duel_pending_event(state: dict[str, Any], actor: str) -> dict[str, Any] | None:
    if state.get("pending_event") or state.get("game_over"):
        return None
    other = _other_actor(actor)
    board_size = int(state.get("board_size") or DEFAULT_BOARD_SIZE)
    pos = int((state.get("positions") or {}).get(actor) or 0)
    other_pos = int((state.get("positions") or {}).get(other) or -1)
    if pos <= 0 or pos >= board_size or pos != other_pos:
        return None
    first_actor = "xinyue"
    pending = {
        "id": secrets.token_hex(4),
        "type": "duel",
        "name": "剪刀石头布对抗",
        "actor": actor,
        "opponent": other,
        "reviewer": other,
        "first_actor": first_actor,
        "current_actor": first_actor,
        "phase": "first_pick",
        "choices": deepcopy(RPS_CHOICES),
        "picks": {},
        "pass_allowed": False,
        "cell": pos,
        "next_actor_after_event": other,
        "created_at": now_beijing_iso(),
    }
    state["pending_event"] = pending
    state["turn_actor"] = first_actor
    return pending


def _submit_pending_event(state: dict[str, Any], text: str) -> list[str]:
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else None
    if not pending:
        return ["当前没有需要提交的惩罚任务。"]
    if str(pending.get("type") or "") != "review":
        return ["当前任务不是提交验收类，请先处理选择惩罚。"]
    if str(pending.get("phase") or "") == "submitted":
        return [f"「{pending.get('name') or '惩罚任务'}」已经提交，等待对方验收。"]
    submission = str(text or "").strip()
    if not submission:
        return ["提交内容不能为空。"]
    actor = str(pending.get("actor") or "xinyue")
    reviewer = str(pending.get("reviewer") or _other_actor(actor))
    if str(pending.get("phase") or "") == "questioning":
        pending["phase"] = "assigned"
        pending["question_text"] = submission
        pending["questioned_at"] = now_beijing_iso()
        state["turn_actor"] = actor
        line = f"{_name(reviewer, DU_VIEW_NAMES)}提交了「{pending.get('name') or '惩罚任务'}」的问题，等待{_name(actor, DU_VIEW_NAMES)}回答。"
        _append_log(state, line)
        return [line]
    pending["phase"] = "submitted"
    pending["submission_text"] = submission
    pending["submitted_at"] = now_beijing_iso()
    state["turn_actor"] = reviewer
    line = f"{_name(actor, DU_VIEW_NAMES)}提交了「{pending.get('name') or '惩罚任务'}」，等待{_name(reviewer, DU_VIEW_NAMES)}验收。"
    _append_log(state, line)
    return [line]


def _approve_pending_event(state: dict[str, Any]) -> list[str]:
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else None
    if not pending:
        return ["当前没有待验收的惩罚任务。"]
    if str(pending.get("type") or "") != "review":
        return ["当前任务不是验收类。"]
    if str(pending.get("phase") or "") != "submitted":
        return ["任务还没有提交，不能验收通过。"]
    actor = str(pending.get("actor") or "xinyue")
    reviewer = str(pending.get("reviewer") or _other_actor(actor))
    name = str(pending.get("name") or "惩罚任务")
    state["pending_event"] = None
    lines = [f"{_name(reviewer, DU_VIEW_NAMES)}通过了{_name(actor, DU_VIEW_NAMES)}的「{name}」。"]
    pass_result = str(pending.get("pass_result") or "").strip()
    if pass_result:
        lines.append(pass_result)
    turn_line = _advance_turn(state, actor)
    if turn_line:
        lines.append(turn_line)
    _append_log(state, " / ".join(lines))
    return lines


def _reject_pending_event(state: dict[str, Any], reason: str = "") -> list[str]:
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else None
    if not pending:
        return ["当前没有待打回的惩罚任务。"]
    if str(pending.get("type") or "") != "review":
        return ["当前任务不是验收类。"]
    if str(pending.get("phase") or "") != "submitted":
        return ["任务还没有提交，不能打回。"]
    actor = str(pending.get("actor") or "xinyue")
    reviewer = str(pending.get("reviewer") or _other_actor(actor))
    name = str(pending.get("name") or "惩罚任务")
    pending["phase"] = "assigned"
    pending["reject_count"] = max(0, int(pending.get("reject_count") or 0)) + 1
    pending["rejected_at"] = now_beijing_iso()
    pending["last_reject_reason"] = str(reason or "").strip()
    pending["submission_text"] = ""
    state["turn_actor"] = actor
    prompt = str(pending.get("reject_prompt") or "对方认为你的任务完成度不够，请重新提交。").strip()
    lines = [f"{_name(reviewer, DU_VIEW_NAMES)}打回了{_name(actor, DU_VIEW_NAMES)}的「{name}」。", prompt]
    _append_log(state, " / ".join(lines))
    return lines


def _choose_pending_option(state: dict[str, Any], choice_id: str) -> list[str]:
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else None
    if not pending:
        return ["当前没有待选择的惩罚。"]
    if str(pending.get("type") or "") == "duel":
        return _choose_duel_option(state, choice_id)
    if str(pending.get("type") or "") != "choice":
        return ["当前任务不是选择惩罚。"]
    actor = str(pending.get("actor") or "xinyue")
    selected = _find_pending_choice(pending, choice_id)
    if not selected:
        choices = " / ".join(str(item.get("label") or item.get("id") or "") for item in pending.get("choices") or [])
        return [f"没有这个选项。可选：{choices}。"]
    state["pending_event"] = None
    lines = _apply_choice_effect(state, actor, selected)
    turn_line = _advance_turn(state, actor)
    if turn_line:
        lines.append(turn_line)
    _append_log(state, " / ".join(lines))
    return lines


def _find_pending_choice(pending: dict[str, Any], choice_id: str) -> dict[str, Any] | None:
    raw = str(choice_id or "").strip()
    normalized = raw.replace("【", "").replace("】", "").strip()
    if normalized.startswith("选择"):
        normalized = normalized.removeprefix("选择").strip(" ：:")
    for prefix in ("剪刀石头布", "石头剪刀布"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix).strip(" ：:")
            break
    normalized_id = RPS_ALIASES.get(normalized, normalized)
    for choice in pending.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        cid = str(choice.get("id") or "").strip()
        label = str(choice.get("label") or "").strip()
        if normalized and normalized in {cid, label}:
            return deepcopy(choice)
        if normalized_id and normalized_id == cid:
            return deepcopy(choice)
        if normalized and (normalized in label or label in normalized):
            return deepcopy(choice)
    return None


def _choose_duel_option(state: dict[str, Any], choice_id: str) -> list[str]:
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else None
    if not pending or str(pending.get("type") or "") != "duel":
        return ["当前没有剪刀石头布对抗。"]
    actor = str(pending.get("actor") or "xinyue")
    opponent = str(pending.get("opponent") or _other_actor(actor))
    current = str(pending.get("current_actor") or actor)
    if str(state.get("turn_actor") or "") != current:
        return [f"现在不是{_name(current, DU_VIEW_NAMES)}的出拳回合。"]
    selected = _find_pending_choice(pending, choice_id)
    if not selected:
        return ["没有这个出拳。可选：石头 / 剪刀 / 布。"]
    selected_id = str(selected.get("id") or "")
    selected_label = str(selected.get("label") or selected_id)
    picks = pending.get("picks") if isinstance(pending.get("picks"), dict) else {}
    picks[current] = selected_id
    pending["picks"] = picks

    if opponent not in picks or actor not in picks:
        next_actor = opponent if current == actor else actor
        pending["current_actor"] = next_actor
        pending["phase"] = "second_pick"
        state["turn_actor"] = next_actor
        line = f"{_name(current, DU_VIEW_NAMES)}已出拳，等待：{_name(next_actor, DU_VIEW_NAMES)}出拳。"
        _append_log(state, line)
        return [line]

    actor_pick = str(picks.get(actor) or "")
    opponent_pick = str(picks.get(opponent) or "")
    actor_label = _rps_label(actor_pick)
    opponent_label = _rps_label(opponent_pick)
    if actor_pick == opponent_pick:
        first_actor = str(pending.get("first_actor") or "xinyue")
        pending["picks"] = {}
        pending["current_actor"] = first_actor
        pending["phase"] = "first_pick"
        state["turn_actor"] = first_actor
        line = f"系统判定：双方都出了{actor_label}，平局，重新选择。"
        _append_log(state, line)
        return [line]

    winner = actor if RPS_BEATS.get(actor_pick) == opponent_pick else opponent
    loser = opponent if winner == actor else actor
    before_winner = int(state["positions"].get(winner) or 0)
    before_loser = int(state["positions"].get(loser) or 0)
    board_size = int(state.get("board_size") or DEFAULT_BOARD_SIZE)
    state["positions"][winner] = min(board_size, before_winner + 3)
    state["positions"][loser] = max(0, before_loser - 3)
    state["pending_event"] = None
    winner_pick = actor_label if winner == actor else opponent_label
    loser_pick = opponent_label if winner == actor else actor_label
    lines = [
        (
            f"系统判定：{_name(winner, DU_VIEW_NAMES)}出{winner_pick}，"
            f"{_name(loser, DU_VIEW_NAMES)}出{loser_pick}，{_name(winner, DU_VIEW_NAMES)}赢下对抗。"
        ),
        (
            f"{_name(winner, DU_VIEW_NAMES)}前进 3 格到 {state['positions'][winner]}，"
            f"{_name(loser, DU_VIEW_NAMES)}后退 3 格到 {state['positions'][loser]}。"
        ),
    ]
    if int(state["positions"].get(winner) or 0) >= board_size:
        _finish_game(state, winner)
        lines.append(_finish_line(winner, DU_VIEW_NAMES))
    else:
        state["turn_actor"] = str(pending.get("next_actor_after_event") or _other_actor(actor))
        lines.append(f"下一次行动：{_name(str(state['turn_actor']), DU_VIEW_NAMES)}。")
    _append_log(state, " / ".join(lines))
    return lines


def _rps_label(choice_id: str) -> str:
    normalized = RPS_ALIASES.get(str(choice_id or "").strip(), str(choice_id or "").strip())
    for choice in RPS_CHOICES:
        if choice["id"] == normalized:
            return choice["label"]
    return normalized or "未出拳"


def _use_pass_card(state: dict[str, Any]) -> tuple[list[str], bool]:
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else None
    if not pending:
        return ["当前没有可跳过的惩罚任务。"], False
    actor = str(pending.get("actor") or "xinyue")
    if not pending.get("pass_allowed", True):
        return [f"「{pending.get('name') or '惩罚任务'}」不能使用Pass卡。"], False
    if str(pending.get("type") or "") == "review" and str(pending.get("phase") or "") == "submitted":
        return ["任务已经提交，不能再用Pass卡跳过。"], False
    if max(0, int(state.get("pass_skips_used") or 0)) >= PASS_SKIP_LIMIT:
        return ["本局已经使用过一次Pass卡，不能再跳过惩罚任务。"], False
    if not _consume_reward_card(state, actor, REWARD_CARD_PASS):
        return [f"{_name(actor, DU_VIEW_NAMES)}没有Pass卡，不能跳过。"], False
    state["pass_skips_used"] = max(0, int(state.get("pass_skips_used") or 0)) + 1
    name = str(pending.get("name") or "惩罚任务")
    state["pending_event"] = None
    lines = [f"{_name(actor, DU_VIEW_NAMES)}使用Pass卡，跳过「{name}」。"]
    turn_line = _advance_turn(state, actor)
    if turn_line:
        lines.append(turn_line)
    _append_log(state, " / ".join(lines))
    return lines, True


def _apply_choice_effect(state: dict[str, Any], actor: str, choice: dict[str, Any]) -> list[str]:
    label = str(choice.get("label") or choice.get("id") or "选项")
    effect = choice.get("effect") if isinstance(choice.get("effect"), dict) else {}
    kind = str(effect.get("kind") or "").strip()
    if kind == "move":
        steps = int(effect.get("steps") or 0)
        old_pos = int(state["positions"].get(actor) or 0)
        new_pos = max(0, min(int(state.get("board_size") or DEFAULT_BOARD_SIZE), old_pos + steps))
        state["positions"][actor] = new_pos
        direction = "前进" if steps >= 0 else "后退"
        return [f"{_name(actor, DU_VIEW_NAMES)}选择「{label}」，从 {old_pos} {direction} {abs(steps)} 格到 {new_pos}。"]
    if kind == "upgrade_status_level":
        slot = str(effect.get("slot") or "prop")
        delta = int(effect.get("delta") or 1)
        upgraded = _upgrade_latest_status_level(state, actor, slot, delta)
        if upgraded:
            return [f"{_name(actor, DU_VIEW_NAMES)}选择「{label}」，{upgraded}。"]
        return [f"{_name(actor, DU_VIEW_NAMES)}选择「{label}」，但没有可上调的状态。"]
    if kind in {"add_status", "add_block", "add_status_and_block"}:
        event = _event_from_choice_effect(effect)
        status = _add_status_from_event(state, actor, event, blocks_action=kind in {"add_block", "add_status_and_block"})
        if kind in {"add_block", "add_status_and_block"}:
            return [f"{_name(actor, DU_VIEW_NAMES)}选择「{label}」，{_status_apply_text(status, blocks_action=True)}。"]
        if _is_final_note_slot(str(status.get("slot") or "")):
            return [f"{_name(actor, DU_VIEW_NAMES)}选择「{label}」，{_final_note_set_text(status)}。"]
        return [f"{_name(actor, DU_VIEW_NAMES)}选择「{label}」，{_status_apply_text(status)}。"]
    return [f"{_name(actor, DU_VIEW_NAMES)}选择「{label}」。"]


def _event_from_choice_effect(effect: dict[str, Any]) -> dict[str, Any]:
    duration_type = str(effect.get("duration_type") or "until_clear").strip()
    event = {
        "slot": str(effect.get("slot") or "prop"),
        "duration": duration_type if duration_type in {"until_finish", "minutes"} else "until_clear",
    }
    if "actions" in effect:
        event["actions"] = max(1, int(effect.get("actions") or 1))
    return event


def _upgrade_latest_status_level(state: dict[str, Any], actor: str, slot: str, delta: int) -> str:
    statuses = state["statuses"].get(actor) or []
    for status in reversed(statuses):
        if str(status.get("slot") or "") != slot:
            continue
        if slot == "prop" and not _status_supports_level(status):
            continue
        status["level"] = max(1, int(status.get("level") or 1)) + max(1, int(delta or 1))
        return f"{_status_brief(status)}"
    return ""


def _add_status_from_event(
    state: dict[str, Any],
    actor: str,
    event: dict[str, Any],
    *,
    blocks_action: bool = False,
) -> dict[str, Any]:
    slot_key = str(event.get("slot") or "").strip()
    slot = _slot_by_key(slot_key)
    label = _slot_display_label(slot_key, str(slot.get("label") or slot_key or "状态"))
    value = _pick_slot_value(state, actor, int(state["positions"].get(actor) or 0), slot_key)
    if slot_key == "prop":
        existing = _find_status_by_value(state, actor, slot_key, value)
        if existing:
            existing_result = deepcopy(existing)
            if _status_supports_level(existing):
                existing["level"] = max(1, int(existing.get("level") or 1)) + 1
                existing_result = deepcopy(existing)
                existing_result["_existing_result"] = "level"
                return existing_result
            if blocks_action:
                existing["duration_type"] = "actions"
                existing["remaining_actions"] = max(1, int(existing.get("remaining_actions") or 0)) + max(1, int(event.get("actions") or 1))
                existing["blocks_action"] = True
                existing_result = deepcopy(existing)
                existing_result["_existing_result"] = "block"
                return existing_result
            existing_result["_existing_result"] = "skip"
            return existing_result
    status = {
        "id": secrets.token_hex(4),
        "slot": slot_key,
        "label": label,
        "value": value,
        "created_at": now_beijing_iso(),
        "blocks_action": bool(blocks_action),
    }
    duration = str(event.get("duration") or "").strip()
    if blocks_action:
        status["duration_type"] = "actions"
        status["remaining_actions"] = max(1, int(event.get("actions") or 1))
    elif duration == "minutes":
        minutes = max(1, int(event.get("minutes") or 10))
        status["duration_type"] = "minutes"
        status["minutes"] = minutes
        status["expires_at"] = _iso_from_now(minutes)
    elif duration == "until_finish":
        status["duration_type"] = "until_finish"
    else:
        status["duration_type"] = "until_clear"
    if _is_final_note_slot(slot_key) and not blocks_action:
        _set_final_note_item(state, status)
    else:
        state["statuses"][actor].append(status)
    if slot_key == "theme":
        state["theme_profile"] = _theme_profile_for(value)
    return status


def _find_status_by_value(state: dict[str, Any], actor: str, slot_key: str, value: str) -> dict[str, Any] | None:
    clean_value = str(value or "").strip()
    if not clean_value:
        return None
    for item in state.get("statuses", {}).get(actor, []):
        if not isinstance(item, dict):
            continue
        if str(item.get("slot") or "").strip() == slot_key and str(item.get("value") or "").strip() == clean_value:
            return item
    return None


def _status_apply_text(status: dict[str, Any], *, blocks_action: bool = False) -> str:
    label = str(status.get("label") or _slot_label(str(status.get("slot") or "")) or "状态")
    value = str(status.get("value") or "状态")
    existing_result = str(status.get("_existing_result") or "")
    if existing_result == "level":
        return f"{label}：{value}已存在，档位上调为 {max(1, int(status.get('level') or 1))} 档"
    if existing_result == "block":
        return f"{label}：{value}已存在，行动限制延长到 {max(1, int(status.get('remaining_actions') or 1))} 次"
    if existing_result == "skip":
        return f"{label}：{value}已存在，不重复追加"
    if blocks_action:
        return f"追加 {label}：{value}，失去 {max(1, int(status.get('remaining_actions') or 1))} 次行动权"
    return f"追加 {label}：{value}（{_duration_text(status)}）"


def _slot_by_key(key: str) -> dict[str, Any]:
    for slot in BOARD_SLOTS:
        if str(slot.get("key") or "").strip() == key:
            return slot
    return {"key": key, "label": key or "状态", "options": [key or "状态"]}


def _set_final_note_item(state: dict[str, Any], status: dict[str, Any]) -> None:
    slot = str(status.get("slot") or "").strip()
    items = state.setdefault("final_note_items", [])
    state["final_note_items"] = [
        item for item in items if isinstance(item, dict) and str(item.get("slot") or "").strip() != slot
    ]
    state["final_note_items"].append(status)


def _pick_slot_value(state: dict[str, Any], actor: str, cell: int, slot_key: str) -> str:
    if slot_key == "limit":
        options = _limit_options_for_theme(state)
        slot_label = "限制"
    else:
        slot = _slot_by_key(slot_key)
        options = [str(item).strip() for item in slot.get("options", []) if str(item).strip()]
        options = _filter_options_for_theme(state, slot_key, options)
        slot_label = str(slot.get("label") or slot_key or "状态").strip()
    if slot_key == "pose":
        options = _filter_pose_options(options)
    options = _filter_options_for_actor(actor, slot_key, options)
    if slot_key == "prop":
        existing_values = {
            str(item.get("value") or "").strip()
            for item in state.get("statuses", {}).get(actor, [])
            if isinstance(item, dict) and str(item.get("slot") or "").strip() == "prop"
        }
        unused_options = [item for item in options if item not in existing_values]
        if unused_options:
            options = unused_options
    if not options:
        return slot_label
    status_count = len(state.get("final_note_items") or []) if _is_final_note_slot(slot_key) else len(state["statuses"].get(actor, []))
    rng = random.Random(_rng_seed(state, actor, slot_key, str(cell), str(status_count)))
    return options[rng.randrange(len(options))]


def _limit_options_for_theme(state: dict[str, Any]) -> list[str]:
    profile = state.get("theme_profile") if isinstance(state.get("theme_profile"), dict) else {}
    theme = str(profile.get("theme") or "").strip()
    options = (*(THEME_LIMIT_OPTIONS.get(theme) or ()), *DEFAULT_LIMIT_OPTIONS)
    seen: set[str] = set()
    result: list[str] = []
    for item in options:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _filter_pose_options(options: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in options:
        value = _sanitize_pose_value(item)
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _filter_options_for_actor(actor: str, slot_key: str, options: list[str]) -> list[str]:
    if slot_key != "prop":
        return options
    if actor == "du":
        filtered = [
            item
            for item in options
            if not _contains_any(item, DU_ACTOR_FORBIDDEN_PROP_PATTERNS)
        ]
        return filtered or options
    if actor != "xinyue":
        return options
    return [
        item
        for item in options
        if not _contains_any(item, HUMAN_ACTOR_FORBIDDEN_PROP_PATTERNS)
    ]


def _filter_options_for_theme(state: dict[str, Any], slot_key: str, options: list[str]) -> list[str]:
    if slot_key == "limit":
        return options
    if slot_key not in {"task", "limit"}:
        return _prefer_options_for_theme(state, slot_key, options)
    direction = str((state.get("theme_profile") or {}).get("direction") or "").strip()
    if direction == "du_leads":
        return _prefer_options_for_theme(state, slot_key, _filter_du_leads_options(slot_key, options))
    if direction == "xinyue_leads":
        return _prefer_options_for_theme(state, slot_key, _filter_xinyue_leads_options(slot_key, options))
    return _prefer_options_for_theme(state, slot_key, options)


def _prefer_options_for_theme(state: dict[str, Any], slot_key: str, options: list[str]) -> list[str]:
    profile = state.get("theme_profile") if isinstance(state.get("theme_profile"), dict) else {}
    theme = str(profile.get("theme") or "").strip()
    style = THEME_CELL_STYLES.get(theme) or {}
    preferred = (style.get("preferred") or {}).get(slot_key) if isinstance(style.get("preferred"), dict) else None
    patterns = tuple(str(item).strip() for item in (preferred or ()) if str(item).strip())
    if not patterns:
        return options
    filtered = [item for item in options if _contains_any(item, patterns)]
    return filtered or options


def _filter_du_leads_options(slot_key: str, options: list[str]) -> list[str]:
    if slot_key == "task":
        filtered = [
            item
            for item in options
            if not _contains_any(item, BOARD_XINYUE_CONTROL_TASK_PATTERNS)
        ]
        return filtered or options
    return options


def _filter_xinyue_leads_options(slot_key: str, options: list[str]) -> list[str]:
    if slot_key == "task":
        preferred = [
            item
            for item in options
            if _contains_any(item, BOARD_XINYUE_CONTROL_TASK_PATTERNS)
            or _contains_any(item, ("伺候小玥", "给小玥看", "交给小玥", "听小玥", "小玥决定", "小玥命令"))
        ]
        pool = preferred or options
        filtered = [item for item in pool if not _contains_any(item, DU_CONTROL_TASK_PATTERNS)]
        return filtered or pool or options
    return options


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern and pattern in text for pattern in patterns)


def _prop_supports_level(value: Any) -> bool:
    return _contains_any(str(value or ""), LEVELABLE_PROP_PATTERNS)


def _status_supports_level(status: dict[str, Any]) -> bool:
    return str(status.get("slot") or "").strip() == "prop" and _prop_supports_level(status.get("value"))


def _theme_profile_for(theme: str) -> dict[str, str]:
    label = str(theme or "").strip()
    if not label:
        return {}
    if label in THEME_DIRECTION_XINYUE_LEADS:
        return {"theme": label, "direction": "xinyue_leads", "direction_label": "小玥主导"}
    if label in THEME_DIRECTION_DU_LEADS:
        return {"theme": label, "direction": "du_leads", "direction_label": "渡主导"}
    return {"theme": label, "direction": "open", "direction_label": "开放方向"}


def _normalize_theme_profile(profile: dict[str, Any]) -> dict[str, str]:
    theme = str(profile.get("theme") or "").strip()
    if not theme or not _theme_is_allowed(theme):
        return {}
    return _theme_profile_for(theme)


def _theme_is_allowed(theme: str) -> bool:
    label = str(theme or "").strip()
    return bool(label and label in set(_opening_theme_options()))


def _opening_theme_options() -> list[str]:
    slot = _slot_by_key("theme")
    options = [str(item).strip() for item in slot.get("options", []) if str(item).strip()]
    return options or ["本局玩法"]


def _assign_opening_theme(state: dict[str, Any]) -> dict[str, str]:
    profile = state.get("theme_profile") if isinstance(state.get("theme_profile"), dict) else {}
    normalized = _normalize_theme_profile(profile)
    if normalized:
        state["theme_profile"] = normalized
        return normalized
    options = _opening_theme_options()
    rng = random.Random(_rng_seed(state, "opening_theme"))
    theme = options[rng.randrange(len(options))]
    profile = _theme_profile_for(theme)
    state["theme_profile"] = profile
    return profile


def _rng_seed(state: dict[str, Any], *parts: str) -> str:
    base = [str(state.get("seed") or ""), str(state.get("turn_index") or 0)]
    base.extend(str(part) for part in parts)
    return ":".join(base)


def _remove_latest_status(state: dict[str, Any], actor: str) -> str:
    statuses = state["statuses"].get(actor) or []
    if not statuses:
        return ""
    item = statuses.pop()
    if str(item.get("slot") or "") == "theme":
        _sync_theme_profile(state)
    return _status_brief(item)


def _remove_latest_status_by_slot(state: dict[str, Any], actor: str, slot: str) -> str:
    if _is_final_note_slot(slot):
        items = state.get("final_note_items") if isinstance(state.get("final_note_items"), list) else []
        for idx in range(len(items) - 1, -1, -1):
            item = items[idx]
            if str(item.get("slot") or "") == slot:
                items.pop(idx)
                return _status_brief(item)
        return ""
    statuses = state["statuses"].get(actor) or []
    for idx in range(len(statuses) - 1, -1, -1):
        item = statuses[idx]
        if str(item.get("slot") or "") == slot:
            statuses.pop(idx)
            if slot == "theme":
                _sync_theme_profile(state)
            return _status_brief(item)
    return ""


def _sync_theme_profile(state: dict[str, Any]) -> None:
    for actor in reversed(ACTORS):
        for status in reversed(state["statuses"].get(actor) or []):
            if str(status.get("slot") or "") == "theme":
                profile = _normalize_theme_profile({"theme": str(status.get("value") or "")})
                if profile:
                    state["theme_profile"] = profile
                    return
    state["theme_profile"] = {}


def _extend_latest_status(state: dict[str, Any], actor: str) -> str:
    statuses = state["statuses"].get(actor) or []
    if not statuses:
        return "没有可延长状态"
    item = statuses[-1]
    if item.get("duration_type") == "actions":
        item["remaining_actions"] = max(0, int(item.get("remaining_actions") or 0)) + 1
        return f"{_status_brief(item)} 延长 1 次行动"
    if item.get("duration_type") == "minutes":
        item["minutes"] = max(1, int(item.get("minutes") or 0)) + 5
        item["expires_at"] = _iso_from_now(5, base_iso=str(item.get("expires_at") or ""))
        return f"{_status_brief(item)} 延长 5 分钟"
    item["duration_type"] = "until_finish"
    return f"{_status_brief(item)} 锁定到终点"


def _actor_blocked(state: dict[str, Any], actor: str) -> bool:
    for status in state["statuses"].get(actor) or []:
        if status.get("blocks_action") and int(status.get("remaining_actions") or 0) > 0:
            return True
    return False


def _consume_block_action(state: dict[str, Any], actor: str) -> str:
    statuses = state["statuses"].get(actor) or []
    for status in list(statuses):
        if not status.get("blocks_action") or int(status.get("remaining_actions") or 0) <= 0:
            continue
        status["remaining_actions"] = int(status.get("remaining_actions") or 0) - 1
        brief = _status_action_brief(status)
        if int(status.get("remaining_actions") or 0) <= 0:
            status.pop("blocks_action", None)
            status.pop("remaining_actions", None)
            if str(status.get("slot") or "") == "prop":
                status["duration_type"] = "until_clear"
                return f"{brief} 停步已结束，道具惩罚仍保留。"
            statuses.remove(status)
            return f"{brief} 停步已结束。"
        return f"{brief} 还剩 {status.get('remaining_actions')} 次。"
    return ""


def _status_action_brief(status: dict[str, Any]) -> str:
    label = _status_label(status)
    value = str(status.get("value") or "").strip() or "状态"
    level = max(1, int(status.get("level") or 1))
    if _status_supports_level(status) and level > 1:
        value = f"{value}（{level}档）"
    return f"{label}：{value}"


def _advance_after_blocked_action(state: dict[str, Any], actor: str) -> str:
    next_actor = _other_actor(actor)
    if _actor_blocked(state, next_actor):
        consumed = _consume_block_action(state, next_actor)
        state["turn_index"] = int(state.get("turn_index") or 0) + 1
        state["turn_actor"] = actor
        return (
            f"{_name(next_actor, DU_VIEW_NAMES)}也没有行动权，自动消耗 1 次限制。"
            f"{_name(actor, DU_VIEW_NAMES)}继续处理停步回合。{consumed}"
        ).strip()
    state["turn_actor"] = next_actor
    return f"下一次行动：{_name(next_actor, DU_VIEW_NAMES)}。"


def _advance_turn(state: dict[str, Any], actor: str) -> str:
    next_actor = _other_actor(actor)
    if _actor_blocked(state, next_actor):
        consumed = _consume_block_action(state, next_actor)
        if _actor_blocked(state, next_actor):
            state["turn_actor"] = actor
            return f"{_name(next_actor, DU_VIEW_NAMES)}没有行动权，{_name(actor, DU_VIEW_NAMES)}继续行动。{consumed}".strip()
        state["turn_actor"] = next_actor
        return f"{_name(next_actor, DU_VIEW_NAMES)}的行动权恢复。{consumed}".strip()
    state["turn_actor"] = next_actor
    return f"下一次行动：{_name(next_actor, DU_VIEW_NAMES)}。"


def _finish_game(state: dict[str, Any], actor: str) -> None:
    other = _other_actor(actor)
    state["positions"][actor] = int(state["board_size"])
    state["statuses"][actor] = []
    state["game_over"] = True
    state["winner"] = actor
    state["result"] = "winner_control"
    state["ended_at"] = now_beijing_iso()
    state["final_note"] = _build_final_note(state, winner=actor, target=other)


def _finish_line(actor: str, names: dict[str, str]) -> str:
    return f"{_name(actor, names)}到达终点，状态清空，并获得最终状态栏决定权。"


def _append_final_status(state: dict[str, Any], slot_alias: str, value: str, level: int = 1) -> list[str]:
    checked = _editable_final_note_target(state)
    if isinstance(checked, list):
        return checked
    note, target = checked

    slot = _final_append_slot(slot_alias)
    if not slot:
        return ["请选择要追加的类型：道具惩罚或限制。"]
    clean_value = " ".join(str(value or "").split()).strip()
    if not clean_value:
        return ["请先填写要追加的内容。"]

    item = {
        "id": secrets.token_hex(4),
        "slot": slot,
        "label": _slot_label(slot),
        "value": clean_value,
        "created_at": now_beijing_iso(),
        "duration_type": "final_note",
        "level": max(1, min(5, int(level or 1))) if slot == "prop" and _prop_supports_level(clean_value) else 1,
        "blocks_action": False,
    }
    state["statuses"].setdefault(target, []).append(item)
    note["sent"] = False
    note["sent_at"] = ""
    return [f"已追加到终局小纸条：{_status_brief(item)}。"]


def _remove_final_status(state: dict[str, Any], slot_alias: str, value: str) -> list[str]:
    checked = _editable_final_note_target(state)
    if isinstance(checked, list):
        return checked
    note, target = checked
    slot = _final_append_slot(slot_alias)
    if not slot:
        return ["请选择要取消的类型：道具惩罚或限制。"]
    clean_value = " ".join(str(value or "").split()).strip()
    if not clean_value:
        return ["请先选择要取消的内容。"]
    statuses = state["statuses"].setdefault(target, [])
    for index in range(len(statuses) - 1, -1, -1):
        item = statuses[index]
        if not isinstance(item, dict):
            continue
        if str(item.get("slot") or "") == slot and str(item.get("value") or "").strip() == clean_value:
            removed = statuses.pop(index)
            note["sent"] = False
            note["sent_at"] = ""
            return [f"已从终局小纸条取消：{_status_brief(removed)}。"]
    return [f"当前没有启用：{clean_value}。"]


def _editable_final_note_target(state: dict[str, Any]) -> tuple[dict[str, Any], str] | list[str]:
    if not state.get("game_over"):
        return ["本局还没有结束，不能修改终局状态。"]
    note = state.get("final_note") if isinstance(state.get("final_note"), dict) else None
    if not note:
        winner = str(state.get("winner") or "")
        if winner not in ACTORS:
            return ["当前没有可修改的终局小纸条。"]
        note = _build_final_note(state, winner=winner, target=_other_actor(winner))
        state["final_note"] = note
    if note.get("sent"):
        return ["终局小纸条已经发送，不能再修改状态。"]
    winner = str(note.get("winner") or state.get("winner") or "")
    if winner != "xinyue":
        return ["只有你先到终点时，才能修改终局状态。"]
    target = str(note.get("target") or _other_actor(winner))
    if target not in ACTORS:
        target = _other_actor(winner)
        note["target"] = target
    return note, target


def _final_append_slot(slot_alias: str) -> str:
    key = str(slot_alias or "").strip()
    return FINAL_APPEND_SLOT_ALIASES.get(key) or FINAL_APPEND_SLOT_ALIASES.get(key.lower(), "")


def _build_final_note(state: dict[str, Any], *, winner: str, target: str) -> dict[str, Any]:
    now = now_beijing_iso()
    profile = state.get("theme_profile") if isinstance(state.get("theme_profile"), dict) else {}
    return {
        "id": secrets.token_hex(4),
        "winner": winner,
        "target": target,
        "theme": str(profile.get("theme") or ""),
        "created_at": now,
        "sent": False,
        "sent_at": "",
    }


def _final_note_payload(state: dict[str, Any], note: dict[str, Any] | None = None) -> dict[str, Any] | None:
    raw = note if isinstance(note, dict) else state.get("final_note") if isinstance(state.get("final_note"), dict) else None
    if not raw:
        return None
    payload = deepcopy(raw)
    payload["text"] = _final_note_text(state, payload, PLAYER_VIEW_NAMES)
    payload["du_text"] = _final_note_text(state, payload, DU_VIEW_NAMES)
    payload["target_status"] = _render_statuses(
        state,
        str(payload.get("target") or ""),
        PLAYER_VIEW_NAMES,
        include_duration=False,
    )
    payload["final_note_items"] = _render_final_note_items(state, PLAYER_VIEW_NAMES)
    payload["final_place"] = _render_final_note_slot(state, "place", PLAYER_VIEW_NAMES)
    payload["final_pose"] = _render_final_pose(state, PLAYER_VIEW_NAMES)
    return payload


def _final_note_text(state: dict[str, Any], note: dict[str, Any], names: dict[str, str]) -> str:
    winner = str(note.get("winner") or state.get("winner") or "xinyue")
    target = str(note.get("target") or _other_actor(winner))
    theme = str(note.get("theme") or (state.get("theme_profile") or {}).get("theme") or "本局主题")
    target_status = _render_statuses(state, target, names, include_duration=False)
    final_place = _render_final_note_slot(state, "place", names)
    final_pose = _render_final_pose(state, names)
    winner_name = _name(winner, names)
    target_name = _name(target, names)
    winner_line = (
        "你先到终点，你的状态已清空。"
        if winner_name == "我"
        else f"{winner_name}先到终点，{winner_name}的状态已清空。"
    )
    parts = []
    if target_status and target_status != "无":
        parts.append(f"{target_name}当前状态：{target_status}")
    if final_place:
        parts.append(f"最终地点：{final_place}")
    if final_pose:
        parts.append(f"最终姿势：{final_pose}")
    status_line = "；".join(parts) if parts else "没有遗留状态，可以自由决定最后玩法"
    return (
        "【终局涩涩小纸条】\n"
        f"{winner_line}\n"
        f"请根据以下内容安排最后的玩法：{status_line}。\n"
        f"本局主题：{theme}。\n"
        "请尽情享受你们的ooxx吧！"
    )


def _mark_final_note_sent(state: dict[str, Any]) -> list[str]:
    note = state.get("final_note") if isinstance(state.get("final_note"), dict) else None
    if not note:
        return ["当前没有可发送的终局小纸条。"]
    note["sent"] = True
    note["sent_at"] = now_beijing_iso()
    return ["终局小纸条已发送给渡。"]


def _cleanup_expired_statuses(state: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    for actor in ACTORS:
        kept = []
        for status in state["statuses"].get(actor) or []:
            if status.get("duration_type") != "minutes":
                kept.append(status)
                continue
            expires_at = _parse_iso(str(status.get("expires_at") or ""))
            if expires_at and expires_at <= now:
                continue
            kept.append(status)
        state["statuses"][actor] = kept


def _iso_from_now(minutes: int, base_iso: str = "") -> str:
    base = _parse_iso(base_iso) or datetime.now(timezone.utc)
    return (base + timedelta(minutes=minutes)).isoformat()


def _parse_iso(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _result(state: dict[str, Any], lines: list[str], *, command: str, ok: bool = True) -> dict[str, Any]:
    public_state = _public_state(state)
    du_text = _render_text(state, lines, DU_VIEW_NAMES)
    player_text = _render_text(state, lines, PLAYER_VIEW_NAMES)
    return {
        "ok": ok,
        "game_id": GAME_ID,
        "command": command,
        "text": du_text,
        "du_text": du_text,
        "player_text": player_text,
        "board": {
            "du": _render_board(state, DU_VIEW_NAMES),
            "player": _render_board(state, PLAYER_VIEW_NAMES),
        },
        "state": public_state,
        "game_over": bool(state.get("game_over")),
        "winner": str(state.get("winner") or ""),
        "result": str(state.get("result") or ""),
        "commands": ["打开", "status", "roll", "roll 3", "submit 内容", "approve", "reject", "choose 选项", "pass", "new_game", "end_game"],
    }


def _public_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "board_size": int(state.get("board_size") or DEFAULT_BOARD_SIZE),
        "positions": deepcopy(state.get("positions") or {}),
        "turn_actor": str(state.get("turn_actor") or "xinyue"),
        "statuses": deepcopy(state.get("statuses") or {}),
        "final_note_items": deepcopy(state.get("final_note_items") or []),
        "hands": deepcopy(state.get("hands") or {}),
        "pass_skips_used": max(0, int(state.get("pass_skips_used") or 0)),
        "pending_event": deepcopy(state.get("pending_event")),
        "theme_profile": deepcopy(state.get("theme_profile") or {}),
        "theme_options": _opening_theme_options(),
        "final_note": _final_note_payload(state),
        "cell_events": _public_cell_events(state),
        "game_over": bool(state.get("game_over")),
        "winner": str(state.get("winner") or ""),
        "result": str(state.get("result") or ""),
        "updated_at": str(state.get("updated_at") or ""),
    }


def _render_text(state: dict[str, Any], lines: list[str], names: dict[str, str]) -> str:
    translated = [_translate_line(line, names) for line in lines if str(line or "").strip()]
    out = ["【涩涩走格棋】", *translated]
    out.append("")
    out.append(_render_positions(state, names))
    theme_line = _render_theme_profile(state)
    if theme_line:
        out.append(theme_line)
    out.append(f"当前行动：{_name(str(state.get('turn_actor') or 'xinyue'), names)}")
    hands = state.get("hands") if isinstance(state.get("hands"), dict) else {}
    pass_bits = []
    for actor in ACTORS:
        hand = hands.get(actor) if isinstance(hands.get(actor), dict) else {}
        count = max(0, int(hand.get(REWARD_CARD_PASS) or 0))
        if count:
            pass_bits.append(f"{_name(actor, names)} {count} 张")
    out.append(f"Pass卡：{'；'.join(pass_bits) if pass_bits else '无'}")
    pending = state.get("pending_event") if isinstance(state.get("pending_event"), dict) else None
    if pending:
        out.append(f"待处理：{_translate_line(_pending_event_brief(pending), names)}")
        if str(pending.get("type") or "") == "review":
            phase = str(pending.get("phase") or "")
            if phase == "questioning":
                reviewer = str(pending.get("reviewer") or "")
                waiting = str(pending.get("waiting_task") or "对方正在出题中。").strip()
                prompt = str(pending.get("question_prompt") or "").strip()
                out.append(f"任务：{_translate_line(prompt if reviewer and _name(reviewer, names) == '我' else waiting, names)}")
            elif phase != "submitted":
                task = str(pending.get("task") or "").strip()
                submission = str(pending.get("submission") or "").strip()
                question = str(pending.get("question_text") or "").strip()
                if question:
                    out.append(f"题目：{_translate_line(question, names)}")
                if task:
                    out.append(f"任务：{_translate_line(task, names)}")
                if submission:
                    out.append(f"提交要求：{_translate_line(submission, names)}")
            else:
                out.append(f"提交内容：{_translate_line(str(pending.get('submission_text') or ''), names)}")
        elif str(pending.get("type") or "") == "choice":
            choices = " / ".join(str(item.get("label") or item.get("id") or "") for item in pending.get("choices") or [])
            if choices:
                out.append(f"可选：{_translate_line(choices, names)}")
        elif str(pending.get("type") or "") == "duel":
            current = str(pending.get("current_actor") or pending.get("actor") or "")
            if current:
                out.append(f"当前出拳：{_name(current, names)}")
            out.append("可选：石头 / 剪刀 / 布")
            out.append("指令：发送【剪刀石头布：石头/剪刀/布】")
    out.append("状态栏：")
    for actor in ACTORS:
        out.append(f"- {_name(actor, names)}：{_render_statuses(state, actor, names)}")
    final_place = _render_final_note_slot(state, "place", names)
    if final_place:
        out.append(f"最终地点：{final_place}")
    final_pose = _render_final_pose(state, names)
    if final_pose:
        out.append(f"最终姿势：{final_pose}")
    if state.get("game_over") and state.get("winner"):
        out.append(_finish_line(str(state.get("winner") or ""), names))
        note = _final_note_payload(state)
        if note:
            out.append(_final_note_text(state, note, names))
    out.append(COMMAND_HINT)
    return "\n".join(out).strip()


def _translate_line(line: str, names: dict[str, str]) -> str:
    if names is DU_VIEW_NAMES:
        return line
    text = line.replace("小玥", "\u0000")
    text = re.sub(
        r"(^|[：，。；、\s-])我(?=(掷出|获得|使用Pass卡|没有Pass卡|提交了|已提交|已出拳|出|需要|通过了|打回了|选择|赢下|前进|后退|触发|当前没有行动权|也没有行动权|没有行动权|继续行动|继续处理|的行动权恢复|到达终点|：))",
        r"\1渡",
        text,
    )
    text = re.sub(r"(等待：)我(?=出拳)", r"\1渡", text)
    text = re.sub(r"(和)我(?=触发)", r"\1渡", text)
    text = re.sub(r"(^|[：，。；、\s-])我(?=和\u0000)", r"\1渡", text)
    return text.replace("\u0000", "我")


def _render_board(state: dict[str, Any], names: dict[str, str]) -> str:
    positions = state.get("positions") if isinstance(state.get("positions"), dict) else {}
    board_size = int(state.get("board_size") or DEFAULT_BOARD_SIZE)
    tokens: list[str] = []
    start_markers = _markers_at(positions, 0, names)
    tokens.append("起点" + (f"({start_markers})" if start_markers else ""))
    for pos in range(1, board_size):
        markers = _markers_at(positions, pos, names)
        tokens.append(markers or "□")
    finish_markers = _markers_at(positions, board_size, names, finish=True)
    tokens.append((finish_markers + "/终点") if finish_markers else "终点")
    return " ".join(tokens)


def _render_positions(state: dict[str, Any], names: dict[str, str]) -> str:
    positions = state.get("positions") if isinstance(state.get("positions"), dict) else {}
    board_size = int(state.get("board_size") or DEFAULT_BOARD_SIZE)
    bits = []
    for actor in ACTORS:
        pos = int(positions.get(actor) or 0)
        bits.append(f"{_name(actor, names)} {_position_text(pos, board_size)}")
    return "位置：" + "；".join(bits)


def _position_text(pos: int, board_size: int) -> str:
    if pos <= 0:
        return "起点"
    if pos >= board_size:
        return "终点"
    return f"第 {pos} 格"


def _render_theme_profile(state: dict[str, Any]) -> str:
    profile = state.get("theme_profile") if isinstance(state.get("theme_profile"), dict) else {}
    theme = str(profile.get("theme") or "").strip()
    if not theme:
        return ""
    direction = str(profile.get("direction_label") or "").strip()
    return f"本局主题：{theme}" + (f"（{direction}）" if direction else "")


def _markers_at(positions: dict[str, Any], pos: int, names: dict[str, str], *, finish: bool = False) -> str:
    markers = []
    for actor in ACTORS:
        actor_pos = int(positions.get(actor) or 0)
        if actor_pos == pos or (finish and actor_pos >= pos):
            markers.append(_name(actor, names))
    return "/".join(markers)


def _render_statuses(state: dict[str, Any], actor: str, names: dict[str, str], *, include_duration: bool = True) -> str:
    statuses = [
        status
        for status in state["statuses"].get(actor) or []
        if isinstance(status, dict) and not _is_final_note_slot(str(status.get("slot") or ""))
    ]
    if not statuses:
        return "无"
    groups: dict[str, list[str]] = {}
    for status in statuses[-6:]:
        label = _status_label(status)
        groups.setdefault(label, []).append(_status_value_brief(status, include_duration=include_duration))
    rendered = "；".join(f"{label}：{'、'.join(values)}" for label, values in groups.items())
    return _translate_line(rendered, names)


def _render_final_note_items(state: dict[str, Any], names: dict[str, str]) -> str:
    items = state.get("final_note_items") if isinstance(state.get("final_note_items"), list) else []
    valid_items = [item for item in items if isinstance(item, dict)]
    if not valid_items:
        return "无"
    groups: dict[str, list[str]] = {}
    for item in valid_items[-6:]:
        slot = str(item.get("slot") or "")
        label = _final_note_slot_label(slot) if _is_final_note_slot(slot) else _status_label(item)
        groups.setdefault(label, []).append(_final_note_item_value(item))
    rendered = "；".join(f"{label}：{'、'.join(values)}" for label, values in groups.items())
    return _translate_line(rendered, names)


def _render_final_note_slot(state: dict[str, Any], slot: str, names: dict[str, str]) -> str:
    slot_key = str(slot or "").strip()
    items = state.get("final_note_items") if isinstance(state.get("final_note_items"), list) else []
    values = [
        _final_note_item_value(item)
        for item in items
        if isinstance(item, dict) and str(item.get("slot") or "") == slot_key
    ]
    return _translate_line("、".join(values[-1:]), names)


def _render_final_pose(state: dict[str, Any], names: dict[str, str]) -> str:
    return _render_final_note_slot(state, "pose", names)


def _final_note_item_value(item: dict[str, Any]) -> str:
    return str(item.get("value") or item.get("label") or item.get("slot") or "状态").strip()


def _status_brief(status: dict[str, Any]) -> str:
    label = _status_label(status)
    value = _status_value_brief(status)
    return f"{label}：{value}"


def _status_label(status: dict[str, Any]) -> str:
    return _slot_display_label(str(status.get("slot") or ""), str(status.get("label") or status.get("slot") or "状态"))


def _status_value_brief(status: dict[str, Any], *, include_duration: bool = True) -> str:
    value = str(status.get("value") or "").strip() or "状态"
    level = max(1, int(status.get("level") or 1))
    detail_parts: list[str] = []
    if _status_supports_level(status) and level > 1:
        detail_parts.append(f"{level}档")
    if include_duration:
        duration = _duration_text(status)
        if duration:
            detail_parts.append(duration)
    if detail_parts:
        return f"{value}（{'，'.join(detail_parts)}）"
    return value


def _duration_text(status: dict[str, Any]) -> str:
    duration_type = str(status.get("duration_type") or "").strip()
    if duration_type == "actions":
        count = max(0, int(status.get("remaining_actions") or 0))
        if status.get("blocks_action"):
            return f"停步剩余 {count} 次"
        return f"剩余 {count} 次行动"
    if duration_type == "minutes":
        minutes = int(status.get("minutes") or 0)
        return f"{minutes} 分钟"
    if duration_type == "until_finish":
        return "到终点前有效"
    if duration_type == "until_clear":
        return "待解除"
    return ""


def _append_log(state: dict[str, Any], text: str) -> None:
    log = state.get("event_log") if isinstance(state.get("event_log"), list) else []
    log.append({"at": now_beijing_iso(), "text": str(text or "").strip()})
    state["event_log"] = log[-40:]


def _name(actor: str, names: dict[str, str]) -> str:
    return names.get(actor, actor)


def _other_actor(actor: str) -> str:
    return "du" if actor == "xinyue" else "xinyue"
