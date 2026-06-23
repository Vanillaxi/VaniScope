from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BudgetContext(BaseModel):
    max_steps: int = 10
    timeout_ms: int = 10000
    retry_limit: int = 0
    max_cost_usd: float | None = None
    max_tool_calls: int = 50
    max_prompt_tokens_per_call: int = 12000
    max_prompt_tokens: int = 12000
    soft_prompt_tokens_per_task: int = 30000
    approval_prompt_tokens_per_task: int = 50000
    hard_prompt_tokens_per_task: int = 80000
    max_completion_tokens_per_call: int = 2048
    max_completion_tokens: int = 2048
    max_completion_tokens_per_task: int = 12000
    max_total_tokens_per_task: int = 50000
    max_llm_calls_per_task: int = 12
    soft_cost_usd_per_task: float = 0.15
    approval_cost_usd_per_task: float = 0.30
    hard_cost_usd_per_task: float = 0.60
    enable_budget_approval: bool = True
    enable_auto_compaction: bool = True
    timeout_seconds: int = 60
    llm_timeout_seconds: int = 60


class SafetyContext(BaseModel):
    mode: str = "read_only"
    allow_login: bool = False
    allow_captcha_bypass: bool = False
    allow_sensitive_input: bool = False
    allow_external_submit: bool = False


class VersionContext(BaseModel):
    runtime_version: str = "0.1.0"
    skill_version: str = "browser_runtime@0.1.0"
    prompt_version: str = "none"
    tool_schema_version: str = "browser_tools@0.1.0"
    review_policy_version: str = "none"
    eval_case_version: str | None = None
    model: str = "none"


class TraceContext(BaseModel):
    run_id: str
    run_dir: str
    trace_path: str | None = None
    transcript_path: str | None = None


class RuntimeState(BaseModel):
    status: str = "created"
    current_step: int = 0
    error_type: str | None = None
    error_message: str | None = None


class WebAgentContextSnapshot(BaseModel):
    task: Any
    trace: TraceContext
    version: VersionContext = Field(default_factory=VersionContext)
    budget: BudgetContext
    safety: SafetyContext
    state: RuntimeState = Field(default_factory=RuntimeState)


TaskEventKind = Literal[
    "task_created",
    "task_started",
    "task_succeeded",
    "task_blocked",
    "user_pause_requested",
    "user_resume_requested",
    "user_cancel_requested",
    "user_stop_requested",
    "task_canceled",
    "prompt_built",
    "planner_started",
    "planner_finished",
    "planner_action_selected",
    "llm_call_started",
    "llm_call_finished",
    "llm_action_proposed",
    "llm_action_validated",
    "llm_action_repaired",
    "llm_action_rejected",
    "tool_policy_checked",
    "risk_check_started",
    "risk_check_finished",
    "tool_call_started",
    "tool_call_finished",
    "executor_started",
    "executor_finished",
    "browser_open_started",
    "browser_open_finished",
    "browser_observe_finished",
    "navigation_started",
    "navigation_finished",
    "navigation_timeout",
    "url_changed",
    "readiness_wait_started",
    "readiness_sampled",
    "readiness_wait_finished",
    "readiness_timeout",
    "readiness_check",
    "action_precondition_checked",
    "action_started",
    "action_finished",
    "post_action_wait_started",
    "post_action_wait_finished",
    "effect_verification_started",
    "effect_verification_finished",
    "verifier_started",
    "verifier_finished",
    "evidence_added",
    "screenshot_evidence_added",
    "text_evidence_added",
    "report_generated",
    "report_written",
    "review_finished",
    "approval_required",
    "approval_resolved",
    "approval_decided",
    "langgraph_interrupted",
    "langgraph_resumed",
    "langgraph_resume_failed",
    "risk_blocked",
    "task_paused",
    "task_resumed",
    "task_rejected",
    "resume_failed",
    "recovery_started",
    "recovery_attempt_started",
    "recovery_attempt_finished",
    "recovery_succeeded",
    "recovery_finished",
    "recovery_failed",
    "recovery_blocked",
    "llm_review_started",
    "llm_review_finished",
    "revision_plan_created",
    "report_revised",
    "final_review_finished",
    "revise_loop_finished",
    "workflow_started",
    "workflow_node_started",
    "workflow_node_finished",
    "workflow_finished",
    "workflow_failed",
    "task_finished",
    "task_failed",
    "budget_exceeded",
    "budget_checked",
    "budget_warning",
    "budget_compaction_started",
    "budget_compaction_finished",
    "budget_approval_required",
    "budget_approval_resolved",
    "budget_hard_limit_exceeded",
    "partial_report_started",
    "partial_report_generated",
    "dry_run_completed",
]


class TaskEvent(BaseModel):
    event_id: str = ""
    task_id: str
    kind: TaskEventKind
    message: str
    created_at: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskEventStreamRecord(BaseModel):
    event: TaskEventKind
    data: TaskEvent


class AgentsMdInstruction(BaseModel):
    source_path: str
    content: str


class RuntimeReminder(BaseModel):
    message: str
    level: str = "info"
    source: str = "runtime"


class SkillPromptContext(BaseModel):
    skill_id: str
    name: str
    description: str
    version: str
    instruction: str
    plan: dict[str, Any] | None = None


class PromptBuildInput(BaseModel):
    identity: str
    task_summary: str
    safety_policy: str
    permission_mode: str
    skill: SkillPromptContext | None = None
    agents_md_instructions: list[AgentsMdInstruction] = Field(default_factory=list)
    runtime_reminders: list[RuntimeReminder] = Field(default_factory=list)


class PromptBuildResult(BaseModel):
    prompt_text: str
    prompt_preview_text: str | None = None
    sections: dict[str, str] = Field(default_factory=dict)
    loaded_agents_md_paths: list[str] = Field(default_factory=list)
    core_tool_ids: list[str] = Field(default_factory=list)
    lazy_tool_ids: list[str] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)
    hidden_tools: dict[str, str] = Field(default_factory=dict)
    disabled_tools: dict[str, str] = Field(default_factory=dict)
    skill: SkillPromptContext | None = None
    compact_context_metadata: dict[str, Any] | None = None


RiskLevel = Literal["safe", "sensitive", "dangerous", "blocked"]
RiskAction = Literal["allow", "require_approval", "block"]
ApprovalStatus = Literal["pending", "approved", "rejected"]
TaskPauseReason = Literal["approval_required"]


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
            "browser_scroll",
            "browser_wait",
            "browser_screenshot",
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


BudgetDecision = Literal[
    "allowed",
    "warning",
    "compaction_required",
    "approval_required",
    "hard_limit_exceeded",
    "denied",
]


class RiskCheckResult(BaseModel):
    allowed: bool
    requires_approval: bool
    blocked: bool
    risk_level: RiskLevel
    reason: str
    signals: list[RiskSignal] = Field(default_factory=list)
    approval_request_id: str | None = None


RiskDecision = RiskCheckResult


class PendingToolCall(BaseModel):
    pending_id: str = ""
    task_id: str
    approval_id: str
    tool_call_id: str | None = None
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str
    created_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskResumeResult(BaseModel):
    task_id: str
    approval_id: str
    resumed: bool
    status: str
    message: str
    error: str | None = None
