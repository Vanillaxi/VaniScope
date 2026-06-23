from __future__ import annotations

from webscoper.api.runner_factory import build_api_task
from webscoper.api.schemas import TaskCreateRequest
from webscoper.runtime.artifacts.report import FinalReportBuilder
from webscoper.schemas.artifact import EvidenceItem
from webscoper.schemas.browser import PageObservation
from webscoper.schemas.task import TaskSpec


def test_chinese_goal_sets_requested_output_language() -> None:
    task = build_api_task(
        "task_lang",
        TaskCreateRequest(
            url="https://github.com/Vanillaxi",
            goal="总结一下这个用户的资料，用中文回答",
            mode="auto_explore",
            language="auto",
            display_language="en-US",
        ),
    )

    assert task.display_language == "en-US"
    assert task.requested_output_language == "zh-CN"
    assert task.report_language == "zh-CN"
    assert task.language == "zh-CN"


def test_chinese_report_uses_localized_headings_and_synthesizes_evidence() -> None:
    task = TaskSpec(
        task_id="task_report_zh",
        raw_input="总结一下这个用户的资料，用中文回答",
        target_url="https://github.com/Vanillaxi",
        goal="总结一下这个用户的资料，用中文回答",
        display_language="en-US",
        requested_output_language="zh-CN",
        report_language="zh-CN",
        language="zh-CN",
    )
    evidence = [
        EvidenceItem(
            evidence_id="ev_000001",
            kind="page_observation",
            source_url="https://github.com/Vanillaxi",
            page_title="Vanillaxi - GitHub",
            text=(
                "Vanillaxi ヴァニラシ Guangzhou 11 followers 47 following "
                "apache/dubbo-go incubator-seata-go dubbo-go-pixiu MemoryFlow"
            ),
            created_at="2026-01-01T00:00:00+00:00",
        )
    ]
    observation = PageObservation(
        url="https://github.com/Vanillaxi",
        title="Vanillaxi - GitHub",
        visible_text_summary="Skip to content Navigation Menu Platform Solutions Open Source",
        interactive_elements=[],
        risk_signals=[],
    )

    report = FinalReportBuilder().build_markdown(task, evidence, observation)

    assert "# VaniScope 任务报告" in report
    assert "## 核心结论" in report
    assert "## 证据链" in report
    assert "VaniScope Task Report" not in report
    assert "visible text:" not in report
    assert "[ev_000001]" in report


def test_english_report_keeps_english_headings() -> None:
    task = TaskSpec(
        task_id="task_report_en",
        raw_input="Summarize this user in English",
        target_url="https://github.com/Vanillaxi",
        goal="Summarize this user in English",
        display_language="zh-CN",
        requested_output_language="en-US",
        report_language="en-US",
        language="en-US",
    )
    report = FinalReportBuilder().build_markdown(task, [], None)

    assert "# VaniScope Task Report" in report
    assert "## Key Findings" in report
    assert "VaniScope 任务报告" not in report


def test_docs_research_chinese_report_uses_chinese_labels() -> None:
    task = TaskSpec(
        task_id="task_docs_zh",
        raw_input="如何安装并运行 VaniScope？",
        target_url="file:///tmp/docs.html",
        task_type="docs_research",
        skill_id="docs_research",
        query="如何安装并运行 VaniScope？",
        expected_output="安装步骤",
        language="zh-CN",
        report_language="zh-CN",
    )
    evidence = [
        EvidenceItem(
            evidence_id="ev_000001",
            kind="text_excerpt",
            source_url="file:///tmp/docs.html",
            page_title="VaniScope Docs",
            text="Install with uv sync. Start API with uv run python scripts/run_api.py.",
            created_at="2026-01-01T00:00:00+00:00",
        )
    ]

    report = FinalReportBuilder().build_markdown(task, evidence, None)

    assert "任务 ID" in report
    assert "技能 ID" in report
    assert "查询" in report
    assert "页面标题" in report
    assert "证据链" in report
    assert "task_id:" not in report
    assert "page_title:" not in report


def test_github_issue_chinese_report_uses_chinese_evidence_labels() -> None:
    task = TaskSpec(
        task_id="task_issue_zh",
        raw_input="分析这个 issue 是否值得做，并总结难度、影响模块和风险。",
        target_url="file:///tmp/issue.html",
        task_type="github_issue_research",
        skill_id="github_issue_research",
        query="分析这个 issue 是否值得做，并总结难度、影响模块和风险。",
        language="zh-CN",
        report_language="zh-CN",
    )
    evidence = [
        EvidenceItem(
            evidence_id="ev_000001",
            kind="page_observation",
            source_url="file:///tmp/issue.html",
            page_title="Issue",
            text=(
                "Repository: apache/dubbo-go\n"
                "Issue: Avoid URL clone allocations\n"
                "Issue Number: #4821\n"
                "Labels\n- performance\n"
                "Affected Modules\n- common/url.go\n"
                "Acceptance Criteria\n- Add benchmark coverage\n"
                "Suggested Implementation\n- Update common/url_test.go"
            ),
            created_at="2026-01-01T00:00:00+00:00",
        )
    ]

    report = FinalReportBuilder().build_markdown(task, evidence, None)

    assert "任务 ID" in report
    assert "查询" in report
    assert "页面标题" in report
    assert "仓库" in report
    assert "标签" in report
    assert "证据：" in report
    assert "Issue title:" not in report
    assert "Labels:" not in report
    assert "Evidence:" not in report
    assert "task_id:" not in report
    assert "page_title:" not in report
