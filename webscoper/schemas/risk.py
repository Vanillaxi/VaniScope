from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["safe", "sensitive", "dangerous", "blocked"]
RiskAction = Literal["allow", "require_approval", "block"]
ApprovalStatus = Literal["pending", "approved", "rejected"]


RiskSignalKind = Literal[
    "login_required",
    "captcha_detected",
    "password_field",
    "payment_form",
    "pii_field",
    "delete_action",
    "publish_action",
    "external_submit",
    "file_upload",
    "unknown_risk",
]


class RiskSignal(BaseModel):
    signal_id: str = ""
    kind: RiskSignalKind
    message: str
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskPolicy(BaseModel):
    read_only_tools: set[str] = Field(
        default_factory=lambda: {
            "browser_open",
            "browser_observe",
            "browser_open_observe",
            "browser_extract",
            "finish_task",
        }
    )
    approval_keywords: list[str] = Field(
        default_factory=lambda: [
            "submit",
            "send",
            "publish",
            "post",
            "upload",
            "confirm",
            "continue",
            "login",
            "sign in",
            "logout",
            "提交",
            "发送",
            "发布",
            "上传",
            "确认",
            "继续",
            "登录",
            "登出",
        ]
    )
    block_keywords: list[str] = Field(
        default_factory=lambda: [
            "delete",
            "remove",
            "pay",
            "buy",
            "checkout",
            "password",
            "captcha",
            "删除",
            "移除",
            "支付",
            "购买",
            "密码",
            "验证码",
        ]
    )


class ApprovalDecision(BaseModel):
    approved: bool
    decided_by: str
    reason: str | None = None
    created_at: str = ""


class ApprovalRequest(BaseModel):
    approval_id: str = ""
    task_id: str
    status: ApprovalStatus = "pending"
    reason: str
    risk_level: str
    tool_name: str | None = None
    action_type: str | None = None
    target_hint: str | None = None
    created_at: str = ""
    decided_at: str | None = None
    decision: ApprovalDecision | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskCheckResult(BaseModel):
    allowed: bool
    requires_approval: bool
    blocked: bool
    risk_level: RiskLevel
    reason: str
    signals: list[RiskSignal] = Field(default_factory=list)
    approval_request_id: str | None = None


RiskDecision = RiskCheckResult
