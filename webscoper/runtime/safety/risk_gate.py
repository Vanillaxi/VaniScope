from __future__ import annotations

import json
from typing import Any

from webscoper.schemas.action import ActionContract
from webscoper.schemas.risk import RiskCheckResult, RiskPolicy, RiskSignal


class RiskGate:
    def __init__(self, policy: RiskPolicy | None = None) -> None:
        self.policy = policy or RiskPolicy()
        self._next_signal_id = 1

    def check_tool_call(
        self,
        task_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        page_observation: Any | None = None,
    ) -> RiskCheckResult:
        if tool_name in self.policy.read_only_tools:
            return _allowed("Read-only tool is allowed.")

        if tool_name == "browser_click_intent":
            action_payload = arguments.get("action")
            if isinstance(action_payload, dict):
                action = ActionContract.model_validate(action_payload)
                return self.check_action_contract(task_id, action, page_observation)

        action_text = _normalize_text([tool_name, json.dumps(arguments, default=str)])
        keyword_result = self._check_keywords(action_text, tool_name=tool_name)
        if keyword_result is not None:
            return keyword_result

        observation_result = self._check_page_observation(page_observation)
        if observation_result is not None:
            return observation_result

        if "submit" in tool_name or "external" in tool_name:
            return self._requires_approval(
                "External submit-like action requires approval.",
                [
                    self._signal(
                        "external_submit",
                        "Action may submit data outside the local page.",
                        source=tool_name,
                    )
                ],
            )

        return self._requires_approval(
            "Unknown non-read-only tool requires approval.",
            [
                self._signal(
                    "unknown_risk",
                    "Tool is not recognized as read-only.",
                    source=tool_name,
                )
            ],
        )

    def check_action_contract(
        self,
        task_id: str,
        action_contract: ActionContract,
        page_observation: Any | None = None,
    ) -> RiskCheckResult:
        action_text = _normalize_text(
            [
                action_contract.action_type,
                action_contract.intent,
                action_contract.target_hint,
            ]
        )
        keyword_result = self._check_keywords(
            action_text,
            tool_name="browser_click_intent",
            action_contract=action_contract,
        )
        if keyword_result is not None:
            return keyword_result

        observation_result = self._check_page_observation(page_observation)
        if observation_result is not None:
            return observation_result

        return _allowed("Browser action is allowed.")

    def _check_keywords(
        self,
        text: str,
        tool_name: str,
        action_contract: ActionContract | None = None,
    ) -> RiskCheckResult | None:
        for keyword in self.policy.block_keywords:
            if keyword in text:
                return self._blocked(
                    f"Action matched blocked keyword: {keyword}",
                    [
                        self._keyword_signal(
                            keyword,
                            source=tool_name,
                            action_contract=action_contract,
                        )
                    ],
                )

        for keyword in self.policy.approval_keywords:
            if keyword in text:
                return self._requires_approval(
                    f"Action matched approval keyword: {keyword}",
                    [
                        self._keyword_signal(
                            keyword,
                            source=tool_name,
                            action_contract=action_contract,
                        )
                    ],
                )

        return None

    def _check_page_observation(self, page_observation: Any | None) -> RiskCheckResult | None:
        signals = self._signals_from_observation(page_observation)
        if not signals:
            return None

        signal_kinds = {signal.kind for signal in signals}
        if signal_kinds & {"captcha_detected", "password_field", "payment_form"}:
            return self._blocked("Page contains blocking risk signals.", signals)
        if "login_required" in signal_kinds:
            return self._requires_approval("Page appears to require login.", signals)
        return None

    def _signals_from_observation(self, page_observation: Any | None) -> list[RiskSignal]:
        raw_signals = _get_value(page_observation, "risk_signals") or []
        signals: list[RiskSignal] = []
        for raw_signal in raw_signals:
            risk_type = str(_get_value(raw_signal, "risk_type") or "").lower()
            message = str(_get_value(raw_signal, "message") or "Page risk signal detected.")
            kind = {
                "captcha": "captcha_detected",
                "password": "password_field",
                "payment": "payment_form",
                "login": "login_required",
            }.get(risk_type)
            if kind is None:
                continue
            signals.append(
                self._signal(
                    kind,
                    message,
                    source="page_observation",
                    metadata={"risk_type": risk_type},
                )
            )
        return signals

    def _keyword_signal(
        self,
        keyword: str,
        source: str,
        action_contract: ActionContract | None = None,
    ) -> RiskSignal:
        kind = "unknown_risk"
        if keyword in {"delete", "remove", "删除", "移除"}:
            kind = "delete_action"
        elif keyword in {"publish", "post", "发布"}:
            kind = "publish_action"
        elif keyword in {"submit", "send", "confirm", "continue", "提交", "发送", "确认", "继续"}:
            kind = "external_submit"
        elif keyword in {"upload", "上传"}:
            kind = "file_upload"
        elif keyword in {"password", "密码"}:
            kind = "password_field"
        elif keyword in {"captcha", "验证码"}:
            kind = "captcha_detected"
        elif keyword in {"pay", "buy", "checkout", "支付", "购买"}:
            kind = "payment_form"
        elif keyword in {"login", "sign in", "logout", "登录", "登出"}:
            kind = "login_required"

        return self._signal(
            kind,
            f"Action text matched risk keyword: {keyword}",
            source=source,
            metadata={
                "keyword": keyword,
                "action_type": action_contract.action_type if action_contract else None,
                "target_hint": action_contract.target_hint if action_contract else None,
            },
        )

    def _signal(
        self,
        kind: str,
        message: str,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RiskSignal:
        signal = RiskSignal(
            signal_id=f"risk_{self._next_signal_id:06d}",
            kind=kind,
            message=message,
            source=source,
            metadata=_json_safe(metadata or {}),
        )
        self._next_signal_id += 1
        return signal

    def _requires_approval(
        self,
        reason: str,
        signals: list[RiskSignal],
    ) -> RiskCheckResult:
        return RiskCheckResult(
            allowed=False,
            requires_approval=True,
            blocked=False,
            risk_level="sensitive",
            reason=reason,
            signals=signals,
        )

    def _blocked(
        self,
        reason: str,
        signals: list[RiskSignal],
    ) -> RiskCheckResult:
        return RiskCheckResult(
            allowed=False,
            requires_approval=False,
            blocked=True,
            risk_level="blocked",
            reason=reason,
            signals=signals,
        )


def _allowed(reason: str) -> RiskCheckResult:
    return RiskCheckResult(
        allowed=True,
        requires_approval=False,
        blocked=False,
        risk_level="safe",
        reason=reason,
    )


def _normalize_text(parts: list[Any]) -> str:
    return " ".join(str(part or "").lower() for part in parts)


def _get_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))
