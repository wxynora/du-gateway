import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./ui/App";
import "./styles.css";

const REPORT_API_BASE = String(import.meta.env.VITE_API_BASE_URL || "").trim().replace(/\/+$/, "");

declare global {
  interface Window {
    SumiNativeLog?: {
      report?: (level: string, message: string, stack: string) => void;
    };
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message || error.name || "Unknown error";
  if (typeof error === "string") return error;
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

function errorStack(error: unknown): string {
  if (error instanceof Error) return String(error.stack || "");
  return "";
}

function getPanelTokenForReport(): string {
  try {
    return String(window.localStorage.getItem("miniapp.panel.token.v1") || "").trim();
  } catch {
    return "";
  }
}

function reportClientError(kind: string, error: unknown, extra: Record<string, unknown> = {}) {
  const message = errorMessage(error).slice(0, 800);
  const stack = errorStack(error).slice(0, 4000);
  try {
    window.SumiNativeLog?.report?.(kind, message, stack);
  } catch {}
  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const token = getPanelTokenForReport();
    if (token) headers.Authorization = `Bearer ${token}`;
    const reportUrl = `${REPORT_API_BASE || ""}/miniapp-api/client-error`;
    void fetch(reportUrl, {
      method: "POST",
      headers,
      body: JSON.stringify({
        kind,
        message,
        stack,
        href: window.location.href,
        userAgent: navigator.userAgent,
        ...extra,
      }),
      keepalive: true,
    }).catch(() => undefined);
  } catch {}
}

window.addEventListener("error", (event) => {
  reportClientError("window_error", event.error || event.message, {
    source: event.filename,
    line: event.lineno,
    column: event.colno,
  });
});

window.addEventListener("unhandledrejection", (event) => {
  reportClientError("unhandled_rejection", event.reason || "unhandled promise rejection");
});

class RootErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    reportClientError("react_render_error", error, { componentStack: info.componentStack });
  }

  render() {
    if (!this.state.error) return this.props.children;
    const msg = errorMessage(this.state.error);
    return (
      <div className="min-h-dvh bg-[#EEF0F3] px-5 py-6 text-[#1f2933]">
        <div className="mx-auto flex min-h-[calc(100dvh-3rem)] max-w-md items-center">
          <div className="w-full rounded-[28px] border border-white/70 bg-white/90 p-5 shadow-[0_18px_50px_rgba(35,45,60,0.12)]">
            <div className="mb-3 text-[18px] font-bold">SumiTalk 前端崩了</div>
            <div className="mb-4 rounded-2xl bg-red-50 px-4 py-3 font-mono text-[12px] leading-5 text-red-600">
              {msg || "未知错误"}
            </div>
            <div className="space-y-3 text-[13px] leading-6 text-gray-500">
              <p>错误已经上报到网关日志。先点重载，如果还不行，把日志里 [SumiTalk] client_error 那段给笨笨。</p>
              <button
                type="button"
                className="w-full rounded-2xl bg-gray-900 px-4 py-3 font-bold text-white"
                onClick={() => window.location.reload()}
              >
                重载页面
              </button>
              <button
                type="button"
                className="w-full rounded-2xl bg-gray-100 px-4 py-3 font-bold text-gray-600"
                onClick={() => {
                  try {
                    for (const key of Object.keys(window.localStorage)) {
                      if (key.startsWith("miniapp.ui.") || key.startsWith("miniapp.co_read.")) {
                        window.localStorage.removeItem(key);
                      }
                    }
                  } catch {}
                  window.location.reload();
                }}
              >
                清理界面缓存后重载
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>
  </React.StrictMode>,
);
