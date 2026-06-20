from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webscoper.api.schemas import TaskCreateRequest
from webscoper.api.task_service import TaskService


@dataclass(frozen=True)
class SmokeCase:
    case_id: str
    request: dict[str, Any]
    expected_status: str
    required_artifacts: tuple[str, ...]
    min_timeline_items: int = 1
    min_evidence_count: int = 0


SMOKE_CASES: tuple[SmokeCase, ...] = (
    SmokeCase(
        case_id="docs_research_demo",
        request={
            "url": "tests/fixtures/mock_site/docs_research.html",
            "task_type": "docs_research",
            "skill_id": "docs_research",
            "query": "How do I install and run VaniScope?",
            "language": "en",
            "planner": "deterministic",
            "workspace": "tests/fixtures/workspace",
        },
        expected_status="succeeded",
        required_artifacts=(
            "final_report.md",
            "evidence.jsonl",
            "review.json",
            "skill_result.json",
            "tool_audit.jsonl",
        ),
        min_evidence_count=1,
    ),
    SmokeCase(
        case_id="github_issue_research_demo",
        request={
            "url": "tests/fixtures/mock_site/github_issue_research.html",
            "task_type": "github_issue_research",
            "skill_id": "github_issue_research",
            "query": (
                "Analyze whether this issue is worth doing and summarize "
                "difficulty, affected modules, and risks."
            ),
            "language": "en",
            "planner": "deterministic",
            "workspace": "tests/fixtures/workspace",
        },
        expected_status="succeeded",
        required_artifacts=(
            "final_report.md",
            "evidence.jsonl",
            "review.json",
            "skill_result.json",
            "tool_audit.jsonl",
        ),
        min_evidence_count=2,
    ),
    SmokeCase(
        case_id="approval_demo",
        request={
            "url": "tests/fixtures/mock_site/risk_actions.html",
            "click": "Submit",
            "expect": "Submitted successfully",
            "planner": "deterministic",
            "workspace": "tests/fixtures/workspace",
            "reminder": "Do not auto-approve this smoke case.",
        },
        expected_status="requires_approval",
        required_artifacts=(
            "trace.jsonl",
            "transcript.jsonl",
            "approvals.jsonl",
            "pending.jsonl",
            "risk_report.json",
            "tool_audit.jsonl",
        ),
    ),
    SmokeCase(
        case_id="recovery_demo",
        request={
            "url": "tests/fixtures/mock_site/lazy_button.html",
            "click": "Quickstart",
            "expect": "pip install playwright",
            "planner": "deterministic",
            "workspace": "tests/fixtures/workspace",
            "reminder": "Exercise deterministic local recovery.",
        },
        expected_status="succeeded",
        required_artifacts=(
            "final_report.md",
            "evidence.jsonl",
            "review.json",
            "recovery.jsonl",
            "trace.jsonl",
            "tool_audit.jsonl",
        ),
        min_evidence_count=1,
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic Phase 39 local demo smoke checks."
    )
    parser.add_argument(
        "--output-dir",
        default="eval_results/phase39_demo_smoke",
        help="Directory for smoke run artifacts and summary.json.",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not delete an existing output directory before running.",
    )
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    if output_dir.exists() and not args.keep_existing:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    service = TaskService(runs_dir=output_dir / "runs")
    results = [_run_case(service, case) for case in SMOKE_CASES]
    passed = sum(1 for result in results if result["passed"])
    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "backend": "langgraph",
        "real_network_required": False,
        "real_llm_required": False,
        "output_dir": str(output_dir),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "cases": results,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["failed"] == 0 else 1


def _run_case(service: TaskService, case: SmokeCase) -> dict[str, Any]:
    differences: list[str] = []
    response = service.create_and_run_task(TaskCreateRequest.model_validate(case.request))
    artifacts = set(response.artifacts)
    missing_artifacts = sorted(set(case.required_artifacts) - artifacts)
    if response.status != case.expected_status:
        differences.append(
            f"status expected {case.expected_status}, got {response.status}"
        )
    if missing_artifacts:
        differences.append("missing artifacts: " + ", ".join(missing_artifacts))

    timeline_count = 0
    evidence_count = 0
    inspector_available = False
    timeline_available = False
    review_status: str | None = None
    try:
        timeline = service.get_timeline(response.task_id)
        timeline_available = True
        timeline_count = len(timeline.timeline_items)
        if timeline_count < case.min_timeline_items:
            differences.append(
                f"timeline items expected >= {case.min_timeline_items}, got {timeline_count}"
            )
    except Exception as exc:
        differences.append(f"timeline unavailable: {type(exc).__name__}: {exc}")

    try:
        inspector = service.get_inspector(response.task_id)
        inspector_available = True
        evidence_count = inspector.summary.evidence_count
        review_status = inspector.summary.review_status
        if evidence_count < case.min_evidence_count:
            differences.append(
                f"evidence count expected >= {case.min_evidence_count}, got {evidence_count}"
            )
        if not inspector.artifact_presentations:
            differences.append("artifact presentations are empty")
    except Exception as exc:
        differences.append(f"inspector unavailable: {type(exc).__name__}: {exc}")

    return {
        "case_id": case.case_id,
        "task_id": response.task_id,
        "status": response.status,
        "passed": not differences,
        "differences": differences,
        "missing_artifacts": missing_artifacts,
        "artifact_count": len(response.artifacts),
        "artifacts": sorted(response.artifacts),
        "timeline_available": timeline_available,
        "timeline_count": timeline_count,
        "inspector_available": inspector_available,
        "evidence_count": evidence_count,
        "review_status": review_status,
        "error": response.error,
    }


if __name__ == "__main__":
    raise SystemExit(main())
