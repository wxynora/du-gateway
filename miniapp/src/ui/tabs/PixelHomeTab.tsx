import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "../api";
import homeDay from "../../assets/life-home-day.png";
import homeNightOff from "../../assets/life-home-night-off.png";
import homeNightOn from "../../assets/life-home-night-on.png";

type HomeMode = "day" | "nightOn" | "nightOff";
type HotspotKey = "bed" | "bath" | "study" | "sofa";
type HomeSpotKey = HotspotKey | "kitchen" | "home";

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
  parts: Array<{
    rect: { left: number; top: number; width: number; height: number };
    shape?: string;
  }>;
  actions: Array<{ label: string }>;
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
  { key: "home", label: "小家里" },
];

const HOTSPOTS: Hotspot[] = [
  {
    key: "bed",
    label: "卧室",
    marker: { left: 33.5, top: 38.5 },
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
    parts: [{ rect: { left: 66.5, top: 16, width: 27, height: 28 } }],
    actions: [{ label: "洗澡" }, { label: "色色" }],
  },
  {
    key: "study",
    label: "书房",
    marker: { left: 54, top: 25.5 },
    parts: [{ rect: { left: 45, top: 15, width: 18, height: 21 } }],
    actions: [{ label: "写日记" }, { label: "看书" }],
  },
  {
    key: "sofa",
    label: "客厅沙发",
    marker: { left: 40.5, top: 80.5 },
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
    actions: [{ label: "一起看电视" }],
  },
];

function isHomeMode(value: unknown): value is HomeMode {
  return value === "day" || value === "nightOn" || value === "nightOff";
}

function isHomeSpot(value: unknown): value is HomeSpotKey {
  return value === "bed" || value === "bath" || value === "study" || value === "sofa" || value === "kitchen" || value === "home";
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

export function PixelHomeTab() {
  const [mode, setMode] = useState<HomeMode>(() => resolveLocalMode());
  const [homeState, setHomeState] = useState<PixelHomeStateResp | null>(null);
  const [pulseSpot, setPulseSpot] = useState<HotspotKey | null>(null);
  const [selectedSpotKey, setSelectedSpotKey] = useState<HotspotKey | null>(null);
  const [mySpot, setMySpot] = useState<HomeSpotKey>("sofa");
  const [myActivity, setMyActivity] = useState("休息");
  const [myDirty, setMyDirty] = useState(false);
  const [savingMyState, setSavingMyState] = useState(false);
  const [sendingAction, setSendingAction] = useState("");
  const [statusEditorOpen, setStatusEditorOpen] = useState(false);
  const pulseTimerRef = useRef<number | null>(null);

  const modeMeta = HOME_MODES[mode];
  const spots = homeState?.spots?.length ? homeState.spots : DEFAULT_SPOTS;
  const duStatus = actorText(homeState?.du, "在书房写日记");
  const mySpotLabel = spots.find((spot) => spot.key === mySpot)?.label || "小家里";
  const myStatus = myDirty ? statusText(mySpotLabel, myActivity) : actorText(homeState?.xinyue, "在客厅沙发休息");
  const activePulse = useMemo(() => HOTSPOTS.find((spot) => spot.key === pulseSpot) || null, [pulseSpot]);
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

  useEffect(() => {
    return () => {
      if (pulseTimerRef.current) window.clearTimeout(pulseTimerRef.current);
    };
  }, []);

  function showPulse(spot: Hotspot) {
    setSelectedSpotKey(spot.key);
    setPulseSpot(spot.key);
    if (pulseTimerRef.current) window.clearTimeout(pulseTimerRef.current);
    pulseTimerRef.current = window.setTimeout(() => {
      setPulseSpot(null);
      pulseTimerRef.current = null;
    }, 3000);
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

  return (
    <div className="pixel-home-ref">
      <div className="pixel-home-ref-container">
        <div className="pixel-home-ref-heart" aria-hidden="true">
          <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path
              d="M50 85C50 85 10 60 10 35C10 15 35 10 50 30C65 10 90 15 90 35C90 60 50 85 50 85Z"
              stroke="#8b6c66"
              strokeWidth="4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>

        <section className="pixel-home-ref-house" aria-label="赛博小家位置">
          <div className="pixel-home-ref-house-wrapper">
            <div className="pixel-home-ref-house-stage">
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
                        onClick={() => showPulse(spot)}
                      />
                    );
                  })}
                </React.Fragment>
              ))}
              {activePulse ? (
                <span
                  className="pixel-home-ref-pulse active"
                  style={{ left: `${activePulse.marker.left}%`, top: `${activePulse.marker.top}%` }}
                  aria-hidden="true"
                />
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

        {selectedSpot ? (
          <section className="pixel-home-ref-actions" aria-label={`${selectedSpot.label}事件`}>
            <div className="pixel-home-ref-actions-room">{selectedSpot.label}</div>
            <div className="pixel-home-ref-action-list">
              {selectedSpot.actions.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  className="pixel-home-ref-action-chip"
                  disabled={!!sendingAction}
                  onClick={() => void sendHomeEvent(action)}
                >
                  {sendingAction === action.label ? "发送中" : action.label}
                </button>
              ))}
            </div>
          </section>
        ) : null}

        <section className="pixel-home-ref-feed">
          <span className="pixel-home-ref-section-label">渡的动态</span>
          <ul className="pixel-home-ref-feed-list">
            {feedItems.map((item, index) => {
              const text = String(item.text || "").trim() || statusText(String(item.spot_label || "小家里"), String(item.activity || "待着"));
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
