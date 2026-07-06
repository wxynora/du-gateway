import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiJson, getOrCreatePanelDeviceId } from "../api";
import homeDay from "../../assets/life-home-day.png";
import homeNightOff from "../../assets/life-home-night-off.png";
import homeNightOn from "../../assets/life-home-night-on.png";

type HomeMode = "day" | "nightOn" | "nightOff";
type HotspotKey = "bed" | "bath" | "study" | "sofa";
type HomeSpotKey = HotspotKey | "kitchen" | "away" | "out";

type PixelHomeActor = {
  spot?: HomeSpotKey;
  spot_label?: string;
  activity?: string;
  text?: string;
  source?: string;
  updated_at?: string;
};

type PixelHomeDynamic = {
  at?: string;
  text?: string;
  spot_label?: string;
  activity?: string;
};

type PixelHomeStateResp = {
  ok?: boolean;
  mode?: HomeMode;
  du?: PixelHomeActor;
  xinyue?: PixelHomeActor;
  du_dynamics?: PixelHomeDynamic[];
  du_vitals?: Record<string, any>;
  du_body_state?: DuBodyState;
  spots?: Array<{ key: HomeSpotKey; label: string }>;
  state?: PixelHomeStateResp;
};

type DuBodyState = {
  toy_types?: string[];
  toy_type?: string;
  intensity?: number;
  desire_value?: number;
  desire_level?: number;
  self_control_level?: number | null;
  stamina_value?: number | string | null;
  sensitivity_value?: number | string | null;
  possessiveness_value?: number | string | null;
  mischief_value?: number | string | null;
  penis_state?: string;
  temperature?: string;
  text?: string;
};

type BodyCalibrationKey = "stamina_value" | "sensitivity_value" | "possessiveness_value" | "mischief_value";

type Hotspot = {
  key: HotspotKey;
  label: string;
  marker: { left: number; top: number };
  menu: { left: number; top: number; align?: "left" | "right" | "top" };
  parts: Array<{
    rect: { left: number; top: number; width: number; height: number };
    shape?: string;
  }>;
  actions: Array<{ label: string }>;
};

type PrivateDrawResult = Array<{
  key: string;
  label: string;
  value: string;
}>;

type PrivateDrawSendStatus = "idle" | "sending" | "sent" | "error";

type PrivateDrawSendResponse = {
  ok?: boolean;
  channel?: string;
  preferred_channel?: string;
  error?: string;
};

type ActivePrivateDrawResponse = {
  ok?: boolean;
  active_private_draw?: {
    entry_number?: string | number;
    result?: PrivateDrawResult;
  } | null;
  error?: string;
};

type LocalPrivateDrawTicket = {
  entryNumber: number;
  result: PrivateDrawResult;
};

const LOCAL_PRIVATE_DRAW_STORAGE_KEY = "pixel-home-local-private-draw";

const HOME_MODES: Record<HomeMode, { image: string; alt: string }> = {
  day: {
    image: homeDay,
    alt: "白天的小家",
  },
  nightOn: {
    image: homeNightOn,
    alt: "夜里开灯的小家",
  },
  nightOff: {
    image: homeNightOff,
    alt: "夜里关灯的小家",
  },
};

const DEFAULT_SPOTS: Array<{ key: HomeSpotKey; label: string }> = [
  { key: "bed", label: "卧室" },
  { key: "bath", label: "浴室" },
  { key: "study", label: "书房" },
  { key: "sofa", label: "客厅沙发" },
  { key: "kitchen", label: "厨房" },
  { key: "away", label: "离家出走" },
  { key: "out", label: "外出" },
];

const BODY_TOY_OPTIONS = ["无", "跳蛋", "震动乳夹", "震动环", "乳夹", "锁精环", "飞机杯", "软绳", "手腕绑带", "眼罩", "口球", "春药"];
const BODY_CALIBRATION_FIELDS: Array<{ key: BodyCalibrationKey; label: string }> = [
  { key: "stamina_value", label: "体力" },
  { key: "sensitivity_value", label: "敏感度" },
  { key: "possessiveness_value", label: "占有欲" },
  { key: "mischief_value", label: "坏心值" },
];

