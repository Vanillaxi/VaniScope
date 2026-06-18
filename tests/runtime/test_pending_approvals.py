from __future__ import annotations

from webscoper.runtime.pending import PendingApprovalManager


def test_pending_approval_manager_create_get_pop_and_list() -> None:
    manager = PendingApprovalManager()

    pending = manager.create_pending_tool_call(
        task_id="task_test",
        approval_id="appr_000001",
        tool_name="browser_click_intent",
        arguments={"action": {"target_hint": "Submit"}},
        tool_call_id="call_001",
        reason="Submit requires approval.",
    )

    assert pending.pending_id == "pending_000001"
    assert manager.get_by_approval_id("appr_000001") == pending
    assert manager.list_for_task("task_test") == [pending]
    assert manager.pop_by_approval_id("appr_000001") == pending
    assert manager.get_by_approval_id("appr_000001") is None
    assert manager.pop_by_approval_id("appr_000001") is None
