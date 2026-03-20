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

type PanelId = "logs" | "reasoning" | null;
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
  milestones: { reachedDays: number[]; reachedRounds: number[] };
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
  const [showTree, setShowTree] = useState(false);
  const [dailyWhisper, setDailyWhisper] = useState("");
  const [tree, setTree] = useState<CyberTreeData | null>(null);
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
    apiJson<CyberTreeData>("/miniapp-api/cyber-tree")
      .then((j) => {
        if (j?.ok) setTree(j);
      })
      .catch(() => {});
  }, []);

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

      <div className="px-4 pt-6 pb-28">
        <div className="grid grid-cols-2 gap-3">
          <FeatureTile title="日志" desc="查看/过滤/复制" color="bg-white/38" icon={<LineIcon name="logs" />} onClick={() => setPanel("logs")} />
          <FeatureTile title="思维链" desc="最近10条（降序）" color="bg-white/38" icon={<LineIcon name="reasoning" />} onClick={() => setPanel("reasoning")} />
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
      {showTree ? <CyberTreeModal data={tree} onClose={() => setShowTree(false)} /> : null}
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

function LineIcon({ name }: { name: "logs" | "reasoning" | "upstream" | "prompt" | "background" | "tree" }) {
  const cls = "h-4 w-4 text-cream-text";
  if (name === "logs") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 6h16M4 12h16M4 18h10" /></svg>;
  if (name === "reasoning") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 12h4l2-4 4 8 2-4h4" /></svg>;
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
  onOpenTree,
}: {
  open: boolean;
  onToggle: () => void;
  onOpenSchedule: () => void;
  onOpenBackground: () => void;
  onOpenAlarm: () => void;
  onOpenUpstream: () => void;
  onOpenTree: () => void;
}) {
  return (
    <div className="fixed inset-x-0 bottom-14 z-30 flex justify-center pointer-events-none">
      <div className="relative pointer-events-auto">
        {open ? (
          <>
            <div className="absolute left-1/2 top-1/2 h-64 w-64 -translate-x-1/2 -translate-y-[58%] rounded-full bg-white/30 backdrop-blur-2xl border border-white/45 shadow-soft pointer-events-none" />
            <button
              className="absolute left-1/2 top-1/2 h-12 w-12 -translate-x-[94px] -translate-y-[54px] rounded-full bg-white/60 backdrop-blur-2xl border border-white/55 shadow-soft2 flex items-center justify-center text-cream-text"
              onClick={onOpenBackground}
              title="背景设置"
            >
              <LineIcon name="background" />
            </button>
            <button
              className="absolute left-1/2 top-1/2 h-12 w-12 -translate-x-1/2 -translate-y-[126px] rounded-full bg-white/60 backdrop-blur-2xl border border-white/55 shadow-soft2 flex items-center justify-center text-cream-text active:scale-[0.99] transition"
              onClick={onOpenSchedule}
              title="日历与提醒"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M7 3v3M17 3v3M4 9h16M5 6h14a1 1 0 0 1 1 1v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a1 1 0 0 1 1-1z" />
              </svg>
            </button>
            <button
              className="absolute left-1/2 top-1/2 h-12 w-12 translate-x-[94px] -translate-y-[54px] rounded-full bg-white/60 backdrop-blur-2xl border border-white/55 shadow-soft2 flex items-center justify-center text-cream-text active:scale-[0.99] transition"
              onClick={onOpenAlarm}
              title="闹钟"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <circle cx="12" cy="13" r="7" />
                <path d="M12 13V9m0 4 3 2M7 4 4 7m13-3 3 3" />
              </svg>
            </button>
            <button
              className="absolute left-1/2 top-1/2 h-12 w-12 translate-x-[78px] translate-y-[28px] rounded-full bg-white/60 backdrop-blur-2xl border border-white/55 shadow-soft2 flex items-center justify-center text-cream-text active:scale-[0.99] transition"
              onClick={onOpenUpstream}
              title="上游切换"
            >
              <LineIcon name="upstream" />
            </button>
            <button
              className="absolute left-1/2 top-1/2 h-12 w-12 -translate-x-[78px] translate-y-[28px] rounded-full bg-white/60 backdrop-blur-2xl border border-white/55 shadow-soft2 flex items-center justify-center text-cream-text active:scale-[0.99] transition"
              onClick={onOpenTree}
              title="赛博种树"
            >
              <LineIcon name="tree" />
            </button>
          </>
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
      const fd = new FormData();
      fd.append("file", file);
      const r = await apiFetch("/miniapp-api/background-image", {
        method: "POST",
        body: fd,
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j?.ok) throw new Error(j?.error || `HTTP ${r.status}`);
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

function CyberTreeModal({ data, onClose }: { data: CyberTreeData | null; onClose: () => void }) {
  const d = data;
  const stageLabel =
    d?.stage === "seedling" ? "树苗" : d?.stage === "young" ? "小树" : d?.stage === "big" ? "大树" : "繁茂";
  const seasonLabel =
    d?.season === "spring" ? "春天" : d?.season === "summer" ? "夏天" : d?.season === "autumn" ? "秋天" : "冬天";
  const canopyColor =
    d?.season === "spring" ? "#7fcf8d" : d?.season === "summer" ? "#3fa35a" : d?.season === "autumn" ? "#c6924a" : "#86a7b9";
  const decoColor =
    d?.season === "spring" ? "#f3a9c8" : d?.season === "summer" ? "#6bcf7a" : d?.season === "autumn" ? "#d9b06c" : "#dbe7ef";
  return (
    <Modal title="赛博种树" onClose={onClose}>
      <div className="space-y-3 text-sm">
        <div className="rounded-xl3 bg-white/52 backdrop-blur-xl border border-white/55 shadow-soft2 p-3">
          <div className="flex items-center gap-2">
            <svg width="56" height="56" viewBox="0 0 56 56" fill="none">
              <rect x="24" y="30" width="8" height="20" rx="3" fill="#7b5a3a" />
              {d?.stage === "seedling" ? <circle cx="28" cy="26" r="10" fill={canopyColor} /> : null}
              {d?.stage === "young" ? <circle cx="28" cy="24" r="14" fill={canopyColor} /> : null}
              {d?.stage === "big" ? (
                <>
                  <circle cx="20" cy="24" r="10" fill={canopyColor} />
                  <circle cx="36" cy="24" r="10" fill={canopyColor} />
                  <circle cx="28" cy="20" r="12" fill={canopyColor} />
                </>
              ) : null}
              {d?.stage === "lush" ? (
                <>
                  <circle cx="18" cy="24" r="11" fill={canopyColor} />
                  <circle cx="38" cy="24" r="11" fill={canopyColor} />
                  <circle cx="28" cy="18" r="13" fill={canopyColor} />
                  <circle cx="28" cy="30" r="9" fill={canopyColor} />
                </>
              ) : null}
              <circle cx="18" cy="18" r="2" fill={decoColor} />
              <circle cx="38" cy="18" r="2" fill={decoColor} />
              <circle cx="28" cy="14" r="2" fill={decoColor} />
            </svg>
            <div className="text-xs text-cream-muted">成长树形（随阶段+季节变化）</div>
          </div>
          <div className="mt-1 text-sm">当前：{seasonLabel} · {stageLabel}</div>
          <div className="mt-1 text-xs text-cream-muted">成长值：{Number(d?.growth || 0).toFixed(2)}</div>
        </div>
        <div className="rounded-xl3 bg-white/45 backdrop-blur-xl border border-white/55 shadow-soft2 p-3 text-xs space-y-1">
          <div>在一起第 <span className="font-semibold">{d?.daysTogether || 1}</span> 天</div>
          <div>聊了 <span className="font-semibold">{d?.totalRounds || 0}</span> 轮</div>
          <div className="text-cream-muted">起始日期：{d?.startDate || "-"}</div>
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

