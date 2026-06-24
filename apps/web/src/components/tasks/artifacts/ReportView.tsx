"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { useI18n } from "@/lib/i18n";

type ReportViewProps = {
  content: string;
};

type MarkdownBlock =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "code"; text: string };

type ReportSectionKey =
  | "overview"
  | "findings"
  | "details"
  | "evidence"
  | "risks"
  | "recommendations"
  | "other";

type ReportSection = {
  key: ReportSectionKey;
  title: string;
  blocks: MarkdownBlock[];
};

export function ReportView({ content }: ReportViewProps) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const blocks = useMemo(() => parseMarkdownBlocks(content), [content]);
  const title =
    blocks.find((block) => block.kind === "heading")?.text ??
    t.taskDetail.finalReportPreview;
  const sourceUrls = useMemo(() => extractUrls(content), [content]);
  const sections = useMemo(() => shapeReportSections(blocks, t), [blocks, t]);

  const copyReport = async () => {
    const value = sectionsToPlainText(title, sections, sourceUrls, t.inspector.sources);
    try {
      await writeClipboard(value || content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="rounded-md border border-[var(--line)] bg-white p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs font-semibold uppercase text-[var(--muted)]">
            {t.inspector.report}
          </div>
          <h2 className="mt-1 text-xl font-semibold text-[var(--brand-dark)]">
            {title}
          </h2>
        </div>
        <button
          type="button"
          onClick={() => void copyReport()}
          className="inline-flex min-h-8 shrink-0 items-center rounded-md border border-[var(--line)] bg-white px-3 text-xs font-semibold text-[var(--brand-dark)] hover:bg-[var(--panel-soft)]"
        >
          {copied ? t.inspector.copied : t.inspector.copy}
        </button>
      </div>

      <div className="grid gap-3">
        {sections.map((section, index) => (
          <section
            key={`${section.key}-${index}`}
            className="rounded-md border border-[var(--line)] bg-[#fbfcfd] p-4"
          >
            <h3 className="text-base font-semibold text-[#1d2939]">{section.title}</h3>
            <div className="mt-3 space-y-3">
              {section.blocks.map((block, blockIndex) => (
                <ReportBlock key={`${block.kind}-${blockIndex}`} block={block} />
              ))}
            </div>
          </section>
        ))}
      </div>
      {sourceUrls.length ? (
        <div className="mt-5">
          <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
            {t.inspector.sources}
          </div>
          <div className="flex flex-wrap gap-2">
            {sourceUrls.map((url) => (
              <Badge key={url} tone="info">
                <span className="max-w-[320px] truncate">{url}</span>
              </Badge>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ReportBlock({ block }: { block: MarkdownBlock }) {
  const { t } = useI18n();
  if (block.kind === "heading") {
    return (
      <h4 className="text-sm font-semibold text-[#344054]">
        {block.text}
      </h4>
    );
  }
  if (block.kind === "list") {
    return (
      <ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-[#344054]">
        {block.items.map((item, itemIndex) => (
          <li key={`${item}-${itemIndex}`}>{item}</li>
        ))}
      </ul>
    );
  }
  if (block.kind === "code") {
    return (
      <details className="rounded-md border border-[var(--line)] bg-white">
        <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-[var(--brand-dark)]">
          {t.inspector.rawDetails}
        </summary>
        <pre className="max-h-72 overflow-auto border-t border-[var(--line)] bg-[#101828] p-3 text-xs leading-5 text-[#f8fafc]">
          {block.text}
        </pre>
      </details>
    );
  }
  return <p className="text-sm leading-7 text-[#344054]">{block.text}</p>;
}

function parseMarkdownBlocks(content: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  const lines = content.split("\n");
  let paragraph: string[] = [];
  let list: string[] = [];
  let code: string[] | null = null;

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list.length) {
      blocks.push({ kind: "list", items: list });
      list = [];
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("```")) {
      if (code) {
        blocks.push({ kind: "code", text: code.join("\n") });
        code = null;
      } else {
        flushParagraph();
        flushList();
        code = [];
      }
      continue;
    }
    if (code) {
      code.push(line);
      continue;
    }
    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }
    if (trimmed.startsWith("#")) {
      flushParagraph();
      flushList();
      const marker = trimmed.match(/^#+/)?.[0] ?? "#";
      blocks.push({
        kind: "heading",
        level: marker.length,
        text: trimmed.slice(marker.length).trim(),
      });
      continue;
    }
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      flushParagraph();
      list.push(trimmed.slice(2).trim());
      continue;
    }
    flushList();
    paragraph.push(trimmed);
  }
  flushParagraph();
  flushList();
  if (code) blocks.push({ kind: "code", text: code.join("\n") });
  return blocks;
}

function extractUrls(content: string) {
  const urls = new Set<string>();
  for (const token of content.replace(/[)\]]/g, " ").split(/\s+/)) {
    const value = token.replace(/[.,;:]$/g, "");
    if (value.startsWith("http://") || value.startsWith("https://") || value.startsWith("file://")) {
      urls.add(value);
    }
  }
  return Array.from(urls).slice(0, 12);
}

function shapeReportSections(
  blocks: MarkdownBlock[],
  t: ReturnType<typeof useI18n>["t"],
): ReportSection[] {
  const groups = splitByHeading(blocks);
  const buckets: Record<ReportSectionKey, MarkdownBlock[]> = {
    overview: [],
    findings: [],
    details: [],
    evidence: [],
    risks: [],
    recommendations: [],
    other: [],
  };

  for (const group of groups) {
    const key = sectionKey(group.heading);
    buckets[key].push(...group.blocks);
  }

  if (!Object.values(buckets).some((value) => value.length)) {
    buckets.findings = blocks.filter((block) => block.kind !== "heading");
  }

  const labels: Record<ReportSectionKey, string> = {
    overview: t.inspector.taskOverview,
    findings: t.inspector.keyFindings,
    details: t.inspector.importantDetails,
    evidence: t.inspector.evidenceSupport,
    risks: t.inspector.risksLimitations,
    recommendations: t.inspector.recommendations,
    other: t.inspector.otherDetails,
  };

  return ([
    "overview",
    "findings",
    "details",
    "evidence",
    "risks",
    "recommendations",
    "other",
  ] as ReportSectionKey[])
    .filter((key) => buckets[key].length)
    .map((key) => ({
      key,
      title: labels[key],
      blocks: buckets[key],
    }));
}

function splitByHeading(blocks: MarkdownBlock[]) {
  const groups: { heading: string; blocks: MarkdownBlock[] }[] = [];
  let current: { heading: string; blocks: MarkdownBlock[] } | null = null;
  for (const block of blocks) {
    if (block.kind === "heading") {
      if (current) groups.push(current);
      current = { heading: block.text, blocks: [] };
      continue;
    }
    if (!current) current = { heading: "", blocks: [] };
    current.blocks.push(block);
  }
  if (current) groups.push(current);
  return groups;
}

function sectionKey(heading: string): ReportSectionKey {
  const normalized = heading.toLowerCase();
  if (
    includesAny(normalized, [
      "task",
      "source url",
      "source",
      "overview",
      "任务",
      "来源",
      "概览",
      "页面",
    ])
  ) {
    return "overview";
  }
  if (
    includesAny(normalized, [
      "result",
      "summary",
      "finding",
      "conclusion",
      "issue summary",
      "核心",
      "结论",
      "摘要",
      "发现",
    ])
  ) {
    return "findings";
  }
  if (includesAny(normalized, ["evidence", "证据"])) return "evidence";
  if (
    includesAny(normalized, [
      "risk",
      "limitation",
      "caveat",
      "uncertainty",
      "风险",
      "限制",
      "不足",
      "不确定",
    ])
  ) {
    return "risks";
  }
  if (
    includesAny(normalized, [
      "recommend",
      "suggested",
      "plan",
      "next",
      "建议",
      "推荐",
      "计划",
      "后续",
    ])
  ) {
    return "recommendations";
  }
  if (
    includesAny(normalized, [
      "metadata",
      "module",
      "difficulty",
      "value",
      "changed",
      "detail",
      "信息",
      "模块",
      "难度",
      "价值",
      "变更",
    ])
  ) {
    return "details";
  }
  return "other";
}

function includesAny(value: string, candidates: string[]) {
  return candidates.some((candidate) => value.includes(candidate));
}

function sectionsToPlainText(
  title: string,
  sections: ReportSection[],
  sourceUrls: string[],
  sourceTitle: string,
) {
  const lines = [`# ${title}`, ""];
  for (const section of sections) {
    lines.push(`## ${section.title}`, "");
    for (const block of section.blocks) {
      if (block.kind === "heading") {
        lines.push(`### ${block.text}`, "");
      } else if (block.kind === "list") {
        lines.push(...block.items.map((item) => `- ${item}`), "");
      } else {
        lines.push(block.text, "");
      }
    }
  }
  if (sourceUrls.length) {
    lines.push(`## ${sourceTitle}`, "", ...sourceUrls.map((url) => `- ${url}`));
  }
  return lines.join("\n").trim();
}

async function writeClipboard(value: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-1000px";
  document.body.appendChild(textarea);
  textarea.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!ok) throw new Error("Clipboard copy failed");
}
