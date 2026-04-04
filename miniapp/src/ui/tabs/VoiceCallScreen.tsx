import React, { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch, buildApiAssetUrl, getPanelToken } from "../api";
import { Btn } from "../components";
import { getInitData, tgReady } from "../tg";
import { useToast } from "../toast";

type VoiceConfig = {
  displayName: string;
  subtitle: string;
  avatarVersion: number;
  useAvatarImage: boolean;
  avatarUrl: string;
  theme?: string;
};

type CallStatus = "connecting" | "ready" | "recording" | "recognizing" | "thinking" | "speaking" | "error";

const DEFAULT_CONFIG: VoiceConfig = {
  displayName: "渡",
  subtitle: "语音通话中",
  avatarVersion: 0,
  useAvatarImage: false,
  avatarUrl: "",
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

function toBase64(buffer: ArrayBuffer): string {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const part = bytes.subarray(i, Math.min(i + chunkSize, bytes.length));
    binary += String.fromCharCode(...part);
  }
  return window.btoa(binary);
}

export function VoiceCallScreen({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [status, setStatus] = useState<CallStatus>("connecting");
  const [statusText, setStatusText] = useState("正在接通...");
  const [callStartedAt] = useState(() => Date.now());
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [config, setConfig] = useState<VoiceConfig>(DEFAULT_CONFIG);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draftName, setDraftName] = useState(DEFAULT_CONFIG.displayName);
  const [draftSubtitle, setDraftSubtitle] = useState(DEFAULT_CONFIG.subtitle);
  const [useAvatarImage, setUseAvatarImage] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [speakerOn, setSpeakerOn] = useState(true);
  const [callId, setCallId] = useState(() => `call_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`);
  const [callStartedAtIso] = useState(() => new Date().toISOString());

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksCountRef = useRef(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mimeTypeRef = useRef("");
  const isClosingRef = useRef(false);
  const statusTextRef = useRef("正在接通...");

  const voiceSocketRef = useRef<WebSocket | null>(null);
  const streamSessionIdRef = useRef("");
  const sessionReadyResolverRef = useRef<((sessionId: string) => void) | null>(null);
  const sessionReadyRejectRef = useRef<((reason?: unknown) => void) | null>(null);

  const audioContextRef = useRef<AudioContext | null>(null);
  const nextPcmPlayTimeRef = useRef(0);
  const activePcmSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const streamAudioEndingRef = useRef(false);

  const avatarSrc = useMemo(() => {
    if (!config.useAvatarImage || !config.avatarUrl) return "";
    return buildApiAssetUrl(config.avatarUrl);
  }, [config.avatarUrl, config.useAvatarImage]);

  useEffect(() => {
    tgReady(true);
    let cancelled = false;

    async function bootstrap() {
      try {
        const resp = await apiFetch("/miniapp-api/voice-config");
        const data = await resp.json().catch(() => ({}));
        if (cancelled) return;
        if (!resp.ok || !data?.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
        const next: VoiceConfig = { ...DEFAULT_CONFIG, ...(data.config || {}) };
        setConfig(next);
        setDraftName(next.displayName || DEFAULT_CONFIG.displayName);
        setDraftSubtitle(next.subtitle || DEFAULT_CONFIG.subtitle);
        setUseAvatarImage(!!next.useAvatarImage);
        setStatus("ready");
        setStatusText("已接通，点一下接通");
      } catch (e: any) {
        setStatus("error");
        setStatusText(e?.message || "语音配置加载失败");
      }
    }

    bootstrap();
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

  useEffect(() => {
    statusTextRef.current = statusText;
  }, [statusText]);

  function cleanupMedia() {
    try {
      if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    } catch {}
    recorderRef.current = null;
    try {
      voiceSocketRef.current?.close();
    } catch {}
    voiceSocketRef.current = null;
    streamSessionIdRef.current = "";
    chunksCountRef.current = 0;
    try {
      audioRef.current?.pause();
      audioRef.current = null;
    } catch {}
    try {
      for (const source of activePcmSourcesRef.current) {
        try {
          source.stop();
        } catch {}
      }
    } catch {}
    activePcmSourcesRef.current = [];
    nextPcmPlayTimeRef.current = 0;
    streamAudioEndingRef.current = false;
    try {
      if (audioContextRef.current && audioContextRef.current.state !== "closed") {
        audioContextRef.current.close().catch(() => {});
      }
    } catch {}
    audioContextRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
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

  function buildVoiceSocketUrl(): string {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = new URL(`${proto}//${window.location.host}/miniapp-api/voice-call/ws`);
    const initData = getInitData();
    const panelToken = getPanelToken();
    if (initData) url.searchParams.set("initData", initData);
    if (panelToken) url.searchParams.set("panel_token", panelToken);
    return url.toString();
  }

  function ensureVoiceSocket(): Promise<WebSocket> {
    const existing = voiceSocketRef.current;
    if (existing && existing.readyState === WebSocket.OPEN) return Promise.resolve(existing);
    if (existing && existing.readyState === WebSocket.CONNECTING) {
      return new Promise((resolve, reject) => {
        const onOpen = () => {
          existing.removeEventListener("open", onOpen);
          existing.removeEventListener("error", onError);
          resolve(existing);
        };
        const onError = () => {
          existing.removeEventListener("open", onOpen);
          existing.removeEventListener("error", onError);
          reject(new Error("语音连接建立失败"));
        };
        existing.addEventListener("open", onOpen);
        existing.addEventListener("error", onError);
      });
    }
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(buildVoiceSocketUrl());
      voiceSocketRef.current = socket;
      socket.onopen = () => resolve(socket);
      socket.onerror = () => reject(new Error("语音连接建立失败"));
      socket.onclose = () => {
        if (voiceSocketRef.current === socket) voiceSocketRef.current = null;
        if (sessionReadyRejectRef.current) {
          sessionReadyRejectRef.current(new Error("语音连接已断开"));
          sessionReadyRejectRef.current = null;
          sessionReadyResolverRef.current = null;
        }
      };
      socket.onmessage = async (event) => {
        try {
          const msg = JSON.parse(String(event.data || "{}"));
          const type = String(msg?.type || "");
          if (type === "ready") {
            streamSessionIdRef.current = String(msg.session_id || "");
            if (msg.call_id) setCallId(String(msg.call_id));
            if (sessionReadyResolverRef.current) {
              sessionReadyResolverRef.current(streamSessionIdRef.current);
              sessionReadyResolverRef.current = null;
              sessionReadyRejectRef.current = null;
            }
            return;
          }
          if (type === "status") {
            const nextStatus = String(msg.status || "");
            if (nextStatus === "recording") setStatus("recording");
            else if (nextStatus === "recognizing") setStatus("recognizing");
            else if (nextStatus === "thinking") setStatus("thinking");
            else if (nextStatus === "speaking") setStatus("speaking");
            setStatusText(String(msg.text || statusTextRef.current || ""));
            return;
          }
          if (type === "transcript_partial") {
            const partial = String(msg.text || "").trim();
            if (partial) {
              setStatus("recording");
              setStatusText(`你在说：${partial}`);
            }
            return;
          }
          if (type === "audio_chunk") {
            setStatus("speaking");
            setStatusText("渡正在讲话...");
            playPcmChunk(String(msg.audio_b64 || ""), Number(msg.sample_rate || 32000), Number(msg.audio_channel || 1));
            return;
          }
          if (type === "audio_stream_end") {
            streamAudioEndingRef.current = true;
            if (activePcmSourcesRef.current.length === 0) {
              streamAudioEndingRef.current = false;
              setStatus("ready");
              setStatusText("已接通，点一下接通");
            }
            return;
          }
          if (type === "result") {
            streamSessionIdRef.current = "";
            chunksCountRef.current = 0;
            if (msg.call_id) setCallId(String(msg.call_id));
            if (msg.streamed_audio) {
              setStatus("speaking");
              setStatusText("渡正在讲话...");
            } else if (msg.audio_b64) {
              setStatus("speaking");
              setStatusText("渡正在讲话...");
              await playReplyAudio(String(msg.audio_b64 || ""), String(msg.audio_format || "mp3"));
            } else {
              setStatus("ready");
              setStatusText("已接通，点一下接通");
            }
            return;
          }
          if (type === "error") {
            throw new Error(String(msg.error || "语音连接异常"));
          }
        } catch (e: any) {
          setStatus("error");
          setStatusText(e?.message || "语音连接异常");
          toast(e?.message || "语音连接异常");
        }
      };
    });
  }

  async function startVoiceStreamSession(socket: WebSocket): Promise<string> {
    streamSessionIdRef.current = "";
    const readyPromise = new Promise<string>((resolve, reject) => {
      sessionReadyResolverRef.current = resolve;
      sessionReadyRejectRef.current = reject;
      window.setTimeout(() => {
        if (sessionReadyRejectRef.current === reject) {
          sessionReadyRejectRef.current = null;
          sessionReadyResolverRef.current = null;
          reject(new Error("语音会话建立超时"));
        }
      }, 4000);
    });
    socket.send(JSON.stringify({ type: "start", call_id: callId, call_started_at: callStartedAtIso }));
    return readyPromise;
  }

  function interruptPlayback() {
    try {
      audioRef.current?.pause();
    } catch {}
    audioRef.current = null;
    try {
      for (const source of activePcmSourcesRef.current) {
        try {
          source.stop();
        } catch {}
      }
    } catch {}
    activePcmSourcesRef.current = [];
    nextPcmPlayTimeRef.current = 0;
    streamAudioEndingRef.current = false;
  }

  function ensureAudioContext(): AudioContext {
    if (audioContextRef.current) return audioContextRef.current;
    const Ctor = window.AudioContext || (window as any).webkitAudioContext;
    const ctx = new Ctor();
    audioContextRef.current = ctx;
    nextPcmPlayTimeRef.current = ctx.currentTime;
    return ctx;
  }

  function playPcmChunk(audioB64: string, sampleRate: number, channelCount: number) {
    if (!speakerOn || !audioB64) return;
    const binary = window.atob(audioB64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    const ctx = ensureAudioContext();
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    const safeChannels = Math.max(1, channelCount || 1);
    const frameCount = Math.max(1, Math.floor(bytes.length / 2 / safeChannels));
    const audioBuffer = ctx.createBuffer(safeChannels, frameCount, sampleRate || 32000);
    const pcm = new DataView(bytes.buffer);
    for (let ch = 0; ch < safeChannels; ch += 1) {
      const channel = audioBuffer.getChannelData(ch);
      for (let i = 0; i < frameCount; i += 1) {
        const idx = (i * safeChannels + ch) * 2;
        channel[i] = Math.max(-1, Math.min(1, pcm.getInt16(idx, true) / 32768));
      }
    }
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    const startAt = Math.max(ctx.currentTime, nextPcmPlayTimeRef.current || ctx.currentTime);
    source.start(startAt);
    nextPcmPlayTimeRef.current = startAt + audioBuffer.duration;
    activePcmSourcesRef.current.push(source);
    source.onended = () => {
      activePcmSourcesRef.current = activePcmSourcesRef.current.filter((item) => item !== source);
      if (streamAudioEndingRef.current && activePcmSourcesRef.current.length === 0) {
        streamAudioEndingRef.current = false;
        setStatus("ready");
        setStatusText("已接通，点一下接通");
      }
    };
  }

  async function beginRecording() {
    if (status === "recognizing" || status === "connecting") return;
    try {
      interruptPlayback();
      const socket = await ensureVoiceSocket();
      await startVoiceStreamSession(socket);
      const stream = await ensureStream();
      chunksCountRef.current = 0;
      mimeTypeRef.current = resolveRecorderMimeType();
      const recorder = mimeTypeRef.current ? new MediaRecorder(stream, { mimeType: mimeTypeRef.current }) : new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksCountRef.current += 1;
          void sendVoiceChunk(event.data, event.data.type || mimeTypeRef.current || recorder.mimeType || "audio/webm");
        }
      };
      recorder.onstop = async () => {
        if (isClosingRef.current) {
          setStatus("ready");
          setStatusText("已接通，点一下接通");
          return;
        }
        await finishVoiceStream(mimeTypeRef.current || recorder.mimeType || "audio/webm");
      };
      recorder.start(350);
      setStatus("recording");
      setStatusText("正在听你说话...");
    } catch (e: any) {
      setStatus("error");
      setStatusText(e?.message || "麦克风打开失败");
    }
  }

  function stopRecording() {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    setStatus("recognizing");
    setStatusText("识别中...");
    recorder.stop();
  }

  async function sendVoiceChunk(blob: Blob, mimeType: string) {
    const socket = await ensureVoiceSocket();
    const sessionId = streamSessionIdRef.current;
    if (!sessionId || !blob || blob.size <= 0) return;
    const ext = mimeType.includes("mp4") ? "m4a" : mimeType.includes("ogg") ? "ogg" : mimeType.includes("mpeg") ? "mp3" : "webm";
    const buffer = await blob.arrayBuffer();
    socket.send(
      JSON.stringify({
        type: "audio_chunk",
        session_id: sessionId,
        mime_type: mimeType,
        filename: `voice-call.${ext}`,
        audio_b64: toBase64(buffer),
      }),
    );
  }

  async function finishVoiceStream(mimeType: string) {
    try {
      const socket = await ensureVoiceSocket();
      const sessionId = streamSessionIdRef.current;
      if (!sessionId || chunksCountRef.current <= 0) {
        setStatus("ready");
        setStatusText("已接通，点一下接通");
        return;
      }
      socket.send(
        JSON.stringify({
          type: "finish",
          session_id: sessionId,
          mime_type: mimeType,
          call_id: callId,
          call_started_at: callStartedAtIso,
        }),
      );
    } catch (e: any) {
      setStatus("error");
      setStatusText(e?.message || "语音请求失败");
      toast(e?.message || "语音请求失败");
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
        setStatusText("已接通，点一下接通");
        resolve();
      };
      audio.onerror = () => {
        setStatus("ready");
        setStatusText("已接通，点一下接通");
        resolve();
      };
      audio.play().catch(() => {
        setStatus("ready");
        setStatusText("语音已生成，点扬声器后再试");
        resolve();
      });
    });
  }

  async function saveVoiceConfig() {
    setSavingConfig(true);
    try {
      const body = {
        displayName: draftName,
        subtitle: draftSubtitle,
        useAvatarImage,
        avatarVersion: config.avatarVersion,
      };
      const resp = await apiFetch("/miniapp-api/voice-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data?.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
      const next: VoiceConfig = { ...DEFAULT_CONFIG, ...(data.config || {}) };
      setConfig(next);
      setDraftName(next.displayName);
      setDraftSubtitle(next.subtitle);
      setUseAvatarImage(!!next.useAvatarImage);
      setSettingsOpen(false);
      toast("通话头像已保存");
    } catch (e: any) {
      toast(e?.message || "保存失败");
    } finally {
      setSavingConfig(false);
    }
  }

  async function uploadAvatar(file: File | null) {
    if (!file) return;
    setUploadingAvatar(true);
    try {
      const form = new FormData();
      form.append("file", file, file.name || "voice-avatar.jpg");
      const resp = await apiFetch("/miniapp-api/voice-avatar", { method: "POST", body: form });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data?.ok) throw new Error(data?.error || `HTTP ${resp.status}`);
      setConfig((prev) => ({
        ...prev,
        avatarVersion: Number(data.avatarVersion || prev.avatarVersion || 0),
        avatarUrl: String(data.avatarUrl || prev.avatarUrl || ""),
        useAvatarImage: true,
      }));
      setUseAvatarImage(true);
      toast("头像已上传");
    } catch (e: any) {
      toast(e?.message || "头像上传失败");
    } finally {
      setUploadingAvatar(false);
    }
  }

  function endCall() {
    isClosingRef.current = true;
    try {
      const socket = voiceSocketRef.current;
      if (socket && socket.readyState === WebSocket.OPEN && streamSessionIdRef.current) {
        socket.send(JSON.stringify({ type: "cancel", session_id: streamSessionIdRef.current }));
      }
    } catch {}
    cleanupMedia();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-[80] overflow-hidden bg-[#111214] text-white voice-call-screen">
      <div className="relative z-10 flex min-h-dvh flex-col px-5 pb-8 pt-4 safe-bottom">
        <div className="text-center" style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 28px)" }}>
          <div className="text-[13px] text-white/72">{formatSeconds(elapsedSeconds)}</div>
        </div>

        <div className="mt-3 flex items-center justify-between">
          <button className="voice-call-top-btn bg-white/10" onClick={endCall} type="button">
            <span className="text-lg leading-none">×</span>
          </button>
          <button className="voice-call-top-btn bg-white/10" onClick={() => setSettingsOpen(true)} type="button">
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M12 3v3m0 12v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1m0-12.8-2.1 2.1M7.7 16.3l-2.1 2.1" />
            </svg>
          </button>
        </div>

        <div className="flex flex-1 flex-col items-center justify-center" style={{ paddingTop: "calc(env(safe-area-inset-top, 0px) + 44px)" }}>
          <div className="voice-call-avatar-wrap">
            {avatarSrc ? (
              <img src={avatarSrc} alt={config.displayName} className="h-full w-full object-cover" />
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
                if (status === "recording") stopRecording();
                else beginRecording();
              }}
              disabled={status === "recognizing" || status === "connecting"}
            >
              <div>
                <div className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-full bg-white/10">
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <path d="M12 4a3 3 0 0 1 3 3v5a3 3 0 1 1-6 0V7a3 3 0 0 1 3-3Z" />
                    <path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8" />
                  </svg>
                </div>
                {status === "recording" ? "点一下发送" : "点一下接通"}
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

      {settingsOpen ? (
        <div className="absolute inset-0 z-30 bg-black/35 backdrop-blur-[2px]">
          <div className="absolute inset-x-0 bottom-0 rounded-t-[32px] bg-[rgba(13,20,31,0.98)] px-5 pb-8 pt-5">
            <div className="flex items-center justify-between">
              <div className="text-base font-medium text-white">通话设置</div>
              <button className="voice-call-top-btn" type="button" onClick={() => setSettingsOpen(false)}>
                <span className="text-lg leading-none">×</span>
              </button>
            </div>
            <div className="mt-5 space-y-4">
              <label className="block">
                <div className="mb-2 text-xs text-white/55">显示名字</div>
                <input className="voice-call-input" value={draftName} onChange={(e) => setDraftName(e.target.value)} maxLength={24} />
              </label>
              <label className="block">
                <div className="mb-2 text-xs text-white/55">副标题</div>
                <input className="voice-call-input" value={draftSubtitle} onChange={(e) => setDraftSubtitle(e.target.value)} maxLength={40} />
              </label>
              <label className="flex items-center justify-between rounded-[22px] bg-white/6 px-4 py-3 text-sm text-white/85">
                <span>使用自定义头像</span>
                <input type="checkbox" checked={useAvatarImage} onChange={(e) => setUseAvatarImage(e.target.checked)} />
              </label>
              <label className="block rounded-[22px] bg-white/6 px-4 py-3 text-sm text-white/82">
                <div className="mb-2">上传头像</div>
                <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" disabled={uploadingAvatar} onChange={(e) => uploadAvatar(e.target.files?.[0] || null)} />
                <div className="mt-2 text-xs text-white/42">{uploadingAvatar ? "上传中..." : "支持 jpg/png/webp/gif，最大 8MB"}</div>
              </label>
              <div className="flex items-center gap-2 pt-1">
                <Btn kind="blue" onClick={() => setSettingsOpen(false)} disabled={savingConfig}>取消</Btn>
                <Btn kind="green" onClick={saveVoiceConfig} disabled={savingConfig}>{savingConfig ? "保存中..." : "保存"}</Btn>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
