import type { ImportSummaryRead } from "@/api/types";

export type ImportCounts = {
  imported: number;
  existing: number;
  unresolved: number;
  ambiguous: number;
  invalid: number;
};

export function importCounts(summary: ImportSummaryRead): ImportCounts {
  return {
    imported: summary.imported.length,
    existing: summary.existing.length,
    unresolved: summary.unresolved.length,
    ambiguous: summary.ambiguous.length,
    invalid: summary.invalid.length,
  };
}

/** Rows that did not make it into the set: they are always listed, never hidden. */
export function skippedCount(summary: ImportSummaryRead): number {
  return summary.unresolved.length + summary.ambiguous.length + summary.invalid.length;
}
