import React, { useEffect, useState } from "react";
import { ToastProvider, useToast } from "./toast";
import { apiJson, consumePendingPanelDeviceIdMigration, getOrCreatePanelDeviceId, getPanelDeviceLabel, getPanelToken, publicApiFetch, setPanelToken } from "./api";
import { AppShell } from "./AppShell";
import { DeviceManagerModal } from "./DeviceManagerModal";
import { migrateLocalChatHistoriesToDevice, migrateLocalChatHistoryDevice } from "./storage/chatHistoryDb";

function isLocalRecallPreviewRoute(): boolean {
  if (!import.meta.env.DEV || typeof window === "undefined") return false;
  try {
    const enabled = new URLSearchParams(window.location.search).get("recallPreview") === "1";
    if (enabled) (window as any).__sumitalkLocalRecallPreview = true;
    return enabled || (window as any).__sumitalkLocalRecallPreview === true;
  } catch {
    return (window as any).__sumitalkLocalRecallPreview === true;
  }
}

export function App() {
  return (
    <ToastProvider>
      <AppWithAuth />
    </ToastProvider>
  );
}

function AppWithAuth() {
  const toast = useToast();
  const [metaLoading, setMetaLoading] = useState(true);
  const [authEnabled, setAuthEnabled] = useState(false);
  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState("");
  const [secondAnswer, setSecondAnswer] = useState("");
  const [loginStep, setLoginStep] = useState<"password" | "question">("password");
  const [submitting, setSubmitting] = useState(false);
  const [errorText, setErrorText] = useState("");
  const [secondPrompt, setSecondPrompt] = useState("");
  const [showDeviceManager, setShowDeviceManager] = useState(false);

  async function repairPanelDeviceMigration(currentDeviceId: string) {
    const migration = consumePendingPanelDeviceIdMigration();
    await migrateLocalChatHistoriesToDevice(currentDeviceId);
    if (!migration?.from || !migration.to || migration.to !== currentDeviceId) return;
    await migrateLocalChatHistoryDevice(migration.from, migration.to);
    try {
      const j = await apiJson<{ ok?: boolean; panel_token?: string }>("/miniapp-api/sumitalk-history/migrate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_device_id: migration.to }),
      });
      const nextToken = String(j?.panel_token || "").trim();
      if (nextToken) setPanelToken(nextToken);
    } catch {}
  }

  useEffect(() => {
    if (isLocalRecallPreviewRoute()) {
      setAuthEnabled(false);
      setReady(true);
      setMetaLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const j = await publicApiFetch("/miniapp-api/panel-auth/meta").then((r) => r.json());
        if (cancelled) return;
        const enabled = !!j?.enabled;
        setAuthEnabled(enabled);
        setSecondPrompt(String(j?.second_prompt || ""));
        if (!enabled) {
          setReady(true);
          return;
        }
        const token = getPanelToken();
        if (!token) {
          setReady(false);
          return;
        }
        const currentDeviceId = await getOrCreatePanelDeviceId();
        await repairPanelDeviceMigration(currentDeviceId);
        const s = await apiJson<{ ok?: boolean; authenticated?: boolean; device_id?: string }>("/miniapp-api/panel-auth/session");
        if (cancelled) return;
        if (s?.ok && s?.authenticated) {
          const tokenDeviceId = String(s?.device_id || "").trim();
          if (currentDeviceId && tokenDeviceId && tokenDeviceId !== currentDeviceId) {
            setPanelToken("");
            setReady(false);
            return;
          }
          setReady(true);
          return;
        }
        setPanelToken("");
        setReady(false);
      } catch {
        if (cancelled) return;
        setReady(false);
      } finally {
        if (!cancelled) setMetaLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function onExpired(ev: Event) {
      const detail = (ev as CustomEvent<{ code?: string; message?: string }>).detail || {};
      setReady(false);
      setPassword("");
      setSecondAnswer("");
      setLoginStep("password");
      setErrorText(String(detail.message || "登录已失效，请重新验证"));
      toast(String(detail.message || "当前浏览器访问已失效"));
    }
    window.addEventListener("miniapp-auth-expired", onExpired as EventListener);
    return () => {
      window.removeEventListener("miniapp-auth-expired", onExpired as EventListener);
    };
  }, [toast]);

  async function login() {
    if (!password.trim()) {
      setErrorText("Please enter your password.");
      return;
    }
    if (secondPrompt && loginStep === "question" && !secondAnswer.trim()) {
      setErrorText("Please answer the security question.");
      return;
    }
    setSubmitting(true);
    setErrorText("");
    try {
      if (secondPrompt && loginStep === "password") {
        const first = await publicApiFetch("/miniapp-api/panel-auth/check-password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password: password.trim() }),
        }).then(async (r) => ({ ok: r.ok, body: await r.json().catch(() => ({})) }));
        if (!first.ok || !first.body?.ok) {
          throw new Error(first.body?.error || "Password verification failed");
        }
        setLoginStep("question");
        setErrorText("");
        return;
      }
      const deviceId = await getOrCreatePanelDeviceId();
      await migrateLocalChatHistoriesToDevice(deviceId);
      const j = await publicApiFetch("/miniapp-api/panel-auth/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          password: password.trim(),
          second_answer: secondAnswer.trim(),
          device_id: deviceId,
          device_name: getPanelDeviceLabel(),
        }),
      }).then(async (r) => ({ ok: r.ok, body: await r.json().catch(() => ({})) }));
      if (!j.ok || !j.body?.ok || !j.body?.panel_token) {
        throw new Error(j.body?.error || "密码校验失败");
      }
      setPanelToken(String(j.body.panel_token));
      setPassword("");
      setSecondAnswer("");
      setLoginStep("password");
      setReady(true);
      toast("已进入 SumiTalk");
    } catch (e: any) {
      setErrorText(e?.message || "登录失败");
    } finally {
      setSubmitting(false);
    }
  }

  function logout() {
    setPanelToken("");
    setReady(false);
    setPassword("");
    setSecondAnswer("");
    setLoginStep("password");
    setErrorText("");
    setShowDeviceManager(false);
    toast("已退出登录");
  }

  if (metaLoading) {
    return <LoadingScreen text="正在检查面板登录状态..." />;
  }
  if (!authEnabled || ready) {
    return (
      <ShellWithLogout
        onLogout={authEnabled ? logout : undefined}
        onOpenDevices={authEnabled ? () => setShowDeviceManager(true) : undefined}
        deviceManagerOpen={showDeviceManager}
        onCloseDevices={() => setShowDeviceManager(false)}
      />
    );
  }
  return (
    <div className="min-h-dvh bg-cream-bg px-5 py-6 text-cream-text" style={{ fontFamily: '"Nunito", sans-serif' }}>
      <div className="mx-auto flex min-h-[calc(100dvh-3rem)] max-w-md flex-col items-center justify-center">
        {/* 螃蟹 + 标题 */}
        <div className="mb-6 flex flex-col items-center">
          <div className="mb-3 flex h-16 w-16 items-center justify-center rounded-[20px] bg-[rgba(244,247,251,0.82)] shadow-soft2">
            <ClaudePixelCrabIcon />
          </div>
          <div className="text-[26px] font-bold tracking-tight text-cream-text">
            {secondPrompt && loginStep === "question" ? "Security Check" : "Welcome to SumiTalk"}
          </div>
          <div className="mt-1 text-[15px] text-cream-muted">
            {secondPrompt && loginStep === "question" ? "Answer the question to continue." : "Enter password to continue."}
          </div>
        </div>

        {/* 卡片 */}
        <div className="neo-panel w-full p-6">
          <div className="space-y-4">
            {loginStep === "password" || !secondPrompt ? (
              <label className="block">
                <div className="mb-2 text-[13px] font-semibold text-cream-muted">Password</div>
                <input
                  className="h-12 w-full rounded-[16px] border-none bg-cream-bg px-4 text-[16px] text-cream-text outline-none shadow-[inset_3px_3px_7px_rgba(173,182,196,0.28),inset_-2px_-2px_4px_rgba(255,255,255,0.7)] placeholder:text-cream-muted focus:ring-2 focus:ring-cream-accent/40"
                  type="password"
                  placeholder="Enter password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !submitting) void login();
                  }}
                />
              </label>
            ) : null}

            {secondPrompt && loginStep === "question" ? (
              <label className="block">
                <div className="mb-2 text-[13px] font-semibold text-cream-muted">{secondPrompt}</div>
                <input
                  className="h-12 w-full rounded-[16px] border-none bg-cream-bg px-4 text-[16px] text-cream-text outline-none shadow-[inset_3px_3px_7px_rgba(173,182,196,0.28),inset_-2px_-2px_4px_rgba(255,255,255,0.7)] placeholder:text-cream-muted focus:ring-2 focus:ring-cream-accent/40"
                  type="text"
                  placeholder="Enter answer"
                  value={secondAnswer}
                  onChange={(e) => setSecondAnswer(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !submitting) void login();
                  }}
                />
              </label>
            ) : null}

            {errorText ? (
              <div className="rounded-[12px] bg-cream-danger/10 px-4 py-2.5 text-[14px] text-cream-danger">
                {errorText}
              </div>
            ) : null}

            <div className="flex items-center justify-center gap-3 pt-1">
              {secondPrompt && loginStep === "question" ? (
                <button
                  type="button"
                  className="min-w-[90px] rounded-[14px] bg-cream-bg px-5 py-3 text-[15px] font-semibold text-cream-muted shadow-soft2 transition active:translate-y-[1px] active:shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={() => {
                    setLoginStep("password");
                    setSecondAnswer("");
                    setErrorText("");
                  }}
                  disabled={submitting}
                >
                  Back
                </button>
              ) : null}
              <button
                type="button"
                className="min-w-[140px] rounded-[14px] bg-cream-accent/80 px-6 py-3 text-[15px] font-bold text-cream-text shadow-soft2 transition active:translate-y-[1px] active:bg-cream-accent/90 active:shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => void login()}
                disabled={submitting}
              >
                {submitting ? "Verifying..." : secondPrompt && loginStep === "password" ? "Next" : "Sign In"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ClaudePixelCrabIcon() {
  return (
    <svg className="h-10 w-10" viewBox="0 0 88 88" aria-hidden>
      <rect x="20" y="18" width="48" height="36" fill="#DD8A6B" />
      <rect x="12" y="26" width="8" height="12" fill="#DD8A6B" />
      <rect x="68" y="26" width="8" height="12" fill="#DD8A6B" />
      <rect x="28" y="10" width="32" height="8" fill="#DD8A6B" />
      <rect x="32" y="26" width="6" height="12" fill="#111111" />
      <rect x="50" y="26" width="6" height="12" fill="#111111" />
      <rect x="24" y="54" width="6" height="12" fill="#DD8A6B" />
      <rect x="40" y="54" width="6" height="12" fill="#DD8A6B" />
      <rect x="56" y="54" width="6" height="12" fill="#DD8A6B" />
      <rect x="22" y="66" width="44" height="6" fill="#8A8A8A" />
    </svg>
  );
}

function ShellWithLogout({
  onLogout,
  onOpenDevices,
  deviceManagerOpen,
  onCloseDevices,
}: {
  onLogout?: () => void;
  onOpenDevices?: () => void;
  deviceManagerOpen?: boolean;
  onCloseDevices?: () => void;
}) {
  return (
    <>
      <AppShell
        onLogout={onLogout}
        onOpenDevices={onOpenDevices}
        deviceManagerOpen={deviceManagerOpen}
        onCloseDevices={onCloseDevices}
      />
      {deviceManagerOpen && onCloseDevices ? <DeviceManagerModal onClose={onCloseDevices} onLogout={onLogout} /> : null}
    </>
  );
}

function LoadingScreen({ text }: { text: string }) {
  return (
    <div className="min-h-dvh bg-[#EEF0F3] px-5 py-6 text-cream-text">
      <div className="mx-auto flex min-h-[calc(100dvh-3rem)] max-w-md items-center">
        <div className="neo-panel-soft w-full p-5 text-sm text-cream-muted">{text}</div>
      </div>
    </div>
  );
}