const HOTSPOTS: Hotspot[] = [
  {
    key: "bed",
    label: "卧室",
    marker: { left: 33.5, top: 38.5 },
    menu: { left: 44.5, top: 39, align: "left" },
    parts: [
      {
        rect: { left: 23.2, top: 29.2, width: 21.8, height: 19.4 },
        shape: "polygon(7% 32%, 38% 8%, 72% 13%, 96% 37%, 94% 76%, 61% 99%, 19% 84%, 4% 59%)",
      },
    ],
    actions: [{ label: "睡觉" }, { label: "色色" }],
  },
  {
    key: "bath",
    label: "浴室",
    marker: { left: 78.5, top: 32.5 },
    menu: { left: 84.5, top: 35.5, align: "right" },
    parts: [{ rect: { left: 66.5, top: 16, width: 27, height: 28 } }],
    actions: [{ label: "洗澡" }, { label: "色色" }],
  },
  {
    key: "study",
    label: "书房",
    marker: { left: 54, top: 25.5 },
    menu: { left: 60, top: 26.5, align: "left" },
    parts: [{ rect: { left: 45, top: 15, width: 18, height: 21 } }],
    actions: [{ label: "写日记" }, { label: "看书" }, { label: "色色" }],
  },
  {
    key: "sofa",
    label: "客厅沙发",
    marker: { left: 40.5, top: 80.5 },
    menu: { left: 41, top: 69, align: "top" },
    parts: [
      {
        rect: { left: 28.8, top: 70.2, width: 13.3, height: 18.7 },
        shape: "polygon(0% 22%, 36% 0%, 100% 34%, 98% 78%, 62% 100%, 0% 68%)",
      },
      {
        rect: { left: 31.6, top: 66.6, width: 23.6, height: 11.2 },
        shape: "polygon(0% 56%, 28% 0%, 100% 48%, 78% 100%, 30% 78%)",
      },
      {
        rect: { left: 38.2, top: 75.4, width: 7.4, height: 9.8 },
        shape: "polygon(0% 12%, 54% 0%, 100% 34%, 84% 100%, 13% 86%)",
      },
      {
        rect: { left: 42.2, top: 75.7, width: 13.8, height: 13.8 },
        shape: "polygon(0% 25%, 33% 0%, 100% 40%, 74% 100%, 0% 65%)",
      },
    ],
    actions: [{ label: "看电视" }, { label: "色色" }],
  },
];

const PRIVATE_DRAW_SLOTS = [
  {
    key: "theme",
    label: "玩法",
    options: [
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
    ],
  },
  {
    key: "place",
    label: "地点",
    options: [
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
    ],
  },
  {
    key: "pose",
    label: "姿势",
    options: [
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
    ],
  },
  {
    key: "prop",
    label: "道具",
    options: [
      "领带",
      "眼罩",
      "皮带",
      "丝袜",
      "黑丝袜",
      "白衬衫",
      "制服外套",
      "情趣内衣",
      "束缚带",
      "束腕带",
      "丝带",
      "缎带",
      "项圈",
      "牵引绳",
      "冰块",
      "润滑液",
      "震动棒",
      "跳蛋",
      "跳蛋遥控器",
      "手铐",
      "口球",
      "乳夹",
      "小皮拍",
      "戒尺",
      "铃铛项圈",
      "按摩棒",
      "口红",
      "发绳",
      "腿环",
      "吊袜带",
      "透明胶带",
      "低温蜡烛",
      "羽毛棒",
    ],
  },
  {
    key: "task",
    label: "任务",
    options: [
      "穿裸身围裙伺候小玥",
      "戴项圈听小玥命令",
      "被小玥蒙眼调戏十分钟",
      "被小玥用领带牵着亲",
      "被小玥手交到快射再停",
      "被小玥素股磨到快射",
      "给小玥舔到高潮",
      "用手把小玥弄到腿软",
      "用玩具让小玥高潮一次",
      "只准用嘴取悦小玥",
      "先让小玥高潮一次",
      "让小玥决定今天的称呼",
      "让小玥决定最后射在哪里",
      "被小玥用口红写上标记",
      "把跳蛋遥控器交给小玥",
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
    ],
  },
  {
    key: "limit",
    label: "限制",
    options: [
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
    ],
  },
] as const;

const PRIVATE_DRAW_DU_LEADS_THEMES = new Set([
  "女仆主人play",
  "成人师生play",
  "上司下属play",
  "医生检查play",
  "秘书老板play",
  "成人补课play",
]);

const PRIVATE_DRAW_XINYUE_CONTROL_TASK_PATTERNS = [
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
];

const PRIVATE_DRAW_XINYUE_CONTROL_LIMIT_PATTERNS = [
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
];

const PRIVATE_DRAW_KEEP_LIMIT_PATTERNS = [
  "小玥说停必须立刻停",
  "不准只顾自己爽",
  "不准弄疼小玥",
  "不准跳过前戏",
  "不准直接插入",
  "不准让小玥自己动手",
  "小玥第一次高潮前",
  "小玥没高潮前",
];

function isHomeMode(value: unknown): value is HomeMode {
  return value === "day" || value === "nightOn" || value === "nightOff";
}

function isHomeSpot(value: unknown): value is HomeSpotKey {
  return value === "bed" || value === "bath" || value === "study" || value === "sofa" || value === "kitchen" || value === "away" || value === "out";
}

function resolveLocalMode(): HomeMode {
  const hourText = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    hour12: false,
  }).format(new Date());
  const hour = Number(hourText);
  return hour >= 18 || hour < 6 ? "nightOn" : "day";
}

