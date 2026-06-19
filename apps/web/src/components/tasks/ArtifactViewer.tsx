"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { getArtifact } from "@/lib/api";
import { formatArtifactContent } from "@/lib/format";

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
  title = "任务产物查看器",
  compact = false,
}: ArtifactViewerProps) {
  const [content, setContent] = useState("");
  const [loadedArtifactName, setLoadedArtifactName] = useState<string | null>(null);
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
        try {
          setContent(
            truncateContent(
              formatArtifactContent(artifact.artifact_name, artifact.content),
              compact ? COMPACT_ARTIFACT_CHARS : MAX_ARTIFACT_CHARS,
            ),
          );
        } catch {
          setContent(
            truncateContent(
              artifact.content,
              compact ? COMPACT_ARTIFACT_CHARS : MAX_ARTIFACT_CHARS,
            ),
          );
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
          <h2 className="text-lg font-semibold">{title}</h2>
          <div className="mt-1 break-all text-sm text-[var(--muted)]">
            {artifactName ?? "请选择 artifact"}
          </div>
        </div>
        {artifactName ? (
          <Button variant="secondary" onClick={() => void loadArtifact()}>
            刷新
          </Button>
        ) : null}
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

function truncateContent(content: string, maxChars: number) {
  if (content.length <= maxChars) return content;
  return `${content.slice(0, maxChars)}\n\n...已截断，原始内容共 ${content.length} 个字符。`;
}
