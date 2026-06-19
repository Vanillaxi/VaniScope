"use client";

import { Suspense } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { LanguageProvider } from "@/lib/i18n";

type AppShellProps = {
  children: React.ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  return (
    <LanguageProvider>
      <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)]">
        <Suspense fallback={null}>
          <Sidebar />
        </Suspense>
        <main className="min-h-screen px-4 py-4 md:pl-76 md:pr-6 md:py-6">
          <div className="mx-auto flex w-full max-w-7xl flex-col gap-5">
            {children}
          </div>
        </main>
      </div>
    </LanguageProvider>
  );
}
