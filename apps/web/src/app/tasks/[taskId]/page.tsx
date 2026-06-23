"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import { InspectorDrawer } from "@/components/layout/InspectorDrawer";
import { ApprovalPanel } from "@/components/tasks/ApprovalPanel";
import { ArtifactList } from "@/components/tasks/ArtifactList";
import { ArtifactViewer } from "@/components/tasks/ArtifactViewer";
import { EvidencePanel } from "@/components/tasks/EvidencePanel";
import { ExecutionGraphPanel } from "@/components/tasks/ExecutionGraphPanel";
import { LlmCallsPanel } from "@/components/tasks/LlmCallsPanel";
import { RuntimeInspectorTabs } from "@/components/tasks/RuntimeInspectorTabs";
import { StepDetailPanel } from "@/components/tasks/StepDetailPanel";
import { TaskControlBar } from "@/components/tasks/TaskControlBar";
import { TimelinePanel } from "@/components/tasks/TimelinePanel";
import { ToolCatalogPanel } from "@/components/tasks/ToolCatalogPanel";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import {
  ApiRequestError,
  getTask,
  getTaskGraph,
  getTaskInspector,
  listArtifacts,
} from "@/lib/api";
import { formatDateTime, statusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { eventDisplay, statusLabel } from "@/lib/localizedDisplay";
import { skillIdFromTask } from "@/lib/skills";
import { updateTaskHistoryOpened } from "@/lib/taskHistory";
import type {
  RuntimeEvidenceLink,
  RuntimeInspectorResponse,
  RuntimeExecutionGraphResponse,
  RuntimeGraphNode,
  RuntimeTimelineItem,
  TaskArtifactListResponse,
  TaskStatusResponse,
} from "@/lib/types";

type TaskPageProps = {
  params: Promise<{
    taskId: string;
  }>;
};

export default function TaskPage({ params }: TaskPageProps) {
  const { language, t } = useI18n();
  const { taskId } = use(params);
  const [task, setTask] = useState<TaskStatusResponse | null>(null);
  const [artifacts, setArtifacts] = useState<string[]>([]);
  const [selectedArtifact, setSelectedArtifact] = useState<string | null>(null);
  const [inspector, setInspector] = useState<RuntimeInspectorResponse | null>(null);
  const [graph, setGraph] = useState<RuntimeExecutionGraphResponse | null>(null);
  const [error, setError] = useState<LoadError | null>(null);
  const [drawer, setDrawer] = useState<DrawerState>({ kind: "closed" });

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const [taskResult, artifactResult, inspectorResult, graphResult]: [
        TaskStatusResponse,
        TaskArtifactListResponse,
        RuntimeInspectorResponse | null,
        RuntimeExecutionGraphResponse | null,
      ] = await Promise.all([
        getTask(taskId),
        listArtifacts(taskId).catch(() => ({ task_id: taskId, artifacts: [] })),
        getTaskInspector(taskId).catch(() => null),
        getTaskGraph(taskId).catch(() => null),
      ]);
      setTask(taskResult);
      setArtifacts(artifactResult.artifacts);
      setInspector(inspectorResult);
      setGraph(graphResult);
      setSelectedArtifact((current) => current ?? artifactResult.artifacts[0] ?? null);
    } catch (reason) {
      setError(loadErrorFromReason(reason, t));
    }
  }, [taskId, t]);

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
        <h1 className="text-xl font-semibold">{error.title}</h1>
        <div className="mt-3 rounded-md border border-[#fecdca] bg-[#fef3f2] p-3 text-sm text-[var(--danger)]">
          <div>{error.message}</div>
          {error.hint ? <div className="mt-2 text-[#912018]">{error.hint}</div> : null}
        </div>
        <Button className="mt-4" variant="secondary" onClick={() => void refresh()}>
          {t.taskDetail.retry}
        </Button>
      </Card>
    );
  }

  if (task?.status === "not_found") {
    return (
      <Card className="p-5">
        <h1 className="text-xl font-semibold">{t.taskDetail.notFoundTitle}</h1>
        <div className="mt-3 rounded-md border border-dashed border-[var(--line)] p-5 text-sm leading-6 text-[var(--muted)]">
          {t.taskDetail.notFoundDescription}
        </div>
      </Card>
    );
  }

  return (
    <>
      {task ? (
        <TaskWorkspaceHeader
          task={task}
          latestItem={latestTimelineItem}
          onRefresh={refresh}
          onOpenDetails={() => setDrawer({ kind: "task" })}
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
                onInspectItem={(item) => setDrawer({ kind: "timeline", item })}
              />
            );
          }
          if (activeTab === "graph") {
            return (
              <ExecutionGraphPanel
                graph={graph}
                onInspectNode={(node) => setDrawer({ kind: "graph", node })}
              />
            );
          }
          if (activeTab === "overview") {
            return (
              <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
                <OverviewPanel
                  task={task}
                  inspector={inspector}
                  artifacts={artifacts}
                />
                <ApprovalPanel taskId={taskId} onDecision={refresh} />
              </div>
            );
          }
          if (activeTab === "report") {
            return artifacts.includes("final_report.md") ? (
              <ArtifactViewer taskId={taskId} artifactName="final_report.md" title={t.inspector.report} />
            ) : (
              <EmptyState title={t.inspector.report} message={t.inspector.reportUnavailable} />
            );
          }
          if (activeTab === "debug") {
            return (
              <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
                <Card className="p-5">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <h2 className="text-lg font-semibold">{t.inspector.debug}</h2>
                    <Button variant="secondary" onClick={() => void refresh()}>
                      {t.taskDetail.refreshArtifacts}
                    </Button>
                  </div>
                  <ArtifactList
                    artifacts={debugArtifacts(artifacts, inspector)}
                    selected={selectedArtifact}
                    onSelect={setSelectedArtifact}
                  />
                </Card>
                <ArtifactViewer
                  taskId={taskId}
                  artifactName={selectedArtifact ?? debugArtifacts(artifacts, inspector)[0]}
                  title={t.inspector.rawArtifacts}
                />
                <div className="xl:col-span-2">
                  <ToolCatalogPanel />
                </div>
              </div>
            );
          }
          if (activeTab === "evidence") {
            return (
              <EvidencePanel
                taskId={taskId}
                evidence={inspector?.evidence_links ?? []}
                onInspectEvidence={(item) => setDrawer({ kind: "evidence", item })}
              />
            );
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
          return null;
        }}
      </RuntimeInspectorTabs>
      <InspectorDrawer
        open={drawer.kind !== "closed"}
        title={drawerTitle(drawer, t)}
        subtitle={drawerSubtitle(drawer, language)}
        onClose={() => setDrawer({ kind: "closed" })}
      >
        {drawer.kind === "task" ? (
          <TaskMetadataInspector
            task={task}
            inspector={inspector}
            artifacts={artifacts}
          />
        ) : null}
        {drawer.kind === "timeline" ? (
          <StepDetailPanel
            taskId={taskId}
            item={drawer.item}
            evidence={inspector?.evidence_links ?? []}
            framed={false}
          />
        ) : null}
        {drawer.kind === "graph" ? (
          <StepDetailPanel
            taskId={taskId}
            node={drawer.node}
            evidence={inspector?.evidence_links ?? []}
            framed={false}
          />
        ) : null}
        {drawer.kind === "evidence" ? <EvidenceInspector item={drawer.item} /> : null}
      </InspectorDrawer>
    </>
  );
}

