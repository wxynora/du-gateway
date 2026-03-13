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

# 白名单/黑名单/最近窗口（管理端用，聊天流程已不再按窗口 ID 判定）
WHITELIST_FILE = DATA_DIR / "whitelist.json"
RECENT_WINDOWS_FILE = DATA_DIR / "recent_windows.json"
BLACKLIST_FILE = DATA_DIR / "blacklist.json"
# 只允许这些 assistant_id 走网关后续进程（记忆、总结等）；逗号分隔；留空=不限制
_ALLOWED_ASSISTANT_IDS_STR = os.environ.get("ALLOWED_ASSISTANT_IDS", "").strip()
ALLOWED_ASSISTANT_IDS = [a.strip() for a in _ALLOWED_ASSISTANT_IDS_STR.split(",") if a.strip()] if _ALLOWED_ASSISTANT_IDS_STR else []
# 白名单：最多保留窗口数，超了按 last_seen 最旧踢；超过 N 天未出现也踢
MAX_WHITELIST_SIZE = int(os.environ.get("MAX_WHITELIST_SIZE", "50"))
WHITELIST_EXPIRE_DAYS = int(os.environ.get("WHITELIST_EXPIRE_DAYS", "14"))

# 转发目标（助手端）；支持多目标 fallback：按顺序试，一个失败用下一个
TARGET_AI_URL = os.environ.get("TARGET_AI_URL", "")
TARGET_AI_API_KEY = os.environ.get("TARGET_AI_API_KEY", "")
# 多目标：逗号分隔，例如 "https://a.com/v1/chat/completions,https://b.com/v1/chat/completions"
_TARGET_AI_URLS_STR = os.environ.get("TARGET_AI_URLS", "").strip()
TARGET_AI_URLS = [u.strip() for u in _TARGET_AI_URLS_STR.split(",") if u.strip()] if _TARGET_AI_URLS_STR else []
# 多目标对应的 Key，逗号分隔，与 URL 一一对应；不足的用 TARGET_AI_API_KEY 或空
_TARGET_AI_KEYS_STR = os.environ.get("TARGET_AI_API_KEYS", "").strip()
TARGET_AI_API_KEYS = [k.strip() for k in _TARGET_AI_KEYS_STR.split(",")] if _TARGET_AI_KEYS_STR else []

# 模型列表兜底：上游没有 /v1/models 或拉取失败时，返回此列表（逗号分隔），RikkaHub 才能显示模型
_GATEWAY_MODELS_STR = os.environ.get("GATEWAY_MODELS", "").strip()
GATEWAY_MODELS = [m.strip() for m in _GATEWAY_MODELS_STR.split(",") if m.strip()] if _GATEWAY_MODELS_STR else []

# DeepSeek：窗口总结
DEEPSEEK_API_URL = os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

# 图像描述 AI（便宜模型）
IMAGE_DESC_API_URL = os.environ.get("IMAGE_DESC_API_URL", "")
IMAGE_DESC_API_KEY = os.environ.get("IMAGE_DESC_API_KEY", "")
IMAGE_DESC_MODEL = os.environ.get("IMAGE_DESC_MODEL", "gpt-4o-mini")  # 当前默认 gpt-4o-mini

# R2（S3 兼容）
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "du-gateway")
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "")

# Notion
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_VERSION = os.environ.get("NOTION_VERSION", "2022-06-28")
# 小本本：网关拎出后追加到此页面（块子级）；留空则不写 Notion
NOTION_NOTEBOOK_PAGE_ID = os.environ.get("NOTION_NOTEBOOK_PAGE_ID", "")
# 卧室通道：网关识别 bedroom tag 后，将原文追加到此页面（块子级）；留空则不写 Notion
NOTION_BEDROOM_PAGE_ID = os.environ.get("NOTION_BEDROOM_PAGE_ID", "")
# 核心缓存待审：sync_to_notion / sync_from_notion 用的 database ID
NOTION_CORE_CACHE_DATABASE_ID = os.environ.get("NOTION_CORE_CACHE_DATABASE_ID", "321043f2b83980d088a5c6e2f7bd77bf")

# 小本本：当前逻辑为「笔记本 emoji（📓📒📔）+ 小本本更新」才触发截取，见 services/notebook_gateway.py
# 以下保留供扩展或兼容，当前未使用
_NOTEBOOK_KEYWORDS_STR = os.environ.get("NOTEBOOK_TRIGGER_KEYWORDS", "小本本更新")
NOTEBOOK_TRIGGER_KEYWORDS = [k.strip() for k in _NOTEBOOK_KEYWORDS_STR.split(",") if k.strip()]

# 每 N 轮触发一次总结
SUMMARY_EVERY_N_ROUNDS = 4
# 新窗口注入：R2 中“最新四轮”的存储键（全局）
R2_KEY_LATEST_4_ROUNDS = "global/latest_4_rounds.json"

# Rikka 等前端预设：要从 system/user/assistant 中移除的短语（逗号分隔，留空则不删）
_RIKKA_STR = os.environ.get("RIKKA_PRESET_PATTERNS", "")
RIKKA_PRESET_PATTERNS = [p.strip() for p in _RIKKA_STR.split(",") if p.strip()]

# 失败对话初筛：低于此长度视为失败
FAILED_RESPONSE_MIN_LENGTH = int(os.environ.get("FAILED_RESPONSE_MIN_LENGTH", "10"))
# 失败对话初筛：包含任一词则视为失败（小写匹配）
_FAILED_KEYWORDS_STR = os.environ.get("FAILED_RESPONSE_ERROR_KEYWORDS", "error,出错,失败,超时,抱歉，我无法")
FAILED_RESPONSE_ERROR_KEYWORDS = [k.strip() for k in _FAILED_KEYWORDS_STR.split(",") if k.strip()]

# 动态层注入：取 Top N 条记忆注入（按 token 预算可调）
DYNAMIC_MEMORY_TOP_N = int(os.environ.get("DYNAMIC_MEMORY_TOP_N", "8"))
# 动态层：记忆有效天数，超期参与权重衰减
DYNAMIC_MEMORY_DAYS_VALID = 7

# 记忆注入 token 上限（总结+动态层合计，粗略按 1 中文字≈0.5 token）
# 建议 2500–4000：省 API 费用且尽量保证渡的记忆连续
MEMORY_INJECTION_MAX_TOKENS = int(os.environ.get("MEMORY_INJECTION_MAX_TOKENS", "3000"))
# 其中总结占比例（余下给动态层）
MEMORY_SUMMARY_TOKEN_RATIO = float(os.environ.get("MEMORY_SUMMARY_TOKEN_RATIO", "0.6"))

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
