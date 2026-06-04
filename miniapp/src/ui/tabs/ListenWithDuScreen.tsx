import { useEffect, useMemo, useRef, useState } from "react";
import { apiJson, buildApiAssetUrl, getOrCreatePanelDeviceId } from "../api";
import { ChevronLeftIcon, ClockIconMini, SendIconMini } from "../icons";

type ListenMessage = {
  id: number;
  role: "du" | "user";
  text: string;
  pending?: boolean;
};

type MusicSegment = {
  start?: number;
  end?: number;
  section?: string;
  plain?: string;
  melody_motion?: string;
  sonic_detail?: string;
  intensity?: string;
  valence?: number;
  arousal?: number;
};

type LyricLine = {
  time?: number;
  text?: string;
};

type LyricsPayload = {
  lines?: LyricLine[];
  plain_lines?: string[];
  synced?: boolean;
  estimated?: boolean;
};

type MusicEntry = {
  id?: string;
  title?: string;
  artist?: string;
  audio_url?: string;
  audio_format?: string;
  duration_seconds?: number;
  melody_text?: string;
  overall_trend?: string;
  lyrics?: LyricsPayload | LyricLine[];
  updated_at?: string;
  structured?: {
    segments?: MusicSegment[];
  };
};

type RecentResp = {
  ok?: boolean;
  items?: MusicEntry[];
};

type ListenChatResp = {
  ok?: boolean;
  du_reply?: string;
  error?: string;
  window_id?: string;
};

