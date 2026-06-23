from __future__ import annotations

import asyncio
import hashlib
import json
from time import perf_counter
from typing import Any
from uuid import uuid4

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
        self.browser_session_id = f"bs_{self.trace_recorder.run_id}"
        self.browser_context_id = f"bc_{self.trace_recorder.run_id}"
        self.page_id = f"page_{uuid4().hex[:10]}"
        self._scroll_count = 0
        self._max_scrolls_per_task = 12

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

    async def open(
        self,
        url: str,
        *,
        session_id: str | None = None,
        wait_until: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        step_id = self._next_step_id()
        screenshot_path = self.trace_recorder.run_dir / f"{step_id}_browser_open.png"
        start = perf_counter()
        policy_decision = self.public_web_policy.check(
            url,
            pages_opened=self._public_pages_opened,
        )
        if not policy_decision.allow:
            observation = _blocked_policy_observation(url, policy_decision)
            self.last_observation = observation
            self.trace_recorder.record(
                TraceStep(
                    step_id=step_id,
                    run_id=self.trace_recorder.run_id,
                    phase="browser_tool_runtime",
                    actor="tool",
                    action_type="browser_open",
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
            self._emit_public_web_block(policy_decision, tool_name="browser_open")
            raise PublicWebPolicyError(policy_decision, observation)

        if policy_decision.url_classification == "public_http":
            self._public_pages_opened += 1
            if self.public_web_config.request_delay_ms > 0:
                await asyncio.sleep(self.public_web_config.request_delay_ms / 1000)

        self._emit_executor_started(step_id, "browser_open", {"url": url, "reason": reason})
        self._emit(
            "browser_open_started",
            "Browser open started",
            {
                "span_id": step_id,
                "step_id": step_id,
                "tool_name": "browser_open",
                "url": url,
                "session": self._session_payload(session_id),
            },
        )
        try:
            if self.page is None:
                await self.start()
            page = self._require_page()
            url_before = page.url
            title_before = await _safe_title(page)
            self._emit(
                "navigation_started",
                "Navigation started",
                {
                    "span_id": step_id,
                    "step_id": step_id,
                    "url_before": url_before,
                    "url_after": url,
                    "navigation_timeout_ms": self.public_web_config.navigation_timeout_ms,
                },
            )
            await page.goto(
                url,
                wait_until=_wait_until(wait_until),
                timeout=self.public_web_config.navigation_timeout_ms,
            )
            title_after = await _safe_title(page)
            screenshot_evidence = None
            try:
                await page.screenshot(path=str(screenshot_path), full_page=True)
                screenshot_evidence = self._add_screenshot_evidence(
                    kind="page_screenshot",
                    screenshot_path=str(screenshot_path),
                    step_id=step_id,
                    tool_name="browser_open",
                    source_url=page.url,
                    page_title=title_after,
                    metadata={"reason": reason},
                )
            except Exception:
                pass
            timing = await _navigation_timing(page, start)
            output = {
                "url": url,
                "final_url": page.url,
                "title": title_after,
                "status": "success",
                "navigation_timing": timing,
                "screenshot_evidence_id": screenshot_evidence.evidence_id
                if screenshot_evidence is not None
                else None,
                "observation_id": None,
                "browser_session_id": self.browser_session_id,
                "browser_context_id": self.browser_context_id,
                "page_id": self.page_id,
            }
            self.trace_recorder.record(
                TraceStep(
                    step_id=step_id,
                    run_id=self.trace_recorder.run_id,
                    phase="browser_tool_runtime",
                    actor="tool",
                    action_type="browser_open",
                    status="success",
                    url_before=url_before,
                    url_after=page.url,
                    title=title_after,
                    observation={
                        **output,
                        "title_before": title_before,
                        "screenshot_path": str(screenshot_path)
                        if screenshot_path.exists()
                        else None,
                    },
                    screenshot_path=str(screenshot_path) if screenshot_path.exists() else None,
                    latency_ms=_elapsed_ms(start),
                )
            )
            if page.url != url_before:
                self._emit(
                    "url_changed",
                    "Browser URL changed",
                    {"span_id": step_id, "step_id": step_id, "url_before": url_before, "url_after": page.url},
                )
            self._emit(
                "navigation_finished",
                "Navigation finished",
                {
                    "span_id": step_id,
                    "step_id": step_id,
                    "url_before": url_before,
                    "url_after": page.url,
                    "duration_ms": _elapsed_ms(start),
                    "navigation_timing": timing,
                },
            )
            self._emit(
                "browser_open_finished",
                "Browser open finished",
                {
                    "span_id": step_id,
                    "step_id": step_id,
                    "tool_name": "browser_open",
                    "status": "success",
                    **output,
                    "duration_ms": _elapsed_ms(start),
                },
            )
            self._emit_executor_finished(step_id, "browser_open", output)
            return output
        except Exception as exc:
            payload = {
                "span_id": step_id,
                "step_id": step_id,
                "tool_name": "browser_open",
                "status": "failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "duration_ms": _elapsed_ms(start),
            }
            self._emit("browser_open_finished", "Browser open failed", payload)
            self._emit_executor_finished(step_id, "browser_open", payload)
            raise

    async def observe(
        self,
        *,
        session_id: str | None = None,
        include_screenshot: bool = True,
        include_accessibility: bool = True,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if self.page is None:
            return _failed_output("PAGE_NOT_OPENED", "Open a page before observing.")
        step_id = self._next_step_id()
        start = perf_counter()
        page = self.page
        screenshot_path = (
            self.trace_recorder.run_dir / f"{step_id}_browser_observe.png"
            if include_screenshot
            else None
        )
        readiness = await self.readiness_detector.wait_for_readiness(page, timeout_ms=1000)
        observation = await observe_page(
            page,
            screenshot_path=screenshot_path,
            include_accessibility=include_accessibility,
        )
        observation.readiness = readiness.model_dump(mode="json")
        observation.metadata["readiness"] = observation.readiness
        observation.metadata["session"] = self._session_payload(session_id)
        screenshot_evidence = None
        if observation.screenshot_path:
            screenshot_evidence = self._add_screenshot_evidence(
                kind="page_screenshot",
                screenshot_path=observation.screenshot_path,
                step_id=step_id,
                tool_name="browser_observe",
                source_url=observation.url,
                page_title=observation.title,
                observation_id=observation.observation_id,
                metadata={"reason": reason, "readiness": observation.readiness},
            )
            if screenshot_evidence is not None:
                observation.screenshot_evidence_id = screenshot_evidence.evidence_id
                observation.metadata["screenshot_evidence_id"] = screenshot_evidence.evidence_id
        self.last_observation = observation
        output = observation.model_dump(mode="json")
        output["status"] = "success"
        self._write_observation_artifact(output)
        self.trace_recorder.record(
            TraceStep(
                step_id=step_id,
                run_id=self.trace_recorder.run_id,
                phase="browser_tool_runtime",
                actor="tool",
                action_type="browser_observe",
                status="success",
                url_after=observation.url,
                title=observation.title,
                observation=output,
                screenshot_path=observation.screenshot_path,
                latency_ms=_elapsed_ms(start),
            )
        )
        self._emit(
            "browser_observe_finished",
            "Browser observe finished",
            {
                "span_id": step_id,
                "step_id": step_id,
                "tool_name": "browser_observe",
                "status": "success",
                "observation_id": observation.observation_id,
                "screenshot_evidence_id": observation.screenshot_evidence_id,
                "duration_ms": _elapsed_ms(start),
                "session": self._session_payload(session_id),
            },
        )
        return output

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
            self._emit(
                "browser_open_started",
                "Browser open started",
                {
                    "step_id": step_id,
                    "tool_name": "browser_open_observe",
                    "url": url,
                    "navigation_timeout_ms": self.public_web_config.navigation_timeout_ms,
                },
            )
            self._emit(
                "navigation_started",
                "Navigation started",
                {
                    "step_id": step_id,
                    "url_before": page.url,
                    "url_after": url,
                    "navigation_timeout_ms": self.public_web_config.navigation_timeout_ms,
                },
            )
            url_before = page.url
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.public_web_config.navigation_timeout_ms,
            )
            if page.url != url_before:
                self._emit(
                    "url_changed",
                    "Browser URL changed",
                    {
                        "step_id": step_id,
                        "url_before": url_before,
                        "url_after": page.url,
                    },
                )
            self._emit(
                "navigation_finished",
                "Navigation finished",
                {
                    "step_id": step_id,
                    "url_before": url_before,
                    "url_after": page.url,
                    "elapsed_ms": _elapsed_ms(start),
                },
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
            observation.readiness = readiness.model_dump(mode="json")
            observation.metadata["public_web_policy"] = policy_decision.model_dump(
                mode="json"
            )
            screenshot_evidence = self._add_screenshot_evidence(
                kind="page_screenshot",
                screenshot_path=str(screenshot_path),
                step_id=step_id,
                tool_name="browser_open_observe",
                source_url=observation.url,
                page_title=observation.title,
                observation_id=observation.observation_id,
                metadata={"readiness": readiness.model_dump(mode="json")},
            )
            if screenshot_evidence is not None:
                observation.screenshot_evidence_id = screenshot_evidence.evidence_id
                observation.metadata["screenshot_evidence_id"] = screenshot_evidence.evidence_id
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
            self._emit(
                "browser_open_finished",
                "Browser open finished",
                {
                    "step_id": step_id,
                    "tool_name": "browser_open_observe",
                    "status": "success",
                    "url_after": observation.url,
                    "title_after": observation.title,
                    "screenshot_path": str(screenshot_path),
                    "screenshot_evidence_id": observation.screenshot_evidence_id,
                    "duration_ms": _elapsed_ms(start),
                    "readiness": readiness.model_dump(mode="json"),
                },
            )
            return observation
        except Exception as exc:
            self._emit(
                "navigation_timeout"
                if type(exc).__name__ in {"TimeoutError", "PlaywrightTimeoutError"}
                else "browser_open_finished",
                "Browser open failed",
                {
                    "step_id": step_id,
                    "tool_name": "browser_open_observe",
                    "status": "failed",
                    "url_after": page_url,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "duration_ms": _elapsed_ms(start),
                },
            )
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

    def _emit_public_web_block(
        self,
        decision,
        *,
        tool_name: str = "browser_open_observe",
    ) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(
                "risk_blocked",
                "Public web URL blocked",
                {
                    "run_id": self.trace_recorder.run_id,
                    "tool_name": tool_name,
                    "error_type": "PUBLIC_WEB_BLOCKED",
                    "error_message": decision.reason,
                    "public_web_policy": decision.model_dump(mode="json"),
                },
            )
        except Exception:
            return

    async def click_intent(
        self,
        action: ActionContract,
        *,
        tool_name: str = "browser_click_intent",
    ) -> dict[str, Any]:
        if self.page is None:
            return _failed_output("PAGE_NOT_OPENED", "Open a page before clicking.")

        page = self.page
        before_step_id = self._next_step_id()
        before_screenshot_path = (
            self.trace_recorder.run_dir / f"{before_step_id}_before_click.png"
        )
        before_title = await _safe_title(page)
        before_url = page.url
        try:
            await page.screenshot(path=str(before_screenshot_path), full_page=True)
            self._add_screenshot_evidence(
                kind="before_action_screenshot",
                screenshot_path=str(before_screenshot_path),
                step_id=before_step_id,
                tool_name=tool_name,
                source_url=before_url,
                page_title=before_title,
                metadata={"target_hint": action.target_hint},
            )
        except Exception:
            pass
        body_text_before = await _body_text(page)
        action_step_id = self._next_step_id()
        action_start = perf_counter()
        self._emit(
            "action_precondition_checked",
            "Action precondition checked",
            {
                "step_id": action_step_id,
                "tool_name": tool_name,
                "action_type": action.action_type,
                "target_hint": action.target_hint,
                "preconditions": action.preconditions,
            },
        )
        self._emit(
            "action_started",
            "Browser action started",
            {
                "step_id": action_step_id,
                "tool_name": tool_name,
                "action_type": action.action_type,
                "target_hint": action.target_hint,
                "expected_effect": action.expected_effect.model_dump(mode="json"),
                "url_before": before_url,
                "screenshot_before": str(before_screenshot_path),
            },
        )
        action_result = await self.action_executor.click(page, action)
        self._emit(
            "action_finished",
            "Browser action finished",
            {
                "step_id": action_step_id,
                "tool_name": tool_name,
                "action_type": action.action_type,
                "target_hint": action.target_hint,
                "status": action_result.status,
                "url_before": action_result.url_before,
                "url_after": action_result.url_after,
                "error_type": action_result.error_type,
                "error_message": action_result.error_message,
                "duration_ms": _elapsed_ms(action_start),
            },
        )
        self.trace_recorder.record(
            TraceStep(
                step_id=action_step_id,
                run_id=self.trace_recorder.run_id,
                phase="browser_tool_runtime",
                actor="tool",
                action_type=tool_name,
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
        self._emit(
            "effect_verification_started",
            "Effect verification started",
            {
                "step_id": verify_step_id,
                "tool_name": tool_name,
                "expected_effect": action.expected_effect.model_dump(mode="json"),
                "url_before": action_result.url_before,
                "title_before": before_title,
                "screenshot_before": str(before_screenshot_path),
            },
        )
        self._emit(
            "verifier_started",
            "Verifier started",
            {
                "span_id": verify_step_id,
                "parent_span_id": action_step_id,
                "step_id": verify_step_id,
                "tool_name": tool_name,
                "expected_effect": action.expected_effect.model_dump(mode="json"),
            },
        )
        verification_result = await self._verify_after_transition(
            page=page,
            action=action,
            action_result=action_result,
            body_text_before=body_text_before,
            initial_readiness=transition_readiness,
        )
        self._emit(
            "effect_verification_finished",
            "Effect verification finished",
            {
                "step_id": verify_step_id,
                "tool_name": tool_name,
                "expected_effect": action.expected_effect.model_dump(mode="json"),
                "url_before": verification_result.url_before,
                "url_after": verification_result.url_after,
                "title_before": before_title,
                "title_after": await _safe_title(page),
                "text_changed": body_text_before != await _body_text(page),
                "screenshot_before": str(before_screenshot_path),
                "satisfied": verification_result.satisfied,
                "status": verification_result.status,
                "error_type": verification_result.error_type,
                "message": verification_result.message,
                "duration_ms": _elapsed_ms(verify_start),
            },
        )
        self._emit(
            "verifier_finished",
            "Verifier finished",
            {
                "span_id": verify_step_id,
                "parent_span_id": action_step_id,
                "step_id": verify_step_id,
                "tool_name": tool_name,
                "status": verification_result.status,
                "satisfied": verification_result.satisfied,
                "error_type": verification_result.error_type,
                "message": verification_result.message,
                "duration_ms": _elapsed_ms(verify_start),
            },
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
        observation.readiness = observation.metadata["readiness"]
        after_screenshot_evidence = self._add_screenshot_evidence(
            kind="after_action_screenshot",
            screenshot_path=str(screenshot_path),
            step_id=observe_step_id,
            tool_name=tool_name,
            source_url=observation.url,
            page_title=observation.title,
            observation_id=observation.observation_id,
            metadata={
                "target_hint": action.target_hint,
                "action_step_id": action_step_id,
                "verification_step_id": verify_step_id,
                "satisfied": verification_result.satisfied,
            },
        )
        if after_screenshot_evidence is not None:
            observation.screenshot_evidence_id = after_screenshot_evidence.evidence_id
            observation.metadata["screenshot_evidence_id"] = (
                after_screenshot_evidence.evidence_id
            )
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
        if status != "success":
            self._add_screenshot_evidence(
                kind="failure_screenshot",
                screenshot_path=str(screenshot_path),
                step_id=observe_step_id,
                tool_name=tool_name,
                source_url=observation.url,
                page_title=observation.title,
                observation_id=observation.observation_id,
                metadata={
                    "target_hint": action.target_hint,
                    "error_type": action_result.error_type
                    or verification_result.error_type,
                    "verification": verification_result.model_dump(mode="json"),
                },
            )
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

    async def click(
        self,
        *,
        target_hint: str,
        expected_effect: dict[str, Any] | None = None,
        session_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        self._emit(
            "planner_action_selected",
            "Planner action selected",
            {
                "action_type": "browser_click",
                "target_hint": target_hint,
                "reason": reason,
                "session": self._session_payload(session_id),
            },
        )
        action = ActionContract(
            action_type="click",
            intent=f"Click {target_hint}",
            target_hint=target_hint,
            preferred_roles=["button", "link", "tab"],
            preconditions=["target_visible", "target_enabled"],
            expected_effect=expected_effect or {"type": "none"},
            risk_level="read_only",
        )
        output = await self.click_intent(action, tool_name="browser_click")
        action_result = output.get("action_result") if isinstance(output, dict) else {}
        verification = (
            output.get("verification_result") if isinstance(output, dict) else {}
        )
        observation = output.get("observation") if isinstance(output, dict) else {}
        selected_target = None
        if isinstance(action_result, dict):
            target = action_result.get("target")
            if isinstance(target, dict):
                selected_target = target.get("selected")
        return {
            **output,
            "selected_target": selected_target,
            "title_before": None,
            "title_after": observation.get("title") if isinstance(observation, dict) else None,
            "effect_verification": verification,
            "before_screenshot_evidence_id": None,
            "after_screenshot_evidence_id": observation.get("screenshot_evidence_id")
            if isinstance(observation, dict)
            else None,
            "browser_session_id": self.browser_session_id,
            "browser_context_id": self.browser_context_id,
            "page_id": self.page_id,
        }

    async def type_text(
        self,
        *,
        target_hint: str,
        text: str,
        session_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if self.page is None:
            return _failed_output("PAGE_NOT_OPENED", "Open a page before typing.")
        safety = _input_safety_decision(target_hint, text, self.page.url)
        if safety["decision"] != "allow":
            return {
                "status": "blocked",
                "error_type": "SENSITIVE_INPUT_BLOCKED",
                "error_message": safety["reason"],
                "selected_target": None,
                "safety_decision": safety,
                "evidence_ids": [],
            }
        step_id = self._next_step_id()
        start = perf_counter()
        page = self.page
        before = await self._page_diff_snapshot(page)
        resolved = await self.action_executor.target_resolver.resolve(
            page,
            target_hint=target_hint,
            preferred_roles=["textbox", "combobox"],
        )
        if resolved.selected is None:
            return {
                "status": "failed",
                "error_type": resolved.error_type or "TARGET_NOT_FOUND",
                "error_message": resolved.error_message,
                "selected_target": None,
                "safety_decision": safety,
                "evidence_ids": [],
            }
        locator = await self.action_executor.target_resolver.locator_for(page, resolved.selected)
        await locator.fill(text, timeout=1500)
        after = await self._page_diff_snapshot(page)
        evidence = self._add_text_evidence(
            kind="action_result",
            step_id=step_id,
            tool_name="browser_type",
            text=f"Typed safe text into {target_hint}.",
            source_url=page.url,
            page_title=await _safe_title(page),
            metadata={"target_hint": target_hint, "diff": _diff_metadata(before, after)},
        )
        output = {
            "selected_target": resolved.selected.model_dump(mode="json"),
            "status": "success",
            "safety_decision": safety,
            "evidence_ids": [evidence.evidence_id] if evidence is not None else [],
            "diff": _diff_metadata(before, after),
        }
        self.trace_recorder.record(
            TraceStep(
                step_id=step_id,
                run_id=self.trace_recorder.run_id,
                phase="browser_tool_runtime",
                actor="tool",
                action_type="browser_type",
                status="success",
                url_before=before["url"],
                url_after=after["url"],
                title=after["title"],
                observation=output,
                latency_ms=_elapsed_ms(start),
            )
        )
        return output

    async def select_option(
        self,
        *,
        target_hint: str,
        option_text: str | None = None,
        option_value: str | None = None,
        session_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if self.page is None:
            return _failed_output("PAGE_NOT_OPENED", "Open a page before selecting.")
        if not option_text and not option_value:
            return _failed_output("OPTION_REQUIRED", "browser_select requires option_text or option_value.")
        safety = {
            "decision": "allow" if self.page.url.startswith("file://") else "ask_human",
            "reason": "Local fixture select is allowed."
            if self.page.url.startswith("file://")
            else "Public web select requires human approval by default.",
        }
        if safety["decision"] != "allow":
            return {
                "status": "blocked",
                "error_type": "PUBLIC_SELECT_BLOCKED",
                "error_message": safety["reason"],
                "selected_target": None,
                "selected_option": None,
                "safety_decision": safety,
                "evidence_ids": [],
            }
        step_id = self._next_step_id()
        page = self.page
        before = await self._page_diff_snapshot(page)
        resolved = await self.action_executor.target_resolver.resolve(
            page,
            target_hint=target_hint,
            preferred_roles=["combobox", "listbox"],
        )
        if resolved.selected is None:
            return _failed_output(resolved.error_type or "TARGET_NOT_FOUND", resolved.error_message or "Select target not found.")
        locator = await self.action_executor.target_resolver.locator_for(page, resolved.selected)
        selected_values = await locator.select_option(
            label=option_text if option_text else None,
            value=option_value if option_value else None,
            timeout=1500,
        )
        after = await self._page_diff_snapshot(page)
        evidence = self._add_text_evidence(
            kind="action_result",
            step_id=step_id,
            tool_name="browser_select",
            text=f"Selected {option_text or option_value} in {target_hint}.",
            source_url=page.url,
            page_title=await _safe_title(page),
            metadata={"target_hint": target_hint, "selected_values": selected_values, "diff": _diff_metadata(before, after)},
        )
        return {
            "selected_target": resolved.selected.model_dump(mode="json"),
            "selected_option": {"text": option_text, "value": option_value, "selected_values": selected_values},
            "status": "success",
            "safety_decision": safety,
            "evidence_ids": [evidence.evidence_id] if evidence is not None else [],
            "diff": _diff_metadata(before, after),
        }

    async def scroll(
        self,
        *,
        direction: str,
        amount: str,
        session_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if self.page is None:
            return _failed_output("PAGE_NOT_OPENED", "Open a page before scrolling.")
        if self._scroll_count >= self._max_scrolls_per_task:
            return _failed_output("MAX_SCROLLS_EXCEEDED", "Maximum scroll count exceeded.")
        self._scroll_count += 1
        page = self.page
        before = await _scroll_position(page)
        pixels = {"small": 320, "medium": 720, "large": 1400}.get(amount, 720)
        if direction == "up":
            pixels *= -1
        await page.mouse.wheel(0, pixels)
        await page.wait_for_timeout(150)
        after = await _scroll_position(page)
        observation = await self.observe(
            session_id=session_id,
            include_screenshot=True,
            include_accessibility=True,
            reason=reason or f"Scrolled {direction} {amount}.",
        )
        return {
            "scroll_position_before": before,
            "scroll_position_after": after,
            "observation_id": observation.get("observation_id"),
            "screenshot_evidence_id": observation.get("screenshot_evidence_id"),
            "status": "success",
        }

    async def wait(
        self,
        *,
        condition: str,
        value: str | None = None,
        timeout_ms: int | None = None,
        session_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if self.page is None:
            return _failed_output("PAGE_NOT_OPENED", "Open a page before waiting.")
        page = self.page
        start = perf_counter()
        timeout = timeout_ms or 3500
        if condition == "fixed_delay":
            await page.wait_for_timeout(min(timeout, 3000))
        elif condition == "url_changes":
            initial_url = page.url
            try:
                await page.wait_for_function(
                    "initial => location.href !== initial",
                    initial_url,
                    timeout=timeout,
                )
            except Exception:
                pass
        elif condition == "content_appears" and value:
            try:
                await page.get_by_text(value).first.wait_for(timeout=timeout)
            except Exception:
                pass
        readiness = await self._wait_and_record_readiness(
            page,
            action_type="browser_wait",
            url_before=None,
            target_hint=None,
            timeout_ms=timeout,
        )
        observation_id = None
        if condition in {"readiness", "content_appears", "network_quiet"}:
            observation = await self.observe(
                session_id=session_id,
                include_screenshot=False,
                include_accessibility=True,
                reason=reason,
            )
            observation_id = observation.get("observation_id")
        return {
            "status": "success" if readiness.status != "timeout" else "timeout",
            "elapsed_ms": _elapsed_ms(start),
            "readiness": readiness.model_dump(mode="json"),
            "warnings": readiness.warnings,
            "observation_id": observation_id,
        }

    async def screenshot(
        self,
        *,
        session_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if self.page is None:
            return _failed_output("PAGE_NOT_OPENED", "Open a page before screenshot.")
        step_id = self._next_step_id()
        page = self.page
        title = await _safe_title(page)
        screenshot_path = self.trace_recorder.run_dir / f"{step_id}_browser_screenshot.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        evidence = self._add_screenshot_evidence(
            kind="page_screenshot",
            screenshot_path=str(screenshot_path),
            step_id=step_id,
            tool_name="browser_screenshot",
            source_url=page.url,
            page_title=title,
            metadata={"reason": reason, "session": self._session_payload(session_id)},
        )
        return {
            "screenshot_path": str(screenshot_path),
            "screenshot_evidence_id": evidence.evidence_id if evidence else None,
            "url": page.url,
            "title": title,
            "status": "success",
        }

    async def extract(
        self,
        instruction: str | None = None,
        evidence_mode: str | None = None,
    ) -> dict[str, Any]:
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
            output["extracted_summary"] = output.get("visible_text_summary")
            output["source_url"] = output.get("url")
            output["evidence_ids"] = []
            output["structured_data"] = None
            output["instruction"] = instruction
            evidence = self._add_text_evidence(
                kind="text_excerpt",
                step_id=step_id,
                tool_name="browser_extract",
                text=str(output.get("visible_text_summary") or ""),
                source_url=observation.url,
                page_title=observation.title,
                metadata={
                    "instruction": instruction,
                    "evidence_mode": evidence_mode,
                    "observation_id": observation.observation_id,
                },
            )
            if evidence is not None:
                output["evidence_ids"] = [evidence.evidence_id]
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
            "summary_instruction": summary,
            "final_url": observation.url if observation else None,
            "final_title": observation.title if observation else None,
            "final_report_path": str(self.trace_recorder.run_dir / "final_report.md"),
            "evidence_ids": [
                item.evidence_id for item in self.evidence_store.list_items()
            ]
            if self.evidence_store is not None
            else [],
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
        self._emit(
            "readiness_wait_started",
            "Waiting for page readiness",
            {
                "action_type": action_type,
                "url_before": url_before,
                "target_hint": target_hint,
                "timeout_ms": timeout_ms,
            },
        )
        self._emit(
            "post_action_wait_started",
            "Post action wait started",
            {
                "action_type": action_type,
                "url_before": url_before,
                "target_hint": target_hint,
                "timeout_ms": timeout_ms,
            },
        )
        readiness = await wait_after_navigation_or_action(
            page,
            target_hint=target_hint,
            timeout_ms=timeout_ms,
        )
        readiness_payload = _readiness_event_payload(readiness)
        self._emit(
            "readiness_sampled",
            "Readiness signals sampled",
            {
                **readiness_payload,
                "action_type": action_type,
                "url_after": page.url,
                "target_hint": target_hint,
            },
        )
        finished_kind = (
            "readiness_timeout" if readiness.status == "timeout" else "readiness_wait_finished"
        )
        self._emit(
            finished_kind,
            "Readiness wait finished",
            {
                **readiness_payload,
                "action_type": action_type,
                "status": readiness.status,
                "url_after": page.url,
                "target_hint": target_hint,
                "duration_ms": _elapsed_ms(start),
            },
        )
        self._emit(
            "post_action_wait_finished",
            "Post action wait finished",
            {
                "action_type": action_type,
                "status": readiness.status,
                "url_after": page.url,
                "target_hint": target_hint,
                "duration_ms": _elapsed_ms(start),
            },
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
        self._emit(
            "readiness_check",
            "Browser readiness checked",
            {
                "status": readiness.status,
                "confidence": readiness.confidence,
                "warnings": readiness.warnings,
                "signals": readiness.signals,
            },
        )
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

    async def _page_diff_snapshot(self, page: Page) -> dict[str, Any]:
        observation = await observe_page(page, include_accessibility=False)
        return {
            "url": observation.url,
            "title": observation.title,
            "visible_text_hash": _hash_text(observation.visible_text_summary),
            "interactive_elements_count": len(observation.interactive_elements),
            "main_content_summary": observation.main_content_summary,
        }

    def _write_observation_artifact(self, observation: dict[str, Any]) -> None:
        path = self.trace_recorder.run_dir / "observation.json"
        try:
            path.write_text(
                json.dumps(observation, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except Exception:
            return

    def _add_text_evidence(
        self,
        *,
        kind: str,
        step_id: str,
        tool_name: str,
        text: str,
        source_url: str | None,
        page_title: str | None,
        metadata: dict[str, Any] | None = None,
    ):
        if self.evidence_store is None:
            return None
        item = self.evidence_store.add_item(
            kind=kind,
            source_url=source_url,
            page_title=page_title,
            text=text,
            step_id=step_id,
            tool_name=tool_name,
            trace_event_id=step_id,
            metadata=metadata or {},
        )
        self._emit(
            "text_evidence_added",
            f"Text evidence added: {item.evidence_id}",
            {
                "evidence_id": item.evidence_id,
                "kind": item.kind,
                "step_id": step_id,
                "tool_name": tool_name,
                "source_url": source_url,
            },
        )
        self._emit(
            "evidence_added",
            f"Evidence added: {item.evidence_id}",
            {
                "evidence_id": item.evidence_id,
                "kind": item.kind,
                "step_id": step_id,
                "tool_name": tool_name,
            },
        )
        return item

    def _session_payload(self, session_id: str | None = None) -> dict[str, Any]:
        return {
            "browser_session_id": session_id or self.browser_session_id,
            "browser_context_id": self.browser_context_id,
            "page_id": self.page_id,
            "scope": "task",
            "persist_storage_state": False,
        }

    def _emit_executor_started(
        self,
        span_id: str,
        tool_name: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._emit(
            "executor_started",
            "Executor started",
            {
                "span_id": span_id,
                "tool_name": tool_name,
                "session": self._session_payload(),
                **(payload or {}),
            },
        )

    def _emit_executor_finished(
        self,
        span_id: str,
        tool_name: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._emit(
            "executor_finished",
            "Executor finished",
            {
                "span_id": span_id,
                "tool_name": tool_name,
                "session": self._session_payload(),
                **(payload or {}),
            },
        )

    def _add_screenshot_evidence(
        self,
        *,
        kind: str,
        screenshot_path: str,
        step_id: str,
        tool_name: str,
        source_url: str | None,
        page_title: str | None,
        observation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        if self.evidence_store is None:
            return None
        item = self.evidence_store.add_item(
            kind=kind,
            source_url=source_url,
            page_title=page_title,
            screenshot_path=screenshot_path,
            step_id=step_id,
            tool_name=tool_name,
            observation_id=observation_id,
            trace_event_id=step_id,
            metadata=metadata or {},
        )
        self._emit(
            "screenshot_evidence_added",
            f"Screenshot evidence added: {item.evidence_id}",
            {
                "evidence_id": item.evidence_id,
                "kind": item.kind,
                "step_id": step_id,
                "tool_name": tool_name,
                "source_url": source_url,
                "screenshot_path": screenshot_path,
                "observation_id": observation_id,
            },
        )
        self._emit(
            "evidence_added",
            f"Evidence added: {item.evidence_id}",
            {
                "evidence_id": item.evidence_id,
                "kind": item.kind,
                "step_id": step_id,
                "tool_name": tool_name,
            },
        )
        return item

    def _emit(
        self,
        kind: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(
                kind,
                message,
                {"run_id": self.trace_recorder.run_id, **(payload or {})},
            )
        except Exception:
            return


def _elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def _wait_until(value: str | None) -> str:
    if value in {"load", "domcontentloaded", "networkidle", "commit"}:
        return value
    return "domcontentloaded"


async def _navigation_timing(page: Page, start: float) -> dict[str, Any]:
    try:
        timing = await page.evaluate(
            """() => {
                const nav = performance.getEntriesByType('navigation')[0];
                if (!nav) return {};
                return {
                    requestStart: Math.round(nav.requestStart || 0),
                    responseStart: Math.round(nav.responseStart || 0),
                    domContentLoadedEventEnd: Math.round(nav.domContentLoadedEventEnd || 0),
                    loadEventEnd: Math.round(nav.loadEventEnd || 0),
                    duration: Math.round(nav.duration || 0)
                };
            }"""
        )
        return timing if isinstance(timing, dict) else {}
    except Exception:
        return {"elapsed_ms": _elapsed_ms(start)}


async def _scroll_position(page: Page) -> dict[str, int]:
    try:
        value = await page.evaluate(
            """() => ({
                x: Math.round(window.scrollX || 0),
                y: Math.round(window.scrollY || 0),
                height: Math.round(document.documentElement.scrollHeight || 0),
                viewport_height: Math.round(window.innerHeight || 0)
            })"""
        )
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _hash_text(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _diff_metadata(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        "url_before": before.get("url"),
        "url_after": after.get("url"),
        "title_before": before.get("title"),
        "title_after": after.get("title"),
        "visible_text_hash_before": before.get("visible_text_hash"),
        "visible_text_hash_after": after.get("visible_text_hash"),
        "text_changed": before.get("visible_text_hash") != after.get("visible_text_hash"),
        "interactive_elements_count_before": before.get("interactive_elements_count"),
        "interactive_elements_count_after": after.get("interactive_elements_count"),
        "main_content_summary_before": before.get("main_content_summary"),
        "main_content_summary_after": after.get("main_content_summary"),
    }


def _input_safety_decision(
    target_hint: str,
    text: str,
    url: str,
) -> dict[str, Any]:
    combined = f"{target_hint} {text}".lower()
    sensitive_terms = [
        "password",
        "token",
        "api key",
        "secret",
        "credit card",
        "ssn",
        "身份证",
        "密码",
        "验证码",
    ]
    if any(term in combined for term in sensitive_terms):
        return {"decision": "block", "reason": "Sensitive input is blocked."}
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 11:
        return {"decision": "block", "reason": "Phone/card-like numeric input is blocked."}
    if "@" in text and "." in text:
        return {"decision": "block", "reason": "Real email-like input is blocked."}
    if not url.startswith("file://"):
        return {"decision": "block", "reason": "Typing on public web is disabled by default."}
    return {"decision": "allow", "reason": "Safe local fixture input is allowed."}


def _readiness_event_payload(readiness: ReadinessResult) -> dict[str, Any]:
    signals = readiness.signals
    payload = {name: bool(signals.get(name, False)) for name in _READINESS_SIGNAL_KEYS}
    payload.update(
        {
            "status": readiness.status,
            "confidence": readiness.confidence,
            "elapsed_ms": readiness.elapsed_ms,
            "warnings": readiness.warnings,
            "metadata": readiness.metadata,
            "sample_count": readiness.metadata.get("sample_count"),
            "final_ready_state": readiness.metadata.get("ready_state"),
        }
    )
    return payload


_READINESS_SIGNAL_KEYS = [
    "dom_complete",
    "url_stable",
    "title_stable",
    "text_stable",
    "interactive_elements_stable",
    "spinner_absent",
    "skeleton_absent",
    "overlay_absent",
    "layout_stable",
    "soft_network_quiet",
    "target_visible",
    "target_enabled",
    "target_stable",
]


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
