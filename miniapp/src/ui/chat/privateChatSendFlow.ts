import {
  extractAssistantReasoning,
  extractAssistantReplyText,
  extractAssistantDisplayParts,
  extractTokenCount,
  type ChatAttachment,
  type ChatDraftMessage,
} from "../chatMessages";
import {
  attachSumiTalkJobEventsToResponse,
  createSumiTalkChatJob,
  waitForSumiTalkChatJob,
  type SumiTalkChatJobStatusResponse,
} from "./sumitalkChatClient";
import {
  extractAssistantAttachments,
  extractSumiTalkVoiceOutput,
  type PrivateModelContent,
} from "./privateChatHelpers";

type ClientLogFields = Record<string, string | number | boolean | undefined | null>;
type ClientLogLevel = "info" | "warning" | "error";

export type PrivateChatRequestBody = {
  model: string;
  messages: Array<{ role: "user"; content: PrivateModelContent }>;
  stream: false;
  window_id: string;
  reply_target: string;
  client_request_id: string;
  music_bgm_context?: any;
};

export type PrivateAssistantTerminal = {
  assistantMessage: ChatDraftMessage;
  reply: string;
  voiceText: string;
  reasoning: string;
  tokenCount?: ChatDraftMessage["tokenCount"];
  assistantAttachments: ChatAttachment[];
};

export type PrivateChatSendFlowResult = PrivateAssistantTerminal & {
  jobId: string;
};

export function buildPrivateChatRequestBody(args: {
  model: string;
  modelContent: PrivateModelContent;
  windowId: string;
  replyTarget: string;
  clientRequestId: string;
  musicBgmContext?: any;
}): PrivateChatRequestBody {
  return {
    model: args.model,
    messages: [{ role: "user", content: args.modelContent }],
    stream: false,
    window_id: args.windowId,
    ...(args.musicBgmContext ? { music_bgm_context: args.musicBgmContext } : {}),
    reply_target: args.replyTarget,
    client_request_id: args.clientRequestId,
  };
}

export function buildPrivateAssistantTerminal(args: {
  data: any;
  assistantId: string;
  assistantCreatedAt: string;
  clientRequestId: string;
  operationId: string;
  jobId?: string;
}): PrivateAssistantTerminal {
  const rawReply = extractAssistantReplyText(args.data);
  const voiceOutput = extractSumiTalkVoiceOutput(rawReply);
  const reply = voiceOutput.displayText || voiceOutput.voiceText || rawReply;
  if (!reply && !voiceOutput.voiceText) throw new Error("上游没有返回内容");
  const reasoning = extractAssistantReasoning(args.data);
  const tokenCount = extractTokenCount(args.data);
  const assistantAttachments = extractAssistantAttachments(args.data);
  const displayParts = extractAssistantDisplayParts(args.data);
  const assistantMessage: ChatDraftMessage = {
    id: args.assistantId,
    role: "assistant",
    content: reply,
    createdAt: args.assistantCreatedAt,
    status: "sent",
    clientRequestId: args.clientRequestId,
    operationId: args.operationId,
    jobId: args.jobId || undefined,
    reasoning: reasoning || undefined,
    tokenCount,
    ...(assistantAttachments.length ? { attachments: assistantAttachments } : {}),
    ...(displayParts.length ? { displayParts } : {}),
  };
  return {
    assistantMessage,
    reply,
    voiceText: voiceOutput.voiceText,
    reasoning,
    tokenCount,
    assistantAttachments,
  };
}

export function buildPrivateAssistantFailureMessage(args: {
  assistantId: string;
  assistantCreatedAt: string;
  clientRequestId: string;
  operationId: string;
  cancelled: boolean;
  error: any;
}): ChatDraftMessage {
  return {
    id: args.assistantId,
    role: "assistant",
    content: args.cancelled ? "（已取消发送）" : `（发送失败：${args.error?.message || args.error}）`,
    createdAt: args.assistantCreatedAt,
    status: "failed",
    clientRequestId: args.clientRequestId,
    operationId: args.operationId,
  };
}

