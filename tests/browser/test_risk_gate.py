from __future__ import annotations

from webscoper.runtime.safety.risk_gate import RiskGate
from webscoper.schemas.browser import ActionContract


def test_risk_gate_allows_safe_browser_open() -> None:
    result = RiskGate().check_tool_call(
        task_id="task_test",
        tool_name="browser_open_observe",
        arguments={"url": "file:///tmp/example.html"},
    )

    assert result.allowed
    assert result.risk_level == "safe"


def test_risk_gate_requires_approval_for_submit_click() -> None:
    result = RiskGate().check_action_contract(
        task_id="task_test",
        action_contract=_action("Submit"),
    )

    assert result.requires_approval
    assert not result.allowed
    assert result.signals[0].kind == "external_submit"


def test_risk_gate_blocks_dangerous_click_intents() -> None:
    cases = [
        ("Delete account", "delete_action"),
        ("Pay now", "payment_form"),
    ]

    for target_hint, signal_kind in cases:
        result = RiskGate().check_action_contract(
            task_id="task_test",
            action_contract=_action(target_hint),
        )
        assert result.blocked
        assert result.signals[0].kind == signal_kind


def test_risk_gate_blocks_password_and_captcha_page_signals() -> None:
    password_result = RiskGate().check_action_contract(
        task_id="task_test",
        action_contract=_action("Profile"),
        page_observation={
            "risk_signals": [
                {
                    "risk_type": "password",
                    "message": "Page contains password input fields.",
                }
            ]
        },
    )
    captcha_result = RiskGate().check_action_contract(
        task_id="task_test",
        action_contract=_action("Profile"),
        page_observation={
            "risk_signals": [
                {
                    "risk_type": "captcha",
                    "message": "Page contains captcha.",
                }
            ]
        },
    )

    assert password_result.blocked
    assert password_result.signals[0].kind == "password_field"
    assert captcha_result.blocked
    assert captcha_result.signals[0].kind == "captcha_detected"


def _action(target_hint: str) -> ActionContract:
    return ActionContract(
        action_type="click",
        intent=f"Click {target_hint}",
        target_hint=target_hint,
        preferred_roles=["button"],
        risk_level="read_only",
    )
