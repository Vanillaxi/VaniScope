from __future__ import annotations

from pydantic import BaseModel


class InteractiveElement(BaseModel):
    tag: str
    role: str | None = None
    name: str
    text: str
    locator_hint: str | None = None
    visible: bool
    enabled: bool
    bbox: dict[str, float] | None = None
    confidence: float


class RiskSignal(BaseModel):
    risk_type: str
    message: str
    severity: str


class PageObservation(BaseModel):
    url: str
    title: str
    visible_text_summary: str
    interactive_elements: list[InteractiveElement]
    risk_signals: list[RiskSignal]
    screenshot_path: str | None = None
