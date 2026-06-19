from __future__ import annotations

from playwright.async_api import Page

from webscoper.browser.target import TargetResolver
from webscoper.schemas.browser import ActionContract, ActionResult, ResolvedTarget, TargetCandidate


class ActionExecutor:
    def __init__(self, target_resolver: TargetResolver | None = None) -> None:
        self.target_resolver = target_resolver or TargetResolver()

    async def click(self, page: Page, contract: ActionContract) -> ActionResult:
        url_before = page.url

        try:
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
                    error_type=resolved.error_type or "TARGET_NOT_FOUND",
                    error_message=resolved.error_message,
                )

            return await self._click_resolved(page, contract, resolved, url_before)
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
                metadata=_selected_metadata(resolved),
            )

        if not await locator.is_enabled():
            return ActionResult(
                action_type=contract.action_type,
                status="failed",
                target=resolved,
                url_before=url_before,
                url_after=page.url,
                error_type="TARGET_DISABLED",
                error_message="Resolved target is disabled.",
                metadata=_selected_metadata(resolved),
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
                metadata=_selected_metadata(resolved),
            )

        await locator.click(timeout=1500)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception:
            pass
        await page.wait_for_timeout(300)

        return ActionResult(
            action_type=contract.action_type,
            status="success",
            target=resolved,
            url_before=url_before,
            url_after=page.url,
            metadata=_selected_metadata(resolved),
        )


def _selected_metadata(resolved) -> dict[str, object]:
    if resolved.selected is None:
        return {}
    return {
        "selected_locator_hint": resolved.selected.locator_hint,
        "selected_strategy": resolved.selected.strategy,
        "selected_score": resolved.selected.score,
    }
