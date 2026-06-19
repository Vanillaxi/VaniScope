"use client";

import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { useI18n } from "@/lib/i18n";

export function EvalResultViewer() {
  const { t } = useI18n();
  const [path, setPath] = useState("eval_results/langgraph_eval_local");

  return (
    <Card className="p-5">
      <h1 className="text-2xl font-semibold">{t.evals.title}</h1>
      <p className="mt-2 text-sm text-[var(--muted)]">
        {t.evals.description}
      </p>
      <div className="mt-5 max-w-xl">
        <Input label={t.evals.outputPath} value={path} onChange={(e) => setPath(e.target.value)} />
      </div>
      <div className="mt-5 rounded-md border border-[var(--line)] bg-[var(--panel-soft)] p-4">
        <div className="text-sm font-semibold">{t.evals.command}</div>
        <pre className="mt-2 text-sm">
          {`uv run python scripts/run_workflow_eval.py \\
  --cases tests/fixtures/langgraph_main_eval_cases.json \\
  --output-dir ${path}`}
        </pre>
      </div>
    </Card>
  );
}
