"use client";

import { useI18n } from "@/lib/i18n";

type ArtifactListProps = {
  artifacts: string[];
  selected?: string | null;
  onSelect: (artifact: string) => void;
};

export function ArtifactList({ artifacts, selected, onSelect }: ArtifactListProps) {
  const { t } = useI18n();

  if (artifacts.length === 0) {
    return <div className="text-sm text-[var(--muted)]">{t.artifacts.empty}</div>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {artifacts.map((artifact) => (
        <button
          key={artifact}
          type="button"
          onClick={() => onSelect(artifact)}
          className={`rounded-md border px-3 py-2 text-sm font-medium transition ${
            selected === artifact
              ? "border-[var(--brand)] bg-[#e6f4f1] text-[var(--brand-dark)]"
              : "border-[var(--line)] bg-white text-[#344054] hover:bg-[var(--panel-soft)]"
          }`}
        >
          {artifact}
        </button>
      ))}
    </div>
  );
}
