export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`bg-eggshell border border-linen rounded-xl shadow-sm p-6 hover:shadow-card-hover transition-shadow duration-200 ${className}`}
    >
      {children}
    </div>
  );
}