type DrawerState =
  | { kind: "closed" }
  | { kind: "task" }
  | { kind: "timeline"; item: RuntimeTimelineItem }
  | { kind: "graph"; node: RuntimeGraphNode }
  | { kind: "evidence"; item: RuntimeEvidenceLink };

function TaskWorkspaceHeader({
  task,
  latestItem,
  onRefresh,
  onOpenDetails,
}: {
  task: TaskStatusResponse;
  latestItem?: RuntimeTimelineItem;
  onRefresh: () => void;
  onOpenDetails: () => void;
}) {
  const { language, t } = useI18n();
  const stage = latestItem
    ? eventDisplay(latestItem, language).title
    : task.current_phase || t.status.waiting;
  return (
    <section className="rounded-lg border border-[var(--line)] bg-white px-4 py-3 shadow-sm">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-lg font-semibold">{compactTaskTitle(task)}</h1>
            <Badge tone={statusTone(task.status)}>{statusLabel(task.status, language)}</Badge>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--muted)]">
            <span>{task.task_type ?? "browser_task"}</span>
            {task.skill_id ? <span>{task.skill_id}</span> : null}
            <span>
              {t.status.currentPhase}: {stage}
            </span>
            <span>
              {t.status.updatedAt}: {formatDateTime(task.updated_at, language)}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <TaskControlBar task={task} onChanged={onRefresh} />
          <Button variant="secondary" className="min-h-8 px-3 text-xs" onClick={onOpenDetails}>
            {t.inspector.details}
          </Button>
        </div>
      </div>
    </section>
  );
}

