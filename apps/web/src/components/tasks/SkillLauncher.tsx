"use client";

import { SkillCard } from "@/components/tasks/SkillCard";
import { CONSOLE_SKILLS, type ConsoleSkillId } from "@/lib/skills";

type SkillLauncherProps = {
  selectedSkillId?: ConsoleSkillId;
};

export function SkillLauncher({ selectedSkillId }: SkillLauncherProps) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {CONSOLE_SKILLS.map((skill) => (
        <SkillCard
          key={skill.id}
          skill={skill}
          active={selectedSkillId === skill.id}
        />
      ))}
    </div>
  );
}
