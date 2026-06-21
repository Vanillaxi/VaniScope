export type ArtifactRendererKind =
  | "report"
  | "evidence"
  | "review"
  | "timeline"
  | "toolAudit"
  | "llmCalls"
  | "prompt"
  | "trace"
  | "transcript"
  | "approval"
  | "recovery"
  | "skillResult"
  | "raw";

const rendererByName: Record<string, ArtifactRendererKind> = {
  "final_report.md": "report",
  "evidence.jsonl": "evidence",
  "review.json": "review",
  "timeline.json": "timeline",
  "tool_audit.jsonl": "toolAudit",
  "llm_calls.jsonl": "llmCalls",
  "prompt_preview.md": "prompt",
  "auto_explore_prompt_preview.md": "prompt",
  "prompt_context.json": "prompt",
  "trace.jsonl": "trace",
  "transcript.jsonl": "transcript",
  "approvals.jsonl": "approval",
  "pending.jsonl": "approval",
  "recovery.jsonl": "recovery",
  "skill_result.json": "skillResult",
};

export function rendererKindForArtifact(artifactName?: string | null): ArtifactRendererKind {
  if (!artifactName) return "raw";
  return rendererByName[artifactName] ?? "raw";
}

export function isDeveloperArtifact(artifactName?: string | null) {
  return ["prompt", "trace", "transcript"].includes(rendererKindForArtifact(artifactName));
}
