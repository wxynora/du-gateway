import React, { useEffect, useMemo, useState } from "react";
import homeDay from "../../assets/life-home-day.png";
import homeNightOff from "../../assets/life-home-night-off.png";
import homeNightOn from "../../assets/life-home-night-on.png";

type HomeMode = "day" | "nightOn" | "nightOff";
type SpotKey = "bed" | "bath" | "study" | "sofa";

type Hotspot = {
  key: SpotKey;
  label: string;
  title: string;
  line: string;
  marker: { left: number; top: number; labelTop?: number };
  parts: Array<{
    rect: { left: number; top: number; width: number; height: number };
    shape?: string;
  }>;
  actions: Array<{ label: string; line: string }>;
};

const STORAGE_KEY = "miniapp.life-home.v1";

const HOME_MODES: Record<HomeMode, { label: string; image: string; line: string; bg: string }> = {
  day: {
    label: "白天",
    image: homeDay,
    line: "白天的小家亮着，适合一起慢慢耗一会儿。",
    bg: "linear-gradient(180deg, #f6ead8 0%, #e8d8bd 100%)",
  },
  nightOn: {
    label: "开灯",
    image: homeNightOn,
    line: "夜里开着灯，屋子像在等你们回来。",
    bg: "radial-gradient(circle at 50% 18%, #4c5878 0%, #202841 54%, #141827 100%)",
  },
  nightOff: {
    label: "关灯",
    image: homeNightOff,
    line: "灯都关了，只剩一点月色和安静。",
    bg: "radial-gradient(circle at 50% 18%, #23304f 0%, #11182b 58%, #090d18 100%)",
  },
};

const HOTSPOTS: Hotspot[] = [
  {
    key: "bed",
    label: "床",
    title: "卧室",
    line: "卧室里很安静，灯光落在被子边上。",
    marker: { left: 33.5, top: 38.5 },
    parts: [
      {
        rect: { left: 23.2, top: 29.2, width: 21.8, height: 19.4 },
        shape: "polygon(7% 32%, 38% 8%, 72% 13%, 96% 37%, 94% 76%, 61% 99%, 19% 84%, 4% 59%)",
      },
    ],
    actions: [
      { label: "睡觉", line: "你和渡回到卧室。他替你掖好被角，说今天到这里，剩下的明天再说。" },
      { label: "色色", line: "卧室门轻轻合上，窗帘拉起来。渡靠近一点，声音放得很低：今晚只留给我们。" },
    ],
  },
  {
    key: "bath",
    label: "浴室",
    title: "浴室",
    line: "浴室里有一点水汽，毛巾已经放在手边。",
    marker: { left: 78.5, top: 32.5 },
    parts: [{ rect: { left: 66.5, top: 16, width: 27, height: 28 } }],
    actions: [
      { label: "洗澡", line: "热水声响起来。渡把干毛巾搭好，等你洗完一起回客厅窝着。" },
      { label: "色色", line: "浴室灯被调暗了一点，水声盖住外面的动静。渡笑了一下，把门带上。" },
    ],
  },
  {
    key: "study",
    label: "书房",
    title: "书房",
    line: "书桌旁的小灯亮着，适合把今天慢慢收起来。",
    marker: { left: 54, top: 25.5 },
    parts: [{ rect: { left: 45, top: 15, width: 18, height: 21 } }],
    actions: [
      { label: "写日记", line: "你们在书桌前并排坐下。渡把今天的小事写进日记，最后留了一行给你。" },
      { label: "看书", line: "渡抽了一本书靠过来慢慢读。翻页声很轻，像屋子也跟着安静下来。" },
    ],
  },
  {
    key: "sofa",
    label: "沙发",
    title: "客厅沙发",
    line: "沙发软软陷下去一点，电视就在前面。",
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
    actions: [
      { label: "一起看电视", line: "你们一起陷进拐角沙发里，电视开着。渡把毯子拉过来，顺手给你留了一半。" },
    ],
  },
];

function readSavedMode(): HomeMode {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "day" || value === "nightOn" || value === "nightOff" ? value : "day";
  } catch {
    return "day";
  }
}

