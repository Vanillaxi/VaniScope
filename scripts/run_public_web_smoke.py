from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webscoper.browser.public_web import (  # noqa: E402
    DEFAULT_RUNTIME_CONFIG_PATH,
    PublicWebRuntimeConfig,
    load_public_web_config,
)
from webscoper.runtime.execution.runner import run_browser_task_sync  # noqa: E402


DEFAULT_CASES_PATH = Path("tests/fixtures/public_web_smoke_cases.example.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run manual, opt-in public web smoke cases."
    )
    parser.add_argument(
        "--cases",
        default=str(DEFAULT_CASES_PATH),
        help="Path to public web smoke cases JSON.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_RUNTIME_CONFIG_PATH),
        help="Path to runtime TOML config.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory where smoke summary and task artifacts are written.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode.",
    )
    args = parser.parse_args()

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path("runs")
        / f"public_web_smoke_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = _load_cases(Path(args.cases))
    config = load_public_web_config(args.config)

    results = []
    if not config.public_network_enabled:
        results = [
            _skipped_case(
                case,
                output_dir,
                (
                    "Public web smoke requires public_network_enabled = true "
                    f"in {args.config}."
                ),
            )
            for case in cases
        ]
    else:
        for case in cases:
            results.append(_run_case(case, config, output_dir, headed=args.headed))

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "cases_path": str(Path(args.cases)),
        "config": config.model_dump(mode="json"),
        "output_dir": str(output_dir),
        "total": len(results),
        "succeeded": sum(1 for result in results if result["task_status"] == "succeeded"),
        "failed": sum(1 for result in results if result["task_status"] == "failed"),
        "blocked": sum(1 for result in results if result["task_status"] == "blocked"),
        "skipped": sum(1 for result in results if result["task_status"] == "skipped"),
        "cases": results,
        "note": "Manual non-deterministic smoke only; not a benchmark or pytest suite.",
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"summary_json: {summary_path}")
    print(f"total: {summary['total']}")
    print(f"succeeded: {summary['succeeded']}")
    print(f"failed: {summary['failed']}")
    print(f"blocked: {summary['blocked']}")
    print(f"skipped: {summary['skipped']}")
    if summary["skipped"] == summary["total"] and summary["total"]:
        return 2
    return 1 if summary["failed"] or summary["blocked"] else 0


def _run_case(
    case: dict[str, Any],
    config: PublicWebRuntimeConfig,
    output_dir: Path,
    *,
    headed: bool,
) -> dict[str, Any]:
    case_id = _safe_case_id(str(case.get("case_id") or case.get("url") or "case"))
    run_dir = output_dir / "runs" / case_id
    failure_reason: str | None = None
    task_status = "failed"
    final_url: str | None = None
    final_title: str | None = None
    visible_text_non_empty = False

    try:
        result = run_browser_task_sync(
            url=str(case["url"]),
            planner="deterministic",
            reviewer="deterministic",
            output_root=output_dir / "runs",
            headed=headed,
            task_id=case_id,
            public_web_config=config,
        )
        observation = result.observation
        context = result.handler.last_context
        run_dir = context.run_dir if context is not None else run_dir
        task_status = _task_status_from_context(context) or "succeeded"
        final_url = observation.url
        final_title = observation.title
        visible_text_non_empty = bool(observation.visible_text_summary.strip())
    except Exception as exc:
        failure_reason = f"{type(exc).__name__}: {exc}"
        task_status = _status_from_run_dir(run_dir) or "failed"
        final_url, final_title, visible_text_non_empty = _last_observation(run_dir)

    artifacts = _artifact_status(run_dir)
    if task_status == "succeeded":
        soft_assertions = {
            "page_opens": bool(final_url),
            "title_exists": bool(final_title),
            "visible_text_non_empty": visible_text_non_empty,
            "final_report_exists": artifacts["final_report_md"],
            "evidence_has_entries": artifacts["evidence_jsonl_entries"] > 0,
            "trace_exists": artifacts["trace_jsonl"],
            "events_has_entries": artifacts["events_jsonl_entries"] > 0,
        }
    else:
        soft_assertions = {
            "failure_reason_recorded": bool(failure_reason)
            or bool(_trace_error_message(run_dir)),
        }

    return {
        "case_id": case_id,
        "description": case.get("description"),
        "url": case.get("url"),
        "task_status": task_status,
        "final_url": final_url,
        "final_title": final_title,
        "artifact_status": artifacts,
        "failure_reason": failure_reason or _trace_error_message(run_dir),
        "soft_assertions": soft_assertions,
        "run_dir": str(run_dir),
    }


