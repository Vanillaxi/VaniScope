"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { SkillLauncher } from "@/components/tasks/SkillLauncher";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { getDiagnostics, getHealth } from "@/lib/api";
import { formatDateTime, statusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { loadTaskHistory, type TaskHistoryItem } from "@/lib/taskHistory";
import type { DiagnosticsResponse, HealthResponse } from "@/lib/types";

export default function Home() {
  const { language, t } = useI18n();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [diagnostics, setDiagnostics] = useState<DiagnosticsResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [taskId, setTaskId] = useState("");
  const [history, setHistory] = useState<TaskHistoryItem[]>([]);

  useEffect(() => {
    getHealth()
      .then((result) => {
        setHealth(result);
        setHealthError(null);
      })
      .catch((reason: unknown) => {
        setHealth(null);
        setHealthError(reason instanceof Error ? reason.message : String(reason));
      });
    getDiagnostics()
      .then((result) => setDiagnostics(result))
      .catch(() => setDiagnostics(null));
  }, []);

  useEffect(() => {
    const refreshHistory = () => setHistory(loadTaskHistory());
    refreshHistory();
    window.addEventListener("vaniscope:task-history", refreshHistory);
    window.addEventListener("storage", refreshHistory);
    return () => {
      window.removeEventListener("vaniscope:task-history", refreshHistory);
      window.removeEventListener("storage", refreshHistory);
    };
  }, []);

  const openTask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (taskId.trim()) {
      window.location.assign(`/tasks/${encodeURIComponent(taskId.trim())}`);
    }
  };

  return (
    <>
      <section className="rounded-lg border border-[var(--line)] bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="text-sm font-semibold uppercase text-[var(--brand)]">
              {t.home.heroEyebrow}
            </div>
            <h1 className="mt-2 text-3xl font-semibold">{t.home.title}</h1>
            <p className="mt-3 text-[var(--muted)]">{t.home.description}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-[var(--muted)]">API</span>
            {health ? (
              <Badge tone="success">{t.home.apiOk}</Badge>
            ) : healthError ? (
              <Badge tone="danger">{t.home.apiDown}</Badge>
            ) : (
              <Badge tone="info">{t.home.apiChecking}</Badge>
            )}
            {diagnostics?.web?.mode ? (
              <Badge
                tone={
                  diagnostics.web.mode === "public_open"
                    ? "warning"
                    : diagnostics.web.mode === "public_safe"
                      ? "info"
                      : "neutral"
                }
              >
                Web Mode: {String(diagnostics.web.mode)}
              </Badge>
            ) : null}
          </div>
        </div>
        {healthError ? (
          <div className="mt-5 rounded-md border border-[#fecdca] bg-[#fef3f2] p-4 text-sm leading-6 text-[var(--danger)]">
            <div className="font-semibold">{t.home.apiErrorTitle}</div>
            <div className="mt-1 text-[#912018]">{t.home.apiErrorHint}</div>
            <div className="mt-2 break-words text-xs text-[#912018]">{healthError}</div>
          </div>
        ) : null}
      </section>

      <SkillLauncher />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">{t.home.recentTasks}</h2>
            <Link href="/tasks/new">
              <Button>+ {t.nav.newTask}</Button>
            </Link>
          </div>
          {history.length ? (
            <div className="grid gap-2">
              {history.slice(0, 6).map((task) => (
                <Link
                  key={task.task_id}
                  href={`/tasks/${encodeURIComponent(task.task_id)}`}
                  className="flex items-center justify-between gap-3 rounded-md border border-[var(--line)] px-3 py-2 hover:bg-[var(--panel-soft)]"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold">{task.title}</div>
                    <div className="mt-1 text-xs text-[var(--muted)]">
                      {formatDateTime(task.created_at, language)}
                    </div>
                  </div>
                  <Badge tone={statusTone(task.status)}>{task.status}</Badge>
                </Link>
              ))}
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-[var(--line)] p-5 text-sm text-[var(--muted)]">
              {t.home.noRecentTasks}
            </div>
          )}
        </Card>

        <Card className="p-5">
          <h2 className="text-lg font-semibold">{t.home.taskByIdTitle}</h2>
          <form onSubmit={openTask} className="mt-4 flex flex-col gap-3">
            <Input
              label={t.home.taskId}
              value={taskId}
              onChange={(event) => setTaskId(event.target.value)}
              placeholder="task_..."
            />
            <Button type="submit" variant="secondary">
              {t.home.viewTask}
            </Button>
          </form>
        </Card>
      </div>
    </>
  );
}
