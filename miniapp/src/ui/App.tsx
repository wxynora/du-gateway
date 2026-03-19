import React, { useEffect, useState } from "react";
import { applyTelegramThemeToHtmlClass, tgReady } from "./tg";
import { ToastProvider, useToast } from "./toast";
import { apiFetch, apiJson } from "./api";
import { Btn, Modal } from "./components";
import { LogsTab } from "./tabs/LogsTab";
import { SettingsUpstream } from "./tabs/SettingsUpstream";
import { ReasoningTab } from "./tabs/ReasoningTab";

type PanelId = "logs" | "reasoning" | null;
type BgPreset = "cream" | "grid" | "soft";
type BgConfig = { preset: BgPreset; useImage: boolean; imageVersion: number; dim: number };
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
    imageVersion: 0,
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
          imageVersion: Number(j?.imageVersion || 0),
          dim: Number.isFinite(Number(j?.dim)) ? Math.max(0, Math.min(70, Number(j?.dim))) : 20,
        });
      }
    } catch {}

    apiJson<{ ok?: boolean; config?: Partial<BgConfig> }>("/miniapp-api/background-config")
      .then((j) => {
        if (!j?.ok || !j?.config) return;
        setBg((prev: BgConfig) => ({
          preset: (j.config?.preset as BgPreset) || prev.preset,
          useImage: !!j.config?.useImage,
          imageVersion: Number(j.config?.imageVersion || 0),
          dim: Number.isFinite(Number(j.config?.dim)) ? Math.max(0, Math.min(70, Number(j.config?.dim))) : prev.dim,
        }));
      })
      .catch(() => {});
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
          <div className="font-semibold tracking-tight rounded-xl2 px-3 py-1 bg-white/65 backdrop-blur-md border border-white/50 shadow-soft2">
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
          <FeatureTile title="日志" desc="查看/过滤/复制" color="bg-white/38" icon={<LineIcon name="logs" />} onClick={() => setPanel("logs")} />
          <FeatureTile title="思维链" desc="窗口轮次与推理" color="bg-white/38" icon={<LineIcon name="reasoning" />} onClick={() => setPanel("reasoning")} />
          <FeatureTile title="上游切换" desc="全局 active 切换" color="bg-white/38" icon={<LineIcon name="upstream" />} onClick={() => setShowSettings(true)} />
          <FeatureTile title="核心Prompt" desc="固定注入，可随时更新" color="bg-white/38" icon={<LineIcon name="prompt" />} onClick={() => setShowCorePrompt(true)} />
          <FeatureTile title="背景设置" desc="可换风格/相册图" color="bg-white/38" icon={<LineIcon name="background" />} onClick={() => setShowBgEditor(true)} />
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

function LineIcon({ name }: { name: "logs" | "reasoning" | "upstream" | "prompt" | "background" }) {
  const cls = "h-4 w-4 text-cream-text";
  if (name === "logs") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 6h16M4 12h16M4 18h10" /></svg>;
  if (name === "reasoning") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 12h4l2-4 4 8 2-4h4" /></svg>;
  if (name === "upstream") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h10M14 7l3-3m-3 3 3 3M20 17H10m0 0-3-3m3 3-3 3" /></svg>;
  if (name === "prompt") return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 5h14v14H5zM8 9h8M8 13h8M8 17h5" /></svg>;
  return <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 20h16M4 8l4 4 4-6 4 5 4-3v12H4z" /></svg>;
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
      backgroundImage: `linear-gradient(rgba(238,240,243,${alpha}), rgba(238,240,243,${alpha})), url("/miniapp-api/background-image?v=${bg.imageVersion}")`,
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
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    setDraft(bg);
  }, [bg]);

  function save() {
    onChange(draft);
    apiJson<{ ok?: boolean }>("/miniapp-api/background-config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    }).catch(() => {});
    toast("背景已保存");
    onClose();
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
        const next = { ...v, useImage: true, imageVersion: version };
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
          <Btn kind={draft.preset === "cream" ? "green" : "default"} onClick={() => setDraft({ ...draft, preset: "cream", useImage: false })}>米白</Btn>
          <Btn kind={draft.preset === "grid" ? "green" : "default"} onClick={() => setDraft({ ...draft, preset: "grid", useImage: false })}>网格灰</Btn>
          <Btn kind={draft.preset === "soft" ? "green" : "default"} onClick={() => setDraft({ ...draft, preset: "soft", useImage: false })}>柔和彩</Btn>
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
            <Btn kind={draft.useImage ? "green" : "default"} onClick={() => setDraft({ ...draft, useImage: !draft.useImage })}>
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
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setDraft({ ...draft, dim: Number(e.target.value || 20) })}
            className="w-full"
          />
        </div>
        <div className="flex items-center gap-2">
          <Btn kind="blue" onClick={onClose}>取消</Btn>
          <Btn kind="green" onClick={save} disabled={uploading}>保存</Btn>
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
          <Btn kind="blue" onClick={load} disabled={loading || saving}>刷新</Btn>
          <Btn kind="green" onClick={save} disabled={loading || saving}>保存</Btn>
        </div>
      </div>
    </Modal>
  );
}