function actorText(actor: PixelHomeActor | undefined, fallback: string) {
  const text = String(actor?.text || "").trim();
  if (text) return text;
  const label = String(actor?.spot_label || "").trim();
  const activity = String(actor?.activity || "").trim();
  if (label && activity) return statusText(label, activity);
  return fallback;
}

function vitalsNumber(vitals: Record<string, any> | undefined, key: string) {
  const raw = vitals?.parameters?.[key] ?? vitals?.[key];
  const value = Number(raw);
  return Number.isFinite(value) ? value : 0;
}

function duMoodLabel(vitals: Record<string, any> | undefined) {
  if (vitalsNumber(vitals, "intimacy_heat") >= 0.6) return "🥵";
  const tempo = String(vitals?.tempo || "").trim().toLowerCase();
  if (tempo === "up" || tempo === "settle") return "😄";
  if (tempo === "down") return "😭";
  if (tempo === "spike") return "😠";
  return "😐";
}

function bodyToyTypes(state: DuBodyState | undefined) {
  if (Array.isArray(state?.toy_types)) return state.toy_types.filter(Boolean);
  return state?.toy_type ? [state.toy_type] : [];
}

function bodyCalibrationValue(value: unknown) {
  if (typeof value === "undefined" || value === null || String(value).trim() === "") return null;
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return Math.max(0, Math.min(100, Math.round(num)));
}

function bodyCalibrationInputValue(state: DuBodyState, key: BodyCalibrationKey) {
  const value = bodyCalibrationValue(state[key]);
  return value === null ? "" : String(value);
}

function clampMeterValue(value: unknown, max: number) {
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return Math.max(0, Math.min(max, num));
}

function desireMeterValue(state: DuBodyState | undefined) {
  const level = clampMeterValue(state?.desire_level, 5);
  if (level !== null) return level;
  const raw = bodyCalibrationValue(state?.desire_value);
  return raw === null ? null : Math.max(0, Math.min(5, Math.round(raw / 20)));
}

function bodyTextField(state: DuBodyState | undefined, label: string) {
  const text = String(state?.text || "").trim();
  if (!text) return "";
  const match = text.match(new RegExp(`${label}[:：]([^；\\n]+)`));
  return match?.[1]?.trim() || "";
}

function bodyPenisStatus(state: DuBodyState | undefined) {
  return String(state?.penis_state || bodyTextField(state, "阴茎状态") || "").trim();
}

function bodyExtraStatusItems(state: DuBodyState | undefined) {
  const temperature = String(state?.temperature || bodyTextField(state, "体温") || "").trim();
  const toys = bodyToyTypes(state).filter((item) => item && item !== "无");
  const intensity = clampMeterValue(state?.intensity, 5);
  const toyText = toys.length ? `道具：${toys.join("、")}${intensity ? ` · ${intensity}档` : ""}` : "";
  return [temperature ? `体温：${temperature}` : "", toyText].filter(Boolean);
}

function BodyMeter({ label, value, max }: { label: string; value: number; max: number }) {
  const safeValue = Math.max(0, Math.min(max, value));
  const percent = max > 0 ? Math.round((safeValue / max) * 100) : 0;
  return (
    <span className="pixel-home-ref-body-meter">
      <span className="pixel-home-ref-body-meter-head">
        <span>{label}</span>
        <b>
          {safeValue}/{max}
        </b>
      </span>
      <span className="pixel-home-ref-body-rail" aria-hidden="true">
        <span style={{ width: `${percent}%` }} />
      </span>
    </span>
  );
}

