import React, { useEffect, useState } from "react";
import { applyTelegramThemeToHtmlClass, tgReady } from "./tg";
import { ToastProvider, useToast } from "./toast";
import { apiFetch, apiJson } from "./api";
import { Btn, Modal } from "./components";
import { LogsTab } from "./tabs/LogsTab";
import { SettingsUpstream } from "./tabs/SettingsUpstream";
import { ReasoningTab } from "./tabs/ReasoningTab";
import { ScheduleTab } from "./tabs/ScheduleTab";
import { AlarmTab } from "./tabs/AlarmTab";
import { MemoryDebugTab } from "./tabs/MemoryDebugTab";
import { DuDayTab } from "./tabs/DuDayTab";
import { DuNotebookTab } from "./tabs/DuNotebookTab";

type PanelId = "logs" | "reasoning" | "memory-debug" | "du-notebook" | null;
type BgPreset = "cream" | "grid" | "soft";
type BgConfig = { preset: BgPreset; useImage: boolean; imageVersion: number; dim: number; imageStamp: number };
type CyberTreeData = {
  ok: boolean;
  startDate: string;
  today: string;
  daysTogether: number;
  totalRounds: number;
  growth: number;
  stage: "seedling" | "young" | "big" | "lush";
  season: "spring" | "summer" | "autumn" | "winter";
  weatherFx?: "rainy" | "sunny" | "snowy";
  milestones: { reachedDays: number[]; reachedRounds: number[] };
  mood?: {
    date?: string;
    score?: number;
  };
  anniversary?: {
    startDate?: string;
    next?: { name?: string; date?: string; days_left?: number };
  };
};
type WeeklyReport = {
  week_id?: string;
  rounds?: number;
  keywords?: string[];
  done_count?: number;
  summary_text?: string;
  generated_at?: string;
};
const BG_STORAGE_KEY = "miniapp.bg.config.v1";

