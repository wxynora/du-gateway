# 一键清空本地运行状态
import json
from pathlib import Path
from typing import Optional

from config import (
    RECENT_WINDOWS_FILE,
    LAST_USER_REPLY_FILE,
)

from storage import runtime_sqlite, wenyou_sqlite_store
from utils.log import get_logger

logger = get_logger(__name__)


def wipe_local_data() -> tuple[bool, int, Optional[str]]:
    """
    清空网关本地数据：最近窗口、上次 user 回复时间和本地 SQLite 表。
    不删 data/emoji_mapping.json（老婆可编辑的对照表）。
    返回 (是否成功, 清空的文件数, 错误信息)。
    """
    files_and_defaults: list[tuple[Path, list | dict]] = [
        (RECENT_WINDOWS_FILE, []),
        (LAST_USER_REPLY_FILE, {}),
    ]
    cleared = 0
    try:
        for path, default in files_and_defaults:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, ensure_ascii=False, indent=2)
            cleared += 1
        cleared += runtime_sqlite.clear_all_tables()
        cleared += wenyou_sqlite_store.clear_all_tables()
        logger.info("wipe_local_data 已清空 %s 个本地文件", cleared)
        return True, cleared, None
    except Exception as e:
        logger.error("wipe_local_data 失败 error=%s", e, exc_info=True)
        return False, cleared, str(e)
