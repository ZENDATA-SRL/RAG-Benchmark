import type { RunResultsRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { TableFrame } from "@/components/ui/TableFrame";

import { findMetric, formatMetric, metricKeys } from "./metrics";

function SnapshotDeclared({ label, detail }: { label: string; detail: string }) {
  return (
    <p>
      <span className="text-ink-muted">{label}:</span> {detail}
    </p>
  );
}

/** Rows are variants; each value carries the number of questions it rests on. */
export function ResultsTable({ results, cutoff }: { results: RunResultsRead; cutoff: number }) {
  const keys = metricKeys(cutoff);
  const corpus = results.corpus_snapshot;
  const qa = results.qa_set_snapshot;

  return (
    <div data-testid="results">
      <div className="mb-2 text-xs" data-testid="results-snapshots">
        <SnapshotDeclared
          label="Corpus snapshot"
          detail={`${corpus.label}${corpus.document_count != null ? ` · ${corpus.document_count} documents` : ""}`}
        />
        <SnapshotDeclared
          label="QA set snapshot"
          detail={`${qa.label}${qa.question_count != null ? ` · ${qa.question_count} questions` : ""}`}
        />
      </div>
      <TableFrame>
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line bg-paper text-xs text-ink-muted">
            <tr>
              <th className="px-4 py-2 font-medium">Variant</th>
              {keys.map((key) => (
                <th key={key} className="px-4 py-2 font-medium">
                  {key}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.variants.map((variant) => (
              <tr
                key={variant.variant_id}
                className={`border-b border-line last:border-0 ${variant.is_baseline ? "bg-amber/10" : ""}`}
                data-testid={`result-row-${variant.name}`}
              >
                <td className="px-4 py-3 font-medium">
                  {variant.name} {variant.is_baseline ? <Badge tone="info">baseline</Badge> : null}
                </td>
                {keys.map((key) => (
                  <td key={key} className="px-4 py-3 font-mono text-xs whitespace-nowrap">
                    {formatMetric(findMetric(variant, key))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </TableFrame>
      <p className="mt-2 text-xs text-ink-muted">
        Each value is the mean, with (questions counted / questions asked). Excluded questions are
        left out of the mean but never hidden.
      </p>
    </div>
  );
}
