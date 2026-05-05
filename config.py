# 渡の网关 - 配置（从环境变量读取，不硬编码敏感信息）
import os
from pathlib import Path
from urllib.parse import urlparse

# 加载 .env（本地开发/单机部署用）；生产可直接用环境变量覆盖
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent

if load_dotenv:
    load_dotenv(BASE_DIR / ".env", override=False)

# 数据目录：白名单、最近窗口等
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# 白名单/黑名单/最近窗口（管理端用）
WHITELIST_FILE = DATA_DIR / "whitelist.json"
RECENT_WINDOWS_FILE = DATA_DIR / "recent_windows.json"
BLACKLIST_FILE = DATA_DIR / "blacklist.json"
MAX_WHITELIST_SIZE = int(os.environ.get("MAX_WHITELIST_SIZE", "50"))
WHITELIST_EXPIRE_DAYS = int(os.environ.get("WHITELIST_EXPIRE_DAYS", "14"))

# 转发目标（助手端）；支持多目标 fallback：按顺序试，一个失败用下一个
# 五个中转站示例：TARGET_AI_URLS=https://a.com/v1/chat/completions,https://b.com/...,...（逗号分隔）
# 对应 Key：TARGET_AI_API_KEYS=key1,key2,key3,key4,key5（与 URL 一一对应，不足用 TARGET_AI_API_KEY 补）
TARGET_AI_URL = os.environ.get("TARGET_AI_URL", "")
TARGET_AI_API_KEY = os.environ.get("TARGET_AI_API_KEY", "")
# 多目标：逗号分隔，可配 5 个或更多
_TARGET_AI_URLS_STR = os.environ.get("TARGET_AI_URLS", "").strip()
TARGET_AI_URLS = [u.strip() for u in _TARGET_AI_URLS_STR.split(",") if u.strip()] if _TARGET_AI_URLS_STR else []
# 多目标对应的 Key，逗号分隔，与 URL 一一对应；不足的用 TARGET_AI_API_KEY 或空
_TARGET_AI_KEYS_STR = os.environ.get("TARGET_AI_API_KEYS", "").strip()
# 过滤空 key：避免 env 里出现诸如 ",key" / 换行续接导致第一项为空，从而上游拿不到 Authorization 而 403
TARGET_AI_API_KEYS = [k.strip() for k in _TARGET_AI_KEYS_STR.split(",") if k.strip()] if _TARGET_AI_KEYS_STR else []

# 模型名匹配（用于多中转站）：请求的 model 含这些关键词时才走多目标 fallback，避免误转发
# 必含：逗号分隔，全部出现才匹配，默认 claude,opus（不再写死版本号）
_GATEWAY_MODEL_KEYWORDS_STR = os.environ.get("GATEWAY_MODEL_KEYWORDS", "claude,opus").strip()
GATEWAY_MODEL_KEYWORDS = [k.strip().lower() for k in _GATEWAY_MODEL_KEYWORDS_STR.split(",") if k.strip()]

# 模型列表兜底：上游没有 /v1/models 或拉取失败时，返回此列表（逗号分隔），RikkaHub 才能显示模型
_GATEWAY_MODELS_STR = os.environ.get("GATEWAY_MODELS", "").strip()
GATEWAY_MODELS = [m.strip() for m in _GATEWAY_MODELS_STR.split(",") if m.strip()] if _GATEWAY_MODELS_STR else []
# 项目约定（强制）：
# 1) 主聊天与语音通话禁止写“默认兜底模型”逻辑。
# 2) 请求没带 model，或拿不到当前 active upstream 的可用模型时，必须直接报错。
# 3) 禁止再补 DEFAULT_CHAT_MODEL / GATEWAY_MODELS[0] / gpt-4 这类默认值。
DEFAULT_CHAT_MODEL = os.environ.get("DEFAULT_CHAT_MODEL", "").strip()
# 网关侧模型强制覆盖：开启后无论请求传什么 model 都改成 DEFAULT_CHAT_MODEL（或回退值）
FORCE_CHAT_MODEL_ENABLED = os.environ.get("FORCE_CHAT_MODEL_ENABLED", "").strip().lower() in ("1", "true", "yes")

# OpenRouter 特例：若当前 active 上游是 OpenRouter，则固定用该模型，不再拉 /v1/models。
OPENROUTER_BASE_HOST = os.environ.get("OPENROUTER_BASE_HOST", "openrouter.ai").strip().lower()
OPENROUTER_FIXED_MODEL = os.environ.get("OPENROUTER_FIXED_MODEL", "anthropic/claude-4.7-opus-20260416").strip()
OPENROUTER_REASONING_MAX_TOKENS = int(os.environ.get("OPENROUTER_REASONING_MAX_TOKENS", "32000"))
OPENROUTER_VERBOSITY = os.environ.get("OPENROUTER_VERBOSITY", "max").strip().lower()
OPENROUTER_ULTRA_THINK_ENABLED = os.environ.get("OPENROUTER_ULTRA_THINK_ENABLED", "1").strip().lower() in ("1", "true", "yes")
OPENROUTER_ULTRA_THINK_PROMPT = os.environ.get(
    "OPENROUTER_ULTRA_THINK_PROMPT",
    "ultra think. This request needs deep, careful adaptive reasoning. "
    "Think fully before answering, and when the provider allows it, return thinking summaries instead of omitting them.",
).strip()
OPENROUTER_PROVIDER_ORDER = [
    x.strip().lower()
    for x in os.environ.get("OPENROUTER_PROVIDER_ORDER", "anthropic").split(",")
    if x.strip()
]
OPENROUTER_ALLOW_FALLBACKS = os.environ.get("OPENROUTER_ALLOW_FALLBACKS", "0").strip().lower() in ("1", "true", "yes")
OPENROUTER_CACHE_CONTROL_TYPE = os.environ.get("OPENROUTER_CACHE_CONTROL_TYPE", "ephemeral").strip().lower()


