from __future__ import annotations

import pytest

from webscoper.runtime.approvals import ApprovalStore, ApprovalStoreError


def test_approval_store_create_list_get_and_decide() -> None:
    store = ApprovalStore()

    request = store.create_request(
        task_id="task_test",
        reason="Submit requires approval.",
        risk_level="sensitive",
        tool_name="browser_click_intent",
        action_type="click",
        target_hint="Submit",
    )

    assert request.approval_id == "appr_000001"
    assert request.status == "pending"
    assert store.get(request.approval_id) == request
    assert store.list_for_task("task_test") == [request]

    decided = store.decide(
        request.approval_id,
        approved=False,
        decided_by="local_user",
        reason="Reject in test.",
    )

    assert decided.status == "rejected"
    assert decided.decision is not None
    assert decided.decision.approved is False
    assert decided.decided_at


def test_approval_store_rejects_duplicate_decision() -> None:
    store = ApprovalStore()
    request = store.create_request(
        task_id="task_test",
        reason="Submit requires approval.",
        risk_level="sensitive",
    )

    store.decide(request.approval_id, approved=True)

    with pytest.raises(ApprovalStoreError, match="already decided"):
        store.decide(request.approval_id, approved=False)


def test_approval_store_missing_approval_is_clear() -> None:
    store = ApprovalStore()

    with pytest.raises(ApprovalStoreError, match="not found"):
        store.decide("appr_missing", approved=True)
