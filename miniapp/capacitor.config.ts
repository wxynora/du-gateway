import type { CapacitorConfig } from "@capacitor/cli";

const remoteMiniappUrl = (process.env.SUMITALK_WEB_URL || "https://duxy-home.com/miniapp/").trim();

const config: CapacitorConfig = {
  appId: "com.sumitalk.app",
  appName: "SumiTalk",
  webDir: "../miniapp_static",
  bundledWebRuntime: false,
  server: {
    url: remoteMiniappUrl,
    cleartext: false,
  },
  android: {
    allowMixedContent: true,
  },
};

export default config;
