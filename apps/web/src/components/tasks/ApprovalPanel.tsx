"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { listApprovals, submitApprovalDecision } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { ApprovalRequest } from "@/lib/types";

type ApprovalPanelProps = {
  taskId: string;
  onDecision?: () => void;
};

export function ApprovalPanel({ taskId, onDecision }: ApprovalPanelProps) {
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      setApprovals(await listApprovals(taskId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [taskId]);

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    const interval = window.setInterval(() => void refresh(), 5000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(interval);
    };
  }, [refresh]);

  const decide = async (approval: ApprovalRequest, approved: boolean) => {
    setBusyId(approval.approval_id);
    try {
      await submitApprovalDecision(approval.approval_id, {
        approved,
        reason: approved ? "在控制台批准" : "在控制台拒绝",
      });
      await refresh();
      onDecision?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">审批</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            高风险工具调用会暂停任务，等待人工确认后再继续。
          </p>
        </div>
        <Button variant="secondary" onClick={() => void refresh()}>
          刷新
        </Button>
      </div>
      {error ? (
        <div className="mt-4 rounded-md border border-[#fecdca] bg-[#fef3f2] p-3 text-sm text-[var(--danger)]">
          {error}
        </div>
      ) : null}
      <div className="mt-4 flex flex-col gap-3">
        {approvals.length === 0 ? (
          <div className="text-sm text-[var(--muted)]">暂无审批请求。</div>
        ) : (
          approvals.map((approval) => (
            <div
              key={approval.approval_id}
              className="rounded-md border border-[var(--line)] bg-white p-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={approval.status === "pending" ? "warning" : "neutral"}>
                  {approvalStatusLabel(approval.status)}
                </Badge>
                <span className="break-all text-sm font-semibold">
                  {approval.approval_id}
                </span>
              </div>
              <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="font-semibold text-[var(--muted)]">工具</dt>
                  <dd>{approval.tool_name ?? "未知"}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-[var(--muted)]">风险等级</dt>
                  <dd>{approval.risk_level}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-[var(--muted)]">请求动作</dt>
                  <dd>{approval.action_type ?? approval.target_hint ?? "未知"}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-[var(--muted)]">创建时间</dt>
                  <dd>{formatDateTime(approval.created_at)}</dd>
                </div>
              </dl>
              <div className="mt-3 rounded-md bg-[var(--panel-soft)] p-3 text-sm">
                {approval.reason}
              </div>
              {approval.status === "pending" ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    onClick={() => void decide(approval, true)}
                    disabled={busyId === approval.approval_id}
                  >
                    批准
                  </Button>
                  <Button
                    variant="danger"
                    onClick={() => void decide(approval, false)}
                    disabled={busyId === approval.approval_id}
                  >
                    拒绝
                  </Button>
                </div>
              ) : null}
            </div>
          ))
        )}
      </div>
    </Card>
  );
}

function approvalStatusLabel(status: ApprovalRequest["status"]) {
  if (status === "approved") return "已批准";
  if (status === "rejected") return "已拒绝";
  return "待审批";
}
