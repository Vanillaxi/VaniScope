# Test Layout

Use this directory as a map for choosing the smallest useful validation set.

## Fast Checks

- `tests/llm/`, `tests/runtime/`, `tests/tools/`, and `tests/eval/` are mostly deterministic unit or integration checks.
- `tests/runtime/test_budget_control_v2.py` covers token budget, user stop/resume, and graph labels.
- `tests/runtime/test_llm_timeout_control.py` covers provider timeout retry and timeout approval choices.

## Browser-Launching Checks

- `tests/browser/`, many `tests/api/`, `tests/skills/`, and `tests/workflows/` cases launch Playwright/Chromium.
- In the Codex sandbox on macOS, these can fail with Mach bootstrap permission errors. Run them outside the sandbox or with an approved escalation.

## Eval And Smoke

- Workflow evals are regression suites, not pytest replacements:
  - `tests/fixtures/langgraph_main_eval_cases.json`
  - `tests/fixtures/tool_gateway_eval_cases.json`
  - `tests/fixtures/langgraph_skill_eval_cases.json`
- Public web and real LLM smoke cases are manual and non-deterministic; keep them opt-in.

## Cleanup Rule

Prefer moving new coverage into the nearest existing area before creating a new test file. Create a new file only when it names a distinct behavior boundary, such as provider timeout control.
