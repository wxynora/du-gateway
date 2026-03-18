# 渡の网关 - 配置（从环境变量读取，不硬编码敏感信息）
import os
from pathlib import Path

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
TARGET_AI_API_KEYS = [k.strip() for k in _TARGET_AI_KEYS_STR.split(",")] if _TARGET_AI_KEYS_STR else []

# 模型名匹配（用于多中转站）：请求的 model 含这些关键词时才走多目标 fallback，避免误转发
# 必含：逗号分隔，全部出现才匹配，默认 claude,opus（thinking 可有可无，不加在默认里）
_GATEWAY_MODEL_KEYWORDS_STR = os.environ.get("GATEWAY_MODEL_KEYWORDS", "claude,opus").strip()
GATEWAY_MODEL_KEYWORDS = [k.strip().lower() for k in _GATEWAY_MODEL_KEYWORDS_STR.split(",") if k.strip()]
# 版本关键词：逗号分隔，匹配「4 和 5 一起出现」或「4.5/4-5」等，默认 4.5,4-5
_GATEWAY_MODEL_KEYWORDS_VERSION_STR = os.environ.get("GATEWAY_MODEL_KEYWORDS_VERSION", "4.5,4-5").strip()
GATEWAY_MODEL_KEYWORDS_VERSION = [k.strip().lower() for k in _GATEWAY_MODEL_KEYWORDS_VERSION_STR.split(",") if k.strip()]

# 模型列表兜底：上游没有 /v1/models 或拉取失败时，返回此列表（逗号分隔），RikkaHub 才能显示模型
_GATEWAY_MODELS_STR = os.environ.get("GATEWAY_MODELS", "").strip()
GATEWAY_MODELS = [m.strip() for m in _GATEWAY_MODELS_STR.split(",") if m.strip()] if _GATEWAY_MODELS_STR else []


def model_matches_gateway_keywords(model_str: str) -> bool:
    """
    请求的 model 是否匹配「claude opus 4.5/4-5 thinking」等关键词，用于多中转站 fallback。
    规则：必含 GATEWAY_MODEL_KEYWORDS 全部；版本为「4 和 5 一起出现」或含 4.5/4-5 等；不区分大小写。
    """
    if not model_str or not isinstance(model_str, str):
        return False
    m = model_str.lower()
    if GATEWAY_MODEL_KEYWORDS and not all(k in m for k in GATEWAY_MODEL_KEYWORDS):
        return False
    if GATEWAY_MODEL_KEYWORDS_VERSION:
        # 含 4.5 或 4-5 等整段，或同时含 4 和 5
        if not (any(v in m for v in GATEWAY_MODEL_KEYWORDS_VERSION) or ("4" in m and "5" in m)):
            return False
    return True


# 聊天响应缓存：几分钟内相同请求直接返缓存，不调上游省费用（仅非流式）
CHAT_CACHE_ENABLED = os.environ.get("CHAT_CACHE_ENABLED", "1").strip().lower() in ("1", "true", "yes")
CHAT_CACHE_TTL_SECONDS = int(os.environ.get("CHAT_CACHE_TTL_SECONDS", "300"))  # 默认 5 分钟
CHAT_CACHE_MAX_SIZE = int(os.environ.get("CHAT_CACHE_MAX_SIZE", "500"))

# DeepSeek：窗口总结
DEEPSEEK_API_URL = os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

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
DYNAMIC_MEMORY_DAYS_VALID = 7

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

# “老婆隔多久回我”的提示：超过阈值才注入（分钟）
REPLY_GAP_THRESHOLD_MINUTES = int(os.environ.get("REPLY_GAP_THRESHOLD_MINUTES", "30"))
# 本地持久化：记录网关“上一次收到 user 回复”的时间（北京时间 ISO）
LAST_USER_REPLY_FILE = DATA_DIR / "last_user_reply.json"

