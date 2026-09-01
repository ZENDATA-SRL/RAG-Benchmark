type Tone = "neutral" | "good" | "warn" | "bad" | "info";

const tones: Record<Tone, string> = {
  neutral: "bg-ink/8 text-ink-muted",
  good: "bg-teal/15 text-teal",
  warn: "bg-amber/20 text-ink",
  bad: "bg-danger/10 text-danger",
  info: "bg-rust/10 text-rust-dark",
};

export function Badge({
  children,
  tone = "neutral",
  className = "",
}: {
  children: string;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
