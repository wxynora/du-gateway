import React, { useEffect, useMemo, useState } from "react";
import { applyTelegramThemeToHtmlClass, tgReady } from "./tg";
import { ToastProvider, useToast } from "./toast";
import { Btn } from "./components";
import { LogsTab } from "./tabs/LogsTab";
import { SettingsUpstream } from "./tabs/SettingsUpstream";
import { ReasoningTab } from "./tabs/ReasoningTab";

type TabId = "logs" | "reasoning";

function Shell() {
  const toast = useToast();
  const [tab, setTab] = useState<TabId>("logs");
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    // 默认不 expand：让 Telegram WebView 以“半屏”形式打开，更像面板弹出入口
    tgReady(false);
    applyTelegramThemeToHtmlClass();
  }, []);

  const activeTitle = useMemo(() => {
    if (tab === "logs") return "日志";
    return "思维链";
  }, [tab]);

  // 第一版只做：日志 / 思维链；状态接口不再强依赖

  return (
    <div className="min-h-dvh safe-top safe-bottom bg-cream-bg text-cream-text">
      <div className="sticky top-0 z-20 border-b border-cream-border/80 bg-cream-bg/85 backdrop-blur">
        <div className="flex items-center justify-between px-4 pb-3 pt-4">
          <div className="font-semibold tracking-tight">{activeTitle}</div>
          <div className="flex items-center gap-2">
            <Btn onClick={() => setShowSettings(true)}>上游</Btn>
          </div>
        </div>
      </div>

      <div className="px-4 py-4 pb-24">
        {tab === "logs" && <LogsTab />}
        {tab === "reasoning" && <ReasoningTab />}
      </div>

      <div className="fixed bottom-0 left-0 right-0 z-30 safe-bottom">
        <div className="mx-auto max-w-xl px-3 pb-3">
          <div className="flex rounded-[22px] border border-cream-border bg-cream-card/90 shadow-soft backdrop-blur px-2">
          <TabButton id="logs" active={tab === "logs"} onClick={() => setTab("logs")}>
            日志
          </TabButton>
          <TabButton id="reasoning" active={tab === "reasoning"} onClick={() => setTab("reasoning")}>
            思维链
          </TabButton>
          </div>
        </div>
      </div>

      {showSettings ? <SettingsUpstream onClose={() => setShowSettings(false)} /> : null}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  id: string;
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  const cls =
    "flex-1 py-2 text-xs font-medium " +
    (active ? "text-cream-text" : "text-cream-muted");
  return (
    <button className={cls} onClick={onClick}>
      {children}
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

