from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.async_api import ElementHandle, Page

from webscoper.browser.risk import detect_risks
from webscoper.schemas.browser import InteractiveElement, PageObservation


INTERACTIVE_SELECTOR = (
    'a, button, input, textarea, select, [role="button"], [role="link"]'
)


async def observe_page(
    page: Page,
    screenshot_path: Path | None = None,
    max_text_chars: int = 4000,
    max_elements: int = 50,
) -> PageObservation:
    url = page.url
    title = await _safe_title(page)
    visible_text_summary = await _safe_body_text(page, max_text_chars=max_text_chars)

    screenshot_path_str: str | None = None
    if screenshot_path is not None:
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path), full_page=True)
        screenshot_path_str = str(screenshot_path)

    interactive_elements = await _collect_interactive_elements(
        page,
        max_elements=max_elements,
    )
    risk_signals = await detect_risks(page)

    return PageObservation(
        url=url,
        title=title,
        visible_text_summary=visible_text_summary,
        interactive_elements=interactive_elements,
        risk_signals=risk_signals,
        screenshot_path=screenshot_path_str,
    )


async def _safe_title(page: Page) -> str:
    try:
        return await page.title()
    except Exception:
        return ""


async def _safe_body_text(page: Page, max_text_chars: int) -> str:
    try:
        text = await page.locator("body").inner_text(timeout=3000)
    except Exception:
        text = ""
    return _truncate(text, max_text_chars)


async def _collect_interactive_elements(
    page: Page,
    max_elements: int,
) -> list[InteractiveElement]:
    try:
        handles = await page.query_selector_all(INTERACTIVE_SELECTOR)
    except Exception:
        return []

    elements: list[InteractiveElement] = []
    for handle in handles[:max_elements]:
        element = await _element_from_handle(handle)
        if element is not None:
            elements.append(element)
    return elements


async def _element_from_handle(
    handle: ElementHandle[Any],
) -> InteractiveElement | None:
    try:
        data = await handle.evaluate(
            """(el) => {
                const tag = el.tagName.toLowerCase();
                const type = (el.getAttribute('type') || '').toLowerCase();
                const role = el.getAttribute('role');
                const ariaLabel = el.getAttribute('aria-label') || '';
                const placeholder = el.getAttribute('placeholder') || '';
                const title = el.getAttribute('title') || '';
                const innerText = (el.innerText || el.textContent || '').trim();
                const value = type === 'password' ? '' : (el.value || '');
                const href = el.getAttribute('href') || '';
                const name = ariaLabel || placeholder || innerText || value || title || href || tag;

                return {
                    tag,
                    role,
                    ariaLabel,
                    placeholder,
                    innerText,
                    value,
                    href,
                    name,
                };
            }"""
        )
        if not isinstance(data, dict):
            return None

        visible = await handle.is_visible()
        enabled = await handle.is_enabled()
        bbox = await handle.bounding_box()
        locator_hint = _build_locator_hint(data)
        name = _truncate(str(data.get("name") or ""), 160)
        text = _truncate(str(data.get("innerText") or data.get("value") or ""), 300)

        return InteractiveElement(
            tag=str(data.get("tag") or ""),
            role=_optional_str(data.get("role")),
            name=name,
            text=text,
            locator_hint=locator_hint,
            visible=visible,
            enabled=enabled,
            bbox=_normalize_bbox(bbox),
            confidence=0.9 if visible else 0.55,
        )
    except Exception:
        return None


def _build_locator_hint(data: dict[str, Any]) -> str | None:
    aria_label = _clean_hint_value(data.get("ariaLabel"))
    if aria_label:
        return f'[aria-label="{aria_label}"]'

    tag = str(data.get("tag") or "").lower()
    text = _clean_hint_value(data.get("innerText"))
    if text and tag in {"a", "button"}:
        return f"text={text}"

    return None


def _clean_hint_value(value: Any) -> str | None:
    if value is None:
        return None
    text = _truncate(str(value).strip().replace("\n", " "), 120)
    if not text:
        return None
    return text.replace('"', '\\"')


def _normalize_bbox(bbox: dict[str, float] | None) -> dict[str, float] | None:
    if bbox is None:
        return None
    return {
        "x": float(bbox.get("x", 0.0)),
        "y": float(bbox.get("y", 0.0)),
        "width": float(bbox.get("width", 0.0)),
        "height": float(bbox.get("height", 0.0)),
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit].rstrip()