function Shell() {
  const toast = useToast();
  const [panel, setPanel] = useState<PanelId>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showCorePrompt, setShowCorePrompt] = useState(false);
  const [showBgEditor, setShowBgEditor] = useState(false);
  const [showHomeMenu, setShowHomeMenu] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  const [showAlarm, setShowAlarm] = useState(false);
  const [showDuDay, setShowDuDay] = useState(false);
  const [showTree, setShowTree] = useState(false);
  const [dailyWhisper, setDailyWhisper] = useState("");
  const [weeklyReport, setWeeklyReport] = useState<WeeklyReport | null>(null);
  const [weeklyRefreshing, setWeeklyRefreshing] = useState(false);
  const [tree, setTree] = useState<CyberTreeData | null>(null);
  const loadTree = () =>
    apiJson<CyberTreeData>("/miniapp-api/cyber-tree")
      .then((j) => {
        if (j?.ok) setTree(j);
      })
      .catch(() => {});
  const loadWeeklyReport = () =>
    apiJson<{ ok?: boolean; report?: WeeklyReport }>("/miniapp-api/weekly-report")
      .then((j) => {
        if (j?.ok && j?.report) setWeeklyReport(j.report);
      })
      .catch(() => {});
  const version = new URLSearchParams(window.location.search).get("v") || "";
  const [bg, setBg] = useState<BgConfig>({
    preset: "cream",
    useImage: false,
    imageVersion: 0,
    dim: 20,
    imageStamp: 0,
  });

  useEffect(() => {
    // 直接展开全屏，避免进入后还要手动上滑/多次点击
    tgReady(true);
    applyTelegramThemeToHtmlClass();
    try {
      const raw = localStorage.getItem(BG_STORAGE_KEY);
      if (raw) {
        const j = JSON.parse(raw);
        setBg({
          preset: (j?.preset || "cream") as BgPreset,
          useImage: !!j?.useImage,
          imageVersion: Number(j?.imageVersion || 0),
          dim: Number.isFinite(Number(j?.dim)) ? Math.max(0, Math.min(70, Number(j?.dim))) : 20,
          imageStamp: 0,
        });
      }
    } catch {}

    apiJson<{ ok?: boolean; config?: Partial<BgConfig> }>("/miniapp-api/background-config")
      .then((j) => {
        if (!j?.ok || !j?.config) return;
        setBg((prev: BgConfig) => ({
          preset: (j.config?.preset as BgPreset) || prev.preset,
          useImage: !!j.config?.useImage,
          // 避免接口晚到的旧配置覆盖刚上传的新版本号（会导致看起来“又回到旧图”）。
          imageVersion: Math.max(Number(prev.imageVersion || 0), Number(j.config?.imageVersion || 0)),
          dim: Number.isFinite(Number(j.config?.dim)) ? Math.max(0, Math.min(70, Number(j.config?.dim))) : prev.dim,
          imageStamp: prev.imageStamp || 0,
        }));
      })
      .catch(() => {});
    apiJson<{ ok?: boolean; text?: string }>("/miniapp-api/daily-whisper")
      .then((j) => {
        const text = (j?.text || "").toString().trim();
        if (text) setDailyWhisper(text);
      })
      .catch(() => {});
    loadWeeklyReport();
    loadTree();
  }, []);
  async function refreshWeeklyReport() {
    setWeeklyRefreshing(true);
    try {
      const j = await apiJson<{ ok?: boolean; report?: WeeklyReport; error?: string }>("/miniapp-api/weekly-report/refresh", { method: "POST" });
      if (!j?.ok) throw new Error(j?.error || "刷新失败");
      if (j.report) setWeeklyReport(j.report);
      toast("周报已刷新");
    } catch (e: any) {
      toast(`周报刷新失败：${e?.message || e}`);
    } finally {
      setWeeklyRefreshing(false);
    }
  }


  useEffect(() => {
    if (!showTree) return;
    loadTree();
    const timer = setInterval(() => loadTree(), 30000);
    return () => clearInterval(timer);
  }, [showTree]);

  useEffect(() => {
    try {
      localStorage.setItem(BG_STORAGE_KEY, JSON.stringify(bg));
    } catch {}
  }, [bg]);

  useEffect(() => {
    if (!tree) return;
    const dayMarks = tree.milestones?.reachedDays || [];
    const roundMarks = tree.milestones?.reachedRounds || [];
    for (const d of dayMarks) {
      const key = `tree.milestone.day.${d}`;
      if (!localStorage.getItem(key)) {
        localStorage.setItem(key, "1");
        toast(`🎉 在一起第 ${d} 天，种树里程碑达成！`);
      }
    }
    for (const r of roundMarks) {
      const key = `tree.milestone.round.${r}`;
      if (!localStorage.getItem(key)) {
        localStorage.setItem(key, "1");
        toast(`🎉 聊到第 ${r} 轮，种树里程碑达成！`);
      }
    }
  }, [tree, toast]);

  const rootStyle = buildBackgroundStyle(bg);

  return (
    <div className="min-h-dvh safe-bottom text-cream-text" style={rootStyle}>
      <div className="sticky top-0 z-20 bg-cream-bg/85 backdrop-blur">
        <div
          className="flex items-center justify-between px-4 pb-3"
          style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 16px)" }}
        >
          <div className="font-semibold tracking-tight rounded-xl2 px-3 py-1 bg-white/65 backdrop-blur-md border border-white/50 shadow-soft2">
            d&x home
          </div>
          {version ? <div className="text-[11px] text-cream-muted">v{version}</div> : null}
          <div className="h-10 w-10" />
        </div>
      </div>

      {dailyWhisper ? (
        <div className="px-4 pt-2">
          <div className="rounded-xl3 bg-white/52 backdrop-blur-xl border border-white/55 shadow-soft2 px-3 py-2 text-[12px] leading-relaxed text-cream-text">
            <span className="text-cream-muted mr-1">渡今天想说：</span>
            {dailyWhisper}
          </div>
        </div>
      ) : null}
      {weeklyReport ? (
        <div className="px-4 pt-2">
          <details className="rounded-xl3 bg-white/52 backdrop-blur-xl border border-white/55 shadow-soft2 px-3 py-2 text-[12px] leading-relaxed text-cream-text">
            <summary className="cursor-pointer select-none text-cream-text">
              本周小报告：聊了 {String(weeklyReport.rounds || 0)} 轮 · {Array.isArray(weeklyReport.keywords) ? weeklyReport.keywords.join(" / ") : "暂无关键词"}
            </summary>
            <div className="mt-2 space-y-1 text-xs">
              <div>周标识：{weeklyReport.week_id || "-"}</div>
              <div>关键词：{Array.isArray(weeklyReport.keywords) ? weeklyReport.keywords.join(" / ") : "-"}</div>
              <div className="text-cream-muted whitespace-pre-wrap">{weeklyReport.summary_text || "（暂无）"}</div>
              <div className="text-cream-muted">更新时间：{weeklyReport.generated_at || "-"}</div>
              <div className="pt-1">
                <Btn kind="dark" onClick={refreshWeeklyReport} disabled={weeklyRefreshing}>
                  {weeklyRefreshing ? "刷新中..." : "刷新周报"}
                </Btn>
              </div>
            </div>
          </details>
        </div>
      ) : null}

      <div className="px-4 pt-6 pb-28">
        <div className="grid grid-cols-2 gap-3">
          <FeatureTile title="日志" desc="查看/过滤/复制" color="bg-white/38" icon={<LineIcon name="logs" />} onClick={() => setPanel("logs")} />
          <FeatureTile title="思维链" desc="最近10条（降序）" color="bg-white/38" icon={<LineIcon name="reasoning" />} onClick={() => setPanel("reasoning")} />
          <FeatureTile title="记忆调试" desc="窗口总结 + 动态召回" color="bg-white/38" icon={<LineIcon name="memory" />} onClick={() => setPanel("memory-debug")} />
          <FeatureTile title="渡的记事本" desc="固定注入 · 条目管理" color="bg-white/38" icon={<LineIcon name="notebook" />} onClick={() => setPanel("du-notebook")} />
          <FeatureTile title="核心Prompt" desc="固定注入，可随时更新" color="bg-white/38" icon={<LineIcon name="prompt" />} onClick={() => setShowCorePrompt(true)} />
        </div>
      </div>

      {panel === "logs" ? (
        <Modal title="日志" onClose={() => setPanel(null)}>
          <LogsTab />
        </Modal>
      ) : null}
      {panel === "reasoning" ? (
        <Modal title="思维链" onClose={() => setPanel(null)}>
          <ReasoningTab />
        </Modal>
      ) : null}
      {panel === "memory-debug" ? (
        <Modal title="记忆调试" onClose={() => setPanel(null)}>
          <MemoryDebugTab />
        </Modal>
      ) : null}
      {panel === "du-notebook" ? (
        <Modal title="渡的记事本" onClose={() => setPanel(null)}>
          <DuNotebookTab />
        </Modal>
      ) : null}

      {showSettings ? <SettingsUpstream onClose={() => setShowSettings(false)} /> : null}
      {showCorePrompt ? <CorePromptEditor onClose={() => setShowCorePrompt(false)} /> : null}
      {showBgEditor ? <BackgroundEditor bg={bg} onChange={setBg} onClose={() => setShowBgEditor(false)} /> : null}
      {showSchedule ? (
        <Modal title="日历与提醒" onClose={() => setShowSchedule(false)}>
          <ScheduleTab />
        </Modal>
      ) : null}
      {showAlarm ? (
        <Modal title="闹钟" onClose={() => setShowAlarm(false)}>
          <AlarmTab />
        </Modal>
      ) : null}
      {showDuDay ? (
        <Modal title="渡的一天" onClose={() => setShowDuDay(false)}>
          <DuDayTab />
        </Modal>
      ) : null}
      {showTree ? <CyberTreeModal data={tree} onClose={() => setShowTree(false)} onRefresh={loadTree} /> : null}
      <HomeOrbMenu
        open={showHomeMenu}
        onToggle={() => setShowHomeMenu((v: boolean) => !v)}
        onOpenSchedule={() => {
          setShowHomeMenu(false);
          setShowSchedule(true);
        }}
        onOpenBackground={() => {
          setShowHomeMenu(false);
          setShowBgEditor(true);
        }}
        onOpenAlarm={() => {
          setShowHomeMenu(false);
          setShowAlarm(true);
        }}
        onOpenUpstream={() => {
          setShowHomeMenu(false);
          setShowSettings(true);
        }}
        onOpenDuDay={() => {
          setShowHomeMenu(false);
          setShowDuDay(true);
        }}
        onOpenTree={() => {
          setShowHomeMenu(false);
          setShowTree(true);
        }}
      />
    </div>
  );
}

