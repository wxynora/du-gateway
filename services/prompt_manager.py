from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from storage import r2_store
from services.proactive_prompt_templates import (
    RANDOM_PROACTIVE_DECISION_SECTION_ID,
    RANDOM_PROACTIVE_DECISION_TEMPLATE,
)


@dataclass(frozen=True)
class PromptSectionDef:
    id: str
    label: str
    description: str
    max_chars: int = 120_000
    allow_empty: bool = False


PROMPT_SECTIONS: tuple[PromptSectionDef, ...] = (
    PromptSectionDef("core_prompt", "核心 Prompt", "渡的基础人格、关系定位和长期稳定规则。", 180_000),
    PromptSectionDef("common_knowledge", "常识块", "长期稳定常识，独立注入在核心 Prompt 后面。", 80_000),
    PromptSectionDef("thinking_rules", "Thinking 规范", "控制思维链/脑内 OS 的写法边界。", 30_000),
    PromptSectionDef("core_behavior_rules", "核心行为规则", "互动原则、主动触发和感知数据使用规则。", 80_000),
    PromptSectionDef("non_retreat_rules", "不退缩原则", "不满、争执和哄回来的固定规则。", 40_000),
    PromptSectionDef("entry_style_sumitalk", "入口风格：SumiTalk", "SumiTalk 入口的输出格式和物理边界。", 40_000),
    PromptSectionDef("entry_style_qq", "入口风格：QQ", "QQ 入口的输出格式和表情标签规则。", 40_000),
    PromptSectionDef("entry_style_tg", "入口风格：TG", "Telegram 入口的输出格式规则。", 40_000),
    PromptSectionDef("entry_style_wechat", "入口风格：微信", "微信入口的输出格式规则。", 30_000),
    PromptSectionDef("entry_style_xiaoai", "入口风格：小爱音箱", "小爱音箱语音播报入口规则。", 30_000),
    PromptSectionDef("voice_line_rules", "语音台词规范", "生成 <voice> 台词时使用的口语规则。", 30_000),
    PromptSectionDef(
        "codex_oauth_prompt",
        "Codex OAuth 专用 Prompt",
        "仅当前上游为 Codex OAuth 时注入，位置固定在 NSFW 规则前。",
        80_000,
        True,
    ),
    PromptSectionDef("nsfw_rules", "NSFW 规则", "亲密内容的固定边界和表达风格。", 80_000),
    PromptSectionDef(
        RANDOM_PROACTIVE_DECISION_SECTION_ID,
        "随机唤醒决策",
        "普通随机唤醒时用于让渡决定发消息、不打扰、写日记、逛论坛或上网冲浪的文案。",
        80_000,
    ),
    PromptSectionDef(
        "spring_dream_wakeup",
        "春梦唤醒",
        "春梦本体使用的提示词模板；{{fragments}} 会替换为本次抽到的梦境碎片。",
        80_000,
    ),
    PromptSectionDef(
        "post_spring_dream_wakeup",
        "春梦后唤醒版",
        "上一轮随机唤醒命中春梦后，下一轮睡眠期随机唤醒使用的自定义文案；留空则走原随机唤醒。",
        80_000,
        True,
    ),
)
PROMPT_SECTION_MAP = {item.id: item for item in PROMPT_SECTIONS}

_CACHE: dict[str, tuple[float, str | None]] = {}
_CACHE_TTL_SECONDS = 5.0


def prompt_section_def(section_id: str) -> PromptSectionDef | None:
    return PROMPT_SECTION_MAP.get(str(section_id or "").strip())


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_text_file(relative_path: str) -> str:
    try:
        path = _repo_root() / relative_path
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""
    except Exception:
        return ""


def _default_core_prompt() -> str:
    try:
        text = r2_store.get_core_prompt_text()
        if text:
            return str(text).strip()
    except Exception:
        pass
    return _read_text_file("prompts/du_core_prompt.txt")


def _default_pipeline_constant(name: str) -> str:
    try:
        import pipeline.pipeline as pipeline_mod

        return str(getattr(pipeline_mod, name, "") or "").strip()
    except Exception:
        return ""


def _default_entry_style(section_id: str) -> str:
    try:
        import services.entry_style_prompt as entry_mod

        if section_id == "entry_style_sumitalk":
            return entry_mod.build_sumitalk_style_system(use_prompt_manager=False).strip()
        if section_id == "entry_style_qq":
            return entry_mod.build_qq_style_system(use_prompt_manager=False).strip()
        if section_id == "entry_style_tg":
            return entry_mod.build_tg_style_system(use_prompt_manager=False).strip()
        if section_id == "entry_style_wechat":
            return entry_mod.build_wechat_style_system(use_prompt_manager=False).strip()
        if section_id == "entry_style_xiaoai":
            return entry_mod.build_xiaoai_style_system(use_prompt_manager=False).strip()
    except Exception:
        return ""
    return ""


