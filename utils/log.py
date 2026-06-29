# 统一日志：带模块名和错误来源，方便排查
# 格式：[模块名] LEVEL: 消息 key=value ...
import logging
import os
import sys
from pathlib import Path

from config import LOG_LEVEL, MINIAPP_LOG_FILE
from utils.log_buffer import add_log_line

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
    "routes.telegram_webhook": "TGHook",
    "services.telegram_bot": "TGBot",
    "services.telegram_webhook_worker": "TGWorker",
    "services.telegram_update_queue": "TGQueue",
    "services.telegram_proactive": "TGPro",
    "services.schedule_runtime": "Alarm",
    "sumitalk": "SumiTalk",
}


class ShortNameFormatter(logging.Formatter):
    """把 logger 名换成短名，方便看来源。"""

    def format(self, record):
        record.short_name = LOG_NAMES.get(record.name, record.name.split(".")[-1])
        return super().format(record)


class FlushingStreamHandler(logging.StreamHandler):
    """每次写日志后立即 flush，nohup 重定向到文件时也能马上看到 [Chat] INFO 等。"""

    def emit(self, record):
        super().emit(record)
        self.flush()


class FlushingFileHandler(logging.FileHandler):
    """写到文件时也 flush，确保手机端 tail 读得到最新日志。"""

    def emit(self, record):
        super().emit(record)
        self.flush()


class LogBufferHandler(logging.Handler):
    """进程内日志缓冲：当 gateway.log 不存在时，Mini App 仍可 tail/stream。"""

    def emit(self, record):
        try:
            line = self.format(record)
        except Exception:
            line = record.getMessage()
        add_log_line(line)
        try:
            from services.log_error_alert import is_alertworthy_log_line, maybe_enqueue_log_error_alert

            explicit_enabled = os.environ.get("LOG_ERROR_APP_ALERT_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
            should_alert = (
                (explicit_enabled and record.levelno >= logging.ERROR)
                or is_alertworthy_log_line(line, record.levelname)
            )
            if should_alert:
                maybe_enqueue_log_error_alert(line, record.levelname)
        except Exception:
            pass


def setup_logging():
    """在 app 启动时调用，配置全局日志。"""
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    fmt = "%(asctime)s [%(short_name)s] %(levelname)s: %(message)s"
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # 1) 标准输出：保留原行为，方便你直接 nohup + tail -f
    stream_handler = FlushingStreamHandler(sys.stdout)
    stream_handler.setFormatter(ShortNameFormatter(fmt))
    root.addHandler(stream_handler)

    # 进程内缓冲：fallback_stdio 使用
    try:
        buffer_handler = LogBufferHandler()
        buffer_handler.setFormatter(ShortNameFormatter(fmt))
        root.addHandler(buffer_handler)
    except Exception:
        pass

    # 2) 可选：同时写入日志文件（供 Mini App 读取）
    # 默认 `gateway.log`，如果配置为相对路径，则写到项目根目录。
    try:
        log_file = (MINIAPP_LOG_FILE or "").strip()
        if log_file:
            base_dir = Path(__file__).resolve().parent.parent
            p = Path(log_file)
            if not p.is_absolute():
                p = base_dir / log_file
            p.parent.mkdir(parents=True, exist_ok=True)
            file_handler = FlushingFileHandler(p, encoding="utf-8")
            file_handler.setFormatter(ShortNameFormatter(fmt))
            root.addHandler(file_handler)
    except Exception:
        # 日志文件失败不影响主服务
        pass

    # 第三方库降噪
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """各模块用此获取 logger，name 用 __name__ 即可。"""
    return logging.getLogger(name)
