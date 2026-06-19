"use client";

import Link from "next/link";
import type { Language } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n";

export function Sidebar() {
  const { language, setLanguage, t } = useI18n();
  const navItems = [
    { href: "/", label: t.nav.overview },
    { href: "/tasks/new", label: t.nav.newTask },
    { href: "/evals", label: t.nav.evals },
  ];

  return (
    <aside className="border-b border-[var(--line)] bg-white px-4 py-3 md:fixed md:inset-y-0 md:left-0 md:w-64 md:border-b-0 md:border-r md:px-5 md:py-6">
      <Link href="/" className="block">
        <div className="text-lg font-semibold tracking-normal">VaniScope</div>
        <div className="mt-1 text-sm text-[var(--muted)]">
          {t.nav.tagline}
        </div>
      </Link>
      <nav className="mt-4 flex gap-2 md:mt-8 md:flex-col">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="rounded-md px-3 py-2 text-sm font-medium text-[#26323f] hover:bg-[var(--panel-soft)]"
          >
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="mt-5 border-t border-[var(--line)] pt-4 md:absolute md:bottom-5 md:left-5 md:right-5 md:mt-0">
        <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
          {t.nav.language}
        </div>
        <div className="grid grid-cols-2 rounded-md border border-[var(--line)] bg-[var(--panel-soft)] p-1">
          {(["zh", "en"] as Language[]).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setLanguage(item)}
              className={`rounded px-2 py-1.5 text-sm font-semibold transition ${
                language === item
                  ? "bg-white text-[var(--brand-dark)] shadow-sm"
                  : "text-[#475467] hover:bg-white/70"
              }`}
            >
              {item === "zh" ? t.nav.zh : t.nav.en}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
