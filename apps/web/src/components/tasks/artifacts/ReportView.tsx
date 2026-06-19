"use client";

import { Badge } from "@/components/ui/Badge";

type ReportViewProps = {
  content: string;
};

type MarkdownBlock =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "code"; text: string };

export function ReportView({ content }: ReportViewProps) {
  const blocks = parseMarkdownBlocks(content);
  const title =
    blocks.find((block) => block.kind === "heading")?.text ?? "Final report";
  const sourceUrls = extractUrls(content);

  return (
    <div className="rounded-md border border-[var(--line)] bg-white p-5">
      <div className="mb-4">
        <div className="text-xs font-semibold uppercase text-[var(--muted)]">
          Report
        </div>
        <h2 className="mt-1 text-xl font-semibold text-[var(--brand-dark)]">{title}</h2>
      </div>
      <div className="space-y-4">
        {blocks.map((block, index) => {
          if (block.kind === "heading") {
            const Tag = block.level <= 1 ? "h3" : "h4";
            return (
              <Tag
                key={`${block.kind}-${index}`}
                className={
                  block.level <= 1
                    ? "text-lg font-semibold text-[#1d2939]"
                    : "text-base font-semibold text-[#344054]"
                }
              >
                {block.text}
              </Tag>
            );
          }
          if (block.kind === "list") {
            return (
              <ul key={`${block.kind}-${index}`} className="list-disc space-y-2 pl-5 text-sm leading-6 text-[#344054]">
                {block.items.map((item, itemIndex) => (
                  <li key={`${item}-${itemIndex}`}>{item}</li>
                ))}
              </ul>
            );
          }
          if (block.kind === "code") {
            return (
              <pre
                key={`${block.kind}-${index}`}
                className="max-h-72 overflow-auto rounded-md bg-[#101828] p-3 text-xs leading-5 text-[#f8fafc]"
              >
                {block.text}
              </pre>
            );
          }
          return (
            <p key={`${block.kind}-${index}`} className="text-sm leading-7 text-[#344054]">
              {block.text}
            </p>
          );
        })}
      </div>
      {sourceUrls.length ? (
        <div className="mt-5">
          <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
            Sources
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
