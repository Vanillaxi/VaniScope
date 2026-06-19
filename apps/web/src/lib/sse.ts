import { API_BASE_URL } from "@/lib/api";
import type { TaskEvent } from "@/lib/types";

export function openTaskEventSource(
  taskId: string,
  onEvent: (event: TaskEvent) => void,
  onInvalidEvent: () => void,
  onError: (error: Event) => void,
) {
  const source = new EventSource(
    `${API_BASE_URL}/tasks/${encodeURIComponent(taskId)}/events`,
  );

  source.onmessage = (message) => handleMessage(message, onEvent, onInvalidEvent);

  const knownEvents = [
    "task_created",
    "task_started",
    "prompt_built",
    "planner_started",
    "planner_finished",
    "tool_call_started",
    "tool_call_finished",
    "evidence_added",
    "report_written",
    "report_generated",
    "review_finished",
    "workflow_started",
    "workflow_node_started",
    "workflow_node_finished",
    "workflow_finished",
    "workflow_failed",
    "approval_required",
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
    "recovery_finished",
    "recovery_succeeded",
    "recovery_failed",
    "recovery_blocked",
    "llm_review_started",
    "llm_review_finished",
    "revision_plan_created",
    "report_revised",
    "final_review_finished",
    "revise_loop_finished",
    "task_completed",
    "task_finished",
    "task_failed",
  ];

  for (const eventName of knownEvents) {
    source.addEventListener(eventName, (message) => {
      handleMessage(message as MessageEvent, onEvent, onInvalidEvent);
    });
  }

  source.onerror = onError;
  return source;
}

function handleMessage(
  message: MessageEvent,
  onEvent: (event: TaskEvent) => void,
  onInvalidEvent: () => void,
) {
  try {
    onEvent(JSON.parse(message.data) as TaskEvent);
  } catch {
    onInvalidEvent();
  }
}
