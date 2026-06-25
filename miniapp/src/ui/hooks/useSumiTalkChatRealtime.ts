import { useEffect, useRef } from "react";
import { buildRealtimeWebSocketUrl } from "../api";

export type SumiTalkChatRealtimeEvent = {
  seq?: number;
  event_id?: string;
  kind?: string;
  job_id?: string;
  client_request_id?: string;
  window_id?: string;
  round?: number;
  text?: string;
  tool_call_id?: string;
  name?: string;
  arguments?: string;
  result_preview?: string;
  error?: string;
  ok?: boolean;
  duration_ms?: number;
};

type Options = {
  enabled: boolean;
  deviceId: string;
  windowId: string;
  onEvent: (event: SumiTalkChatRealtimeEvent) => void;
};

export function useSumiTalkChatRealtime({ enabled, deviceId, windowId, onEvent }: Options) {
  const onEventRef = useRef(onEvent);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    const did = String(deviceId || "").trim();
    const wid = String(windowId || "").trim();
    if (!enabled || !did || !wid || typeof WebSocket === "undefined") return;

    let cancelled = false;
    let socket: WebSocket | null = null;
    let reconnectTimer = 0;
    let retryCount = 0;

    const scheduleReconnect = () => {
      if (cancelled || reconnectTimer) return;
      retryCount += 1;
      const delay = Math.min(15000, 800 * 2 ** Math.min(retryCount, 5));
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = 0;
        connect();
      }, delay);
    };

    const connect = () => {
      if (cancelled) return;
      try {
        socket = new WebSocket(buildRealtimeWebSocketUrl("/ws/device", { device_id: did, window_id: wid }));
      } catch {
        scheduleReconnect();
        return;
      }

      socket.onopen = () => {
        retryCount = 0;
      };
      socket.onmessage = (event) => {
        let data: any = null;
        try {
          data = JSON.parse(String(event.data || "{}"));
        } catch {
          return;
        }
        if (data?.type !== "sumitalk_chat_event") return;
        const payload = data?.event && typeof data.event === "object" ? data.event : data;
        onEventRef.current(payload);
      };
      socket.onclose = () => {
        if (!cancelled) scheduleReconnect();
      };
      socket.onerror = () => {
        try {
          socket?.close();
        } catch {}
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      try {
        socket?.close();
      } catch {}
    };
  }, [deviceId, enabled, windowId]);
}
