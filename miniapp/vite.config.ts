import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === "android" ? "./" : "/miniapp/",
  build: {
    outDir: path.resolve(__dirname, "../miniapp_static"),
    emptyOutDir: true,
    assetsDir: "assets",
  },
}));

