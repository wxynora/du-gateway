type StageFields = Record<string, string | number | boolean | undefined | null>;

export function resolveChatSendStageLabel(event: string, fields: StageFields = {}): string {
  const name = String(event || "").trim();
  const stage = String(fields.stage || "").trim();
  const status = String(fields.status || "").trim();
  if (name === "chat_send_start") return "准备发送";
  if (name === "chat_job_create_start") return "提交给后端";
  if (name === "chat_job_create_ok") {
    return String(fields.jobId || "").trim() ? "任务已创建，等渡回复" : "渡正在整理回复";
  }
  if (name === "chat_job_status") {
    if (/upstream|gateway_call|chat_call|forward/i.test(stage)) return "正在请求上游";
    if (/thinking|reasoning/i.test(stage)) return "渡在想";
    if (/post|request/i.test(stage)) return "正在请求上游";
    if (/return|done|complete/i.test(stage)) return "上游已返回";
    if (status === "queued" || status === "pending") return "排队中";
    if (status === "running") return "任务运行中";
    return stage ? `任务阶段：${stage}` : "任务运行中";
  }
  if (name === "chat_reply_ready") return "正在写入回复";
  if (name === "assistant_voice_tts_start") return "正在生成语音";
  if (name === "chat_cancel_click" || name === "chat_cancel_post_ok") return "正在取消";
  if (name === "chat_send_cancelled") return "已取消";
  if (name === "chat_send_error") return "发送失败";
  return "";
}
