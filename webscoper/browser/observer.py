from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

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
    include_accessibility: bool = True,
) -> PageObservation:
    url = page.url
    title = await _safe_title(page)
    visible_text_summary = await _safe_body_text(page, max_text_chars=max_text_chars)
    main_content_summary = await _main_content_text(page, max_text_chars=max_text_chars)

    screenshot_path_str: str | None = None
    if screenshot_path is not None:
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path), full_page=True)
        screenshot_path_str = str(screenshot_path)

    interactive_elements = await _collect_interactive_elements(
        page,
        max_elements=max_elements,
    )
    accessibility_summary = (
        _accessibility_summary(interactive_elements) if include_accessibility else None
    )
    risk_signals = await detect_risks(page)

    return PageObservation(
        observation_id=f"obs_{uuid4().hex[:12]}",
        observation_mode="dom_with_screenshot" if screenshot_path_str else "dom_only",
        url=url,
        title=title,
        visible_text_summary=visible_text_summary,
        main_content_summary=main_content_summary,
        accessibility_summary=accessibility_summary,
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


async def _main_content_text(page: Page, max_text_chars: int) -> str:
    try:
        text = await page.evaluate(
            """() => {
                const blocked = ['nav', 'header', 'footer', '[role="navigation"]', '[aria-label*="cookie" i]', '.cookie', '.banner'];
                const clone = document.body ? document.body.cloneNode(true) : null;
                if (!clone) return '';
                for (const selector of blocked) {
                    clone.querySelectorAll(selector).forEach((el) => el.remove());
                }
                const main = clone.querySelector('main, [role="main"], article') || clone;
                return String(main.innerText || main.textContent || '').replace(/\\s+/g, ' ').trim();
            }"""
        )
    except Exception:
        text = ""
    return _truncate(str(text or ""), max_text_chars)


async def _collect_interactive_elements(
    page: Page,
    max_elements: int,
) -> list[InteractiveElement]:
    try:
        handles = await page.query_selector_all(INTERACTIVE_SELECTOR)
    except Exception:
        return []

    elements: list[InteractiveElement] = []
    for index, handle in enumerate(handles[:max_elements], start=1):
        element = await _element_from_handle(handle, index=index)
        if element is not None:
            elements.append(element)
    return elements


async def _element_from_handle(
    handle: ElementHandle[Any],
    *,
    index: int,
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
                    id: el.id || el.getAttribute('data-testid') || '',
                    tag,
                    role,
                    ariaLabel,
                    placeholder,
                    innerText,
                    value,
                    href,
                    name,
                    type,
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
            id=_element_id(data, index),
            tag=str(data.get("tag") or ""),
            role=_optional_str(data.get("role")),
            name=name,
            text=text,
            href=_optional_str(data.get("href")),
            locator_hint=locator_hint,
            visible=visible,
            enabled=enabled,
            is_visible=visible,
            is_enabled=enabled,
            risk_hint=_risk_hint(data, name, text),
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


def _element_id(data: dict[str, Any], index: int) -> str:
    raw_id = _optional_str(data.get("id"))
    if raw_id:
        return f"el_{index:03d}_{_slug(raw_id)[:32]}"
    tag = str(data.get("tag") or "el")
    name = str(data.get("name") or "")
    return f"el_{index:03d}_{_slug(tag + '_' + name)[:32]}"


def _risk_hint(data: dict[str, Any], name: str, text: str) -> str:
    joined = " ".join(
        [
            str(data.get("tag") or ""),
            str(data.get("role") or ""),
            str(data.get("type") or ""),
            name,
            text,
            str(data.get("href") or ""),
        ]
    ).lower()
    if any(term in joined for term in ("password", "sign in", "login", "验证码", "密码")):
        return "auth"
    if any(term in joined for term in ("pay", "checkout", "credit", "buy", "支付", "购买")):
        return "payment"
    if any(term in joined for term in ("delete", "remove", "删除", "移除")):
        return "destructive"
    if any(term in joined for term in ("submit", "send", "publish", "post", "提交", "发送", "发布")):
        return "submit"
    if str(data.get("tag") or "").lower() in {"input", "textarea", "select"}:
        return "input"
    if data.get("href"):
        return "navigation"
    return "read_only"


def _accessibility_summary(elements: list[InteractiveElement]) -> str:
    if not elements:
        return "No visible interactive accessibility targets detected."
    items = []
    for element in elements[:20]:
        role = element.role or element.tag
        label = element.name or element.text or element.href or ""
        state = "enabled" if element.enabled else "disabled"
        items.append(f"{element.id}: {role} {label} ({state}, {element.risk_hint})")
    return "\n".join(items)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit].rstrip()


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "element"
