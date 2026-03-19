import React, { useEffect, useState } from "react";
import { applyTelegramThemeToHtmlClass, tgReady } from "./tg";
import { ToastProvider, useToast } from "./toast";
import { apiJson } from "./api";
import { Btn, Modal } from "./components";
import { LogsTab } from "./tabs/LogsTab";
import { SettingsUpstream } from "./tabs/SettingsUpstream";
import { ReasoningTab } from "./tabs/ReasoningTab";

type PanelId = "logs" | "reasoning" | null;

function Shell() {
  const [panel, setPanel] = useState<PanelId>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showCorePrompt, setShowCorePrompt] = useState(false);
  const version = new URLSearchParams(window.location.search).get("v") || "";

  useEffect(() => {
    // 默认不 expand：让 Telegram WebView 以“半屏”形式打开，更像面板弹出入口
    tgReady(false);
    applyTelegramThemeToHtmlClass();
  }, []);

  return (
    <div className="min-h-dvh safe-top safe-bottom bg-cream-bg text-cream-text">
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
          <FeatureTile title="日志" desc="查看/过滤/复制" color="bg-cream-blue/30" onClick={() => setPanel("logs")} />
          <FeatureTile title="思维链" desc="窗口轮次与推理" color="bg-cream-pink/45" onClick={() => setPanel("reasoning")} />
          <FeatureTile title="上游切换" desc="全局 active 切换" color="bg-cream-green/55" onClick={() => setShowSettings(true)} />
          <FeatureTile title="核心Prompt" desc="固定注入，可随时更新" color="bg-cream-card" onClick={() => setShowCorePrompt(true)} />
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
        "h-24 rounded-xl3 p-3 text-left shadow-soft transition active:scale-[0.99] " +
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

