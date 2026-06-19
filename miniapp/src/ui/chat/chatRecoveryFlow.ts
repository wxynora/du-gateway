import {
  applyAssistantTerminalMessage,
  applyMessageById,
  type ChatDraftMessage,
} from "../chatMessages";
import type { ChatOperation } from "./chatStore";
import {
  createSumiTalkChatJob,
  waitForSumiTalkChatJob,
  type SumiTalkChatJobStatusResponse,
} from "./sumitalkChatClient";
import {
  buildPrivateAssistantFailureMessage,
  buildPrivateAssistantTerminal,
} from "./privateChatSendFlow";
import {
  buildGroupAssistantFailureMessage,
  buildGroupAssistantTerminal,
} from "./groupChatSendFlow";

type ClientLogFields = Record<string, string | number | boolean | undefined | null>;
type ClientLogLevel = "info" | "warning" | "error";

type OperationVoiceOutput = {
  assistantId: string;
  clientRequestId: string;
  operationId: string;
  jobId: string;
  voiceText: string;
  localDeviceId: string;
};

function retryPayloadFor(operation: ChatOperation) {
  const retryPayload = operation.retryPayload && typeof operation.retryPayload === "object"
    ? operation.retryPayload
    : {};
  const path = String(retryPayload.path || "").trim();
  const body = retryPayload.body && typeof retryPayload.body === "object"
    ? retryPayload.body as Record<string, any>
    : null;
  if (!path || !body) throw new Error("缺少可恢复请求");
  return { path, body };
}

function isGroupChatPath(path: string) {
  return /sumitalk-chat-jobs/.test(String(path || ""));
}

function isMissingJobError(error: any) {
  const message = String(error?.message || error || "");
  return /不存在|过期|404/.test(message);
}

function errorText(error: any) {
  return String(error?.message || error || "发送失败");
}

