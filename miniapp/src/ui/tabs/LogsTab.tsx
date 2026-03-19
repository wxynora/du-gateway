import React, { useEffect, useMemo, useRef, useState } from "react";
import { apiJson, buildLogStreamUrl } from "../api";
import { Btn } from "../components";
import { useToast } from "../toast";

type LogsResp = { ok?: boolean; lines?: string[]; error?: string };

export function LogsTab() {
  const toast = useToast();
  const [paused, setPaused] = useState(false);
  const [lines, setLines] = useState<string[]>([]);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const [filterText, setFilterText] = useState("");
  const [loadError, setLoadError] = useState("");

  const filtered = useMemo(() => {
    const k = (filterText || "").trim().toLowerCase();
    if (!k) return lines;
    return (lines || []).filter((l) => (l || "").toLowerCase().includes(k));
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

  async function loadTail() {
    try {
      const j = await apiJson<LogsResp>("/miniapp-api/logs?lines=200");
      setLines(j.lines || []);
      setLoadError("");
      toast("已加载最新日志");
    } catch (e: any) {
      setLoadError(e?.message || String(e));
      toast(`加载失败：${e?.message || e}`);
    }
  }

  function connect() {
    if (esRef.current) return;
    const es = new EventSource(buildLogStreamUrl(80));
    esRef.current = es;
    setConnected(true);
    es.onmessage = (ev) => {
      if (paused) return;
      setLines((prev) => {
        const next = [...prev, ev.data];
        if (next.length > 2000) next.splice(0, next.length - 2000);
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

  function disconnect() {
    if (!esRef.current) return;
    try {
      esRef.current.close();
    } catch {}
    esRef.current = null;
    setConnected(false);
    toast("已断开实时");
  }

  useEffect(() => {
    return () => disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Btn kind="blue" onClick={loadTail}>拉取末尾 200 行</Btn>
        <Btn
          kind="green"
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
        <div className="rounded-xl2 bg-cream-pink/65 px-3 py-2 text-xs text-cream-text shadow-soft2">
          接口加载失败：{loadError}
          <br />
          若在 Telegram 里半屏空白，通常是 initData 校验失败或反代吞头。
        </div>
      ) : null}

      <div className="rounded-xl3 bg-cream-blue/45 shadow-soft p-3 space-y-2">
        <div className="flex items-center gap-2">
          <input
            className="flex-1 rounded-xl2 bg-cream-card px-3 py-2 text-sm shadow-soft2"
            placeholder="过滤关键字（不区分大小写）"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
          />
          <Btn kind="green"
            onClick={() => {
              setFilterText("");
              toast("已清空过滤");
            }}
            disabled={!filterText.trim()}
          >
            清空
          </Btn>
          <Btn kind="pink"
            onClick={() => {
              const k = (filterText || "").trim();
              const text = (filtered || []).slice(-200).join("\n") || "";
              if (!text) return toast("暂无可复制内容");
              void copyText(text);
            }}
            disabled={filtered.length === 0}
          >
            一键复制
          </Btn>
        </div>

        <div className="min-h-[50vh] rounded-2xl bg-[#1F1A12] p-3 font-mono text-xs leading-relaxed text-[#FFF7E6] overflow-auto shadow-soft2">
          {(filtered || []).slice(-800).map((l, idx) => (
            <div key={idx} className="whitespace-pre-wrap">
              {highlightLine(l, filterText)}
            </div>
          ))}
          {!filtered.length ? <div>（暂无日志）</div> : null}
        </div>
      </div>
    </div>
  );
}