function FeatureTile({
  title,
  desc,
  color,
  icon,
  onClick,
  disabled,
}: {
  title: string;
  desc: string;
  color: string;
  icon: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      className={
        "h-24 rounded-xl3 p-3 text-left shadow-soft backdrop-blur-xl border border-white/50 transition active:scale-[0.99] " +
        color +
        (disabled ? " opacity-60 cursor-not-allowed" : "")
      }
      onClick={() => {
        if (disabled) return;
        onClick();
      }}
      disabled={disabled}
    >
      <div className="flex items-center gap-2">
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-xl2 bg-white/65 border border-white/50 shadow-soft2">
          {icon}
        </span>
        <div className="text-sm font-semibold">{title}</div>
      </div>
      <div className="mt-1 text-[11px] text-cream-muted leading-tight">{desc}</div>
    </button>
  );
}

function LineIcon({ name }: { name: "logs" | "reasoning" | "upstream" | "prompt" | "background" | "tree" | "memory" | "notebook" }) {
  const cls = "h-4 w-4 text-cream-text";
  if (name === "logs") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 6h16M4 12h16M4 18h10" /></svg>;
  if (name === "reasoning") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 12h4l2-4 4 8 2-4h4" /></svg>;
  if (name === "memory") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 5h14v14H5zM8 9h8M8 13h8M8 17h5" /></svg>;
  if (name === "notebook") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M6 4h12v16H6zM9 8h6M9 12h6M9 16h4" /></svg>;
  if (name === "upstream") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h10M14 7l3-3m-3 3 3 3M20 17H10m0 0-3-3m3 3-3 3" /></svg>;
  if (name === "prompt") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 5h14v14H5zM8 9h8M8 13h8M8 17h5" /></svg>;
  if (name === "tree") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 21v-5M12 16c-3.8 0-6-2.2-6-5 0-2.2 1.4-4 3.4-4.7A4.8 4.8 0 0 1 19 8c1.8.8 3 2.5 3 4.5 0 3-2.4 3.5-5 3.5h-5z" /></svg>;
  return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 20h16M4 8l4 4 4-6 4 5 4-3v12H4z" /></svg>;
}

