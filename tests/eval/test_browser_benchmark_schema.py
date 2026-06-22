from __future__ import annotations

from webscoper.schemas.eval import BrowserBenchmarkEvalCase, BrowserBenchmarkMetrics


def test_browser_benchmark_eval_case_schema_supports_webarena_style_fields() -> None:
    case = BrowserBenchmarkEvalCase(
        case_id="local_docs_001",
        site_type="local_fixture",
        start_url="tests/fixtures/mock_site/basic.html",
        goal="Find the quickstart install command.",
        allowed_domains=["localhost"],
        max_steps=5,
        success_criteria=[
            {"type": "content_appears", "value": "pip install playwright"},
            {"type": "evidence_exists", "value": "text_excerpt"},
        ],
        risk_policy="read_only",
    )

    assert case.case_id == "local_docs_001"
    assert case.success_criteria[0].type == "content_appears"
    assert BrowserBenchmarkMetrics(graph_artifact_rate=1.0).graph_artifact_rate == 1.0
