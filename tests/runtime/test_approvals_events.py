from __future__ import annotations

# From test_approval_store.py
import pytest

from webscoper.runtime.safety.approvals import ApprovalStore, ApprovalStoreError


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

# From test_pending_approvals.py
from webscoper.runtime.safety.pending import PendingApprovalManager


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

# From test_task_events.py
from pathlib import Path

from webscoper.runtime.execution.events import TaskEventStore
from webscoper.schemas.runtime import TaskEvent


def test_task_event_store_appends_and_lists_events(tmp_path: Path) -> None:
    store = TaskEventStore()

    first = store.append(
        TaskEvent(
            task_id="task_test",
            kind="task_started",
            message="Task started",
        )
    )
    second = store.append(
        TaskEvent(
            task_id="task_test",
            kind="prompt_built",
            message="Prompt built",
            payload={"ok": True},
        )
    )

    assert first.event_id == "evt_000001"
    assert second.event_id == "evt_000002"
    assert first.created_at
    assert store.list_events("task_test") == [first, second]

    output_path = tmp_path / "events.jsonl"
    store.write_jsonl("task_test", output_path)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "evt_000001" in lines[0]