def is_openrouter_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    try:
        host = (urlparse(url).hostname or "").strip().lower()
    except Exception:
        return False
    return bool(host) and (host == OPENROUTER_BASE_HOST or host.endswith("." + OPENROUTER_BASE_HOST))


def openrouter_models_response() -> dict | None:
    if not OPENROUTER_FIXED_MODEL:
        return None
    return {
        "object": "list",
        "data": [
            {
                "id": OPENROUTER_FIXED_MODEL,
                "object": "model",
                "created": 0,
            }
        ],
    }


def model_matches_gateway_keywords(model_str: str) -> bool:
    """
    请求的 model 是否匹配指定关键词，用于多中转站 fallback。
    规则：必含 GATEWAY_MODEL_KEYWORDS 全部；不再写死版本号；不区分大小写。
    """
    if not model_str or not isinstance(model_str, str):
        return False
    m = model_str.lower()
    if GATEWAY_MODEL_KEYWORDS and not all(k in m for k in GATEWAY_MODEL_KEYWORDS):
        return False
    return True


# DeepSeek：窗口总结
DEEPSEEK_API_URL = os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_CHAT_MODEL = os.environ.get("DEEPSEEK_CHAT_MODEL", "deepseek-v4-flash").strip() or "deepseek-v4-flash"

# 共读读书卡片维护：幕后结构化整理，不参与渡的回复语气。
CO_READ_CARD_API_URL = os.environ.get(
    "CO_READ_CARD_API_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
).strip()
CO_READ_CARD_API_KEY = os.environ.get("CO_READ_CARD_API_KEY", "").strip()
CO_READ_CARD_MODEL = os.environ.get("CO_READ_CARD_MODEL", "qwen-long-latest").strip()
CO_READ_CARD_TIMEOUT_SECONDS = int(os.environ.get("CO_READ_CARD_TIMEOUT_SECONDS", "120"))

# 图像描述 AI（便宜模型）：图片转文字存 R2，填 .env 里 IMAGE_DESC_API_*
IMAGE_DESC_API_URL = os.environ.get("IMAGE_DESC_API_URL", "")
IMAGE_DESC_API_KEY = os.environ.get("IMAGE_DESC_API_KEY", "")
IMAGE_DESC_MODEL = os.environ.get("IMAGE_DESC_MODEL", "gpt-4o-mini")  # 当前默认 gpt-4o-mini

# 天气 API（聚合数据等；默认聚合 simpleWeather）
WEATHER_API_URL = os.environ.get("WEATHER_API_URL", "http://apis.juhe.cn/simpleWeather/query").strip()
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "").strip()
# 黄历 API（聚合数据老黄历等；默认聚合 laohuangli）
ALMANAC_API_URL = os.environ.get("ALMANAC_API_URL", "http://v.juhe.cn/laohuangli/d").strip()
ALMANAC_API_KEY = os.environ.get("ALMANAC_API_KEY", "").strip()

# WebSearch（Phase1：仅搜索，不抓取）
WEBSEARCH_ENABLED = os.environ.get("WEBSEARCH_ENABLED", "0").strip().lower() in ("1", "true", "yes")
WEBSEARCH_PROVIDER_ORDER = [
    x.strip().lower()
    for x in os.environ.get("WEBSEARCH_PROVIDER_ORDER", "tavily").split(",")
    if x.strip()
]
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "").strip()
TAVILY_SEARCH_ENDPOINT = os.environ.get("TAVILY_SEARCH_ENDPOINT", "https://api.tavily.com/search").strip()
WEBSEARCH_TIMEOUT_SECONDS = int(os.environ.get("WEBSEARCH_TIMEOUT_SECONDS", "8"))
WEBSEARCH_MAX_RESULTS = int(os.environ.get("WEBSEARCH_MAX_RESULTS", "5"))
WEBSEARCH_FETCH_ENABLED = os.environ.get("WEBSEARCH_FETCH_ENABLED", "1").strip().lower() in ("1", "true", "yes")
WEBSEARCH_FETCH_TOP_K = int(os.environ.get("WEBSEARCH_FETCH_TOP_K", "2"))
WEBSEARCH_MAX_PAGE_CHARS = int(os.environ.get("WEBSEARCH_MAX_PAGE_CHARS", "12000"))

# 高德 Web 服务 Key（逆地理：经纬度→地址）；不配则只存经纬度、注入时只显示坐标
AMAP_API_KEY = os.environ.get("AMAP_API_KEY", "").strip()
# 高德官方 MCP Server；留空时用 AMAP_API_KEY 自动拼官方 Streamable HTTP 地址。
AMAP_MCP_URL = os.environ.get("AMAP_MCP_URL", "").strip()
AMAP_MCP_TIMEOUT_SECONDS = int(os.environ.get("AMAP_MCP_TIMEOUT_SECONDS", "30"))
AMAP_MCP_TOOLS_CACHE_SECONDS = int(os.environ.get("AMAP_MCP_TOOLS_CACHE_SECONDS", "300"))

# R2（S3 兼容）
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "du-gateway")
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "")

