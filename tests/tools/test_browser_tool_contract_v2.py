from __future__ import annotations

from webscoper.runtime.llm.auto_explore import (
    decision_to_tool_call,
    parse_auto_explore_decision,
)
from webscoper.tools.registry import create_default_tool_registry


def test_browser_tool_descriptors_include_v2_metadata() -> None:
    registry = create_default_tool_registry()
    browser_open = registry.get("browser_open")
    assert browser_open is not None
    assert browser_open.input_schema["url"] == "string"
    assert browser_open.output_schema["final_url"] == "string"
    assert browser_open.public_web_allowed is True
    assert browser_open.produces_evidence is True
    assert browser_open.produces_screenshot is True
    assert browser_open.exposure == "core"
    assert browser_open.real_llm_prompt_allowed is True

    browser_type = registry.get("browser_type")
    assert browser_type is not None
    assert browser_type.risk_level == "sensitive"
    assert browser_type.public_web_allowed is False
    assert browser_type.can_mutate_page is True
    assert browser_type.exposure == "contextual"
    assert browser_type.public_web_exposure == "approval_required"

    upload = registry.get("browser_upload_file")
    assert upload is not None
    assert upload.enabled is False
    assert upload.public_web_allowed is False
    assert upload.exposure == "disabled"
    assert upload.real_llm_prompt_allowed is False

    compat = registry.get("browser_open_observe")
    assert compat is not None
    assert compat.exposure == "compatibility"
    assert compat.real_llm_prompt_allowed is False


def test_llm_action_aliases_map_to_v2_tool_ids() -> None:
    decision, record = parse_auto_explore_decision(
        '{"tool":"click","target_text":"Repositories"}',
    )

    assert decision is not None
    assert record["validation_status"] == "success"
    assert decision.action.type == "browser_click"
    assert decision_to_tool_call(decision, "call_001").tool_id == "browser_click"

    extract, _record = parse_auto_explore_decision(
        '{"action":"extract"}',
        user_goal="Summarize the profile.",
    )
    assert extract is not None
    assert extract.action.type == "browser_extract"
    assert decision_to_tool_call(extract, "call_002").tool_id == "browser_extract"
