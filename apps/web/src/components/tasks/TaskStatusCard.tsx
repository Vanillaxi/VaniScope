import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { formatDateTime, statusLabel, statusTone } from "@/lib/format";
import type { TaskEvent, TaskStatusResponse } from "@/lib/types";

type TaskStatusCardProps = {
  task: TaskStatusResponse;
  latestEvent?: TaskEvent;
};

export function TaskStatusCard({ task, latestEvent }: TaskStatusCardProps) {
  const phase =
    latestEvent?.payload?.phase?.toString() ??
    task.current_phase ??
    latestEvent?.kind ??
    (task.status === "not_found" ? "缺失" : "等待中");

  return (
    <Card className="p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="text-sm font-medium text-[var(--muted)]">任务</div>
          <h1 className="mt-1 break-words text-2xl font-semibold">{task.task_id}</h1>
        </div>
        <Badge tone={statusTone(task.status)}>{statusLabel(task.status)}</Badge>
      </div>
      <dl className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            当前阶段
          </dt>
          <dd className="mt-1 break-words text-sm">{phase}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            更新时间
          </dt>
          <dd className="mt-1 text-sm">
            {formatDateTime(task.updated_at ?? latestEvent?.created_at)}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            当前步骤
          </dt>
          <dd className="mt-1 text-sm">{task.current_step ?? "未知"}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            运行目录
          </dt>
          <dd className="mt-1 break-words text-sm">{task.run_dir ?? "未知"}</dd>
        </div>
      </dl>
      <dl className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            创建时间
          </dt>
          <dd className="mt-1 text-sm">{formatDateTime(task.created_at)}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase text-[var(--muted)]">
            产物数量
          </dt>
          <dd className="mt-1 text-sm">{task.artifacts.length}</dd>
        </div>
      </dl>
      {task.error ? (
        <div className="mt-5 rounded-md border border-[#fecdca] bg-[#fef3f2] p-3 text-sm text-[var(--danger)]">
          {task.error}
        </div>
      ) : null}
    </Card>
  );
}