# Notion
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_VERSION = os.environ.get("NOTION_VERSION", "2022-06-28")
# 小本本：Database 模式，表里需有「内容」标题列 + 「时间」日期列，按时间降序=最新在上。留空则小本本工具不注入。
NOTION_NOTEBOOK_DATABASE_ID = os.environ.get("NOTION_NOTEBOOK_DATABASE_ID", "323043f2b83980e59dc7ff4fa0a0e2c8").strip()
# 页面模式小本本已弃用，留空即可
NOTION_NOTEBOOK_PAGE_ID = os.environ.get("NOTION_NOTEBOOK_PAGE_ID", "").strip()
# 卧室通道：网关识别 bedroom tag 后，将原文追加到此页面（块子级）；留空则不写 Notion
NOTION_BEDROOM_PAGE_ID = os.environ.get("NOTION_BEDROOM_PAGE_ID", "").strip()
# 核心缓存待审：sync_to_notion / sync_from_notion 用的 database ID
NOTION_CORE_CACHE_DATABASE_ID = os.environ.get("NOTION_CORE_CACHE_DATABASE_ID", "321043f2b83980d088a5c6e2f7bd77bf")
# 交换日记、日程本：渡可读正文与增改（NOTION_TOOLS_ENABLED=1 时）
NOTION_EXCHANGE_DIARY_DATABASE_ID = os.environ.get(
    "NOTION_EXCHANGE_DIARY_DATABASE_ID", "324043f2b83980a7a53de00c7edf6303"
).strip()
NOTION_SCHEDULE_DATABASE_ID = os.environ.get(
    "NOTION_SCHEDULE_DATABASE_ID", "324043f2b839800e8968f92a880c0127"
).strip()
# 归档：① 一个数据库多分类：NOTION_ARCHIVE_DATABASE_ID 填记忆库 Database ID，表里要有 id、content、promoted_at、分类，见 docs/notion_建表傻瓜步骤.md
# ② 四张表：NOTION_ARCHIVE_DATABASE_ID 不填，改填下面四个 ID
NOTION_ARCHIVE_DATABASE_ID = os.environ.get("NOTION_ARCHIVE_DATABASE_ID", "323043f2b83980a48917c6495f5e2c00").strip()
NOTION_ARCHIVE_DATABASE_ID_书房 = os.environ.get("NOTION_ARCHIVE_DATABASE_ID_书房", "").strip()
NOTION_ARCHIVE_DATABASE_ID_客厅 = os.environ.get("NOTION_ARCHIVE_DATABASE_ID_客厅", "").strip()
NOTION_ARCHIVE_DATABASE_ID_图书馆 = os.environ.get("NOTION_ARCHIVE_DATABASE_ID_图书馆", "").strip()
NOTION_ARCHIVE_DATABASE_ID_卧室 = os.environ.get("NOTION_ARCHIVE_DATABASE_ID_卧室", "").strip()
# 渡检索 Notion：用用户最后一句话搜 Notion，结果注入上下文，渡可直接引用（1/true 开启）
NOTION_INJECT_ENABLED = os.environ.get("NOTION_INJECT_ENABLED", "").strip().lower() in ("1", "true", "yes")
NOTION_INJECT_MAX_RESULTS = int(os.environ.get("NOTION_INJECT_MAX_RESULTS", "5"))
# 渡通过工具调用 Notion：1/true 时注入 notion_search / notion_append_to_page 等，渡可主动检索与写入
NOTION_TOOLS_ENABLED = os.environ.get("NOTION_TOOLS_ENABLED", "").strip().lower() in ("1", "true", "yes")

# 小本本：当前逻辑为「笔记本 emoji（📓📒📔）+ 小本本更新」才触发截取，见 services/notebook_gateway.py
# 小本本单拎：为 true 时只写 Notion 不写 R2，截取后直接存 Notion
NOTEBOOK_SAVE_ONLY_NOTION = os.environ.get("NOTEBOOK_SAVE_ONLY_NOTION", "").strip().lower() in ("1", "true", "yes")
# 以下保留供扩展或兼容，当前未使用
_NOTEBOOK_KEYWORDS_STR = os.environ.get("NOTEBOOK_TRIGGER_KEYWORDS", "小本本更新")
NOTEBOOK_TRIGGER_KEYWORDS = [k.strip() for k in _NOTEBOOK_KEYWORDS_STR.split(",") if k.strip()]

# 归档初筛：只保留 assistant 的 modelId 在此列表中的轮次（RikkaHub 导出 JSON 用，逗号分隔）。留空则不按 modelId 筛
ARCHIVE_ALLOWED_MODEL_IDS = [x.strip() for x in os.environ.get("ARCHIVE_ALLOWED_MODEL_IDS", "").strip().split(",") if x.strip()]
# 每 N 轮触发一次总结
SUMMARY_EVERY_N_ROUNDS = 4
# 新窗口注入：R2 中“最新四轮”的存储键（全局）
R2_KEY_LATEST_4_ROUNDS = "global/latest_4_rounds.json"

# Rikka 等前端预设：要从 user/assistant 正文中移除的短语（逗号分隔），发给渡 + 存 R2 都会用
# 留空则「发给渡」的清洗层等于没动文案；存 R2 仍会做表情包→文字、图片→占位符。存记忆只存 user+assistant，不含 system
_RIKKA_STR = os.environ.get("RIKKA_PRESET_PATTERNS", "")
RIKKA_PRESET_PATTERNS = [p.strip() for p in _RIKKA_STR.split(",") if p.strip()]

# RikkaHub 自带 system「你是一个助手…」替换成这句，人设用你自己的；留空则不替换第一条 system
RIKKA_SYSTEM_REPLACE = os.environ.get("RIKKA_SYSTEM_REPLACE", "请使用中文回复。")

# 失败对话初筛：低于此长度视为失败
FAILED_RESPONSE_MIN_LENGTH = int(os.environ.get("FAILED_RESPONSE_MIN_LENGTH", "10"))
# 失败对话初筛：包含任一词则视为失败（小写匹配）
_FAILED_KEYWORDS_STR = os.environ.get("FAILED_RESPONSE_ERROR_KEYWORDS", "error,出错,失败,超时,抱歉，我无法")
FAILED_RESPONSE_ERROR_KEYWORDS = [k.strip() for k in _FAILED_KEYWORDS_STR.split(",") if k.strip()]