export async function runPrivateChatSendFlow(args: {
  source: string;
  requestPath: string;
  requestBody: Record<string, any>;
  attemptId: string;
  clientRequestId: string;
  operationId: string;
  assistantId: string;
  assistantCreatedAt: string;
  abortSignal?: AbortSignal | null;
  logEvent: (event: string, fields?: ClientLogFields, level?: ClientLogLevel) => void;
  skipStaleAttemptUpdate: (stage: string) => boolean;
  onJobId?: (jobId: string) => Promise<void>;
  onEvent?: (event: any) => void | Promise<void>;
}): Promise<PrivateChatSendFlowResult | null> {
  let lastJobStatusKey = "";
  args.logEvent("chat_job_create_start", {
    source: args.source,
    requestPath: args.requestPath,
    attemptId: args.attemptId,
    clientRequestId: args.clientRequestId,
    operationId: args.operationId,
  });
  const started = await createSumiTalkChatJob(args.requestPath, args.requestBody, { signal: args.abortSignal });
  if (args.skipStaleAttemptUpdate("job_create_return")) return null;
  if (started?.status === "error") {
    const upstreamError = started.response?.error || started.response?.message || "";
    throw new Error(String(started.error || upstreamError || "渡回复失败"));
  }
  const jobId = String(started?.job_id || "").trim();
  args.logEvent("chat_job_create_ok", {
    source: args.source,
    requestPath: args.requestPath,
    attemptId: args.attemptId,
    clientRequestId: args.clientRequestId,
    operationId: args.operationId,
    jobId,
    status: String(started?.status || ""),
    mode: String((started as any)?.mode || ""),
  });
  if (jobId) await args.onJobId?.(jobId);
  const startedStatus = String(started?.status || "").trim();
  const data = startedStatus === "done"
    ? attachSumiTalkJobEventsToResponse(started?.response || started, (started as any)?.events)
    : jobId
      ? await waitForSumiTalkChatJob(jobId, {
        signal: args.abortSignal,
        onEvent: args.onEvent,
        onStatus: (job: SumiTalkChatJobStatusResponse) => {
          const statusKey = `${job.status || ""}:${job.stage || ""}`;
          if (statusKey === lastJobStatusKey) return;
          lastJobStatusKey = statusKey;
          args.logEvent("chat_job_status", {
            source: args.source,
            attemptId: args.attemptId,
            clientRequestId: args.clientRequestId,
            operationId: args.operationId,
            jobId,
            status: String(job.status || ""),
            stage: String(job.stage || ""),
            stageElapsedMs: Number(job.stage_elapsed_ms || 0),
            statusCode: Number(job.status_code || 0),
          });
        },
      })
    : started?.response || started;
  if (data?.error) {
    const err = typeof data.error === "string" ? data.error : data.error?.message || JSON.stringify(data.error);
    throw new Error(err || "上游返回错误");
  }
  if (args.skipStaleAttemptUpdate("job_done")) return null;
  const terminal = buildPrivateAssistantTerminal({
    data,
    assistantId: args.assistantId,
    assistantCreatedAt: args.assistantCreatedAt,
    clientRequestId: args.clientRequestId,
    operationId: args.operationId,
    jobId,
  });
  args.logEvent("chat_reply_ready", {
    source: args.source,
    attemptId: args.attemptId,
    clientRequestId: args.clientRequestId,
    operationId: args.operationId,
    jobId,
    replyChars: terminal.reply.length,
    voiceChars: terminal.voiceText.length,
    reasoningChars: terminal.reasoning.length,
    inputTokens: terminal.tokenCount?.input || 0,
    outputTokens: terminal.tokenCount?.output || 0,
    assistantAttachments: terminal.assistantAttachments.length,
  });
  return {
    ...terminal,
    jobId,
  };
}
