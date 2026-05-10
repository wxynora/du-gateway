import React, { useState } from "react";
import { apiJson } from "./api";
import { Btn, Modal } from "./components";
import { useToast } from "./toast";

export type CyberTreeData = {
  ok: boolean;
  startDate: string;
  today: string;
  daysTogether: number;
  totalRounds: number;
  growth: number;
  stage: "seedling" | "young" | "big" | "lush";
  season: TreeSeason;
  weatherFx?: TreeWeatherFx;
  milestones: { reachedDays: number[]; reachedRounds: number[] };
  mood?: {
    date?: string;
    score?: number;
  };
};

type TreeSeason = "spring" | "summer" | "autumn" | "winter";
type TreeWeatherFx = "rainy" | "sunny" | "snowy";

export function TreeScreen({
  data,
  onRefresh,
}: {
  data: CyberTreeData | null;
  onRefresh: () => void;
}) {
  const toast = useToast();
  const d = data;
  const growth = Number(d?.growth || 0);
  const seasonLabel =
    d?.season === "spring" ? "春天" : d?.season === "summer" ? "夏天" : d?.season === "autumn" ? "秋天" : "冬天";
  const stageLabel =
    growth < 10 ? "种子/发芽" : growth < 30 ? "小树苗" : growth < 60 ? "小树" : growth < 100 ? "大树" : "满级大树";
  const [refreshing, setRefreshing] = useState(false);

  async function refreshMood() {
    setRefreshing(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/mood-meter/refresh", { method: "POST" });
      if (!j?.ok) throw new Error(j?.error || "刷新失败");
      onRefresh();
      toast("心情温度已刷新");
    } catch (e: any) {
      toast(`刷新失败：${e?.message || e}`);
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="rounded-[20px] border border-white/60 bg-[rgba(255,255,255,0.9)] px-4 py-4 shadow-[0_8px_20px_rgba(44,34,24,0.05)]">
        <div className="flex items-center gap-3">
          <GrowthTreeSVG
            growthValue={growth}
            season={d?.season || "spring"}
            weatherFx={d?.weatherFx || undefined}
          />
          <div className="text-xs text-cream-muted">当前：{seasonLabel} · {stageLabel}</div>
        </div>
      </div>
      <div className="rounded-[20px] border border-white/60 bg-[rgba(255,255,255,0.9)] px-4 py-4 shadow-[0_8px_20px_rgba(44,34,24,0.05)] text-[13px] leading-6 text-cream-text">
        <div>在一起第 {d?.daysTogether || 0} 天</div>
        <div>聊了 {d?.totalRounds || 0} 轮</div>
        <div>成长值：{growth.toFixed(2)}</div>
        <div>起始日期：{d?.startDate || "-"}</div>
      </div>
      <div className="rounded-[20px] border border-white/60 bg-[rgba(255,255,255,0.9)] px-4 py-4 shadow-[0_8px_20px_rgba(44,34,24,0.05)]">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[14px] text-cream-text">今日心情温度：{String(d?.mood?.score ?? "-")}/100</div>
          <Btn kind="blue" onClick={refreshMood} disabled={refreshing}>
            {refreshing ? "刷新中..." : "刷新"}
          </Btn>
        </div>
      </div>
    </div>
  );
}

function GrowthTreeSVG({
  growthValue,
  season,
  weatherFx,
}: {
  growthValue: number;
  season: TreeSeason;
  weatherFx?: TreeWeatherFx;
}) {
  const g = Number.isFinite(growthValue) ? Math.max(0, growthValue) : 0;
  const stage = g < 10 ? 0 : g < 30 ? 1 : g < 60 ? 2 : g < 100 ? 3 : 4;
  const fullness = Math.min(1, g / 100);
  const trunkW = 3 + stage * 1.4 + fullness * 1.2;
  const trunkH = 12 + stage * 7 + Math.min(10, g * 0.08);
  const trunkY = 86 - trunkH;
  const branchLevel = stage >= 2 ? (stage >= 4 ? 4 : stage === 3 ? 3 : 2) : 0;
  const leafCountBase = [2, 5, 12, 20, 26][stage];
  const leafCount = season === "winter" ? Math.max(0, Math.round(leafCountBase * 0.15)) : leafCountBase;
  const leafPalette =
    season === "spring"
      ? ["#9adf86", "#8cd97f", "#f6b4cb"]
      : season === "summer"
        ? ["#4cb165", "#3f9e56", "#2f8c4a"]
        : season === "autumn"
          ? ["#f2c35f", "#ef9a4b", "#d96a3b"]
          : ["#bfc9d3", "#d7e0e8", "#e8eef3"];
  const branchColor = season === "winter" ? "#6e5945" : "#76573d";
  const trunkColor = season === "winter" ? "#7a6045" : "#835f3f";
  const glow = stage >= 4;

  const leaves = Array.from({ length: leafCount }).map((_, i) => {
    const t = i / Math.max(1, leafCount - 1);
    const angle = -150 + t * 300;
    const radius = 10 + (stage + 1) * 5 + (i % 3) * 2;
    const cx = 50 + Math.cos((angle * Math.PI) / 180) * radius;
    const cy = trunkY - 5 + Math.sin((angle * Math.PI) / 180) * (radius * 0.72) - stage * 1.8;
    const rx = 2.4 + (i % 3) * 0.6 + stage * 0.2;
    const ry = 3.2 + (i % 2) * 0.7 + stage * 0.2;
    const color = leafPalette[i % leafPalette.length];
    return { cx, cy, rx, ry, color, idx: i };
  });

  const fx = weatherFx || (season === "winter" ? "snowy" : season === "summer" ? "sunny" : "rainy");
  const flowers = season === "spring" ? leaves.filter((_, i) => i % 5 === 0).slice(0, 8) : [];
  const snowCaps = fx === "snowy" ? leaves.filter((_, i) => i % 3 === 0).slice(0, 10) : [];
  const petals = season === "spring" && stage >= 2 ? [0, 1, 2].map((i) => ({ i, x: 40 + i * 10 })) : [];
  const rainDrops = fx === "rainy" ? Array.from({ length: 8 }).map((_, i) => ({ i, x: 18 + i * 9, y: 8 + (i % 3) * 4 })) : [];
  const sunGlints = fx === "sunny" ? Array.from({ length: 6 }).map((_, i) => ({ i, x: 18 + i * 11, y: 16 + (i % 2) * 5 })) : [];

  return (
    <svg viewBox="0 0 100 100" className="w-full max-w-[280px] h-auto" aria-label="growth-tree-svg">
      <defs>
        <linearGradient id="soilGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#b7865e" />
          <stop offset="100%" stopColor="#8f5f3c" />
        </linearGradient>
        <filter id="softGlow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="2.2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <style>{`
        .tree-leaf { transform-box: fill-box; transform-origin: center; animation: leaf-sway 3.4s ease-in-out infinite; }
        .tree-leaf:nth-child(2n) { animation-duration: 4.1s; }
        .tree-leaf:nth-child(3n) { animation-duration: 2.9s; }
        .petal-fall { animation: petal-fall 4.8s ease-in infinite; opacity: 0.75; }
        .grow-in { animation: grow-in .7s ease-out; transform-origin: center bottom; }
        @keyframes leaf-sway { 0%,100% { transform: rotate(-2deg) translateY(0px); } 50% { transform: rotate(2deg) translateY(-.4px); } }
        @keyframes petal-fall { 0% { transform: translateY(0px) translateX(0px); opacity: .75; } 100% { transform: translateY(20px) translateX(4px); opacity: 0; } }
        @keyframes rain-fall { 0% { transform: translateY(-2px); opacity: .7; } 100% { transform: translateY(9px); opacity: .2; } }
        @keyframes glint { 0%,100% { opacity: .18; } 50% { opacity: .42; } }
        @keyframes grow-in { from { transform: scale(.82); opacity: .45; } to { transform: scale(1); opacity: 1; } }
      `}</style>

      <ellipse cx="50" cy="90" rx="28" ry="7" fill="url(#soilGrad)" />

      {stage === 0 ? (
        <g className="grow-in">
          <path d="M50 88 C50 84, 50 81, 50 78" stroke={trunkColor} strokeWidth="1.6" fill="none" />
          <ellipse cx="47.5" cy="77.6" rx="2.2" ry="3.2" fill="#8dd97a" className="tree-leaf" />
          <ellipse cx="52.5" cy="77.8" rx="2.2" ry="3.2" fill="#8dd97a" className="tree-leaf" />
        </g>
      ) : null}

      {stage >= 1 ? (
        <g className="grow-in">
          <path
            d={`M50 ${88} C ${50 - trunkW * 0.3} ${80 - trunkH * 0.25}, ${50 + trunkW * 0.35} ${75 - trunkH * 0.55}, 50 ${trunkY}`}
            stroke={trunkColor}
            strokeWidth={trunkW}
            strokeLinecap="round"
            fill="none"
          />
          {branchLevel >= 1 ? <path d={`M50 ${trunkY + 11} C 42 ${trunkY + 6}, 39 ${trunkY}, 36 ${trunkY - 6}`} stroke={branchColor} strokeWidth="2.1" fill="none" strokeLinecap="round" /> : null}
          {branchLevel >= 1 ? <path d={`M50 ${trunkY + 10} C 58 ${trunkY + 5}, 61 ${trunkY}, 64 ${trunkY - 6}`} stroke={branchColor} strokeWidth="2.1" fill="none" strokeLinecap="round" /> : null}
          {branchLevel >= 2 ? <path d={`M50 ${trunkY + 4} C 43 ${trunkY - 1}, 41 ${trunkY - 5}, 38 ${trunkY - 10}`} stroke={branchColor} strokeWidth="1.8" fill="none" strokeLinecap="round" /> : null}
          {branchLevel >= 2 ? <path d={`M50 ${trunkY + 3} C 57 ${trunkY - 2}, 59 ${trunkY - 5}, 62 ${trunkY - 11}`} stroke={branchColor} strokeWidth="1.8" fill="none" strokeLinecap="round" /> : null}
          {branchLevel >= 3 ? <path d={`M50 ${trunkY - 2} C 47 ${trunkY - 7}, 46 ${trunkY - 11}, 45 ${trunkY - 15}`} stroke={branchColor} strokeWidth="1.6" fill="none" strokeLinecap="round" /> : null}
          {branchLevel >= 3 ? <path d={`M50 ${trunkY - 2} C 53 ${trunkY - 7}, 54 ${trunkY - 11}, 55 ${trunkY - 16}`} stroke={branchColor} strokeWidth="1.6" fill="none" strokeLinecap="round" /> : null}
        </g>
      ) : null}

      {leaves.map((l) => (
        <ellipse
          key={`leaf-${l.idx}`}
          cx={l.cx}
          cy={l.cy}
          rx={l.rx}
          ry={l.ry}
          fill={l.color}
          className="tree-leaf grow-in"
          style={{ animationDelay: `${(l.idx % 7) * 0.12}s` }}
        />
      ))}

      {flowers.map((f, i) => (
        <g key={`flower-${i}`} className="grow-in">
          <circle cx={f.cx} cy={f.cy} r="1.1" fill="#ffd7e8" />
          <circle cx={f.cx - 1} cy={f.cy} r="0.7" fill="#f5a8ca" />
          <circle cx={f.cx + 1} cy={f.cy} r="0.7" fill="#f5a8ca" />
          <circle cx={f.cx} cy={f.cy - 1} r="0.7" fill="#f5a8ca" />
          <circle cx={f.cx} cy={f.cy + 1} r="0.7" fill="#f5a8ca" />
        </g>
      ))}

      {snowCaps.map((s, i) => (
        <ellipse key={`snow-${i}`} cx={s.cx} cy={s.cy - 1} rx={s.rx * 0.9} ry="0.8" fill="#f2f7fb" opacity="0.95" />
      ))}

      {rainDrops.map((d) => (
        <line
          key={`rain-${d.i}`}
          x1={d.x}
          y1={d.y}
          x2={d.x - 1.5}
          y2={d.y + 5}
          stroke="#9ec7e8"
          strokeWidth="1.2"
          strokeLinecap="round"
          style={{ animation: "rain-fall 1.2s linear infinite", animationDelay: `${d.i * 0.18}s` }}
        />
      ))}

      {sunGlints.map((s) => (
        <circle
          key={`glint-${s.i}`}
          cx={s.x}
          cy={s.y}
          r="1.8"
          fill="#fff3bd"
          style={{ animation: "glint 2.4s ease-in-out infinite", animationDelay: `${s.i * 0.22}s` }}
        />
      ))}

      {petals.map((p) => (
        <circle key={`petal-${p.i}`} cx={p.x} cy={trunkY - 6} r="1.1" fill="#f5a8ca" className="petal-fall" style={{ animationDelay: `${p.i * 1.15}s` }} />
      ))}

      {glow ? (
        <g filter="url(#softGlow)">
          <circle cx="50" cy={trunkY - 12} r="16" fill="#ffdca8" opacity="0.28" />
        </g>
      ) : null}
    </svg>
  );
}

export function CyberTreeModal({
  data,
  onClose,
  onRefresh,
}: {
  data: CyberTreeData | null;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const d = data;
  const toast = useToast();
  const [refreshing, setRefreshing] = useState(false);
  const growth = Number(d?.growth || 0);
  const moodScore = Number(d?.mood?.score ?? 0);
  const moodFace =
    moodScore >= 85 ? "٩(ˊᗜˋ*)و" : moodScore >= 70 ? "(◕‿◕✿)" : moodScore >= 55 ? "(๑•ᴗ•๑)" : moodScore >= 40 ? "(｡•́︿•̀｡)" : "(╥﹏╥)";
  const stageLabel =
    growth < 10 ? "种子/发芽" : growth < 30 ? "小树苗" : growth < 60 ? "小树" : growth < 100 ? "大树" : "满级大树";
  const seasonLabel =
    d?.season === "spring" ? "春天" : d?.season === "summer" ? "夏天" : d?.season === "autumn" ? "秋天" : "冬天";

  async function refreshMood() {
    setRefreshing(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/mood-meter/refresh", { method: "POST" });
      if (!j?.ok) throw new Error(j?.error || "刷新失败");
      onRefresh();
      toast("心情温度已刷新");
    } catch (e: any) {
      toast(`刷新失败：${e?.message || e}`);
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <Modal title="小渡&小玥の树" onClose={onClose}>
      <div className="space-y-3 text-sm">
        <div className="rounded-xl3 bg-white border border-white/70 shadow-soft2 p-3">
          <div className="flex items-center gap-2">
            <GrowthTreeSVG
              growthValue={growth}
              season={d?.season || "spring"}
              weatherFx={d?.weatherFx || undefined}
            />
            <div className="text-xs text-cream-muted">SVG 动态小树（随成长值 + 季节变化）</div>
          </div>
          <div className="mt-1 text-sm">当前：{seasonLabel} · {stageLabel}</div>
          <div className="mt-1 text-xs text-cream-muted">成长值：{growth.toFixed(2)}</div>
        </div>
        <div className="rounded-xl3 bg-white border border-white/70 shadow-soft2 p-3 text-xs space-y-1">
          <div>在一起第 <span className="font-semibold">{d?.daysTogether || 1}</span> 天</div>
          <div>聊了 <span className="font-semibold">{d?.totalRounds || 0}</span> 轮</div>
          <div className="text-cream-muted">起始日期：{d?.startDate || "-"}</div>
        </div>
        <div className="rounded-xl3 bg-white border border-white/70 shadow-soft2 p-2.5 text-xs space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="inline-flex items-center rounded-2xl bg-neutral-900 px-3.5 py-1.5 text-[13px] font-semibold text-white shadow-soft2">
              {moodFace}
            </div>
            <div className="text-[15px] text-cream-text whitespace-nowrap">
              今日心情温度&nbsp;<span className="font-bold text-[20px]">{String(d?.mood?.score ?? "-")}</span>/100
            </div>
            <button
              className="h-9 w-9 shrink-0 rounded-full bg-white/70 backdrop-blur-lg border border-white/75 shadow-[0_2px_8px_rgba(40,34,26,0.14)] flex items-center justify-center text-[#5a544c] active:scale-[0.98] transition"
              onClick={refreshMood}
              disabled={refreshing}
              title="刷新温度"
            >
              <svg className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9">
                <path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v6h-6" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