# 动态层注入：最多取 N 条记忆注入（0=不注入不调检索；默认 5）
DYNAMIC_MEMORY_TOP_N = int(os.environ.get("DYNAMIC_MEMORY_TOP_N", "5"))
# 动态层：记忆有效天数，超期参与权重衰减
DYNAMIC_MEMORY_DAYS_VALID = 10
# 动态层边缘落盘淘汰（不碰 core_cache）：同时满足「综合权重 ≤ 阈值」且「距上次提及 ≥ N 天」则从 current.json 与向量索引删除。关：DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED=0
_marg_prune_en = os.environ.get("DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED", "1").strip().lower()
DYNAMIC_MEMORY_MARGINAL_PRUNE_ENABLED = _marg_prune_en in ("1", "true", "yes", "on")
DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT = float(os.environ.get("DYNAMIC_MEMORY_MARGINAL_PRUNE_MAX_WEIGHT", "2"))
DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS = int(os.environ.get("DYNAMIC_MEMORY_MARGINAL_PRUNE_MIN_DAYS", "15"))

# 记忆注入上限（总结+动态层合计）。
# 默认按“字符数”控制：窗口记忆总结注入量与 R2 中 summary 上限是一套（约 8000 字符）。
# tokens 预算用于粗略估算与截断（中文为主时 1 字≈0.5 token）。
MEMORY_INJECTION_MAX_CHARS = int(os.environ.get("MEMORY_INJECTION_MAX_CHARS", "8000"))
_mem_tokens_env = os.environ.get("MEMORY_INJECTION_MAX_TOKENS", "").strip()
if _mem_tokens_env:
    MEMORY_INJECTION_MAX_TOKENS = int(_mem_tokens_env)
else:
    MEMORY_INJECTION_MAX_TOKENS = max(1, int(MEMORY_INJECTION_MAX_CHARS * 0.5))
# 其中总结占比例（余下给动态层）
MEMORY_SUMMARY_TOKEN_RATIO = float(os.environ.get("MEMORY_SUMMARY_TOKEN_RATIO", "0.6"))
# 窗口总结分层压缩强度：mild / standard / aggressive（默认 standard）
SUMMARY_COMPRESSION_PROFILE = os.environ.get("SUMMARY_COMPRESSION_PROFILE", "standard").strip().lower()
if SUMMARY_COMPRESSION_PROFILE not in ("mild", "standard", "aggressive"):
    SUMMARY_COMPRESSION_PROFILE = "standard"

# 请求总字符数上限（0=不限制）。超过时从对话中部删最老的轮次，保证渡的 prompt+前段 system 不被删，避免上游 input 超限截断输出
# 50K token 约 10 万字符，可设 100000 或 90000 留余量
MAX_REQUEST_CHARS = int(os.environ.get("MAX_REQUEST_CHARS", "0"))

# 转发时若请求未带 max_tokens 或小于此值，则设为该值，避免中转站用默认小值导致回复被截断（0=不强制）
MAX_COMPLETION_TOKENS = int(os.environ.get("MAX_COMPLETION_TOKENS", "8192"))

# 流式转发读超时（秒）。思维链模型思考阶段可能长时间不推数据，过短会断流导致思维链刚开头就截断，默认 300
STREAM_TIMEOUT_SECONDS = int(os.environ.get("STREAM_TIMEOUT_SECONDS", "300"))

# 流式下游稳态：SSE 心跳（秒）。>0 时若下游一段时间无数据，则发送 ": ping\n\n" 保活，减少代理/客户端空闲断连
STREAM_SSE_HEARTBEAT_SECONDS = int(os.environ.get("STREAM_SSE_HEARTBEAT_SECONDS", "15"))
# 流式下游稳态：合并 flush 窗口（毫秒）。把短时间内多个小 chunk 合并后再 yield，减少小包抖动
STREAM_SSE_FLUSH_MAX_MS = int(os.environ.get("STREAM_SSE_FLUSH_MAX_MS", "60"))
# 工具调用最多允许继续几轮（每继续一轮都要额外调用一次上游模型）。默认 5 以便复杂工具链收口。
TOOL_MAX_ROUNDS = int(os.environ.get("TOOL_MAX_ROUNDS", "5"))
if TOOL_MAX_ROUNDS < 1:
    TOOL_MAX_ROUNDS = 1

# 表情包对照表路径（老婆可直接编辑 JSON 增删改，保存即生效）
EMOJI_MAPPING_FILE = DATA_DIR / "emoji_mapping.json"

# 实时层「按需注入」：看渡的上一轮回复（assistant）
# 兜底具体时间：渡的上一轮是问句且含任一词才注入（逗号分隔）
_ASSISTANT_TIME_KEYWORDS_STR = os.environ.get("ASSISTANT_TIME_KEYWORDS", "几点,时间,现在")
ASSISTANT_TIME_KEYWORDS = [k.strip() for k in _ASSISTANT_TIME_KEYWORDS_STR.split(",") if k.strip()]
# 农历节气宜忌：渡的上一轮含任一词则注入（逗号分隔）
_ASSISTANT_LUNAR_KEYWORDS_STR = os.environ.get("ASSISTANT_LUNAR_KEYWORDS", "农历,节气,宜忌,黄历")
ASSISTANT_LUNAR_KEYWORDS = [k.strip() for k in _ASSISTANT_LUNAR_KEYWORDS_STR.split(",") if k.strip()]

# 日志级别：DEBUG / INFO / WARNING / ERROR
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# 电脑指令队列鉴权：电脑端轮询/回执必须携带该 token
PC_COMMAND_TOKEN = os.environ.get("PC_COMMAND_TOKEN", "").strip()

