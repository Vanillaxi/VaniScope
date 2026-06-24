"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { LanguageProvider, type Language, useI18n } from "@/lib/i18n";

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
          <div className="mx-auto mb-3 flex w-full max-w-7xl justify-end">
            <LanguageMenu />
          </div>
          <div className="mx-auto flex w-full max-w-7xl flex-col gap-5">
            {children}
          </div>
        </main>
      </div>
    </LanguageProvider>
  );
}

function LanguageMenu() {
  const { language, setLanguage, t } = useI18n();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  const chooseLanguage = (value: Language) => {
    setLanguage(value);
    setOpen(false);
  };

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        aria-label={t.nav.languageMenu}
        title={t.nav.languageMenu}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[var(--line)] bg-white text-sm font-semibold text-[var(--brand-dark)] shadow-sm transition hover:bg-[var(--panel-soft)]"
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="h-4 w-4"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.8"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18M12 3c2.2 2.5 3.3 5.5 3.3 9S14.2 18.5 12 21M12 3c-2.2 2.5-3.3 5.5-3.3 9S9.8 18.5 12 21" />
        </svg>
      </button>
      {open ? (
        <div className="absolute right-0 z-30 mt-2 w-32 overflow-hidden rounded-md border border-[var(--line)] bg-white p-1 shadow-lg">
          {(["zh", "en"] as Language[]).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => chooseLanguage(item)}
              className={`flex w-full items-center justify-between rounded px-3 py-2 text-left text-sm font-semibold transition ${
                language === item
                  ? "bg-[#eef7f8] text-[var(--brand-dark)]"
                  : "text-[#344054] hover:bg-[var(--panel-soft)]"
              }`}
            >
              <span>{item === "zh" ? t.nav.zh : t.nav.en}</span>
              {language === item ? (
                <span
                  aria-hidden="true"
                  className="h-1.5 w-1.5 rounded-full bg-[var(--brand-dark)]"
                />
              ) : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
