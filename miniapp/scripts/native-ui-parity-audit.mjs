#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";
import postcss from "postcss";
import ts from "typescript";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const miniappRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(miniappRoot, "..");
const defaultNativeRoot = path.resolve(repoRoot, "..", "sumitalk-android-native");

const paritySlices = [
  {
    priority: "P0",
    name: "App shell and bottom navigation",
    source: ["src/ui/AppShell.tsx", "src/ui/BottomNav.tsx"],
    native: [
      "app/src/main/java/com/sumitalk/nativeapp/ui/SumiTalkApp.kt",
      "app/src/main/java/com/sumitalk/nativeapp/ui/navigation/SumiTalkHomeHost.kt",
      "app/src/main/java/com/sumitalk/nativeapp/ui/navigation/BottomCapsuleNav.kt",
    ],
  },
  {
    priority: "P0",
    name: "Conversation list",
    source: ["src/ui/ChatsHome.tsx", "src/ui/AppShell.tsx"],
    native: ["app/src/main/java/com/sumitalk/nativeapp/ui/tabs/ConversationHomeScreen.kt"],
  },
  {
    priority: "P0",
    name: "Chat screen and message presentation",
    source: ["src/ui/MainChatScreen.tsx", "src/ui/ChatPresentation.tsx", "src/ui/sumitalkSystemCards.tsx"],
    native: [
      "app/src/main/java/com/sumitalk/nativeapp/ui/chat/ChatScreen.kt",
      "app/src/main/java/com/sumitalk/nativeapp/ui/chat/ChatSystemCards.kt",
      "app/src/main/java/com/sumitalk/nativeapp/ui/chat/ChatAppearance.kt",
    ],
  },
  {
    priority: "P1",
    name: "Settings home and shared rows",
    source: ["src/ui/AppShell.tsx", "src/ui/SettingsRows.tsx"],
    native: [
      "app/src/main/java/com/sumitalk/nativeapp/ui/tabs/SettingsHomeScreen.kt",
      "app/src/main/java/com/sumitalk/nativeapp/ui/detail/settings/SettingsDetailComponents.kt",
    ],
  },
  {
    priority: "P1",
    name: "Personalization and appearance",
    source: ["src/ui/PersonalizationScreen.tsx", "src/ui/chatAppearance.ts"],
    native: [
      "app/src/main/java/com/sumitalk/nativeapp/ui/detail/settings/PersonalizationScreen.kt",
      "app/src/main/java/com/sumitalk/nativeapp/ui/detail/settings/PersonalizationComponents.kt",
      "app/src/main/java/com/sumitalk/nativeapp/ui/chat/ChatAppearance.kt",
    ],
  },
  {
    priority: "P1",
    name: "Prompt and diagnostics settings",
    source: ["src/ui/PromptManagerScreen.tsx", "src/ui/DiagnosticsScreen.tsx"],
    native: [
      "app/src/main/java/com/sumitalk/nativeapp/ui/detail/settings/PromptManagerScreen.kt",
      "app/src/main/java/com/sumitalk/nativeapp/ui/detail/settings/SystemDiagnosticsScreen.kt",
    ],
  },
  {
    priority: "P2",
    name: "Companion home and detail pages",
    source: ["src/ui/AppShell.tsx", "src/ui/tabs/StayWithDuScreen.tsx"],
    native: [
      "app/src/main/java/com/sumitalk/nativeapp/ui/tabs/CompanionHomeScreen.kt",
      "app/src/main/java/com/sumitalk/nativeapp/ui/detail/CompanionDetailCommon.kt",
    ],
  },
  {
    priority: "P2",
    name: "Feature and game pages",
    source: ["src/ui/tabs"],
    native: ["app/src/main/java/com/sumitalk/nativeapp/ui/detail"],
  },
];

