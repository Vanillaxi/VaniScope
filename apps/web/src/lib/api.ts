import type {
  ApprovalDecisionRequest,
  ApprovalDecisionResponse,
  ApprovalRequest,
  BackendPlannerMode,
  HealthResponse,
  PlannerMode,
  TaskArtifactContentResponse,
  TaskArtifactListResponse,
  TaskCreateApiRequest,
  TaskCreateRequest,
  TaskCreateResponse,
  TaskStatusResponse,
} from "@/lib/types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_VANISCOPE_API_BASE_URL ?? "http://localhost:8000";

function plannerToApiMode(planner: PlannerMode): BackendPlannerMode {
  return planner === "llm" ? "real_llm" : planner;
}

function compactPayload(payload: TaskCreateApiRequest) {
  return Object.fromEntries(
    Object.entries(payload).filter(([, value]) => value !== "" && value !== undefined),
  );
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getHealth() {
  return requestJson<HealthResponse>("/health", { cache: "no-store" });
}

export function createTask(payload: TaskCreateRequest) {
  return requestJson<TaskCreateResponse>("/tasks/async", {
    method: "POST",
    body: JSON.stringify(
      compactPayload({
        ...payload,
        planner: plannerToApiMode(payload.planner),
      }),
    ),
  });
}

export function getTask(taskId: string) {
  return requestJson<TaskStatusResponse>(`/tasks/${encodeURIComponent(taskId)}`, {
    cache: "no-store",
  });
}

export function listArtifacts(taskId: string) {
  return requestJson<TaskArtifactListResponse>(
    `/tasks/${encodeURIComponent(taskId)}/artifacts`,
    { cache: "no-store" },
  );
}

export function getArtifact(taskId: string, artifactName: string) {
  return requestJson<TaskArtifactContentResponse>(
    `/tasks/${encodeURIComponent(taskId)}/artifacts/${encodeURIComponent(artifactName)}`,
    { cache: "no-store" },
  );
}

export function listApprovals(taskId: string) {
  return requestJson<ApprovalRequest[]>(
    `/tasks/${encodeURIComponent(taskId)}/approvals`,
    { cache: "no-store" },
  );
}

export function getApproval(approvalId: string) {
  return requestJson<ApprovalRequest>(`/approvals/${encodeURIComponent(approvalId)}`, {
    cache: "no-store",
  });
}

export function submitApprovalDecision(
  approvalId: string,
  payload: ApprovalDecisionRequest,
) {
  return requestJson<ApprovalDecisionResponse>(
    `/approvals/${encodeURIComponent(approvalId)}/decision`,
    {
      method: "POST",
      body: JSON.stringify({
        decided_by: "console_user",
        ...payload,
      }),
    },
  );
}
