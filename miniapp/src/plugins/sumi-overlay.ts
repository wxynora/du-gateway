import { Capacitor, registerPlugin } from "@capacitor/core";

export interface SumiOverlayPlugin {
  setFloatingBallEnabled(options: { enabled: boolean }): Promise<void>;
  getFloatingBallEnabled(): Promise<{ enabled: boolean }>;
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
};
