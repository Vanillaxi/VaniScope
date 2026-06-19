"use client";

import { API_BASE_URL } from "@/lib/api";

type RawArtifactViewProps = {
  taskId: string;
  artifactName: string;
  content: string;
  defaultOpen?: boolean;
  title?: string;
};

export function RawArtifactView({
  taskId,
  artifactName,
  content,
  defaultOpen = false,
  title = "Developer raw",
}: RawArtifactViewProps) {
  return (
    <details
      open={defaultOpen}
      className="rounded-md border border-[var(--line)] bg-[#101828]"
    >
      <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-[#f8fafc]">
        {title}
      </summary>
      <div className="border-t border-[#344054] p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3 text-xs text-[#d0d5dd]">
          <span className="break-all">{artifactName}</span>
          <a
            className="rounded border border-[#667085] px-2 py-1 font-semibold text-[#f8fafc] hover:bg-[#1d2939]"
            href={`${API_BASE_URL}/tasks/${encodeURIComponent(
              taskId,
            )}/artifacts/${encodeURIComponent(artifactName)}`}
            download={artifactName}
          >
            Download raw
          </a>
        </div>
        <pre className="max-h-[560px] overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-[#f8fafc]">
          {content}
        </pre>
      </div>
    </details>
  );
}