function HomeOrbMenu({
  open,
  onToggle,
  onOpenSchedule,
  onOpenBackground,
  onOpenAlarm,
  onOpenUpstream,
  onOpenDuDay,
  onOpenTree,
}: {
  open: boolean;
  onToggle: () => void;
  onOpenSchedule: () => void;
  onOpenBackground: () => void;
  onOpenAlarm: () => void;
  onOpenUpstream: () => void;
  onOpenDuDay: () => void;
  onOpenTree: () => void;
}) {
  return (
    <div className="fixed inset-x-0 bottom-14 z-30 flex justify-center pointer-events-none">
      <div className="relative pointer-events-auto">
        {open ? (
          <div className="absolute left-1/2 top-1/2 w-[272px] -translate-x-1/2 -translate-y-[122%] rounded-3xl bg-white/36 backdrop-blur-2xl border border-white/50 shadow-soft p-4">
            <div className="grid grid-cols-3 gap-3">
              <button
                className="h-14 rounded-2xl bg-white/60 border border-white/55 shadow-soft2 flex items-center justify-center text-cream-text active:scale-[0.99] transition"
                onClick={onOpenBackground}
                title="背景设置"
              >
                <LineIcon name="background" />
              </button>
              <button
                className="h-14 rounded-2xl bg-white/60 border border-white/55 shadow-soft2 flex items-center justify-center text-cream-text active:scale-[0.99] transition"
                onClick={onOpenSchedule}
                title="日历与提醒"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M7 3v3M17 3v3M4 9h16M5 6h14a1 1 0 0 1 1 1v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a1 1 0 0 1 1-1z" />
                </svg>
              </button>
              <button
                className="h-14 rounded-2xl bg-white/60 border border-white/55 shadow-soft2 flex items-center justify-center text-cream-text active:scale-[0.99] transition"
                onClick={onOpenAlarm}
                title="闹钟"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <circle cx="12" cy="13" r="7" />
                  <path d="M12 13V9m0 4 3 2M7 4 4 7m13-3 3 3" />
                </svg>
              </button>
              <button
                className="h-14 rounded-2xl bg-white/60 border border-white/55 shadow-soft2 flex items-center justify-center text-cream-text active:scale-[0.99] transition"
                onClick={onOpenDuDay}
                title="渡的一天"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M6 5h12M6 12h12M6 19h8" />
                </svg>
              </button>
              <button
                className="h-14 rounded-2xl bg-white/60 border border-white/55 shadow-soft2 flex items-center justify-center text-cream-text active:scale-[0.99] transition"
                onClick={onOpenTree}
                title="小渡&小玥の树"
              >
                <LineIcon name="tree" />
              </button>
              <button
                className="h-14 rounded-2xl bg-white/60 border border-white/55 shadow-soft2 flex items-center justify-center text-cream-text active:scale-[0.99] transition"
                onClick={onOpenUpstream}
                title="上游切换"
              >
                <LineIcon name="upstream" />
              </button>
              <button
                className="h-14 rounded-2xl bg-white/45 border border-white/45 shadow-soft2 flex items-center justify-center text-cream-muted active:scale-[0.99] transition"
                onClick={onToggle}
                title="收起"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M6 14l6-6 6 6" />
                </svg>
              </button>
            </div>
          </div>
        ) : null}
        <button
          className="h-16 w-16 rounded-full bg-white/62 backdrop-blur-2xl border border-white/55 shadow-soft flex items-center justify-center text-cream-text"
          onClick={onToggle}
          title="Home"
        >
          <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M3 10.5 12 3l9 7.5V21h-6v-6h-6v6H3z" />
          </svg>
        </button>
      </div>
    </div>
  );
}