export async function recoverSumiTalkOperationFlow(args: {
  operation: ChatOperation;
  localDeviceId: string;
  forceCreateJob?: boolean;
  getMessages: () => ChatDraftMessage[];
  persistMessages: (nextMessages: ChatDraftMessage[], localDeviceId: string) => Promise<void>;
  attachJob: (operationId: string, jobId: string) => Promise<void>;
  completeOperation: (operationId: string, assistantMessage: ChatDraftMessage) => Promise<void>;
  failOperation: (operationId: string, error: string, assistantMessage?: ChatDraftMessage) => Promise<void>;
  appendVoiceOutputAudio: (voiceOutput: OperationVoiceOutput) => void;
  logEvent?: (event: string, fields?: ClientLogFields, level?: ClientLogLevel) => void;
}): Promise<void> {
  const operation = args.operation;
  const opId = String(operation?.id || "").trim();
  const clientRequestId = String(operation?.clientRequestId || "").trim();
  const assistantId = String(operation?.assistantMessageId || "").trim();
  if (!opId || !clientRequestId) throw new Error("缺少可恢复任务");

  let jobId = args.forceCreateJob ? "" : String(operation.jobId || "").trim();
  const source = args.forceCreateJob ? "retry" : "recovery";

  const logFields = (fields: ClientLogFields = {}) => ({
    source,
    operationId: opId,
    clientRequestId,
    jobId,
    ...fields,
  });
  let lastLoggedJobStatusKey = "";
  const logJobStatus = (job: SumiTalkChatJobStatusResponse) => {
    const statusKey = `${job.status || ""}:${job.stage || ""}:${job.status_code || 0}`;
    if (statusKey === lastLoggedJobStatusKey) return;
    lastLoggedJobStatusKey = statusKey;
    args.logEvent?.("chat_job_status", logFields({
      status: String(job.status || ""),
      stage: String(job.stage || ""),
      stageElapsedMs: Number(job.stage_elapsed_ms || 0),
      statusCode: Number(job.status_code || 0),
    }));
  };

  try {
    if (!assistantId) throw new Error("缺少 pending 回复 ID");
    let completedData: any = null;
    const { path, body } = retryPayloadFor(operation);
    const groupPath = isGroupChatPath(path);

    args.logEvent?.("chat_recovery_start", logFields({
      forceCreateJob: Boolean(args.forceCreateJob),
      requestPath: path,
      operationStatus: operation.status,
    }));

    const createOrReuseJob = async () => {
      args.logEvent?.("chat_job_create_start", logFields({ requestPath: path }));
      const started = await createSumiTalkChatJob(path, body);
      if (started?.status === "error") {
        const upstreamError = started.response?.error || started.response?.message || "";
        throw new Error(String(started.error || upstreamError || "渡回复失败"));
      }
      jobId = String(started?.job_id || "").trim();
      args.logEvent?.("chat_job_create_ok", logFields({
        requestPath: path,
        status: String(started?.status || ""),
        mode: String((started as any)?.mode || ""),
      }));
      if (jobId) {
        await args.attachJob(opId, jobId);
        const current = args.getMessages().find((msg) => msg.id === assistantId);
        if (current) {
          const pendingWithJob = applyMessageById(args.getMessages(), assistantId, {
            ...current,
            role: "assistant",
            content: "",
            status: "pending",
            clientRequestId,
            operationId: opId,
            jobId,
          });
          await args.persistMessages(pendingWithJob, args.localDeviceId);
        }
      }
      if (String(started?.status || "").trim() === "done") {
        completedData = started?.response || started;
      }
    };

    if (jobId) {
      try {
        completedData = await waitForSumiTalkChatJob(jobId, {
          onStatus: logJobStatus,
        });
      } catch (e: any) {
        if (!isMissingJobError(e)) throw e;
        args.logEvent?.("chat_recovery_existing_job_missing", logFields({
          error: errorText(e),
        }), "warning");
        jobId = "";
      }
    }

    if (!completedData && !jobId) {
      await createOrReuseJob();
    }

    const data = completedData || (jobId ? await waitForSumiTalkChatJob(jobId, {
      onStatus: logJobStatus,
    }) : null);
    if (!data) throw new Error("任务没有返回内容");
    if (data?.error) {
      const err = typeof data.error === "string" ? data.error : data.error?.message || JSON.stringify(data.error);
      throw new Error(err || "上游返回错误");
    }

    const existing = args.getMessages().find((msg) => msg.id === assistantId);
    const terminal = groupPath
      ? buildGroupAssistantTerminal({
          data,
          assistantId,
          assistantCreatedAt: existing?.createdAt || operation.createdAt || new Date().toISOString(),
          clientRequestId,
          operationId: opId,
          jobId,
        })
      : buildPrivateAssistantTerminal({
          data,
          assistantId,
          assistantCreatedAt: existing?.createdAt || operation.createdAt || new Date().toISOString(),
          clientRequestId,
          operationId: opId,
          jobId,
        });

    await args.completeOperation(opId, terminal.assistantMessage);
    const finalMessages = applyAssistantTerminalMessage(args.getMessages(), clientRequestId, terminal.assistantMessage);
    await args.persistMessages(finalMessages, args.localDeviceId);
    args.logEvent?.("chat_recovery_done", logFields({
      replyChars: terminal.reply.length,
      voiceChars: terminal.voiceText.length,
      reasoningChars: terminal.reasoning.length,
      inputTokens: terminal.tokenCount?.input || 0,
      outputTokens: terminal.tokenCount?.output || 0,
      assistantAttachments: terminal.assistantAttachments.length,
    }));
    if (terminal.voiceText) {
      args.appendVoiceOutputAudio({
        assistantId,
        clientRequestId,
        operationId: opId,
        jobId,
        voiceText: terminal.voiceText,
        localDeviceId: args.localDeviceId,
      });
    }
  } catch (e: any) {
    const failedAssistantId = assistantId || `assistant-failed-${Date.now()}`;
    const existing = args.getMessages().find((msg) => msg.id === failedAssistantId);
    const { path } = (() => {
      try {
        return retryPayloadFor(operation);
      } catch {
        return { path: "" };
      }
    })();
    const failedMessage = isGroupChatPath(path)
      ? buildGroupAssistantFailureMessage({
          assistantId: failedAssistantId,
          assistantCreatedAt: existing?.createdAt || operation.createdAt || new Date().toISOString(),
          clientRequestId,
          operationId: opId,
          error: e,
        })
      : buildPrivateAssistantFailureMessage({
          assistantId: failedAssistantId,
          assistantCreatedAt: existing?.createdAt || operation.createdAt || new Date().toISOString(),
          clientRequestId,
          operationId: opId,
          cancelled: false,
          error: e,
        });
    await args.failOperation(opId, errorText(e), failedMessage);
    const failedMessages = applyAssistantTerminalMessage(args.getMessages(), clientRequestId, failedMessage);
    await args.persistMessages(failedMessages, args.localDeviceId);
    args.logEvent?.("chat_recovery_error", logFields({
      error: errorText(e),
    }), "error");
  }
}
