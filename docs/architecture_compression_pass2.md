# Architecture Compression Pass 2

## Baseline

- Python files under `webscoper`: 119
- Python files under `webscoper/runtime`: 51
- Python files under `webscoper/browser`: 17
- Test files: 25
- Pytest collection: 122 tests

## Achieved

- Python files under `webscoper`: 99
- Python files under `webscoper/runtime`: 40
- Python files under `webscoper/browser`: 11
- Test files: 18
- Pytest collection: 78 tests

Measured with:

```bash
find webscoper -type f -name "*.py" | sort
find webscoper/runtime -type f -name "*.py" | sort
find webscoper/browser -type f -name "*.py" | sort
find tests -type f -name "test_*.py" | sort
uv run pytest --collect-only -q
```

## Collapse Plan

- Collapse `webscoper/browser/recovery/` into `webscoper/browser/recovery.py`.
- Collapse `webscoper/runtime/prompt/` into fewer prompt files and remove wrapper-only prompt modules.
- Collapse `webscoper/runtime/review/` into one review surface.
- Collapse `webscoper/runtime/safety/` by merging pending approval helpers into approvals/risk code.
- Collapse `webscoper/runtime/execution/` by merging parser, validation, result, and executor helpers into fewer execution files.
- Collapse `webscoper/runtime/artifacts/` so evidence, report, and trace remain while pipeline/transcript layering is removed or inlined.
- Collapse `webscoper/runtime/inspector/` so graph, timeline, loading, links, and presentation are not split into tiny framework files.
- Collapse `webscoper/runtime/llm/` around client, config, budget, and planner behavior.
- Collapse `webscoper/tools/gateway/` by merging audit, permissions, and error wrappers into the gateway/policy/provider files.
- Collapse `webscoper/workflows/langgraph_backend/` around adapter, graph, nodes, and state.

## Delete Plan

- Delete compatibility tool descriptors for `browser_open_observe` and `browser_click_intent` if no formal path requires them.
- Delete ToolGateway/browser runtime branches that only adapt those old tool names.
- Delete LLM prompt/action aliases that normalize old browser wrapper names.
- Delete docs and README examples that promote deterministic legacy command-line flows over the formal LangGraph path.
- Delete old schema aliases that exist only to preserve deleted wrapper behavior.
- Delete duplicate or low-value tests for helper internals, parser shapes, wrapper hiding, and old deterministic planner implementation details.

## Compatibility Wrappers To Remove

- old browser compatibility tool ids

Current hits show these still appear in:

- `webscoper/tools/registry.py`
- `webscoper/tools/gateway/providers.py`
- `webscoper/browser/tool_runtime.py`
- `webscoper/runtime/execution/results.py`
- `webscoper/runtime/execution/tool_executor.py`
- `webscoper/runtime/llm/auto_explore.py`
- `webscoper/runtime/llm/client.py`
- `webscoper/runtime/safety/risk_gate.py`
- `webscoper/schemas/runtime.py`
- prompt/tool tests and browser tool contract tests
- `docs/architecture_cleanup_audit.md`

## Test Shrink Plan

Keep product behavior coverage in these areas:

- API task creation, conversation persistence, diagnostics, approval, and resume
- Browser Tool Contract v2 behavior
- readiness, recovery, public web, and risk policy
- ToolGateway policy and invocation
- LangGraph workflow and approval bridge
- prompt tool exposure and LLM budget gates
- execution graph, evidence, report, and review
- docs research and GitHub issue research skills

Delete or merge:

- `tests/llm/test_auto_explore_action_contract.py` helper-shape cases not tied to the product path
- duplicate real/fake LLM readiness mocks
- old deterministic planner internals in `tests/runtime/test_execution_flow.py`
- parser implementation-detail cases in `tests/runtime/test_tools_and_parsing.py`
- compatibility wrapper assertions in prompt and browser contract tests
- duplicate public web policy cases that exercise the same gate
- low-value review/revision helper cases where one end-to-end report review test is enough
