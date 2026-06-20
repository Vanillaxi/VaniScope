from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

from playwright.async_api import Page

from webscoper.browser.actions import ActionExecutor
from webscoper.browser.effects import EffectVerifier
from webscoper.browser.observer import observe_page
from webscoper.browser.public_web import (
    PublicWebPolicy,
    PublicWebPolicyError,
    PublicWebRuntimeConfig,
)
from webscoper.browser.readiness import (
    PageReadinessDetector,
    wait_after_navigation_or_action,
)
from webscoper.browser.recovery import RecoveryManager
from webscoper.browser.session import BrowserSession
from webscoper.runtime.execution.events import TaskEventSink
from webscoper.runtime.artifacts.evidence import EvidenceStore
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.runtime.artifacts.transcript import TranscriptStore
from webscoper.schemas.browser import ActionContract, EffectVerificationResult, RiskSignal
from webscoper.schemas.browser import PageObservation, ReadinessResult
from webscoper.schemas.artifact import TraceStep


class StatefulBrowserToolRuntime:
    def __init__(
        self,
        trace_recorder: TraceRecorder,
        headless: bool = True,
        transcript_store: TranscriptStore | None = None,
        event_sink: TaskEventSink | None = None,
        evidence_store: EvidenceStore | None = None,
        recovery_manager: RecoveryManager | None = None,
        public_web_config: PublicWebRuntimeConfig | None = None,
    ) -> None:
        self.trace_recorder = trace_recorder
        self.headless = headless
        self.transcript_store = transcript_store
        self.event_sink = event_sink
        self.evidence_store = evidence_store
        self.session: BrowserSession | None = None
        self.page: Page | None = None
        self.last_observation: PageObservation | None = None
        self.readiness_detector = PageReadinessDetector()
        self.action_executor = ActionExecutor(readiness_detector=self.readiness_detector)
        self.effect_verifier = EffectVerifier()
        self.recovery_manager = recovery_manager or RecoveryManager()
        self.public_web_config = public_web_config or PublicWebRuntimeConfig()
        self.public_web_policy = PublicWebPolicy(self.public_web_config)
        self._public_pages_opened = 0
        self._step_index = 0

    async def start(self) -> None:
        self.session = BrowserSession(headless=self.headless)
        self.page = await self.session.__aenter__()

    async def close(self) -> None:
        if self.session is None:
            return
        try:
            await self.session.__aexit__(None, None, None)
        except Exception:
            pass
        finally:
            self.session = None
            self.page = None

    async def open_observe(self, url: str) -> PageObservation:
        step_id = self._next_step_id()
        screenshot_path = self.trace_recorder.run_dir / f"{step_id}_open.png"
        start = perf_counter()
        page_url: str | None = None
        policy_decision = self.public_web_policy.check(
            url,
            pages_opened=self._public_pages_opened,
        )
        if not policy_decision.allow:
            observation = _blocked_policy_observation(url, policy_decision)
            self.last_observation = observation
            payload = policy_decision.model_dump(mode="json")
            self.trace_recorder.record(
                TraceStep(
                    step_id=step_id,
                    run_id=self.trace_recorder.run_id,
                    phase="browser_tool_runtime",
                    actor="tool",
                    action_type="browser_open_observe",
                    status="blocked",
                    url_before=None,
                    url_after=url,
                    title=observation.title,
                    observation=observation.model_dump(mode="json"),
                    error_type="PUBLIC_WEB_BLOCKED",
                    error_message=policy_decision.reason,
                    latency_ms=_elapsed_ms(start),
                )
            )
            self._emit_public_web_block(policy_decision)
            raise PublicWebPolicyError(policy_decision, observation)

        if policy_decision.url_classification == "public_http":
            self._public_pages_opened += 1
            if self.public_web_config.request_delay_ms > 0:
                await asyncio.sleep(self.public_web_config.request_delay_ms / 1000)

        try:
            if self.page is None:
                await self.start()
            page = self._require_page()
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.public_web_config.navigation_timeout_ms,
            )
            readiness = await self._wait_and_record_readiness(
                page,
                action_type="readiness_check",
                url_before=None,
                target_hint=None,
                timeout_ms=4000,
            )
            observation = await observe_page(page, screenshot_path=screenshot_path)
            observation.metadata["readiness"] = readiness.model_dump(mode="json")
            observation.metadata["public_web_policy"] = policy_decision.model_dump(
                mode="json"
            )
            page_url = observation.url
            self.last_observation = observation
            self.trace_recorder.record(
                TraceStep(
                    step_id=step_id,
                    run_id=self.trace_recorder.run_id,
                    phase="browser_tool_runtime",
                    actor="tool",
                    action_type="browser_open_observe",
                    status="success",
                    url_before=None,
                    url_after=observation.url,
                    title=observation.title,
                    observation=observation.model_dump(mode="json"),
                    screenshot_path=str(screenshot_path),
                    latency_ms=_elapsed_ms(start),
                )
            )
            return observation
        except Exception as exc:
            self.trace_recorder.record(
                TraceStep(
                    step_id=step_id,
                    run_id=self.trace_recorder.run_id,
                    phase="browser_tool_runtime",
                    actor="tool",
                    action_type="browser_open_observe",
                    status="failed",
                    url_before=None,
                    url_after=page_url,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    latency_ms=_elapsed_ms(start),
                )
            )
            raise

    def _emit_public_web_block(self, decision) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(
                "risk_blocked",
                "Public web URL blocked",
                {
                    "run_id": self.trace_recorder.run_id,
                    "tool_name": "browser_open_observe",
                    "error_type": "PUBLIC_WEB_BLOCKED",
                    "public_web_policy": decision.model_dump(mode="json"),
                },
            )
        except Exception:
            return

    async def click_intent(self, action: ActionContract) -> dict[str, Any]:
        if self.page is None:
            return _failed_output("PAGE_NOT_OPENED", "Open a page before clicking.")

        page = self.page
        body_text_before = await _body_text(page)
        action_step_id = self._next_step_id()
        action_start = perf_counter()
        action_result = await self.action_executor.click(page, action)
        self.trace_recorder.record(
            TraceStep(
                step_id=action_step_id,
                run_id=self.trace_recorder.run_id,
                phase="browser_tool_runtime",
                actor="tool",
                action_type="browser_click_intent",
                status=action_result.status,
                url_before=action_result.url_before,
                url_after=action_result.url_after,
                title=await _safe_title(page),
                observation=action_result.model_dump(mode="json"),
                error_type=action_result.error_type,
                error_message=action_result.error_message,
                latency_ms=_elapsed_ms(action_start),
            )
        )

        transition_readiness = await self._wait_and_record_readiness(
            page,
            action_type="post_action_readiness",
            url_before=action_result.url_before,
            target_hint=None,
            timeout_ms=3500,
        )

        verify_step_id = self._next_step_id()
        verify_start = perf_counter()
        verification_result = await self._verify_after_transition(
            page=page,
            action=action,
            action_result=action_result,
            body_text_before=body_text_before,
            initial_readiness=transition_readiness,
        )
        self.trace_recorder.record(
            TraceStep(
                step_id=verify_step_id,
                run_id=self.trace_recorder.run_id,
                phase="browser_tool_runtime",
                actor="tool",
                action_type="effect_verify",
                status="success" if verification_result.satisfied else "failed",
                url_before=verification_result.url_before,
                url_after=verification_result.url_after,
                title=await _safe_title(page),
                observation={
                    **verification_result.model_dump(mode="json"),
                    "transition_readiness": transition_readiness.model_dump(mode="json"),
                },
                error_type=verification_result.error_type,
                error_message=verification_result.message
                if not verification_result.satisfied
                else None,
                latency_ms=_elapsed_ms(verify_start),
            )
        )

        recovery_result = None
        if action_result.status != "success" or not verification_result.satisfied:
            recovery_observation = await observe_page(page)
            self.last_observation = recovery_observation
            error_type = self.recovery_manager.classify_failure(
                action_result=action_result,
                verification_result=verification_result,
                observation=recovery_observation,
                target_hint=action.target_hint,
            )

            async def recover_observe() -> PageObservation:
                observation = await observe_page(page)
                self.last_observation = observation
                return observation

            async def recover_resolve():
                return await self.action_executor.target_resolver.resolve(
                    page,
                    target_hint=action.target_hint,
                    preferred_roles=action.preferred_roles,
                )

            async def recover_click(candidate=None):
                if candidate is None:
                    return await self.action_executor.click(page, action)
                return await self.action_executor.click_candidate(page, action, candidate)

            async def recover_verify():
                return await self.effect_verifier.verify(
                    page,
                    expected=action.expected_effect,
                    url_before=action_result.url_before,
                    body_text_before=body_text_before,
                )

            recovery_result = await self.recovery_manager.recover_click_intent(
                page=page,
                task_id=self.trace_recorder.run_id,
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

        observe_step_id = self._next_step_id()
        observe_start = perf_counter()
        screenshot_path = self.trace_recorder.run_dir / f"{observe_step_id}_after_click.png"
        observation = await observe_page(page, screenshot_path=screenshot_path)
        observation.metadata["readiness"] = (
            await self.readiness_detector.wait_for_readiness(page, timeout_ms=1000)
        ).model_dump(mode="json")
        self.last_observation = observation
        self.trace_recorder.record(
            TraceStep(
                step_id=observe_step_id,
                run_id=self.trace_recorder.run_id,
                phase="browser_tool_runtime",
                actor="tool",
                action_type="browser_observe_after_click",
                status="success",
                url_before=action_result.url_before,
                url_after=observation.url,
                title=observation.title,
                observation=observation.model_dump(mode="json"),
                screenshot_path=str(screenshot_path),
                latency_ms=_elapsed_ms(observe_start),
            )
        )

        status = (
            "success"
            if (
                action_result.status == "success"
                and verification_result.satisfied
                or (recovery_result is not None and recovery_result.recovered)
            )
            else "failed"
        )
        if recovery_result is not None and recovery_result.blocked:
            status = "blocked"
        error_type = action_result.error_type or verification_result.error_type
        error_message = action_result.error_message
        if error_message is None and not verification_result.satisfied:
            error_message = verification_result.message
        if recovery_result is not None and recovery_result.recovered:
            error_type = None
            error_message = None
        elif recovery_result is not None and recovery_result.final_error_type is not None:
            error_type = recovery_result.final_error_type.value
            error_message = recovery_result.message

        return {
            "status": status,
            "error_type": error_type,
            "error_message": error_message,
            "action_result": action_result.model_dump(mode="json"),
            "verification_result": verification_result.model_dump(mode="json"),
            "observation": observation.model_dump(mode="json"),
            "recovery_result": recovery_result.model_dump(mode="json")
            if recovery_result is not None
            else None,
        }

    async def extract(self) -> dict[str, Any]:
        if self.page is None:
            output = _failed_output("PAGE_NOT_OPENED", "Open a page before extracting.")
            self._record_simple_trace("browser_extract", output, status="failed")
            return output

        start = perf_counter()
        step_id = self._next_step_id()
        try:
            observation = await observe_page(self.page)
            observation.metadata["readiness"] = (
                await self.readiness_detector.wait_for_readiness(
                    self.page,
                    timeout_ms=1000,
                )
            ).model_dump(mode="json")
            self.last_observation = observation
            output = _observation_extract(observation)
            self.trace_recorder.record(
                TraceStep(
                    step_id=step_id,
                    run_id=self.trace_recorder.run_id,
                    phase="browser_tool_runtime",
                    actor="tool",
                    action_type="browser_extract",
                    status="success",
                    url_before=None,
                    url_after=observation.url,
                    title=observation.title,
                    observation=output,
                    latency_ms=_elapsed_ms(start),
                )
            )
            return output
        except Exception as exc:
            output = _failed_output(type(exc).__name__, str(exc))
            self.trace_recorder.record(
                TraceStep(
                    step_id=step_id,
                    run_id=self.trace_recorder.run_id,
                    phase="browser_tool_runtime",
                    actor="tool",
                    action_type="browser_extract",
                    status="failed",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    latency_ms=_elapsed_ms(start),
                )
            )
            return output

    async def finish_task(self, summary: str | None = None) -> dict[str, Any]:
        observation = self.last_observation
        output = {
            "status": "success",
            "summary": summary or "Browser task completed.",
            "final_url": observation.url if observation else None,
            "final_title": observation.title if observation else None,
        }
        self._record_simple_trace("finish_task", output, status="success")
        return output

    def _require_page(self) -> Page:
        if self.page is None:
            raise RuntimeError("Browser tool runtime has not been started.")
        return self.page

    async def _wait_and_record_readiness(
        self,
        page: Page,
        *,
        action_type: str,
        url_before: str | None,
        target_hint: str | None,
        timeout_ms: int,
    ) -> ReadinessResult:
        start = perf_counter()
        readiness = await wait_after_navigation_or_action(
            page,
            target_hint=target_hint,
            timeout_ms=timeout_ms,
        )
        self.trace_recorder.record(
            TraceStep(
                step_id=self._next_step_id(),
                run_id=self.trace_recorder.run_id,
                phase="browser_tool_runtime",
                actor="tool",
                action_type=action_type,
                status=readiness.status,
                url_before=url_before,
                url_after=page.url,
                title=await _safe_title(page),
                observation={"readiness": readiness.model_dump(mode="json")},
                error_type=_readiness_error_type(readiness),
                error_message="; ".join(readiness.warnings) if readiness.warnings else None,
                latency_ms=_elapsed_ms(start),
            )
        )
        if self.event_sink is not None:
            try:
                self.event_sink(
                    "readiness_check",
                    "Browser readiness checked",
                    {
                        "status": readiness.status,
                        "confidence": readiness.confidence,
                        "warnings": readiness.warnings,
                        "signals": readiness.signals,
                    },
                )
            except Exception:
                pass
        return readiness

    async def _verify_after_transition(
        self,
        *,
        page: Page,
        action: ActionContract,
        action_result,
        body_text_before: str,
        initial_readiness: ReadinessResult,
    ) -> EffectVerificationResult:
        metadata_attempts = [
            {
                "kind": "initial_readiness",
                "readiness": initial_readiness.model_dump(mode="json"),
            }
        ]
        result = await self.effect_verifier.verify(
            page,
            expected=action.expected_effect,
            url_before=action_result.url_before,
            body_text_before=body_text_before,
            timeout_ms=1800,
        )
        if result.satisfied:
            return result

        for attempt in range(1, 3):
            readiness = await self.readiness_detector.wait_for_readiness(
                page,
                timeout_ms=1800,
            )
            await observe_page(page)
            result = await self.effect_verifier.verify(
                page,
                expected=action.expected_effect,
                url_before=action_result.url_before,
                body_text_before=body_text_before,
                timeout_ms=1200,
            )
            metadata_attempts.append(
                {
                    "kind": "wait_and_reobserve",
                    "attempt": attempt,
                    "readiness": readiness.model_dump(mode="json"),
                    "verification": result.model_dump(mode="json"),
                }
            )
            if result.satisfied:
                return result

        error_type = "ACTION_NO_EFFECT_AFTER_TRANSITION"
        if not initial_readiness.signals.get("text_stable", True):
            error_type = "POSTCONDITION_STILL_PENDING"
        return result.model_copy(
            update={
                "error_type": error_type,
                "message": result.message or "Expected effect was still pending after transition waits.",
            }
        )

    def _next_step_id(self) -> str:
        self._step_index += 1
        return f"step_{self._step_index:03d}"

    def _record_simple_trace(
        self,
        action_type: str,
        output: dict[str, Any],
        status: str,
    ) -> None:
        step_id = self._next_step_id()
        observation = self.last_observation
        self.trace_recorder.record(
            TraceStep(
                step_id=step_id,
                run_id=self.trace_recorder.run_id,
                phase="browser_tool_runtime",
                actor="tool",
                action_type=action_type,
                status=status,
                url_after=observation.url if observation else None,
                title=observation.title if observation else None,
                observation=output,
                error_type=output.get("error_type"),
                error_message=output.get("error_message"),
            )
        )


def _elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def _blocked_policy_observation(url: str, decision) -> PageObservation:
    return PageObservation(
        url=url,
        title="Blocked by public web policy",
        visible_text_summary=decision.reason,
        interactive_elements=[],
        risk_signals=[
            RiskSignal(
                risk_type="public_web_policy",
                message=decision.reason,
                severity="high",
            )
        ],
        metadata={"public_web_policy": decision.model_dump(mode="json")},
    )


def _failed_output(error_type: str, error_message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "error_type": error_type,
        "error_message": error_message,
    }


def _observation_extract(observation: PageObservation) -> dict[str, Any]:
    return {
        "status": "success",
        "url": observation.url,
        "title": observation.title,
        "visible_text_summary": observation.visible_text_summary,
        "interactive_elements_count": len(observation.interactive_elements),
        "risk_signals_count": len(observation.risk_signals),
    }


def _readiness_error_type(readiness: ReadinessResult) -> str | None:
    if readiness.status == "ready":
        return None
    signals = readiness.signals
    if not signals.get("overlay_absent", True):
        return "OVERLAY_BLOCKING_ACTION"
    if not signals.get("spinner_absent", True):
        return "PAGE_STILL_LOADING"
    if not signals.get("skeleton_absent", True):
        return "TARGET_HYDRATING"
    if not signals.get("target_visible", True):
        return "TARGET_NOT_READY"
    if not signals.get("target_enabled", True):
        return "TARGET_DISABLED_PENDING_HYDRATION"
    if not signals.get("text_stable", True):
        return "CONTENT_STABILITY_TIMEOUT"
    if not signals.get("soft_network_quiet", True):
        return "NETWORK_QUIET_TIMEOUT"
    if readiness.status == "timeout":
        return "PAGE_LOADING_TIMEOUT"
    if readiness.status == "loading":
        return "PAGE_STILL_LOADING"
    return None


async def _body_text(page: Page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=1000)
    except Exception:
        return ""


async def _safe_title(page: Page) -> str:
    try:
        return await page.title()
    except Exception:
        return ""
