# VaniScope Regression Eval Report

This report describes the release-candidate regression posture for the current
Python mainline. VaniScope is evaluated as a LangGraph-only Browser Agent
Runtime. The evals are local, deterministic or fake-LLM only, and do not require
real network access, real GitHub access, real MCP servers, or real LLM
credentials.

## Evaluation Scope

The regression suite covers these runtime surfaces:

- Browser Runtime execution on local fixtures
- LangGraph workflow orchestration
- ToolGateway invocation, policy, audit, approval, and blocking behavior
- Recovery planning and telemetry
- Evidence, report, review, compaction, and skill artifacts
- Runtime Inspector timeline and summary aggregation
- Docs Research and GitHub Issue Research demo skills
- FastAPI task lifecycle, approval resume, artifact, timeline, inspector, and diagnostics endpoints

## Browser Runtime Eval Coverage

Browser Runtime tests cover local Playwright execution against fixture pages:

- basic open/observe/click intent
- target resolution by button/link text and intent hints
- effect verification for expected text
- delayed content and lazy controls
- modal overlay recovery
- no-effect click recovery
- ambiguous target recovery
- disabled control blocking
- login/password and CAPTCHA blocking
- risk signal detection for submit/delete/payment/password/CAPTCHA flows

Key artifacts verified:

- `trace.jsonl`
- `transcript.jsonl`
- `events.jsonl`
- `evidence.jsonl`
- `recovery.jsonl`
- `risk_report.json`

## LangGraph Skill Eval Coverage

`tests/fixtures/langgraph_skill_eval_cases.json` runs the skill demos through
the same LangGraph workflow used by the API and console.

Docs Research cases verify:

- English and Chinese install/run queries
- console API configuration query
- insufficient-information behavior
- `skill_result.json` status
- evidence-backed final reports
- deterministic review pass

GitHub Issue Research cases verify:

- local mock issue analysis only
- difficulty estimate
- contribution value
- affected modules
- risk/caveat extraction
- English and Chinese queries
- uncertainty handling around acceptance criteria

Required artifacts include:

- `final_report.md`
- `evidence.jsonl`
- `review.json`
- `skill_result.json`
- `tool_audit.jsonl`

## Demo Scenario Coverage

### Docs Research Demo

The Docs Research demo reads `tests/fixtures/mock_site/docs_research.html`,
answers install/run or API configuration questions, writes evidence, generates
`skill_result.json`, and produces a reviewed report. It is a local docs-reading
demo, not a web search assistant.

### GitHub Issue Research Demo

The GitHub Issue Research demo reads
`tests/fixtures/mock_site/github_issue_research.html`. It does not call GitHub.
It demonstrates structured issue assessment: difficulty, contribution value,
affected modules, risks, caveats, and recommendation.

### Approval Demo

The approval demo uses `tests/fixtures/mock_site/risk_actions.html` with a
submit-style action. RiskGate requires approval, LangGraph pauses, and FastAPI
persists approval and pending-call artifacts. Resume and reject behavior are
covered by API and workflow tests.

Verified artifacts:

- `approvals.jsonl`
- `pending.jsonl`
- `risk_report.json`
- `tool_audit.jsonl`
- `events.jsonl`

### Recovery Demo

The recovery demo uses local lazy, modal, no-effect, ambiguous, disabled,
login, and CAPTCHA fixtures. Recovery evals assert the strategy kind and error
type recorded in `recovery.jsonl`, not only final status.

Example strategy checks:

- `wait_and_reobserve`
- `close_modal_if_safe`
- `abort_as_failed`

## Artifact And Inspector Verification

Runtime Inspector coverage verifies that incomplete and successful run
directories can be replayed without re-executing a task. The inspector reads
artifacts, tolerates missing files, rejects path traversal, merges timeline
items, builds evidence links, and returns presentation metadata for
user-facing and developer-only artifact views.

Important endpoints:

```text
GET /tasks/{task_id}/timeline
GET /tasks/{task_id}/inspector
GET /diagnostics
```

Important UI views:

- Overview
- Timeline
- Report
- Evidence
- Review
- Tools
- LLM / Prompt
- Debug

## Deterministic Smoke Validation

Phase 39 adds:

```bash
uv run python scripts/run_phase39_smoke.py \
  --output-dir eval_results/phase39_demo_smoke
```

The smoke runner executes local deterministic demos for:

- `docs_research`
- `github_issue_research`
- approval pause
- recovery
- artifact existence
- inspector and timeline availability

It writes `summary.json` under the selected output directory and returns a
non-zero exit code on failure.

## Known Limitations

- Real websites are not part of the release-candidate regression target.
- Real LLM providers are supported only through explicit local config and are
  not enabled by default.
- GitHub Issue Research uses a mock issue fixture; it does not use GitHub API.
- No database, authentication, multi-user tenancy, or hosted deployment is
  included.
- Browser automation does not bypass login, CAPTCHA, paywalls, or access
  control.
- The Next.js console is a local control surface, not a production SaaS UI.
- Go control plane work is intentionally deferred to a later branch.

## Intentionally Out Of Scope

- Native workflow compatibility
- Real MCP server integration
- Real network scraping as a default demo path
- Long-running distributed workers
- Cross-browser matrix testing
- Production secrets management
- Heavy Playwright end-to-end UI tests for the console
