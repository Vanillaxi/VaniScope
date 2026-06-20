from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.browser.readiness import PageReadinessDetector
from webscoper.browser.session import BrowserSession
from webscoper.browser.tool_runtime import StatefulBrowserToolRuntime
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.schemas.browser import ActionContract, ExpectedEffect


@pytest.mark.asyncio
async def test_readiness_detector_reports_loading_while_spinner_visible() -> None:
    async with BrowserSession() as page:
        await page.set_content(
            """
            <!doctype html>
            <html>
            <body>
              <main>
                <div class="spinner" role="progressbar">Loading forever</div>
                <p>Partial content</p>
              </main>
            </body>
            </html>
            """
        )
        result = await PageReadinessDetector(timeout_ms=150).wait_for_readiness(page)

    assert result.status == "loading"
    assert result.signals["spinner_absent"] is False


@pytest.mark.asyncio
async def test_readiness_detector_returns_ready_after_content_stabilizes(
    tmp_path: Path,
) -> None:
    page_url = _write_html(
        tmp_path,
        "readiness_skeleton.html",
        """
        <!doctype html>
        <html>
        <body>
          <main>
            <h1>Skeleton Fixture</h1>
            <div class="skeleton" data-skeleton>Placeholder card</div>
            <section id="content" hidden>Hydrated article content</section>
          </main>
          <script>
            setTimeout(() => {
              document.querySelector('.skeleton').remove();
              document.getElementById('content').hidden = false;
            }, 450);
          </script>
        </body>
        </html>
        """,
    )
    async with BrowserSession() as page:
        await page.goto(page_url, wait_until="domcontentloaded")
        result = await PageReadinessDetector(timeout_ms=2000).wait_for_readiness(page)

    assert result.status == "ready"
    assert result.signals["skeleton_absent"] is True
    assert result.signals["text_stable"] is True


@pytest.mark.asyncio
async def test_readiness_detector_degrades_when_network_quiet_is_unreliable(
    tmp_path: Path,
) -> None:
    page_url = _write_html(
        tmp_path,
        "long_polling_quiet.html",
        """
        <!doctype html>
        <html>
        <body>
          <main>
            <h1>Long Polling Fixture</h1>
            <p>Usable content despite ongoing polling</p>
            <button>Inspect</button>
          </main>
          <script>
            window.__webscoperPendingRequests = 1;
            setInterval(() => {
              performance.mark('poll-' + Date.now());
            }, 200);
          </script>
        </body>
        </html>
        """,
    )
    async with BrowserSession() as page:
        await page.goto(page_url, wait_until="domcontentloaded")
        result = await PageReadinessDetector(timeout_ms=900).wait_for_readiness(page)

    assert result.status == "degraded_ready"
    assert result.signals["soft_network_quiet"] is False


@pytest.mark.asyncio
async def test_action_waits_until_hydrated_button_becomes_enabled(tmp_path: Path) -> None:
    page_url = _write_html(
        tmp_path,
        "hydration_delayed_button.html",
        """
        <!doctype html>
        <html>
        <body>
          <main>
            <h1>Hydration Fixture</h1>
            <button id="load" disabled>Load details</button>
            <section id="result" hidden>Details ready after hydration</section>
          </main>
          <script>
            let hydrated = false;
            setTimeout(() => {
              hydrated = true;
              document.getElementById('load').disabled = false;
            }, 500);
            document.getElementById('load').addEventListener('click', () => {
              if (!hydrated) return;
              document.getElementById('result').hidden = false;
            });
          </script>
        </body>
        </html>
        """,
    )
    recorder = TraceRecorder(run_dir=tmp_path / "hydration", run_id="hydration")
    runtime = StatefulBrowserToolRuntime(trace_recorder=recorder)
    contract = ActionContract(
        action_type="click",
        intent="Click Load details",
        target_hint="Load details",
        preferred_roles=["button"],
        expected_effect=ExpectedEffect(
            type="content_appears",
            value="Details ready after hydration",
        ),
    )

    await runtime.start()
    try:
        await runtime.open_observe(page_url)
        output = await runtime.click_intent(contract)
    finally:
        await runtime.close()

    assert output["status"] == "success"
    assert "Details ready after hydration" in output["observation"]["visible_text_summary"]
    trace_steps = _read_jsonl(recorder.trace_path)
    readiness_steps = [
        step for step in trace_steps if step["action_type"] == "readiness_check"
    ]
    assert readiness_steps
    assert "readiness" in readiness_steps[0]["observation"]


