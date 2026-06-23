from __future__ import annotations

import re
from dataclasses import dataclass


SUPPORTED_LOCALES = {"zh-CN", "en-US"}
DEFAULT_LOCALE = "zh-CN"


@dataclass(frozen=True)
class TaskLanguageSelection:
    display_language: str
    requested_output_language: str | None
    report_language: str


def normalize_locale(value: str | None, *, default: str = DEFAULT_LOCALE) -> str:
    if not value:
        return default
    normalized = value.strip().replace("_", "-")
    lowered = normalized.lower()
    if lowered in {"zh", "zh-cn", "cn", "chinese", "中文"}:
        return "zh-CN"
    if lowered in {"en", "en-us", "english", "英文"}:
        return "en-US"
    return normalized if normalized in SUPPORTED_LOCALES else default


def infer_requested_output_language(*texts: str | None) -> str | None:
    haystack = "\n".join(text for text in texts if text).strip()
    if not haystack:
        return None
    if re.search(r"中文|用中文|中文回答|Chinese", haystack, flags=re.IGNORECASE):
        return "zh-CN"
    if re.search(r"English|英文|用英文", haystack, flags=re.IGNORECASE):
        return "en-US"
    return None


def select_task_languages(
    *,
    goal: str | None = None,
    query: str | None = None,
    research_goal: str | None = None,
    expected_output: str | None = None,
    language: str | None = None,
    display_language: str | None = None,
    preferred_report_language: str | None = None,
    requested_output_language: str | None = None,
) -> TaskLanguageSelection:
    console_language = normalize_locale(display_language or language)
    explicit = (
        normalize_locale(requested_output_language)
        if requested_output_language
        else infer_requested_output_language(goal, query, research_goal, expected_output)
    )
    legacy_language = None
    if language and language.strip().lower() not in {"auto", ""}:
        legacy_language = normalize_locale(language)
    preferred_report = (
        normalize_locale(preferred_report_language)
        if preferred_report_language
        else None
    )
    report_language = explicit or legacy_language or preferred_report or console_language
    return TaskLanguageSelection(
        display_language=console_language,
        requested_output_language=explicit or legacy_language,
        report_language=report_language,
    )


def is_zh(locale: str | None) -> bool:
    return normalize_locale(locale).startswith("zh")
