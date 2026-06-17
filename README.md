# VaniScope

[中文说明](README_CN.md)

VaniScope / Web-Scoper phase one is a Python single-machine Browser Runtime MVP. It provides the browser execution foundation for public web tasks without LLMs, LangGraph, Go backend services, MCP, reviewers, or web research skills.

Current capabilities:

- Open public URLs.
- Observe page state and extract structured observations.
- Save screenshots.
- Write each action / observation to `trace.jsonl`.
- Detect basic high-risk page signals such as password, captcha, payment, and login.
- Provide a command-line smoke script that opens a page and generates a trace.

## Scope

This MVP does not bypass login, CAPTCHA, or paywalls. It does not enter real accounts, passwords, payment details, or identity documents. It is intended for public pages and test pages by default.

## Smoke Test

```bash
uv run python scripts/smoke_open_page.py https://example.com
uv run python scripts/smoke_open_page.py https://example.com --headed
```

Each run creates `traces/<run_id>/trace.jsonl` and `traces/<run_id>/step_001.png`.

The terminal prints the run ID, final URL, page title, screenshot path, interactive element count, risk signal count, and trace path.

## Tests

```bash
uv run pytest
```

## Project Layout

```text
webscoper/
  schemas/       # Pydantic schemas such as TraceStep and PageObservation
  runtime/       # TraceRecorder and BrowserRuntime orchestration
  browser/       # Playwright session, observer, and risk detection

scripts/
  smoke_open_page.py

traces/
  .gitkeep

tests/
  test_trace_recorder.py
```

## Future Extensions

The current module boundaries leave room for TargetResolver, ActionContract, EffectVerifier, and RecoveryManager. Phase one is limited to browser sessions, page observation, risk signals, and trace recording.
