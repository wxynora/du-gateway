import React, { useEffect, useState } from "react";
import { applyTelegramThemeToHtmlClass, tgReady } from "./tg";
import { ToastProvider, useToast } from "./toast";
import { apiJson } from "./api";
import { Btn, Modal } from "./components";
import { LogsTab } from "./tabs/LogsTab";
import { SettingsUpstream } from "./tabs/SettingsUpstream";
import { ReasoningTab } from "./tabs/ReasoningTab";

type PanelId = "logs" | "reasoning" | null;
type BgPreset = "cream" | "grid" | "soft";
type BgConfig = { preset: BgPreset; useImage: boolean; imageUrl: string; dim: number };
const BG_STORAGE_KEY = "miniapp.bg.config.v1";

function Shell() {
  const [panel, setPanel] = useState<PanelId>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showCorePrompt, setShowCorePrompt] = useState(false);
  const [showBgEditor, setShowBgEditor] = useState(false);
  const version = new URLSearchParams(window.location.search).get("v") || "";
  const [bg, setBg] = useState<BgConfig>({
    preset: "cream",
    useImage: false,
    imageUrl: "",
    dim: 20,
  });

  useEffect(() => {
    // 默认不 expand：让 Telegram WebView 以“半屏”形式打开，更像面板弹出入口
    tgReady(false);
    applyTelegramThemeToHtmlClass();
    try {
      const raw = localStorage.getItem(BG_STORAGE_KEY);
      if (raw) {
        const j = JSON.parse(raw);
        setBg({
          preset: (j?.preset || "cream") as BgPreset,
          useImage: !!j?.useImage,
          imageUrl: String(j?.imageUrl || ""),
          dim: Number.isFinite(Number(j?.dim)) ? Math.max(0, Math.min(70, Number(j?.dim))) : 20,
        });
      }
    } catch {}
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(BG_STORAGE_KEY, JSON.stringify(bg));
    } catch {}
  }, [bg]);

  const rootStyle = buildBackgroundStyle(bg);

  return (
    <div className="min-h-dvh safe-top safe-bottom text-cream-text" style={rootStyle}>
      <div className="sticky top-0 z-20 bg-cream-bg/85 backdrop-blur">
        <div className="flex items-center justify-between px-4 pb-3 pt-4">
          <div className="font-semibold tracking-tight rounded-xl2 px-3 py-1 bg-cream-green/80 shadow-soft2">
            d&x home
          </div>
          {version ? <div className="text-[11px] text-cream-muted">v{version}</div> : null}
          <div className="flex items-center gap-2">
            <Btn kind="pink" onClick={() => setShowSettings(true)}>上游</Btn>
          </div>
        </div>
      </div>

      <div className="px-4 py-4 pb-6">
        <div className="grid grid-cols-2 gap-3">
          <FeatureTile title="日志" desc="查看/过滤/复制" color="bg-cream-blue/24" onClick={() => setPanel("logs")} />
          <FeatureTile title="思维链" desc="窗口轮次与推理" color="bg-cream-pink/28" onClick={() => setPanel("reasoning")} />
          <FeatureTile title="上游切换" desc="全局 active 切换" color="bg-cream-green/30" onClick={() => setShowSettings(true)} />
          <FeatureTile title="核心Prompt" desc="固定注入，可随时更新" color="bg-white/24" onClick={() => setShowCorePrompt(true)} />
          <FeatureTile title="背景设置" desc="可换风格/自定义图" color="bg-cream-blue/20" onClick={() => setShowBgEditor(true)} />
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
    </div>
  );
}

