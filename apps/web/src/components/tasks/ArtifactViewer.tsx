"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { getArtifact } from "@/lib/api";
import { formatArtifactContent } from "@/lib/format";

type ArtifactViewerProps = {
  taskId: string;
  artifactName?: string | null;
};

export function ArtifactViewer({ taskId, artifactName }: ArtifactViewerProps) {
  const [content, setContent] = useState("");
  const [loadedArtifactName, setLoadedArtifactName] = useState<string | null>(null);
  const [error, setError] = useState<{
    artifactName: string;
    message: string;
  } | null>(null);

  useEffect(() => {
    if (!artifactName) {
      return;
    }

    let cancelled = false;
    getArtifact(taskId, artifactName)
      .then((artifact) => {
        if (cancelled) return;
        try {
          setContent(formatArtifactContent(artifact.artifact_name, artifact.content));
        } catch {
          setContent(artifact.content);
        }
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
  }, [artifactName, taskId]);

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">任务产物查看器</h2>
        <div className="break-all text-sm text-[var(--muted)]">
          {artifactName ?? "请选择 artifact"}
        </div>
      </div>
      <div className="mt-4 min-h-64 rounded-md border border-[var(--line)] bg-[#101828] p-4">
        {artifactName && error?.artifactName === artifactName ? (
          <div className="text-sm text-[#fecdca]">{error.message}</div>
        ) : artifactName && loadedArtifactName === artifactName ? (
          <pre className="max-h-[560px] overflow-auto text-xs leading-5 text-[#f8fafc]">
            {content}
          </pre>
        ) : artifactName ? (
          <div className="text-sm text-[#d0d5dd]">正在加载 artifact...</div>
        ) : (
          <div className="text-sm text-[#d0d5dd]">尚未选择 artifact。</div>
        )}
      </div>
    </Card>
  );
}
