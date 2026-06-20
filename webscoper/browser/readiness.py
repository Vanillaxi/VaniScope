from __future__ import annotations

import hashlib
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from playwright.async_api import Page

from webscoper.schemas.browser import ReadinessResult


DEFAULT_POLL_INTERVAL_MS = 250
DEFAULT_STABLE_SAMPLES = 3
DEFAULT_TIMEOUT_MS = 3500


class PageReadinessDetector:
    def __init__(
        self,
        *,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        stable_samples: int = DEFAULT_STABLE_SAMPLES,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> None:
        self.poll_interval_ms = max(100, poll_interval_ms)
        self.stable_samples = max(2, stable_samples)
        self.timeout_ms = max(200, timeout_ms)

    async def wait_for_readiness(
        self,
        page: Page,
        *,
        target_hint: str | None = None,
        timeout_ms: int | None = None,
    ) -> ReadinessResult:
        timeout = self.timeout_ms if timeout_ms is None else max(100, timeout_ms)
        start = perf_counter()
        samples: list[_ReadinessSample] = []
        last_result: ReadinessResult | None = None

        while True:
            sample = await _sample_page(page, target_hint=target_hint)
            samples.append(sample)
            samples = samples[-self.stable_samples :]
            last_result = _result_from_samples(
                samples,
                elapsed_ms=_elapsed_ms(start),
                target_hint=target_hint,
                timed_out=False,
                required_stable_samples=self.stable_samples,
            )
            if last_result.status in {"ready", "degraded_ready"}:
                return last_result
            if _elapsed_ms(start) >= timeout:
                return _result_from_samples(
                    samples,
                    elapsed_ms=_elapsed_ms(start),
                    target_hint=target_hint,
                    timed_out=True,
                    required_stable_samples=self.stable_samples,
                )
            await page.wait_for_timeout(self.poll_interval_ms)


async def wait_for_page_readiness(
    page: Page,
    *,
    target_hint: str | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> ReadinessResult:
    return await PageReadinessDetector(timeout_ms=timeout_ms).wait_for_readiness(
        page,
        target_hint=target_hint,
    )


async def wait_for_target_readiness(
    page: Page,
    *,
    target_hint: str,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> ReadinessResult:
    return await wait_for_page_readiness(
        page,
        target_hint=target_hint,
        timeout_ms=timeout_ms,
    )


async def wait_after_navigation_or_action(
    page: Page,
    *,
    target_hint: str | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> ReadinessResult:
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=1000)
    except Exception:
        pass
    try:
        await page.wait_for_timeout(150)
    except Exception:
        pass
    return await wait_for_page_readiness(
        page,
        target_hint=target_hint,
        timeout_ms=timeout_ms,
    )


@dataclass(frozen=True)
class _ReadinessSample:
    url: str
    title: str
    ready_state: str
    text_hash: str
    text_length: int
    interactive_count: int
    spinner_present: bool
    skeleton_present: bool
    overlay_present: bool
    target_visible: bool | None
    target_enabled: bool | None
    target_box_hash: str | None
    layout_hash: str
    resource_count: int
    pending_fetches: int


async def _sample_page(page: Page, *, target_hint: str | None) -> _ReadinessSample:
    data = await page.evaluate(
        """(targetHint) => {
            const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
            const visible = (el) => {
                if (!el || !(el instanceof Element)) return false;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const selectors = {
                spinner: [
                    '[aria-busy="true"]',
                    '[role="progressbar"]',
                    '.spinner',
                    '.loading',
                    '.loader',
                    '[data-loading="true"]'
                ],
                skeleton: [
                    '.skeleton',
                    '[data-skeleton]',
                    '[aria-label*="skeleton" i]',
                    '[class*="skeleton" i]',
                    '[class*="placeholder" i]'
                ],
                overlay: [
                    '[role="dialog"]',
                    '[aria-modal="true"]',
                    '.modal',
                    '.overlay',
                    '[data-overlay]',
                    '[data-blocking-overlay="true"]'
                ],
                interactive: 'a, button, input, textarea, select, [role="button"], [role="link"]'
            };
            const anyVisible = (items) => items.some((selector) =>
                Array.from(document.querySelectorAll(selector)).some(visible)
            );
            const bodyText = normalize(document.body ? document.body.innerText : '');
            const interactive = Array.from(document.querySelectorAll(selectors.interactive)).filter(visible);
            let targetVisible = null;
            let targetEnabled = null;
            let targetBoxHash = null;
            if (targetHint) {
                const hint = String(targetHint).toLowerCase();
                const candidates = interactive.filter((el) => {
                    const label = normalize(
                        el.getAttribute('aria-label') ||
                        el.getAttribute('placeholder') ||
                        el.innerText ||
                        el.textContent ||
                        el.getAttribute('title') ||
                        el.getAttribute('href') ||
                        ''
                    ).toLowerCase();
                    return label.includes(hint);
                });
                const target = candidates[0] || null;
                targetVisible = visible(target);
                targetEnabled = target ? !target.disabled && target.getAttribute('aria-disabled') !== 'true' : false;
                if (target) {
                    const rect = target.getBoundingClientRect();
                    targetBoxHash = [rect.x, rect.y, rect.width, rect.height].map((v) => Math.round(v)).join(':');
                }
            }
            const root = document.documentElement;
            const body = document.body;
            const layoutHash = [
                root ? root.scrollWidth : 0,
                root ? root.scrollHeight : 0,
                body ? body.offsetWidth : 0,
                body ? body.offsetHeight : 0,
                window.innerWidth,
                window.innerHeight
            ].map((v) => Math.round(Number(v || 0))).join(':');
            return {
                url: location.href,
                title: document.title || '',
                readyState: document.readyState || '',
                bodyText,
                interactiveCount: interactive.length,
                spinnerPresent: anyVisible(selectors.spinner),
                skeletonPresent: anyVisible(selectors.skeleton),
                overlayPresent: anyVisible(selectors.overlay),
                targetVisible,
                targetEnabled,
                targetBoxHash,
                layoutHash,
                resourceCount: performance.getEntriesByType('resource').length,
                pendingFetches: Number(window.__webscoperPendingRequests || 0)
            };
        }""",
        target_hint,
    )
    text = str(data.get("bodyText") or "")
    return _ReadinessSample(
        url=str(data.get("url") or page.url),
        title=str(data.get("title") or ""),
        ready_state=str(data.get("readyState") or ""),
        text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        text_length=len(text),
        interactive_count=int(data.get("interactiveCount") or 0),
        spinner_present=bool(data.get("spinnerPresent")),
        skeleton_present=bool(data.get("skeletonPresent")),
        overlay_present=bool(data.get("overlayPresent")),
        target_visible=_optional_bool(data.get("targetVisible")),
        target_enabled=_optional_bool(data.get("targetEnabled")),
        target_box_hash=_optional_str(data.get("targetBoxHash")),
        layout_hash=str(data.get("layoutHash") or ""),
        resource_count=int(data.get("resourceCount") or 0),
        pending_fetches=int(data.get("pendingFetches") or 0),
    )


def _result_from_samples(
    samples: list[_ReadinessSample],
    *,
    elapsed_ms: int,
    target_hint: str | None,
    timed_out: bool,
    required_stable_samples: int,
) -> ReadinessResult:
    current = samples[-1]
    stable = len(samples) >= required_stable_samples or len(samples) >= 2 and timed_out
    signals = {
        "dom_complete": current.ready_state == "complete",
        "url_stable": stable and _all_equal(sample.url for sample in samples),
        "title_stable": stable and _all_equal(sample.title for sample in samples),
        "text_stable": stable and _all_equal(sample.text_hash for sample in samples),
        "interactive_elements_stable": stable
        and _all_equal(sample.interactive_count for sample in samples),
        "spinner_absent": not current.spinner_present,
        "skeleton_absent": not current.skeleton_present,
        "overlay_absent": not current.overlay_present,
        "layout_stable": stable and _all_equal(sample.layout_hash for sample in samples),
        "soft_network_quiet": stable
        and current.pending_fetches == 0
        and _all_equal(sample.resource_count for sample in samples),
    }
    if target_hint:
        signals["target_visible"] = bool(current.target_visible)
        signals["target_enabled"] = bool(current.target_enabled)
        signals["target_stable"] = stable and _all_equal(
            sample.target_box_hash for sample in samples
        )

    warnings = _warnings_for(signals, timed_out=timed_out)
    blockers = [
        "spinner_absent",
        "skeleton_absent",
        "overlay_absent",
        "url_stable",
        "title_stable",
        "text_stable",
        "interactive_elements_stable",
    ]
    if target_hint:
        blockers.extend(["target_visible", "target_enabled", "target_stable"])

    ready = all(signals.get(name, False) for name in blockers)
    usable = (
        signals["url_stable"]
        and signals["text_stable"]
        and signals["interactive_elements_stable"]
        and signals["overlay_absent"]
        and (not target_hint or (signals["target_visible"] and signals["target_enabled"]))
    )

    if ready and signals["soft_network_quiet"] and (signals["dom_complete"] or timed_out):
        status = "ready"
    elif ready and not signals["soft_network_quiet"]:
        status = "degraded_ready"
        warnings.append("Network activity is still changing; content appears usable.")
    elif timed_out and (current.spinner_present or current.skeleton_present):
        status = "loading"
    elif usable and timed_out:
        status = "degraded_ready"
        warnings.append("Timed out before every readiness signal was clean, but page is usable.")
    elif usable and not signals["soft_network_quiet"]:
        status = "degraded_ready"
        warnings.append("Network activity is still changing; content appears usable.")
    elif timed_out and current.text_length > 0 and signals["overlay_absent"]:
        status = "degraded_ready"
        warnings.append("Readiness timed out with stable enough visible content.")
    elif timed_out:
        status = "timeout"
    else:
        status = "loading"

    confidence = _confidence(signals, status=status)
    return ReadinessResult(
        status=status,
        confidence=confidence,
        signals=signals,
        warnings=_dedupe(warnings),
        elapsed_ms=elapsed_ms,
        metadata={
            "sample_count": len(samples),
            "target_hint": target_hint,
            "ready_state": current.ready_state,
            "text_length": current.text_length,
            "interactive_count": current.interactive_count,
        },
    )


def _warnings_for(signals: dict[str, bool], *, timed_out: bool) -> list[str]:
    labels = {
        "dom_complete": "Document did not reach complete readyState.",
        "spinner_absent": "Loading spinner is still visible.",
        "skeleton_absent": "Skeleton placeholder is still visible.",
        "overlay_absent": "Blocking overlay or modal is visible.",
        "target_visible": "Target is not visible.",
        "target_enabled": "Target is not enabled yet.",
        "target_stable": "Target layout is still changing.",
        "soft_network_quiet": "Soft network quiet signal did not settle.",
        "text_stable": "Visible text is still changing.",
        "interactive_elements_stable": "Interactive element count is still changing.",
    }
    warnings = [message for key, message in labels.items() if signals.get(key) is False]
    if timed_out:
        warnings.append("Readiness polling reached its timeout.")
    return warnings


def _confidence(signals: dict[str, bool], *, status: str) -> float:
    if not signals:
        return 0.0
    base = sum(1 for value in signals.values() if value) / len(signals)
    if status == "ready":
        base = max(base, 0.92)
    elif status == "degraded_ready":
        base = min(max(base, 0.55), 0.82)
    elif status == "loading":
        base = min(base, 0.45)
    else:
        base = min(base, 0.35)
    return round(base, 4)


def _all_equal(values: Any) -> bool:
    items = list(values)
    return len(set(items)) <= 1


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
