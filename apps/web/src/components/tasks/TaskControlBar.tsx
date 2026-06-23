"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  cancelTask,
  pauseTask,
  resumeTask,
  stopAndSummarizeTask,
} from "@/lib/api";
import type { TaskStatusResponse } from "@/lib/types";

type TaskControlBarProps = {
  task: TaskStatusResponse;
  onChanged?: () => void;
};

export function TaskControlBar({ task, onChanged }: TaskControlBarProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const terminal = ["succeeded", "succeeded_partial", "failed", "canceled", "rejected", "blocked"].includes(
    task.status,
  );
  const canPause = task.status === "running";
  const canResume = task.status === "paused";
  const canStop = ["running", "paused", "waiting_for_approval", "requires_approval"].includes(task.status);
  const canCancel = ["running", "paused", "waiting_for_approval", "requires_approval", "stop_requested"].includes(
    task.status,
  );

  const run = async (action: string, fn: () => Promise<{ message: string }>) => {
    setBusy(action);
    setError(null);
    try {
      const response = await fn();
      setMessage(response.message);
      onChanged?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">Task controls</div>
          <div className="mt-1 text-xs text-[var(--muted)]">
            {task.status === "stop_requested"
              ? "Generating partial report from collected evidence..."
              : terminal
                ? "Task is complete; controls are disabled."
                : "Requests are applied at the next safe checkpoint."}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            disabled={!canPause || busy !== null}
            onClick={() => void run("pause", () => pauseTask(task.task_id))}
          >
            Pause
          </Button>
          <Button
            variant="secondary"
            disabled={!canResume || busy !== null}
            onClick={() => void run("resume", () => resumeTask(task.task_id))}
          >
            Resume
          </Button>
          <Button
            variant="secondary"
            disabled={!canStop || busy !== null}
            onClick={() => void run("stop", () => stopAndSummarizeTask(task.task_id))}
          >
            Stop and summarize
          </Button>
          <Button
            variant="danger"
            disabled={!canCancel || busy !== null}
            onClick={() => void run("cancel", () => cancelTask(task.task_id))}
          >
            Cancel
          </Button>
        </div>
      </div>
      {message ? <div className="mt-3 text-sm text-[var(--muted)]">{message}</div> : null}
      {error ? (
        <div className="mt-3 rounded-md border border-[#fecdca] bg-[#fef3f2] p-3 text-sm text-[var(--danger)]">
          {error}
        </div>
      ) : null}
    </Card>
  );
}