function BodyStatusBars({ state }: { state: DuBodyState | undefined }) {
  const penisStatus = bodyPenisStatus(state);
  const extraStatusItems = bodyExtraStatusItems(state);
  const desire = desireMeterValue(state);
  const selfControl = clampMeterValue(state?.self_control_level, 5);
  const calibrationMeters = BODY_CALIBRATION_FIELDS.flatMap((field) => {
    const value = bodyCalibrationValue(state?.[field.key]);
    return value === null ? [] : [{ key: field.key, label: field.label, value }];
  });
  const hasMeters = desire !== null || selfControl !== null || calibrationMeters.length > 0;
  if (!penisStatus && !extraStatusItems.length && !hasMeters) return <span className="pixel-home-ref-body-empty">未记录</span>;
  return (
    <span className="pixel-home-ref-body-content">
      <span className="pixel-home-ref-body-penis">阴茎：{penisStatus || "未记录"}</span>
      {extraStatusItems.length ? (
        <span className="pixel-home-ref-body-status">
          {extraStatusItems.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </span>
      ) : null}
      {desire !== null || selfControl !== null ? (
        <span className="pixel-home-ref-body-primary-bars">
          {desire !== null ? <BodyMeter label="想做指数" value={desire} max={5} /> : null}
          {selfControl !== null ? <BodyMeter label="自制力" value={selfControl} max={5} /> : null}
        </span>
      ) : null}
      {calibrationMeters.length ? (
        <span className="pixel-home-ref-body-secondary-bars">
          {calibrationMeters.map((item) => (
            <BodyMeter key={item.key} label={item.label} value={item.value} max={100} />
          ))}
        </span>
      ) : null}
    </span>
  );
}

function toggleToyType(prev: DuBodyState, item: string): DuBodyState {
  if (item === "无") return { ...prev, toy_types: [], toy_type: "无" };
  const current = bodyToyTypes(prev);
  const next = current.includes(item) ? current.filter((value) => value !== item) : [...current, item];
  return { ...prev, toy_types: next, toy_type: next[0] || "无" };
}

function updateBodyCalibration(prev: DuBodyState, key: BodyCalibrationKey, rawValue: string): DuBodyState {
  const next = { ...prev };
  const value = rawValue.trim();
  if (!value) {
    delete next[key];
    return next;
  }
  const num = Number(value);
  if (!Number.isFinite(num)) return prev;
  next[key] = num;
  return next;
}

function statusText(label: string, activity: string) {
  const clean = String(activity || "").trim().replace(/^正在/, "") || "待着";
  if (clean.startsWith("在")) return clean;
  if (label === "离家出走" || label === "外出") {
    if (clean === "待着" || clean === "休息") return label;
    return `${label}，${clean}`;
  }
  return `在${label}${clean}`;
}

function formatDynamicTime(value: string | undefined) {
  const raw = String(value || "").trim();
  if (!raw) return "现在";
  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) return "现在";
  const diffMinutes = Math.max(0, Math.floor((Date.now() - dt.getTime()) / 60000));
  if (diffMinutes < 3) return "刚刚";
  if (diffMinutes < 60) return `${diffMinutes}分钟前`;
  const now = new Date();
  const sameDay = dt.getFullYear() === now.getFullYear() && dt.getMonth() === now.getMonth() && dt.getDate() === now.getDate();
  const hh = String(dt.getHours()).padStart(2, "0");
  const mm = String(dt.getMinutes()).padStart(2, "0");
  if (sameDay) return `今天 ${hh}:${mm}`;
  return `${dt.getMonth() + 1}/${dt.getDate()} ${hh}:${mm}`;
}

function privateDrawContainsAny(text: string, patterns: readonly string[]) {
  return patterns.some((pattern) => text.includes(pattern));
}

function privateDrawFilteredOptions(slotKey: string, options: readonly string[], selected: Record<string, string>) {
  const theme = String(selected.theme || "").trim();
  if (!PRIVATE_DRAW_DU_LEADS_THEMES.has(theme) || (slotKey !== "task" && slotKey !== "limit")) {
    return [...options];
  }
  if (slotKey === "task") {
    const filtered = options.filter((item) => !privateDrawContainsAny(item, PRIVATE_DRAW_XINYUE_CONTROL_TASK_PATTERNS));
    return filtered.length ? filtered : [...options];
  }
  const filtered = options.filter((item) => {
    if (privateDrawContainsAny(item, PRIVATE_DRAW_KEEP_LIMIT_PATTERNS)) return true;
    return !privateDrawContainsAny(item, PRIVATE_DRAW_XINYUE_CONTROL_LIMIT_PATTERNS);
  });
  return filtered.length ? filtered : [...options];
}

function privateDrawPick(options: readonly string[]) {
  return options[Math.floor(Math.random() * options.length)] || options[0] || "";
}

function createPrivateDraw(): PrivateDrawResult {
  const selected: Record<string, string> = {};
  return PRIVATE_DRAW_SLOTS.map((slot) => {
    const options = privateDrawFilteredOptions(slot.key, slot.options, selected);
    const value = privateDrawPick(options);
    selected[slot.key] = value;
    return { key: slot.key, label: slot.label, value };
  });
}

function createPrivateDrawEntryNumber() {
  return Math.floor(100 + Math.random() * 900);
}

function normalizePrivateDrawResult(value: unknown): PrivateDrawResult | null {
  if (!Array.isArray(value) || !value.length) return null;
  const rows = value
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const row = item as Record<string, unknown>;
      const key = String(row.key || row.label || "").trim();
      const label = String(row.label || row.key || "").trim();
      const text = String(row.value || "").trim();
      if (!key || !label || !text) return null;
      return { key, label, value: text };
    })
    .filter(Boolean) as PrivateDrawResult;
  return rows.length ? rows : null;
}

async function loadActivePrivateDraw() {
  const data = await apiJson<ActivePrivateDrawResponse>("/miniapp-api/private-draw/active");
  const active = data?.active_private_draw;
  const result = normalizePrivateDrawResult(active?.result);
  if (!result) return null;
  const entryNumber = Number(active?.entry_number) || createPrivateDrawEntryNumber();
  return { entryNumber, result };
}