# Telegram Bot（接入方案见 docs/主动发消息与Telegram完整方案.md）
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
# Telegram Webhook：网关接收更新的 secret（可选）。若设置了，Telegram 会在请求头携带 X-Telegram-Bot-Api-Secret-Token
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
# Bot 调网关的 base URL（如 http://127.0.0.1:5000 或公网网关地址）
TELEGRAM_GATEWAY_URL = os.environ.get("TELEGRAM_GATEWAY_URL", "http://127.0.0.1:5000").strip().rstrip("/")
# Telegram MiniApp（WebApp）对外入口：仅用于 ReplyKeyboard 的 web_app 按钮（Telegram 强制要求 HTTPS）
# 说明：不要用它来让 Bot 调用网关；Bot 调网关请继续用 TELEGRAM_GATEWAY_URL（可保持 127.0.0.1）
TELEGRAM_WEBAPP_URL = os.environ.get("TELEGRAM_WEBAPP_URL", "").strip().rstrip("/")
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

# Telegram 主动发消息（调度器）
TELEGRAM_PROACTIVE_ENABLED = os.environ.get("TELEGRAM_PROACTIVE_ENABLED", "").strip().lower() in ("1", "true", "yes")
TELEGRAM_PROACTIVE_TARGET_USER_ID = int(os.environ.get("TELEGRAM_PROACTIVE_TARGET_USER_ID", "0") or "0")
TELEGRAM_PROACTIVE_INTERVAL_MINUTES = int(os.environ.get("TELEGRAM_PROACTIVE_INTERVAL_MINUTES", "30"))
# 禁扰：北京时间 00:00–07:30（可改成例如 0:00-7:30）
TELEGRAM_PROACTIVE_QUIET_START_HM = os.environ.get("TELEGRAM_PROACTIVE_QUIET_START_HM", "00:00").strip()
TELEGRAM_PROACTIVE_QUIET_END_HM = os.environ.get("TELEGRAM_PROACTIVE_QUIET_END_HM", "07:30").strip()
# 概率模型：P = min(1, base + k_per_hour * hours_since_last)
TELEGRAM_PROACTIVE_BASE_P = float(os.environ.get("TELEGRAM_PROACTIVE_BASE_P", "0.05"))
TELEGRAM_PROACTIVE_K_PER_HOUR = float(os.environ.get("TELEGRAM_PROACTIVE_K_PER_HOUR", "0.03"))
# 渡决策标记：不联系时必须只输出该串
TELEGRAM_PROACTIVE_NO_CONTACT_TOKEN = os.environ.get("TELEGRAM_PROACTIVE_NO_CONTACT_TOKEN", "NO_CONTACT").strip() or "NO_CONTACT"
# 若用户在此分钟数内发过消息（正在聊天），则本 tick 不主动发，默认 30 分钟
TELEGRAM_PROACTIVE_SKIP_IF_ACTIVE_MINUTES = int(float(os.environ.get("TELEGRAM_PROACTIVE_SKIP_IF_ACTIVE_MINUTES", "30") or "30"))

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

# -------------------- Telegram Mini App（手机端运维面板） --------------------
# 静态站点目录：由 Flask 直接托管 /miniapp
MINIAPP_STATIC_DIR = BASE_DIR / "miniapp_static"

# 鉴权：Telegram WebApp initData 校验（推荐开启）
MINIAPP_TELEGRAM_AUTH_ENABLED = os.environ.get("MINIAPP_TELEGRAM_AUTH_ENABLED", "1").strip().lower() in ("1", "true", "yes")
# initData 允许的最大时效（秒），避免旧链接被长期复用；默认 10 分钟
MINIAPP_INITDATA_MAX_AGE_SECONDS = int(os.environ.get("MINIAPP_INITDATA_MAX_AGE_SECONDS", "600"))

# IP 白名单（CIDR/单 IP，逗号分隔）。留空则不限制 IP。
# 示例：MINIAPP_IP_ALLOWLIST=127.0.0.1,10.0.0.0/8,192.168.0.0/16
MINIAPP_IP_ALLOWLIST = [x.strip() for x in os.environ.get("MINIAPP_IP_ALLOWLIST", "").split(",") if x.strip()]
# 若在反代后面（Nginx/Caddy），可开启信任 X-Forwarded-For
MINIAPP_TRUST_PROXY = os.environ.get("MINIAPP_TRUST_PROXY", "").strip().lower() in ("1", "true", "yes")

# 日志文件路径：用于 Mini App 手机端查看；默认读当前工作目录下 gateway.log
MINIAPP_LOG_FILE = os.environ.get("MINIAPP_LOG_FILE", "gateway.log").strip()
