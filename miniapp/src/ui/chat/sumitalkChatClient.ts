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
  status?: "queued" | "pending" | "running" | "done" | "error";
  status_code?: number;
  response?: any;
  error?: string;
};

const SUMITALK_CHAT_JOB_POLL_MS = 1000;
const SUMITALK_CHAT_JOB_TIMEOUT_MS = 10 * 60 * 1000;

export function waitMs(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
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

export async function createSumiTalkChatJob(path: string, body: Record<string, any>): Promise<SumiTalkChatJobCreateResponse> {
  return apiJson<SumiTalkChatJobCreateResponse>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

export async function waitForSumiTalkChatJob(jobId: string): Promise<any> {
  const jid = String(jobId || "").trim();
  if (!jid) throw new Error("缺少渡回复任务 ID");
  const startedAt = Date.now();
  let lastError = "";
  while (Date.now() - startedAt < SUMITALK_CHAT_JOB_TIMEOUT_MS) {
    await waitMs(SUMITALK_CHAT_JOB_POLL_MS);
    let job: SumiTalkChatJobStatusResponse;
    try {
      job = await apiJson<SumiTalkChatJobStatusResponse>(`/miniapp-api/sumitalk-chat-jobs/${encodeURIComponent(jid)}`);
    } catch (e: any) {
      lastError = String(e?.message || e);
      if (e instanceof ApiError && e.status === 404) {
        throw new Error(lastError || "任务不存在或已过期");
      }
      continue;
    }
    if (job.status === "done") return job.response || {};
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
