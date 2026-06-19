"use client";

import { useEffect, useState } from "react";
import { ArtifactRenderer } from "@/components/tasks/artifacts/ArtifactRenderer";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { getArtifact } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type ArtifactViewerProps = {
  taskId: string;
  artifactName?: string | null;
  title?: string;
  compact?: boolean;
};

const MAX_ARTIFACT_CHARS = 120_000;
const COMPACT_ARTIFACT_CHARS = 12_000;

export function ArtifactViewer({
  taskId,
  artifactName,
  title,
  compact = false,
}: ArtifactViewerProps) {
  const { t } = useI18n();
  const [content, setContent] = useState("");
  const [loadedArtifactName, setLoadedArtifactName] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"user" | "developer">("user");
  const [error, setError] = useState<{
    artifactName: string;
    message: string;
  } | null>(null);

  const loadArtifact = () => {
    if (!artifactName) {
      return;
    }

    let cancelled = false;
    getArtifact(taskId, artifactName)
      .then((artifact) => {
        if (cancelled) return;
        setContent(
          truncateContent(
            artifact.content,
            compact ? COMPACT_ARTIFACT_CHARS : MAX_ARTIFACT_CHARS,
            t.artifacts.truncated,
          ),
        );
        setLoadedArtifactName(artifact.artifact_name);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError({
            artifactName,
            message: reason instanceof Error ? reason.message : String(reason),
          });
        }
      });

    return () => {
      cancelled = true;
    };
  };

  useEffect(() => {
    return loadArtifact();
    // loadArtifact closes over view props; keeping dependencies explicit avoids stale artifact reads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifactName, taskId]);

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{title ?? t.artifacts.viewer}</h2>
          <div className="mt-1 break-all text-sm text-[var(--muted)]">
            {artifactName === "skill_result.json"
              ? `${artifactName} · ${t.artifacts.skillResult}`
            : artifactName ?? t.artifacts.select}
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {artifactName ? (
            <div className="flex rounded-md border border-[var(--line)] bg-white p-1">
              {(["user", "developer"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setViewMode(mode)}
                  className={`rounded px-3 py-1.5 text-xs font-semibold ${
                    viewMode === mode
                      ? "bg-[var(--panel-soft)] text-[var(--brand-dark)]"
                      : "text-[#475467] hover:bg-[var(--panel-soft)]"
                  }`}
                >
                  {mode === "user" ? t.artifacts.userView : t.artifacts.developerView}
                </button>
              ))}
            </div>
          ) : null}
          {artifactName ? (
            <Button variant="secondary" onClick={() => void loadArtifact()}>
              {t.artifacts.refresh}
            </Button>
          ) : null}
        </div>
      </div>
      <div className="mt-4 min-h-64">
        {artifactName && error?.artifactName === artifactName ? (
          <div className="rounded-md border border-[#fecdca] bg-[#fef3f2] p-4 text-sm text-[var(--danger)]">
            {error.message}
          </div>
        ) : artifactName && loadedArtifactName === artifactName ? (
          <ArtifactRenderer
            taskId={taskId}
            artifactName={artifactName}
            content={content}
            developerView={viewMode === "developer"}
            compact={compact}
          />
        ) : artifactName ? (
          <div className="rounded-md border border-[var(--line)] p-4 text-sm text-[var(--muted)]">
            {t.artifacts.loading}
          </div>
        ) : (
          <div className="rounded-md border border-[var(--line)] p-4 text-sm text-[var(--muted)]">
            {t.artifacts.noneSelected}
          </div>
        )}
      </div>
    </Card>
  );
}

function truncateContent(content: string, maxChars: number, messageTemplate: string) {
  if (content.length <= maxChars) return content;
  return `${content.slice(0, maxChars)}\n\n...${messageTemplate.replace(
    "{count}",
    String(content.length),
  )}`;
}