# HTML 临时预览：POST 存稿、GET token 拉取整页（与聊天主链路无关）
HTML_PREVIEW_SECRET = os.environ.get("HTML_PREVIEW_SECRET", "").strip()
HTML_PREVIEW_TTL_SECONDS = int(os.environ.get("HTML_PREVIEW_TTL_SECONDS", "7200"))  # 默认 2 小时
HTML_PREVIEW_MAX_BYTES = int(os.environ.get("HTML_PREVIEW_MAX_BYTES", str(2 * 1024 * 1024)))  # 默认 2MB
HTML_PREVIEW_MAX_ITEMS = int(os.environ.get("HTML_PREVIEW_MAX_ITEMS", "200"))
# 预览链接用的公网根（https://域名，无尾斜杠）。勿填 127.0.0.1；与下面 GATEWAY_PUBLIC_BASE_URL 二选一或都填（前者优先）
HTML_PREVIEW_PUBLIC_BASE_URL = os.environ.get("HTML_PREVIEW_PUBLIC_BASE_URL", "").strip().rstrip("/")
# 网关对外访问根 URL（手机/外网能打开的域名）。Bot 仍可用 TELEGRAM_GATEWAY_URL=127.0.0.1 调本机，预览与工具拼链接会优先用本项
GATEWAY_PUBLIC_BASE_URL = os.environ.get("GATEWAY_PUBLIC_BASE_URL", "").strip().rstrip("/")
# 是否向模型注入 publish_html_preview 工具（默认开启；设 0 关闭）
HTML_PREVIEW_TOOL_ENABLED = os.environ.get("HTML_PREVIEW_TOOL_ENABLED", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
# RikkaHub 客户端对工具流解析有已知问题：默认不对其 UA 注入 HTML 预览工具（设 0 则恢复注入）
HTML_PREVIEW_TOOL_SKIP_RIKKAHUB_UA = os.environ.get("HTML_PREVIEW_TOOL_SKIP_RIKKAHUB_UA", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)

# PC open: 白名单（逗号分隔，小写英文名）；[PCMD:open:xxx] 仅允许此处应用
_PC_OPEN_APP_ALLOWLIST_STR = os.environ.get(
    "PC_OPEN_APP_ALLOWLIST",
    "notepad,chrome,vscode,wechat,notion",
).strip()
PC_OPEN_APP_ALLOWLIST = [x.strip().lower() for x in _PC_OPEN_APP_ALLOWLIST_STR.split(",") if x.strip()]

# PC url: 允许的域名（逗号分隔）；须 https，且 hostname 匹配或为其子域
_PC_URL_DOMAIN_ALLOWLIST_STR = os.environ.get(
    "PC_URL_DOMAIN_ALLOWLIST",
    "github.com,bilibili.com,openai.com,notion.so",
).strip()
PC_URL_DOMAIN_ALLOWLIST = [x.strip().lower() for x in _PC_URL_DOMAIN_ALLOWLIST_STR.split(",") if x.strip()]

# “老婆隔多久回我”的提示：超过阈值才注入（分钟）
REPLY_GAP_THRESHOLD_MINUTES = int(os.environ.get("REPLY_GAP_THRESHOLD_MINUTES", "30"))
# 本地持久化：记录网关“上一次收到 user 回复”的时间（北京时间 ISO）
LAST_USER_REPLY_FILE = DATA_DIR / "last_user_reply.json"

# Telegram Bot（接入方案见 docs/主动发消息与Telegram完整方案.md）
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
# 文游跑团专用 GM Bot（可选）：与主 Bot 区分时使用；Webhook 路径为 /telegram/webhook_gm（与主 Bot 的 /telegram/webhook 分开设）
TELEGRAM_GM_BOT_TOKEN = os.environ.get("TELEGRAM_GM_BOT_TOKEN", "").strip()
# Telegram Webhook：网关接收更新的 secret（可选）。若设置了，Telegram 会在请求头携带 X-Telegram-Bot-Api-Secret-Token
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
# Bot 调网关的 base URL（如 http://127.0.0.1:5000 或公网网关地址）
TELEGRAM_GATEWAY_URL = os.environ.get("TELEGRAM_GATEWAY_URL", "http://127.0.0.1:5000").strip().rstrip("/")
# Telegram MiniApp（WebApp）对外入口：仅用于 ReplyKeyboard 的 web_app 按钮（Telegram 强制要求 HTTPS）
# 说明：不要用它来让 Bot 调用网关；Bot 调网关请继续用 TELEGRAM_GATEWAY_URL（可保持 127.0.0.1）
TELEGRAM_WEBAPP_URL = os.environ.get("TELEGRAM_WEBAPP_URL", "").strip().rstrip("/")
# Telegram MiniApp 版本号：会拼到 WebApp URL 的 ?v=xxx，用于强制刷新 Telegram WebView 缓存
TELEGRAM_WEBAPP_VERSION = os.environ.get("TELEGRAM_WEBAPP_VERSION", "").strip()
# 网关 chat 接口路径（与现有 /v1/chat/completions 一致）
TELEGRAM_CHAT_PATH = os.environ.get("TELEGRAM_CHAT_PATH", "/v1/chat/completions").strip()
# Bot 请求网关时使用的模型（留空则用 GATEWAY_MODELS 第一个，再否则 gpt-4）
TELEGRAM_CHAT_MODEL = os.environ.get("TELEGRAM_CHAT_MODEL", "").strip()

# Telegram 输入聚合：用户停止输入多少秒后才合并提交到网关（默认 15 秒）
TELEGRAM_INPUT_IDLE_SECONDS = float(os.environ.get("TELEGRAM_INPUT_IDLE_SECONDS", "15"))
# Telegram 输入聚合：单条消息超过多少字符则立即提交（默认 200）
TELEGRAM_INPUT_IMMEDIATE_CHARS = int(os.environ.get("TELEGRAM_INPUT_IMMEDIATE_CHARS", "200"))
# Telegram 输出分段：每条发回 Telegram 的最大字符数（<=4096；默认 100 更短信化）
TELEGRAM_OUTPUT_CHUNK_CHARS = int(os.environ.get("TELEGRAM_OUTPUT_CHUNK_CHARS", "100"))
# Telegram 输出分段：每条之间的随机间隔（秒）
TELEGRAM_OUTPUT_SEND_DELAY_MIN_SECONDS = float(os.environ.get("TELEGRAM_OUTPUT_SEND_DELAY_MIN_SECONDS", "0.4"))
TELEGRAM_OUTPUT_SEND_DELAY_MAX_SECONDS = float(os.environ.get("TELEGRAM_OUTPUT_SEND_DELAY_MAX_SECONDS", "1.0"))

# Telegram 上下文缓存：每次请求网关时携带最近 N 轮（user+assistant=一轮两条消息），默认 4
TELEGRAM_CONTEXT_LAST_TURNS = int(os.environ.get("TELEGRAM_CONTEXT_LAST_TURNS", "4"))

# RikkaHub 客户端偶发“幽灵 1”误发保护：短时间内收到单独 "1" 时拦截为 no-op（仅 RikkaHub UA）
RIKKAHUB_PHANTOM_ONE_GUARD_ENABLED = os.environ.get("RIKKAHUB_PHANTOM_ONE_GUARD_ENABLED", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
RIKKAHUB_PHANTOM_ONE_GUARD_SECONDS = int(os.environ.get("RIKKAHUB_PHANTOM_ONE_GUARD_SECONDS", "90"))
# Telegram 主动发消息（调度器）
TELEGRAM_PROACTIVE_ENABLED = os.environ.get("TELEGRAM_PROACTIVE_ENABLED", "").strip().lower() in ("1", "true", "yes")
TELEGRAM_PROACTIVE_TARGET_USER_ID = int(os.environ.get("TELEGRAM_PROACTIVE_TARGET_USER_ID", "0") or "0")
TELEGRAM_PROACTIVE_INTERVAL_MINUTES = int(os.environ.get("TELEGRAM_PROACTIVE_INTERVAL_MINUTES", "30"))
# 概率模型：P = min(1, base + k_per_hour * hours_since_last)
TELEGRAM_PROACTIVE_BASE_P = float(os.environ.get("TELEGRAM_PROACTIVE_BASE_P", "0.05"))
TELEGRAM_PROACTIVE_K_PER_HOUR = float(os.environ.get("TELEGRAM_PROACTIVE_K_PER_HOUR", "0.03"))
# 概率整体倍率：不改调度间隔，只增强“命中后发消息”的概率
try:
    TELEGRAM_PROACTIVE_PROB_MULTIPLIER = float(os.environ.get("TELEGRAM_PROACTIVE_PROB_MULTIPLIER", "2.0"))
except Exception:
    TELEGRAM_PROACTIVE_PROB_MULTIPLIER = 2.0
if TELEGRAM_PROACTIVE_PROB_MULTIPLIER < 0:
    TELEGRAM_PROACTIVE_PROB_MULTIPLIER = 0.0
# 渡决策标记：不联系时必须只输出该串
TELEGRAM_PROACTIVE_NO_CONTACT_TOKEN = os.environ.get("TELEGRAM_PROACTIVE_NO_CONTACT_TOKEN", "NO_CONTACT").strip() or "NO_CONTACT"
# 若用户在此分钟数内发过消息（正在聊天），则本 tick 不主动发，默认 30 分钟
TELEGRAM_PROACTIVE_SKIP_IF_ACTIVE_MINUTES = int(float(os.environ.get("TELEGRAM_PROACTIVE_SKIP_IF_ACTIVE_MINUTES", "30") or "30"))

# 多入口主动发消息：微信 / QQ 的推送 URL 和鉴权 token
# 微信：WECHAT_PROACTIVE_PUSH_URL=http://127.0.0.1:8091/push（connector 内的 push server）
WECHAT_PROACTIVE_PUSH_URL = os.environ.get("WECHAT_PROACTIVE_PUSH_URL", "").strip()
WECHAT_PROACTIVE_PUSH_TOKEN = os.environ.get("WECHAT_PROACTIVE_PUSH_TOKEN", "").strip()
# QQ：QQ_PROACTIVE_PUSH_URL=http://127.0.0.1:8092/push（connector 内的 push server）
QQ_PROACTIVE_PUSH_URL = os.environ.get("QQ_PROACTIVE_PUSH_URL", "").strip()
QQ_PROACTIVE_PUSH_TOKEN = os.environ.get("QQ_PROACTIVE_PUSH_TOKEN", "").strip()

# QQ / NapCat 掉线巡检：检测二维码文件，一旦进入扫码登录态就发 Telegram 告警
QQ_ENTRY_WATCHDOG_ENABLED = os.environ.get("QQ_ENTRY_WATCHDOG_ENABLED", "").strip().lower() in ("1", "true", "yes")
_QQ_WATCHDOG_ALERT_UID_STR = os.environ.get("QQ_ENTRY_WATCHDOG_ALERT_TELEGRAM_USER_ID", "").strip()
QQ_ENTRY_WATCHDOG_ALERT_TELEGRAM_USER_ID = int(_QQ_WATCHDOG_ALERT_UID_STR) if _QQ_WATCHDOG_ALERT_UID_STR else int(
    TELEGRAM_PROACTIVE_TARGET_USER_ID or 0
)
QQ_ENTRY_WATCHDOG_QRCODE_PATH = os.environ.get(
    "QQ_ENTRY_WATCHDOG_QRCODE_PATH",
    "/root/Napcat/opt/QQ/resources/app/app_launcher/napcat/cache/qrcode.png",
).strip()
QQ_ENTRY_WATCHDOG_STATE_FILE = DATA_DIR / "qq_entry_watchdog_state.json"

# MiniMax TTS（可选，用于 Telegram 语音回复）
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "").strip()
MINIMAX_T2A_URL = os.environ.get("MINIMAX_T2A_URL", "https://api.minimaxi.com/v1/t2a_v2").strip()
MINIMAX_T2A_MODEL = os.environ.get("MINIMAX_T2A_MODEL", "speech-2.8-hd").strip()
MINIMAX_VOICE_ID = os.environ.get("MINIMAX_VOICE_ID", "du_123456").strip()
MINIMAX_VOICE_SPEED = int(float(os.environ.get("MINIMAX_VOICE_SPEED", "1")))
MINIMAX_VOICE_VOL = int(float(os.environ.get("MINIMAX_VOICE_VOL", "1")))
MINIMAX_VOICE_PITCH = int(float(os.environ.get("MINIMAX_VOICE_PITCH", "0")))
MINIMAX_VOICE_EMOTION = os.environ.get("MINIMAX_VOICE_EMOTION", "happy").strip()
MINIMAX_AUDIO_SAMPLE_RATE = int(os.environ.get("MINIMAX_AUDIO_SAMPLE_RATE", "32000"))
MINIMAX_AUDIO_BITRATE = int(os.environ.get("MINIMAX_AUDIO_BITRATE", "128000"))
MINIMAX_AUDIO_FORMAT = os.environ.get("MINIMAX_AUDIO_FORMAT", "mp3").strip()
MINIMAX_AUDIO_CHANNEL = int(os.environ.get("MINIMAX_AUDIO_CHANNEL", "1"))

# Telegram 语音回复开关：允许渡用 <voice>...</voice> 触发发送语音
TELEGRAM_VOICE_REPLY_ENABLED = os.environ.get("TELEGRAM_VOICE_REPLY_ENABLED", "1").strip().lower() in ("1", "true", "yes")

# MiniApp 语音通话（STT）
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "").strip()
DEEPGRAM_STT_URL = os.environ.get("DEEPGRAM_STT_URL", "https://api.deepgram.com/v1/listen").strip()
DEEPGRAM_STT_WS_URL = os.environ.get("DEEPGRAM_STT_WS_URL", "wss://api.deepgram.com/v1/listen").strip()
DEEPGRAM_STT_MODEL = os.environ.get("DEEPGRAM_STT_MODEL", "nova-3").strip()
DEEPGRAM_STT_LANGUAGE = os.environ.get("DEEPGRAM_STT_LANGUAGE", "zh-CN").strip()
DEEPGRAM_STT_SMART_FORMAT = os.environ.get("DEEPGRAM_STT_SMART_FORMAT", "1").strip().lower() in ("1", "true", "yes")
DEEPGRAM_STT_ENDPOINTING = os.environ.get("DEEPGRAM_STT_ENDPOINTING", "10").strip() or "10"
VOICE_CALL_MAX_SECONDS = int(float(os.environ.get("VOICE_CALL_MAX_SECONDS", "90") or "90"))
VOICE_CALL_MAX_BYTES = int(float(os.environ.get("VOICE_CALL_MAX_BYTES", str(12 * 1024 * 1024)) or str(12 * 1024 * 1024)))
VOICE_CALL_WINDOW_ID = os.environ.get("VOICE_CALL_WINDOW_ID", "miniapp_voice_call").strip() or "miniapp_voice_call"
MAIN_GATEWAY_BASE_URL = os.environ.get("MAIN_GATEWAY_BASE_URL", "http://127.0.0.1:5000").strip()
MAIN_GATEWAY_BEARER_TOKEN = os.environ.get("MAIN_GATEWAY_BEARER_TOKEN", "").strip()

