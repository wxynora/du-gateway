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
    MIJIA_LAMP_DID,
    MIJIA_SPEAKER_DID,
    MIJIA_WIFISPEAKER_NAME,
    NOTION_CORE_CACHE_DATABASE_ID,
)
from utils.log import get_logger

logger = get_logger(__name__)

SYNC_TOOL_NAMES = ("sync_core_cache_to_notion", "sync_core_cache_from_notion")
XIAOAI_TOOL_NAMES = ("xiaoai_speak", "xiaoai_run_command", "mijia_lamp_get", "mijia_lamp_set")

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
                    "让小爱音箱执行一句米家/红外智能家居自然语言命令，底层直接调用小爱音箱 execute-text-directive。"
                    "开灯、关灯、开关空调、调温度、控制红外设备、执行米家设备动作时优先用这个工具。"
                    "如果命令是在调小爱音箱自身音量，会自动改走 MIoT 结构化 volume 属性，不赌自然语言理解。"
                    "只传明确的家居控制命令，不要用来普通聊天，也不要播报渡的声音。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要让小爱执行的自然语言命令，如“关闭卧室空调”“打开客厅灯”。小爱音箱自身音量请用阿拉伯数字，例如“把小爱音箱音量调到50”。",
                        },
                        "speaker_name": {
                            "type": "string",
                            "description": "可选，小爱音箱在米家设备列表里的完整名称，不是 did；通常不要传，不传会使用 MIJIA_WIFISPEAKER_NAME。",
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
        {
            "type": "function",
            "function": {
                "name": "mijia_lamp_get",
                "description": (
                    "读取台灯当前属性。用于确认台灯是否开着、当前亮度或色温。"
                    "不要自己拼 mijiaAPI get 命令；本工具内部会处理 mijiaAPI 的 auth 参数位置。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "property": {
                            "type": "string",
                            "description": "可选：on / brightness / color-temperature；不传则读取三项。",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "mijia_lamp_set",
                "description": (
                    "结构化控制台灯，支持开关、亮度和冷暖色温。"
                    "调亮度/色温时优先用这个工具，不要让渡自己拼 mijiaAPI set 命令。"
                    "brightness 范围 1-100；color_temperature 范围 2700-5100，数值越低越暖。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "on": {"type": "boolean", "description": "可选：打开或关闭台灯"},
                        "brightness": {"type": "integer", "description": "可选：亮度 1-100"},
                        "color_temperature": {"type": "integer", "description": "可选：色温 2700-5100，越低越暖"},
                        "reason": {"type": "string", "description": "为什么这样调整，简短写给日志看"},
                    },
                    "required": [],
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


def _normalize_mijia_speaker_name(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s{2,}", " ", text)
    # mijiaAPI 的 --wifispeaker_name 对 L05C 需要米家列表里的完整设备名。
    if text and text in {MIJIA_SPEAKER_DID, "2037350052"}:
        return MIJIA_WIFISPEAKER_NAME or "小米小爱音箱Play 增强版"
    aliases = {
        "小爱音箱Play增强版": "小米小爱音箱Play 增强版",
        "小爱音箱Play 增强版": "小米小爱音箱Play 增强版",
        "小米小爱音箱Play增强版": "小米小爱音箱Play 增强版",
    }
    text = aliases.get(text, text)
    return text


def _build_mijia_run_command(prompt: str, speaker_name: str = "") -> list[str]:
    base = shlex.split(MIJIA_API_COMMAND or "mijiaAPI")
    if not base:
        base = ["mijiaAPI"]
    cmd = [*base, "--run", prompt]
    name = _normalize_mijia_speaker_name(speaker_name or MIJIA_WIFISPEAKER_NAME)
    if name:
        cmd.extend(["--wifispeaker_name", name])
    if MIJIA_API_AUTH_PATH:
        cmd.extend(["--auth_path", MIJIA_API_AUTH_PATH])
    if MIJIA_API_QUIET:
        cmd.append("--quiet")
    return cmd


def _mijia_cli_base() -> list[str]:
    base = shlex.split(MIJIA_API_COMMAND or "mijiaAPI")
    return base or ["mijiaAPI"]


def _mijia_auth_args() -> list[str]:
    if not MIJIA_API_AUTH_PATH:
        return []
    # mijiaAPI 的 get/set 子命令各自定义 -p；必须放在子命令后，不能放在全局位置。
    return ["-p", MIJIA_API_AUTH_PATH]


def _build_mijia_lamp_get_command(prop_name: str) -> list[str]:
    did = MIJIA_LAMP_DID or "2025297301"
    return [*_mijia_cli_base(), "get", *_mijia_auth_args(), "--did", did, "--prop_name", prop_name]


def _build_mijia_lamp_set_command(prop_name: str, value: Any) -> list[str]:
    did = MIJIA_LAMP_DID or "2025297301"
    return [*_mijia_cli_base(), "set", *_mijia_auth_args(), "--did", did, "--prop_name", prop_name, "--value", str(value)]


def _mijia_speaker_did() -> str:
    return MIJIA_SPEAKER_DID or "2037350052"


def _build_mijia_speaker_volume_set_command(volume: int) -> list[str]:
    return [*_mijia_cli_base(), "set", *_mijia_auth_args(), "--did", _mijia_speaker_did(), "--prop_name", "volume", "--value", str(volume)]


def _run_mijia_text_directive(command: str, speaker_name: str = "") -> tuple[bool, int, str, str, str, str]:
    from mijiaAPI.apis import mijiaAPI

    api = mijiaAPI(auth_data_path=MIJIA_API_AUTH_PATH or None)
    target_name = _normalize_mijia_speaker_name(speaker_name or MIJIA_WIFISPEAKER_NAME or "")
    target_did = _mijia_speaker_did()

    devices: list[dict[str, Any]] = []
    for getter_name in ("get_devices_list", "get_shared_devices_list"):
        getter = getattr(api, getter_name, None)
        if getter is None:
            continue
        try:
            got = getter()
            if isinstance(got, list):
                devices.extend([d for d in got if isinstance(d, dict)])
        except Exception:
            logger.warning("mijiaAPI %s failed while resolving speaker", getter_name, exc_info=True)

    matched: dict[str, Any] | None = None
    if target_did:
        matched = next((d for d in devices if str(d.get("did") or "") == target_did), None)
    if matched is None and target_name:
        matched = next((d for d in devices if str(d.get("name") or "") == target_name), None)
    if matched is None:
        matched = next((d for d in devices if "xiaomi.wifispeaker" in str(d.get("model") or "")), None)

    speaker_did = str((matched or {}).get("did") or target_did).strip()
    resolved_name = str((matched or {}).get("name") or target_name or speaker_did).strip()
    if not speaker_did:
        names = [str(d.get("name") or d.get("did") or "") for d in devices[:12]]
        raise ValueError(f"未找到可用小爱音箱设备。可见设备：{', '.join([n for n in names if n])}")

    payload = {
        "did": speaker_did,
        "siid": 5,
        "aiid": 4,
        "value": [command, 1 if MIJIA_API_QUIET else 0],
    }
    result = api.run_action(payload)
    code = int((result or {}).get("code", -1))
    ok = code in (0, 1)
    return ok, code, json.dumps(result, ensure_ascii=False), "", resolved_name, speaker_did


def _extract_speaker_volume(command: str) -> int | None:
    text = str(command or "").strip()
    if "音量" not in text:
        return None
    if not any(word in text for word in ("小爱", "音箱", "speaker")):
        return None
    match = re.search(r"(\d{1,3})", text)
    if not match:
        return None
    volume = int(match.group(1))
    if volume < 0 or volume > 100:
        return None
    return volume


def _run_mijia_cli(cmd: list[str]) -> tuple[bool, int, str, str]:
    timeout = max(5, min(180, int(MIJIA_API_TIMEOUT_SECONDS or 45)))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    return proc.returncode == 0, int(proc.returncode), stdout, stderr


def _coerce_int(value: Any, *, minimum: int, maximum: int, field: str) -> tuple[bool, int | None, str]:
    if value is None:
        return True, None, ""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return False, None, f"{field} 必须是整数"
    if n < minimum or n > maximum:
        return False, None, f"{field} 必须在 {minimum}-{maximum} 之间"
    return True, n, ""


def _execute_mijia_run_command(arguments: dict) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    command = _clean_mijia_command(args.get("command"))
    speaker_name = str(args.get("speaker_name") or "").strip()
    reason = str(args.get("reason") or "").strip()
    if not command:
        return json.dumps({"ok": False, "error": "COMMAND_REQUIRED", "message": "command 不能为空"}, ensure_ascii=False)

    try:
        from storage.xiaoai_store import add_xiaoai_log

        speaker_volume = _extract_speaker_volume(command)
        if speaker_volume is not None:
            run_cmd = _build_mijia_speaker_volume_set_command(speaker_volume)
            ok, returncode, stdout, stderr = _run_mijia_cli(run_cmd)
            add_xiaoai_log(
                "info" if ok else "error",
                "小爱音箱音量设置完成" if ok else "小爱音箱音量设置失败",
                event="mijia_speaker_volume_set",
                speaker=_normalize_mijia_speaker_name(speaker_name or MIJIA_WIFISPEAKER_NAME or ""),
                text=command,
                error=stderr if not ok else "",
            )
            return json.dumps(
                {
                    "ok": ok,
                    "tool": "xiaoai_run_command",
                    "mode": "speaker_volume_set",
                    "command": command,
                    "speaker_did": _mijia_speaker_did(),
                    "volume": speaker_volume,
                    "returncode": returncode,
                    "stdout": stdout[-1200:],
                    "stderr": stderr[-1200:],
                    "reason": reason,
                },
                ensure_ascii=False,
            )

        resolved_speaker_name = _normalize_mijia_speaker_name(speaker_name or MIJIA_WIFISPEAKER_NAME or "")
        logger.info("mijiaAPI text directive command=%s speaker=%s", command, resolved_speaker_name)
        ok, returncode, stdout, stderr, resolved_speaker_name, speaker_did = _run_mijia_text_directive(command, speaker_name=speaker_name)
        add_xiaoai_log(
            "info" if ok else "error",
            "小爱自然语言家居命令执行完成" if ok else "小爱自然语言家居命令执行失败",
            event="mijia_text_directive",
            speaker=resolved_speaker_name,
            text=command,
            error=stderr if not ok else "",
        )
        return json.dumps(
            {
                "ok": ok,
                "tool": "xiaoai_run_command",
                "mode": "speaker_text_directive",
                "command": command,
                "speaker_name": resolved_speaker_name,
                "speaker_did": speaker_did,
                "returncode": returncode,
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


def _execute_mijia_lamp_get(arguments: dict) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    requested = str(args.get("property") or "").strip()
    props = [requested] if requested else ["on", "brightness", "color-temperature"]
    allowed = {"on", "brightness", "color-temperature"}
    if any(p not in allowed for p in props):
        return json.dumps({"ok": False, "error": "INVALID_PROPERTY", "message": "property 只能是 on / brightness / color-temperature"}, ensure_ascii=False)
    results: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    try:
        for prop in props:
            cmd = _build_mijia_lamp_get_command(prop)
            ok, returncode, stdout, stderr = _run_mijia_cli(cmd)
            if ok:
                results[prop] = stdout
            else:
                errors.append({"property": prop, "returncode": returncode, "stderr": stderr[-1200:]})
        return json.dumps({"ok": not errors, "tool": "mijia_lamp_get", "values": results, "errors": errors}, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({"ok": False, "error": "MIJIA_API_TIMEOUT", "message": f"mijiaAPI 执行超过 {MIJIA_API_TIMEOUT_SECONDS} 秒未返回。"}, ensure_ascii=False)
    except FileNotFoundError:
        return json.dumps({"ok": False, "error": "MIJIA_API_NOT_FOUND", "message": f"找不到 mijiaAPI 命令：{MIJIA_API_COMMAND or 'mijiaAPI'}"}, ensure_ascii=False)
    except Exception as e:
        logger.exception("mijia_lamp_get 执行异常")
        return json.dumps({"ok": False, "error": "EXECUTION_FAILED", "message": str(e)}, ensure_ascii=False)


def _execute_mijia_lamp_set(arguments: dict) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    updates: list[tuple[str, Any]] = []
    if "on" in args and args.get("on") is not None:
        updates.append(("on", bool(args.get("on"))))
    ok_brightness, brightness, err = _coerce_int(args.get("brightness"), minimum=1, maximum=100, field="brightness")
    if not ok_brightness:
        return json.dumps({"ok": False, "error": "INVALID_BRIGHTNESS", "message": err}, ensure_ascii=False)
    if brightness is not None:
        updates.append(("brightness", brightness))
    ok_ct, color_temperature, err = _coerce_int(args.get("color_temperature"), minimum=2700, maximum=5100, field="color_temperature")
    if not ok_ct:
        return json.dumps({"ok": False, "error": "INVALID_COLOR_TEMPERATURE", "message": err}, ensure_ascii=False)
    if color_temperature is not None:
        updates.append(("color-temperature", color_temperature))
    if not updates:
        return json.dumps({"ok": False, "error": "NO_UPDATES", "message": "至少传 on / brightness / color_temperature 之一"}, ensure_ascii=False)

    results: list[dict[str, Any]] = []
    try:
        for prop, value in updates:
            cmd = _build_mijia_lamp_set_command(prop, value)
            ok, returncode, stdout, stderr = _run_mijia_cli(cmd)
            results.append({"property": prop, "value": value, "ok": ok, "returncode": returncode, "stdout": stdout[-1200:], "stderr": stderr[-1200:]})
            if not ok:
                break
        all_ok = all(item.get("ok") for item in results)
        return json.dumps({"ok": all_ok, "tool": "mijia_lamp_set", "results": results, "reason": str(args.get("reason") or "").strip()}, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({"ok": False, "error": "MIJIA_API_TIMEOUT", "message": f"mijiaAPI 执行超过 {MIJIA_API_TIMEOUT_SECONDS} 秒未返回。"}, ensure_ascii=False)
    except FileNotFoundError:
        return json.dumps({"ok": False, "error": "MIJIA_API_NOT_FOUND", "message": f"找不到 mijiaAPI 命令：{MIJIA_API_COMMAND or 'mijiaAPI'}"}, ensure_ascii=False)
    except Exception as e:
        logger.exception("mijia_lamp_set 执行异常")
        return json.dumps({"ok": False, "error": "EXECUTION_FAILED", "message": str(e)}, ensure_ascii=False)


def execute_xiaoai_tool(name: str, arguments: dict) -> str:
    """执行小爱音箱工具，返回给渡的 JSON 字符串。"""
    if name not in XIAOAI_TOOL_NAMES:
        return json.dumps({"ok": False, "error": "UNKNOWN_TOOL"}, ensure_ascii=False)
    if name == "xiaoai_run_command":
        return _execute_mijia_run_command(arguments if isinstance(arguments, dict) else {})
    if name == "mijia_lamp_get":
        return _execute_mijia_lamp_get(arguments if isinstance(arguments, dict) else {})
    if name == "mijia_lamp_set":
        return _execute_mijia_lamp_set(arguments if isinstance(arguments, dict) else {})

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
