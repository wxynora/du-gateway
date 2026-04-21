import { Capacitor, registerPlugin } from "@capacitor/core";

export interface SumiOverlayPlugin {
  setFloatingBallEnabled(options: { enabled: boolean }): Promise<void>;
  getFloatingBallEnabled(): Promise<{ enabled: boolean }>;
  getStableDeviceId(): Promise<{ deviceId: string }>;
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
};
