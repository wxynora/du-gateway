# 网关工具：核心缓存同步、小爱音箱外放等网关本地能力。
import json
import re
import shlex
import subprocess
from typing import Any, List

from config import (
    MIJIA_API_AUTH_PATH,
    MIJIA_API_COMMAND,
    MIJIA_API_QUIET,
    MIJIA_API_TIMEOUT_SECONDS,
    MIJIA_WIFISPEAKER_NAME,
    NOTION_CORE_CACHE_DATABASE_ID,
)
from utils.log import get_logger

logger = get_logger(__name__)

SYNC_TOOL_NAMES = ("sync_core_cache_to_notion", "sync_core_cache_from_notion")
XIAOAI_TOOL_NAMES = ("xiaoai_speak", "xiaoai_run_command")

# 提醒文案：老婆问「明确的指令是什么」或「我该怎么说」时，渡可直接用这句回复
SYNC_REMINDER_FOR_WIFE = (
    "老婆你可以跟我说：\n"
    "· 「同步到 Notion」或「推到待审表」——我会把当前核心缓存推到 Notion 待审表；\n"
    "· 「从 Notion 同步回来」或「把待审表同步回来」——我会把 Notion 待审表当前内容同步回核心缓存。\n"
    "只有你说这两类明确指令时我才会执行，不会误触。"
)