export function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}

function buildBackgroundStyle(bg: BgConfig): React.CSSProperties {
  if (bg.useImage && bg.imageVersion > 0) {
    const alpha = Math.max(0, Math.min(70, Number(bg.dim || 0))) / 100;
    return {
      backgroundColor: "#eaedf1",
      backgroundImage: `linear-gradient(rgba(238,240,243,${alpha}), rgba(238,240,243,${alpha})), url("/miniapp-api/background-image/${bg.imageVersion}?s=${bg.imageStamp || 0}")`,
      backgroundSize: "cover",
      backgroundPosition: "center",
      backgroundRepeat: "no-repeat",
    };
  }
  if (bg.preset === "grid") {
    return {
      backgroundColor: "#e8ebef",
      backgroundImage:
        "linear-gradient(rgba(21,31,43,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(21,31,43,0.06) 1px, transparent 1px), radial-gradient(circle at 50% 40%, rgba(255,255,255,0.8) 0%, rgba(255,255,255,0.45) 45%, rgba(232,235,239,0) 72%)",
      backgroundSize: "30px 30px, 30px 30px, 100% 100%",
    };
  }
  if (bg.preset === "soft") {
    return {
      backgroundColor: "#eef0f3",
      backgroundImage:
        "radial-gradient(circle at 20% 20%, rgba(183,199,223,0.28), transparent 36%), radial-gradient(circle at 80% 18%, rgba(213,193,208,0.30), transparent 34%), radial-gradient(circle at 50% 80%, rgba(191,212,204,0.28), transparent 38%)",
    };
  }
  return { backgroundColor: "#EEF0F3" };
}

