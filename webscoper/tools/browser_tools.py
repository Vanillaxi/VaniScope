from __future__ import annotations

from time import perf_counter
from typing import Any

from playwright.async_api import Page

from webscoper.browser.actions import ActionExecutor
from webscoper.browser.effects import EffectVerifier
from webscoper.browser.observer import observe_page
from webscoper.browser.session import BrowserSession
from webscoper.runtime.trace import TraceRecorder
from webscoper.schemas.action import ActionContract
from webscoper.schemas.observation import PageObservation
from webscoper.schemas.trace import TraceStep


class StatefulBrowserToolRuntime:
    def __init__(
        self,
        trace_recorder: TraceRecorder,
        headless: bool = True,
    ) -> None:
        self.trace_recorder = trace_recorder
        self.headless = headless
        self.session: BrowserSession | None = None
        self.page: Page | None = None
        self.last_observation: PageObservation | None = None
        self.action_executor = ActionExecutor()
        self.effect_verifier = EffectVerifier()
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

        try:
            page = self._require_page()
            await page.goto(url, wait_until="domcontentloaded")
            observation = await observe_page(page, screenshot_path=screenshot_path)
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

        verify_step_id = self._next_step_id()
        verify_start = perf_counter()
        verification_result = await self.effect_verifier.verify(
            page,
            expected=action.expected_effect,
            url_before=action_result.url_before,
            body_text_before=body_text_before,
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
                observation=verification_result.model_dump(mode="json"),
                error_type=verification_result.error_type,
                error_message=verification_result.message
                if not verification_result.satisfied
                else None,
                latency_ms=_elapsed_ms(verify_start),
            )
        )

        observe_step_id = self._next_step_id()
        observe_start = perf_counter()
        screenshot_path = self.trace_recorder.run_dir / f"{observe_step_id}_after_click.png"
        observation = await observe_page(page, screenshot_path=screenshot_path)
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
            if action_result.status == "success" and verification_result.satisfied
            else "failed"
        )
        error_type = action_result.error_type or verification_result.error_type
        error_message = action_result.error_message
        if error_message is None and not verification_result.satisfied:
            error_message = verification_result.message

        return {
            "status": status,
            "error_type": error_type,
            "error_message": error_message,
            "action_result": action_result.model_dump(mode="json"),
            "verification_result": verification_result.model_dump(mode="json"),
            "observation": observation.model_dump(mode="json"),
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
