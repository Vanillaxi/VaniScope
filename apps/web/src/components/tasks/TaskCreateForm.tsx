"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { createTask } from "@/lib/api";
import type { PlannerMode } from "@/lib/types";

export function TaskCreateForm() {
  const router = useRouter();
  const [url, setUrl] = useState("tests/fixtures/mock_site/basic.html");
  const [click, setClick] = useState("Quickstart");
  const [expect, setExpect] = useState("pip install playwright");
  const [planner, setPlanner] = useState<PlannerMode>("deterministic");
  const [workspace, setWorkspace] = useState("tests/fixtures/workspace");
  const [reminder, setReminder] = useState("");
  const [riskMode, setRiskMode] = useState("read_only");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const fillDemoCase = () => {
    setUrl("tests/fixtures/mock_site/basic.html");
    setClick("Quickstart");
    setExpect("pip install playwright");
    setPlanner("deterministic");
    setWorkspace("tests/fixtures/workspace");
    setReminder("This is a local full-stack console demo.");
    setRiskMode("read_only");
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const task = await createTask({
        url,
        click,
        expect,
        planner,
        workspace,
        reminder,
        risk_mode: riskMode,
      });
      router.push(`/tasks/${task.task_id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="p-5">
      <form onSubmit={onSubmit} className="flex flex-col gap-5">
        <div>
          <h1 className="text-2xl font-semibold">新建任务</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            通过 FastAPI Task API 提交 LangGraph 浏览器任务。
          </p>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Demo 默认使用仓库内 mock site 路径，不访问真实网页。
          </p>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <Input
            label="URL 或 fixture 路径"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
          />
          <Input
            label="点击目标 / 意图"
            value={click}
            onChange={(e) => setClick(e.target.value)}
          />
          <Input
            label="期望文本"
            value={expect}
            onChange={(e) => setExpect(e.target.value)}
          />
          <label className="flex flex-col gap-1.5 text-sm font-medium text-[#344054]">
            Planner
            <select
              value={planner}
              onChange={(event) => setPlanner(event.target.value as PlannerMode)}
              className="min-h-10 rounded-md border border-[var(--line)] bg-white px-3 text-[var(--foreground)] outline-none focus:border-[var(--brand)] focus:ring-2 focus:ring-[#0f6f7826]"
            >
              <option value="deterministic">确定性 deterministic</option>
              <option value="fake_llm">模拟 LLM fake_llm</option>
              <option value="llm">真实 LLM llm</option>
            </select>
          </label>
          <Input
            label="Workspace 路径"
            value={workspace}
            onChange={(e) => setWorkspace(e.target.value)}
          />
          <label className="flex flex-col gap-1.5 text-sm font-medium text-[#344054]">
            风险模式
            <select
              value={riskMode}
              onChange={(event) => setRiskMode(event.target.value)}
              className="min-h-10 rounded-md border border-[var(--line)] bg-white px-3 text-[var(--foreground)] outline-none focus:border-[var(--brand)] focus:ring-2 focus:ring-[#0f6f7826]"
            >
              <option value="read_only">只读 read_only</option>
              <option value="approval_required">需要审批 approval_required</option>
            </select>
          </label>
        </div>
        <Textarea
          label="运行提醒"
          value={reminder}
          onChange={(e) => setReminder(e.target.value)}
          placeholder="可选的 runtime reminder"
        />
        {error ? (
          <div className="rounded-md border border-[#fecdca] bg-[#fef3f2] p-3 text-sm text-[var(--danger)]">
            {error}
          </div>
        ) : null}
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="secondary" onClick={fillDemoCase}>
            填入 demo case
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "创建中..." : "创建任务"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