function BackgroundEditor({
  bg,
  onChange,
  onClose,
}: {
  bg: BgConfig;
  onChange: (v: BgConfig) => void;
  onClose: () => void;
}) {
  const toast = useToast();
  const [draft, setDraft] = useState<BgConfig>(bg);
  const [origin, setOrigin] = useState<BgConfig>(bg);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    setDraft(bg);
    setOrigin(bg);
  }, [bg]);

  function applyDraft(next: BgConfig) {
    setDraft(next);
    onChange(next);
  }

  async function save() {
    try {
      const j = await apiJson<{ ok?: boolean; config?: Partial<BgConfig> }>("/miniapp-api/background-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      const next: BgConfig = {
        preset: ((j?.config?.preset as BgPreset) || draft.preset) as BgPreset,
        useImage: !!(j?.config?.useImage ?? draft.useImage),
        imageVersion: Number(j?.config?.imageVersion ?? draft.imageVersion),
        dim: Number.isFinite(Number(j?.config?.dim)) ? Math.max(0, Math.min(70, Number(j?.config?.dim))) : draft.dim,
        imageStamp: draft.imageStamp || 0,
      };
      onChange(next);
      toast("背景已保存");
      onClose();
    } catch (e: any) {
      toast(`保存失败：${e?.message || e}`);
    }
  }

  async function uploadFromAlbum(file: File | null) {
    if (!file) return;
    setUploading(true);
    try {
      const toDataUrl = (blob: Blob) =>
        new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result || ""));
          reader.onerror = () => reject(new Error("读取图片失败"));
          reader.readAsDataURL(blob);
        });
      const loadImage = (src: string) =>
        new Promise<HTMLImageElement>((resolve, reject) => {
          const img = new Image();
          img.onload = () => resolve(img);
          img.onerror = () => reject(new Error("图片解码失败"));
          img.src = src;
        });
      const canvasToBlob = (canvas: HTMLCanvasElement, quality: number) =>
        new Promise<Blob>((resolve, reject) => {
          canvas.toBlob(
            (blob) => {
              if (blob) resolve(blob);
              else reject(new Error("图片编码失败"));
            },
            "image/jpeg",
            quality
          );
        });

      // 上传前压缩：避免运营商/反向代理 413（体积过大）并降低上传失败概率
      const maxUploadBytes = 1500 * 1024; // 约 1.5MB
      const maxSide = 1920;
      let uploadBlob: Blob = file;
      if (file.size > maxUploadBytes || file.type !== "image/jpeg") {
        const src = await toDataUrl(file);
        const img = await loadImage(src);
        const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
        const w = Math.max(1, Math.round(img.width * scale));
        const h = Math.max(1, Math.round(img.height * scale));
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("浏览器不支持图片处理");
        ctx.drawImage(img, 0, 0, w, h);
        let q = 0.88;
        let out = await canvasToBlob(canvas, q);
        while (out.size > maxUploadBytes && q > 0.5) {
          q -= 0.08;
          out = await canvasToBlob(canvas, q);
        }
        uploadBlob = out;
      }

      const fd = new FormData();
      fd.append("file", uploadBlob, "miniapp-bg.jpg");
      const r = await apiFetch("/miniapp-api/background-image", {
        method: "POST",
        body: fd,
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j?.ok) {
        if (r.status === 413) throw new Error("图片体积仍然过大（413），请换更小图片");
        if (r.status === 403) throw new Error("鉴权失效（403），关闭重进 miniapp 后再试");
        throw new Error(j?.error || `HTTP ${r.status}`);
      }
      const version = Number(j?.imageVersion || Date.now());
      setDraft((v: BgConfig) => {
        const next = { ...v, useImage: true, imageVersion: version, imageStamp: Date.now() };
        onChange(next);
        return next;
      });
      toast("已上传背景图");
    } catch (e: any) {
      toast(`上传失败：${e?.message || e}`);
    } finally {
      setUploading(false);
    }
  }

  return (
    <Modal title="背景设置" onClose={onClose}>
      <div className="space-y-3 text-sm">
        <div className="text-xs text-cream-muted">可选预设风格，或从手机相册上传背景图（跨设备同步）。</div>
        <div className="grid grid-cols-3 gap-2">
          <Btn kind={draft.preset === "cream" ? "green" : "default"} onClick={() => applyDraft({ ...draft, preset: "cream", useImage: false })}>米白</Btn>
          <Btn kind={draft.preset === "grid" ? "green" : "default"} onClick={() => applyDraft({ ...draft, preset: "grid", useImage: false })}>网格灰</Btn>
          <Btn kind={draft.preset === "soft" ? "green" : "default"} onClick={() => applyDraft({ ...draft, preset: "soft", useImage: false })}>柔和彩</Btn>
        </div>
        <div className="rounded-xl2 bg-white/42 backdrop-blur-xl border border-white/50 p-3 shadow-soft2 space-y-2">
          <label className="text-xs text-cream-muted">从相册上传图片（jpg/png/webp/gif，最大 8MB）</label>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            className="w-full rounded-xl2 bg-white/68 border border-white/50 px-3 py-2 text-sm shadow-soft2"
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => uploadFromAlbum((e.target.files && e.target.files[0]) || null)}
            disabled={uploading}
          />
          <div className="flex items-center gap-2">
            <Btn
              kind={draft.useImage ? "green" : "default"}
              onClick={() =>
                applyDraft({
                  ...draft,
                  useImage: !draft.useImage,
                  imageStamp: !draft.useImage ? Date.now() : draft.imageStamp,
                })
              }
            >
              {draft.useImage ? "已启用图片" : "启用图片"}
            </Btn>
            {uploading ? <span className="text-xs text-cream-muted">上传中...</span> : null}
            <span className="text-xs text-cream-muted">遮罩 {draft.dim}%</span>
          </div>
          <input
            type="range"
            min={0}
            max={70}
            value={draft.dim}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => applyDraft({ ...draft, dim: Number(e.target.value || 20) })}
            className="w-full"
          />
        </div>
        <div className="flex items-center gap-2">
          <Btn
            kind="blue"
            onClick={() => {
              onChange(origin);
              onClose();
            }}
          >
            取消
          </Btn>
          <Btn kind="green" onClick={save} disabled={uploading}>保存</Btn>
        </div>
      </div>
    </Modal>
  );
}

