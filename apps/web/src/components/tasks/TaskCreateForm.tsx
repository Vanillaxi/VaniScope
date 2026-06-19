"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { createTask } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { PlannerMode } from "@/lib/types";

export function TaskCreateForm() {
  const { t } = useI18n();
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
    setReminder(t.taskCreate.demoReminder);
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
          <h1 className="text-2xl font-semibold">{t.taskCreate.title}</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {t.taskCreate.description}
          </p>
          <p className="mt-2 text-sm text-[var(--muted)]">
            {t.taskCreate.demoHint}
          </p>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <Input
            label={t.taskCreate.url}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
          />
          <Input
            label={t.taskCreate.click}
            value={click}
            onChange={(e) => setClick(e.target.value)}
          />
          <Input
            label={t.taskCreate.expect}
            value={expect}
            onChange={(e) => setExpect(e.target.value)}
          />
          <label className="flex flex-col gap-1.5 text-sm font-medium text-[#344054]">
            {t.taskCreate.planner}
            <select
              value={planner}
              onChange={(event) => setPlanner(event.target.value as PlannerMode)}
              className="min-h-10 rounded-md border border-[var(--line)] bg-white px-3 text-[var(--foreground)] outline-none focus:border-[var(--brand)] focus:ring-2 focus:ring-[#0f6f7826]"
            >
              <option value="deterministic">{t.taskCreate.deterministic}</option>
              <option value="fake_llm">{t.taskCreate.fakeLlm}</option>
              <option value="llm">{t.taskCreate.llm}</option>
            </select>
          </label>
          <Input
            label={t.taskCreate.workspace}
            value={workspace}
            onChange={(e) => setWorkspace(e.target.value)}
          />
          <label className="flex flex-col gap-1.5 text-sm font-medium text-[#344054]">
            {t.taskCreate.riskMode}
            <select
              value={riskMode}
              onChange={(event) => setRiskMode(event.target.value)}
              className="min-h-10 rounded-md border border-[var(--line)] bg-white px-3 text-[var(--foreground)] outline-none focus:border-[var(--brand)] focus:ring-2 focus:ring-[#0f6f7826]"
            >
              <option value="read_only">{t.taskCreate.readOnly}</option>
              <option value="approval_required">{t.taskCreate.approvalRequired}</option>
            </select>
          </label>
        </div>
        <Textarea
          label={t.taskCreate.reminder}
          value={reminder}
          onChange={(e) => setReminder(e.target.value)}
          placeholder={t.taskCreate.reminderPlaceholder}
        />
        {error ? (
          <div className="rounded-md border border-[#fecdca] bg-[#fef3f2] p-3 text-sm text-[var(--danger)]">
            {error}
          </div>
        ) : null}
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="secondary" onClick={fillDemoCase}>
            {t.taskCreate.fillDemo}
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? t.taskCreate.creating : t.taskCreate.create}
          </Button>
        </div>
      </form>
    </Card>
  );
}
