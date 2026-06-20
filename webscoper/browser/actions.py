from __future__ import annotations

from playwright.async_api import Page

from webscoper.browser.readiness import PageReadinessDetector
from webscoper.browser.target import TargetResolver
from webscoper.schemas.browser import (
    ActionContract,
    ActionResult,
    ReadinessResult,
    ResolvedTarget,
    TargetCandidate,
)


class ActionExecutor:
    def __init__(
        self,
        target_resolver: TargetResolver | None = None,
        readiness_detector: PageReadinessDetector | None = None,
    ) -> None:
        self.target_resolver = target_resolver or TargetResolver()
        self.readiness_detector = readiness_detector or PageReadinessDetector()

    async def click(self, page: Page, contract: ActionContract) -> ActionResult:
        url_before = page.url

        try:
            readiness = await self.readiness_detector.wait_for_readiness(
                page,
                target_hint=contract.target_hint,
                timeout_ms=3000,
            )
            readiness_error = _blocking_readiness_error(readiness)
            if readiness_error is not None:
                return ActionResult(
                    action_type=contract.action_type,
                    status="failed",
                    url_before=url_before,
                    url_after=page.url,
                    error_type=readiness_error[0],
                    error_message=readiness_error[1],
                    metadata=_readiness_metadata(readiness),
                )

            resolved = await self.target_resolver.resolve(
                page,
                target_hint=contract.target_hint,
                preferred_roles=contract.preferred_roles,
            )
            if resolved.selected is None:
                return ActionResult(
                    action_type=contract.action_type,
                    status="failed",
                    target=resolved,
                    url_before=url_before,
                    url_after=page.url,
                    error_type=(
                        "TARGET_NOT_READY"
                        if not readiness.signals.get("target_visible", True)
                        else resolved.error_type or "TARGET_NOT_FOUND"
                    ),
                    error_message=resolved.error_message,
                    metadata=_readiness_metadata(readiness),
                )

            return await self._click_resolved(
                page,
                contract,
                resolved,
                url_before,
                readiness,
            )
        except Exception as exc:
            return ActionResult(
                action_type=contract.action_type,
                status="failed",
                url_before=url_before,
                url_after=page.url,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

    async def click_candidate(
        self,
        page: Page,
        contract: ActionContract,
        candidate: TargetCandidate,
    ) -> ActionResult:
        url_before = page.url
        resolved = ResolvedTarget(
            target_hint=contract.target_hint,
            selected=candidate,
            candidates=[candidate],
            confidence=candidate.score,
        )
        try:
            return await self._click_resolved(page, contract, resolved, url_before)
        except Exception as exc:
            return ActionResult(
                action_type=contract.action_type,
                status="failed",
                target=resolved,
                url_before=url_before,
                url_after=page.url,
                error_type=type(exc).__name__,
                error_message=str(exc),
                metadata=_selected_metadata(resolved),
            )

    async def _click_resolved(
        self,
        page: Page,
        contract: ActionContract,
        resolved: ResolvedTarget,
        url_before: str,
        readiness: ReadinessResult | None = None,
    ) -> ActionResult:
        if resolved.selected is None:
            return ActionResult(
                action_type=contract.action_type,
                status="failed",
                target=resolved,
                url_before=url_before,
                url_after=page.url,
                error_type=resolved.error_type or "TARGET_NOT_FOUND",
                error_message=resolved.error_message,
            )

        if readiness is None:
            readiness = await self.readiness_detector.wait_for_readiness(
                page,
                target_hint=contract.target_hint,
                timeout_ms=2500,
            )
        readiness_error = _blocking_readiness_error(readiness)
        if readiness_error is not None:
            return ActionResult(
                action_type=contract.action_type,
                status="failed",
                target=resolved,
                url_before=url_before,
                url_after=page.url,
                error_type=readiness_error[0],
                error_message=readiness_error[1],
                metadata={**_selected_metadata(resolved), **_readiness_metadata(readiness)},
            )

        locator = await self.target_resolver.locator_for(page, resolved.selected)
        if not await locator.is_visible():
            return ActionResult(
                action_type=contract.action_type,
                status="failed",
                target=resolved,
                url_before=url_before,
                url_after=page.url,
                error_type="TARGET_NOT_VISIBLE",
                error_message="Resolved target is not visible.",
                metadata={**_selected_metadata(resolved), **_readiness_metadata(readiness)},
            )

        if not await locator.is_enabled():
            return ActionResult(
                action_type=contract.action_type,
                status="failed",
                target=resolved,
                url_before=url_before,
                url_after=page.url,
                error_type="TARGET_DISABLED_PENDING_HYDRATION",
                error_message="Resolved target is disabled after waiting for hydration.",
                metadata={**_selected_metadata(resolved), **_readiness_metadata(readiness)},
            )

        bbox = await locator.bounding_box()
        if bbox is None:
            return ActionResult(
                action_type=contract.action_type,
                status="failed",
                target=resolved,
                url_before=url_before,
                url_after=page.url,
                error_type="TARGET_NOT_VISIBLE",
                error_message="Resolved target has no clickable bounding box.",
                metadata={**_selected_metadata(resolved), **_readiness_metadata(readiness)},
            )

        await locator.click(timeout=1500)
        post_action_readiness = await self.readiness_detector.wait_for_readiness(
            page,
            timeout_ms=2500,
        )

        return ActionResult(
            action_type=contract.action_type,
            status="success",
            target=resolved,
            url_before=url_before,
            url_after=page.url,
            metadata={
                **_selected_metadata(resolved),
                **_readiness_metadata(readiness, "pre_action_readiness"),
                **_readiness_metadata(post_action_readiness, "post_action_readiness"),
            },
        )


def _selected_metadata(resolved) -> dict[str, object]:
    if resolved.selected is None:
        return {}
    return {
        "selected_locator_hint": resolved.selected.locator_hint,
        "selected_strategy": resolved.selected.strategy,
        "selected_score": resolved.selected.score,
    }


def _readiness_metadata(
    readiness: ReadinessResult,
    key: str = "readiness",
) -> dict[str, object]:
    return {key: readiness.model_dump(mode="json")}


def _blocking_readiness_error(readiness: ReadinessResult) -> tuple[str, str] | None:
    signals = readiness.signals
    if not signals.get("overlay_absent", True):
        return (
            "TARGET_COVERED_BY_OVERLAY",
            "A blocking overlay or modal covers the page.",
        )
    if not signals.get("spinner_absent", True):
        return ("PAGE_STILL_LOADING", "A loading spinner is still visible.")
    if not signals.get("skeleton_absent", True):
        return ("TARGET_HYDRATING", "Skeleton content is still hydrating.")
    if not signals.get("target_visible", True):
        return ("TARGET_NOT_READY", "The target is not visible yet.")
    if not signals.get("target_enabled", True):
        return (
            "TARGET_DISABLED_PENDING_HYDRATION",
            "The target is visible but disabled while hydration finishes.",
        )
    if readiness.status == "timeout":
        return ("PAGE_LOADING_TIMEOUT", "Page readiness did not settle before timeout.")
    if readiness.status == "loading":
        return ("PAGE_STILL_LOADING", "Page is still loading.")
    return None
