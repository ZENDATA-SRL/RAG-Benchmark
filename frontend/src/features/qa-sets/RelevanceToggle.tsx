import type { RelevanceGrade } from "@/api/types";

/** The two grades of a chunk as toggles: clicking the active grade takes the chunk out. */
export function RelevanceToggle({
  ordinal,
  value,
  onChange,
}: {
  ordinal: number;
  value: RelevanceGrade | null;
  onChange: (relevance: RelevanceGrade | null) => void;
}) {
  const options: { grade: RelevanceGrade; label: string }[] = [
    { grade: "sufficient", label: "sufficient" },
    { grade: "supporting", label: "supporting" },
  ];
  return (
    <span className="flex gap-1">
      {options.map(({ grade, label }) => (
        <button
          key={grade}
          type="button"
          aria-pressed={value === grade}
          aria-label={`Mark chunk ${ordinal} as ${label}`}
          onClick={(event) => {
            event.stopPropagation();
            // Give the focus back to the page, so Enter decides instead of clicking again.
            event.currentTarget.blur();
            onChange(value === grade ? null : grade);
          }}
          className={`rounded-full border px-2 py-0.5 ${
            value === grade
              ? grade === "sufficient"
                ? "border-teal bg-teal/15 text-teal"
                : "border-amber bg-amber/20 text-ink"
              : "border-line text-ink-muted hover:border-ink/30"
          }`}
        >
          {label}
        </button>
      ))}
    </span>
  );
}
