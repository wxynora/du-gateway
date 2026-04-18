import React, { useEffect, useMemo, useRef, useState } from "react";
import { apiJson, buildLogStreamUrl } from "../api";
import { Btn } from "../components";
import { useToast } from "../toast";

type LogsResp = { ok?: boolean; lines?: string[]; error?: string };

type LogCategory = "all" | "proactive" | "wechat" | "tgbot" | "qq";

const LOG_CATEGORY_OPTIONS: Array<{ value: LogCategory; label: string }> = [
  { value: "all", label: "网关总日志" },
  { value: "proactive", label: "主动信息日志" },
  { value: "wechat", label: "微信连接器日志" },
  { value: "tgbot", label: "TGBot 日志" },
  { value: "qq", label: "QQ 连接器日志" },
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

  function lineKind(line: string): LogCategory | "other" {
    const raw = String(line || "");
    if (raw.includes("[TGPro]") || raw.includes("主动发消息")) return "proactive";
    if (raw.includes("[wechat-ilink]")) return "wechat";
    if (raw.includes("[TGBot]")) return "tgbot";
    if (raw.includes("[qq-onebot]")) return "qq";
    return "other";
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
        <span key={`${idx}-${hit.length}`} className="rounded bg-cream-accent/25 px-0.5 text-cream-text">
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
      // fallback: textarea
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
      // 降序展示：最新在最上
      setLines((j.lines || []).slice().reverse());
      setLoadError("");
      if (!silent) toast("已加载最新日志");
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
      setLines((prev) => {
        // 实时日志也保持“最新在最上”
        const next = [ev.data, ...prev];
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
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Btn kind="blue" onClick={loadTail}>拉取末尾 200 行</Btn>
        <Btn
          kind="yellow"
          onClick={() => {
            setPaused((p) => !p);
            toast(!paused ? "已暂停" : "已继续");
          }}
        >
          {paused ? "继续" : "暂停"}
        </Btn>
        <Btn kind="pink" onClick={() => (connected ? disconnect() : connect())}>{connected ? "断开实时" : "连接实时"}</Btn>
      </div>

      {loadError ? (
        <div className="neo-muted-box bg-[linear-gradient(145deg,rgba(251,230,236,0.95),rgba(236,206,221,0.82))]">
          接口加载失败：{loadError}
          <br />
          若在 Telegram 里半屏空白，通常是 initData 校验失败或反代吞头。
        </div>
      ) : null}

      <div className="neo-panel p-3 space-y-2">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <select
            className="neo-input w-full sm:w-52"
            value={filterKind}
            onChange={(e) => setFilterKind(e.target.value as LogCategory)}
          >
            {LOG_CATEGORY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <input
            className="neo-input flex-1"
            placeholder="过滤关键字（不区分大小写）"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-2">
          <Btn kind="yellow"
            onClick={() => {
              setFilterText("");
              setFilterKind("all");
              toast("已清空过滤");
            }}
            disabled={!filterText.trim() && filterKind === "all"}
          >
            清空
          </Btn>
          <Btn kind="pink"
            onClick={() => {
              const k = (filterText || "").trim();
              const text = (filtered || []).slice(0, 200).join("\n") || "";
              if (!text) return toast("暂无可复制内容");
              void copyText(text);
            }}
            disabled={filtered.length === 0}
          >
            一键复制
          </Btn>
        </div>

        <div className="neo-console">
          {(filtered || []).slice(0, 800).map((l, idx) => {
            const kind = lineKind(l);
            const lineClass =
              kind === "proactive"
                ? "neo-line-proactive"
                : "";
            return (
            <div key={idx} className={`whitespace-pre-wrap ${lineClass}`}>
              {highlightLine(l, filterText)}
            </div>
          )})}
          {!filtered.length ? <div>（暂无日志）</div> : null}
        </div>
      </div>
    </div>
  );
}

