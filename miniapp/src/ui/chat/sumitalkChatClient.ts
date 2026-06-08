import { ApiError, apiJson } from "../api";

export type SumiTalkChatJobCreateResponse = {
  ok?: boolean;
  job_id?: string;
  status?: string;
  response?: any;
  status_code?: number;
  error?: string;
};

export type SumiTalkChatJobStatusResponse = {
  ok?: boolean;
  status?: "queued" | "pending" | "running" | "done" | "error" | "cancelled";
  stage?: string;
  stage_elapsed_ms?: number;
  status_code?: number;
  response?: any;
  error?: string;
};

const SUMITALK_CHAT_JOB_POLL_MS = 1000;
const SUMITALK_CHAT_JOB_TIMEOUT_MS = 10 * 60 * 1000;

function makeAbortError(message = "已取消发送"): Error {
  if (typeof DOMException !== "undefined") return new DOMException(message, "AbortError");
  const error = new Error(message);
  error.name = "AbortError";
  return error;
}

function throwIfAborted(signal?: AbortSignal | null) {
  if (signal?.aborted) throw makeAbortError();
}

export function waitMs(ms: number, signal?: AbortSignal | null): Promise<void> {
  return new Promise((resolve, reject) => {
    try {
      throwIfAborted(signal);
    } catch (e) {
      reject(e);
      return;
    }
    const timer = window.setTimeout(() => {
      if (signal) signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      window.clearTimeout(timer);
      reject(makeAbortError());
    };
    if (signal) signal.addEventListener("abort", onAbort, { once: true });
  });
}

export async function apiJsonWithTimeout<T>(path: string, timeoutMs: number, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await apiJson<T>(path, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

export function isAbortLikeError(error: any): boolean {
  const name = String(error?.name || "").trim();
  const message = String(error?.message || error || "").toLowerCase();
  return name === "AbortError" || /abort|aborted|signal is aborted|timeout|timed out/.test(message);
}

export async function createSumiTalkChatJob(path: string, body: Record<string, any>, options: { signal?: AbortSignal | null } = {}): Promise<SumiTalkChatJobCreateResponse> {
  return apiJson<SumiTalkChatJobCreateResponse>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
    signal: options.signal || undefined,
  });
}

export async function cancelSumiTalkChatJob(jobId: string, reason = "client_cancelled"): Promise<void> {
  const jid = String(jobId || "").trim();
  if (!jid) return;
  await apiJson(`/miniapp-api/sumitalk-chat-jobs/${encodeURIComponent(jid)}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
}

export async function waitForSumiTalkChatJob(
  jobId: string,
  options: {
    signal?: AbortSignal | null;
    onStatus?: (job: SumiTalkChatJobStatusResponse) => void;
  } = {},
): Promise<any> {
  const jid = String(jobId || "").trim();
  if (!jid) throw new Error("缺少渡回复任务 ID");
  const startedAt = Date.now();
  let lastError = "";
  while (Date.now() - startedAt < SUMITALK_CHAT_JOB_TIMEOUT_MS) {
    throwIfAborted(options.signal);
    await waitMs(SUMITALK_CHAT_JOB_POLL_MS, options.signal);
    let job: SumiTalkChatJobStatusResponse;
    try {
      job = await apiJson<SumiTalkChatJobStatusResponse>(`/miniapp-api/sumitalk-chat-jobs/${encodeURIComponent(jid)}`, {
        signal: options.signal || undefined,
      });
    } catch (e: any) {
      if (isAbortLikeError(e)) throw e;
      lastError = String(e?.message || e);
      if (e instanceof ApiError && e.status === 404) {
        throw new Error(lastError || "任务不存在或已过期");
      }
      continue;
    }
    options.onStatus?.(job);
    if (job.status === "done") return job.response || {};
    if (job.status === "cancelled") throw makeAbortError(String(job.error || "已取消发送"));
    if (job.status === "error") {
      const upstreamError = job.response?.error || job.response?.message || "";
      throw new Error(String(job.error || upstreamError || "渡回复失败"));
    }
    if (job.response?.choices) return job.response;
    if (job.status && !["running", "queued", "pending"].includes(job.status)) {
      throw new Error("任务状态异常");
    }
  }
  throw new Error(lastError ? `等待渡回复超时：${lastError}` : "等待渡回复超时");
}