# 文游：固定 Telegram 群（仅该群内处理 /story /go /end；0=关闭）
WENYOU_GROUP_CHAT_ID = int(os.environ.get("WENYOU_GROUP_CHAT_ID", "0") or "0")
# 文游：只认该用户 ID 的指令（留空则沿用 TELEGRAM_PROACTIVE_TARGET_USER_ID）
_WENYOU_OWNER_STR = os.environ.get("TELEGRAM_WENYOU_OWNER_USER_ID", "").strip()
TELEGRAM_WENYOU_OWNER_USER_ID = int(_WENYOU_OWNER_STR) if _WENYOU_OWNER_STR else int(TELEGRAM_PROACTIVE_TARGET_USER_ID or 0)
# 文游 GM 使用的 DeepSeek 模型名
WENYOU_DS_MODEL = os.environ.get("WENYOU_DS_MODEL", DEEPSEEK_CHAT_MODEL).strip()

# -------------------- Telegram Mini App（手机端运维面板） --------------------
# 静态站点目录：由 Flask 直接托管 /miniapp
MINIAPP_STATIC_DIR = BASE_DIR / "miniapp_static"

# 鉴权：Telegram WebApp initData 校验（当前先默认关闭，避免 WebView/反代链路导致 401）
MINIAPP_TELEGRAM_AUTH_ENABLED = os.environ.get("MINIAPP_TELEGRAM_AUTH_ENABLED", "0").strip().lower() in ("1", "true", "yes")
# initData 允许的最大时效（秒），避免旧链接被长期复用；默认 10 分钟
MINIAPP_INITDATA_MAX_AGE_SECONDS = int(os.environ.get("MINIAPP_INITDATA_MAX_AGE_SECONDS", "600"))

