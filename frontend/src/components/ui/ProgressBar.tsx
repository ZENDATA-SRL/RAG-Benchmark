export function ProgressBar({
  value,
  max,
  label,
  className = "",
}: {
  value: number;
  max: number;
  label?: string;
  className?: string;
}) {
  const percent = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div className={className}>
      {label ? (
        <div className="mb-1 flex justify-between text-xs text-ink-muted">
          <span>{label}</span>
          <span>
            {value}/{max}
          </span>
        </div>
      ) : null}
      <div className="h-2 overflow-hidden rounded-full bg-line">
        <div className="h-full bg-teal transition-[width]" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
