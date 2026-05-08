import { useEffect, useState } from "react";
import { apiJson } from "./api";
import { useToast } from "./toast";

type DiagnosticStatus = "ok" | "warn" | "error";
type DiagnosticItem = {
  key: string;
  label: string;
  status: DiagnosticStatus;
  ok?: boolean;
  detail?: string;
  path?: string;
  latest_at?: string;
  bucket?: string;
};
type DiagnosticsResponse = {
  ok?: boolean;
  status?: DiagnosticStatus;
  generated_at?: string;
  items?: DiagnosticItem[];
};

function diagnosticStatusLabel(status?: DiagnosticStatus): string {
  if (status === "ok") return "正常";
  if (status === "warn") return "注意";
  return "异常";
}

function diagnosticStatusClass(status?: DiagnosticStatus): string {
  if (status === "ok") return "bg-emerald-50 text-emerald-600 border-emerald-100";
  if (status === "warn") return "bg-amber-50 text-amber-600 border-amber-100";
  return "bg-red-50 text-red-600 border-red-100";
}

export function DiagnosticsScreen() {
  const toast = useToast();
  const [data, setData] = useState<DiagnosticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load(showToast = false) {
    setLoading(true);
    setError("");
    try {
      const j = await apiJson<DiagnosticsResponse>("/miniapp-api/diagnostics");
      setData(j);
      if (showToast) toast("诊断完成");
    } catch (e: any) {
      const msg = e?.message || String(e);
      setError(msg);
      if (showToast) toast(`诊断失败：${msg}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load(false);
  }, []);

  const items = Array.isArray(data?.items) ? data.items : [];
  const errors = items.filter((it) => it.status === "error").length;
  const warns = items.filter((it) => it.status === "warn").length;
  const overall = data?.status || (errors ? "error" : warns ? "warn" : "ok");

  return (
    <div className="min-h-full bg-[#FDFDFD] px-4 pb-8 pt-4">
      <div className="mb-4 rounded-[28px] border border-gray-100 bg-white p-5 shadow-[0_10px_25px_-5px_rgba(0,0,0,0.04)]">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="text-[13px] font-bold uppercase tracking-[0.16em] text-gray-400">SumiTalk Health</div>
            <h2 className="mt-1 text-[22px] font-bold text-gray-900">
              {overall === "ok" ? "系统看起来正常" : overall === "warn" ? "有几项需要注意" : "有链路异常"}
            </h2>
            <p className="mt-1 text-[13px] leading-5 text-gray-400">
              {data?.generated_at ? `生成时间：${data.generated_at.replace("T", " ").replace("+08:00", "")}` : "进页自动检查一次，不常驻轮询。"}
            </p>
          </div>
          <span className={`rounded-full border px-3 py-1 text-[12px] font-bold ${diagnosticStatusClass(overall)}`}>
            {diagnosticStatusLabel(overall)}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-2xl bg-emerald-50 px-3 py-3">
            <div className="text-[18px] font-bold text-emerald-600">{items.filter((it) => it.status === "ok").length}</div>
            <div className="text-[11px] font-medium text-emerald-500">正常</div>
          </div>
          <div className="rounded-2xl bg-amber-50 px-3 py-3">
            <div className="text-[18px] font-bold text-amber-600">{warns}</div>
            <div className="text-[11px] font-medium text-amber-500">注意</div>
          </div>
          <div className="rounded-2xl bg-red-50 px-3 py-3">
            <div className="text-[18px] font-bold text-red-600">{errors}</div>
            <div className="text-[11px] font-medium text-red-500">异常</div>
          </div>
        </div>
        <button
          type="button"
          className="mt-4 w-full rounded-2xl bg-gray-900 px-4 py-3 text-[14px] font-bold text-white transition active:scale-[0.99] disabled:opacity-60"
          onClick={() => void load(true)}
          disabled={loading}
        >
          {loading ? "检查中..." : "重新检查"}
        </button>
      </div>

      {error ? (
        <div className="mb-4 rounded-[24px] border border-red-100 bg-red-50 px-4 py-3 text-[13px] leading-6 text-red-600">
          诊断接口失败：{error}
        </div>
      ) : null}

      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.key} className="rounded-[24px] border border-gray-100 bg-white p-4 shadow-[0_8px_22px_rgba(15,23,42,0.035)]">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-[15px] font-bold text-gray-800">{item.label}</div>
                <div className="mt-0.5 break-all text-[12px] leading-5 text-gray-400">{item.detail || "-"}</div>
              </div>
              <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-bold ${diagnosticStatusClass(item.status)}`}>
                {diagnosticStatusLabel(item.status)}
              </span>
            </div>
            {item.path ? <div className="mt-2 break-all rounded-2xl bg-gray-50 px-3 py-2 font-mono text-[11px] text-gray-400">{item.path}</div> : null}
          </div>
        ))}
      </div>

      {!loading && !error && !items.length ? (
        <div className="rounded-[24px] border border-gray-100 bg-white px-4 py-8 text-center text-[13px] text-gray-400">
          暂无诊断数据。
        </div>
      ) : null}
    </div>
  );
}
