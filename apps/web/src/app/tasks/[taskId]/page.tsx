"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import { ApprovalPanel } from "@/components/tasks/ApprovalPanel";
import { ArtifactList } from "@/components/tasks/ArtifactList";
import { ArtifactViewer } from "@/components/tasks/ArtifactViewer";
import { EvidencePanel } from "@/components/tasks/EvidencePanel";
import { LlmCallsPanel } from "@/components/tasks/LlmCallsPanel";
import { ReviewPanel } from "@/components/tasks/ReviewPanel";
import { RuntimeInspectorTabs } from "@/components/tasks/RuntimeInspectorTabs";
import { TaskStatusCard } from "@/components/tasks/TaskStatusCard";
import { TimelinePanel } from "@/components/tasks/TimelinePanel";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { getTask, getTaskInspector, listArtifacts } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { skillIdFromTask } from "@/lib/skills";
import { updateTaskHistoryOpened } from "@/lib/taskHistory";
import type {
  RuntimeInspectorResponse,
  TaskArtifactListResponse,
  TaskStatusResponse,
} from "@/lib/types";

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
  const [inspector, setInspector] = useState<RuntimeInspectorResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const [taskResult, artifactResult, inspectorResult]: [
        TaskStatusResponse,
        TaskArtifactListResponse,
        RuntimeInspectorResponse | null,
      ] = await Promise.all([
        getTask(taskId),
        listArtifacts(taskId).catch(() => ({ task_id: taskId, artifacts: [] })),
        getTaskInspector(taskId).catch(() => null),
      ]);
      setTask(taskResult);
      setArtifacts(artifactResult.artifacts);
      setInspector(inspectorResult);
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

  const latestTimelineItem = useMemo(
    () => inspector?.timeline_items.at(-1),
    [inspector?.timeline_items],
  );

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
        <TaskStatusCard
          task={task}
          latestEvent={
            latestTimelineItem
              ? {
                  event_id: latestTimelineItem.id,
                  task_id: taskId,
                  kind: latestTimelineItem.kind,
                  message: latestTimelineItem.title,
                  created_at: latestTimelineItem.timestamp ?? "",
                  payload: latestTimelineItem.raw,
                }
              : undefined
          }
        />
      ) : (
        <Card className="p-5 text-sm text-[var(--muted)]">{t.taskDetail.loading}</Card>
      )}
      <RuntimeInspectorTabs>
        {(activeTab) => {
          if (activeTab === "timeline") {
            return (
              <TimelinePanel
                items={inspector?.timeline_items ?? []}
                summary={inspector?.summary}
              />
            );
          }
          if (activeTab === "artifacts") {
            return (
              <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
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
            );
          }
          if (activeTab === "evidence") {
            return <EvidencePanel evidence={inspector?.evidence_links ?? []} />;
          }
          if (activeTab === "llm") {
            return (
              <LlmCallsPanel
                taskId={taskId}
                artifacts={artifacts}
                llmSummary={inspector?.llm_summary}
              />
            );
          }
          if (activeTab === "review") {
            return (
              <ReviewPanel
                taskId={taskId}
                artifacts={artifacts}
                reviewSummary={inspector?.review_summary}
              />
            );
          }
          return <ApprovalPanel taskId={taskId} onDecision={refresh} />;
        }}
      </RuntimeInspectorTabs>
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
