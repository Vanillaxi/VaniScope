import type { SkillId, TaskLanguage, TaskType } from "@/lib/types";

export type ConsoleSkillId = "browser_task" | Exclude<SkillId, "auto">;

export type SkillPreset = {
  id: string;
  labelKey: "quickstart" | "docsInstall" | "docsZh" | "issueValue" | "issueZh";
  values: {
    url: string;
    click: string;
    expect: string;
    query: string;
    researchGoal: string;
    language: TaskLanguage;
    reminderKey: "demoReminder" | "docsDemoReminder" | "githubDemoReminder";
  };
};

export type ConsoleSkill = {
  id: ConsoleSkillId;
  taskType: TaskType;
  skillId?: Exclude<SkillId, "auto">;
  nameKey: "browserTask" | "docsResearch" | "githubIssueResearch";
  descriptionKey: "browserDescription" | "docsDescription" | "githubDescription";
  exampleKey: "browserExample" | "docsExample" | "githubExample";
  presets: SkillPreset[];
};

export const CONSOLE_SKILLS: ConsoleSkill[] = [
  {
    id: "browser_task",
    taskType: "browser_task",
    nameKey: "browserTask",
    descriptionKey: "browserDescription",
    exampleKey: "browserExample",
    presets: [
      {
        id: "quickstart",
        labelKey: "quickstart",
        values: {
          url: "tests/fixtures/mock_site/basic.html",
          click: "Quickstart",
          expect: "pip install playwright",
          query: "",
          researchGoal: "",
          language: "auto",
          reminderKey: "demoReminder",
        },
      },
    ],
  },
  {
    id: "docs_research",
    taskType: "docs_research",
    skillId: "docs_research",
    nameKey: "docsResearch",
    descriptionKey: "docsDescription",
    exampleKey: "docsExample",
    presets: [
      {
        id: "docs-install",
        labelKey: "docsInstall",
        values: {
          url: "tests/fixtures/mock_site/docs_research.html",
          click: "",
          expect: "installation steps with evidence",
          query: "How do I install and run VaniScope?",
          researchGoal: "",
          language: "en",
          reminderKey: "docsDemoReminder",
        },
      },
      {
        id: "docs-zh",
        labelKey: "docsZh",
        values: {
          url: "tests/fixtures/mock_site/docs_research.html",
          click: "",
          expect: "安装并运行步骤和证据",
          query: "如何安装并运行 VaniScope？",
          researchGoal: "",
          language: "zh",
          reminderKey: "docsDemoReminder",
        },
      },
    ],
  },
  {
    id: "github_issue_research",
    taskType: "github_issue_research",
    skillId: "github_issue_research",
    nameKey: "githubIssueResearch",
    descriptionKey: "githubDescription",
    exampleKey: "githubExample",
    presets: [
      {
        id: "issue-value",
        labelKey: "issueValue",
        values: {
          url: "tests/fixtures/mock_site/github_issue_research.html",
          click: "",
          expect: "difficulty, affected modules, risks, and recommendation",
          query:
            "Analyze whether this issue is worth doing and summarize difficulty, affected modules, and risks.",
          researchGoal: "",
          language: "en",
          reminderKey: "githubDemoReminder",
        },
      },
      {
        id: "issue-zh",
        labelKey: "issueZh",
        values: {
          url: "tests/fixtures/mock_site/github_issue_research.html",
          click: "",
          expect: "难度、影响模块、风险和推荐结论",
          query: "分析这个 issue 是否值得做，并总结难度、影响模块和风险。",
          researchGoal: "",
          language: "zh",
          reminderKey: "githubDemoReminder",
        },
      },
    ],
  },
];

export function skillById(value: string | null | undefined) {
  return CONSOLE_SKILLS.find((skill) => skill.id === value) ?? CONSOLE_SKILLS[0];
}

export function skillIdFromTask(taskType?: string | null, skillId?: string | null) {
  if (skillId === "docs_research" || taskType === "docs_research") return "docs_research";
  if (skillId === "github_issue_research" || taskType === "github_issue_research") {
    return "github_issue_research";
  }
  return "browser_task";
}