@pytest.mark.asyncio
async def test_post_action_verifier_waits_for_spa_route_transition(tmp_path: Path) -> None:
    page_url = _write_html(
        tmp_path,
        "spa_route_delay.html",
        """
        <!doctype html>
        <html>
        <body>
          <main id="app">
            <h1>Home</h1>
            <button id="route">Open route</button>
          </main>
          <script>
            document.getElementById('route').addEventListener('click', () => {
              history.pushState({}, '', '#loading');
              document.getElementById('app').insertAdjacentHTML(
                'beforeend',
                '<div class="spinner" role="progressbar">Routing...</div>'
              );
              setTimeout(() => {
                history.pushState({}, '', '#details');
                document.getElementById('app').innerHTML =
                  '<h1>Details Route</h1><p>SPA details loaded</p>';
              }, 650);
            });
          </script>
        </body>
        </html>
        """,
    )
    recorder = TraceRecorder(run_dir=tmp_path / "spa", run_id="spa")
    runtime = StatefulBrowserToolRuntime(trace_recorder=recorder)
    contract = ActionContract(
        action_type="click",
        intent="Click Open route",
        target_hint="Open route",
        preferred_roles=["button"],
        expected_effect=ExpectedEffect(
            type="content_appears",
            value="SPA details loaded",
        ),
    )

    await runtime.start()
    try:
        await runtime.open_observe(page_url)
        output = await runtime.click_intent(contract)
    finally:
        await runtime.close()

    assert output["status"] == "success"
    assert "SPA details loaded" in output["observation"]["visible_text_summary"]
    trace_steps = _read_jsonl(recorder.trace_path)
    assert any(step["action_type"] == "post_action_readiness" for step in trace_steps)


@pytest.mark.asyncio
async def test_action_does_not_click_through_loading_overlay(tmp_path: Path) -> None:
    page_url = _write_html(
        tmp_path,
        "overlay_during_load.html",
        """
        <!doctype html>
        <html>
        <head>
          <style>
            .overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.2); }
          </style>
        </head>
        <body>
          <div class="overlay" data-blocking-overlay="true">Preparing controls...</div>
          <main>
            <h1>Overlay Fixture</h1>
            <button id="target">Continue</button>
            <section id="result" hidden>Overlay cleared and clicked</section>
          </main>
          <script>
            setTimeout(() => document.querySelector('.overlay').remove(), 500);
            document.getElementById('target').addEventListener('click', () => {
              document.getElementById('result').hidden = false;
            });
          </script>
        </body>
        </html>
        """,
    )
    recorder = TraceRecorder(run_dir=tmp_path / "overlay", run_id="overlay")
    runtime = StatefulBrowserToolRuntime(trace_recorder=recorder)
    contract = ActionContract(
        action_type="click",
        intent="Click Continue",
        target_hint="Continue",
        preferred_roles=["button"],
        expected_effect=ExpectedEffect(
            type="content_appears",
            value="Overlay cleared and clicked",
        ),
    )

    await runtime.start()
    try:
        await runtime.open_observe(page_url)
        output = await runtime.click_intent(contract)
    finally:
        await runtime.close()

    assert output["status"] == "success"
    action_readiness = output["action_result"]["metadata"]["pre_action_readiness"]
    assert action_readiness["signals"]["overlay_absent"] is True


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_html(tmp_path: Path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path.resolve().as_uri()
