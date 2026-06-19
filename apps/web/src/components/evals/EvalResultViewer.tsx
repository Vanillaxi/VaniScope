"use client";

import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";

export function EvalResultViewer() {
  const [path, setPath] = useState("eval_results/langgraph_eval_local");

  return (
    <Card className="p-5">
      <h1 className="text-2xl font-semibold">评测结果</h1>
      <p className="mt-2 text-sm text-[var(--muted)]">
        当前 MVP 保持 eval 输出为本地文件模式。运行 LangGraph eval 后，
        从选定输出目录查看生成的 artifacts。
      </p>
      <div className="mt-5 max-w-xl">
        <Input label="Eval 输出路径" value={path} onChange={(e) => setPath(e.target.value)} />
      </div>
      <div className="mt-5 rounded-md border border-[var(--line)] bg-[var(--panel-soft)] p-4">
        <div className="text-sm font-semibold">命令</div>
        <pre className="mt-2 text-sm">
          {`uv run python scripts/run_workflow_eval.py \\
  --cases tests/fixtures/langgraph_main_eval_cases.json \\
  --output-dir ${path}`}
        </pre>
      </div>
    </Card>
  );
}
