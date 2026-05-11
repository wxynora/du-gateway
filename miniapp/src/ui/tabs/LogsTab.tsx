import React, { useEffect, useMemo, useRef, useState } from "react";
import { apiJson, buildLogStreamUrl } from "../api";
import { useToast } from "../toast";

type LogsResp = { ok?: boolean; lines?: string[]; error?: string };

type LogCategory = "all" | "proactive" | "sumitalk" | "wechat" | "tgbot" | "qq";

const LOG_CATEGORY_OPTIONS: Array<{ value: LogCategory; label: string }> = [
  { value: "all", label: "全部" },
  { value: "sumitalk", label: "SumiTalk" },
  { value: "proactive", label: "主动信息" },
  { value: "wechat", label: "微信通道" },
  { value: "tgbot", label: "TGBot" },
  { value: "qq", label: "QQ 通道" },
];

function CopyIcon() {
  return <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="11" height="11" rx="2" ry="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>;
}

function PauseIcon() {
  return <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="6" y="4" width="4" height="16" rx="1" /><rect x="14" y="4" width="4" height="16" rx="1" /></svg>;
}

function DownloadIcon() {
  return <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M5 21h14" /></svg>;
}

function SearchIcon() {
  return <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></svg>;
}

function ClearIcon() {
  return <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm3.54 12.12-1.42 1.42L12 13.41l-2.12 2.13-1.42-1.42L10.59 12 8.46 9.88l1.42-1.42L12 10.59l2.12-2.13 1.42 1.42L13.41 12Z" /></svg>;
}

function TrashIcon() {
  return <svg className="h-[14px] w-[14px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="m19 6-1 14H6L5 6" /></svg>;
}

const ERROR_PATTERNS = [
  /\]\s*(ERROR|CRITICAL|FATAL):/i,
  /(^|\s)(error|err|exception|fatal|fail(ed|ure)?|traceback|panic)(\s|:|=|$)/i,
  /(^|\s)(timeout|timed out|connection (closed|reset|refused))(\s|:|$)/i,
  /\bhttp\s*[45]\d{2}\b/i,
  /\bstatus\s*[:=]?\s*[45]\d{2}\b/i,
  /\b(401|403|404|408|409|429|500|502|503|504)\b/i,
  /非\s*200|接口加载失败|请求失败|操作失败|转发失败|发送失败|生成失败|保存失败|加载失败|\/push 失败|失败|异常|报错|错误|上游返回异常|未送达|未找到|权限不足|鉴权失败|无权限|unauthorized|forbidden|no access|permission denied|rate limit|too many requests/i,
];

