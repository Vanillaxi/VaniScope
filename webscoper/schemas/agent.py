from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from webscoper.schemas.browser import ExpectedEffect


AutoExploreActionType = Literal[
    "observe",
    "click_intent",
    "extract",
    "ask_human",
    "finish",
]


class AutoExploreAction(BaseModel):
    type: AutoExploreActionType
    target_hint: str | None = None
    expected_effect: ExpectedEffect = Field(default_factory=ExpectedEffect)
    risk_level: str = "read_only"
    summary: str | None = None
    question: str | None = None


class AutoExploreDecision(BaseModel):
    reasoning_summary: str
    action: AutoExploreAction
