export type PlannerMode = "deterministic" | "fake_llm" | "llm";
export type BackendPlannerMode = "deterministic" | "fake_llm" | "real_llm";
export type TaskType = "browser_task" | "docs_research";
export type SkillId = "auto" | "docs_research";
export type TaskLanguage = "auto" | "zh" | "en";

export type TaskStatus =
  | "running"
  | "succeeded"
  | "failed"
  | "requires_approval"
  | "resuming"
  | "blocked"
  | "rejected"
  | "not_found";

export type TaskCreateRequest = {
  url: string;
  click?: string;
  expect?: string;
  task_type?: TaskType;
  skill_id?: Exclude<SkillId, "auto">;
  query?: string;
  research_goal?: string;
  language?: TaskLanguage;
  planner: PlannerMode;
  reminder?: string;
  workspace?: string;
  risk_mode?: string;
};

export type TaskCreateApiRequest = Omit<TaskCreateRequest, "planner"> & {
  planner: BackendPlannerMode;
};

export type TaskCreateResponse = {
  task_id: string;
  status: Exclude<TaskStatus, "not_found">;
  run_dir: string;
  artifacts: string[];
  error?: string | null;
};

export type TaskStatusResponse = {
  task_id: string;
  status: TaskStatus;
  run_dir?: string | null;
  artifacts: string[];
  error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  current_step?: number | null;
  current_phase?: string | null;
  skill_id?: string | null;
  task_type?: string | null;
  skill_status?: string | null;
};

export type TaskArtifactListResponse = {
  task_id: string;
  artifacts: string[];
};

export type TaskArtifactContentResponse = {
  task_id: string;
  artifact_name: string;
  content: string;
};

export type ApprovalDecision = {
  approved: boolean;
  decided_by: string;
  reason?: string | null;
  created_at?: string;
};

export type ApprovalRequest = {
  approval_id: string;
  task_id: string;
  status: "pending" | "approved" | "rejected";
  reason: string;
  risk_level: string;
  tool_name?: string | null;
  action_type?: string | null;
  target_hint?: string | null;
  created_at?: string;
  decided_at?: string | null;
  decision?: ApprovalDecision | null;
  metadata?: Record<string, unknown>;
};

export type ApprovalDecisionRequest = {
  approved: boolean;
  decided_by?: string;
  reason?: string;
};

export type ApprovalDecisionResponse = {
  approval: ApprovalRequest;
  resume_result?: unknown;
};

export type TaskEvent = {
  event_id: string;
  task_id: string;
  kind: string;
  message: string;
  created_at: string;
  payload: Record<string, unknown>;
};

export type HealthResponse = {
  status: string;
  service: string;
};