function usage() {
  return `Usage:
  node ./scripts/native-ui-parity-audit.mjs [options]

Options:
  --native-root <path>     Native Android repository root.
  --output <path>          Write the Markdown report instead of stdout.
  --json-output <path>     Also write the machine-readable manifest.
  --kotlin-output <path>   Generate a Kotlin token scaffold from MiniApp tokens.
  --kotlin-package <name>  Package for the token scaffold.
  --help                   Show this help.

The command is read-only unless an output option is supplied. It never edits
the native repository in place.`;
}

function parseArgs(argv) {
  const out = {
    nativeRoot: defaultNativeRoot,
    output: "",
    jsonOutput: "",
    kotlinOutput: "",
    kotlinPackage: "com.sumitalk.nativeapp.ui.theme",
    help: false,
  };
  const aliases = {
    "native-root": "nativeRoot",
    output: "output",
    "json-output": "jsonOutput",
    "kotlin-output": "kotlinOutput",
    "kotlin-package": "kotlinPackage",
  };
  for (let index = 0; index < argv.length; index += 1) {
    const raw = argv[index];
    if (raw === "--help" || raw === "-h") {
      out.help = true;
      continue;
    }
    if (!raw.startsWith("--")) throw new Error(`Unknown argument: ${raw}`);
    const equalsIndex = raw.indexOf("=");
    const flag = raw.slice(2, equalsIndex >= 0 ? equalsIndex : undefined);
    const key = aliases[flag];
    if (!key) throw new Error(`Unknown option: --${flag}`);
    const value = equalsIndex >= 0 ? raw.slice(equalsIndex + 1) : argv[index + 1];
    if (!value || (equalsIndex < 0 && value.startsWith("--"))) {
      throw new Error(`Missing value for --${flag}`);
    }
    out[key] = value;
    if (equalsIndex < 0) index += 1;
  }
  if (out.nativeRoot) out.nativeRoot = path.resolve(repoRoot, out.nativeRoot);
  for (const key of ["output", "jsonOutput", "kotlinOutput"]) {
    if (out[key]) out[key] = path.resolve(process.cwd(), out[key]);
  }
  return out;
}

function walkFiles(root, extensions) {
  const files = [];
  if (!fs.existsSync(root)) return files;
  const visit = (current) => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (entry.name === "node_modules" || entry.name === "build" || entry.name === ".gradle" || entry.name === ".git") continue;
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) visit(fullPath);
      else if (extensions.has(path.extname(entry.name))) files.push(fullPath);
    }
  };
  visit(root);
  return files.sort();
}

function toPosix(filePath) {
  return filePath.split(path.sep).join("/");
}

function relativeTo(root, filePath) {
  return toPosix(path.relative(root, filePath));
}

function increment(map, key, file = "") {
  if (!key) return;
  const current = map.get(key) || { count: 0, files: new Set() };
  current.count += 1;
  if (file) current.files.add(file);
  map.set(key, current);
}

