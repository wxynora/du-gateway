import React, { useEffect, useState } from "react";
import { applyTelegramThemeToHtmlClass, tgReady } from "./tg";
import { ToastProvider } from "./toast";
import { Btn, Modal } from "./components";
import { LogsTab } from "./tabs/LogsTab";
import { SettingsUpstream } from "./tabs/SettingsUpstream";
import { ReasoningTab } from "./tabs/ReasoningTab";

type PanelId = "logs" | "reasoning" | null;

function Shell() {
  const [panel, setPanel] = useState<PanelId>(null);
  const [showSettings, setShowSettings] = useState(false);
  const version = new URLSearchParams(window.location.search).get("v") || "";

  useEffect(() => {
    // 默认不 expand：让 Telegram WebView 以“半屏”形式打开，更像面板弹出入口
    tgReady(false);
    applyTelegramThemeToHtmlClass();
  }, []);

  return (
    <div className="min-h-dvh safe-top safe-bottom bg-cream-bg text-cream-text">
      <div className="sticky top-0 z-20 border-b border-cream-border/80 bg-cream-bg/85 backdrop-blur">
        <div className="flex items-center justify-between px-4 pb-3 pt-4">
          <div className="font-semibold tracking-tight rounded-xl2 px-3 py-1 border border-cream-border bg-cream-green/35">
            躺着运维
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
          <FeatureTile title="思维链" desc="窗口轮次与推理" color="bg-cream-pink/35" onClick={() => setPanel("reasoning")} />
          <FeatureTile title="上游切换" desc="全局 active 切换" color="bg-cream-green/40" onClick={() => setShowSettings(true)} />
          <FeatureTile title="更多功能" desc="后续继续扩展" color="bg-cream-card" onClick={() => {}} disabled />
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
        "aspect-square rounded-xl3 border border-cream-border p-4 text-left shadow-soft transition active:scale-[0.99] " +
        color +
        (disabled ? " opacity-60 cursor-not-allowed" : "")
      }
      onClick={() => {
        if (disabled) return;
        onClick();
      }}
      disabled={disabled}
    >
      <div className="text-base font-semibold">{title}</div>
      <div className="mt-2 text-xs text-cream-muted">{desc}</div>
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