function FeatureTile({
  title,
  desc,
  color,
  onClick,
  disabled,
}: {
  title: string;
  desc: string;
  color: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      className={
        "h-24 rounded-xl3 p-3 text-left shadow-soft backdrop-blur-md border border-white/35 transition active:scale-[0.99] " +
        color +
        (disabled ? " opacity-60 cursor-not-allowed" : "")
      }
      onClick={() => {
        if (disabled) return;
        onClick();
      }}
      disabled={disabled}
    >
      <div className="text-sm font-semibold">{title}</div>
      <div className="mt-1 text-[11px] text-cream-muted leading-tight">{desc}</div>
    </button>
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
  if (bg.useImage && (bg.imageUrl || "").trim()) {
    const alpha = Math.max(0, Math.min(70, Number(bg.dim || 0))) / 100;
    return {
      backgroundColor: "#f2eee6",
      backgroundImage: `linear-gradient(rgba(255,251,243,${alpha}), rgba(255,251,243,${alpha})), url("${bg.imageUrl}")`,
      backgroundSize: "cover",
      backgroundPosition: "center",
      backgroundRepeat: "no-repeat",
    };
  }
  if (bg.preset === "grid") {
    return {
      backgroundColor: "#ececec",
      backgroundImage:
        "linear-gradient(rgba(0,0,0,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,0.04) 1px, transparent 1px), radial-gradient(circle at 50% 40%, rgba(255,255,255,0.75) 0%, rgba(255,255,255,0.35) 46%, rgba(236,236,236,0) 70%)",
      backgroundSize: "30px 30px, 30px 30px, 100% 100%",
    };
  }
  if (bg.preset === "soft") {
    return {
      backgroundColor: "#f3f0e8",
      backgroundImage:
        "radial-gradient(circle at 20% 20%, rgba(149,194,228,0.28), transparent 36%), radial-gradient(circle at 80% 18%, rgba(239,175,183,0.30), transparent 34%), radial-gradient(circle at 50% 80%, rgba(169,216,175,0.28), transparent 38%)",
    };
  }
  return { backgroundColor: "#FFFBF3" };
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

  useEffect(() => {
    setDraft(bg);
  }, [bg]);

  function save() {
    onChange(draft);
    toast("背景已保存");
    onClose();
  }

  return (
    <Modal title="背景设置" onClose={onClose}>
      <div className="space-y-3 text-sm">
        <div className="text-xs text-cream-muted">可选预设风格，或填图片 URL 自定义背景。</div>
        <div className="grid grid-cols-3 gap-2">
          <Btn kind={draft.preset === "cream" ? "green" : "default"} onClick={() => setDraft({ ...draft, preset: "cream", useImage: false })}>米白</Btn>
          <Btn kind={draft.preset === "grid" ? "green" : "default"} onClick={() => setDraft({ ...draft, preset: "grid", useImage: false })}>网格灰</Btn>
          <Btn kind={draft.preset === "soft" ? "green" : "default"} onClick={() => setDraft({ ...draft, preset: "soft", useImage: false })}>柔和彩</Btn>
        </div>
        <div className="rounded-xl2 bg-cream-card p-3 shadow-soft2 space-y-2">
          <label className="text-xs text-cream-muted">自定义图片 URL（https）</label>
          <input
            className="w-full rounded-xl2 bg-white/70 px-3 py-2 text-sm shadow-soft2"
            placeholder="https://..."
            value={draft.imageUrl}
            onChange={(e) => setDraft({ ...draft, imageUrl: e.target.value })}
          />
          <div className="flex items-center gap-2">
            <Btn kind={draft.useImage ? "green" : "default"} onClick={() => setDraft({ ...draft, useImage: !draft.useImage })}>
              {draft.useImage ? "已启用图片" : "启用图片"}
            </Btn>
            <span className="text-xs text-cream-muted">遮罩 {draft.dim}%</span>
          </div>
          <input
            type="range"
            min={0}
            max={70}
            value={draft.dim}
            onChange={(e) => setDraft({ ...draft, dim: Number(e.target.value || 20) })}
            className="w-full"
          />
        </div>
        <div className="flex items-center gap-2">
          <Btn kind="blue" onClick={onClose}>取消</Btn>
          <Btn kind="green" onClick={save}>保存</Btn>
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
          onChange={(e) => setText(e.target.value)}
          placeholder={loading ? "加载中..." : "在这里编辑核心 Prompt"}
        />
        <div className="flex items-center gap-2">
          <Btn kind="blue" onClick={load} disabled={loading || saving}>刷新</Btn>
          <Btn kind="green" onClick={save} disabled={loading || saving}>保存</Btn>
        </div>
      </div>
    </Modal>
  );
}

