"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { getHealth } from "@/lib/api";
import { formatDateTime, statusTone } from "@/lib/format";
import type { Language } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n";
import { CONSOLE_SKILLS } from "@/lib/skills";
import {
  clearTaskHistory,
  loadTaskHistory,
  type TaskHistoryItem,
} from "@/lib/taskHistory";
import type { HealthResponse } from "@/lib/types";

export function Sidebar() {
  const { language, setLanguage, t } = useI18n();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [history, setHistory] = useState<TaskHistoryItem[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState(false);

  useEffect(() => {
    const refreshHistory = () => setHistory(loadTaskHistory());
    refreshHistory();
    window.addEventListener("storage", refreshHistory);
    window.addEventListener("vaniscope:task-history", refreshHistory);
    return () => {
      window.removeEventListener("storage", refreshHistory);
      window.removeEventListener("vaniscope:task-history", refreshHistory);
    };
  }, []);

  useEffect(() => {
    getHealth()
      .then((result) => {
        setHealth(result);
        setHealthError(false);
      })
      .catch(() => {
        setHealth(null);
        setHealthError(true);
      });
  }, []);

  const recentTasks = useMemo(() => history.slice(0, 20), [history]);

  return (
    <aside className="border-b border-[var(--line)] bg-white px-4 py-3 md:fixed md:inset-y-0 md:left-0 md:flex md:w-72 md:flex-col md:border-b-0 md:border-r md:px-5 md:py-6">
      <div className="flex items-start justify-between gap-3 md:block">
        <Link href="/" className="block">
          <div className="text-lg font-semibold tracking-normal">VaniScope</div>
          <div className="mt-1 text-sm leading-5 text-[var(--muted)]">
            {t.nav.tagline}
          </div>
        </Link>
        <Link
          href="/tasks/new"
          className="inline-flex rounded-md bg-[var(--brand)] px-3 py-2 text-sm font-semibold text-white hover:bg-[var(--brand-dark)] md:mt-5 md:w-full md:justify-center"
        >
          + {t.nav.newTask}
        </Link>
      </div>

      <div className="mt-5 grid gap-5 md:min-h-0 md:flex-1 md:grid-rows-[auto_minmax(0,1fr)]">
        <section>
          <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
            {t.nav.skills}
          </div>
          <nav className="flex gap-2 overflow-x-auto md:flex-col md:overflow-visible">
            {CONSOLE_SKILLS.map((skill) => {
              const href = `/tasks/new?skill=${skill.id}`;
              const active =
                pathname === "/tasks/new" &&
                searchParams.get("skill") === skill.id;
              return (
                <Link
                  key={skill.id}
                  href={href}
                  className={`whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium text-[#26323f] hover:bg-[var(--panel-soft)] ${
                    active ? "bg-[var(--panel-soft)] text-[var(--brand-dark)]" : ""
                  }`}
                >
                  {t.skills[skill.nameKey]}
                </Link>
              );
            })}
          </nav>
          <Link
            href="/evals"
            className="mt-2 inline-flex rounded-md px-3 py-2 text-sm font-medium text-[#26323f] hover:bg-[var(--panel-soft)]"
          >
            {t.nav.evals}
          </Link>
        </section>

        <section className="md:min-h-0 md:overflow-hidden">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-xs font-semibold uppercase text-[var(--muted)]">
              {t.nav.recentTasks}
            </div>
            {recentTasks.length ? (
              <button
                type="button"
                onClick={() => {
                  clearTaskHistory();
                  setHistory([]);
                }}
                className="text-xs font-semibold text-[var(--brand-dark)] hover:underline"
              >
                {t.nav.clearHistory}
              </button>
            ) : null}
          </div>
          <div className="flex gap-2 overflow-x-auto md:max-h-full md:flex-col md:overflow-y-auto">
            {recentTasks.length ? (
              recentTasks.map((task) => (
                <Link
                  key={task.task_id}
                  href={`/tasks/${encodeURIComponent(task.task_id)}`}
                  className="min-w-56 rounded-md border border-transparent px-3 py-2 hover:border-[var(--line)] hover:bg-[var(--panel-soft)] md:min-w-0"
                >
                  <div className="truncate text-sm font-semibold text-[#26323f]">
                    {task.title}
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <Badge tone={statusTone(task.status)}>{task.status}</Badge>
                    <span className="truncate text-xs text-[var(--muted)]">
                      {formatDateTime(task.created_at, language)}
                    </span>
                  </div>
                </Link>
              ))
            ) : (
              <div className="rounded-md border border-dashed border-[var(--line)] px-3 py-4 text-sm text-[var(--muted)]">
                {t.nav.emptyHistory}
              </div>
            )}
          </div>
        </section>
      </div>

      <div className="mt-5 grid gap-4 border-t border-[var(--line)] pt-4">
        <div>
          <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
            {t.nav.language}
          </div>
          <div className="grid grid-cols-2 rounded-md border border-[var(--line)] bg-[var(--panel-soft)] p-1">
            {(["zh", "en"] as Language[]).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setLanguage(item)}
                className={`rounded px-2 py-1.5 text-sm font-semibold transition ${
                  language === item
                    ? "bg-white text-[var(--brand-dark)] shadow-sm"
                    : "text-[#475467] hover:bg-white/70"
                }`}
              >
                {item === "zh" ? t.nav.zh : t.nav.en}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center justify-between gap-2 text-sm">
          <span className="font-medium text-[var(--muted)]">{t.nav.apiHealth}</span>
          {health ? (
            <Badge tone="success">{t.home.apiOk}</Badge>
          ) : healthError ? (
            <Badge tone="danger">{t.home.apiDown}</Badge>
          ) : (
            <Badge tone="info">{t.home.apiChecking}</Badge>
          )}
        </div>
      </div>
    </aside>
  );
}
