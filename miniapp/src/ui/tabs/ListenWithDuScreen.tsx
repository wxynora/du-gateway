import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { apiJson, buildApiAssetUrl, getOrCreatePanelDeviceId } from "../api";
import { MAIN_SUMITALK_DISPLAY_WINDOW_ID } from "../chatWindowIds";
import { ChevronLeftIcon, SendIconMini } from "../icons";
import { writeMusicBgmContext } from "../listenBgm";
import { useToast } from "../toast";

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
  translation?: string;
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
    .map((item) => ({
      time: asSeconds(item?.time),
      text: String(item?.text || "").trim(),
      translation: String(item?.translation || "").trim(),
    }))
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

const LYRIC_VIEWPORT_HEIGHT = 168;

function QueueIcon() {
  return (
    <svg className="h-5 w-5 stroke-[1.6]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 7h10" />
      <path d="M4 12h10" />
      <path d="M4 17h7" />
      <path d="M17 6v10.5a2.5 2.5 0 1 0 1.7 2.35V9h2.3" />
    </svg>
  );
}

function NextTrackIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M5.75 5.55v12.9a1 1 0 0 0 1.56.83l8.95-6.45a1 1 0 0 0 0-1.66L7.31 4.72a1 1 0 0 0-1.56.83Z" />
      <path d="M18.75 5.5a1 1 0 0 1 1 1v11a1 1 0 1 1-2 0v-11a1 1 0 0 1 1-1Z" />
    </svg>
  );
}

function PreviousTrackIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M5.25 5.5a1 1 0 0 1 2 0v11a1 1 0 1 1-2 0v-11Z" />
      <path d="M18.25 5.55v12.9a1 1 0 0 1-1.56.83l-8.95-6.45a1 1 0 0 1 0-1.66l8.95-6.45a1 1 0 0 1 1.56.83Z" />
    </svg>
  );
}

function ListenAvatar({
  image,
  label,
  className,
}: {
  image?: string;
  label: string;
  className: string;
}) {
  if (image) {
    return (
      <span className="block h-9 w-9 overflow-hidden rounded-full bg-white/25 shadow-[0_5px_14px_rgba(70,90,120,0.18)]">
        <img src={image} alt={label} className="h-full w-full object-cover" />
      </span>
    );
  }
  return (
    <span className={`flex h-9 w-9 items-center justify-center rounded-full text-[12px] font-medium shadow-[0_5px_14px_rgba(70,90,120,0.18)] ${className}`}>
      {label}
    </span>
  );
}

function ListenAvatarPair({ myAvatarImage, duAvatarImage }: { myAvatarImage?: string; duAvatarImage?: string }) {
  return (
    <div className="relative flex h-9 items-center pl-1" aria-label="我和渡一起听">
      <span className="relative z-0">
        <ListenAvatar image={myAvatarImage} label="我" className="bg-[#eef2f7] text-[#67748a]" />
      </span>
      <span className="relative z-10 -ml-1">
        <ListenAvatar image={duAvatarImage} label="渡" className="bg-[#fff7df] text-[#8b6a34]" />
      </span>
      <HeartbeatWave />
    </div>
  );
}

function HeartbeatWave() {
  const path = "M0,12 L14,12 L18,4 L22,20 L26,8 L30,12 L52,12";
  return (
    <span className="ml-3 flex h-6 w-[48px] items-center overflow-hidden text-white/78 drop-shadow-[0_2px_8px_rgba(70,90,120,0.18)]" aria-hidden="true">
      <svg className="h-6 w-full fill-none stroke-current" viewBox="0 0 52 24">
        <path
          className="listen-heartbeat-draw"
          d={path}
          strokeWidth="0.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="200"
          strokeDashoffset="200"
        />
      </svg>
      <style>
        {`@keyframes listen-heartbeat-draw {
          0% { stroke-dashoffset: 200; opacity: 0; }
          30% { opacity: 0.6; }
          70% { opacity: 0.6; }
          100% { stroke-dashoffset: 0; opacity: 0; }
        }
        .listen-heartbeat-draw {
          animation: listen-heartbeat-draw 3s ease-in-out infinite;
        }`}
      </style>
    </span>
  );
}

