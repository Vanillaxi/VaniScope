# Skill System

VaniScope skills are task-level capabilities above the Browser Runtime. They do
not replace LangGraph and do not bypass ToolGateway. A skill selects task
instructions, expected evidence, artifact expectations, and deterministic report
metadata while the LangGraph workflow still performs prompt, plan, tool
execution, report, review, compaction, and finalization.

## Modules

- `webscoper/skills/base.py` defines `SkillDefinition`, `SkillInput`,
  `SkillPlan`, `SkillResult`, and `SkillInstruction`.
- `webscoper/skills/registry.py` registers available skills. The default
  registry includes `docs_research`.
- `webscoper/skills/router.py` deterministically routes a `TaskSpec` to a skill
  from explicit `skill_id`, task type, or a URL plus query/research goal.
- `webscoper/skills/docs_research.py` implements the first skill MVP.

## docs_research

`docs_research` reads one local documentation page or mock page and produces an
evidence-backed report. It is designed for questions such as:

```text
url: tests/fixtures/mock_site/docs_research.html
task_type: docs_research
skill_id: docs_research
query: How do I install and run VaniScope?
language: en
```

The skill instruction is injected into `DynamicPromptBuilder` before tool
instructions. It emphasizes page-grounded answers, no unsupported claims,
evidence references, source URL preservation, and explicit limitations when
page information is insufficient.

## Artifacts

Skill-aware runs still write the normal runtime artifacts:

- `evidence.jsonl`
- `final_report.md`
- `review.json`
- `review_summary.md`
- `compact_context.json`
- `tool_audit.jsonl`
- `workflow_state.json`

They also write:

- `skill_result.json`

`skill_result.json` records the skill id, status, summary, relevant evidence
ids, expected artifact names, query, language, and evidence counts.

## Eval

Skill eval uses local fixtures only:

```bash
uv run python scripts/run_langgraph_eval.py \
  --cases tests/fixtures/langgraph_skill_eval_cases.json \
  --output-dir eval_results/langgraph_skill_eval_local
```

The cases verify docs research artifacts, report phrases, evidence counts,
review status, and skill result status without real network access or real LLM
calls.
