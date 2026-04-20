import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.sumitalk.app",
  appName: "SumiTalk",
  webDir: "../miniapp_static",
  bundledWebRuntime: false,
  server: {
    url: "https://duxy-home.com/miniapp",
    cleartext: false,
  },
  android: {
    allowMixedContent: true,
  },
};

export default config;
