from __future__ import annotations

import re
from typing import Any

from playwright.async_api import Locator, Page

from webscoper.schemas.action import ResolvedTarget, TargetCandidate


class TargetResolver:
    async def resolve(
        self,
        page: Page,
        target_hint: str,
        preferred_roles: list[str] | None = None,
        max_candidates: int = 5,
    ) -> ResolvedTarget:
        roles = preferred_roles or []
        candidates: list[TargetCandidate] = []
        seen: set[str] = set()

        for role in roles:
            locator = page.get_by_role(
                role,
                name=re.compile(re.escape(target_hint), re.IGNORECASE),
            )
            await self._collect_candidates(
                locator=locator,
                candidates=candidates,
                seen=seen,
                target_hint=target_hint,
                strategy="role_name",
                locator_hint=f"role={role}[name={target_hint}]",
                role=role,
                max_candidates=max_candidates,
            )
            if len(candidates) >= max_candidates:
                break

        if len(candidates) < max_candidates:
            await self._collect_candidates(
                locator=page.get_by_text(target_hint, exact=False),
                candidates=candidates,
                seen=seen,
                target_hint=target_hint,
                strategy="text",
                locator_hint=f"text={target_hint}",
                role=None,
                max_candidates=max_candidates,
            )

        if len(candidates) < max_candidates:
            aria_selector = f'[aria-label*="{_css_attr_value(target_hint)}" i]'
            await self._collect_candidates(
                locator=page.locator(aria_selector),
                candidates=candidates,
                seen=seen,
                target_hint=target_hint,
                strategy="aria_label",
                locator_hint=aria_selector,
                role=None,
                max_candidates=max_candidates,
            )

        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        candidates = candidates[:max_candidates]
        selected = candidates[0] if candidates else None

        if selected is None:
            return ResolvedTarget(
                target_hint=target_hint,
                error_type="TARGET_NOT_FOUND",
                error_message=f"No target matched hint: {target_hint}",
            )

        return ResolvedTarget(
            target_hint=target_hint,
            selected=selected,
            candidates=candidates,
            confidence=selected.score,
        )

    async def locator_for(self, page: Page, candidate: TargetCandidate) -> Locator:
        if candidate.strategy == "role_name" and candidate.role and candidate.name:
            return page.get_by_role(
                candidate.role,
                name=re.compile(re.escape(candidate.name), re.IGNORECASE),
            ).first

        if candidate.strategy == "text":
            text = candidate.text or candidate.name or _strip_text_hint(candidate.locator_hint)
            return page.get_by_text(text, exact=False).first

        if candidate.strategy == "aria_label":
            return page.locator(candidate.locator_hint).first

        return page.get_by_text(candidate.name or candidate.text or "", exact=False).first

    async def _collect_candidates(
        self,
        locator: Locator,
        candidates: list[TargetCandidate],
        seen: set[str],
        target_hint: str,
        strategy: str,
        locator_hint: str,
        role: str | None,
        max_candidates: int,
    ) -> None:
        try:
            count = min(await locator.count(), max_candidates - len(candidates))
        except Exception:
            return

        for index in range(count):
            current = locator.nth(index)
            candidate = await _candidate_from_locator(
                current,
                target_hint=target_hint,
                strategy=strategy,
                locator_hint=locator_hint,
                role=role,
            )
            if candidate is None:
                continue
            key = _candidate_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)


async def _candidate_from_locator(
    locator: Locator,
    target_hint: str,
    strategy: str,
    locator_hint: str,
    role: str | None,
) -> TargetCandidate | None:
    try:
        data = await locator.evaluate(
            """(el) => {
                const tag = el.tagName.toLowerCase();
                const ariaLabel = el.getAttribute('aria-label') || '';
                const placeholder = el.getAttribute('placeholder') || '';
                const title = el.getAttribute('title') || '';
                const text = (el.innerText || el.textContent || '').trim();
                const value = (el.getAttribute('type') || '').toLowerCase() === 'password'
                    ? ''
                    : (el.value || '');
                const name = ariaLabel || placeholder || text || value || title || tag;
                return { ariaLabel, name, text, value };
            }"""
        )
        if not isinstance(data, dict):
            return None

        visible = await locator.is_visible()
        enabled = await locator.is_enabled()
        bbox = _normalize_bbox(await locator.bounding_box())
        name = _optional_str(data.get("name"))
        text = _optional_str(data.get("text") or data.get("value"))
        score = _score_candidate(
            strategy=strategy,
            visible=visible,
            enabled=enabled,
            bbox=bbox,
            name=name,
            text=text,
            target_hint=target_hint,
        )

        return TargetCandidate(
            strategy=strategy,
            locator_hint=locator_hint,
            role=role,
            name=name,
            text=text,
            visible=visible,
            enabled=enabled,
            bbox=bbox,
            score=score,
        )
    except Exception:
        return None


def _score_candidate(
    strategy: str,
    visible: bool,
    enabled: bool,
    bbox: dict[str, float] | None,
    name: str | None,
    text: str | None,
    target_hint: str,
) -> float:
    score = 0.0
    if visible:
        score += 0.35
    if enabled:
        score += 0.25
    if strategy == "role_name":
        score += 0.25
    elif strategy == "text":
        score += 0.15
    elif strategy == "aria_label":
        score += 0.10
    if bbox is not None:
        score += 0.10
    if _basic_match(target_hint, name) or _basic_match(target_hint, text):
        score += 0.20
    return round(score, 4)


def _basic_match(target_hint: str, value: str | None) -> bool:
    if not value:
        return False
    normalized_hint = " ".join(target_hint.lower().split())
    normalized_value = " ".join(value.lower().split())
    return normalized_hint in normalized_value or normalized_value in normalized_hint


def _candidate_key(candidate: TargetCandidate) -> str:
    bbox = candidate.bbox or {}
    return "|".join(
        [
            candidate.strategy,
            candidate.locator_hint,
            candidate.name or "",
            candidate.text or "",
            str(round(bbox.get("x", 0.0), 2)),
            str(round(bbox.get("y", 0.0), 2)),
        ]
    )


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
    text = str(value).strip()
    return text if text else None


def _css_attr_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _strip_text_hint(locator_hint: str) -> str:
    if locator_hint.startswith("text="):
        return locator_hint.removeprefix("text=")
    return locator_hint
