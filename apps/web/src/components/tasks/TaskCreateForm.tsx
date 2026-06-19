"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { createTask } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { type ConsoleSkill, type ConsoleSkillId, skillById } from "@/lib/skills";
import { upsertTaskHistory } from "@/lib/taskHistory";
import type { PlannerMode, TaskLanguage } from "@/lib/types";

export function TaskCreateForm() {
  const searchParams = useSearchParams();
  const selectedSkill = useMemo(
    () => skillById(searchParams.get("skill")) as ConsoleSkill,
    [searchParams],
  );
  return <TaskCreateFormBody key={selectedSkill.id} selectedSkill={selectedSkill} />;
}

function TaskCreateFormBody({ selectedSkill }: { selectedSkill: ConsoleSkill }) {
  const { t } = useI18n();
  const router = useRouter();
  const initialPreset = selectedSkill.presets[0];
  const [url, setUrl] = useState(initialPreset?.values.url ?? "");
  const [click, setClick] = useState(initialPreset?.values.click ?? "");
  const [expect, setExpect] = useState(initialPreset?.values.expect ?? "");
  const [query, setQuery] = useState(initialPreset?.values.query ?? "");
  const [researchGoal, setResearchGoal] = useState(
    initialPreset?.values.researchGoal ?? "",
  );
  const [taskLanguage, setTaskLanguage] = useState<TaskLanguage>(
    initialPreset?.values.language ?? "auto",
  );
  const [planner, setPlanner] = useState<PlannerMode>("deterministic");
  const [workspace, setWorkspace] = useState("tests/fixtures/workspace");
  const [reminder, setReminder] = useState(
    initialPreset ? t.taskCreate[initialPreset.values.reminderKey] : "",
  );
  const [riskMode, setRiskMode] = useState("read_only");
  const [dryRun, setDryRun] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const applyPreset = (skill: ConsoleSkill, presetId?: string) => {
    const preset = skill.presets.find((item) => item.id === presetId) ?? skill.presets[0];
    if (!preset) return;
    setUrl(preset.values.url);
    setClick(preset.values.click);
    setExpect(preset.values.expect);
    setQuery(preset.values.query);
    setResearchGoal(preset.values.researchGoal);
    setTaskLanguage(preset.values.language);
    setReminder(t.taskCreate[preset.values.reminderKey]);
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const task = await createTask({
        url,
        click: selectedSkill.id === "browser_task" ? click : undefined,
        expect,
        task_type: selectedSkill.taskType,
        skill_id: selectedSkill.skillId,
        query,
        research_goal: researchGoal,
        language: taskLanguage,
        planner,
        workspace: selectedSkill.id === "browser_task" ? workspace : undefined,
        reminder,
        risk_mode: selectedSkill.id === "browser_task" ? riskMode : undefined,
        dry_run: dryRun,
      });
      const now = new Date().toISOString();
      upsertTaskHistory({
        task_id: task.task_id,
        title: taskTitle(selectedSkill.id, query || click || url),
        task_type: task.task_type ?? selectedSkill.taskType,
        skill_id: task.skill_id ?? selectedSkill.skillId,
        status: task.status,
        created_at: now,
        last_opened_at: now,
      });
      router.push(`/tasks/${task.task_id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSubmitting(false);
    }
  };

  const skillText = t.skills;

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <Card className="p-5">
        <form onSubmit={onSubmit} className="flex flex-col gap-5">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge tone="info">{t.taskCreate.selectedSkill}</Badge>
              <span className="text-sm font-semibold text-[var(--brand-dark)]">
                {skillText[selectedSkill.nameKey]}
              </span>
            </div>
            <h1 className="text-2xl font-semibold">{t.taskCreate.title}</h1>
            <p className="mt-1 text-sm text-[var(--muted)]">
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

            {selectedSkill.id === "browser_task" ? (
              <>
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
              </>
            ) : null}

            {selectedSkill.id !== "browser_task" ? (
              <>
                <Input
                  label={t.taskCreate.query}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                {selectedSkill.id === "docs_research" ? (
                  <Input
                    label={t.taskCreate.researchGoal}
                    value={researchGoal}
                    onChange={(e) => setResearchGoal(e.target.value)}
                  />
                ) : null}
                <label className="flex flex-col gap-1.5 text-sm font-medium text-[#344054]">
                  {t.taskCreate.language}
                  <select
                    value={taskLanguage}
                    onChange={(event) =>
                      setTaskLanguage(event.target.value as TaskLanguage)
                    }
                    className="min-h-10 rounded-md border border-[var(--line)] bg-white px-3 text-[var(--foreground)] outline-none focus:border-[var(--brand)] focus:ring-2 focus:ring-[#0f6f7826]"
                  >
                    <option value="auto">{t.taskCreate.autoLanguage}</option>
                    <option value="en">English</option>
                    <option value="zh">中文</option>
                  </select>
                </label>
              </>
            ) : null}

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

            {selectedSkill.id === "browser_task" ? (
              <>
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
                    <option value="approval_required">
                      {t.taskCreate.approvalRequired}
                    </option>
                  </select>
                </label>
              </>
            ) : null}
          </div>

          <Textarea
            label={t.taskCreate.reminder}
            value={reminder}
            onChange={(e) => setReminder(e.target.value)}
            placeholder={t.taskCreate.reminderPlaceholder}
          />

          <label className="flex items-start gap-3 rounded-md border border-[var(--line)] bg-[var(--panel-soft)] p-3 text-sm">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(event) => setDryRun(event.target.checked)}
              className="mt-1"
            />
            <span>
              <span className="block font-semibold text-[#344054]">
                {t.taskCreate.llmReadiness}
              </span>
              <span className="text-[var(--muted)]">
                {t.taskCreate.llmReadinessDescription}
              </span>
            </span>
          </label>

          {error ? (
            <div className="rounded-md border border-[#fecdca] bg-[#fef3f2] p-3 text-sm text-[var(--danger)]">
              {error}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-2">
              {selectedSkill.presets.map((preset) => (
                <Button
                  key={preset.id}
                  type="button"
                  variant="secondary"
                  onClick={() => applyPreset(selectedSkill, preset.id)}
                >
                  {t.taskCreate[preset.labelKey]}
                </Button>
              ))}
            </div>
            <Button type="submit" disabled={submitting}>
              {submitting ? t.taskCreate.creating : t.taskCreate.create}
            </Button>
          </div>
        </form>
      </Card>

      <aside className="flex flex-col gap-5">
        <Card className="p-5">
          <h2 className="text-lg font-semibold">{t.taskCreate.whatThisSkillDoes}</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
            {skillText[selectedSkill.descriptionKey]}
          </p>
          <div className="mt-4 rounded-md border border-[var(--line)] bg-[var(--panel-soft)] p-3 text-sm text-[#344054]">
            {skillText[selectedSkill.exampleKey]}
          </div>
        </Card>
        <Card className="p-5">
          <h2 className="text-lg font-semibold">{t.taskCreate.demoPresets}</h2>
          <div className="mt-4 grid gap-2">
            {selectedSkill.presets.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => applyPreset(selectedSkill, preset.id)}
                className="rounded-md border border-[var(--line)] bg-white px-3 py-2 text-left text-sm font-medium hover:bg-[var(--panel-soft)]"
              >
                {t.taskCreate[preset.labelKey]}
              </button>
            ))}
          </div>
        </Card>
      </aside>
    </div>
  );
}

function taskTitle(skillId: ConsoleSkillId, value: string) {
  const label =
    skillId === "docs_research"
      ? "Docs"
      : skillId === "github_issue_research"
        ? "Issue"
        : "Browser";
  const compactValue = value.trim().replace(/\s+/g, " ").slice(0, 72);
  return compactValue ? `${label}: ${compactValue}` : `${label}: New task`;
}
