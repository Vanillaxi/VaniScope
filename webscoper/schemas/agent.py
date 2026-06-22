from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AutoExploreActionType = Literal[
    "browser_open",
    "browser_observe",
    "browser_click",
    "browser_type",
    "browser_select",
    "browser_scroll",
    "browser_wait",
    "browser_extract",
    "browser_screenshot",
    "ask_human",
    "finish_task",
]
AutoExploreEffectType = Literal[
    "content_or_url_changes",
    "content_appears",
    "url_contains",
    "none",
]
AutoExploreRiskLevel = Literal["read_only", "low", "medium", "high"]

FORBIDDEN_ACTION_PATTERNS = (
    "selector",
    "css=",
    "xpath",
    "//",
    "locator(",
    "click(",
    "evaluate(",
    "javascript:",
    "<script",
    "document.",
    "window.",
)


class AutoExploreExpectedEffect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AutoExploreEffectType = "none"
    value: str | None = None

    @field_validator("value")
    @classmethod
    def reject_automation_code(cls, value: str | None) -> str | None:
        if value is not None:
            _reject_forbidden_text(value, field_name="expected_effect.value")
        return value


class AutoExploreAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AutoExploreActionType
    url: str | None = None
    target_hint: str | None = None
    text: str | None = None
    option_text: str | None = None
    option_value: str | None = None
    direction: str | None = None
    amount: str | None = None
    condition: str | None = None
    value: str | None = None
    instruction: str | None = None
    summary_instruction: str | None = None
    expected_effect: AutoExploreExpectedEffect = Field(default_factory=AutoExploreExpectedEffect)
    risk_level: AutoExploreRiskLevel = "read_only"
    summary: str | None = None
    question: str | None = None

    @field_validator(
        "url",
        "target_hint",
        "text",
        "option_text",
        "option_value",
        "direction",
        "amount",
        "condition",
        "value",
        "instruction",
        "summary_instruction",
        "summary",
        "question",
    )
    @classmethod
    def reject_raw_automation(cls, value: str | None) -> str | None:
        if value is not None:
            _reject_forbidden_text(value, field_name="action text")
        return value

    @model_validator(mode="after")
    def validate_action_contract(self) -> "AutoExploreAction":
        if self.type == "browser_open" and not self.url:
            raise ValueError("browser_open requires url")
        if self.type == "browser_click" and not self.target_hint:
            raise ValueError("browser_click requires target_hint")
        if self.type == "browser_type" and (not self.target_hint or not self.text):
            raise ValueError("browser_type requires target_hint and text")
        if self.type == "browser_select" and not (
            self.target_hint and (self.option_text or self.option_value)
        ):
            raise ValueError("browser_select requires target_hint and option")
        if self.type == "browser_wait" and not self.condition:
            raise ValueError("browser_wait requires condition")
        if self.type == "browser_extract" and not self.instruction:
            raise ValueError("browser_extract requires instruction")
        if self.type != "browser_click" and self.target_hint:
            _reject_forbidden_text(self.target_hint, field_name="target_hint")
        return self


class AutoExploreDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning_summary: str
    action: AutoExploreAction

    @field_validator("reasoning_summary")
    @classmethod
    def reject_reasoning_automation(cls, value: str) -> str:
        _reject_forbidden_text(value, field_name="reasoning_summary")
        return value


def _reject_forbidden_text(value: str, *, field_name: str) -> None:
    normalized = value.lower()
    for pattern in FORBIDDEN_ACTION_PATTERNS:
        if pattern in normalized:
            raise ValueError(
                f"{field_name} contains forbidden raw automation pattern: {pattern}"
            )