function TaskMetadataInspector({
  task,
  inspector,
  artifacts,
}: {
  task: TaskStatusResponse | null;
  inspector: RuntimeInspectorResponse | null;
  artifacts: string[];
}) {
  const { language, t } = useI18n();
  const summary = inspector?.summary;
  if (!task) {
    return <div className="text-sm text-[var(--muted)]">{t.taskDetail.loading}</div>;
  }
  return (
    <div className="grid gap-4 text-sm">
      <InspectorMeta label={t.status.task} value={task.task_id} />
      <InspectorMeta label={t.status.taskType} value={task.task_type} />
      <InspectorMeta label={t.status.skillId} value={task.skill_id} />
      <InspectorMeta label={t.status.skillStatus} value={task.skill_status} />
      <InspectorMeta label={t.status.currentPhase} value={task.current_phase} />
      <InspectorMeta label={t.status.currentStep} value={String(task.current_step ?? "-")} />
      <InspectorMeta label={t.status.runDir} value={task.run_dir} />
      <InspectorMeta label={t.status.createdAt} value={formatDateTime(task.created_at, language)} />
      <InspectorMeta label={t.status.updatedAt} value={formatDateTime(task.updated_at, language)} />
      <InspectorMeta label={t.status.artifactCount} value={String(artifacts.length)} />
      <InspectorMeta label={t.status.difficulty} value={task.difficulty} />
      <InspectorMeta label={t.status.recommendation} value={task.recommendation} />
      <div className="grid grid-cols-2 gap-2 border-t border-[var(--line)] pt-4">
        <InspectorMetric label={t.inspector.evidence} value={String(summary?.evidence_count ?? 0)} />
        <InspectorMetric label={t.inspector.tools} value={String(inspector?.tool_summary?.total_calls ?? 0)} />
        <InspectorMetric label={t.inspector.llmPrompt} value={String(inspector?.llm_summary?.mode ?? "deterministic")} />
        <InspectorMetric label={t.inspector.review} value={String(summary?.review_status ?? "-")} />
      </div>
    </div>
  );
}

function EvidenceInspector({ item }: { item: RuntimeEvidenceLink }) {
  const { t } = useI18n();
  return (
    <div className="grid gap-4 text-sm">
      <InspectorMeta label={t.inspector.evidenceIds} value={item.evidence_id} />
      <InspectorMeta label={t.inspector.sourceUrl} value={item.source_url} />
      <InspectorMeta label={t.status.task} value={item.page_title} />
      <InspectorMeta label={t.inspector.reportSections} value={item.report_sections.join(", ")} />
      <InspectorMeta label={t.inspector.reviewIssues} value={item.review_issue_ids.join(", ")} />
      {item.text_preview ? (
        <div className="rounded-md bg-[var(--panel-soft)] p-3 leading-6 text-[#344054]">
          {item.text_preview}
        </div>
      ) : null}
      <div>
        <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
          {t.inspector.rawPayload}
        </div>
        <pre className="max-h-96 overflow-auto rounded-md bg-[#101828] p-3 text-xs leading-5 text-[#f8fafc]">
          {JSON.stringify(item.raw ?? {}, null, 2)}
        </pre>
      </div>
    </div>
  );
}

function InspectorMeta({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase text-[var(--muted)]">{label}</div>
      <div className="mt-1 break-words text-[#344054]">{value || "-"}</div>
    </div>
  );
}

function InspectorMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--line)] bg-[var(--panel-soft)] p-3">
      <div className="text-xs font-semibold uppercase text-[var(--muted)]">{label}</div>
      <div className="mt-1 font-semibold text-[#344054]">{value}</div>
    </div>
  );
}

function drawerTitle(drawer: DrawerState, t: ReturnType<typeof useI18n>["t"]) {
  if (drawer.kind === "task") return t.inspector.taskInfo;
  if (drawer.kind === "timeline") return t.inspector.eventDetail;
  if (drawer.kind === "graph") return t.inspector.nodeDetail;
  if (drawer.kind === "evidence") return t.inspector.evidence;
  return t.inspector.details;
}

