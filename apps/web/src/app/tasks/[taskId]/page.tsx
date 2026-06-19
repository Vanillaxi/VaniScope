"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import { ApprovalPanel } from "@/components/tasks/ApprovalPanel";
import { ArtifactList } from "@/components/tasks/ArtifactList";
import { ArtifactViewer } from "@/components/tasks/ArtifactViewer";
import { EventStreamPanel } from "@/components/tasks/EventStreamPanel";
import { TaskStatusCard } from "@/components/tasks/TaskStatusCard";
import { Card } from "@/components/ui/Card";
import { getTask, listArtifacts } from "@/lib/api";
import type { TaskArtifactListResponse, TaskEvent, TaskStatusResponse } from "@/lib/types";

type TaskPageProps = {
  params: Promise<{
    taskId: string;
  }>;
};

export default function TaskPage({ params }: TaskPageProps) {
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

  const latestEvent = useMemo(() => events.at(-1), [events]);

  if (error) {
    return (
      <Card className="p-5">
        <h1 className="text-xl font-semibold">任务不可用</h1>
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
        <Card className="p-5 text-sm text-[var(--muted)]">正在加载任务...</Card>
      )}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex flex-col gap-5">
          <EventStreamPanel taskId={taskId} onEventsChange={setEvents} />
          <Card className="p-5">
            <h2 className="mb-4 text-lg font-semibold">任务产物</h2>
            <ArtifactList
              artifacts={artifacts}
              selected={selectedArtifact}
              onSelect={setSelectedArtifact}
            />
          </Card>
          <ArtifactViewer taskId={taskId} artifactName={selectedArtifact} />
        </div>
        <ApprovalPanel taskId={taskId} onDecision={refresh} />
      </div>
    </>
  );
}