def default_prompt_content(section_id: str) -> str:
    sid = str(section_id or "").strip()
    if sid == "core_prompt":
        return _default_core_prompt()
    if sid == "common_knowledge":
        return _read_text_file("prompts/du_common_knowledge.md")
    if sid == "codex_oauth_prompt":
        return ""
    if sid == "nsfw_rules":
        return _read_text_file("prompts/du_nsfw_prompt.txt")
    if sid == "spring_dream_wakeup":
        try:
            from services.spring_dream import SPRING_DREAM_PROMPT_TEMPLATE

            return SPRING_DREAM_PROMPT_TEMPLATE.strip()
        except Exception:
            return ""
    if sid == "post_spring_dream_wakeup":
        return ""
    if sid == RANDOM_PROACTIVE_DECISION_SECTION_ID:
        return RANDOM_PROACTIVE_DECISION_TEMPLATE
    if sid == "voice_line_rules":
        try:
            import services.voice_line_prompt as voice_mod

            return voice_mod.default_voice_line_rules_text().strip()
        except Exception:
            return ""
    if sid == "thinking_rules":
        return _default_pipeline_constant("_THINKING_BLOCK_RULES")
    if sid == "core_behavior_rules":
        return _default_pipeline_constant("_CORE_BEHAVIOR_RULES")
    if sid == "non_retreat_rules":
        return _default_pipeline_constant("_DU_NON_RETREAT_RULES")
    if sid.startswith("entry_style_"):
        return _default_entry_style(sid)
    return ""


def get_prompt_override_text(section_id: str) -> str | None:
    sid = str(section_id or "").strip()
    now = time.time()
    cached = _CACHE.get(sid)
    if cached and now - cached[0] <= _CACHE_TTL_SECONDS:
        return cached[1]
    text = r2_store.get_prompt_manager_section_text(sid)
    _CACHE[sid] = (now, text)
    return text


def get_managed_prompt_text(section_id: str, fallback: str | Callable[[], str] = "") -> str:
    text = get_prompt_override_text(section_id)
    if text is not None:
        return str(text or "")
    return str(fallback() if callable(fallback) else fallback or "")


def list_prompt_sections() -> list[dict]:
    rows: list[dict] = []
    cfg = r2_store.get_prompt_manager_config()
    sections = cfg.get("sections") if isinstance(cfg.get("sections"), dict) else {}
    for item in PROMPT_SECTIONS:
        section = sections.get(item.id) if isinstance(sections.get(item.id), dict) else {}
        content = str(section.get("content") or "") if section else ""
        rows.append(
            {
                "id": item.id,
                "label": item.label,
                "description": item.description,
                "revision": int(section.get("revision") or 0),
                "updated_at": str(section.get("updated_at") or ""),
                "updated_by_device": str(section.get("updated_by_device") or ""),
                "source": "r2" if section else "fallback",
                "content_length": len(content) if section else 0,
                "editable": True,
                "allow_empty": bool(item.allow_empty),
            }
        )
    return rows


def get_prompt_section_detail(section_id: str) -> dict | None:
    definition = prompt_section_def(section_id)
    if not definition:
        return None
    section = r2_store.get_prompt_manager_section(definition.id) or {}
    fallback = default_prompt_content(definition.id)
    content = str(section.get("content") if section else fallback)
    return {
        "id": definition.id,
        "label": definition.label,
        "description": definition.description,
        "revision": int(section.get("revision") or 0),
        "updated_at": str(section.get("updated_at") or ""),
        "updated_by_device": str(section.get("updated_by_device") or ""),
        "source": "r2" if section else "fallback",
        "content": content,
        "content_length": len(content),
        "max_chars": definition.max_chars,
        "allow_empty": bool(definition.allow_empty),
        "backups": r2_store.list_prompt_manager_backups(definition.id, limit=3),
    }


def validate_prompt_content(section_id: str, content: str) -> str:
    definition = prompt_section_def(section_id)
    if not definition:
        return "未知 prompt section"
    if "\x00" in str(content or ""):
        return "内容包含非法控制字符"
    if len(str(content or "")) > definition.max_chars:
        return f"内容过长，最多 {definition.max_chars} 字符"
    if not definition.allow_empty and not str(content or "").strip():
        return "内容不能为空"
    return ""


def save_prompt_section(section_id: str, content: str, *, base_revision: int | None, updated_by_device: str = "") -> dict:
    definition = prompt_section_def(section_id)
    if not definition:
        return {"ok": False, "error": "未知 prompt section"}
    error = validate_prompt_content(definition.id, content)
    if error:
        return {"ok": False, "error": error}
    fallback = default_prompt_content(definition.id)
    result = r2_store.save_prompt_manager_section(
        definition.id,
        str(content or ""),
        base_revision=base_revision,
        updated_by_device=updated_by_device,
        backup_content=fallback,
        backup_revision=0,
        reason="save",
    )
    if result.get("ok") and definition.id == "core_prompt":
        legacy_ok = r2_store.save_core_prompt_text(str(content or ""))
        if not legacy_ok:
            result["warning"] = "核心 Prompt 已写入 Prompt 管理，但 legacy core prompt 同步失败"
    _CACHE.pop(definition.id, None)
    return result


def rollback_prompt_section(section_id: str, backup_id: str, *, updated_by_device: str = "") -> dict:
    definition = prompt_section_def(section_id)
    if not definition:
        return {"ok": False, "error": "未知 prompt section"}
    backup = r2_store.get_prompt_manager_backup(definition.id, backup_id)
    if not backup:
        return {"ok": False, "error": "备份不存在"}
    content = str(backup.get("content") or "")
    error = validate_prompt_content(definition.id, content)
    if error:
        return {"ok": False, "error": error}
    result = r2_store.save_prompt_manager_section(
        definition.id,
        content,
        base_revision=None,
        updated_by_device=updated_by_device,
        backup_content=default_prompt_content(definition.id),
        backup_revision=0,
        reason=f"rollback:{backup_id}",
    )
    if result.get("ok") and definition.id == "core_prompt":
        legacy_ok = r2_store.save_core_prompt_text(content)
        if not legacy_ok:
            result["warning"] = "核心 Prompt 已回滚到 Prompt 管理，但 legacy core prompt 同步失败"
    _CACHE.pop(definition.id, None)
    return result