export function LogsTab() {
  const toast = useToast();
  const [paused, setPaused] = useState(false);
  const [lines, setLines] = useState<string[]>([]);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const [filterText, setFilterText] = useState("");
  const [filterKind, setFilterKind] = useState<LogCategory>("all");
  const [loadError, setLoadError] = useState("");
  const alertedErrorLinesRef = useRef<Set<string>>(new Set());

  function lineKind(line: string): LogCategory | "other" {
    const raw = String(line || "");
    if (raw.includes("[SumiTalk]")) return "sumitalk";
    if (raw.includes("[TGPro]") || raw.includes("主动发消息")) return "proactive";
    if (raw.includes("[wechat-ilink]")) return "wechat";
    if (raw.includes("[TGBot]")) return "tgbot";
    if (raw.includes("[qq-onebot]")) return "qq";
    return "other";
  }

  function labelForKind(kind: LogCategory | "other") {
    if (kind === "proactive") return "主动信息";
    if (kind === "sumitalk") return "SumiTalk";
    if (kind === "wechat") return "微信通道";
    if (kind === "tgbot") return "TGBot";
    if (kind === "qq") return "QQ 通道";
    return "系统";
  }

  function accentForKind(kind: LogCategory | "other") {
    if (kind === "proactive") return "border-l-[#4A5568] bg-[#F7F8FA] text-[#4A5568]";
    if (kind === "sumitalk") return "border-l-cyan-400 bg-cyan-50 text-cyan-700";
    if (kind === "wechat") return "border-l-green-400 bg-green-50 text-green-600";
    if (kind === "tgbot") return "border-l-blue-400 bg-blue-50 text-blue-600";
    if (kind === "qq") return "border-l-purple-400 bg-purple-50 text-purple-600";
    return "border-l-orange-400 bg-orange-50 text-orange-500";
  }

  function extractClock(line: string) {
    const m = String(line || "").match(/\b(\d{2}:\d{2}:\d{2})\b/);
    return m?.[1] || "--:--:--";
  }

  function isErrorLine(line: string) {
    const raw = String(line || "");
    return ERROR_PATTERNS.some((p) => p.test(raw));
  }

  function compactErrorLine(line: string) {
    const raw = String(line || "")
      .replace(/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}\s*/, "")
      .replace(/^\[[^\]]+\]\s*/, "")
      .trim();
    return raw.length > 180 ? `${raw.slice(0, 180)}...` : raw;
  }

  function notifyErrorLine(line: string) {
    if (!isErrorLine(line)) return false;
    const raw = String(line || "");
    const key = raw
      .replace(/\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3}/g, "<time>")
      .slice(0, 800);
    const seen = alertedErrorLinesRef.current;
    if (seen.has(key)) return false;
    if (seen.size > 120) seen.clear();
    seen.add(key);
    toast(`日志报错：${compactErrorLine(raw)}`);
    return true;
  }

  const filtered = useMemo(() => {
    const k = (filterText || "").trim().toLowerCase();
    return (lines || []).filter((l) => {
      if (!k) return true;
      return (l || "").toLowerCase().includes(k);
    });
  }, [lines, filterText]);

  function highlightLine(line: string, keyword: string) {
    const k = (keyword || "").trim().toLowerCase();
    if (!k) return line;
    const raw = line ?? "";
    const lower = raw.toLowerCase();
    const out: React.ReactNode[] = [];
    let i = 0;
    while (true) {
      const idx = lower.indexOf(k, i);
      if (idx < 0) {
        out.push(raw.slice(i));
        break;
      }
      if (idx > i) out.push(raw.slice(i, idx));
      const hit = raw.slice(idx, idx + k.length);
      out.push(
        <span key={`${idx}-${hit.length}`} className="rounded bg-blue-50 px-0.5 font-semibold text-blue-600">
          {hit}
        </span>,
      );
      i = idx + k.length;
    }
    return out;
  }

  async function copyText(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast("已复制");
    } catch {
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.left = "-10000px";
        ta.style.top = "-10000px";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand("copy");
        ta.remove();
        toast("已复制");
      } catch (e) {
        toast(`复制失败：${(e as any)?.message || e}`);
      }
    }
  }

  async function loadTail(silent = false) {
    try {
      const q = new URLSearchParams({ lines: "200", category: filterKind });
      const j = await apiJson<LogsResp>(`/miniapp-api/logs?${q.toString()}`);
      const latestFirst = (j.lines || []).slice().reverse();
      setLines(latestFirst);
      setLoadError("");
      if (!silent) {
        const latestError = latestFirst.find((line) => isErrorLine(line));
        if (!latestError || !notifyErrorLine(latestError)) toast("已加载最新日志");
      }
    } catch (e: any) {
      setLoadError(e?.message || String(e));
      if (!silent) toast(`加载失败：${e?.message || e}`);
    }
  }

  function connect() {
    if (esRef.current) return;
    const es = new EventSource(buildLogStreamUrl(80, filterKind));
    esRef.current = es;
    setConnected(true);
    es.onmessage = (ev) => {
      if (paused) return;
      const line = String(ev.data || "");
      notifyErrorLine(line);
      setLines((prev) => {
        const next = [line, ...prev];
        if (next.length > 2000) next.splice(2000);
        return next;
      });
    };
    es.onerror = () => {
      try {
        es.close();
      } catch {}
      esRef.current = null;
      setConnected(false);
      toast("实时日志断开");
    };
  }

  function disconnect(silent = false) {
    if (!esRef.current) return;
    try {
      esRef.current.close();
    } catch {}
    esRef.current = null;
    setConnected(false);
    if (!silent) toast("已断开实时");
  }

  useEffect(() => {
    return () => disconnect(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadTail(true);
    if (!connected) return;
    disconnect(true);
    connect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKind]);

  return (
    <div className="flex min-h-full flex-col overflow-hidden bg-[#FDFDFD]" style={{ fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" }}>
      <div className="flex items-center border-b border-gray-50 bg-white/90 px-4 pb-4 pt-[calc(env(safe-area-inset-top,0px)+14px)] backdrop-blur-md">
        <div className="ml-auto flex items-center rounded-full border border-gray-100 bg-gray-50 px-3 py-1">
          <span className={`mr-2 h-1.5 w-1.5 rounded-full ${connected ? "animate-pulse bg-green-400" : "bg-gray-300"}`} />
          <span className="text-[11px] font-medium text-gray-500">{connected ? "实时连接中" : "未连接"}</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto pb-8">
        <div className="px-5 pt-6">
          <div className="mb-4 rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.04),0_8px_10px_-6px_rgba(0,0,0,0.02)]">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <h3 className="text-[15px] font-bold text-gray-800">实时追加</h3>
                <p className="mt-0.5 text-[12px] font-light text-gray-400">自动同步服务器最新内容</p>
              </div>
              <label className="relative inline-block h-6 w-[42px]">
                <input
                  type="checkbox"
                  className="peer sr-only"
                  checked={connected}
                  onChange={() => {
                    if (connected) disconnect();
                    else connect();
                  }}
                />
                <span className="absolute inset-0 rounded-full bg-[#E2E8F0] transition peer-checked:bg-[#4A5568]" />
                <span className="absolute bottom-[3px] left-[3px] h-[18px] w-[18px] rounded-full bg-white transition peer-checked:translate-x-[18px]" />
              </label>
            </div>

            <div className="flex gap-3">
              <button
                className="flex flex-1 items-center justify-center gap-2 rounded-2xl bg-gray-50 py-3 text-[13px] font-medium text-gray-600 transition-colors active:bg-gray-100"
                onClick={() => {
                  setPaused((p) => !p);
                  toast(!paused ? "已暂停" : "已继续");
                }}
              >
                <PauseIcon />
                {paused ? "继续更新" : "暂停更新"}
              </button>
              <button
                className="flex flex-1 items-center justify-center gap-2 rounded-2xl border border-gray-100 py-3 text-[13px] font-medium text-gray-600 transition-colors active:bg-gray-50"
                onClick={() => void loadTail()}
              >
                <DownloadIcon />
                拉取快照
              </button>
            </div>
          </div>

          <div className="mb-6 rounded-[28px] border border-gray-100/80 bg-white p-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.04),0_8px_10px_-6px_rgba(0,0,0,0.02)]">
            <div className="relative mb-4">
              <div className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">
                <SearchIcon />
              </div>
              <input
                type="text"
                placeholder="搜索关键字..."
                className="w-full rounded-2xl bg-gray-50 py-3 pl-11 pr-10 text-[14px] outline-none placeholder:text-gray-300 focus:ring-1 focus:ring-gray-200"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
              />
              {filterText ? (
                <button
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-300 transition-colors active:text-gray-500"
                  onClick={() => setFilterText("")}
                >
                  <ClearIcon />
                </button>
              ) : null}
            </div>

            <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
              {LOG_CATEGORY_OPTIONS.map((option) => {
                const active = filterKind === option.value;
                return (
                  <button
                    key={option.value}
                    className={`whitespace-nowrap rounded-full px-4 py-1.5 text-[12px] font-medium transition-all ${active ? "bg-gray-800 text-white" : "bg-gray-50 text-gray-500"}`}
                    onClick={() => setFilterKind(option.value)}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>

            <div className="mt-3 flex justify-end">
              <button
                className="flex items-center gap-1 text-[11px] font-medium text-blue-500"
                onClick={() => {
                  setFilterText("");
                  setFilterKind("all");
                  toast("已清空筛选");
                }}
              >
                <TrashIcon />
                清空筛选
              </button>
            </div>
          </div>

          {loadError ? (
            <div className="mb-4 rounded-[24px] border border-red-100 bg-red-50 px-4 py-3 text-[12px] leading-6 text-red-500">
              接口加载失败：{loadError}
            </div>
          ) : null}

          <div className="mb-4 flex items-center justify-between px-1">
            <div className="flex items-baseline space-x-2">
              <h2 className="text-[13px] font-bold uppercase tracking-widest text-gray-400">日志输出</h2>
              <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-400">最新在上</span>
            </div>
            <span className="text-[11px] text-gray-300">共 {filtered.length} 条</span>
          </div>

          <div className="space-y-0.5">
            {filtered.slice(0, 800).map((line, idx) => {
              const kind = lineKind(line);
              const isError = isErrorLine(line);
              return (
                <div
                  key={idx}
                  className={`border-b border-l-[3px] p-4 active:bg-[#F8FAFC] ${
                    isError ? "border-l-red-400 border-b-red-50 bg-red-50/40" : "border-gray-50 bg-white"
                  }`}
                >
                  <div className="mb-1 flex items-center gap-2">
                    <span className={`font-mono text-[10px] ${isError ? "text-red-400" : "text-gray-400"}`}>{extractClock(line)}</span>
                    {isError ? (
                      <span className="rounded px-1 text-[9px] font-bold uppercase tracking-tighter border-l-red-400 bg-red-100 text-red-600">
                        ERROR
                      </span>
                    ) : (
                      <span className={`rounded px-1 text-[9px] font-bold uppercase tracking-tighter ${accentForKind(kind)}`}>
                        {labelForKind(kind)}
                      </span>
                    )}
                    <button className="ml-auto text-gray-300 transition-colors active:text-gray-500" onClick={() => void copyText(line)}>
                      <CopyIcon />
                    </button>
                  </div>
                  <p className={`break-all font-mono text-[12px] leading-[1.6] ${isError ? "font-semibold text-red-600" : "text-gray-700"}`}>
                    {highlightLine(line, filterText)}
                  </p>
                </div>
              );
            })}
            {!filtered.length ? <div className="px-1 py-6 text-center text-[12px] text-gray-300">（暂无日志）</div> : null}
          </div>
        </div>
      </div>
    </div>
  );
}
