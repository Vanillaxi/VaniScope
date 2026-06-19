import type { ButtonHTMLAttributes } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
};

const variantClass = {
  primary: "bg-[var(--brand)] text-white hover:bg-[var(--brand-dark)]",
  secondary:
    "border border-[var(--line)] bg-white text-[var(--foreground)] hover:bg-[var(--panel-soft)]",
  danger: "bg-[var(--danger)] text-white hover:bg-[#912018]",
};

export function Button({
  variant = "primary",
  className = "",
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex min-h-10 items-center justify-center rounded-md px-4 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-55 ${variantClass[variant]} ${className}`}
      {...props}
    />
  );
}
