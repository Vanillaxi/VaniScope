import type { TaskStatus } from "@/lib/types";

export function statusTone(status: TaskStatus) {
  if (status === "succeeded") return "success";
  if (status === "failed" || status === "blocked" || status === "rejected") {
    return "danger";
  }
  if (status === "requires_approval" || status === "resuming") return "warning";
  if (status === "running") return "info";
  return "neutral";
}

export function statusLabel(status: TaskStatus) {
  const labels: Record<TaskStatus, string> = {
    running: "运行中",
    succeeded: "已成功",
    failed: "已失败",
    requires_approval: "等待审批",
    resuming: "恢复中",
    blocked: "已阻止",
    rejected: "已拒绝",
    not_found: "未找到",
  };
  return labels[status];
}

export function formatDateTime(value?: string | null) {
  if (!value) return "未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
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
