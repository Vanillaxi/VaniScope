"use client";

import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import type { ConsoleSkill } from "@/lib/skills";
import { useI18n } from "@/lib/i18n";

type SkillCardProps = {
  skill: ConsoleSkill;
  active?: boolean;
};

export function SkillCard({ skill, active = false }: SkillCardProps) {
  const { t } = useI18n();
  const skillText = t.skills;

  return (
    <Card
      className={`p-5 transition hover:border-[var(--brand)] hover:shadow-md ${
        active ? "border-[var(--brand)] ring-2 ring-[#0f6f7820]" : ""
      }`}
    >
      <div className="flex h-full flex-col gap-4">
        <div>
          <h2 className="text-lg font-semibold">{skillText[skill.nameKey]}</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
            {skillText[skill.descriptionKey]}
          </p>
        </div>
        <div className="rounded-md border border-[var(--line)] bg-[var(--panel-soft)] p-3 text-sm text-[#344054]">
          {skillText[skill.exampleKey]}
        </div>
        <Link href={`/tasks/new?skill=${skill.id}`} className="mt-auto inline-flex">
          <Button>{skillText.start}</Button>
        </Link>
      </div>
    </Card>
  );
}
