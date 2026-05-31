import React, { useEffect, useRef, useState } from "react";
import { apiFetch } from "../api";
import { tgReady } from "../tg";
import { useToast } from "../toast";

type VoiceConfig = {
  displayName: string;
  subtitle: string;
  theme?: string;
};

type CallStatus = "connecting" | "ready" | "recording" | "recognizing" | "speaking" | "error";

const DEFAULT_CONFIG: VoiceConfig = {
  displayName: "渡",
  subtitle: "语音通话中",
  theme: "night",
};

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
  "audio/ogg",
];

function formatSeconds(total: number): string {
  const safe = Math.max(0, Math.floor(total || 0));
  const mm = String(Math.floor(safe / 60)).padStart(2, "0");
  const ss = String(safe % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function resolveRecorderMimeType(): string {
  if (typeof window === "undefined" || typeof window.MediaRecorder === "undefined") return "";
  const mediaRecorderCtor = window.MediaRecorder as typeof MediaRecorder;
  const supported = MIME_CANDIDATES.find((item) => {
    try {
      return typeof mediaRecorderCtor.isTypeSupported === "function" ? mediaRecorderCtor.isTypeSupported(item) : false;
    } catch {
      return false;
    }
  });
  return supported || "";
}

export function VoiceCallScreen({ onClose, duAvatarImage }: { onClose: () => void; duAvatarImage: string }) {
  const toast = useToast();
  const [status, setStatus] = useState<CallStatus>("connecting");
  const [statusText, setStatusText] = useState("正在接通...");
  const [callStartedAt] = useState(() => Date.now());
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [config, setConfig] = useState<VoiceConfig>(DEFAULT_CONFIG);
  const [speakerOn, setSpeakerOn] = useState(true);
  const [callId, setCallId] = useState(() => `call_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`);
  const [callStartedAtIso] = useState(() => new Date().toISOString());

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mimeTypeRef = useRef("");
  const isClosingRef = useRef(false);
  const actionBusyRef = useRef(false);
  const previewBusyRef = useRef(false);
  const previewTextRef = useRef("");
  const previewStampRef = useRef(0);

  useEffect(() => {
    tgReady(false);
    let cancelled = false;

    async function bootstrap() {
      try {
        const resp = await apiFetch("/miniapp-api/voice-config");
        const data = await resp.json().catch(() => ({}));
        if (cancelled) return;
        if (!resp.ok || !data?.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
        const next: VoiceConfig = {
          ...DEFAULT_CONFIG,
          ...(data.config || {}),
        };
        setConfig(next);
        setStatus("ready");
        setStatusText("已接通，点一下录音");
      } catch (e: any) {
        setStatus("error");
        setStatusText(e?.message || "语音配置加载失败");
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
      cleanupMedia();
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - callStartedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [callStartedAt]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.muted = !speakerOn;
  }, [speakerOn]);

  function cleanupMedia() {
    try {
      if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    } catch {}
    recorderRef.current = null;
    chunksRef.current = [];
    try {
      audioRef.current?.pause();
      audioRef.current = null;
    } catch {}
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    actionBusyRef.current = false;
    previewBusyRef.current = false;
    previewTextRef.current = "";
    previewStampRef.current = 0;
  }

  async function ensureStream(): Promise<MediaStream> {
    if (streamRef.current) return streamRef.current;
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("当前环境不支持麦克风录音");
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    streamRef.current = stream;
    return stream;
  }

  async function beginRecording() {
    if (status === "recording" || status === "recognizing" || status === "speaking" || actionBusyRef.current) return;
    actionBusyRef.current = true;
    try {
      try {
        audioRef.current?.pause();
      } catch {}
      audioRef.current = null;
      const stream = await ensureStream();
      chunksRef.current = [];
      mimeTypeRef.current = resolveRecorderMimeType();
      const recorder = mimeTypeRef.current ? new MediaRecorder(stream, { mimeType: mimeTypeRef.current }) : new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
          void triggerPreview(mimeTypeRef.current || recorder.mimeType || "audio/webm");
        }
      };
      recorder.onstop = () => {
      };
      previewTextRef.current = "";
      previewStampRef.current = 0;
      recorder.start(1200);
      actionBusyRef.current = false;
      setStatus("recording");
      setStatusText("正在听你说话...");
    } catch (e: any) {
      actionBusyRef.current = false;
      setStatus("error");
      setStatusText(e?.message || "麦克风打开失败");
    }
  }

  async function stopRecordingAndSend() {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive" || actionBusyRef.current) return;
    actionBusyRef.current = true;
    setStatus("recognizing");
    setStatusText("识别中...");
    recorder.stop();
    const mimeType = mimeTypeRef.current || recorder.mimeType || "audio/webm";
    previewBusyRef.current = false;
    const blob = await new Promise<Blob>((resolve) => {
      const finalize = () => {
        recorder.removeEventListener("stop", finalize);
        resolve(new Blob(chunksRef.current, { type: mimeType }));
      };
      recorder.addEventListener("stop", finalize);
    });
    chunksRef.current = [];
    if (blob.size <= 0 || isClosingRef.current) {
      actionBusyRef.current = false;
      setStatus("ready");
      setStatusText("已接通，点一下录音");
      return;
    }
    await sendVoice(blob, mimeType);
    actionBusyRef.current = false;
  }

  async function sendVoice(blob: Blob, mimeType: string) {
    try {
      const form = new FormData();
      const ext = mimeType.includes("mp4") ? "m4a" : mimeType.includes("ogg") ? "ogg" : mimeType.includes("mpeg") ? "mp3" : "webm";
      form.append("audio", blob, `voice-call.${ext}`);
      form.append("mime_type", mimeType);
      form.append("call_id", callId);
      form.append("call_started_at", callStartedAtIso);
      if (previewTextRef.current.trim()) form.append("user_text_override", previewTextRef.current.trim());
      const resp = await apiFetch("/miniapp-api/voice-call", { method: "POST", body: form });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data?.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
      if (data.call_id) setCallId(String(data.call_id));
      if (data.audio_b64) {
        setStatus("speaking");
        setStatusText("渡正在讲话...");
        await playReplyAudio(String(data.audio_b64 || ""), String(data.audio_format || "mp3"));
      } else {
        setStatus("ready");
        setStatusText("已接通，点一下录音");
      }
    } catch (e: any) {
      setStatus("error");
      setStatusText(e?.message || "语音请求失败");
      toast(e?.message || "语音请求失败");
    }
  }

  async function triggerPreview(mimeType: string) {
    if (previewBusyRef.current || status !== "recording") return;
    if (chunksRef.current.length < 2) return;
    const now = Date.now();
    if (now - previewStampRef.current < 2200) return;
    previewBusyRef.current = true;
    previewStampRef.current = now;
    try {
      const blob = new Blob(chunksRef.current, { type: mimeType || "audio/webm" });
      if (blob.size <= 0) return;
      const form = new FormData();
      const ext = mimeType.includes("mp4") ? "m4a" : mimeType.includes("ogg") ? "ogg" : mimeType.includes("mpeg") ? "mp3" : "webm";
      form.append("audio", blob, `voice-preview.${ext}`);
      form.append("mime_type", mimeType);
      const resp = await apiFetch("/miniapp-api/voice-call-preview", { method: "POST", body: form });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data?.ok) return;
      const text = String(data.text || "").trim();
      if (!text) return;
      previewTextRef.current = text;
      setStatusText(`你在说：${text}`);
    } catch {
    } finally {
      previewBusyRef.current = false;
    }
  }

  function playReplyAudio(audioB64: string, audioFormat: string): Promise<void> {
    return new Promise((resolve) => {
      try {
        audioRef.current?.pause();
      } catch {}
      const audio = new Audio(`data:audio/${audioFormat || "mp3"};base64,${audioB64}`);
      audioRef.current = audio;
      audio.muted = !speakerOn;
      audio.onended = () => {
        setStatus("ready");
        setStatusText("已接通，点一下录音");
        resolve();
      };
      audio.onerror = () => {
        setStatus("ready");
        setStatusText("已接通，点一下录音");
        resolve();
      };
      audio.play().catch(() => {
        setStatus("ready");
        setStatusText("语音已生成，点扬声器后再试");
        resolve();
      });
    });
  }

  function endCall() {
    isClosingRef.current = true;
    cleanupMedia();
    onClose();
  }

  return (
    <div className="overflow-hidden text-white voice-call-screen">
      <div className="relative z-10 flex min-h-[calc(100dvh-14rem)] flex-col bg-[#111214] px-5 pb-8 pt-5">
        <div className="flex items-center justify-end">
          <div className="text-[13px] text-white/72">{formatSeconds(elapsedSeconds)}</div>
        </div>

        <div className="flex flex-1 flex-col items-center justify-center pt-8">
          <div className="voice-call-avatar-wrap">
            {duAvatarImage ? (
              <img src={duAvatarImage} alt={config.displayName} className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center bg-[#2b2d31] text-[64px] font-semibold text-white">
                {(config.displayName || "渡").slice(0, 1)}
              </div>
            )}
          </div>

          <div className="mt-8 text-center">
            <div className="text-[34px] font-semibold tracking-[0.02em]">{config.displayName || "渡"}</div>
            <div className="mt-2 text-[15px] text-white/65">{config.subtitle || "语音通话中"}</div>
          </div>

          <div className="mt-8 flex items-center gap-2">
            <span className={`voice-call-dot ${status === "recording" ? "voice-call-dot-live" : ""}`} />
            <span className="text-sm text-white/74">{statusText}</span>
          </div>

          <div className="mt-8 flex items-end gap-2">
            {[0, 1, 2, 3, 4].map((idx) => (
              <span
                key={idx}
                className={"voice-call-wave " + (status === "recording" || status === "speaking" ? "voice-call-wave-active" : "")}
                style={{ animationDelay: `${idx * 0.12}s` }}
              />
            ))}
          </div>

          <div className="mt-10 flex items-center justify-center gap-8">
            <button type="button" className="flex flex-col items-center gap-2 text-xs text-white/72" onClick={() => setSpeakerOn((v) => !v)}>
              <span className={`voice-call-action-icon ${speakerOn ? "bg-[#d7e8ff] text-[#183a6f]" : ""}`}>
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M5 10h4l5-4v12l-5-4H5zM17 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11" />
                </svg>
              </span>
              <span>{speakerOn ? "扬声器" : "已静音"}</span>
            </button>

            <button
              type="button"
              className={
                "flex h-[112px] w-[112px] items-center justify-center rounded-full border border-white/10 text-center text-sm font-medium transition " +
                (status === "recording"
                  ? "bg-[#8fd4bf] text-[#0d2c25] shadow-[0_22px_44px_rgba(143,212,191,0.28)]"
                  : "bg-white/12 text-white shadow-[0_12px_28px_rgba(0,0,0,0.18)]")
              }
              onClick={() => {
                if (status === "recording") {
                  void stopRecordingAndSend();
                } else {
                  void beginRecording();
                }
              }}
              disabled={status === "recognizing" || actionBusyRef.current}
            >
              <div>
                <div className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-full bg-white/10">
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <path d="M12 4a3 3 0 0 1 3 3v5a3 3 0 1 1-6 0V7a3 3 0 0 1 3-3Z" />
                    <path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8" />
                  </svg>
                </div>
                {status === "recording" ? "点一下发送" : "点一下录音"}
              </div>
            </button>

            <button type="button" className="flex flex-col items-center gap-2 text-xs text-white/72" onClick={endCall}>
              <span className="voice-call-action-icon bg-[#ef6d63] text-white">
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M4 15c4-5 12-5 16 0M8 15l-2 4m10-4 2 4" />
                </svg>
              </span>
              <span>挂断</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
