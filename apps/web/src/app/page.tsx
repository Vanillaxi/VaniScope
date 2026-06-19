"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { getHealth } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { HealthResponse } from "@/lib/types";

export default function Home() {
  const { t } = useI18n();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [taskId, setTaskId] = useState("");

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
  }, []);

  const openTask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (taskId.trim()) {
      window.location.assign(`/tasks/${encodeURIComponent(taskId.trim())}`);
    }
  };

  return (
    <>
      <Card className="p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="text-sm font-semibold uppercase text-[var(--brand)]">
              VaniScope
            </div>
            <h1 className="mt-2 text-3xl font-semibold">
              {t.home.title}
            </h1>
            <p className="mt-3 text-[var(--muted)]">
              {t.home.description}
            </p>
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
          </div>
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="p-5">
          <h2 className="text-lg font-semibold">{t.home.newTaskTitle}</h2>
          <p className="mt-2 min-h-12 text-sm text-[var(--muted)]">
            {t.home.newTaskDescription}
          </p>
          <Link href="/tasks/new" className="mt-5 inline-flex">
            <Button>{t.home.open}</Button>
          </Link>
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
        <Card className="p-5">
          <h2 className="text-lg font-semibold">{t.home.evalTitle}</h2>
          <p className="mt-2 min-h-12 text-sm text-[var(--muted)]">
            {t.home.evalDescription}
          </p>
          <Link href="/evals" className="mt-5 inline-flex">
            <Button variant="secondary">{t.home.open}</Button>
          </Link>
        </Card>
      </div>
    </>
  );
}
