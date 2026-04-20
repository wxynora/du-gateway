import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.sumitalk.app",
  appName: "SumiTalk",
  webDir: "../miniapp_static",
  bundledWebRuntime: false,
  android: {
    allowMixedContent: true,
  },
};

export default config;
