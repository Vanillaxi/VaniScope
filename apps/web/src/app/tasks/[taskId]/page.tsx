"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import { ApprovalPanel } from "@/components/tasks/ApprovalPanel";
import { ArtifactList } from "@/components/tasks/ArtifactList";
import { ArtifactViewer } from "@/components/tasks/ArtifactViewer";
import { EventStreamPanel } from "@/components/tasks/EventStreamPanel";
import { TaskStatusCard } from "@/components/tasks/TaskStatusCard";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { getTask, listArtifacts } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { skillIdFromTask } from "@/lib/skills";
import { updateTaskHistoryOpened } from "@/lib/taskHistory";
import type { TaskArtifactListResponse, TaskEvent, TaskStatusResponse } from "@/lib/types";

type TaskPageProps = {
  params: Promise<{
    taskId: string;
  }>;
};

export default function TaskPage({ params }: TaskPageProps) {
  const { t } = useI18n();
  const { taskId } = use(params);
  const [task, setTask] = useState<TaskStatusResponse | null>(null);
  const [artifacts, setArtifacts] = useState<string[]>([]);
  const [selectedArtifact, setSelectedArtifact] = useState<string | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const [taskResult, artifactResult]: [
        TaskStatusResponse,
        TaskArtifactListResponse,
      ] = await Promise.all([
        getTask(taskId),
        listArtifacts(taskId).catch(() => ({ task_id: taskId, artifacts: [] })),
      ]);
      setTask(taskResult);
      setArtifacts(artifactResult.artifacts);
      setSelectedArtifact((current) => current ?? artifactResult.artifacts[0] ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [taskId]);

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    const interval = window.setInterval(() => void refresh(), 5000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(interval);
    };
  }, [refresh]);

  useEffect(() => {
    if (!task || task.status === "not_found") return;
    updateTaskHistoryOpened(taskId, {
      status: task.status,
      task_type: task.task_type ?? "browser_task",
      skill_id: task.skill_id,
      title: historyTitle(
        skillIdFromTask(task.task_type, task.skill_id),
        task.task_id,
      ),
    });
  }, [task, taskId]);

  const latestEvent = useMemo(() => events.at(-1), [events]);
  const hasFinalReport = artifacts.includes("final_report.md");

  if (error) {
    return (
      <Card className="p-5">
        <h1 className="text-xl font-semibold">{t.taskDetail.unavailable}</h1>
        <div className="mt-3 rounded-md border border-[#fecdca] bg-[#fef3f2] p-3 text-sm text-[var(--danger)]">
          {error}
        </div>
      </Card>
    );
  }

  return (
    <>
      {task ? (
        <TaskStatusCard task={task} latestEvent={latestEvent} />
      ) : (
        <Card className="p-5 text-sm text-[var(--muted)]">{t.taskDetail.loading}</Card>
      )}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex flex-col gap-5">
          <EventStreamPanel taskId={taskId} onEventsChange={setEvents} />
          <Card className="p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold">{t.taskDetail.artifacts}</h2>
              <Button variant="secondary" onClick={() => void refresh()}>
                {t.taskDetail.refreshArtifacts}
              </Button>
            </div>
            <ArtifactList
              artifacts={artifacts}
              selected={selectedArtifact}
              onSelect={setSelectedArtifact}
            />
          </Card>
          <ArtifactViewer taskId={taskId} artifactName={selectedArtifact} />
        </div>
        <aside className="flex flex-col gap-5">
          <ApprovalPanel taskId={taskId} onDecision={refresh} />
          {hasFinalReport ? (
            <ArtifactViewer
              taskId={taskId}
              artifactName="final_report.md"
              title={t.taskDetail.finalReportPreview}
              compact
            />
          ) : null}
        </aside>
      </div>
    </>
  );
}

function historyTitle(skillId: string, taskId: string) {
  const prefix =
    skillId === "docs_research"
      ? "Docs"
      : skillId === "github_issue_research"
        ? "Issue"
        : "Browser";
  return `${prefix}: ${taskId}`;
}
