import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const miniappDir = process.cwd();
const repoRoot = path.resolve(miniappDir, "..");
const envPath = path.join(repoRoot, ".env");

function readEnvFile(filePath) {
  const out = {};
  if (!fs.existsSync(filePath)) return out;
  const text = fs.readFileSync(filePath, "utf8");
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf("=");
    if (idx <= 0) continue;
    const key = trimmed.slice(0, idx).trim();
    let value = trimmed.slice(idx + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  }
  return out;
}

const envFile = readEnvFile(envPath);
const apiBase =
  String(process.env.VITE_API_BASE_URL || envFile.MAIN_GATEWAY_BASE_URL || envFile.GATEWAY_PUBLIC_BASE_URL || "").trim().replace(/\/+$/, "");

if (!apiBase) {
  console.error("缺少 Android 构建可用的网关地址：请在 ../.env 里配置 MAIN_GATEWAY_BASE_URL 或 GATEWAY_PUBLIC_BASE_URL");
  process.exit(1);
}

const child = spawnSync(
  process.platform === "win32" ? "npx.cmd" : "npx",
  ["vite", "build", "--mode", "android"],
  {
    cwd: miniappDir,
    stdio: "inherit",
    env: {
      ...process.env,
      VITE_API_BASE_URL: apiBase,
    },
  },
);

process.exit(child.status ?? 1);
