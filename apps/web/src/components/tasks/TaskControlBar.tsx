"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import {
  cancelTask,
  pauseTask,
  resumeTask,
  stopAndSummarizeTask,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { TaskStatusResponse } from "@/lib/types";

type TaskControlBarProps = {
  task: TaskStatusResponse;
  onChanged?: () => void;
};

export function TaskControlBar({ task, onChanged }: TaskControlBarProps) {
  const { t } = useI18n();
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
    <div className="flex flex-wrap items-center justify-end gap-2">
      <div className="min-w-0 text-right">
        <div className="text-xs text-[var(--muted)]">
            {task.status === "stop_requested"
              ? t.controls.stopRequested
              : terminal
                ? t.controls.completeDisabled
                : t.controls.checkpointHint}
        </div>
      </div>
      {!terminal ? (
        <div className="flex flex-wrap gap-1.5">
          <Button
            variant="secondary"
            className="min-h-8 px-2.5 text-xs"
            disabled={!canPause || busy !== null}
            onClick={() => void run("pause", () => pauseTask(task.task_id))}
          >
            {t.controls.pause}
          </Button>
          <Button
            variant="secondary"
            className="min-h-8 px-2.5 text-xs"
            disabled={!canResume || busy !== null}
            onClick={() => void run("resume", () => resumeTask(task.task_id))}
          >
            {t.controls.resume}
          </Button>
          <Button
            variant="secondary"
            className="min-h-8 px-2.5 text-xs"
            disabled={!canStop || busy !== null}
            onClick={() => void run("stop", () => stopAndSummarizeTask(task.task_id))}
          >
            {t.controls.stopAndSummarize}
          </Button>
          <Button
            variant="danger"
            className="min-h-8 px-2.5 text-xs"
            disabled={!canCancel || busy !== null}
            onClick={() => void run("cancel", () => cancelTask(task.task_id))}
          >
            {t.controls.cancel}
          </Button>
        </div>
      ) : null}
      {message ? <div className="mt-3 text-sm text-[var(--muted)]">{message}</div> : null}
      {error ? (
        <div className="basis-full rounded-md border border-[#fecdca] bg-[#fef3f2] p-2 text-xs text-[var(--danger)]">
          {error}
        </div>
      ) : null}
    </div>
  );
}
