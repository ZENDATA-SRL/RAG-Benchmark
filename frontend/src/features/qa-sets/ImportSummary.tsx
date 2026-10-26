import type { ImportSummaryRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";

import { importCounts } from "./importCounts";

function Section({
  title,
  note,
  testId,
  children,
}: {
  title: string;
  note: string;
  testId: string;
  children: React.ReactNode;
}) {
  return (
    <section data-testid={testId}>
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mb-2 text-xs text-ink-muted">{note}</p>
      <ul className="space-y-1 text-sm">{children}</ul>
    </section>
  );
}

/** Every row of the file is accounted for: rows left out are listed with the reason. */
export function ImportSummary({ summary }: { summary: ImportSummaryRead }) {
  const counts = importCounts(summary);

  return (
    <div className="space-y-4" data-testid="import-summary">
      <p className="text-sm">
        {summary.total_rows} {summary.total_rows === 1 ? "row" : "rows"} in the file.
      </p>
      <div className="flex flex-wrap gap-2">
        <Badge tone="good">{`${counts.imported} imported`}</Badge>
        <Badge tone="info">{`${counts.existing} already present`}</Badge>
        <Badge tone="warn">{`${counts.unresolved} unresolved`}</Badge>
        <Badge tone="warn">{`${counts.ambiguous} ambiguous`}</Badge>
        <Badge tone="bad">{`${counts.invalid} invalid`}</Badge>
      </div>

      {summary.existing.length > 0 ? (
        <Section
          title="Already present"
          note="The question was already in the set with the same gold documents: nothing changed."
          testId="import-existing"
        >
          {summary.existing.map((item) => (
            <li key={`${item.row}-${item.question_id}`}>
              <span className="text-ink-muted">Row {item.row}:</span> {item.text}
            </li>
          ))}
        </Section>
      ) : null}

      {summary.unresolved.length > 0 ? (
        <Section
          title="Unresolved"
          note="No document in the library has this file name. Upload the file or fix the name, then import again."
          testId="import-unresolved"
        >
          {summary.unresolved.map((item) => (
            <li key={item.row}>
              <span className="text-ink-muted">Row {item.row}:</span> {item.question}
              <span className="block font-mono text-xs text-danger">{item.files.join(", ")}</span>
            </li>
          ))}
        </Section>
      ) : null}

      {summary.ambiguous.length > 0 ? (
        <Section
          title="Ambiguous"
          note="Several different documents share this file name. The row was not imported."
          testId="import-ambiguous"
        >
          {summary.ambiguous.map((item) => (
            <li key={item.row}>
              <span className="text-ink-muted">Row {item.row}:</span> {item.question}
              {item.files.map((file) => (
                <span key={file.file} className="block font-mono text-xs">
                  {file.file}: {file.candidates.length} candidates (
                  {file.candidates
                    .map((candidate) => candidate.content_hash.slice(0, 8))
                    .join(", ")}
                  )
                </span>
              ))}
            </li>
          ))}
        </Section>
      ) : null}

      {summary.invalid.length > 0 ? (
        <Section title="Invalid" note="The row could not be read." testId="import-invalid">
          {summary.invalid.map((item) => (
            <li key={item.row}>
              <span className="text-ink-muted">Row {item.row}:</span> {item.question || "(empty)"}
              <span className="block text-xs text-danger">{item.reason}</span>
            </li>
          ))}
        </Section>
      ) : null}
    </div>
  );
}
