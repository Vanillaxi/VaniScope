from __future__ import annotations

from time import perf_counter
from typing import Any

from playwright.async_api import Page

from webscoper.browser.actions import ActionExecutor
from webscoper.browser.effects import EffectVerifier
from webscoper.browser.observer import observe_page
from webscoper.browser.recovery import RecoveryManager
from webscoper.browser.session import BrowserSession
from webscoper.runtime.execution.events import TaskEventSink
from webscoper.runtime.artifacts.evidence import EvidenceStore
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.runtime.artifacts.transcript import TranscriptStore
from webscoper.schemas.browser import ActionContract
from webscoper.schemas.browser import PageObservation
from webscoper.schemas.artifact import TraceStep


class BrowserRuntime:
    def __init__(
        self,
        trace_recorder: TraceRecorder,
        headless: bool = True,
        transcript_store: TranscriptStore | None = None,
        event_sink: TaskEventSink | None = None,
        evidence_store: EvidenceStore | None = None,
        recovery_manager: RecoveryManager | None = None,
    ) -> None:
        self.trace_recorder = trace_recorder
        self.headless = headless
        self.transcript_store = transcript_store
        self.event_sink = event_sink
        self.evidence_store = evidence_store
        self.action_executor = ActionExecutor()
        self.effect_verifier = EffectVerifier()
        self.recovery_manager = recovery_manager or RecoveryManager()

    async def open_and_observe(self, url: str) -> PageObservation:
        step_id = "step_001"
        screenshot_path = self.trace_recorder.run_dir / f"{step_id}.png"
        start = perf_counter()
        page_url: str | None = None

        try:
            async with BrowserSession(headless=self.headless) as page:
                await page.goto(url, wait_until="domcontentloaded")
                observation = await observe_page(page, screenshot_path=screenshot_path)
                page_url = observation.url
                latency_ms = _elapsed_ms(start)

                self.trace_recorder.record(
                    TraceStep(
                        step_id=step_id,
                        run_id=self.trace_recorder.run_id,
                        phase="browser_runtime",
                        actor="system",
                        action_type="browser_open_observe",
                        status="success",
                        url_before=None,
                        url_after=observation.url,
                        title=observation.title,
                        observation=_model_dump(observation),
                        screenshot_path=str(screenshot_path),
                        latency_ms=latency_ms,
                    )
                )
                return observation
        except Exception as exc:
            latency_ms = _elapsed_ms(start)
            self.trace_recorder.record(
                TraceStep(
                    step_id=step_id,
                    run_id=self.trace_recorder.run_id,
                    phase="browser_runtime",
                    actor="system",
                    action_type="browser_open_observe",
                    status="failed",
                    url_before=None,
                    url_after=page_url,
                    title=None,
                    observation=None,
                    screenshot_path=None,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    latency_ms=latency_ms,
                )
            )
            raise

    async def open_click_and_observe(
        self,
        url: str,
        action: ActionContract,
    ) -> PageObservation:
        run_id = self.trace_recorder.run_id
        overall_start = perf_counter()
        page_url: str | None = None

        try:
            async with BrowserSession(headless=self.headless) as page:
                open_start = perf_counter()
                await page.goto(url, wait_until="domcontentloaded")
                page_url = page.url

                initial_screenshot = self.trace_recorder.run_dir / "step_001_initial.png"
                initial_observation = await observe_page(
                    page,
                    screenshot_path=initial_screenshot,
                )
                self.trace_recorder.record(
                    TraceStep(
                        step_id="step_001",
                        run_id=run_id,
                        phase="browser_runtime",
                        actor="system",
                        action_type="browser_open_observe",
                        status="success",
                        url_before=None,
                        url_after=initial_observation.url,
                        title=initial_observation.title,
                        observation=_model_dump(initial_observation),
                        screenshot_path=str(initial_screenshot),
                        latency_ms=_elapsed_ms(open_start),
                    )
                )

                body_text_before = await _body_text(page)

                action_start = perf_counter()
                action_result = await self.action_executor.click(page, action)
                self.trace_recorder.record(
                    TraceStep(
                        step_id="step_002",
                        run_id=run_id,
                        phase="browser_runtime",
                        actor="system",
                        action_type="browser_click_intent",
                        status=action_result.status,
                        url_before=action_result.url_before,
                        url_after=action_result.url_after,
                        title=await _safe_title(page),
                        observation=_model_dump(action_result),
                        screenshot_path=None,
                        error_type=action_result.error_type,
                        error_message=action_result.error_message,
                        latency_ms=_elapsed_ms(action_start),
                    )
                )

                verify_start = perf_counter()
                verification_result = await self.effect_verifier.verify(
                    page,
                    expected=action.expected_effect,
                    url_before=action_result.url_before,
                    body_text_before=body_text_before,
                )
                self.trace_recorder.record(
                    TraceStep(
                        step_id="step_003",
                        run_id=run_id,
                        phase="browser_runtime",
                        actor="system",
                        action_type="effect_verify",
                        status="success" if verification_result.satisfied else "failed",
                        url_before=verification_result.url_before,
                        url_after=verification_result.url_after,
                        title=await _safe_title(page),
                        observation=_model_dump(verification_result),
                        screenshot_path=None,
                        error_type=verification_result.error_type,
                        error_message=verification_result.message
                        if not verification_result.satisfied
                        else None,
                        latency_ms=_elapsed_ms(verify_start),
                    )
                )

                if action_result.status != "success" or not verification_result.satisfied:
                    recovery_observation = await observe_page(page)
                    error_type = self.recovery_manager.classify_failure(
                        action_result=action_result,
                        verification_result=verification_result,
                        observation=recovery_observation,
                        target_hint=action.target_hint,
                    )

                    async def recover_observe() -> PageObservation:
                        return await observe_page(page)

                    async def recover_resolve():
                        return await self.action_executor.target_resolver.resolve(
                            page,
                            target_hint=action.target_hint,
                            preferred_roles=action.preferred_roles,
                        )

                    async def recover_click(candidate=None):
                        if candidate is None:
                            return await self.action_executor.click(page, action)
                        return await self.action_executor.click_candidate(
                            page,
                            action,
                            candidate,
                        )

                    async def recover_verify():
                        return await self.effect_verifier.verify(
                            page,
                            expected=action.expected_effect,
                            url_before=action_result.url_before,
                            body_text_before=body_text_before,
                        )

                    recovery_result = await self.recovery_manager.recover_click_intent(
                        page=page,
                        task_id=run_id,
                        target_hint=action.target_hint,
                        expected_content=action.expected_effect.value
                        if action.expected_effect.type == "content_appears"
                        else None,
                        observe_fn=recover_observe,
                        resolve_fn=recover_resolve,
                        execute_click_fn=recover_click,
                        verify_fn=recover_verify,
                        trace_recorder=self.trace_recorder,
                        event_sink=self.event_sink,
                        evidence_store=self.evidence_store,
                        transcript_store=self.transcript_store,
                        initial_error_type=error_type,
                        initial_observation=recovery_observation,
                        action_result=action_result,
                        verification_result=verification_result,
                    )
                    if recovery_result.blocked:
                        final_screenshot = self.trace_recorder.run_dir / "step_004_after.png"
                        final_observation = await observe_page(
                            page,
                            screenshot_path=final_screenshot,
                        )
                        self.trace_recorder.record(
                            TraceStep(
                                step_id="step_004",
                                run_id=run_id,
                                phase="browser_runtime",
                                actor="system",
                                action_type="browser_final_observe",
                                status="blocked",
                                url_before=initial_observation.url,
                                url_after=final_observation.url,
                                title=final_observation.title,
                                observation=_model_dump(final_observation),
                                screenshot_path=str(final_screenshot),
                                error_type=recovery_result.final_error_type.value
                                if recovery_result.final_error_type is not None
                                else None,
                                error_message=recovery_result.message,
                            )
                        )
                        return final_observation

                final_start = perf_counter()
                final_screenshot = self.trace_recorder.run_dir / "step_004_after.png"
                final_observation = await observe_page(
                    page,
                    screenshot_path=final_screenshot,
                )
                self.trace_recorder.record(
                    TraceStep(
                        step_id="step_004",
                        run_id=run_id,
                        phase="browser_runtime",
                        actor="system",
                        action_type="browser_final_observe",
                        status="success",
                        url_before=initial_observation.url,
                        url_after=final_observation.url,
                        title=final_observation.title,
                        observation=_model_dump(final_observation),
                        screenshot_path=str(final_screenshot),
                        latency_ms=_elapsed_ms(final_start),
                    )
                )
                return final_observation
        except Exception as exc:
            self.trace_recorder.record(
                TraceStep(
                    step_id="step_001",
                    run_id=run_id,
                    phase="browser_runtime",
                    actor="system",
                    action_type="browser_open_observe",
                    status="failed",
                    url_before=None,
                    url_after=page_url,
                    title=None,
                    observation=None,
                    screenshot_path=None,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    latency_ms=_elapsed_ms(overall_start),
                )
            )
            raise


def _elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def _model_dump(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


async def _body_text(page: Page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=3000)
    except Exception:
        return ""


async def _safe_title(page: Page) -> str:
    try:
        return await page.title()
    except Exception:
        return ""
