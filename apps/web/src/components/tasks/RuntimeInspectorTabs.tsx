"use client";

import { useState } from "react";
import { useI18n } from "@/lib/i18n";

export type InspectorTabId =
  | "overview"
  | "timeline"
  | "graph"
  | "report"
  | "evidence"
  | "llm"
  | "debug";

type RuntimeInspectorTabsProps = {
  children: (activeTab: InspectorTabId) => React.ReactNode;
};

export function RuntimeInspectorTabs({ children }: RuntimeInspectorTabsProps) {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState<InspectorTabId>("overview");
  const tabs: { id: InspectorTabId; label: string }[] = [
    { id: "overview", label: t.inspector.overview },
    { id: "timeline", label: t.inspector.timeline },
    { id: "graph", label: t.inspector.graph },
    { id: "report", label: t.inspector.report },
    { id: "evidence", label: t.inspector.evidence },
    { id: "llm", label: t.inspector.llmPrompt },
    { id: "debug", label: t.inspector.debug },
  ];

  return (
    <div className="flex flex-col gap-5">
      <div className="flex gap-2 overflow-x-auto rounded-md border border-[var(--line)] bg-white p-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`whitespace-nowrap rounded px-3 py-2 text-sm font-semibold ${
              activeTab === tab.id
                ? "bg-[var(--panel-soft)] text-[var(--brand-dark)]"
                : "text-[#475467] hover:bg-[var(--panel-soft)]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {children(activeTab)}
    </div>
  );
}
