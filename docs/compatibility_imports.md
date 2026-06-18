# Runtime Compatibility Imports

After the runtime package split, old flat runtime import paths are kept as compatibility re-exports.

Project-internal code should prefer the new package paths.

Do not remove compatibility wrappers until a later dedicated cleanup phase.

## Legacy To New Path

| Legacy Path | New Path |
|---|---|
| `webscoper.runtime.evidence` | `webscoper.runtime.artifacts.evidence` |
| `webscoper.runtime.report` | `webscoper.runtime.artifacts.report` |
| `webscoper.runtime.trace` | `webscoper.runtime.artifacts.trace` |
| `webscoper.runtime.transcript` | `webscoper.runtime.artifacts.transcript` |
| `webscoper.runtime.compaction` | `webscoper.runtime.artifacts.compaction` |
| `webscoper.runtime.llm_client` | `webscoper.runtime.llm.client` |
| `webscoper.runtime.llm_config` | `webscoper.runtime.llm.config` |
| `webscoper.runtime.llm_router` | `webscoper.runtime.llm.router` |
| `webscoper.runtime.llm_planner` | `webscoper.runtime.llm.planner` |
| `webscoper.runtime.llm_reviewer` | `webscoper.runtime.llm.reviewer` |
| `webscoper.runtime.prompt_builder` | `webscoper.runtime.prompt.builder` |
| `webscoper.runtime.agents_md` | `webscoper.runtime.prompt.agents_md` |
| `webscoper.runtime.reminders` | `webscoper.runtime.prompt.reminders` |
| `webscoper.runtime.reviewer` | `webscoper.runtime.review.reviewer` |
| `webscoper.runtime.revision` | `webscoper.runtime.review.revision` |
| `webscoper.runtime.revise_loop` | `webscoper.runtime.review.revise_loop` |
| `webscoper.runtime.approvals` | `webscoper.runtime.safety.approvals` |
| `webscoper.runtime.pending` | `webscoper.runtime.safety.pending` |
| `webscoper.runtime.risk_gate` | `webscoper.runtime.safety.risk_gate` |
| `webscoper.runtime.execution_loop` | `webscoper.runtime.execution.loop` |
| `webscoper.runtime.planner` | `webscoper.runtime.execution.planner` |
| `webscoper.runtime.plan_validator` | `webscoper.runtime.execution.plan_validator` |
| `webscoper.runtime.tool_executor` | `webscoper.runtime.execution.tool_executor` |
| `webscoper.runtime.tool_call_parser` | `webscoper.runtime.execution.tool_call_parser` |
