import { Sidebar } from "@/components/layout/Sidebar";

type AppShellProps = {
  children: React.ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      <Sidebar />
      <main className="min-h-screen px-4 py-4 md:pl-68 md:pr-6 md:py-6">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-5">{children}</div>
      </main>
    </div>
  );
}
