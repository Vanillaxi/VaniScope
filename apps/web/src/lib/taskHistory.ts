import type { TaskStatus } from "@/lib/types";

export type TaskHistoryItem = {
  task_id: string;
  title: string;
  task_type: string;
  skill_id?: string | null;
  status: TaskStatus;
  created_at: string;
  last_opened_at: string;
};

const STORAGE_KEY = "vaniscope.console.taskHistory";
const MAX_HISTORY = 20;

export function loadTaskHistory(): TaskHistoryItem[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter(isTaskHistoryItem).slice(0, MAX_HISTORY) : [];
  } catch {
    return [];
  }
}

export function saveTaskHistory(items: TaskHistoryItem[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify(items.slice(0, MAX_HISTORY)),
  );
  window.dispatchEvent(new Event("vaniscope:task-history"));
}

export function upsertTaskHistory(item: TaskHistoryItem) {
  const current = loadTaskHistory().filter((entry) => entry.task_id !== item.task_id);
  saveTaskHistory(
    [item, ...current].sort(
      (left, right) =>
        new Date(right.last_opened_at).getTime() -
        new Date(left.last_opened_at).getTime(),
    ),
  );
}

export function updateTaskHistoryOpened(
  taskId: string,
  updates: Partial<TaskHistoryItem> = {},
) {
  const now = new Date().toISOString();
  const current = loadTaskHistory();
  const existing = current.find((entry) => entry.task_id === taskId);
  if (existing) {
    upsertTaskHistory({ ...existing, ...updates, last_opened_at: now });
  }
}

export function clearTaskHistory() {
  saveTaskHistory([]);
}

function isTaskHistoryItem(value: unknown): value is TaskHistoryItem {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return (
    typeof item.task_id === "string" &&
    typeof item.title === "string" &&
    typeof item.task_type === "string" &&
    typeof item.status === "string" &&
    typeof item.created_at === "string" &&
    typeof item.last_opened_at === "string"
  );
}
