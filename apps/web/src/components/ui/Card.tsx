type CardProps = {
  children: React.ReactNode;
  className?: string;
};

export function Card({ children, className = "" }: CardProps) {
  return (
    <section
      className={`rounded-lg border border-[var(--line)] bg-[var(--panel)] shadow-sm ${className}`}
    >
      {children}
    </section>
  );
}