function asSeconds(value: unknown): number {
  const n = Number(value || 0);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

function formatClock(seconds: number): string {
  const total = Math.max(0, Math.round(seconds || 0));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

function segmentsFor(entry?: MusicEntry): MusicSegment[] {
  const list = entry?.structured?.segments;
  return Array.isArray(list) ? list.filter((item) => asSeconds(item?.end) > asSeconds(item?.start)) : [];
}

function durationFor(entry?: MusicEntry): number {
  const explicit = asSeconds(entry?.duration_seconds);
  if (explicit > 0) return explicit;
  return segmentsFor(entry).reduce((max, item) => Math.max(max, asSeconds(item.end)), 0);
}

function currentSegmentFor(entry: MusicEntry | undefined, currentTime: number): MusicSegment | null {
  const segments = segmentsFor(entry);
  if (!segments.length) return null;
  const t = Math.max(0, currentTime || 0);
  return (
    segments.find((item) => {
      const start = asSeconds(item.start);
      const end = asSeconds(item.end);
      return t >= start && t < end;
    }) || segments[segments.length - 1] || null
  );
}

function lyricsPayloadFor(entry?: MusicEntry): LyricsPayload {
  const raw = entry?.lyrics;
  if (Array.isArray(raw)) return { lines: raw, plain_lines: [], synced: raw.length > 0 };
  return raw && typeof raw === "object" ? raw : {};
}

function lyricLinesFor(entry?: MusicEntry): LyricLine[] {
  const lines = lyricsPayloadFor(entry).lines;
  if (!Array.isArray(lines)) return [];
  return lines
    .map((item) => ({ time: asSeconds(item?.time), text: String(item?.text || "").trim() }))
    .filter((item) => item.text)
    .sort((a, b) => asSeconds(a.time) - asSeconds(b.time));
}

function plainLyricsFor(entry?: MusicEntry): string[] {
  const lines = lyricsPayloadFor(entry).plain_lines;
  return Array.isArray(lines) ? lines.map((item) => String(item || "").trim()).filter(Boolean) : [];
}

function currentLyricIndex(lines: LyricLine[], currentTime: number): number {
  if (!lines.length) return -1;
  const t = Math.max(0, currentTime || 0);
  let current = 0;
  for (let i = 0; i < lines.length; i += 1) {
    if (asSeconds(lines[i]?.time) <= t + 0.15) current = i;
    else break;
  }
  return current;
}

export function ListenWithDuScreen({ onBack, backgroundImage }: { onBack: () => void; backgroundImage?: string }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const sendSeqRef = useRef(0);
  const [songs, setSongs] = useState<MusicEntry[]>([]);
  const [songIndex, setSongIndex] = useState(0);
  const [messages, setMessages] = useState<ListenMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [sending, setSending] = useState(false);

  const song = songs[songIndex];
  const songDuration = duration || durationFor(song);
  const progress = songDuration > 0 ? Math.min(100, Math.max(0, (currentTime / songDuration) * 100)) : 0;
  const currentSegment = useMemo(() => currentSegmentFor(song, currentTime), [song, currentTime]);
  const audioSrc = song?.audio_url ? buildApiAssetUrl(song.audio_url) : "";
  const lyricLines = useMemo(() => lyricLinesFor(song), [song]);
  const plainLyrics = useMemo(() => plainLyricsFor(song), [song]);
  const activeLyricIndex = useMemo(() => currentLyricIndex(lyricLines, currentTime), [lyricLines, currentTime]);
  const visibleLyrics = useMemo(() => {
    if (lyricLines.length) {
      const active = activeLyricIndex >= 0 ? activeLyricIndex : 0;
      const start = Math.max(0, active - 2);
      return lyricLines.slice(start, start + 5).map((line, offset) => ({ text: line.text || "", active: start + offset === active }));
    }
    return plainLyrics.slice(0, 5).map((text, index) => ({ text, active: index === 0 }));
  }, [activeLyricIndex, lyricLines, plainLyrics]);

  const historyItems = useMemo(
    () => songs.map((item, index) => ({ ...item, active: index === songIndex, durationLabel: formatClock(durationFor(item)) })),
    [songs, songIndex],
  );

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    apiJson<RecentResp>("/api/music/listen/recent?limit=50")
      .then((data) => {
        if (!alive) return;
        const items = (Array.isArray(data?.items) ? data.items : [])
          .filter((item) => String(item?.title || "").trim())
          .sort((a, b) => String(a.title || "").localeCompare(String(b.title || ""), "zh-Hans"));
        setSongs(items);
        setSongIndex(0);
        setMessages([]);
      })
      .catch((e) => {
        if (!alive) return;
        setError(`加载失败：${String(e?.message || e || "")}`);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const audio = audioRef.current;
    setCurrentTime(0);
    setDuration(durationFor(song));
    setIsPlaying(false);
    if (audio) {
      audio.pause();
      audio.load();
    }
  }, [song?.id]);

  function switchSong(nextIndex = songs.length ? (songIndex + 1) % songs.length : 0) {
    if (!songs.length) return;
    sendSeqRef.current += 1;
    setSongIndex(nextIndex);
    setShowHistory(false);
    setSending(false);
    setMessages([]);
  }

  async function togglePlay() {
    const audio = audioRef.current;
    if (!audio || !audioSrc) return;
    if (!audio.paused) {
      audio.pause();
      setIsPlaying(false);
      return;
    }
    try {
      await audio.play();
      setIsPlaying(true);
    } catch {
      setIsPlaying(false);
    }
  }

  async function sendMessage() {
    const text = draft.trim();
    if (!text || !song || sending) return;
    const now = Date.now();
    const requestSeq = sendSeqRef.current + 1;
    const placeholderId = now + 1;
    const recentMessages = messages.slice(-8).map((message) => ({
      role: message.role === "du" ? "assistant" : "user",
      content: message.text,
    }));
    sendSeqRef.current = requestSeq;
    setMessages((prev) => [...prev, { id: now, role: "user", text }, { id: placeholderId, role: "du", text: "……", pending: true }]);
    setDraft("");
    setSending(true);
    try {
      const deviceId = await getOrCreatePanelDeviceId().catch(() => "");
      const data = await apiJson<ListenChatResp>("/api/music/listen/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          entry_id: song.id,
          title: song.title,
          artist: song.artist,
          current_time: currentTime,
          duration_seconds: songDuration,
          segment: currentSegment,
          message: text,
          recent_messages: recentMessages,
          window_id: deviceId ? `music_listen_${deviceId}` : "music_listen",
        }),
      });
      const reply = String(data?.du_reply || "").trim();
      if (!reply) throw new Error(data?.error || "渡没有返回内容");
      setMessages((prev) => prev.map((item) => (item.id === placeholderId ? { ...item, text: reply, pending: false } : item)));
    } catch {
      setMessages((prev) =>
        prev.map((item) =>
          item.id === placeholderId
            ? {
                ...item,
                text: "我刚刚没接上这一句，再发我一次。",
                pending: false,
              }
            : item,
        ),
      );
    } finally {
      if (sendSeqRef.current === requestSeq) setSending(false);
    }
  }

  return (
    <div className="absolute inset-0 z-30 flex h-dvh w-full flex-col overflow-hidden bg-[#9ebadc] text-white">
      {backgroundImage ? (
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: `url(${backgroundImage})` }}
        />
      ) : (
        <div className="absolute inset-0 bg-[linear-gradient(180deg,#6a9bd1_0%,#9ebadc_48%,#e8d7e1_100%)]" />
      )}
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(37,58,85,0.18)_0%,rgba(62,78,108,0.10)_42%,rgba(232,215,225,0.58)_100%)]" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_15%,rgba(255,255,255,0.45),transparent_30%),radial-gradient(circle_at_82%_74%,rgba(255,210,226,0.46),transparent_32%),linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0))] mix-blend-overlay" />

      {audioSrc ? (
        <audio
          ref={audioRef}
          src={audioSrc}
          preload="metadata"
          onLoadedMetadata={(e) => setDuration(asSeconds(e.currentTarget.duration) || durationFor(song))}
          onTimeUpdate={(e) => setCurrentTime(asSeconds(e.currentTarget.currentTime))}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onEnded={() => setIsPlaying(false)}
        />
      ) : null}

      <header className="relative z-10 border-b border-white/35 px-6 pb-8 pt-[calc(env(safe-area-inset-top,0px)+18px)]">
        <div className="mb-7 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="flex h-9 w-9 items-center justify-center rounded-full bg-white/16 text-white backdrop-blur-md transition active:bg-white/25"
              onClick={onBack}
              aria-label="返回"
            >
              <ChevronLeftIcon />
            </button>
            <div className="flex h-8 items-center gap-2 rounded-full border border-white/20 bg-white/18 px-3 text-[12px] font-medium shadow-[0_6px_20px_rgba(255,255,255,0.08)] backdrop-blur-md">
              <span className={`h-2 w-2 rounded-full ${audioSrc ? "bg-[#a8ff78]" : "bg-white/55"} shadow-[0_0_10px_rgba(168,255,120,0.75)]`} />
              <span>{audioSrc ? "渡 正在听" : "渡 准备就绪"}</span>
            </div>
          </div>
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-white/12 text-white backdrop-blur-md transition active:bg-white/25"
            onClick={() => setShowHistory((prev) => !prev)}
            aria-label="听歌记录"
          >
            <ClockIconMini />
          </button>
        </div>

        <h1 className="font-['Playfair_Display','Noto_Serif_SC',serif] text-[36px] font-medium leading-tight tracking-normal drop-shadow-sm">
          {loading ? "加载中" : song?.title || "一起听"}
        </h1>
        <p className="mt-3 text-[15px] italic tracking-normal text-white/80">
          {song?.artist || (error || "还没有可播放的歌")}
        </p>

        <div className="mt-8">
          <div className="relative h-[3px] overflow-visible rounded-full bg-white/25">
            <div className="h-full rounded-full bg-white shadow-[0_0_12px_rgba(255,255,255,0.45)]" style={{ width: `${progress}%` }} />
            <div
              className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border border-white/60 bg-white shadow-[0_2px_8px_rgba(0,0,0,0.14)]"
              style={{ left: `calc(${progress}% - 6px)` }}
            />
          </div>
          <div className="mt-2 flex justify-between text-[11px] text-white/70">
            <span>{formatClock(currentTime)}</span>
            <span>{formatClock(songDuration)}</span>
          </div>
        </div>

        <div className="mt-6 flex items-center gap-4">
          <button
            type="button"
            className="flex h-[54px] w-[54px] items-center justify-center rounded-full bg-white text-[#6a9bd1] shadow-[0_10px_30px_rgba(70,108,150,0.25)] transition active:scale-95 disabled:opacity-45"
            aria-label={isPlaying ? "暂停" : "播放"}
            onClick={togglePlay}
            disabled={!audioSrc}
          >
            {isPlaying ? (
              <svg className="h-6 w-6" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M7 5.5A1.5 1.5 0 0 1 8.5 4h1A1.5 1.5 0 0 1 11 5.5v13A1.5 1.5 0 0 1 9.5 20h-1A1.5 1.5 0 0 1 7 18.5v-13Zm6 0A1.5 1.5 0 0 1 14.5 4h1A1.5 1.5 0 0 1 17 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-1a1.5 1.5 0 0 1-1.5-1.5v-13Z" />
              </svg>
            ) : (
              <svg className="ml-1 h-6 w-6" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M8 5.3v13.4a1 1 0 0 0 1.52.85l10.1-6.7a1 1 0 0 0 0-1.7L9.52 4.45A1 1 0 0 0 8 5.3Z" />
              </svg>
            )}
          </button>
          <button
            type="button"
            className="h-11 rounded-full border border-white/18 bg-white/16 px-5 text-[14px] font-medium text-white shadow-[0_8px_22px_rgba(255,255,255,0.08)] backdrop-blur-md transition active:bg-white/25 disabled:opacity-45"
            onClick={() => switchSong()}
            disabled={!songs.length}
          >
            切换歌曲
          </button>
        </div>
      </header>

      <main className="relative z-10 min-h-0 flex-1 overflow-y-auto px-6 py-8">
        {showHistory ? (
          <div className="mb-6 rounded-[24px] border border-white/16 bg-white/14 p-3 backdrop-blur-xl">
            {historyItems.map((item, index) => (
              <button
                key={item.id || `${item.title}-${item.artist}`}
                type="button"
                className={`flex w-full items-center justify-between rounded-[18px] px-3 py-3 text-left transition ${
                  item.active ? "bg-white/20" : "active:bg-white/14"
                }`}
                onClick={() => switchSong(index)}
              >
                <span className="min-w-0">
                  <span className="block truncate text-[14px] font-medium">{item.title}</span>
                  <span className="mt-0.5 block truncate text-[12px] text-white/62">{item.artist}</span>
                </span>
                <span className="ml-4 text-[11px] text-white/62">{item.durationLabel}</span>
              </button>
            ))}
          </div>
        ) : null}

        {visibleLyrics.length ? (
          <div className="mb-8 space-y-2 text-center">
            {visibleLyrics.map((line, index) => (
              <p
                key={`${line.text}-${index}`}
                className={`mx-auto max-w-[92%] transition ${
                  line.active
                    ? "text-[16px] font-medium leading-7 text-white drop-shadow-[0_1px_2px_rgba(65,86,114,0.18)]"
                    : "text-[13px] leading-6 text-white/56"
                }`}
              >
                {line.text}
              </p>
            ))}
          </div>
        ) : null}

        <div className="space-y-7">
          {messages.map((message) => {
            if (message.role === "user") {
              return (
                <div key={message.id} className="flex justify-end">
                  <div className="max-w-[78%] rounded-[20px_20px_4px_20px] border border-white/16 bg-white/18 px-5 py-3 text-[14px] leading-relaxed text-white shadow-[0_8px_24px_rgba(255,255,255,0.08)] backdrop-blur-md">
                    {message.text}
                  </div>
                </div>
              );
            }
            return (
              <div key={message.id} className="max-w-[86%] pt-3 text-left">
                <div className="mb-4 h-[2px] w-6 rounded-full bg-white/80" />
                <p className={`text-[15px] leading-[1.65] tracking-normal text-white drop-shadow-[0_1px_2px_rgba(65,86,114,0.14)] ${message.pending ? "animate-pulse text-white/70" : ""}`}>
                  {message.text}
                </p>
              </div>
            );
          })}
        </div>
      </main>

      <footer className="relative z-10 bg-[linear-gradient(0deg,rgba(232,215,225,0.92)_0%,rgba(232,215,225,0.74)_64%,rgba(232,215,225,0)_100%)] px-5 pb-[calc(env(safe-area-inset-bottom,0px)+18px)] pt-5">
        <form
          className="flex min-h-[54px] items-center gap-2 rounded-full bg-white/95 py-1.5 pl-6 pr-1.5 shadow-[0_10px_30px_rgba(108,111,146,0.16)]"
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage();
          }}
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="min-w-0 flex-1 bg-transparent text-[14px] text-[#4b5563] outline-none placeholder:text-[#9ca3af]"
            placeholder={sending ? "渡在听..." : "聊聊你的感受..."}
            disabled={sending}
          />
          <button
            type="submit"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#9ebadc] text-white shadow-[0_4px_12px_rgba(100,129,164,0.28)] transition active:scale-95 disabled:opacity-45"
            disabled={sending || !draft.trim() || !song}
            aria-label="发送"
          >
            <SendIconMini />
          </button>
        </form>
      </footer>
    </div>
  );
}