export function ListenWithDuScreen({
  onBack,
  backgroundImage,
  myAvatarImage,
  duAvatarImage,
  isActive = true,
}: {
  onBack: () => void;
  backgroundImage?: string;
  myAvatarImage?: string;
  duAvatarImage?: string;
  isActive?: boolean;
}) {
  const toast = useToast();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const lyricViewportRef = useRef<HTMLDivElement | null>(null);
  const lyricRowRefs = useRef<(HTMLDivElement | null)[]>([]);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const sendSeqRef = useRef(0);
  const playAfterSwitchRef = useRef(false);
  const listenBackgroundHeightRef = useRef(
    typeof window !== "undefined"
      ? Math.max(
          Math.round(window.innerHeight || 0),
          Math.round(document.documentElement?.clientHeight || 0),
          Math.round(window.visualViewport?.height || 0),
        )
      : 0,
  );
  const [songs, setSongs] = useState<MusicEntry[]>([]);
  const [songIndex, setSongIndex] = useState(0);
  const [messages, setMessages] = useState<ListenMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackStarting, setPlaybackStarting] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [sending, setSending] = useState(false);
  const [keyboardOffset, setKeyboardOffset] = useState(0);

  useEffect(() => {
    if (!isActive) return;
    const body = document.body;
    const html = document.documentElement;
    const previousBodyOverflow = body.style.overflow;
    const previousBodyOverscroll = body.style.overscrollBehavior;
    const previousHtmlOverflow = html.style.overflow;
    const previousHtmlOverscroll = html.style.overscrollBehavior;

    body.style.overflow = "hidden";
    body.style.overscrollBehavior = "none";
    html.style.overflow = "hidden";
    html.style.overscrollBehavior = "none";

    return () => {
      body.style.overflow = previousBodyOverflow;
      body.style.overscrollBehavior = previousBodyOverscroll;
      html.style.overflow = previousHtmlOverflow;
      html.style.overscrollBehavior = previousHtmlOverscroll;
    };
  }, [isActive]);

  useEffect(() => {
    if (!isActive) {
      setKeyboardOffset(0);
      setShowHistory(false);
      return;
    }
    const viewport = window.visualViewport;
    if (!viewport) return;

    const updateKeyboardOffset = () => {
      const offset = Math.max(0, Math.round(window.innerHeight - viewport.height - viewport.offsetTop));
      setKeyboardOffset(offset > 24 ? offset : 0);
    };

    updateKeyboardOffset();
    viewport.addEventListener("resize", updateKeyboardOffset);
    viewport.addEventListener("scroll", updateKeyboardOffset);
    window.addEventListener("resize", updateKeyboardOffset);

    return () => {
      viewport.removeEventListener("resize", updateKeyboardOffset);
      viewport.removeEventListener("scroll", updateKeyboardOffset);
      window.removeEventListener("resize", updateKeyboardOffset);
    };
  }, [isActive]);

  const song = songs[songIndex];
  const songDuration = duration || durationFor(song);
  const progress = songDuration > 0 ? Math.min(100, Math.max(0, (currentTime / songDuration) * 100)) : 0;
  const currentSegment = useMemo(() => currentSegmentFor(song, currentTime), [song, currentTime]);
  const audioSrc = song?.audio_url ? buildApiAssetUrl(song.audio_url) : "";
  const lyricLines = useMemo(() => lyricLinesFor(song), [song]);
  const plainLyrics = useMemo(() => plainLyricsFor(song), [song]);
  const activeLyricIndex = useMemo(() => currentLyricIndex(lyricLines, currentTime), [lyricLines, currentTime]);
  const lyricActiveIndex = activeLyricIndex >= 0 ? activeLyricIndex : 0;
  const [lyricTrackOffset, setLyricTrackOffset] = useState(LYRIC_VIEWPORT_HEIGHT / 2);
  const playbackActive = isPlaying || playbackStarting;
  const listenBackgroundCanvasHeight = listenBackgroundHeightRef.current ? `${listenBackgroundHeightRef.current}px` : "100lvh";

  const historyItems = useMemo(
    () => songs.map((item, index) => ({ ...item, active: index === songIndex, durationLabel: formatClock(durationFor(item)) })),
    [songs, songIndex],
  );

  function writeStoppedBgmContext(atSeconds = currentTime) {
    writeMusicBgmContext({
      active: Boolean(song && audioSrc),
      is_playing: false,
      entry_id: song?.id,
      title: song?.title,
      artist: song?.artist,
      current_time: atSeconds,
      duration_seconds: songDuration,
      segment: currentSegment,
      source: "listen-with-du",
    });
  }

  async function startPlayback(): Promise<boolean> {
    const audio = audioRef.current;
    if (!audio || !audioSrc) return false;
    setError("");
    setPlaybackStarting(true);
    try {
      if (audio.ended) audio.currentTime = 0;
      await audio.play();
      setIsPlaying(true);
      return true;
    } catch (e) {
      setIsPlaying(false);
      toast(`播放没接上：${String((e as any)?.message || e || "再点一下")}`);
      return false;
    } finally {
      setPlaybackStarting(false);
    }
  }

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
    const shouldPlay = playAfterSwitchRef.current;
    playAfterSwitchRef.current = false;
    setCurrentTime(0);
    setDuration(durationFor(song));
    if (audio) {
      audio.pause();
      audio.load();
      if (shouldPlay && audioSrc) {
        void startPlayback();
      } else {
        setIsPlaying(false);
        setPlaybackStarting(false);
      }
    } else {
      setIsPlaying(false);
      setPlaybackStarting(false);
    }
  }, [audioSrc, song?.id]);

  useEffect(() => {
    writeMusicBgmContext({
      active: Boolean(song && audioSrc),
      is_playing: Boolean(song && audioSrc && isPlaying),
      entry_id: song?.id,
      title: song?.title,
      artist: song?.artist,
      current_time: currentTime,
      duration_seconds: songDuration,
      segment: currentSegment,
      source: "listen-with-du",
    });
  }, [audioSrc, currentSegment, currentTime, isPlaying, song?.artist, song?.id, song?.title, songDuration]);

  useEffect(() => {
    return () => {
      writeMusicBgmContext({ active: false, is_playing: false, source: "listen-with-du" });
    };
  }, []);

  useEffect(() => {
    const syncStoppedIfHidden = () => {
      const audio = audioRef.current;
      if (!audio || (!audio.paused && !audio.ended)) return;
      writeStoppedBgmContext(asSeconds(audio.currentTime));
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") syncStoppedIfHidden();
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("pagehide", syncStoppedIfHidden);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("pagehide", syncStoppedIfHidden);
    };
  }, [audioSrc, currentSegment, currentTime, song?.artist, song?.id, song?.title, songDuration]);

  useLayoutEffect(() => {
    if (!lyricLines.length) return;
    let frame = 0;
    const measure = () => {
      const viewport = lyricViewportRef.current;
      const activeRow = lyricRowRefs.current[lyricActiveIndex];
      if (!viewport || !activeRow) return;
      const nextOffset = viewport.clientHeight / 2 - activeRow.offsetTop - activeRow.offsetHeight / 2;
      setLyricTrackOffset((prev) => (Math.abs(prev - nextOffset) > 0.5 ? nextOffset : prev));
    };
    frame = window.requestAnimationFrame(measure);
    window.addEventListener("resize", measure);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", measure);
    };
  }, [lyricActiveIndex, lyricLines]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages.length]);

  function switchSong(nextIndex = songs.length ? (songIndex + 1) % songs.length : 0) {
    if (!songs.length) return;
    sendSeqRef.current += 1;
    writeStoppedBgmContext(audioRef.current ? asSeconds(audioRef.current.currentTime) : currentTime);
    setIsPlaying(false);
    setPlaybackStarting(false);
    setSongIndex(nextIndex);
    setShowHistory(false);
    setSending(false);
    setMessages([]);
  }

  function switchPreviousSong() {
    if (!songs.length) return;
    switchSong((songIndex - 1 + songs.length) % songs.length);
  }

  function handleAudioEnded() {
    writeStoppedBgmContext(songDuration || currentTime);
    if (!songs.length) {
      setIsPlaying(false);
      return;
    }
    if (songs.length === 1) {
      const audio = audioRef.current;
      if (!audio || !audioSrc) {
        setIsPlaying(false);
        return;
      }
      audio.currentTime = 0;
      void startPlayback();
      return;
    }
    playAfterSwitchRef.current = true;
    switchSong((songIndex + 1) % songs.length);
  }

  async function togglePlay() {
    const audio = audioRef.current;
    if (!audio || !audioSrc) return;
    if (!audio.paused || playbackStarting) {
      audio.pause();
      setIsPlaying(false);
      setPlaybackStarting(false);
      return;
    }
    await startPlayback();
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
          lyrics: lyricsPayloadFor(song),
          message: text,
          recent_messages: recentMessages,
          window_id: MAIN_SUMITALK_DISPLAY_WINDOW_ID,
          reply_target: deviceId,
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
    <div
      className={`fixed inset-0 z-30 flex h-[100lvh] min-h-screen w-full flex-col overflow-hidden overscroll-none bg-transparent text-white transition-opacity duration-150 ${
        isActive ? "opacity-100" : "pointer-events-none invisible opacity-0"
      }`}
      aria-hidden={!isActive}
    >
      {backgroundImage ? (
        <div
          className="pointer-events-none absolute left-0 top-0 z-0 w-full bg-cover bg-center"
          style={{ backgroundImage: `url(${backgroundImage})`, height: listenBackgroundCanvasHeight }}
        />
      ) : (
        <div
          className="pointer-events-none absolute left-0 top-0 z-0 w-full bg-[linear-gradient(180deg,#6a9bd1_0%,#9ebadc_48%,#e8d7e1_100%)]"
          style={{ height: listenBackgroundCanvasHeight }}
        />
      )}
      <div
        className="pointer-events-none absolute left-0 top-0 z-0 w-full bg-[linear-gradient(180deg,rgba(37,58,85,0.18)_0%,rgba(62,78,108,0.10)_42%,rgba(232,215,225,0.58)_100%)]"
        style={{ height: listenBackgroundCanvasHeight }}
      />
      <div
        className="pointer-events-none absolute left-0 top-0 z-0 w-full bg-[radial-gradient(circle_at_20%_15%,rgba(255,255,255,0.45),transparent_30%),radial-gradient(circle_at_82%_74%,rgba(255,210,226,0.46),transparent_32%),linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0))] mix-blend-overlay"
        style={{ height: listenBackgroundCanvasHeight }}
      />

      {audioSrc ? (
        <audio
          ref={audioRef}
          src={audioSrc}
          preload="auto"
          onLoadedMetadata={(e) => setDuration(asSeconds(e.currentTarget.duration) || durationFor(song))}
          onTimeUpdate={(e) => setCurrentTime(asSeconds(e.currentTarget.currentTime))}
          onPlay={() => {
            setIsPlaying(true);
            setPlaybackStarting(false);
          }}
          onPlaying={() => {
            setIsPlaying(true);
            setPlaybackStarting(false);
          }}
          onWaiting={() => {
            if (!audioRef.current?.paused) setPlaybackStarting(true);
          }}
          onCanPlay={() => setPlaybackStarting(false)}
          onPause={(e) => {
            const pausedAt = asSeconds(e.currentTarget.currentTime);
            setCurrentTime(pausedAt);
            setIsPlaying(false);
            setPlaybackStarting(false);
            writeStoppedBgmContext(pausedAt);
          }}
          onError={(e) => {
            setIsPlaying(false);
            setPlaybackStarting(false);
            setError("音频加载失败");
            toast(`音频加载失败：${e.currentTarget.error?.message || "再试一下"}`);
          }}
          onEnded={handleAudioEnded}
        />
      ) : null}

      <header className="relative z-10 px-6 pb-4 pt-[calc(env(safe-area-inset-top,0px)+18px)]">
        <div className="mb-7 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="flex h-9 w-9 items-center justify-center text-white drop-shadow-[0_2px_8px_rgba(70,90,120,0.28)] transition active:scale-95 active:text-white/80"
              onClick={onBack}
              aria-label="返回"
            >
              <ChevronLeftIcon />
            </button>
            <ListenAvatarPair myAvatarImage={myAvatarImage} duAvatarImage={duAvatarImage} />
          </div>
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-white/12 text-white backdrop-blur-md transition active:bg-white/25"
            onClick={() => setShowHistory((prev) => !prev)}
            aria-label="播放列表"
          >
            <QueueIcon />
          </button>
        </div>

        <h1 className="font-['Playfair_Display','Noto_Serif_SC',serif] text-[26px] font-medium leading-tight tracking-normal drop-shadow-sm">
          {loading ? "加载中" : song?.title || "一起听"}
        </h1>
        <p className="mt-1.5 font-['Playfair_Display','Noto_Serif_SC',serif] text-[11px] italic leading-tight tracking-normal text-white/70">
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

        <div className="mt-2 flex items-center justify-center gap-16">
          <button
            type="button"
            className="flex h-10 w-10 items-center justify-center text-white drop-shadow-[0_3px_10px_rgba(70,90,120,0.22)] transition active:scale-95 disabled:cursor-default"
            onClick={switchPreviousSong}
            disabled={!songs.length}
            aria-label="上一首"
          >
            <PreviousTrackIcon />
          </button>
          <button
            type="button"
            className="flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.24)] backdrop-blur-[2px] drop-shadow-[0_3px_10px_rgba(70,90,120,0.24)] transition active:scale-95 disabled:cursor-default"
            aria-label={playbackActive ? "暂停" : "播放"}
            onClick={togglePlay}
            disabled={!audioSrc}
          >
            {playbackActive ? (
              <svg className="h-[22px] w-[22px]" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M7 5.5A1.5 1.5 0 0 1 8.5 4h1A1.5 1.5 0 0 1 11 5.5v13A1.5 1.5 0 0 1 9.5 20h-1A1.5 1.5 0 0 1 7 18.5v-13Zm6 0A1.5 1.5 0 0 1 14.5 4h1A1.5 1.5 0 0 1 17 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-1a1.5 1.5 0 0 1-1.5-1.5v-13Z" />
              </svg>
            ) : (
              <svg className="h-[22px] w-[22px]" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M8 5.3v13.4a1 1 0 0 0 1.52.85l10.1-6.7a1 1 0 0 0 0-1.7L9.52 4.45A1 1 0 0 0 8 5.3Z" />
              </svg>
            )}
          </button>
          <button
            type="button"
            className="flex h-10 w-10 items-center justify-center text-white drop-shadow-[0_3px_10px_rgba(70,90,120,0.22)] transition active:scale-95 disabled:cursor-default"
            onClick={() => switchSong()}
            disabled={!songs.length}
            aria-label="下一首"
          >
            <NextTrackIcon />
          </button>
        </div>
      </header>

      {showHistory ? (
        <>
          <button
            type="button"
            className="absolute inset-0 z-20 cursor-default bg-transparent"
            onClick={() => setShowHistory(false)}
            aria-label="关闭播放列表"
          />
          <div className="absolute left-5 right-5 top-[calc(env(safe-area-inset-top,0px)+70px)] z-30 max-h-[52dvh] overflow-y-auto rounded-[24px] border border-white/18 bg-white/18 p-3 shadow-[0_18px_50px_rgba(55,76,105,0.18)] backdrop-blur-2xl">
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
        </>
      ) : null}

      <section className="relative z-10 shrink-0 px-6 pt-1">
        {lyricLines.length ? (
          <div
            ref={lyricViewportRef}
            className="relative h-[168px] overflow-hidden text-center font-['Songti_SC','STSong','Noto_Serif_SC','SimSun',serif]"
            style={{
              WebkitMaskImage: "linear-gradient(180deg, transparent 0%, #000 20%, #000 80%, transparent 100%)",
              maskImage: "linear-gradient(180deg, transparent 0%, #000 20%, #000 80%, transparent 100%)",
            }}
          >
            <div
              className="will-change-transform"
              style={{
                transform: `translate3d(0, ${lyricTrackOffset}px, 0)`,
                transition: "transform 680ms cubic-bezier(0.22, 1, 0.36, 1)",
              }}
            >
              {lyricLines.map((line, index) => {
                const active = index === lyricActiveIndex;
                const hasTranslation = Boolean(line.translation);
                return (
                  <div
                    key={`${asSeconds(line.time)}-${line.text}-${index}`}
                    ref={(el) => {
                      lyricRowRefs.current[index] = el;
                    }}
                    className={`flex flex-col items-center justify-center transition duration-500 ${hasTranslation ? "min-h-11 py-1.5" : "min-h-8 py-0.5"} ${
                      active ? "scale-100 opacity-100" : "scale-[0.96] opacity-55"
                    }`}
                  >
                    <p
                      className={`mx-auto max-w-[94%] truncate transition duration-500 ${
                        active
                          ? `text-[16px] font-medium ${hasTranslation ? "leading-7" : "leading-6"} text-white drop-shadow-[0_1px_2px_rgba(65,86,114,0.2)]`
                          : `text-[13px] ${hasTranslation ? "leading-6" : "leading-5"} text-white/62`
                      }`}
                    >
                      {line.text}
                    </p>
                    {line.translation ? (
                      <p className={`mx-auto mt-0.5 max-w-[92%] truncate text-[12px] leading-5 transition duration-500 ${active ? "text-white/78" : "text-white/42"}`}>
                        {line.translation}
                      </p>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        ) : plainLyrics.length ? (
          <div className="space-y-1 text-center font-['Songti_SC','STSong','Noto_Serif_SC','SimSun',serif]">
            {plainLyrics.slice(0, 5).map((text, index) => (
              <p
                key={`${text}-${index}`}
                className={`mx-auto max-w-[92%] transition ${
                  index === 0
                    ? "text-[16px] font-medium leading-6 text-white drop-shadow-[0_1px_2px_rgba(65,86,114,0.18)]"
                    : "text-[13px] leading-5 text-white/56"
                }`}
              >
                {text}
              </p>
            ))}
          </div>
        ) : null}
      </section>

      <main className="relative z-10 min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 pb-6 pt-4">
        <div className="space-y-4">
          {messages.map((message) => {
            if (message.role === "user") {
              return (
                <div key={message.id} className="flex justify-end">
                  <div className="max-w-[72%] rounded-[18px_18px_5px_18px] border border-white/15 bg-white/20 px-4 py-2.5 text-[13px] leading-[1.55] text-white shadow-[0_6px_18px_rgba(255,255,255,0.07)] backdrop-blur-md">
                    {message.text}
                  </div>
                </div>
              );
            }
            return (
              <div key={message.id} className="flex justify-start">
                <p className={`max-w-[78%] rounded-[18px_18px_18px_5px] border border-white/15 bg-white/15 px-4 py-2.5 text-[13px] leading-[1.6] tracking-normal text-white shadow-[0_6px_18px_rgba(70,90,120,0.08)] backdrop-blur-md ${message.pending ? "animate-pulse text-white/70" : ""}`}>
                  {message.text}
                </p>
              </div>
            );
          })}
          <div ref={chatEndRef} />
        </div>
      </main>

      <footer
        className="relative z-10 px-5 pb-[calc(env(safe-area-inset-bottom,0px)+18px)] pt-5 transition-transform duration-200 ease-out will-change-transform"
        style={{ transform: keyboardOffset ? `translate3d(0, -${keyboardOffset}px, 0)` : undefined }}
      >
        <form
          className="flex min-h-[46px] items-center gap-2 rounded-full border border-white/25 bg-white/20 py-1 pl-5 pr-1 shadow-[0_12px_34px_rgba(70,90,120,0.16)] backdrop-blur-2xl"
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage();
          }}
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="min-w-0 flex-1 bg-transparent text-[14px] text-white outline-none placeholder:text-white/60"
            placeholder={sending ? "渡在听..." : "聊聊你的感受..."}
            disabled={sending}
          />
          <button
            type="submit"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-[#9ebadc] shadow-[0_4px_12px_rgba(70,90,120,0.18)] transition active:scale-95 disabled:cursor-default"
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
