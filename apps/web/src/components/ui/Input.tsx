import type { InputHTMLAttributes } from "react";

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
};

export function Input({ label, className = "", ...props }: InputProps) {
  return (
    <label className="flex flex-col gap-1.5 text-sm font-medium text-[#344054]">
      {label}
      <input
        className={`min-h-10 rounded-md border border-[var(--line)] bg-white px-3 text-[var(--foreground)] outline-none transition placeholder:text-[#98a2b3] focus:border-[var(--brand)] focus:ring-2 focus:ring-[#0f6f7826] ${className}`}
        {...props}
      />
    </label>
  );
}
