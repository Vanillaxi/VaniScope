from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webscoper.api.schemas import TaskCreateRequest  # noqa: E402
from webscoper.api.task_service import TaskService  # noqa: E402
from webscoper.browser.public_web import DEFAULT_RUNTIME_CONFIG_PATH, load_public_web_config  # noqa: E402
from webscoper.runtime.llm.config import load_llm_router_config_from_file  # noqa: E402


DEFAULT_CASES_PATH = Path("tests/fixtures/real_llm_smoke_cases.example.json")
DEFAULT_LLM_CONFIG_PATH = Path("configs/llm.local.toml")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run manual, opt-in real LLM auto_explore smoke cases."
    )
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--llm-config", default=str(DEFAULT_LLM_CONFIG_PATH))
    parser.add_argument("--runtime-config", default=str(DEFAULT_RUNTIME_CONFIG_PATH))
    parser.add_argument("--output-dir")
    parser.add_argument("--max-steps", type=int, default=8)
    args = parser.parse_args()

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path("eval_results")
        / f"real_llm_smoke_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = _load_cases(Path(args.cases))
    llm_status = _llm_config_status(Path(args.llm_config))
    web_config = load_public_web_config(args.runtime_config)

    if not llm_status["real_enabled"]:
        results = [
            _skipped_case(case, output_dir, "Real LLM smoke requires router.mode = real.")
            for case in cases
        ]
    elif not web_config.public_network_enabled:
        results = [
            _skipped_case(
                case,
                output_dir,
                "Real LLM smoke requires public_network_enabled = true.",
            )
            for case in cases
        ]
    else:
        service = TaskService(
            runs_dir=output_dir / "runs",
            runtime_config_path=args.runtime_config,
            persistence_path=output_dir / "vaniscope_smoke.db",
        )
        results = [
            _run_case(
                service,
                case,
                output_dir,
                llm_config=Path(args.llm_config),
                runtime_config=Path(args.runtime_config),
                max_steps=int(case.get("max_steps") or args.max_steps),
            )
            for case in cases
        ]

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "cases_path": str(Path(args.cases)),
        "output_dir": str(output_dir),
        "llm": llm_status,
        "web": web_config.diagnostics_payload(),
        "total": len(results),
        "succeeded": sum(1 for result in results if result["task_status"] == "succeeded"),
        "failed": sum(1 for result in results if result["task_status"] == "failed"),
        "blocked": sum(1 for result in results if result["task_status"] == "blocked"),
        "skipped": sum(1 for result in results if result["task_status"] == "skipped"),
        "cases": results,
        "note": "Manual, opt-in, non-deterministic smoke only; not pytest or CI.",
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
    service: TaskService,
    case: dict[str, Any],
    output_dir: Path,
    *,
    llm_config: Path,
    runtime_config: Path,
    max_steps: int,
) -> dict[str, Any]:
    case_id = _safe_case_id(str(case.get("case_id") or case.get("url") or "case"))
    failure_reason: str | None = None
    response = None
    try:
        response = service.create_and_run_task(
            TaskCreateRequest(
                url=str(case["url"]),
                goal=str(case["goal"]),
                mode="auto_explore",
                planner="real_llm",
                reviewer="deterministic",
                repair_attempts=1,
                max_steps=max_steps,
                llm_config=str(llm_config),
                public_web_config=str(runtime_config),
                task_type="browser_task",
            )
        )
        task_status = response.status
        run_dir = Path(response.run_dir)
    except Exception as exc:
        task_status = "failed"
        run_dir = output_dir / "runs" / case_id
        failure_reason = f"{type(exc).__name__}: {exc}"

    final_url, final_title = _last_observation(run_dir)
    artifacts = _artifact_status(run_dir)
    soft_assertions = {
        "run_dir_exists": run_dir.exists(),
        "llm_calls_recorded": artifacts["llm_call_count"] > 0,
        "tool_actions_recorded": artifacts["action_count"] > 0,
        "has_trace": artifacts["trace_jsonl"],
        "has_evidence": artifacts["evidence_jsonl_entries"] > 0,
        "has_final_report_when_succeeded": task_status != "succeeded"
        or artifacts["final_report_md"],
    }
    return {
        "case_id": case_id,
        "description": case.get("description"),
        "url": case.get("url"),
        "goal": case.get("goal"),
        "task_status": task_status,
        "final_url": final_url,
        "final_title": final_title,
        "action_count": artifacts["action_count"],
        "llm_call_count": artifacts["llm_call_count"],
        "artifacts": artifacts,
        "failure_reason": failure_reason or (response.error if response else None),
        "soft_assertions": soft_assertions,
        "run_dir": str(run_dir),
    }