function GrowthTreeSVG({
  growthValue,
  season,
  weatherFx,
}: {
  growthValue: number;
  season: "spring" | "summer" | "autumn" | "winter";
  weatherFx?: "rainy" | "sunny" | "snowy";
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

function CyberTreeModal({
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
    moodScore >= 85 ? "(*^▽^*)" : moodScore >= 70 ? "(^_−)☆" : moodScore >= 55 ? "(•ᴗ•)" : moodScore >= 40 ? "(´･ω･`)" : "(T_T)";
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

  async function editAnniversary() {
    const current = String(d?.anniversary?.startDate || "").slice(0, 10);
    const next = window.prompt("输入纪念日起始日（YYYY-MM-DD）", current);
    if (next === null) return;
    const val = (next || "").trim();
    if (!val) return;
    setRefreshing(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/anniversary", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ startDate: val }),
      });
      if (!j?.ok) throw new Error(j?.error || "保存失败");
      onRefresh();
      toast("纪念日已更新");
    } catch (e: any) {
      toast(`保存失败：${e?.message || e}`);
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
              season={(d?.season || "spring") as "spring" | "summer" | "autumn" | "winter"}
              weatherFx={(d?.weatherFx || undefined) as "rainy" | "sunny" | "snowy" | undefined}
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
        <div className="rounded-xl3 bg-white border border-white/70 shadow-soft2 p-3 text-xs space-y-2">
          <div className="flex items-center justify-between gap-3">
            <div className="relative h-20 w-20 shrink-0">
              <div className="h-20 w-20 rounded-full bg-white/72 backdrop-blur-lg border border-white/75 shadow-[0_2px_8px_rgba(40,34,26,0.14)] flex items-center justify-center text-[17px] font-black text-[#18140f]">
                {moodFace}
              </div>
              <span className="absolute -bottom-1 left-3 h-4 w-4 rounded-full bg-white/70 border border-white/75 shadow-[0_1px_3px_rgba(40,34,26,0.12)]" />
              <span className="absolute -bottom-3 left-1 h-2.5 w-2.5 rounded-full bg-white/68 border border-white/75 shadow-[0_1px_2px_rgba(40,34,26,0.10)]" />
            </div>
            <button
              className="h-11 w-11 shrink-0 rounded-full bg-white/70 backdrop-blur-lg border border-white/75 shadow-[0_2px_8px_rgba(40,34,26,0.14)] flex items-center justify-center text-[#5a544c] active:scale-[0.98] transition"
              onClick={refreshMood}
              disabled={refreshing}
              title="刷新温度"
            >
              <svg className={`h-5 w-5 ${refreshing ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9">
                <path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v6h-6" />
              </svg>
            </button>
          </div>
          <div className="text-[15px]">
            今日心情温度：<span className="font-bold text-[18px]">{String(d?.mood?.score ?? "-")}</span>/100
          </div>
        </div>
        <div className="rounded-xl3 bg-white border border-white/70 shadow-soft2 p-3 text-xs space-y-1">
          <div className="inline-flex items-center rounded-2xl bg-neutral-900 px-3.5 py-1.5 text-[11px] font-medium text-white shadow-soft2">纪念日倒计时</div>
          <div className="flex items-center justify-between gap-3">
            <div className="space-y-1">
              <div>下一个：<span className="font-semibold">{d?.anniversary?.next?.date || "-"}</span></div>
              <div>D-{String(d?.anniversary?.next?.days_left ?? "-")} · {d?.anniversary?.next?.name || "纪念日"}</div>
            </div>
            <div className="relative h-32 w-32 shrink-0">
              <div className="absolute inset-0 translate-x-1.5 translate-y-1.5 rotate-[-4deg] rounded-md bg-[#f0ece8] border border-[#d9d2cb]" />
              <div className="absolute inset-0 translate-x-[-1px] translate-y-[2px] rotate-[3deg] rounded-md bg-[#f7f4f1] border border-[#ddd6cf]" />
              <div className="absolute inset-0 rounded-md bg-[#fbf8f5] border border-[#d7d0c8] shadow-[0_2px_8px_rgba(40,34,26,0.12)] p-3">
                <div className="text-[12px] text-[#8a837b] leading-tight">距离{d?.anniversary?.next?.name || "纪念日"}还有</div>
                <div className="mt-2 text-[30px] font-bold leading-none text-[#1f1a14]">{String(d?.anniversary?.next?.days_left ?? "-")}天</div>
              </div>
              <div className="absolute -top-2 left-[56px] h-5 w-[10px] rounded-full border-2 border-[#8a90a9] bg-transparent" />
            </div>
          </div>
          <div className="pt-1">
            <Btn kind="dark" onClick={editAnniversary} disabled={refreshing}>编辑纪念日</Btn>
          </div>
        </div>
      </div>
    </Modal>
  );
}

function CorePromptEditor({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [source, setSource] = useState<string>("");

  async function load() {
    setLoading(true);
    try {
      const j = await apiJson<{ ok?: boolean; content?: string; source?: string; error?: string }>("/miniapp-api/core-prompt");
      if (!j?.ok) throw new Error(j?.error || "加载失败");
      setText((j.content || "").toString());
      setSource((j.source || "").toString());
    } catch (e: any) {
      toast(`加载失败：${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    const content = (text || "").trim();
    if (!content) {
      toast("内容不能为空");
      return;
    }
    const ok = window.confirm("确认保存核心 Prompt 吗？保存后会立即覆盖线上注入内容。");
    if (!ok) return;
    setSaving(true);
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/core-prompt", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!j?.ok) throw new Error(j?.error || "保存失败");
      toast("已保存，下一条请求生效");
      setSource("r2");
    } catch (e: any) {
      toast(`保存失败：${e?.message || e}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title="核心 Prompt（3.16）" onClose={onClose}>
      <div className="space-y-3">
        <div className="text-xs text-cream-muted">
          当前来源：{source || "unknown"}。保存后会固定注入到所有对话请求。
        </div>
        <textarea
          className="w-full min-h-[40vh] rounded-xl2 bg-cream-card shadow-soft2 p-3 text-sm leading-relaxed"
          value={text}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setText(e.target.value)}
          placeholder={loading ? "加载中..." : "在这里编辑核心 Prompt"}
        />
        <div className="flex items-center gap-2">
          <Btn kind="dark" onClick={load} disabled={loading || saving}>刷新</Btn>
          <Btn kind="dark" onClick={save} disabled={loading || saving}>保存</Btn>
        </div>
      </div>
    </Modal>
  );
}

