import type {
  ApprovalDecisionRequest,
  ApprovalDecisionResponse,
  ApprovalRequest,
  BackendPlannerMode,
  DiagnosticsResponse,
  HealthResponse,
  PlannerMode,
  RuntimeInspectorResponse,
  RuntimeTimelineResponse,
  TaskArtifactContentResponse,
  TaskArtifactListResponse,
  TaskCreateApiRequest,
  TaskCreateRequest,
  TaskCreateResponse,
  TaskStatusResponse,
} from "@/lib/types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_VANISCOPE_API_BASE_URL ?? "http://localhost:8000";

export class ApiRequestError extends Error {
  status?: number;
  detail?: unknown;

  constructor(message: string, status?: number, detail?: unknown) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.detail = detail;
  }
}

function plannerToApiMode(planner: PlannerMode): BackendPlannerMode {
  return planner === "llm" ? "real_llm" : planner;
}

function compactPayload(payload: TaskCreateApiRequest) {
  return Object.fromEntries(
    Object.entries(payload).filter(([, value]) => value !== "" && value !== undefined),
  );
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch (reason) {
    throw new ApiRequestError(
      `Cannot connect to VaniScope API at ${API_BASE_URL}. Start the FastAPI server with "uv run python scripts/run_api.py". Details: ${
        reason instanceof Error ? reason.message : String(reason)
      }`,
    );
  }

  if (!response.ok) {
    const body = await response.text();
    const detail = parseApiErrorDetail(body);
    throw new ApiRequestError(formatApiError(response.status, body), response.status, detail);
  }

  return response.json() as Promise<T>;
}

function formatApiError(status: number, body: string) {
  if (!body) return `Request failed: HTTP ${status}`;
  const detail = parseApiErrorDetail(body);
  if (typeof detail === "string") return `Request failed: HTTP ${status} - ${detail}`;
  if (detail) return `Request failed: HTTP ${status} - ${JSON.stringify(detail)}`;
  return `Request failed: HTTP ${status} - ${body}`;
}

function parseApiErrorDetail(body: string) {
  if (!body) return null;
  try {
    const parsed = JSON.parse(body) as { detail?: unknown; message?: unknown };
    return parsed.detail ?? parsed.message ?? parsed;
  } catch {
    return body;
  }
}

export function getHealth() {
  return requestJson<HealthResponse>("/health", { cache: "no-store" });
}

export function getDiagnostics() {
  return requestJson<DiagnosticsResponse>("/diagnostics", { cache: "no-store" });
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

export function getTaskTimeline(taskId: string) {
  return requestJson<RuntimeTimelineResponse>(
    `/tasks/${encodeURIComponent(taskId)}/timeline`,
    { cache: "no-store" },
  );
}

export function getTaskInspector(taskId: string) {
  return requestJson<RuntimeInspectorResponse>(
    `/tasks/${encodeURIComponent(taskId)}/inspector`,
    { cache: "no-store" },
  );
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