function readLocalPrivateDraw(): LocalPrivateDrawTicket | null {
  try {
    const raw = window.localStorage.getItem(LOCAL_PRIVATE_DRAW_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<LocalPrivateDrawTicket>;
    const result = normalizePrivateDrawResult(parsed.result);
    if (!result) return null;
    return {
      entryNumber: Number(parsed.entryNumber) || createPrivateDrawEntryNumber(),
      result,
    };
  } catch {
    return null;
  }
}

function writeLocalPrivateDraw(ticket: LocalPrivateDrawTicket | null) {
  try {
    if (!ticket) {
      window.localStorage.removeItem(LOCAL_PRIVATE_DRAW_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(LOCAL_PRIVATE_DRAW_STORAGE_KEY, JSON.stringify(ticket));
  } catch {
    // UI-only persistence; backend active draw is saved separately on send.
  }
}

async function clearActivePrivateDraw() {
  const cleared = await apiJson<ActivePrivateDrawResponse>("/miniapp-api/private-draw/active", {
    method: "DELETE",
  });
  if (!cleared?.ok) {
    throw new Error(String(cleared?.error || "纸条清理失败"));
  }
}

async function sendPrivateDrawToDu(result: PrivateDrawResult, entryNumber: number) {
  const replyTarget = await getOrCreatePanelDeviceId();
  const sent = await apiJson<PrivateDrawSendResponse>("/miniapp-api/private-draw/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      reply_target: replyTarget,
      entry_number: entryNumber,
      result,
    }),
  });
  if (!sent?.ok) {
    throw new Error(String(sent?.error || "发送失败"));
  }
}

