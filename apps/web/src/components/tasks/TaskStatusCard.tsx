"use client";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { formatDateTime, statusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { TaskEvent, TaskStatusResponse } from "@/lib/types";

type TaskStatusCardProps = {
  task: TaskStatusResponse;
  latestEvent?: TaskEvent;
};

export function TaskStatusCard({ task, latestEvent }: TaskStatusCardProps) {
  const { language, t } = useI18n();
  const phase =
    latestEvent?.payload?.phase?.toString() ??
    task.current_phase ??
    latestEvent?.kind ??
    (task.status === "not_found" ? t.status.missing : t.status.waiting);

  return (
    <Card className="p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="text-sm font-medium text-[var(--muted)]">{t.status.task}</div>
          <h1 className="mt-1 break-words text-2xl font-semibold">{task.task_id}</h1>
        </div>
        <Badge tone={statusTone(task.status)}>{t.status[task.status]}</Badge>
      </div>
      <dl className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            {t.status.currentPhase}
          </dt>
          <dd className="mt-1 break-words text-sm">{phase}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            {t.status.updatedAt}
          </dt>
          <dd className="mt-1 text-sm">
            {formatDateTime(task.updated_at ?? latestEvent?.created_at, language)}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            {t.status.currentStep}
          </dt>
          <dd className="mt-1 text-sm">{task.current_step ?? t.status.unknown}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            {t.status.runDir}
          </dt>
          <dd className="mt-1 break-words text-sm">{task.run_dir ?? t.status.unknown}</dd>
        </div>
      </dl>
      <dl className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            {t.status.createdAt}
          </dt>
          <dd className="mt-1 text-sm">{formatDateTime(task.created_at, language)}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            {t.status.artifactCount}
          </dt>
          <dd className="mt-1 text-sm">{task.artifacts.length}</dd>
        </div>
      </dl>
      <dl className="mt-4 grid gap-4 sm:grid-cols-3">
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            {t.status.taskType}
          </dt>
          <dd className="mt-1 break-words text-sm">
            {task.task_type ?? t.status.unknown}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            {t.status.skillId}
          </dt>
          <dd className="mt-1 break-words text-sm">
            {task.skill_id ?? t.status.unknown}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            {t.status.skillStatus}
          </dt>
          <dd className="mt-1 break-words text-sm">
            {task.skill_status ?? t.status.unknown}
          </dd>
        </div>
      </dl>
      <dl className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            {t.status.difficulty}
          </dt>
          <dd className="mt-1 break-words text-sm">
            {task.difficulty ?? t.status.unknown}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            {t.status.recommendation}
          </dt>
          <dd className="mt-1 break-words text-sm">
            {task.recommendation ?? t.status.unknown}
          </dd>
        </div>
      </dl>
      {task.error ? (
        <div className="mt-5 rounded-md border border-[#fecdca] bg-[#fef3f2] p-3 text-sm text-[var(--danger)]">
          <div className="font-semibold">
            {publicWebBlocked(task.error)
              ? "Blocked by public web policy"
              : t.taskDetail.failureReason}
          </div>
          <div className="mt-1 break-words text-[#912018]">{friendlyTaskError(task.error)}</div>
        </div>
      ) : null}
    </Card>
  );
}

function friendlyTaskError(error: string) {
  if (!error) return "";
  if (publicWebBlocked(error)) {
    const detail = error.replace(/^.*PUBLIC_WEB_BLOCKED:\s*/s, "").trim();
    const hints = [];
    if (error.includes("disabled")) {
      hints.push("Enable public web mode in configs/runtime.local.toml and restart the API.");
    }
    if (error.includes("not in allowed_domains")) {
      hints.push(
        "Add this domain to allowed_domains or use public_open for local manual exploration.",
      );
    }
    return [detail || "Public web navigation was blocked.", ...hints].join(" ");
  }
  if (error.includes("Task not found")) return "The task run could not be found.";
  if (error.includes("approval")) return error;
  if (error.includes("LangGraph workflow completed without a final observation")) {
    return "The workflow ended before producing a final browser observation. Check Timeline and Debug artifacts for the last runtime step.";
  }
  return error;
}

function publicWebBlocked(error: string) {
  return error.includes("PUBLIC_WEB_BLOCKED") || error.includes("public web policy");
}