function mapToRows(map) {
  return [...map.entries()]
    .map(([value, details]) => ({ value, count: details.count, files: [...details.files].sort() }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
}

function flattenObject(value, prefix = "", out = {}) {
  if (typeof value === "string" || typeof value === "number") {
    out[prefix] = String(value);
    return out;
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) return out;
  for (const [key, child] of Object.entries(value)) {
    flattenObject(child, prefix ? `${prefix}.${key}` : key, out);
  }
  return out;
}

function normalizeHexColor(raw) {
  const text = String(raw || "").trim().toUpperCase();
  const match = text.match(/^#([0-9A-F]{3,8})$/);
  if (!match) return "";
  let hex = match[1];
  if (hex.length === 3 || hex.length === 4) hex = [...hex].map((part) => part + part).join("");
  if (hex.length !== 6 && hex.length !== 8) return "";
  if (hex.length === 8 && hex.endsWith("FF")) hex = hex.slice(0, 6);
  return `#${hex}`;
}

function extractHexColors(text) {
  const colors = new Set();
  for (const match of String(text || "").matchAll(/#[0-9a-fA-F]{3,8}\b/g)) {
    const color = normalizeHexColor(match[0]);
    if (color) colors.add(color);
  }
  return colors;
}

function nativeColorToCss(raw) {
  const match = String(raw || "").match(/0x([0-9A-Fa-f]{6,8})/);
  if (!match) return "";
  const hex = match[1].toUpperCase();
  if (hex.length === 6) return normalizeHexColor(`#${hex}`);
  return normalizeHexColor(`#${hex.slice(2)}${hex.slice(0, 2)}`);
}

function classCategory(token) {
  const base = String(token || "").split(":").at(-1) || "";
  if (/^(flex|grid|block|inline|hidden|contents|table|fixed|absolute|relative|sticky|inset|top-|right-|bottom-|left-|z-)/.test(base)) return "layout";
  if (/^(p[trblxy]?|m[trblxy]?|space-[xy]|gap)-/.test(base)) return "spacing";
  if (/^(text-|font-|leading-|tracking-|whitespace-|break-|truncate|line-clamp-)/.test(base)) return "typography";
  if (/^(bg-|text-|border-|ring-|outline-|fill-|stroke-|from-|via-|to-)/.test(base)) return "color";
  if (/^(rounded|shadow|opacity|blur|backdrop|mix-blend|drop-shadow)/.test(base)) return "surface";
  if (/^(w-|h-|min-w|max-w|min-h|max-h|size-|aspect-)/.test(base)) return "size";
  if (/^(animate-|transition|duration-|delay-|ease-|transform|translate-|scale-|rotate-)/.test(base)) return "motion";
  return "other";
}

function isHighRiskClass(token) {
  const base = String(token || "").split(":").at(-1) || "";
  return /^(fixed|sticky|absolute|backdrop-|blur|animate-|transition|overflow-|z-\[|translate-|scale-|rotate-|pointer-events|touch-|snap-)/.test(base)
    || /^(shadow|bg)-\[/.test(base)
    || /\b(vh|vw|dvh|dvw)\b/.test(base);
}

function collectStaticStrings(node, sourceFile, out) {
  if (!node) return;
  if (ts.isStringLiteralLike(node)) {
    out.push(node.text);
    return;
  }
  if (ts.isTemplateExpression(node)) {
    out.push(node.head.text);
    for (const span of node.templateSpans) {
      collectStaticStrings(span.expression, sourceFile, out);
      out.push(span.literal.text);
    }
    return;
  }
  if (ts.isJsxExpression(node)) {
    collectStaticStrings(node.expression, sourceFile, out);
    return;
  }
  ts.forEachChild(node, (child) => collectStaticStrings(child, sourceFile, out));
}

function staticValue(node, sourceFile) {
  if (!node) return "<dynamic>";
  if (ts.isStringLiteralLike(node) || ts.isNumericLiteral(node)) return node.text;
  if (node.kind === ts.SyntaxKind.TrueKeyword) return "true";
  if (node.kind === ts.SyntaxKind.FalseKeyword) return "false";
  if (ts.isPrefixUnaryExpression(node) && ts.isNumericLiteral(node.operand)) return node.getText(sourceFile);
  return "<dynamic>";
}

function propertyName(node, sourceFile) {
  if (!node) return "unknown";
  if (ts.isIdentifier(node) || ts.isStringLiteralLike(node) || ts.isNumericLiteral(node)) return node.text;
  return node.getText(sourceFile);
}

function containsJsx(node) {
  let found = false;
  const visit = (child) => {
    if (found) return;
    if (ts.isJsxElement(child) || ts.isJsxSelfClosingElement(child) || ts.isJsxFragment(child)) {
      found = true;
      return;
    }
    ts.forEachChild(child, visit);
  };
  visit(node);
  return found;
}

function scanTsxFile(filePath) {
  const text = fs.readFileSync(filePath, "utf8");
  const sourceFile = ts.createSourceFile(filePath, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const classTokens = [];
  const inlineStyles = [];
  const assets = new Set();
  const components = new Set();
  let dynamicClassNames = 0;
  let dynamicStyleValues = 0;

  const visit = (node) => {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      const specifier = node.moduleSpecifier.text;
      if (/\.(png|jpe?g|webp|gif|svg|ttf|otf|woff2?|mp3|wav|flac)$/i.test(specifier) || specifier.includes("/assets/")) assets.add(specifier);
    }
    if (ts.isFunctionDeclaration(node) && node.name && /^[A-Z]/.test(node.name.text) && containsJsx(node)) {
      components.add(node.name.text);
    }
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && /^[A-Z]/.test(node.name.text) && node.initializer && containsJsx(node.initializer)) {
      components.add(node.name.text);
    }
    if (ts.isJsxAttribute(node)) {
      const name = node.name.getText(sourceFile);
      if (name === "className") {
        const fragments = [];
        collectStaticStrings(node.initializer, sourceFile, fragments);
        for (const fragment of fragments) {
          for (const token of fragment.split(/\s+/).map((part) => part.trim()).filter(Boolean)) classTokens.push(token);
        }
        if (node.initializer && !ts.isStringLiteral(node.initializer) && fragments.length === 0) dynamicClassNames += 1;
      }
      if (name === "style" && node.initializer && ts.isJsxExpression(node.initializer) && ts.isObjectLiteralExpression(node.initializer.expression)) {
        for (const property of node.initializer.expression.properties) {
          if (!ts.isPropertyAssignment(property)) {
            dynamicStyleValues += 1;
            continue;
          }
          const key = propertyName(property.name, sourceFile);
          const value = staticValue(property.initializer, sourceFile);
          inlineStyles.push({ property: key, value });
          if (value === "<dynamic>") dynamicStyleValues += 1;
        }
      }
      if (["src", "href", "poster"].includes(name)) {
        const fragments = [];
        collectStaticStrings(node.initializer, sourceFile, fragments);
        for (const fragment of fragments) {
          if (/\.(png|jpe?g|webp|gif|svg|ttf|otf|woff2?|mp3|wav|flac)(\?|$)/i.test(fragment) || fragment.includes("/assets/")) assets.add(fragment);
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
  return {
    text,
    classTokens,
    inlineStyles,
    assets: [...assets].sort(),
    components: [...components].sort(),
    dynamicClassNames,
    dynamicStyleValues,
  };
}

async function scanSource() {
  const tailwindModule = await import(pathToFileURL(path.join(miniappRoot, "tailwind.config.js")).href);
  const extend = tailwindModule.default?.theme?.extend || {};
  const tailwind = {
    colors: flattenObject(extend.colors || {}),
    borderRadius: flattenObject(extend.borderRadius || {}),
    boxShadow: flattenObject(extend.boxShadow || {}),
  };

  const cssPath = path.join(miniappRoot, "src", "styles.css");
  const cssText = fs.readFileSync(cssPath, "utf8");
  const cssRoot = postcss.parse(cssText, { from: cssPath });
  const cssVariables = {};
  const cssProperties = new Map();
  const keyframes = new Set();
  cssRoot.walkDecls((declaration) => {
    if (declaration.prop.startsWith("--")) cssVariables[declaration.prop] = declaration.value;
    increment(cssProperties, declaration.prop, "src/styles.css");
  });
  cssRoot.walkAtRules((rule) => {
    if (/keyframes$/i.test(rule.name)) keyframes.add(rule.params);
  });

  const files = walkFiles(path.join(miniappRoot, "src"), new Set([".tsx", ".ts"]));
  const classTokens = new Map();
  const inlineStyleProperties = new Map();
  const sourceColors = new Set(extractHexColors(cssText));
  const fileRows = [];
  const assets = new Set();
  const components = [];
  let dynamicClassNames = 0;
  let dynamicStyleValues = 0;

  for (const filePath of files) {
    const relative = relativeTo(miniappRoot, filePath);
    const result = scanTsxFile(filePath);
    for (const token of result.classTokens) increment(classTokens, token, relative);
    for (const style of result.inlineStyles) {
      increment(inlineStyleProperties, style.property, relative);
      for (const color of extractHexColors(style.value)) sourceColors.add(color);
    }
    for (const color of extractHexColors(result.text)) sourceColors.add(color);
    for (const asset of result.assets) assets.add(asset);
    for (const component of result.components) components.push({ component, file: relative });
    dynamicClassNames += result.dynamicClassNames;
    dynamicStyleValues += result.dynamicStyleValues;
    const highRisk = result.classTokens.filter(isHighRiskClass).length;
    const arbitrary = result.classTokens.filter((token) => token.includes("[")).length;
    fileRows.push({
      file: relative,
      classTokens: result.classTokens.length,
      arbitrary,
      highRisk,
      inlineStyles: result.inlineStyles.length,
      dynamicStyles: result.dynamicStyleValues,
      components: result.components.length,
      score: highRisk * 3 + arbitrary * 2 + result.inlineStyles.length + result.dynamicStyleValues * 2,
    });
  }
  for (const value of Object.values(tailwind.colors)) {
    const color = normalizeHexColor(value);
    if (color) sourceColors.add(color);
  }

  const classRows = mapToRows(classTokens);
  const categoryCounts = {};
  for (const row of classRows) {
    const category = classCategory(row.value);
    categoryCounts[category] = (categoryCounts[category] || 0) + row.count;
  }
  return {
    root: miniappRoot,
    files: fileRows.sort((a, b) => b.score - a.score || a.file.localeCompare(b.file)),
    classTokens: classRows,
    categoryCounts,
    inlineStyleProperties: mapToRows(inlineStyleProperties),
    dynamicClassNames,
    dynamicStyleValues,
    cssVariables,
    cssProperties: mapToRows(cssProperties),
    keyframes: [...keyframes].sort(),
    tailwind,
    colors: [...sourceColors].sort(),
    assets: [...assets].sort(),
    components: components.sort((a, b) => a.file.localeCompare(b.file) || a.component.localeCompare(b.component)),
  };
}

function scanNative(nativeRoot) {
  const sourceRoot = path.join(nativeRoot, "app", "src", "main", "java");
  const resourceRoot = path.join(nativeRoot, "app", "src", "main", "res");
  const files = [
    ...walkFiles(sourceRoot, new Set([".kt", ".java"])),
    ...walkFiles(resourceRoot, new Set([".xml"])),
  ].sort();
  const colors = new Map();
  const dpValues = new Map();
  const spValues = new Map();
  const cornerValues = new Map();
  const filesReport = [];
  for (const filePath of files) {
    const relative = relativeTo(nativeRoot, filePath);
    const text = fs.readFileSync(filePath, "utf8");
    let colorCount = 0;
    let dpCount = 0;
    let spCount = 0;
    let cornerCount = 0;
    let shadowCount = 0;
    if (path.extname(filePath) === ".xml") {
      for (const color of extractHexColors(text)) {
        increment(colors, color, relative);
        colorCount += 1;
      }
      for (const match of text.matchAll(/(-?\d+(?:\.\d+)?)dp\b/g)) {
        increment(dpValues, match[1], relative);
        dpCount += 1;
      }
      for (const match of text.matchAll(/(-?\d+(?:\.\d+)?)sp\b/g)) {
        increment(spValues, match[1], relative);
        spCount += 1;
      }
      for (const match of text.matchAll(/(?:cornerRadius|android:radius)\s*=\s*"([^"]+)"/g)) {
        increment(cornerValues, match[1].trim(), relative);
        cornerCount += 1;
      }
    } else {
      for (const match of text.matchAll(/Color\(\s*(0x[0-9A-Fa-f]{6,8})\s*\)/g)) {
        const color = nativeColorToCss(match[1]);
        increment(colors, color, relative);
        colorCount += 1;
      }
      for (const match of text.matchAll(/(-?\d+(?:\.\d+)?)\.dp\b/g)) {
        increment(dpValues, match[1], relative);
        dpCount += 1;
      }
      for (const match of text.matchAll(/(-?\d+(?:\.\d+)?)\.sp\b/g)) {
        increment(spValues, match[1], relative);
        spCount += 1;
      }
      for (const match of text.matchAll(/RoundedCornerShape\(\s*([^\n)]{1,80})\)/g)) {
        increment(cornerValues, match[1].trim(), relative);
        cornerCount += 1;
      }
      shadowCount += (text.match(/\.shadow\s*\(/g) || []).length;
      shadowCount += (text.match(/shadowElevation\s*=/g) || []).length;
    }
    const materialThemeUses = (text.match(/MaterialTheme\./g) || []).length;
    const score = colorCount * 3 + cornerCount * 2 + shadowCount * 2 + dpCount + spCount;
    if (score > 0) {
      filesReport.push({
        file: relative,
        colors: colorCount,
        dp: dpCount,
        sp: spCount,
        corners: cornerCount,
        shadows: shadowCount,
        materialThemeUses,
        score,
      });
    }
  }
  return {
    root: nativeRoot,
    files: filesReport.sort((a, b) => b.score - a.score || a.file.localeCompare(b.file)),
    colors: mapToRows(colors),
    dpValues: mapToRows(dpValues),
    spValues: mapToRows(spValues),
    cornerValues: mapToRows(cornerValues),
  };
}

function pathExistsOrDirectory(root, item) {
  return fs.existsSync(path.join(root, item));
}

function parityStatus(nativeRoot) {
  return paritySlices.map((slice) => ({
    ...slice,
    sourceMissing: slice.source.filter((item) => !pathExistsOrDirectory(miniappRoot, item)),
    nativeMissing: slice.native.filter((item) => !pathExistsOrDirectory(nativeRoot, item)),
  }));
}

function markdownCell(value) {
  return String(value ?? "").replace(/\|/g, "\\|").replace(/\r?\n/g, " ");
}

function table(headers, rows) {
  if (!rows.length) return "_None._\n";
  const lines = [
    `| ${headers.map(markdownCell).join(" | ")} |`,
    `| ${headers.map(() => "---").join(" | ")} |`,
  ];
  for (const row of rows) lines.push(`| ${row.map(markdownCell).join(" | ")} |`);
  return `${lines.join("\n")}\n`;
}

function shortList(values, limit = 12) {
  const rows = values.slice(0, limit);
  return rows.length ? rows.map((value) => `\`${value}\``).join(", ") : "_None_";
}

function buildReport(manifest) {
  const { source, native, parity } = manifest;
  const sourceColorSet = new Set(source.colors);
  const nativeColorSet = new Set(native.colors.map((row) => row.value));
  const sharedColors = [...sourceColorSet].filter((color) => nativeColorSet.has(color)).sort();
  const sourceOnlyColors = [...sourceColorSet].filter((color) => !nativeColorSet.has(color)).sort();
  const nativeOnlyColors = [...nativeColorSet].filter((color) => !sourceColorSet.has(color)).sort();
  const highRiskClasses = source.classTokens.filter((row) => isHighRiskClass(row.value));
  const lines = [];
  lines.push("# SumiTalk native UI parity audit", "");
  lines.push("> Source code is the specification. Screenshots are validation evidence, not a substitute for reading TSX/CSS.", "");
  lines.push("## Scope", "");
  lines.push(`- MiniApp: \`${toPosix(source.root)}\``);
  lines.push(`- Native app: \`${toPosix(native.root)}\``);
  lines.push("- This report is read-only and does not rewrite Kotlin files.", "");
  lines.push("## Summary", "");
  lines.push(table(
    ["Metric", "Value"],
    [
      ["MiniApp TS/TSX files", source.files.length],
      ["Detected React components", source.components.length],
      ["Distinct Tailwind classes", source.classTokens.length],
      ["Arbitrary-value class uses", source.files.reduce((sum, row) => sum + row.arbitrary, 0)],
      ["Inline style declarations", source.files.reduce((sum, row) => sum + row.inlineStyles, 0)],
      ["CSS keyframes", source.keyframes.length],
      ["Native files with visual literals", native.files.length],
      ["Native hard-coded color uses", native.colors.reduce((sum, row) => sum + row.count, 0)],
      ["Shared exact hex colors", sharedColors.length],
      ["Source-only hex colors", sourceOnlyColors.length],
      ["Native-only hex colors", nativeOnlyColors.length],
    ],
  ));
  lines.push("## MiniApp design tokens", "");
  lines.push("### Tailwind colors", "");
  lines.push(table(["Token", "Value"], Object.entries(source.tailwind.colors).map(([key, value]) => [key, value])));
  lines.push("### Radius, shadow, and CSS tokens", "");
  lines.push(table(
    ["Kind", "Token", "Value"],
    [
      ...Object.entries(source.tailwind.borderRadius).map(([key, value]) => ["radius", key, value]),
      ...Object.entries(source.tailwind.boxShadow).map(([key, value]) => ["shadow", key, value]),
      ...Object.entries(source.cssVariables).map(([key, value]) => ["CSS variable", key, value]),
    ],
  ));
  lines.push("### Exact palette comparison", "");
  lines.push(`- Shared: ${shortList(sharedColors, 20)}`);
  lines.push(`- Present only in MiniApp source: ${shortList(sourceOnlyColors, 30)}`);
  lines.push(`- Present only in native source: ${shortList(nativeOnlyColors, 30)}`, "");
  lines.push("## Source translation hotspots", "");
  lines.push(table(
    ["File", "Score", "Classes", "Arbitrary", "High risk", "Inline", "Dynamic"],
    source.files.slice(0, 30).map((row) => [row.file, row.score, row.classTokens, row.arbitrary, row.highRisk, row.inlineStyles, row.dynamicStyles]),
  ));
  lines.push("High-risk classes include fixed/absolute positioning, blur, animation, overflow, transforms, viewport units, and arbitrary shadows/backgrounds.", "");
  lines.push(table(
    ["High-risk class", "Uses", "Files"],
    highRiskClasses.slice(0, 40).map((row) => [row.value, row.count, row.files.slice(0, 4).join(", ")]),
  ));
  lines.push("## Native hard-code hotspots", "");
  lines.push(table(
    ["File", "Score", "Colors", "dp", "sp", "Corners", "Shadows", "Theme uses"],
    native.files.slice(0, 35).map((row) => [row.file, row.score, row.colors, row.dp, row.sp, row.corners, row.shadows, row.materialThemeUses]),
  ));
  lines.push("## Migration slices", "");
  lines.push(table(
    ["Priority", "Slice", "MiniApp", "Native", "Status"],
    parity.map((slice) => [
      slice.priority,
      slice.name,
      slice.source.join("<br>"),
      slice.native.join("<br>"),
      slice.sourceMissing.length || slice.nativeMissing.length
        ? `missing source=${slice.sourceMissing.length}, native=${slice.nativeMissing.length}`
        : "mapped",
    ]),
  ));
  lines.push("## Required workflow", "");
  lines.push("1. Generate the Kotlin token scaffold and move visible colors/radii out of page files.");
  lines.push("2. Align P0 shared components before changing feature pages.");
  lines.push("3. Translate TSX structure and state variants; do not redesign from memory.");
  lines.push("4. Re-run this report until page-level hard-coded visual values are documented exceptions.");
  lines.push("5. Build, lint, install, and compare screenshots at the same viewport and font scale.", "");
  lines.push("## Known static-analysis limits", "");
  lines.push(`- Dynamic className expressions without static strings: ${source.dynamicClassNames}.`);
  lines.push(`- Dynamic inline style values: ${source.dynamicStyleValues}.`);
  lines.push("- Browser font metrics, backdrop blur, multi-layer CSS shadows, pseudo-elements, canvas, and arbitrary HTML still require manual native implementation.");
  lines.push("- A matching numeric value does not prove semantic parity; inspect the mapped component before accepting it.", "");
  return `${lines.join("\n")}\n`;
}

function kotlinIdentifier(raw) {
  const words = String(raw || "")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .split(/[^A-Za-z0-9]+/)
    .filter(Boolean);
  let result = words.map((word) => word[0].toUpperCase() + word.slice(1)).join("") || "Token";
  if (/^\d/.test(result)) result = `Token${result}`;
  return result;
}

function cssHexToCompose(raw) {
  const normalized = normalizeHexColor(raw);
  if (!normalized) return "";
  const hex = normalized.slice(1);
  if (hex.length === 6) return `0xFF${hex}`;
  return `0x${hex.slice(6)}${hex.slice(0, 6)}`;
}

function escapeKotlinString(raw) {
  return String(raw).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\r?\n/g, "\\n");
}

function buildKotlinTokens(source, packageName) {
  const lines = [
    "// Generated by miniapp/scripts/native-ui-parity-audit.mjs.",
    "// Treat MiniApp source as the specification; review before committing.",
    `package ${packageName}`,
    "",
    "import androidx.compose.ui.graphics.Color",
    "import androidx.compose.ui.unit.dp",
    "",
    "object MiniAppSourceColors {",
  ];
  for (const [key, value] of Object.entries(source.tailwind.colors)) {
    const compose = cssHexToCompose(value);
    if (compose) lines.push(`    val ${kotlinIdentifier(key)} = Color(${compose})`);
  }
  lines.push("}", "", "object MiniAppSourceRadii {");
  for (const [key, value] of Object.entries(source.tailwind.borderRadius)) {
    const match = String(value).match(/^(-?\d+(?:\.\d+)?)px$/);
    if (match) lines.push(`    val ${kotlinIdentifier(key)} = ${match[1]}.dp`);
  }
  lines.push("}", "", "object MiniAppCssShadowReference {");
  for (const [key, value] of Object.entries(source.tailwind.boxShadow)) {
    lines.push(`    const val ${kotlinIdentifier(key)} = "${escapeKotlinString(value)}"`);
  }
  for (const [key, value] of Object.entries(source.cssVariables).filter(([name]) => name.includes("shadow") || name.includes("inset"))) {
    lines.push(`    const val ${kotlinIdentifier(key)} = "${escapeKotlinString(value)}"`);
  }
  lines.push("}", "");
  return lines.join("\n");
}

function writeText(filePath, content) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content, "utf8");
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  if (!fs.existsSync(options.nativeRoot)) throw new Error(`Native root not found: ${options.nativeRoot}`);
  const source = await scanSource();
  const native = scanNative(options.nativeRoot);
  const manifest = {
    schemaVersion: 1,
    source,
    native,
    parity: parityStatus(options.nativeRoot),
  };
  const report = buildReport(manifest);
  if (options.output) writeText(options.output, report);
  else process.stdout.write(report);
  if (options.jsonOutput) writeText(options.jsonOutput, `${JSON.stringify(manifest, null, 2)}\n`);
  if (options.kotlinOutput) writeText(options.kotlinOutput, buildKotlinTokens(source, options.kotlinPackage));
  if (options.output) process.stdout.write(`Wrote Markdown report: ${options.output}\n`);
  if (options.jsonOutput) process.stdout.write(`Wrote JSON manifest: ${options.jsonOutput}\n`);
  if (options.kotlinOutput) process.stdout.write(`Wrote Kotlin token scaffold: ${options.kotlinOutput}\n`);
}

main().catch((error) => {
  process.stderr.write(`native-ui-parity-audit: ${error?.stack || error}\n`);
  process.exitCode = 1;
});
