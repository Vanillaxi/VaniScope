from __future__ import annotations

from webscoper.runtime.inspector.schemas import ArtifactPresentation


_ARTIFACT_TYPES: dict[str, tuple[str, str, bool, bool, str, int]] = {
    "final_report.md": (
        "report",
        "Final report",
        True,
        False,
        "markdown",
        10,
    ),
    "evidence.jsonl": (
        "evidence",
        "Evidence",
        True,
        False,
        "cards",
        20,
    ),
    "review.json": (
        "review",
        "Review",
        True,
        False,
        "summary",
        30,
    ),
    "timeline.json": (
        "events",
        "Timeline",
        True,
        False,
        "timeline",
        40,
    ),
    "tool_audit.jsonl": (
        "tool_audit",
        "Tool audit",
        True,
        False,
        "table",
        50,
    ),
    "llm_calls.jsonl": (
        "llm_calls",
        "LLM calls",
        True,
        False,
        "summary",
        60,
    ),
    "budget_decisions.jsonl": (
        "budget",
        "Budget decisions",
        True,
        False,
        "summary",
        65,
    ),
    "prompt_budget_estimate.json": (
        "budget",
        "Prompt budget estimate",
        True,
        False,
        "summary",
        66,
    ),
    "user_control.jsonl": (
        "control",
        "User control",
        True,
        False,
        "summary",
        67,
    ),
    "approvals.jsonl": (
        "approval",
        "Approvals",
        True,
        False,
        "summary",
        70,
    ),
    "pending.jsonl": (
        "approval",
        "Pending approvals",
        True,
        False,
        "summary",
        71,
    ),
    "recovery.jsonl": (
        "recovery",
        "Recovery",
        True,
        False,
        "summary",
        80,
    ),
    "skill_result.json": (
        "skill_result",
        "Skill result",
        True,
        False,
        "summary",
        90,
    ),
    "prompt_preview.md": (
        "prompt",
        "Prompt preview",
        False,
        True,
        "raw",
        200,
    ),
    "prompt_context.json": (
        "prompt",
        "Prompt context",
        False,
        True,
        "raw",
        201,
    ),
    "trace.jsonl": (
        "trace",
        "Trace",
        False,
        True,
        "raw",
        210,
    ),
    "transcript.jsonl": (
        "transcript",
        "Transcript",
        False,
        True,
        "raw",
        220,
    ),
    "events.jsonl": (
        "events",
        "Events",
        False,
        True,
        "raw",
        230,
    ),
}


def artifact_presentations(artifact_names: list[str]) -> list[ArtifactPresentation]:
    return sorted(
        (artifact_presentation(name) for name in artifact_names),
        key=lambda item: (item.priority, item.artifact_name),
    )


def artifact_presentation(artifact_name: str) -> ArtifactPresentation:
    artifact_type, title, user_facing, developer_only, default_view, priority = (
        _ARTIFACT_TYPES.get(
            artifact_name,
            (
                _infer_artifact_type(artifact_name),
                _title_from_name(artifact_name),
                True,
                False,
                _infer_default_view(artifact_name),
                500,
            ),
        )
    )
    return ArtifactPresentation(
        artifact_name=artifact_name,
        artifact_type=artifact_type,
        display_title=title,
        user_facing=user_facing,
        developer_only=developer_only,
        default_view=default_view,
        description=_description(artifact_type, developer_only),
        priority=priority,
    )


def _infer_artifact_type(artifact_name: str) -> str:
    if artifact_name.endswith(".md"):
        return "report"
    if artifact_name.endswith(".jsonl"):
        return "trace"
    if artifact_name.endswith(".json"):
        return "unknown"
    return "unknown"


def _infer_default_view(artifact_name: str) -> str:
    if artifact_name.endswith(".md"):
        return "markdown"
    return "raw"


def _title_from_name(artifact_name: str) -> str:
    return artifact_name.rsplit(".", 1)[0].replace("_", " ").strip().title()


def _description(artifact_type: str, developer_only: bool) -> str:
    if developer_only:
        return "Developer/debug artifact; raw content is hidden from the default user view."
    return f"User-facing {artifact_type.replace('_', ' ')} artifact."
