"use client";

import { ArtifactViewer } from "@/components/tasks/ArtifactViewer";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { useI18n } from "@/lib/i18n";

type LlmCallsPanelProps = {
  taskId: string;
  artifacts: string[];
  llmSummary?: Record<string, unknown>;
};

export function LlmCallsPanel({ taskId, artifacts, llmSummary = {} }: LlmCallsPanelProps) {
  const { t } = useI18n();
  const callCount = numberValue(llmSummary.call_count);
  const realCallCount = numberValue(llmSummary.real_call_count);
  const modes = arrayValue(llmSummary.modes);
  const providers = arrayValue(llmSummary.providers);
  const hasPromptPreview = artifacts.includes("prompt_preview.md");
  const hasPromptContext = artifacts.includes("prompt_context.json");
  const hasLlmCalls = artifacts.includes("llm_calls.jsonl");

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="flex flex-col gap-5">
        {hasPromptPreview ? (
          <ArtifactViewer
            taskId={taskId}
            artifactName="prompt_preview.md"
            title={t.inspector.promptPreview}
          />
        ) : null}
        {hasPromptContext ? (
          <ArtifactViewer
            taskId={taskId}
            artifactName="prompt_context.json"
            title={t.inspector.promptContext}
          />
        ) : null}
        {hasLlmCalls ? (
          <ArtifactViewer
            taskId={taskId}
            artifactName="llm_calls.jsonl"
            title={t.artifacts.llmCalls}
          />
        ) : null}
      </div>
      <Card className="p-5">
        <h2 className="text-lg font-semibold">{t.inspector.llmPrompt}</h2>
        <div className="mt-4 grid gap-3 text-sm">
          <Meta label="Calls" value={String(callCount)} />
          <Meta label={t.inspector.realCalls} value={String(realCallCount)} />
          <Meta label={t.inspector.mode} value={modes.join(", ") || "deterministic"} />
          <Meta label={t.inspector.provider} value={providers.join(", ") || "fake"} />
          <Meta
            label={t.inspector.budget}
            value={JSON.stringify(llmSummary.budget_decisions ?? {})}
          />
        </div>
        {callCount === 0 ? (
          <div className="mt-4">
            <Badge tone="info">{t.inspector.noLlmCalls}</Badge>
          </div>
        ) : null}
      </Card>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase text-[var(--muted)]">{label}</div>
      <div className="mt-1 break-words text-[#344054]">{value || "-"}</div>
    </div>
  );
}

function numberValue(value: unknown) {
  return typeof value === "number" ? value : 0;
}

function arrayValue(value: unknown) {
  return Array.isArray(value) ? value.map(String) : [];
}