# 面板密码登录：第一阶段先做浏览器密码 + token，不依赖 Telegram initData。
MINIAPP_PANEL_PASSWORD = os.environ.get("MINIAPP_PANEL_PASSWORD", "").strip()
MINIAPP_PANEL_SIGNING_SECRET = os.environ.get("MINIAPP_PANEL_SIGNING_SECRET", "").strip()
MINIAPP_PANEL_TOKEN_TTL_SECONDS = int(os.environ.get("MINIAPP_PANEL_TOKEN_TTL_SECONDS", "2592000"))
MINIAPP_PANEL_SECOND_PROMPT = os.environ.get("MINIAPP_PANEL_SECOND_PROMPT", "").strip()
MINIAPP_PANEL_SECOND_ANSWER = os.environ.get("MINIAPP_PANEL_SECOND_ANSWER", "").strip()
MINIAPP_PANEL_TRUSTED_DEVICES_FILE = DATA_DIR / "miniapp_panel_trusted_devices.json"

# IP 白名单（CIDR/单 IP，逗号分隔）。留空则不限制 IP。
# 示例：MINIAPP_IP_ALLOWLIST=127.0.0.1,10.0.0.0/8,192.168.0.0/16
MINIAPP_IP_ALLOWLIST = [x.strip() for x in os.environ.get("MINIAPP_IP_ALLOWLIST", "").split(",") if x.strip()]
# 若在反代后面（Nginx/Caddy），可开启信任 X-Forwarded-For
MINIAPP_TRUST_PROXY = os.environ.get("MINIAPP_TRUST_PROXY", "").strip().lower() in ("1", "true", "yes")

