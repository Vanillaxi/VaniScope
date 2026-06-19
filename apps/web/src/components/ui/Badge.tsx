type BadgeProps = {
  children: React.ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
};

const toneClass = {
  neutral: "border-[#d5dae3] bg-[#f2f4f7] text-[#344054]",
  success: "border-[#abefc6] bg-[#ecfdf3] text-[var(--success)]",
  warning: "border-[#fedf89] bg-[#fffaeb] text-[#93370d]",
  danger: "border-[#fecdca] bg-[#fef3f2] text-[var(--danger)]",
  info: "border-[#b9e6fe] bg-[#f0f9ff] text-[#026aa2]",
};

export function Badge({ children, tone = "neutral" }: BadgeProps) {
  return (
    <span
      className={`inline-flex max-w-full items-center rounded-md border px-2 py-1 text-xs font-semibold ${toneClass[tone]}`}
    >
      {children}
    </span>
  );
}
