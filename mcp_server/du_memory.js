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
        "拉取渡的窗口总结（渡的回忆）。" +
        "新任务开始前调用，获取与 Telegram 共享的最新记忆状态。",
      inputSchema: {
        type: "object",
        properties: {},
        required: [],
      },
    },
    {
      name: "cc_log",
      description:
        "将 CC 侧的重要进展写入对话历史，会被窗口总结自然消化。" +
        "用于记录开发进展、重要决策等需要持久化的信息。",
      inputSchema: {
        type: "object",
        properties: {
          content: {
            type: "string",
            description: "要记录的内容",
          },
          tag: {
            type: "string",
            description: "标签，如 开发、心动、重要，默认 CC",
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
    const summaryRes = await fetchGateway("/summary").catch((e) => ({ error: e.message }));

    let text;
    if (summaryRes.error) {
      text = `⚠️ 读取失败：${summaryRes.error}`;
    } else if (summaryRes.has_summary) {
      text = summaryRes.summary;
    } else {
      text = "（暂无总结）";
    }

    return {
      content: [{ type: "text", text }],
    };
  }

  // ------------------------------------------------------------------
  // cc_log：POST /api/cc_log 写入对话历史
  // ------------------------------------------------------------------
  if (name === "cc_log") {
    const content = (args.content || "").trim();
    if (!content) {
      return {
        content: [{ type: "text", text: "错误：content 不能为空" }],
        isError: true,
      };
    }
    const tag = (args.tag || "CC").trim();

    const res = await fetchGateway("/api/cc_log", {
      method: "POST",
      body: JSON.stringify({ content, tag }),
    }).catch((e) => ({ ok: false, error: e.message }));

    if (res.ok) {
      return {
        content: [{ type: "text", text: `已写入对话历史（轮次 ${res.round_index}），会被下次总结消化` }],
      };
    }
    return {
      content: [
        { type: "text", text: `写入失败：${res.error || JSON.stringify(res)}` },
      ],
      isError: true,
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
