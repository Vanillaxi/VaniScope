"use client";

import Link from "next/link";
import { CONSOLE_SKILLS, type ConsoleSkillId } from "@/lib/skills";
import { useI18n } from "@/lib/i18n";

type SkillLauncherProps = {
  selectedSkillId?: ConsoleSkillId;
};

export function SkillLauncher({ selectedSkillId }: SkillLauncherProps) {
  const { t } = useI18n();
  const skillText = t.skills;
  return (
    <div className="flex flex-wrap gap-2">
      {CONSOLE_SKILLS.map((skill) => {
        const active = selectedSkillId === skill.id;
        return (
          <Link
            key={skill.id}
            href={`/tasks/new?skill=${skill.id}`}
            className={`inline-flex min-h-9 max-w-full rounded-md border px-3 py-2 text-left text-sm font-semibold transition ${
              active
                ? "border-[var(--brand)] bg-[var(--brand)] text-white"
                : "border-[var(--line)] bg-white text-[var(--foreground)] hover:bg-[var(--panel-soft)]"
            }`}
          >
            <span className="flex min-w-0 flex-col items-start leading-tight">
              <span>{skillText[skill.nameKey]}</span>
              <span
                className={`max-w-56 truncate text-[11px] font-normal ${
                  active ? "text-white/80" : "text-[var(--muted)]"
                }`}
              >
                {skillText[skill.exampleKey]}
              </span>
            </span>
          </Link>
        );
      })}
    </div>
  );
}
