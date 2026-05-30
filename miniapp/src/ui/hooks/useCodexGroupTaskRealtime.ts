import { useEffect, useRef } from "react";
import { buildRealtimeWebSocketUrl } from "../api";

export type CodexGroupTaskRealtimeTask = {
  id?: string;
  mode?: string;
  status?: "queued" | "running" | "done" | "error" | "cancelled";
  response?: string;
  error?: string;
  client_request_id?: string;
  coding_thread_key?: string;
};

type Options = {
  enabled: boolean;
  deviceId: string;
  onTask: (task: CodexGroupTaskRealtimeTask) => void;
};

export function useCodexGroupTaskRealtime({ enabled, deviceId, onTask }: Options) {
  const onTaskRef = useRef(onTask);

  useEffect(() => {
    onTaskRef.current = onTask;
  }, [onTask]);

  useEffect(() => {
    const did = String(deviceId || "").trim();
    if (!enabled || !did || typeof WebSocket === "undefined") return;

    let cancelled = false;
    let socket: WebSocket | null = null;
    let reconnectTimer = 0;
    let retryCount = 0;

    const connect = () => {
      if (cancelled) return;
      try {
        socket = new WebSocket(buildRealtimeWebSocketUrl("/ws/device", { device_id: did }));
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
        if (data?.type !== "codex_group_chat_task" || !data?.task) return;
        onTaskRef.current(data.task);
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

    const scheduleReconnect = () => {
      if (cancelled || reconnectTimer) return;
      retryCount += 1;
      const delay = Math.min(15000, 800 * 2 ** Math.min(retryCount, 5));
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = 0;
        connect();
      }, delay);
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      try {
        socket?.close();
      } catch {}
    };
  }, [deviceId, enabled]);
}
