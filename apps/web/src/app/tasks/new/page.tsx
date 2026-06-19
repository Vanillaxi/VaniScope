import { Suspense } from "react";
import { TaskCreateForm } from "@/components/tasks/TaskCreateForm";
import { Card } from "@/components/ui/Card";

export default function NewTaskPage() {
  return (
    <Suspense
      fallback={
        <Card className="p-5 text-sm text-[var(--muted)]">Loading task form...</Card>
      }
    >
      <TaskCreateForm />
    </Suspense>
  );
}
