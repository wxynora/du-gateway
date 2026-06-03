import { Capacitor, registerPlugin } from "@capacitor/core";

export interface SumiOverlayPlugin {
  setFloatingBallEnabled(options: { enabled: boolean }): Promise<void>;
  getFloatingBallEnabled(): Promise<{ enabled: boolean }>;
  getStableDeviceId(): Promise<{ deviceId: string }>;
  getSenseReportingStatus(): Promise<SenseReportingStatus>;
  setSenseReportingConfig(options: { enabled: boolean }): Promise<{ enabled: boolean }>;
  requestSenseReportingSnapshot(): Promise<SenseReportingSnapshotResult>;
  getHealthReportingStatus(): Promise<HealthReportingStatus>;
  setHealthReportingConfig(options: { intervalSeconds: number }): Promise<{ intervalSeconds: number }>;
  requestHealthReportingSnapshot(): Promise<{ requested?: boolean }>;
  clearHealthReportingLogs(): Promise<void>;
  showDuVitalsNotification(options: DuVitalsNotificationOptions): Promise<{ shown?: boolean }>;
  clearDuVitalsNotification(): Promise<void>;
  openNotificationListenerSettings(): Promise<void>;
  createSystemAlarm(options: { hour: number; minute: number; title?: string; skipUi?: boolean; notify?: boolean }): Promise<{
    ok?: boolean;
    hour?: number;
    minute?: number;
    title?: string;
    notified?: boolean;
  }>;
  openSystemAlarms(): Promise<void>;
  openCalendarEvent(options: { eventId?: number | string; startMillis?: number }): Promise<void>;
}

export type HealthReportingLog = {
  at?: string;
  level?: "ok" | "skip" | "error" | string;
  message?: string;
  heart_rate?: number;
  steps?: number;
  raw_text?: string;
  http_code?: number;
};

export type HealthReportingStatus = {
  intervalSeconds?: number;
  packageName?: string;
  listenerEnabled?: boolean;
  listenerConnected?: boolean;
  last?: Record<string, any>;
  logs?: HealthReportingLog[];
};

export type SenseReportingStatus = {
  enabled?: boolean;
  deviceId?: string;
  accessibilityEnabled?: boolean;
  locationPermission?: boolean;
  usageStatsAvailable?: boolean;
};

export type SenseReportingSnapshotResult = {
  requested?: boolean;
  foregroundRequested?: boolean;
  usageRequested?: boolean;
};

export type DuVitalsNotificationOptions = {
  heartBpm?: number;
  breathRpm?: number;
  status?: string;
  updatedAt?: string;
};

const native = registerPlugin<SumiOverlayPlugin>("SumiOverlay");

export const SumiOverlay = {
  async setFloatingBallEnabled(options: { enabled: boolean }): Promise<void> {
    if (Capacitor.getPlatform() !== "android") return;
    return native.setFloatingBallEnabled(options);
  },

  async getFloatingBallEnabled(): Promise<{ enabled: boolean }> {
    if (Capacitor.getPlatform() !== "android") return { enabled: true };
    return native.getFloatingBallEnabled();
  },

  async getStableDeviceId(): Promise<{ deviceId: string }> {
    if (Capacitor.getPlatform() !== "android") return { deviceId: "" };
    return native.getStableDeviceId();
  },

  async getSenseReportingStatus(): Promise<SenseReportingStatus> {
    if (Capacitor.getPlatform() !== "android") return { enabled: false, deviceId: "" };
    return native.getSenseReportingStatus();
  },

  async setSenseReportingConfig(options: { enabled: boolean }): Promise<{ enabled: boolean }> {
    if (Capacitor.getPlatform() !== "android") return { enabled: false };
    return native.setSenseReportingConfig(options);
  },

  async requestSenseReportingSnapshot(): Promise<SenseReportingSnapshotResult> {
    if (Capacitor.getPlatform() !== "android") return { requested: false };
    return native.requestSenseReportingSnapshot();
  },

  async getHealthReportingStatus(): Promise<HealthReportingStatus> {
    if (Capacitor.getPlatform() !== "android") {
      return { intervalSeconds: 60, packageName: "com.mc.xiaomi1", listenerEnabled: false, listenerConnected: false, last: {}, logs: [] };
    }
    return native.getHealthReportingStatus();
  },

  async setHealthReportingConfig(options: { intervalSeconds: number }): Promise<{ intervalSeconds: number }> {
    if (Capacitor.getPlatform() !== "android") return { intervalSeconds: options.intervalSeconds };
    return native.setHealthReportingConfig(options);
  },

  async requestHealthReportingSnapshot(): Promise<{ requested?: boolean }> {
    if (Capacitor.getPlatform() !== "android") return { requested: false };
    return native.requestHealthReportingSnapshot();
  },

  async clearHealthReportingLogs(): Promise<void> {
    if (Capacitor.getPlatform() !== "android") return;
    return native.clearHealthReportingLogs();
  },

  async showDuVitalsNotification(options: DuVitalsNotificationOptions): Promise<{ shown?: boolean }> {
    if (Capacitor.getPlatform() !== "android") return { shown: false };
    return native.showDuVitalsNotification(options);
  },

  async clearDuVitalsNotification(): Promise<void> {
    if (Capacitor.getPlatform() !== "android") return;
    return native.clearDuVitalsNotification();
  },

  async openNotificationListenerSettings(): Promise<void> {
    if (Capacitor.getPlatform() !== "android") return;
    return native.openNotificationListenerSettings();
  },

  async createSystemAlarm(options: { hour: number; minute: number; title?: string; skipUi?: boolean; notify?: boolean }): Promise<{
    ok?: boolean;
    hour?: number;
    minute?: number;
    title?: string;
    notified?: boolean;
  }> {
    if (Capacitor.getPlatform() !== "android") return { ok: false };
    const result = await native.createSystemAlarm(options);
    if (result?.ok) {
      window.dispatchEvent(new CustomEvent("sumitalk-system-alarm-created", { detail: result }));
    }
    return result;
  },

  async openSystemAlarms(): Promise<void> {
    if (Capacitor.getPlatform() !== "android") return;
    return native.openSystemAlarms();
  },

  async openCalendarEvent(options: { eventId?: number | string; startMillis?: number }): Promise<void> {
    if (Capacitor.getPlatform() !== "android") return;
    return native.openCalendarEvent(options);
  },
};
