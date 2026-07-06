import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const DEV_API_PROXY = String(
  process.env.MINIAPP_DEV_API_PROXY ||
    process.env.VITE_DEV_API_PROXY ||
    "http://127.0.0.1:5055",
).replace(/\/+$/, "");

const apiProxy = {
  "/miniapp-api": {
    target: DEV_API_PROXY,
    changeOrigin: true,
  },
};

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === "android" ? "./" : "/miniapp/",
  server: {
    proxy: apiProxy,
  },
  preview: {
    proxy: apiProxy,
  },
  build: {
    outDir: path.resolve(__dirname, "../miniapp_static"),
    emptyOutDir: true,
    assetsDir: "assets",
  },
}));
