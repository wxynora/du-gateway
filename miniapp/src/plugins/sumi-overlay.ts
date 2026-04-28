import { Capacitor, registerPlugin } from "@capacitor/core";

export interface SumiOverlayPlugin {
  setFloatingBallEnabled(options: { enabled: boolean }): Promise<void>;
  getFloatingBallEnabled(): Promise<{ enabled: boolean }>;
  getStableDeviceId(): Promise<{ deviceId: string }>;
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
