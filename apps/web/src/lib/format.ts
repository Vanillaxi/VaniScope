import type { Language } from "@/lib/i18n";
import type { TaskStatus } from "@/lib/types";

export function statusTone(status: TaskStatus) {
  if (status === "succeeded" || status === "succeeded_partial") return "success";
  if (status === "failed" || status === "blocked" || status === "rejected" || status === "canceled") {
    return "danger";
  }
  if (
    status === "requires_approval" ||
    status === "waiting_for_approval" ||
    status === "resuming" ||
    status === "paused" ||
    status === "cancel_requested" ||
    status === "stop_requested"
  )
    return "warning";
  if (status === "running" || status === "created") return "info";
  return "neutral";
}

export function formatDateTime(
  value?: string | null,
  language: Language = "zh",
  fallback = language === "zh" ? "未知" : "Unknown",
) {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(language === "zh" ? "zh-CN" : "en-US");
}

export function formatArtifactContent(name: string, content: string) {
  if (name.endsWith(".json")) {
    return JSON.stringify(JSON.parse(content), null, 2);
  }
  if (name.endsWith(".jsonl")) {
    return content
      .split("\n")
      .filter(Boolean)
      .map((line) => {
        try {
          return JSON.stringify(JSON.parse(line), null, 2);
        } catch {
          return line;
        }
      })
      .join("\n\n");
  }
  return content;
}
