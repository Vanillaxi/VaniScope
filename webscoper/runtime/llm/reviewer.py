from __future__ import annotations

import asyncio
import json
import re
from abc import ABC, abstractmethod
from typing import Any

from webscoper.runtime.llm.client import BaseLLMClient, OpenAICompatibleLLMClient
from webscoper.schemas.llm import LLMMessage, LLMRequest
from webscoper.schemas.revise import (
    LLMReviewFinding,
    LLMReviewRequest,
    LLMReviewResult,
)


class BaseLLMReportReviewer(ABC):
    @abstractmethod
    def review(self, request: LLMReviewRequest) -> LLMReviewResult:
        ...


class FakeLLMReportReviewer(BaseLLMReportReviewer):
    def review(self, request: LLMReviewRequest) -> LLMReviewResult:
        findings: list[LLMReviewFinding] = []
        deterministic_review = request.deterministic_review or {}
        issues = deterministic_review.get("issues")
        if not isinstance(issues, list):
            issues = []

        for issue in issues:
            if not isinstance(issue, dict):
                continue
            issue_type = str(issue.get("issue_type") or "unknown")
            severity = str(issue.get("severity") or "warning")
            if issue_type == "unsupported_claim":
                findings.append(
                    LLMReviewFinding(
                        severity=_severity(severity),
                        issue_type=issue_type,
                        message="A result claim is not supported by an evidence id.",
                        evidence_ids=_issue_evidence_ids(issue),
                        suggested_fix="Remove the claim or add a valid evidence reference.",
                        metadata={"deterministic_issue": issue},
                    )
                )
            elif issue_type == "missing_evidence_section":
                findings.append(
                    LLMReviewFinding(
                        severity=_severity(severity),
                        issue_type=issue_type,
                        message="The report is missing an Evidence section.",
                        suggested_fix="Add a ## Evidence section with available evidence ids.",
                        metadata={"deterministic_issue": issue},
                    )
                )
            elif issue_type == "missing_result_section":
                findings.append(
                    LLMReviewFinding(
                        severity=_severity(severity),
                        issue_type=issue_type,
                        message="The report is missing a Result section.",
                        suggested_fix="Add a concise ## Result section grounded in evidence.",
                        metadata={"deterministic_issue": issue},
                    )
                )
            elif issue_type == "missing_evidence_reference":
                findings.append(
                    LLMReviewFinding(
                        severity=_severity(severity),
                        issue_type=issue_type,
                        message=str(issue.get("message") or "Unknown evidence id."),
                        evidence_ids=_issue_evidence_ids(issue),
                        suggested_fix="Replace the unknown evidence id with an available evidence id.",
                        metadata={"deterministic_issue": issue},
                    )
                )

        if findings:
            score = max(0.0, round(1.0 - 0.15 * len(findings), 4))
            return LLMReviewResult(
                passed=not any(finding.severity == "error" for finding in findings),
                score=score,
                findings=findings,
                summary=f"Fake LLM reviewer found {len(findings)} issue(s).",
                raw_response=None,
                metadata={"mode": "fake_llm"},
            )

        return LLMReviewResult(
            passed=True,
            score=1.0,
            findings=[],
            summary="Fake LLM reviewer found no issues.",
            raw_response=None,
            metadata={"mode": "fake_llm"},
        )


class OpenAICompatibleLLMReportReviewer(BaseLLMReportReviewer):
    def __init__(
        self,
        client: BaseLLMClient,
        model: str = "none",
    ) -> None:
        self.client = client
        self.model = model

    def review(self, request: LLMReviewRequest) -> LLMReviewResult:
        llm_request = LLMRequest(
            model=self.model,
            temperature=0.0,
            max_tokens=1600,
            messages=[
                LLMMessage(
                    role="system",
                    content=(
                        "You are a strict evidence-aware report reviewer. "
                        "Return only JSON with keys passed, score, findings, summary."
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
                ),
            ],
            metadata={"task_id": request.task_id, "reviewer": "real_llm"},
        )

        try:
            response = _generate_sync(self.client, llm_request)
        except Exception as exc:
            return _parse_failure_result(
                raw_response=None,
                message=f"LLM reviewer request failed: {type(exc).__name__}: {exc}",
            )

        raw = response.content
        try:
            payload = _extract_json(raw)
            findings_payload = payload.get("findings", [])
            findings = [
                LLMReviewFinding.model_validate(item)
                for item in findings_payload
                if isinstance(item, dict)
            ]
            return LLMReviewResult(
                passed=bool(payload.get("passed", not findings)),
                score=float(payload.get("score", 1.0 if not findings else 0.7)),
                findings=findings,
                summary=str(payload.get("summary") or "LLM review completed."),
                raw_response=raw,
                metadata={"mode": "real_llm", "model": response.model},
            )
        except Exception as exc:
            return _parse_failure_result(
                raw_response=raw,
                message=f"LLM reviewer JSON parse failed: {type(exc).__name__}: {exc}",
            )


def _generate_sync(client: BaseLLMClient, request: LLMRequest):
    if isinstance(client, OpenAICompatibleLLMClient):
        return client._generate_sync(request)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(client.generate(request))
    raise RuntimeError("Synchronous LLM reviewer cannot run generic async client inside event loop.")


def _extract_json(value: str) -> dict[str, Any]:
    text = value.strip()
    fence = re.search(r"```(?:json)?\s*(?P<body>.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group("body").strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("LLM review JSON must be an object.")
    return payload


def _parse_failure_result(raw_response: str | None, message: str) -> LLMReviewResult:
    return LLMReviewResult(
        passed=False,
        score=0.0,
        findings=[
            LLMReviewFinding(
                severity="error",
                issue_type="llm_review_parse_failed",
                message=message,
                suggested_fix="Retry with a reviewer that returns valid JSON.",
            )
        ],
        summary=message,
        raw_response=raw_response,
        metadata={"mode": "real_llm", "error": True},
    )


def _severity(value: str) -> str:
    return value if value in {"info", "warning", "error"} else "warning"


def _issue_evidence_ids(issue: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    evidence_id = issue.get("evidence_id")
    if evidence_id:
        ids.append(str(evidence_id))
    metadata = issue.get("metadata")
    if isinstance(metadata, dict):
        claim = metadata.get("claim")
        if isinstance(claim, str):
            ids.extend(sorted(set(re.findall(r"\bev_\d{6}\b", claim))))
    return sorted(set(ids))
