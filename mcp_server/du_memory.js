#!/usr/bin/env node
/**
 * du-memory MCP stdio server
 *
 * 供 Claude Code (CC) 通过 MCP 协议读写渡の网关记忆池。
 *
 * 工具：
 *   get_context  — 拉取总结 + 动态层，新任务前调用
 *   save_memory  — 向动态层追加一条记忆（需网关先实现 POST /api/memory/append）
 *
 * 环境变量：
 *   DU_GATEWAY_BASE_URL  网关地址，默认 http://localhost:5000
 *   DU_GATEWAY_TOKEN     Bearer token（若网关开启鉴权则必填）
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const BASE_URL = (process.env.DU_GATEWAY_BASE_URL || "http://localhost:5000").replace(/\/$/, "");
const TOKEN = process.env.DU_GATEWAY_TOKEN || "";

function authHeaders() {
  const h = { "Content-Type": "application/json" };
  if (TOKEN) h["Authorization"] = `Bearer ${TOKEN}`;
  return h;
}

async function fetchGateway(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------

const server = new Server(
  { name: "du-memory", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "get_context",
      description:
        "拉取渡的记忆上下文：总结（渡的回忆）+ 动态层记忆。" +
        "新任务开始前调用，获取与 Telegram 共享的最新记忆状态。",
      inputSchema: {
        type: "object",
        properties: {},
        required: [],
      },
    },
    {
      name: "ring_phone",
      description:
        "让老婆手机响铃。用于叫醒或提醒。" +
        "调用后命令入队，手机 Tasker 会在几秒内拉取并执行。",
      inputSchema: {
        type: "object",
        properties: {
          duration_sec: {
            type: "number",
            description: "响铃时长（秒），默认 30",
          },
          volume: {
            type: "number",
            description: "音量 0-100，默认 80",
          },
          sound: {
            type: "string",
            description: "铃声名称，默认 default",
          },
        },
        required: [],
      },
    },
    {
      name: "play_music",
      description:
        "让老婆手机播放音乐。不传 uri 则播放当前播放器。",
      inputSchema: {
        type: "object",
        properties: {
          uri: {
            type: "string",
            description: "可选，指定歌曲/歌单链接",
          },
        },
        required: [],
      },
    },
    {
      name: "pause_music",
      description: "暂停老婆手机音乐播放。",
      inputSchema: {
        type: "object",
        properties: {},
        required: [],
      },
    },
    {
      name: "check_phone_command",
      description:
        "查询手机命令执行状态。调完 ring_phone 后可查看是否已响铃。",
      inputSchema: {
        type: "object",
        properties: {
          command_id: {
            type: "string",
            description: "可选，查特定命令。不传则返回最近状态。",
          },
        },
        required: [],
      },
    },
    {
      name: "save_memory",
      description:
        "向动态层追加一条记忆。" +
        "用于把 CC 侧重要进展写回共享记忆池，渡在 Telegram 下次会话时可见。" +
        "注意：需要网关先实现 POST /api/memory/append 后才能真正写入。",
      inputSchema: {
        type: "object",
        properties: {
          content: {
            type: "string",
            description: "要保存的记忆内容",
          },
          importance: {
            type: "number",
            description: "重要程度 1-5，默认 3",
          },
          tag: {
            type: "string",
            description: "标签，如 CC、开发、重要，默认 CC",
          },
        },
        required: ["content"],
      },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;

  // ------------------------------------------------------------------
  // get_context：GET /summary + GET /dynamic-memory，合并输出
  // ------------------------------------------------------------------
  if (name === "get_context") {
    const [summaryRes, memoryRes] = await Promise.all([
      fetchGateway("/summary").catch((e) => ({ error: e.message })),
      fetchGateway("/dynamic-memory").catch((e) => ({ error: e.message })),
    ]);

    const lines = [];

    // 总结
    if (summaryRes.error) {
      lines.push(`## 渡的回忆（总结）\n⚠️ 读取失败：${summaryRes.error}`);
    } else if (summaryRes.has_summary) {
      lines.push("## 渡的回忆（总结）\n" + summaryRes.summary);
    } else {
      lines.push("## 渡的回忆（总结）\n（暂无）");
    }

    // 动态层
    if (memoryRes.error) {
      lines.push(`## 动态层记忆\n⚠️ 读取失败：${memoryRes.error}`);
    } else {
      const memories = (memoryRes.memories || []).map((m) => {
        if (typeof m === "string") return m;
        const parts = [];
        if (m.content) parts.push(m.content);
        if (m.tag) parts.push(`[${m.tag}]`);
        if (m.importance) parts.push(`重要度:${m.importance}`);
        return parts.join(" ") || JSON.stringify(m);
      });
      lines.push(
        "## 动态层记忆\n" +
          (memories.length
            ? memories.map((m, i) => `${i + 1}. ${m}`).join("\n")
            : "（暂无）")
      );
    }

    return {
      content: [{ type: "text", text: lines.join("\n\n") }],
    };
  }

  // ------------------------------------------------------------------
  // ring_phone：POST /api/mobile_command 入队 alarm_ring
  // ------------------------------------------------------------------
  if (name === "ring_phone") {
    const duration_sec = typeof args.duration_sec === "number" ? args.duration_sec : 30;
    const volume = typeof args.volume === "number" ? args.volume : 80;
    const sound = (args.sound || "default").trim();
    const idempotency_key = `ring_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

    const res = await fetchGateway("/api/mobile_command", {
      method: "POST",
      headers: { "X-Mobile-Token": TOKEN },
      body: JSON.stringify({
        cmd: "alarm_ring",
        payload: { sound, duration_sec, volume },
        expires_in_sec: Math.min(duration_sec + 120, 600),
        idempotency_key,
      }),
    }).catch((e) => ({ ok: false, error: e.message }));

    if (res.ok) {
      return {
        content: [{ type: "text", text: `已下发响铃命令（id: ${res.id}），手机会在几秒内开始响铃 ${duration_sec}s，音量 ${volume}%` }],
      };
    }
    return {
      content: [{ type: "text", text: `响铃命令下发失败：${res.error || JSON.stringify(res)}` }],
      isError: true,
    };
  }

  // ------------------------------------------------------------------
  // play_music：POST /api/mobile_command 入队 music_play 或 music_play_uri
  // ------------------------------------------------------------------
  if (name === "play_music") {
    const uri = (args.uri || "").trim();
    const cmd = uri ? "music_play_uri" : "music_play";
    const payload = uri ? { uri } : {};
    const idempotency_key = `music_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

    const res = await fetchGateway("/api/mobile_command", {
      method: "POST",
      headers: { "X-Mobile-Token": TOKEN },
      body: JSON.stringify({
        cmd,
        payload,
        expires_in_sec: 300,
        idempotency_key,
      }),
    }).catch((e) => ({ ok: false, error: e.message }));

    if (res.ok) {
      return {
        content: [{ type: "text", text: uri ? `已下发播放命令：${uri}` : "已下发播放命令，手机会开始播放当前音乐" }],
      };
    }
    return {
      content: [{ type: "text", text: `播放命令下发失败：${res.error || JSON.stringify(res)}` }],
      isError: true,
    };
  }

  // ------------------------------------------------------------------
  // pause_music：POST /api/mobile_command 入队 music_pause
  // ------------------------------------------------------------------
  if (name === "pause_music") {
    const idempotency_key = `pause_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

    const res = await fetchGateway("/api/mobile_command", {
      method: "POST",
      headers: { "X-Mobile-Token": TOKEN },
      body: JSON.stringify({
        cmd: "music_pause",
        payload: {},
        expires_in_sec: 60,
        idempotency_key,
      }),
    }).catch((e) => ({ ok: false, error: e.message }));

    if (res.ok) {
      return {
        content: [{ type: "text", text: "已下发暂停命令" }],
      };
    }
    return {
      content: [{ type: "text", text: `暂停命令下发失败：${res.error || JSON.stringify(res)}` }],
      isError: true,
    };
  }

  // ------------------------------------------------------------------
  // check_phone_command：GET /api/mobile_command/status
  // ------------------------------------------------------------------
  if (name === "check_phone_command") {
    const command_id = (args.command_id || "").trim();
    const qs = command_id ? `?command_id=${encodeURIComponent(command_id)}` : "";

    const res = await fetchGateway(`/api/mobile_command/status${qs}`, {
      headers: { "X-Mobile-Token": TOKEN },
    }).catch((e) => ({ error: e.message }));

    if (res.error) {
      return {
        content: [{ type: "text", text: `查询失败：${res.error}` }],
        isError: true,
      };
    }

    const pending = res.pending || [];
    const history = res.recent_history || [];
    const lines = [];
    if (pending.length) {
      lines.push("⏳ 等待执行：");
      for (const p of pending) {
        lines.push(`  - ${p.cmd} (id: ${p.id}, 创建: ${p.created_at})`);
      }
    }
    if (history.length) {
      lines.push("📋 最近记录：");
      for (const h of history) {
        lines.push(`  - ${h.cmd} → ${h.status} (${h.finished_at})`);
      }
    }
    if (!lines.length) lines.push("无待执行命令，无历史记录");

    return {
      content: [{ type: "text", text: lines.join("\n") }],
    };
  }

  // ------------------------------------------------------------------
  // save_memory：POST /api/memory/append（网关待实现）
  // ------------------------------------------------------------------
  if (name === "save_memory") {
    const content = (args.content || "").trim();
    if (!content) {
      return {
        content: [{ type: "text", text: "错误：content 不能为空" }],
        isError: true,
      };
    }
    const importance = typeof args.importance === "number" ? args.importance : 3;
    const tag = (args.tag || "CC").trim();

    const res = await fetchGateway("/api/memory/append", {
      method: "POST",
      body: JSON.stringify({ content, importance, tag }),
    }).catch((e) => ({ ok: false, error: e.message }));

    if (res.ok) {
      return {
        content: [{ type: "text", text: `✅ 已保存到动态层：${content}` }],
      };
    }
    return {
      content: [
        {
          type: "text",
          text:
            `❌ 保存失败（POST /api/memory/append 尚未实现）：` +
            (res.error || JSON.stringify(res)),
        },
      ],
      isError: true,
    };
  }

  // ------------------------------------------------------------------
  return {
    content: [{ type: "text", text: `未知工具：${name}` }],
    isError: true,
  };
});

// ---------------------------------------------------------------------------

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("[du-memory MCP] 已启动，等待 CC 调用...");
}

main().catch((e) => {
  console.error("[du-memory MCP] 启动失败:", e);
  process.exit(1);
});
