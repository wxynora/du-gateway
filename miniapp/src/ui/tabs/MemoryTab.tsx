import React, { useEffect, useMemo, useState } from "react";
import { apiJson } from "../api";
import { Btn, Card } from "../components";
import { useToast } from "../toast";
import type { CoreCacheEntry, CoreCacheResponse, NotebookEntry, NotebookResponse } from "../types";

export function MemoryTab() {
  const toast = useToast();
  const [core, setCore] = useState<CoreCacheResponse | null>(null);
  const [notebook, setNotebook] = useState<NotebookResponse | null>(null);
  const [nbText, setNbText] = useState("");

  async function reload() {
    try {
      const [c, n] = await Promise.all([
        apiJson<CoreCacheResponse>("/miniapp-api/core_cache"),
        apiJson<NotebookResponse>("/miniapp-api/notebook"),
      ]);
      setCore(c);
      setNotebook(n);
    } catch (e: any) {
      toast(`加载失败：${e?.message || e}`);
    }
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const coreItems = useMemo(() => (core?.pending || []).slice().reverse().slice(0, 30), [core]);
  const nbItems = useMemo(() => (notebook?.entries || []).slice().reverse().slice(0, 30), [notebook]);

  async function deleteCore(id: string) {
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/core_cache/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (!j.ok) throw new Error(j?.error || "删除失败");
      toast("已删除");
      await reload();
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    }
  }

  async function addNotebook() {
    const content = nbText.trim();
    if (!content) return toast("先写点内容");
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>("/miniapp-api/notebook", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!j.ok) throw new Error(j?.error || "写入失败");
      setNbText("");
      toast("已写入");
      await reload();
    } catch (e: any) {
      toast(`写入失败：${e?.message || e}`);
    }
  }

  async function deleteNotebook(ts: string) {
    try {
      const j = await apiJson<{ ok?: boolean; error?: string }>(`/miniapp-api/notebook/${encodeURIComponent(ts)}`, {
        method: "DELETE",
      });
      if (!j.ok) throw new Error(j?.error || "删除失败");
      toast("已删除");
      await reload();
    } catch (e: any) {
      toast(`删除失败：${e?.message || e}`);
    }
  }

  return (
    <div className="space-y-3">
      <Card title="核心缓存（待审）">
        <div className="text-sm">
          <div className="mb-2 text-slate-600 dark:text-slate-300">条数：{String(core?.count ?? "-")}</div>
          <div className="flex gap-2">
            <Btn onClick={reload}>刷新列表</Btn>
          </div>
          <div className="mt-3 space-y-2">
            {coreItems.map((it: CoreCacheEntry) => (
              <div key={it.id} className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
                <div className="text-xs text-slate-500 dark:text-slate-400">
                  {it.id || ""} · imp={String(it.importance ?? "")} · mention={String(it.mention_count ?? "")}
                </div>
                <div className="mt-1 whitespace-pre-wrap text-sm">{String(it.content || "")}</div>
                {it.id ? (
                  <div className="mt-2">
                    <Btn kind="danger" onClick={() => deleteCore(it.id!)}>
                      删除
                    </Btn>
                  </div>
                ) : null}
              </div>
            ))}
            {!coreItems.length ? <div className="text-xs text-slate-500">（暂无）</div> : null}
          </div>
        </div>
      </Card>

      <Card title="小本本">
        <div className="text-sm">
          <div className="mb-2 text-slate-600 dark:text-slate-300">条数：{String(notebook?.count ?? "-")}</div>
          <div className="flex gap-2">
            <input
              className="flex-1 rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-900/40"
              placeholder="新增一条…"
              value={nbText}
              onChange={(e) => setNbText(e.target.value)}
            />
            <Btn onClick={addNotebook}>添加</Btn>
          </div>
          <div className="mt-3 space-y-2">
            {nbItems.map((it: NotebookEntry) => (
              <div key={it.timestamp} className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
                <div className="text-xs text-slate-500 dark:text-slate-400">{String(it.timestamp || "")}</div>
                <div className="mt-1 whitespace-pre-wrap text-sm">{String(it.content || "")}</div>
                {it.timestamp ? (
                  <div className="mt-2">
                    <Btn kind="danger" onClick={() => deleteNotebook(it.timestamp!)}>
                      删除
                    </Btn>
                  </div>
                ) : null}
              </div>
            ))}
            {!nbItems.length ? <div className="text-xs text-slate-500">（暂无）</div> : null}
          </div>
        </div>
      </Card>
    </div>
  );
}