function PrivateDrawPage({ onClose }: { onClose: () => void }) {
  const initialTicket = useMemo(() => readLocalPrivateDraw(), []);
  const [result, setResult] = useState<PrivateDrawResult | null>(() => initialTicket?.result || null);
  const [entryNumber, setEntryNumber] = useState(() => initialTicket?.entryNumber || createPrivateDrawEntryNumber());
  const [loadingActive, setLoadingActive] = useState(true);
  const [savingDraw, setSavingDraw] = useState(false);
  const [settled, setSettled] = useState<"done" | "void" | null>(null);
  const [sendStatus, setSendStatus] = useState<PrivateDrawSendStatus>("idle");
  const [sendError, setSendError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const active = await loadActivePrivateDraw();
        if (!cancelled && active) {
          setEntryNumber(active.entryNumber);
          setResult(active.result);
          setSettled(null);
          setSendStatus("sent");
        }
      } catch (error: any) {
        if (!cancelled) setSendError(String(error?.message || error || "读取纸条失败"));
      } finally {
        if (!cancelled) setLoadingActive(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function drawOnce() {
    if (result || loadingActive || savingDraw) return;
    const nextEntryNumber = createPrivateDrawEntryNumber();
    const nextResult = createPrivateDraw();
    setSavingDraw(true);
    setSendError("");
    setEntryNumber(nextEntryNumber);
    setResult(nextResult);
    setSettled(null);
    writeLocalPrivateDraw({ entryNumber: nextEntryNumber, result: nextResult });
    setSavingDraw(false);
  }

  async function settle(next: "done" | "void") {
    if (!result) return;
    setSendError("");
    try {
      await clearActivePrivateDraw();
      writeLocalPrivateDraw(null);
      setSettled(next);
    } catch (error: any) {
      setSendError(String(error?.message || error || "纸条清理失败"));
    }
  }

  async function sendToDu() {
    if (!result || sendStatus === "sending" || sendStatus === "sent") return;
    setSendStatus("sending");
    setSendError("");
    try {
      await sendPrivateDrawToDu(result, entryNumber);
      setSendStatus("sent");
    } catch (error: any) {
      setSendStatus("error");
      setSendError(String(error?.message || error || "发送失败"));
    }
  }

  return (
    <div className={result ? "private-draw-page private-draw-page-result" : "private-draw-page"}>
      <header className="private-draw-header">
        <button className="private-draw-back" type="button" aria-label="返回小家" onClick={onClose}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
            <path d="M15 6L9 12L15 18" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <div>
          <span>私密抽屉</span>
          <h1>小纸条</h1>
        </div>
      </header>

      <main className="private-draw-stage">
        {result ? (
          <section className="private-draw-ticket" aria-label="今晚抽签结果">
            <span className="private-draw-ticket-mark" aria-hidden="true" />
            <h2>Entry #{entryNumber}</h2>
            {result.map((item) => (
              <div className="private-draw-row" key={item.key}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
            <footer className="private-draw-ticket-footer">
              <span>Tonight only.</span>
              <i aria-hidden="true" />
            </footer>
          </section>
        ) : (
          <div className="private-draw-drawer">
            <span className="private-draw-drawer-slit" aria-hidden="true" />
            <button
              className="private-draw-main-button"
              type="button"
              aria-label={loadingActive ? "读取中" : "抽一张"}
              disabled={loadingActive || savingDraw}
              onClick={() => void drawOnce()}
            >
              <span className="private-draw-main-label" aria-hidden="true">
                {loadingActive ? (
                  <>
                    <span>读</span>
                    <span>取</span>
                    <span>中</span>
                  </>
                ) : (
                  <>
                    <span>抽</span>
                    <span>一</span>
                    <span>张</span>
                  </>
                )}
              </span>
            </button>
            <span className="private-draw-paper-shadow" aria-hidden="true" />
            <p>Private &amp; Confidential</p>
            {sendError ? <span className="private-draw-send-error">{sendError}</span> : null}
          </div>
        )}

        {result ? (
          <div className="private-draw-actions">
            {settled ? <span className="private-draw-state">{settled === "done" ? "已完成" : "已作废"}</span> : null}
            {!settled ? (
              <>
                <button
                  className="private-draw-action-primary private-draw-action-send"
                  type="button"
                  disabled={sendStatus === "sending" || sendStatus === "sent"}
                  onClick={sendToDu}
                >
                  {sendStatus === "sending" ? "发送中" : sendStatus === "sent" ? "已发到聊天" : "发给渡"}
                </button>
                <button className="private-draw-action-muted" type="button" onClick={() => void settle("void")}>
                  作废
                </button>
                <button className="private-draw-action-muted" type="button" onClick={() => void settle("done")}>
                  完成
                </button>
              </>
            ) : null}
            <button className="private-draw-action-muted" type="button" onClick={onClose}>
              收起
            </button>
            {sendError ? <span className="private-draw-send-error">{sendError}</span> : null}
          </div>
        ) : null}
      </main>
    </div>
  );
}

export function PixelHomeTab() {
  const [mode, setMode] = useState<HomeMode>(() => resolveLocalMode());
  const [homeState, setHomeState] = useState<PixelHomeStateResp | null>(null);
  const [selectedSpotKey, setSelectedSpotKey] = useState<HotspotKey | null>(null);
  const [mySpot, setMySpot] = useState<HomeSpotKey>("sofa");
  const [myActivity, setMyActivity] = useState("休息");
  const [myDirty, setMyDirty] = useState(false);
  const [savingMyState, setSavingMyState] = useState(false);
  const [sendingAction, setSendingAction] = useState("");
  const [statusEditorOpen, setStatusEditorOpen] = useState(false);
  const [toyEditorOpen, setToyEditorOpen] = useState(false);
  const [savingToyState, setSavingToyState] = useState(false);
  const [toyDraft, setToyDraft] = useState<DuBodyState>({});
  const [toySaveError, setToySaveError] = useState("");
  const [privateDrawOpen, setPrivateDrawOpen] = useState(false);

  const modeMeta = HOME_MODES[mode];
  const spots = homeState?.spots?.length ? homeState.spots : DEFAULT_SPOTS;
  const duStatus = actorText(homeState?.du, "在书房写日记");
  const duMood = duMoodLabel(homeState?.du_vitals);
  const mySpotLabel = spots.find((spot) => spot.key === mySpot)?.label || "离家出走";
  const myStatus = myDirty ? statusText(mySpotLabel, myActivity) : actorText(homeState?.xinyue, "在客厅沙发休息");
  const selectedSpot = useMemo(() => HOTSPOTS.find((spot) => spot.key === selectedSpotKey) || null, [selectedSpotKey]);
  const feedItems = useMemo(() => {
    const dynamics = (homeState?.du_dynamics || []).slice(-5).reverse();
    if (dynamics.length) return dynamics;
    return [
      {
        at: homeState?.du?.updated_at,
        text: duStatus,
        spot_label: homeState?.du?.spot_label,
        activity: homeState?.du?.activity,
      },
    ];
  }, [duStatus, homeState?.du?.activity, homeState?.du?.spot_label, homeState?.du?.updated_at, homeState?.du_dynamics]);

  const refreshHomeState = useCallback(async () => {
    const data = await apiJson<PixelHomeStateResp>("/miniapp-api/pixel-home-state");
    if (isHomeMode(data?.mode)) setMode(data.mode);
    setHomeState(data || null);
    const nextSpot = data?.xinyue?.spot;
    if (!myDirty && isHomeSpot(nextSpot)) {
      setMySpot(nextSpot);
      setMyActivity(String(data?.xinyue?.activity || "休息").trim() || "休息");
    }
    setToyDraft(data?.du_body_state || {});
  }, [myDirty]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        await refreshHomeState();
      } catch {
        if (!cancelled) setMode((prev) => prev || resolveLocalMode());
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [refreshHomeState]);

  function selectSpot(spot: Hotspot) {
    setSelectedSpotKey(spot.key);
  }

  function clearSelectedSpot() {
    setSelectedSpotKey(null);
  }

  async function saveMyState() {
    if (savingMyState) return;
    setSavingMyState(true);
    try {
      const data = await apiJson<PixelHomeStateResp>("/miniapp-api/pixel-home-state/xinyue", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ spot: mySpot, activity: myActivity }),
      });
      if (data?.state) setHomeState(data.state);
      else await refreshHomeState();
      setMyDirty(false);
      setStatusEditorOpen(false);
    } finally {
      setSavingMyState(false);
    }
  }

  async function sendHomeEvent(action: { label: string }) {
    if (!selectedSpot || sendingAction) return;
    setSendingAction(action.label);
    try {
      const data = await apiJson<PixelHomeStateResp>("/miniapp-api/pixel-home-event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ spot: selectedSpot.key, action: action.label }),
      });
      if (data?.state) setHomeState(data.state);
      else await refreshHomeState();
    } finally {
      setSendingAction("");
    }
  }

  async function saveToyState() {
    if (savingToyState) return;
    setToySaveError("");
    setSavingToyState(true);
    try {
      const payload: Record<string, unknown> = {
        toy_types: bodyToyTypes(toyDraft),
        intensity: Number(toyDraft.intensity || 0) || 0,
      };
      BODY_CALIBRATION_FIELDS.forEach((field) => {
        const value = bodyCalibrationValue(toyDraft[field.key]);
        if (value !== null) payload[field.key] = value;
      });
      const data = await apiJson<PixelHomeStateResp>("/miniapp-api/pixel-home-state/du-body", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (data?.state) setHomeState(data.state);
      else await refreshHomeState();
      setToyEditorOpen(false);
    } catch (error: any) {
      setToySaveError(String(error?.message || error || "保存失败"));
    } finally {
      setSavingToyState(false);
    }
  }

  if (privateDrawOpen) {
    return <PrivateDrawPage onClose={() => setPrivateDrawOpen(false)} />;
  }

  return (
    <div className="pixel-home-ref" onClick={clearSelectedSpot}>
      <div className="pixel-home-ref-container">
        <button
          className="pixel-home-ref-heart"
          type="button"
          aria-label="打开私密抽签"
          onClick={(event) => {
            event.stopPropagation();
            clearSelectedSpot();
            setPrivateDrawOpen(true);
          }}
        >
          <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path
              d="M50 85C50 85 10 60 10 35C10 15 35 10 50 30C65 10 90 15 90 35C90 60 50 85 50 85Z"
              fill="currentColor"
            />
          </svg>
        </button>

        <section className="pixel-home-ref-house" aria-label="赛博小家位置">
          <div className="pixel-home-ref-house-wrapper">
            <div className="pixel-home-ref-house-stage" onClick={(event) => event.stopPropagation()}>
              <img src={modeMeta.image} alt={modeMeta.alt} decoding="async" draggable={false} />
              {HOTSPOTS.map((spot) => (
                <React.Fragment key={spot.key}>
                  {spot.parts.map((part, index) => {
                    const hotspotStyle: React.CSSProperties = {
                      left: `${part.rect.left}%`,
                      top: `${part.rect.top}%`,
                      width: `${part.rect.width}%`,
                      height: `${part.rect.height}%`,
                      clipPath: part.shape,
                      WebkitClipPath: part.shape,
                    };
                    return (
                      <button
                        key={`${spot.key}-${index}`}
                        type="button"
                        aria-label={index === 0 ? spot.label : undefined}
                        aria-hidden={index === 0 ? undefined : true}
                        tabIndex={index === 0 ? undefined : -1}
                        className="pixel-home-ref-hotspot"
                        style={hotspotStyle}
                        onClick={() => selectSpot(spot)}
                      />
                    );
                  })}
                </React.Fragment>
              ))}
              {selectedSpot ? (
                <span
                  className="pixel-home-ref-pulse active"
                  style={{ left: `${selectedSpot.marker.left}%`, top: `${selectedSpot.marker.top}%` }}
                  aria-hidden="true"
                />
              ) : null}
              {selectedSpot ? (
                <div
                  className={`pixel-home-ref-room-menu pixel-home-ref-room-menu-${selectedSpot.menu.align || "top"}`}
                  style={{ left: `${selectedSpot.menu.left}%`, top: `${selectedSpot.menu.top}%` }}
                  aria-label={`${selectedSpot.label}事件`}
                >
                  {selectedSpot.actions.map((action) => (
                    <button
                      key={action.label}
                      type="button"
                      className="pixel-home-ref-room-action"
                      disabled={!!sendingAction}
                      onClick={() => void sendHomeEvent(action)}
                    >
                      {sendingAction === action.label ? "发送中" : action.label}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        </section>

        <section className="pixel-home-ref-status">
          <div className="pixel-home-ref-status-lines">
            <div className="pixel-home-ref-status-row">
              <span>渡:</span>
              {duStatus}
            </div>
            <div className="pixel-home-ref-status-row">
              <span>我:</span>
              {myStatus}
            </div>
          </div>
          <button className="pixel-home-ref-add" type="button" aria-label="设置我的状态" onClick={() => setStatusEditorOpen(true)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M12 5V19M5 12H19" strokeLinecap="round" />
            </svg>
          </button>
        </section>

        <section className="pixel-home-ref-body-panel">
          <span className="pixel-home-ref-body-label">渡的身体</span>
          <button
            className="pixel-home-ref-body-inline"
            type="button"
            aria-label="选择小玩具"
            onClick={() => {
              setToyDraft(homeState?.du_body_state || {});
              setToySaveError("");
              setToyEditorOpen(true);
            }}
          >
            <BodyStatusBars state={homeState?.du_body_state} />
            <i aria-hidden="true">+</i>
          </button>
        </section>

        <section className="pixel-home-ref-feed">
          <div className="pixel-home-ref-feed-head">
            <span className="pixel-home-ref-section-label">渡的动态</span>
            <span className="pixel-home-ref-mood">当前心情：{duMood}</span>
          </div>
          <ul className="pixel-home-ref-feed-list">
            {feedItems.map((item, index) => {
              const text = String(item.text || "").trim() || statusText(String(item.spot_label || "离家出走"), String(item.activity || "待着"));
              return (
                <li className="pixel-home-ref-feed-item" key={`${item.at || "du"}-${index}`}>
                  <span className="pixel-home-ref-feed-time">{formatDynamicTime(item.at)}</span>
                  <span className="pixel-home-ref-feed-content">{text}</span>
                </li>
              );
            })}
          </ul>
        </section>
      </div>

      {statusEditorOpen ? (
        <div className="pixel-home-ref-modal active" onClick={() => setStatusEditorOpen(false)}>
          <div className="pixel-home-ref-sheet" onClick={(event) => event.stopPropagation()}>
            <div className="pixel-home-ref-input-group">
              <label>你想去哪里？</label>
              <div className="pixel-home-ref-location-grid">
                {spots.map((spot) => (
                  <button
                    key={spot.key}
                    type="button"
                    className={`pixel-home-ref-location-chip${mySpot === spot.key ? " selected" : ""}`}
                    onClick={() => {
                      setMySpot(spot.key);
                      setMyDirty(true);
                    }}
                  >
                    {spot.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="pixel-home-ref-input-group">
              <label>正在做什么？</label>
              <input
                type="text"
                className="pixel-home-ref-custom-input"
                placeholder="输入此刻的心情或动作..."
                value={myActivity}
                onChange={(event) => {
                  setMyActivity(event.target.value);
                  setMyDirty(true);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && myActivity.trim()) void saveMyState();
                }}
                autoFocus
              />
            </div>

            <button className="pixel-home-ref-save" type="button" disabled={savingMyState || !myActivity.trim()} onClick={() => void saveMyState()}>
              {savingMyState ? "保存中" : "记录此刻"}
            </button>
          </div>
        </div>
      ) : null}

      {toyEditorOpen ? (
        <div className="pixel-home-ref-modal active" onClick={() => setToyEditorOpen(false)}>
          <div className="pixel-home-ref-sheet pixel-home-ref-toy-sheet" onClick={(event) => event.stopPropagation()}>
            <div className="pixel-home-ref-input-group">
              <label>启用道具</label>
              <div className="pixel-home-ref-chip-grid">
                {BODY_TOY_OPTIONS.map((item) => (
                  <button
                    key={item}
                    type="button"
                    className={`pixel-home-ref-location-chip${
                      item === "无" ? (bodyToyTypes(toyDraft).length === 0 ? " selected" : "") : bodyToyTypes(toyDraft).includes(item) ? " selected" : ""
                    }`}
                    onClick={() => setToyDraft((prev) => toggleToyType(prev, item))}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>

            <div className="pixel-home-ref-input-group">
              <label>强度</label>
              <div className="pixel-home-ref-level-row">
                {[1, 2, 3, 4, 5].map((level) => (
                  <button
                    key={level}
                    type="button"
                    className={`pixel-home-ref-level${Number(toyDraft.intensity || 0) === level ? " selected" : ""}`}
                    onClick={() => setToyDraft((prev) => ({ ...prev, intensity: level }))}
                  >
                    {level}
                  </button>
                ))}
              </div>
            </div>

            <div className="pixel-home-ref-input-group">
              <label>校准值</label>
              <div className="pixel-home-ref-calibration-grid">
                {BODY_CALIBRATION_FIELDS.map((field) => (
                  <label className="pixel-home-ref-calibration-field" key={field.key}>
                    <span>{field.label}</span>
                    <input
                      type="number"
                      inputMode="numeric"
                      min="0"
                      max="100"
                      step="1"
                      placeholder="未设"
                      value={bodyCalibrationInputValue(toyDraft, field.key)}
                      onChange={(event) => setToyDraft((prev) => updateBodyCalibration(prev, field.key, event.currentTarget.value))}
                    />
                  </label>
                ))}
              </div>
            </div>

            <button className="pixel-home-ref-save" type="button" disabled={savingToyState} onClick={() => void saveToyState()}>
              {savingToyState ? "保存中" : "保存"}
            </button>
            {toySaveError ? <span className="private-draw-send-error">{toySaveError}</span> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
