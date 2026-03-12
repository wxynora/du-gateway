# 统一日志：带模块名和错误来源，方便排查
# 格式：[模块名] LEVEL: 消息 key=value ...
import logging
import sys

from config import LOG_LEVEL

# 短模块名，一眼能看出错误来源
LOG_NAMES = {
    "storage.r2_store": "R2",
    "pipeline.pipeline": "Pipeline",
    "pipeline.cleaner": "Cleaner",
    "pipeline.failed_response": "FailedResponse",
    "routes.chat": "Chat",
    "services.deepseek_summary": "DeepSeek",
    "services.image_desc": "ImageDesc",
    "services.notion_client": "Notion",
    "services.dynamic_layer_ds": "DynDS",
    "services.bedroom_gateway": "Bedroom",
}


class ShortNameFormatter(logging.Formatter):
    """把 logger 名换成短名，方便看来源。"""

    def format(self, record):
        record.short_name = LOG_NAMES.get(record.name, record.name.split(".")[-1])
        return super().format(record)


def setup_logging():
    """在 app 启动时调用，配置全局日志。"""
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    fmt = "%(asctime)s [%(short_name)s] %(levelname)s: %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ShortNameFormatter(fmt))
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    # 第三方库降噪
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """各模块用此获取 logger，name 用 __name__ 即可。"""
    return logging.getLogger(name)