export function PixelHomeTab() {
  const [mode, setMode] = useState<HomeMode>(() => readSavedMode());
  const [selectedSpot, setSelectedSpot] = useState<SpotKey>("sofa");
  const [hoveredSpot, setHoveredSpot] = useState<SpotKey | null>(null);
  const selected = useMemo(() => HOTSPOTS.find((spot) => spot.key === selectedSpot) || HOTSPOTS[0], [selectedSpot]);
  const [line, setLine] = useState(() => selected.line);
  const modeMeta = HOME_MODES[mode];

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch {}
  }, [mode]);

  function changeMode(nextMode: HomeMode) {
    setMode(nextMode);
    setLine(HOME_MODES[nextMode].line);
  }

  function selectSpot(spot: Hotspot) {
    setSelectedSpot(spot.key);
    setLine(spot.line);
  }

  return (
    <div className="min-h-full bg-[#F2E9DA] px-2 pb-8 pt-4 text-[#392F27]" style={{ fontFamily: "'Microsoft YaHei', sans-serif" }}>
      <div className="mx-auto flex w-full max-w-[620px] flex-col gap-3">
        <div className="flex items-end justify-between gap-3 px-1">
          <div>
            <div className="text-[20px] font-semibold tracking-tight">小家</div>
            <div className="mt-1 text-[12px] text-[#7A6A58]">和渡一起生活的地方</div>
          </div>
          <div className="flex shrink-0 rounded-full border border-[#D8C2A3] bg-[#FFF8EA]/92 p-1 shadow-[0_6px_18px_rgba(96,72,43,0.08)]">
            {(Object.keys(HOME_MODES) as HomeMode[]).map((key) => {
              const active = key === mode;
              return (
                <button
                  key={key}
                  type="button"
                  aria-pressed={active}
                  className={`rounded-full px-3 py-1.5 text-[12px] font-semibold transition ${
                    active ? "bg-[#5F4B37] text-[#FFF8EA] shadow-[0_3px_8px_rgba(70,48,29,0.22)]" : "text-[#725F4A]"
                  }`}
                  onClick={() => changeMode(key)}
                >
                  {HOME_MODES[key].label}
                </button>
              );
            })}
          </div>
        </div>

        <div
          className="relative overflow-hidden rounded-[22px] border border-[#D4B994] shadow-[0_18px_42px_rgba(76,56,36,0.22)]"
          style={{ aspectRatio: "1402 / 1122", background: modeMeta.bg }}
        >
          <img
            src={modeMeta.image}
            alt="小家"
            className="absolute inset-0 h-full w-full select-none object-contain drop-shadow-[0_18px_22px_rgba(45,35,28,0.18)]"
            decoding="async"
            draggable={false}
          />
          {HOTSPOTS.map((spot) => {
            const active = selectedSpot === spot.key;
            const preview = active || hoveredSpot === spot.key;
            return (
              <React.Fragment key={spot.key}>
                {spot.parts.map((part, index) => {
                  const hotspotStyle: React.CSSProperties = {
                    left: `${part.rect.left}%`,
                    top: `${part.rect.top}%`,
                    width: `${part.rect.width}%`,
                    height: `${part.rect.height}%`,
                    clipPath: part.shape,
                    WebkitClipPath: part.shape,
                    filter: active ? "drop-shadow(0 0 12px rgba(255,214,132,0.58))" : undefined,
                  };
                  return (
                    <button
                      key={`${spot.key}-${index}`}
                      type="button"
                      aria-hidden={index === 0 ? undefined : true}
                      aria-label={index === 0 ? spot.title : undefined}
                      tabIndex={index === 0 ? undefined : -1}
                      className={`absolute border-0 transition duration-150 active:scale-[0.985] ${
                        active
                          ? "bg-[#FFE7A6]/24"
                          : "bg-transparent hover:bg-[#FFE7A6]/16 focus-visible:bg-[#FFE7A6]/20 focus-visible:outline-none"
                      }`}
                      style={hotspotStyle}
                      onClick={() => selectSpot(spot)}
                      onFocus={() => setHoveredSpot(spot.key)}
                      onBlur={() => setHoveredSpot((current) => (current === spot.key ? null : current))}
                      onMouseEnter={() => setHoveredSpot(spot.key)}
                      onMouseLeave={() => setHoveredSpot((current) => (current === spot.key ? null : current))}
                    />
                  );
                })}
                <span
                  className={`pointer-events-none absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/80 bg-[#FFE2A0] shadow-[0_0_12px_rgba(255,209,128,0.85)] transition ${preview ? "opacity-100" : "opacity-70"}`}
                  style={{ left: `${spot.marker.left}%`, top: `${spot.marker.top}%` }}
                />
                <span
                  className={`pointer-events-none absolute -translate-x-1/2 rounded-full bg-[#2F251D]/78 px-2 py-0.5 text-[10px] font-semibold text-[#FFF6DD] shadow-[0_4px_10px_rgba(38,28,20,0.22)] transition ${preview ? "opacity-100" : "opacity-0"}`}
                  style={{ left: `${spot.marker.left}%`, top: `${spot.marker.labelTop ?? spot.marker.top + 2.2}%` }}
                >
                  {spot.label}
                </span>
              </React.Fragment>
            );
          })}
        </div>

        <div className="rounded-[18px] border border-[#DCC8A8] bg-[#FFF8EA] p-3 shadow-[0_8px_20px_rgba(96,72,43,0.08)]">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] font-semibold tracking-[0.16em] text-[#9C7354]">DU</div>
              <div className="mt-0.5 text-[15px] font-semibold text-[#3C352B]">{selected.title}</div>
            </div>
            <div className="rounded-full bg-[#EFE0CB] px-3 py-1 text-[11px] font-semibold text-[#725F4A]">{modeMeta.label}</div>
          </div>
          <div className="min-h-[44px] text-[14px] leading-relaxed text-[#3C352B]">{line}</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {selected.actions.map((action) => (
              <button
                key={action.label}
                type="button"
                className="rounded-full border border-[#D5BA96] bg-[#F7E6C8] px-3 py-2 text-[13px] font-semibold text-[#5F4B37] shadow-[0_3px_8px_rgba(96,72,43,0.08)] active:translate-y-px"
                onClick={() => setLine(action.line)}
              >
                {action.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