def _skipped_case(
    case: dict[str, Any],
    output_dir: Path,
    reason: str,
) -> dict[str, Any]:
    case_id = _safe_case_id(str(case.get("case_id") or case.get("url") or "case"))
    return {
        "case_id": case_id,
        "description": case.get("description"),
        "url": case.get("url"),
        "task_status": "skipped",
        "final_url": None,
        "final_title": None,
        "artifact_status": _artifact_status(output_dir / "runs" / case_id),
        "failure_reason": reason,
        "soft_assertions": {"failure_reason_recorded": True},
        "run_dir": str(output_dir / "runs" / case_id),
    }


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Public web smoke cases must be a JSON list.")
    cases = [item for item in payload if isinstance(item, dict) and item.get("url")]
    if not cases:
        raise ValueError("Public web smoke cases file contains no URL cases.")
    return cases


def _artifact_status(run_dir: Path) -> dict[str, Any]:
    trace_path = run_dir / "trace.jsonl"
    screenshot_paths = _screenshot_paths(trace_path)
    return {
        "run_dir_exists": run_dir.exists(),
        "final_report_md": (run_dir / "final_report.md").exists(),
        "evidence_jsonl": (run_dir / "evidence.jsonl").exists(),
        "evidence_jsonl_entries": _jsonl_count(run_dir / "evidence.jsonl"),
        "trace_jsonl": trace_path.exists(),
        "trace_path": str(trace_path) if trace_path.exists() else None,
        "events_jsonl": (run_dir / "events.jsonl").exists(),
        "events_jsonl_entries": _jsonl_count(run_dir / "events.jsonl"),
        "screenshots": screenshot_paths,
        "screenshots_exist": [Path(path).exists() for path in screenshot_paths],
    }


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _screenshot_paths(trace_path: Path) -> list[str]:
    paths: list[str] = []
    if not trace_path.exists():
        return paths
    for row in _read_jsonl(trace_path):
        screenshot_path = row.get("screenshot_path")
        if isinstance(screenshot_path, str) and screenshot_path:
            paths.append(screenshot_path)
    return paths


def _last_observation(run_dir: Path) -> tuple[str | None, str | None, bool]:
    observations = [
        row.get("observation")
        for row in _read_jsonl(run_dir / "trace.jsonl")
        if isinstance(row.get("observation"), dict)
    ]
    for observation in reversed(observations):
        if "url" in observation or "title" in observation:
            return (
                _str_or_none(observation.get("url")),
                _str_or_none(observation.get("title")),
                bool(str(observation.get("visible_text_summary") or "").strip()),
            )
    return None, None, False


def _trace_error_message(run_dir: Path) -> str | None:
    for row in reversed(_read_jsonl(run_dir / "trace.jsonl")):
        message = row.get("error_message")
        if isinstance(message, str) and message:
            return message
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _status_from_run_dir(run_dir: Path) -> str | None:
    transcript = _read_jsonl(run_dir / "transcript.jsonl")
    for row in reversed(transcript):
        event_type = row.get("event_type")
        payload = row.get("payload")
        if event_type in {"execution_completed", "task_finished"}:
            return "succeeded"
        if isinstance(payload, dict):
            state = payload.get("state")
            if isinstance(state, dict) and isinstance(state.get("status"), str):
                status = state["status"]
                if status == "completed":
                    return "succeeded"
                if status in {"blocked", "requires_approval", "rejected"}:
                    return status
                if status == "failed":
                    return "failed"
    return None


def _task_status_from_context(context: Any | None) -> str | None:
    if context is None:
        return None
    status = context.state.status
    if status == "completed":
        return "succeeded"
    if status in {"blocked", "requires_approval", "rejected"}:
        return status
    if status == "failed":
        return "failed"
    return None


def _safe_case_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "public_web_case"


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