function drawerSubtitle(drawer: DrawerState, language: "zh" | "en") {
  if (drawer.kind === "timeline") return eventDisplay(drawer.item, language).title;
  if (drawer.kind === "graph") return drawer.node.id;
  if (drawer.kind === "evidence") return drawer.item.evidence_id;
  return null;
}

function compactTaskTitle(task: TaskStatusResponse) {
  const prefix = task.skill_id || task.task_type || "task";
  const shortId = task.task_id.length > 28 ? `${task.task_id.slice(0, 28)}...` : task.task_id;
  return `${prefix}: ${shortId}`;
}

function OverviewPanel({
  task,
  inspector,
  artifacts,
}: {
  task: TaskStatusResponse | null;
  inspector: RuntimeInspectorResponse | null;
  artifacts: string[];
}) {
  const { language, t } = useI18n();
  const summary = inspector?.summary;
  const review = inspector?.review_summary ?? {};
  const tool = inspector?.tool_summary ?? {};
  const llm = inspector?.llm_summary ?? {};
  const approval = inspector?.approval_summary ?? {};
  const recovery = inspector?.recovery_summary ?? {};
  const report = inspector?.report_summary ?? {};

  return (
    <Card className="p-5">
      <h2 className="text-lg font-semibold">{t.inspector.overview}</h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <OverviewMetric label={t.status.task} value={statusLabel(task?.status, language)} />
        <OverviewMetric label={t.status.skillId} value={task?.skill_id ?? "-"} />
        <OverviewMetric label={t.status.taskType} value={task?.task_type ?? "-"} />
        <OverviewMetric label={t.inspector.evidence} value={String(summary?.evidence_count ?? 0)} />
        <OverviewMetric label={t.inspector.tools} value={String(tool.total_calls ?? 0)} />
        <OverviewMetric label={t.inspector.llmPrompt} value={String(llm.mode ?? "deterministic")} />
        <OverviewMetric label={t.inspector.review} value={String(review.status ?? summary?.review_status ?? "-")} />
        <OverviewMetric label={t.inspector.unsupportedClaims} value={String(review.unsupported_claim_count ?? 0)} />
        <OverviewMetric label={t.inspector.approval} value={String(approval.pending_count ?? 0)} />
        <OverviewMetric label={t.inspector.recovery} value={String(recovery.recovery_attempts ?? 0)} />
        <OverviewMetric label={t.status.artifactCount} value={String(artifacts.length)} />
        <OverviewMetric label={t.inspector.realCalls} value={String(llm.real_call_count ?? 0)} />
      </div>
      {typeof report.summary === "string" && report.summary ? (
        <div className="mt-5 rounded-md bg-[var(--panel-soft)] p-4 text-sm leading-7 text-[#344054]">
          {report.summary}
        </div>
      ) : null}
    </Card>
  );
}

function OverviewMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--line)] bg-white p-3">
      <div className="text-xs font-semibold uppercase text-[var(--muted)]">{label}</div>
      <div className="mt-1 break-words text-sm font-semibold text-[#344054]">{value || "-"}</div>
    </div>
  );
}

function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <Card className="p-5">
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="mt-4 rounded-md border border-dashed border-[var(--line)] p-5 text-sm text-[var(--muted)]">
        {message}
      </div>
    </Card>
  );
}

function debugArtifacts(
  artifacts: string[],
  inspector: RuntimeInspectorResponse | null,
) {
  const developer = inspector?.artifact_presentations
    ?.filter((item) => item.developer_only)
    .map((item) => item.artifact_name);
  const preferred = developer?.length
    ? developer
    : artifacts.filter((name) =>
        [
          "trace.jsonl",
          "transcript.jsonl",
          "events.jsonl",
          "prompt_context.json",
          "prompt_preview.md",
          "tool_audit.jsonl",
          "llm_calls.jsonl",
        ].includes(name),
      );
  return preferred.length ? preferred : artifacts;
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

type LoadError = {
  title: string;
  message: string;
  hint?: string;
};

function loadErrorFromReason(
  reason: unknown,
  t: ReturnType<typeof useI18n>["t"],
): LoadError {
  const message = reason instanceof Error ? reason.message : String(reason);
  if (reason instanceof ApiRequestError && reason.status === 404) {
    return {
      title: t.taskDetail.notFoundTitle,
      message,
      hint: t.taskDetail.notFoundDescription,
    };
  }
  return {
    title: t.taskDetail.loadFailedTitle,
    message,
    hint: t.taskDetail.loadFailedHint,
  };
}
