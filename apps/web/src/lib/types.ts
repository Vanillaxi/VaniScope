export type PlannerMode = "deterministic" | "fake_llm" | "llm";
export type BackendPlannerMode = "deterministic" | "fake_llm" | "real_llm";
export type TaskType = "browser_task" | "docs_research" | "github_issue_research";
export type SkillId = "auto" | "docs_research" | "github_issue_research";
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
  dry_run?: boolean;
  public_web_config?: string;
};

export type TaskCreateApiRequest = Omit<TaskCreateRequest, "planner"> & {
  planner: BackendPlannerMode;
};

export type TaskCreateResponse = {
  task_id: string;
  status: Exclude<TaskStatus, "not_found">;
  run_dir: string;
  artifacts: string[];
  skill_id?: string | null;
  task_type?: string | null;
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
  difficulty?: string | null;
  recommendation?: string | null;
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

export type DiagnosticsResponse = {
  status: string;
  service: string;
  runtime_backend: "langgraph";
  artifact_directory: Record<string, unknown>;
  llm: Record<string, unknown>;
  web: Record<string, unknown>;
  registered_skills: Record<string, unknown>[];
  browser: Record<string, unknown>;
  config: Record<string, unknown>;
};

export type RuntimeArtifactRef = {
  artifact_name: string;
  ref_id?: string | null;
  line?: number | null;
  path?: string | null;
};

export type ArtifactPresentation = {
  artifact_name: string;
  artifact_type: string;
  display_title: string;
  user_facing: boolean;
  developer_only: boolean;
  default_view: string;
  description?: string | null;
  priority: number;
};

export type RuntimeTimelineItem = {
  id: string;
  timestamp?: string | null;
  kind: string;
  category: string;
  title: string;
  summary?: string | null;
  status?: string | null;
  step_id?: string | null;
  tool_name?: string | null;
  evidence_ids: string[];
  artifact_refs: RuntimeArtifactRef[];
  raw_ref?: RuntimeArtifactRef | null;
  raw: Record<string, unknown>;
};

export type RuntimeInspectorSummary = {
  task_id: string;
  status?: string | null;
  artifact_count: number;
  timeline_count: number;
  evidence_count: number;
  llm_call_count: number;
  real_llm_call_count: number;
  approval_count: number;
  recovery_count: number;
  review_status?: string | null;
  budget_decisions: Record<string, number>;
  categories: Record<string, number>;
};

export type RuntimeEvidenceLink = {
  evidence_id: string;
  source_url?: string | null;
  page_title?: string | null;
  text_preview?: string | null;
  report_sections: string[];
  review_issue_ids: string[];
  raw: Record<string, unknown>;
};

export type RuntimeTimelineResponse = {
  task_id: string;
  summary: RuntimeInspectorSummary;
  timeline_items: RuntimeTimelineItem[];
};

export type RuntimeInspectorResponse = {
  task_id: string;
  status?: string | null;
  artifacts: string[];
  summary: RuntimeInspectorSummary;
  timeline_items: RuntimeTimelineItem[];
  evidence_links: RuntimeEvidenceLink[];
  task_summary: Record<string, unknown>;
  result_summary: Record<string, unknown>;
  report_summary: Record<string, unknown>;
  evidence_summary: Record<string, unknown>;
  review_summary: Record<string, unknown>;
  tool_summary: Record<string, unknown>;
  llm_summary: Record<string, unknown>;
  recovery_summary: Record<string, unknown>;
  approval_summary: Record<string, unknown>;
  artifact_presentations: ArtifactPresentation[];
};
