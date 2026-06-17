from __future__ import annotations

from time import perf_counter
from typing import Any

from webscoper.browser.observer import observe_page
from webscoper.browser.session import BrowserSession
from webscoper.runtime.trace import TraceRecorder
from webscoper.schemas.observation import PageObservation
from webscoper.schemas.trace import TraceStep


class BrowserRuntime:
    def __init__(self, trace_recorder: TraceRecorder, headless: bool = True) -> None:
        self.trace_recorder = trace_recorder
        self.headless = headless

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


def _elapsed_ms(start: float) -> int:
    return int((perf_counter() - start) * 1000)


def _model_dump(observation: PageObservation) -> dict[str, Any]:
    if hasattr(observation, "model_dump"):
        return observation.model_dump(mode="json")
    return observation.dict()
