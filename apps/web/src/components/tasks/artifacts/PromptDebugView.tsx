"use client";

type PromptDebugViewProps = {
  artifactName: string;
};

export function PromptDebugView({ artifactName }: PromptDebugViewProps) {
  return (
    <div className="rounded-md border border-[var(--line)] bg-[var(--panel-soft)] p-4">
      <h3 className="text-base font-semibold text-[#1d2939]">
        Developer Debug: {artifactName === "prompt_preview.md" ? "Prompt Preview" : "Prompt Context"}
      </h3>
      <p className="mt-2 text-sm leading-6 text-[#475467]">
        This is useful for debugging prompt construction and should not be treated as the final user-facing answer.
      </p>
    </div>
  );
}
