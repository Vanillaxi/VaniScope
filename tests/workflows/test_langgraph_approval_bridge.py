from __future__ import annotations

import json

from webscoper.runtime.safety.approvals import ApprovalStore
from webscoper.runtime.safety.pending import PendingApprovalManager
from webscoper.schemas.runtime import RiskCheckResult, RiskSignal
from webscoper.workflows.langgraph_approval import LangGraphApprovalBridge


def test_langgraph_approval_bridge_creates_json_safe_interrupt_payload() -> None:
    events: list[tuple[str, dict]] = []
    bridge = LangGraphApprovalBridge(
        ApprovalStore(),
        PendingApprovalManager(),
        event_sink=lambda kind, _message, payload: events.append((kind, payload)),
    )
    risk_result = RiskCheckResult(
        allowed=False,
        requires_approval=True,
        blocked=False,
        risk_level="sensitive",
        reason="Submit action requires approval.",
        signals=[
            RiskSignal(
                kind="external_submit",
                message="Submit-like action.",
                metadata={"values": {"Submit"}},
            )
        ],
    )

    payload = bridge.create_interrupt_payload(
        task_id="task_bridge",
        thread_id="task_bridge",
        tool_name="browser_click_intent",
        arguments={"action": {"action_type": "click", "target_hint": "Submit"}},
        risk_result=risk_result,
        node_name="execute_plan",
        tool_call_id="call_001",
    )

    assert payload["interrupt_id"] == "lg_interrupt_000001"
    assert payload["approval_id"] == "appr_000001"
    assert payload["thread_id"] == "task_bridge"
    assert payload["approval_request"]["metadata"]["workflow"] == "langgraph"
    assert [event[0] for event in events] == [
        "approval_required",
        "langgraph_interrupted",
        "task_paused",
    ]
    json.dumps(payload)


def test_langgraph_approval_bridge_reuses_pending_interrupt() -> None:
    bridge = LangGraphApprovalBridge(ApprovalStore(), PendingApprovalManager())
    risk_result = RiskCheckResult(
        allowed=False,
        requires_approval=True,
        blocked=False,
        risk_level="sensitive",
        reason="Submit action requires approval.",
    )

    first = bridge.create_interrupt_payload(
        task_id="task_bridge",
        thread_id="task_bridge",
        tool_name="browser_click_intent",
        arguments={"action": {"target_hint": "Submit"}},
        risk_result=risk_result,
    )
    second = bridge.create_interrupt_payload(
        task_id="task_bridge",
        thread_id="task_bridge",
        tool_name="browser_click_intent",
        arguments={"action": {"target_hint": "Submit"}},
        risk_result=risk_result,
    )

    assert second["interrupt_id"] == first["interrupt_id"]
    assert second["approval_id"] == first["approval_id"]
