"use client";

import { Button } from "@/components/ui/Button";

type InspectorDrawerProps = {
  open: boolean;
  title: string;
  subtitle?: string | null;
  onClose: () => void;
  children: React.ReactNode;
};

export function InspectorDrawer({
  open,
  title,
  subtitle,
  onClose,
  children,
}: InspectorDrawerProps) {
  return (
    <>
      <div
        className={`fixed inset-0 z-40 bg-black/10 transition-opacity md:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className={`fixed bottom-0 right-0 top-0 z-50 flex w-full max-w-[440px] flex-col border-l border-[var(--line)] bg-white shadow-xl transition-transform duration-200 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
        aria-hidden={!open}
      >
        <div className="flex items-start justify-between gap-3 border-b border-[var(--line)] px-4 py-3">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold">{title}</h2>
            {subtitle ? (
              <div className="mt-1 truncate text-xs text-[var(--muted)]">{subtitle}</div>
            ) : null}
          </div>
          <Button variant="secondary" className="min-h-8 px-2.5" onClick={onClose}>
            ×
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
      </aside>
    </>
  );
}
