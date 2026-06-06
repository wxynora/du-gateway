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
  spots?: Array<{ key: HomeSpotKey; label: string }>;
  state?: PixelHomeStateResp;
};

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
      "NTR幻想",
      "偷情play",
      "主人宠物play",
      "身份倒置",
      "反差诱惑",
      "秘密恋人",
      "支配臣服",
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
      "露出边缘",
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
      "避孕套",
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
      "小玥没说够了不准离开",
      "小玥没验收不准摘项圈",
      "想换动作必须先申请",
    ],
  },
] as const;

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

function createPrivateDraw(): PrivateDrawResult {
  return PRIVATE_DRAW_SLOTS.map((slot) => {
    const value = slot.options[Math.floor(Math.random() * slot.options.length)] || slot.options[0];
    return { key: slot.key, label: slot.label, value };
  });
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
  const [result, setResult] = useState<PrivateDrawResult | null>(null);
  const [settled, setSettled] = useState<"done" | "void" | null>(null);
  const [sendStatus, setSendStatus] = useState<PrivateDrawSendStatus>("idle");
  const [sendError, setSendError] = useState("");
  const entryNumber = useMemo(() => Math.floor(100 + Math.random() * 900), [result]);

  function drawOnce() {
    if (result) return;
    setResult(createPrivateDraw());
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
            <button className="private-draw-main-button" type="button" aria-label="抽一张" onClick={drawOnce}>
              <span className="private-draw-main-label" aria-hidden="true">
                <span>抽</span>
                <span>一</span>
                <span>张</span>
              </span>
            </button>
            <span className="private-draw-paper-shadow" aria-hidden="true" />
            <p>Private &amp; Confidential</p>
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
                <button className="private-draw-action-muted" type="button" onClick={() => setSettled("void")}>
                  作废
                </button>
                <button className="private-draw-action-muted" type="button" onClick={() => setSettled("done")}>
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
  const [privateDrawOpen, setPrivateDrawOpen] = useState(false);

  const modeMeta = HOME_MODES[mode];
  const spots = homeState?.spots?.length ? homeState.spots : DEFAULT_SPOTS;
  const duStatus = actorText(homeState?.du, "在书房写日记");
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

        <section className="pixel-home-ref-feed">
          <span className="pixel-home-ref-section-label">渡的动态</span>
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
    </div>
  );
}