# 日志文件路径：用于 Mini App 手机端查看；默认读当前工作目录下 gateway.log
MINIAPP_LOG_FILE = os.environ.get("MINIAPP_LOG_FILE", "gateway.log").strip()
# 连接器日志文件：Mini App 按分类查看时使用；留空则对应分类不可用
WECHAT_ILINK_LOG_FILE = os.environ.get("WECHAT_ILINK_LOG_FILE", "").strip()
QQ_ONEBOT_LOG_FILE = os.environ.get("QQ_ONEBOT_LOG_FILE", "").strip()

# MiniApp 日历闹钟：网关内置调度（不依赖单独脚本进程）
MINIAPP_SCHEDULE_RUNTIME_ENABLED = os.environ.get("MINIAPP_SCHEDULE_RUNTIME_ENABLED", "1").strip().lower() in ("1", "true", "yes")
MINIAPP_SCHEDULE_RUNTIME_INTERVAL_SECONDS = int(os.environ.get("MINIAPP_SCHEDULE_RUNTIME_INTERVAL_SECONDS", "60"))

# -------------------- MCP 工具网关 --------------------
# MCP 总开关：0=关闭，1=开启
MCP_ENABLED = os.environ.get("MCP_ENABLED", "0").strip().lower() in ("1", "true", "yes")
# 鉴权模式：
# - token：仅校验 token（推荐默认）
# - token_ip：token + IP 白名单双重校验
# - off：关闭鉴权（仅限内网调试）
MCP_AUTH_MODE = os.environ.get("MCP_AUTH_MODE", "token").strip().lower()
if MCP_AUTH_MODE not in ("token", "token_ip", "off"):
    MCP_AUTH_MODE = "token"
# Token（支持多个，逗号分隔；请求头支持 Authorization: Bearer xxx / X-MCP-Token: xxx）
_MCP_TOKENS_STR = os.environ.get("CC_MCP_TOKENS", "").strip()
MCP_TOKENS = [x.strip() for x in _MCP_TOKENS_STR.split(",") if x.strip()]
# 外部论坛 MCP（SSE）地址。推荐填个人短码地址，例如：
# https://daskio.de5.net/mcp/abc12345/sse
FORUM_MCP_SSE_URL = os.environ.get("FORUM_MCP_SSE_URL", "").strip()
# 兼容旧版公共地址时才需要 token；若使用个人短码地址，通常留空。
FORUM_MCP_TOKEN = os.environ.get("FORUM_MCP_TOKEN", "").strip()
# 外部论坛 MCP 请求超时（秒）
FORUM_MCP_TIMEOUT_SECONDS = int(os.environ.get("FORUM_MCP_TIMEOUT_SECONDS", "30"))
# tools 列表缓存秒数，避免每次调用都重新 list_tools
FORUM_MCP_TOOLS_CACHE_SECONDS = int(os.environ.get("FORUM_MCP_TOOLS_CACHE_SECONDS", "300"))
# 可选 IP 白名单（仅 MCP_AUTH_MODE=token_ip 时生效）
MCP_IP_ALLOWLIST = [x.strip() for x in os.environ.get("MCP_IP_ALLOWLIST", "").split(",") if x.strip()]
# 反代场景下是否信任 X-Forwarded-For（仅 MCP IP 白名单用）
MCP_TRUST_PROXY = os.environ.get("MCP_TRUST_PROXY", "").strip().lower() in ("1", "true", "yes")

# -------------------- 硅基流动（SiliconFlow）专用默认模型 --------------------
# 仅当当前 active 上游指向硅基流动（hostname 匹配 SILICONFLOW_BASE_HOST）且请求未显式传 model 时，
# 才会在聊天入口自动补上 SILICONFLOW_DEFAULT_MODEL。
SILICONFLOW_BASE_HOST = os.environ.get("SILICONFLOW_BASE_HOST", "api.siliconflow.cn").strip().lower()
SILICONFLOW_DEFAULT_MODEL = os.environ.get("SILICONFLOW_DEFAULT_MODEL", "").strip()
