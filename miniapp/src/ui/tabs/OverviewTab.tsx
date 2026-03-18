import React from "react";
import type { MiniappStatus } from "../types";
import { Card, Pill } from "../components";

export function OverviewTab({ status }: { status: MiniappStatus | null; onReload: () => void }) {
  if (!status) {
    return <div className="text-sm text-slate-600 dark:text-slate-300">加载中…</div>;
  }

  const coreCount = status.core_cache?.pending_count ?? "-";
  const dynCount = status.dynamic_memory?.count ?? "-";
  const nbCount = status.notebook?.count ?? "-";
  const r2ok = !!status.r2?.ok;

  return (
    <Card title="一眼状态">
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
          <div className="text-xs text-slate-500 dark:text-slate-400">核心缓存待审</div>
          <div className="mt-1 text-2xl font-semibold">{String(coreCount)}</div>
        </div>
        <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
          <div className="text-xs text-slate-500 dark:text-slate-400">动态记忆条数</div>
          <div className="mt-1 text-2xl font-semibold">{String(dynCount)}</div>
        </div>
        <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
          <div className="text-xs text-slate-500 dark:text-slate-400">小本本条数</div>
          <div className="mt-1 text-2xl font-semibold">{String(nbCount)}</div>
        </div>
        <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
          <div className="text-xs text-slate-500 dark:text-slate-400">R2</div>
          <div className="mt-2">{r2ok ? <Pill ok text="可读" /> : <Pill ok={false} text="异常" />}</div>
        </div>
      </div>
    </Card>
  );
}

