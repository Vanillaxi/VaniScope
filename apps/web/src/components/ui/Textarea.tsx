import type { TextareaHTMLAttributes } from "react";

type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label: string;
};

export function Textarea({ label, className = "", ...props }: TextareaProps) {
  return (
    <label className="flex flex-col gap-1.5 text-sm font-medium text-[#344054]">
      {label}
      <textarea
        className={`min-h-24 rounded-md border border-[var(--line)] bg-white px-3 py-2 text-[var(--foreground)] outline-none transition placeholder:text-[#98a2b3] focus:border-[var(--brand)] focus:ring-2 focus:ring-[#0f6f7826] ${className}`}
        {...props}
      />
    </label>
  );
}
