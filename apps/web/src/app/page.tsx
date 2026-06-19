"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { getHealth } from "@/lib/api";
import type { HealthResponse } from "@/lib/types";

export default function Home() {
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
              基于 LangGraph 的浏览器 Agent Runtime
            </h1>
            <p className="mt-3 text-[var(--muted)]">
              在一个控制台里创建本地浏览器任务、查看运行事件、检查 artifacts，
              并处理需要人工确认的审批关卡。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-[var(--muted)]">API</span>
            {health ? (
              <Badge tone="success">正常</Badge>
            ) : healthError ? (
              <Badge tone="danger">不可用</Badge>
            ) : (
              <Badge tone="info">检查中</Badge>
            )}
          </div>
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="p-5">
          <h2 className="text-lg font-semibold">新建任务</h2>
          <p className="mt-2 min-h-12 text-sm text-[var(--muted)]">
            填写 planner、点击意图、期望文本和可选 workspace，上交给 FastAPI
            创建 LangGraph 浏览器任务。
          </p>
          <Link href="/tasks/new" className="mt-5 inline-flex">
            <Button>打开</Button>
          </Link>
        </Card>
        <Card className="p-5">
          <h2 className="text-lg font-semibold">按 ID 查看任务</h2>
          <form onSubmit={openTask} className="mt-4 flex flex-col gap-3">
            <Input
              label="任务 ID"
              value={taskId}
              onChange={(event) => setTaskId(event.target.value)}
              placeholder="task_..."
            />
            <Button type="submit" variant="secondary">
              查看任务
            </Button>
          </form>
        </Card>
        <Card className="p-5">
          <h2 className="text-lg font-semibold">评测结果</h2>
          <p className="mt-2 min-h-12 text-sm text-[var(--muted)]">
            打开本地 LangGraph eval 命令辅助页，按输出目录查看生成的评测文件。
          </p>
          <Link href="/evals" className="mt-5 inline-flex">
            <Button variant="secondary">打开</Button>
          </Link>
        </Card>
      </div>
    </>
  );
}