def get_gateway_sync_tools() -> List[dict]:
    """返回两个同步工具定义，供注入到 chat；仅当配置了核心缓存 Notion 时才有意义。"""
    return [
        {
            "type": "function",
            "function": {
                "name": "sync_core_cache_to_notion",
                "description": (
                    "把当前核心缓存（R2 pending）全量推到 Notion 待审表，然后清空 R2 里的 pending。"
                    "只有老婆明确说「同步到 Notion」或「推到待审表」时才调用，不要根据模糊表述调用。"
                    "老婆问「明确的指令是什么」或「我该怎么说」时，提醒她可以说：同步到 Notion / 从 Notion 同步回来。"
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sync_core_cache_from_notion",
                "description": (
                    "从 Notion 待审表读回当前所有条目，追加到 R2 核心缓存。"
                    "只有老婆明确说「从 Notion 同步回来」或「把待审表同步回来」时才调用。"
                    "调用前若老婆没先确认，可先回复一句确认（会覆盖/追加核心缓存哦），老婆说对/要再调。"
                    "老婆问「明确的指令是什么」或「我该怎么说」时，提醒她可以说：同步到 Notion / 从 Notion 同步回来。"
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


def get_gateway_xiaoai_tools() -> List[dict]:
    """返回小爱音箱相关工具定义，供 chat 常驻注入。"""
    return [
        {
            "type": "function",
            "function": {
                "name": "xiaoai_speak",
                "description": (
                    "让卧室小爱音箱外放一段渡的声音，像手机弹窗/强提醒一样把话送到房间里。"
                    "适合用户没看手机、长时间不理你、需要及时提醒或你需要主动出现时调用。"
                    "只播短句，不要播隐私、敏感、会让旁人尴尬的内容；普通聊天不要每句都调用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "要通过音箱说出的短句，建议 80 字以内，口语化，不要使用 markdown。",
                        },
                        "reason": {
                            "type": "string",
                            "description": "为什么需要通过音箱提醒，简短写给系统日志看。",
                        },
                    },
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "xiaoai_run_command",
                "description": (
                    "让小爱音箱执行一句米家/红外智能家居自然语言命令，底层调用 mijiaAPI --run。"
                    "开灯、关灯、开关空调、调温度、控制红外设备、执行米家设备动作时优先用这个工具。"
                    "只传明确的家居控制命令，不要用来普通聊天，也不要播报渡的声音。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要让小爱执行的自然语言命令，如“关闭卧室空调”“打开客厅灯”。",
                        },
                        "speaker_name": {
                            "type": "string",
                            "description": "可选，小爱音箱名称。不传则使用 MIJIA_WIFISPEAKER_NAME，仍为空时让 mijiaAPI 使用默认音箱。",
                        },
                        "reason": {
                            "type": "string",
                            "description": "为什么要执行这个家居控制，简短写给日志看。",
                        },
                    },
                    "required": ["command"],
                },
            },
        },
    ]


def get_gateway_tools_for_inject() -> List[dict]:
    """返回不依赖 Notion 开关的网关工具。"""
    return get_gateway_xiaoai_tools()


_VOICE_TAG_RE = re.compile(r"</?voice>", flags=re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"</?[^>]+>")


def _clean_xiaoai_speak_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = _VOICE_TAG_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.strip()
    if len(text) > 240:
        text = text[:240].rstrip() + "。"
    return text


def _clean_mijia_command(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s{2,}", " ", text)
    if len(text) > 120:
        text = text[:120].rstrip()
    return text


def _build_mijia_run_command(prompt: str, speaker_name: str = "") -> list[str]:
    base = shlex.split(MIJIA_API_COMMAND or "mijiaAPI")
    if not base:
        base = ["mijiaAPI"]
    cmd = [*base, "--run", prompt]
    name = str(speaker_name or MIJIA_WIFISPEAKER_NAME or "").strip()
    if name:
        cmd.extend(["--wifispeaker_name", name])
    if MIJIA_API_AUTH_PATH:
        cmd.extend(["--auth_path", MIJIA_API_AUTH_PATH])
    if MIJIA_API_QUIET:
        cmd.append("--quiet")
    return cmd


def _execute_mijia_run_command(arguments: dict) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    command = _clean_mijia_command(args.get("command"))
    speaker_name = str(args.get("speaker_name") or "").strip()
    reason = str(args.get("reason") or "").strip()
    if not command:
        return json.dumps({"ok": False, "error": "COMMAND_REQUIRED", "message": "command 不能为空"}, ensure_ascii=False)

    try:
        from storage.xiaoai_store import add_xiaoai_log

        run_cmd = _build_mijia_run_command(command, speaker_name=speaker_name)
        timeout = max(5, min(180, int(MIJIA_API_TIMEOUT_SECONDS or 45)))
        logger.info("mijiaAPI run command=%s speaker=%s", command, speaker_name or MIJIA_WIFISPEAKER_NAME or "")
        proc = subprocess.run(
            run_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        ok = proc.returncode == 0
        add_xiaoai_log(
            "info" if ok else "error",
            "mijiaAPI 家居命令执行完成" if ok else "mijiaAPI 家居命令执行失败",
            event="mijia_run_command",
            speaker=speaker_name or MIJIA_WIFISPEAKER_NAME or "",
            text=command,
            error=stderr if not ok else "",
        )
        return json.dumps(
            {
                "ok": ok,
                "tool": "xiaoai_run_command",
                "command": command,
                "speaker_name": speaker_name or MIJIA_WIFISPEAKER_NAME or "",
                "returncode": proc.returncode,
                "stdout": stdout[-1200:],
                "stderr": stderr[-1200:],
                "reason": reason,
            },
            ensure_ascii=False,
        )
    except FileNotFoundError:
        return json.dumps(
            {
                "ok": False,
                "error": "MIJIA_API_NOT_FOUND",
                "message": f"找不到 mijiaAPI 命令：{MIJIA_API_COMMAND or 'mijiaAPI'}，请先在运行 du-gateway 的环境安装并配置 MIJIA_API_COMMAND。",
            },
            ensure_ascii=False,
        )
    except subprocess.TimeoutExpired:
        return json.dumps(
            {
                "ok": False,
                "error": "MIJIA_API_TIMEOUT",
                "message": f"mijiaAPI 执行超过 {MIJIA_API_TIMEOUT_SECONDS} 秒未返回。",
                "command": command,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        logger.exception("mijiaAPI 工具执行异常")
        return json.dumps({"ok": False, "error": "EXECUTION_FAILED", "message": str(e)}, ensure_ascii=False)


def execute_xiaoai_tool(name: str, arguments: dict) -> str:
    """执行小爱音箱工具，返回给渡的 JSON 字符串。"""
    if name not in XIAOAI_TOOL_NAMES:
        return json.dumps({"ok": False, "error": "UNKNOWN_TOOL"}, ensure_ascii=False)
    if name == "xiaoai_run_command":
        return _execute_mijia_run_command(arguments if isinstance(arguments, dict) else {})

    args = arguments if isinstance(arguments, dict) else {}
    text = _clean_xiaoai_speak_text(args.get("text"))
    reason = str(args.get("reason") or "").strip()
    if not text:
        return json.dumps({"ok": False, "error": "TEXT_REQUIRED", "message": "text 不能为空"}, ensure_ascii=False)

    try:
        from storage.xiaoai_store import add_xiaoai_log, enqueue_xiaoai_action, get_xiaoai_status
        from services.minimax_tts import tts_to_audio_bytes
        from services.xiaoai_audio_store import create_xiaoai_audio, resolve_xiaoai_audio_base_url_for_http_request

        status = get_xiaoai_status()
        if not bool((status or {}).get("online")):
            add_xiaoai_log("warn", "xiaoai_speak 调用失败：runner 不在线", event="tool_offline", text=text)
            return json.dumps(
                {
                    "ok": False,
                    "error": "XIAOAI_OFFLINE",
                    "message": "小爱音箱 runner 当前不在线，无法外放。",
                    "status": status,
                },
                ensure_ascii=False,
            )

        audio_bytes = tts_to_audio_bytes(text, audio_format="mp3")
        if not audio_bytes:
            add_xiaoai_log("error", "xiaoai_speak 调用失败：MiniMax TTS 生成失败", event="tool_tts_failed", text=text)
            return json.dumps({"ok": False, "error": "TTS_FAILED", "message": "MiniMax TTS 生成失败。"}, ensure_ascii=False)

        ok, payload = create_xiaoai_audio(
            audio_bytes=audio_bytes,
            audio_format="mp3",
            url_base=resolve_xiaoai_audio_base_url_for_http_request(""),
        )
        if not ok:
            add_xiaoai_log("error", "xiaoai_speak 调用失败：音频公网 URL 不可用", event="tool_audio_url_failed", text=text, error=str(payload))
            return json.dumps(
                {"ok": False, "error": "PUBLIC_URL_UNAVAILABLE", "message": str(payload)},
                ensure_ascii=False,
            )

        audio_url = str((payload or {}).get("url") or "").strip()
        action = enqueue_xiaoai_action(
            "play_url",
            text=text,
            audio_url=audio_url,
            audio_format="mp3",
            source="tool:xiaoai_speak",
            metadata={"reason": reason},
        )
        add_xiaoai_log("info", "xiaoai_speak 已加入播放队列", event="tool_action_queued", text=text, audio_url=audio_url)
        return json.dumps(
            {
                "ok": True,
                "message": "已排队让小爱音箱外放。",
                "action_id": action.get("id"),
                "audio_url": audio_url,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        logger.exception("xiaoai_speak 工具执行异常")
        return json.dumps({"ok": False, "error": "EXECUTION_FAILED", "message": str(e)}, ensure_ascii=False)


def execute_gateway_tool(name: str, arguments: dict) -> str:
    """执行 sync 工具，返回给渡的字符串结果。"""
    if name not in SYNC_TOOL_NAMES:
        return "未知工具"
    if not NOTION_CORE_CACHE_DATABASE_ID:
        return "未配置核心缓存 Notion（NOTION_CORE_CACHE_DATABASE_ID）"
    try:
        if name == "sync_core_cache_to_notion":
            from services.core_cache_notion_sync import sync_to_notion
            ok, err = sync_to_notion()
            if ok:
                return "已把核心缓存推到 Notion 待审表，R2 pending 已清空。"
            return f"同步失败：{err or '未知错误'}"
        if name == "sync_core_cache_from_notion":
            from services.core_cache_notion_sync import sync_from_notion
            ok, err = sync_from_notion()
            if ok:
                return "已从 Notion 待审表同步回核心缓存。"
            return f"同步失败：{err or '未知错误'}"
    except Exception as e:
        logger.exception("网关 sync 工具执行异常 name=%s", name)
        return f"执行出错：{e}"
    return "未知工具"