def _skipped_case(case: dict[str, Any], output_dir: Path, reason: str) -> dict[str, Any]:
    case_id = _safe_case_id(str(case.get("case_id") or case.get("url") or "case"))
    return {
        "case_id": case_id,
        "description": case.get("description"),
        "url": case.get("url"),
        "goal": case.get("goal"),
        "task_status": "skipped",
        "final_url": None,
        "final_title": None,
        "action_count": 0,
        "llm_call_count": 0,
        "artifacts": _artifact_status(output_dir / "runs" / case_id),
        "failure_reason": reason,
        "soft_assertions": {"failure_reason_recorded": True},
        "run_dir": str(output_dir / "runs" / case_id),
    }


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Real LLM smoke cases must be a JSON list.")
    cases = [item for item in payload if isinstance(item, dict) and item.get("url") and item.get("goal")]
    if not cases:
        raise ValueError("Real LLM smoke cases file contains no URL + goal cases.")
    return cases


def _llm_config_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "mode": "fake",
            "real_enabled": False,
            "config_source": str(path),
            "warnings": ["LLM local config does not exist."],
            "sensitive_values_redacted": True,
        }
    try:
        router = load_llm_router_config_from_file(path)
    except Exception as exc:
        return {
            "mode": "invalid",
            "real_enabled": False,
            "config_source": str(path),
            "warnings": [f"Failed to load LLM config: {type(exc).__name__}"],
            "sensitive_values_redacted": True,
        }
    provider = router.providers.get(router.default_provider)
    return {
        "mode": router.mode,
        "real_enabled": router.mode in {"real", "openai_compatible"}
        and provider is not None
        and provider.provider_type == "openai_compatible",
        "default_provider": router.default_provider,
        "model": provider.model if provider is not None else router.default_model,
        "provider_type": provider.provider_type if provider is not None else None,
        "config_source": str(path),
        "budget": router.budget,
        "warnings": [],
        "sensitive_values_redacted": True,
    }


def _artifact_status(run_dir: Path) -> dict[str, Any]:
    return {
        "run_dir_exists": run_dir.exists(),
        "final_report_md": (run_dir / "final_report.md").exists(),
        "evidence_jsonl": (run_dir / "evidence.jsonl").exists(),
        "evidence_jsonl_entries": _jsonl_count(run_dir / "evidence.jsonl"),
        "trace_jsonl": (run_dir / "trace.jsonl").exists(),
        "events_jsonl": (run_dir / "events.jsonl").exists(),
        "llm_calls_jsonl": (run_dir / "llm_calls.jsonl").exists(),
        "llm_call_count": _jsonl_count(run_dir / "llm_calls.jsonl"),
        "tool_audit_jsonl": (run_dir / "tool_audit.jsonl").exists(),
        "action_count": _jsonl_count(run_dir / "tool_audit.jsonl"),
    }


def _last_observation(run_dir: Path) -> tuple[str | None, str | None]:
    for row in reversed(_read_jsonl(run_dir / "trace.jsonl")):
        observation = row.get("observation")
        if isinstance(observation, dict):
            url = observation.get("url") or row.get("url_after")
            title = observation.get("title") or row.get("title")
            if url or title:
                return _str_or_none(url), _str_or_none(title)
        if row.get("url_after") or row.get("title"):
            return _str_or_none(row.get("url_after")), _str_or_none(row.get("title"))
    return None, None


def _jsonl_count(path: Path) -> int:
    return len(_read_jsonl(path))


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


def _safe_case_id(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_")[:80] or "case"


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
