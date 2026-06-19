import Link from "next/link";

const navItems = [
  { href: "/", label: "总览" },
  { href: "/tasks/new", label: "新建任务" },
  { href: "/evals", label: "评测结果" },
];

export function Sidebar() {
  return (
    <aside className="border-b border-[var(--line)] bg-white px-4 py-3 md:fixed md:inset-y-0 md:left-0 md:w-64 md:border-b-0 md:border-r md:px-5 md:py-6">
      <Link href="/" className="block">
        <div className="text-lg font-semibold tracking-normal">VaniScope</div>
        <div className="mt-1 text-sm text-[var(--muted)]">
          LangGraph 浏览器 Agent Runtime
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
    </aside>
  );
}
