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
  registry includes `docs_research` and `github_issue_research`.
- `webscoper/skills/router.py` deterministically routes a `TaskSpec` to a skill
  from explicit `skill_id`, task type, or a URL plus query/research goal.
- `webscoper/skills/docs_research.py` implements the docs research skill.
- `webscoper/skills/github_issue_research.py` implements the GitHub issue
  contribution research skill.

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

## github_issue_research

`github_issue_research` analyzes a local mock GitHub issue or PR page and
produces an evidence-backed contribution report. It is designed for questions
such as:

```text
url: tests/fixtures/mock_site/github_issue_research.html
task_type: github_issue_research
skill_id: github_issue_research
query: Analyze whether this issue is worth doing and summarize difficulty, affected modules, and risks.
language: en
```

The skill uses the opened page as the source of truth. It does not access
`github.com`, does not call the GitHub API, does not use OAuth, and does not
submit comments, create PRs, or modify repository state. The current fixture
simulates repository metadata, labels, affected files, maintainer comments,
acceptance criteria, and implementation risks.

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

For `github_issue_research`, `skill_result.json` also includes:

- `task_type`
- `recommendation`
- `difficulty`
- `contribution_value`
- `affected_modules`

## Eval

Skill eval uses local fixtures only:

```bash
uv run python scripts/run_langgraph_eval.py \
  --cases tests/fixtures/langgraph_skill_eval_cases.json \
  --output-dir eval_results/langgraph_skill_eval_local
```

The cases verify docs research and GitHub issue research artifacts, report
phrases, evidence counts, review status, skill result status, affected modules,
difficulty, and contribution value without real network access or real LLM
calls.
