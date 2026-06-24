"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { getDiagnostics, getHealth } from "@/lib/api";
import { formatDateTime, statusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { statusLabel } from "@/lib/localizedDisplay";
import { CONSOLE_SKILLS, skillById, skillIdFromTask } from "@/lib/skills";
import {
  clearTaskHistory,
  loadTaskHistory,
  type TaskHistoryItem,
} from "@/lib/taskHistory";
import type { DiagnosticsResponse, HealthResponse } from "@/lib/types";

export function Sidebar() {
  const { language, t } = useI18n();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [history, setHistory] = useState<TaskHistoryItem[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [diagnostics, setDiagnostics] = useState<DiagnosticsResponse | null>(null);
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
    getDiagnostics()
      .then((result) => setDiagnostics(result))
      .catch(() => setDiagnostics(null));
  }, []);

  const recentTasks = useMemo(() => history.slice(0, 20), [history]);
  const activeHistoryTask = useMemo(
    () =>
      history.find(
        (task) => pathname === `/tasks/${encodeURIComponent(task.task_id)}`,
      ),
    [history, pathname],
  );
  const activeSkillId =
    pathname === "/tasks/new"
      ? skillById(searchParams.get("skill")).id
      : activeHistoryTask
        ? skillIdFromTask(activeHistoryTask.task_type, activeHistoryTask.skill_id)
        : null;
  const activeSkill = activeSkillId ? skillById(activeSkillId) : null;
  const visibleTasks = useMemo(() => {
    if (!activeSkill) return recentTasks;
    return recentTasks.filter(
      (task) => skillIdFromTask(task.task_type, task.skill_id) === activeSkill.id,
    );
  }, [activeSkill, recentTasks]);

  return (
    <aside className="border-b border-[var(--line)] bg-white px-4 py-3 md:fixed md:inset-y-0 md:left-0 md:flex md:w-72 md:flex-col md:border-b-0 md:border-r md:px-4 md:py-4">
      <div className="flex items-start justify-between gap-3 md:block">
        <Link href="/" className="block">
          <div className="text-lg font-semibold tracking-normal">VaniScope</div>
          <div className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--muted)]">
            {t.nav.tagline}
          </div>
        </Link>
        <Link
          href={activeSkill ? `/tasks/new?skill=${activeSkill.id}` : "/tasks/new"}
          className="inline-flex min-h-9 rounded-md bg-[var(--brand)] px-3 py-2 text-sm font-semibold text-white hover:bg-[var(--brand-dark)] md:mt-4 md:w-full md:justify-center"
        >
          + {t.nav.newTask}
        </Link>
      </div>

      <div className="mt-4 flex min-h-0 flex-1 flex-col gap-3">
        <section className="min-h-0 flex-1 overflow-hidden">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="text-xs font-semibold uppercase text-[var(--muted)]">
                {activeSkill ? t.nav.skillRecentTasks : t.nav.recentTasks}
              </div>
              {activeSkill ? (
                <div className="mt-1 truncate text-sm font-semibold text-[#26323f]">
                  {t.skills[activeSkill.nameKey]}
                </div>
              ) : null}
            </div>
            {recentTasks.length ? (
              <button
                type="button"
                onClick={() => {
                  clearTaskHistory();
                  setHistory([]);
                }}
                className="text-xs font-medium text-[var(--muted)] hover:text-[var(--brand-dark)]"
              >
                {t.nav.clearHistory}
              </button>
            ) : null}
          </div>
          <div className="flex gap-2 overflow-x-auto md:max-h-full md:flex-col md:overflow-y-auto md:pr-1">
            {visibleTasks.length ? (
              visibleTasks.map((task) => {
                const active = pathname === `/tasks/${encodeURIComponent(task.task_id)}`;
                return (
                  <Link
                    key={task.task_id}
                    href={`/tasks/${encodeURIComponent(task.task_id)}`}
                    className={`min-w-56 rounded-md border px-3 py-2 md:min-w-0 ${
                      active
                        ? "border-[#b9d9dd] bg-[#eef7f8]"
                        : "border-transparent hover:border-[var(--line)] hover:bg-[var(--panel-soft)]"
                    }`}
                  >
                    <div className="truncate text-sm font-semibold text-[#26323f]">
                      {task.title}
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <Badge tone={statusTone(task.status)}>
                        {statusLabel(task.status, language)}
                      </Badge>
                      <span className="truncate text-xs text-[var(--muted)]">
                        {formatDateTime(task.created_at, language)}
                      </span>
                    </div>
                  </Link>
                );
              })
            ) : (
              <div className="rounded-md border border-dashed border-[var(--line)] px-3 py-4 text-sm text-[var(--muted)]">
                {activeSkill ? t.nav.emptySkillHistory : t.nav.emptyHistory}
              </div>
            )}
          </div>
        </section>

        <section className="border-t border-[var(--line)] pt-2">
          {activeSkill ? (
            <div className="rounded-md border border-[#b9d9dd] bg-[#eef7f8] p-3">
              <div className="text-xs font-semibold uppercase text-[var(--muted)]">
                {t.nav.currentWorkspace}
              </div>
              <div className="mt-1 text-sm font-semibold text-[var(--brand-dark)]">
                {t.skills[activeSkill.nameKey]}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Link
                  href="/tasks/new"
                  className="rounded border border-[var(--line)] bg-white px-2 py-1 text-xs font-semibold text-[#344054] hover:bg-[var(--panel-soft)]"
                >
                  {t.nav.allWorkspaces}
                </Link>
                {CONSOLE_SKILLS.filter((skill) => skill.id !== activeSkill.id).map(
                  (skill) => (
                    <Link
                      key={skill.id}
                      href={`/tasks/new?skill=${skill.id}`}
                      className="rounded border border-transparent px-2 py-1 text-xs font-semibold text-[#344054] hover:bg-white"
                    >
                      {t.skills[skill.nameKey]}
                    </Link>
                  ),
                )}
              </div>
            </div>
          ) : (
            <>
              <div className="px-2 py-2 text-xs font-semibold uppercase text-[var(--muted)]">
                {t.nav.skills}
              </div>
              <nav className="flex flex-wrap gap-2 px-2">
                {CONSOLE_SKILLS.map((skill) => (
                  <Link
                    key={skill.id}
                    href={`/tasks/new?skill=${skill.id}`}
                    className="rounded-md border border-[var(--line)] bg-white px-2 py-1 text-xs font-semibold text-[#344054] hover:bg-[var(--panel-soft)]"
                  >
                    {t.skills[skill.nameKey]}
                  </Link>
                ))}
              </nav>
            </>
          )}
          <Link
            href="/evals"
            className="mt-1 inline-flex rounded-md px-3 py-1.5 text-sm font-medium text-[#26323f] hover:bg-[var(--panel-soft)]"
          >
            {t.nav.evals}
          </Link>
        </section>
      </div>

      <div className="mt-3 grid gap-2 border-t border-[var(--line)] pt-3">
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
        {diagnostics?.web?.mode ? (
          <div className="flex items-center justify-between gap-2 text-sm">
            <span className="font-medium text-[var(--muted)]">{t.nav.webMode}</span>
            <Badge tone={diagnostics.web.mode === "public_open" ? "warning" : "neutral"}>
              {String(diagnostics.web.mode)}
            </Badge>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
