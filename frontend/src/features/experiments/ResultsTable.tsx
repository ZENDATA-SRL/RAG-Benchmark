import { useState } from "react";

import type { ResultGroupRead, RunResultsRead, VariantResultRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { TableFrame } from "@/components/ui/TableFrame";

import {
  chunkMetricKeys,
  describeCoverage,
  excludedDetail,
  findMetric,
  formatCeiling,
  formatMetric,
  groupsOf,
  metricKeys,
} from "./metrics";

function SnapshotDeclared({ label, detail }: { label: string; detail: string }) {
  return (
    <p>
      <span className="text-ink-muted">{label}:</span> {detail}
    </p>
  );
}

function GroupHeader({ group, span }: { group: ResultGroupRead; span: number }) {
  return (
    <tr
      className="border-b border-line bg-paper"
      data-testid={`result-group-${group.chunking_configuration_id}`}
    >
      <td colSpan={span} className="px-4 py-2 text-xs">
        <span className="font-semibold">{group.chunking_configuration_name}</span>
        <span className="text-ink-muted">
          {" "}
          · {group.parsing} → {group.chunking} · evidence:{" "}
          {describeCoverage(group.evidence_coverage)} · recall ceiling{" "}
          {formatCeiling(group.recall_ceiling)}
        </span>
      </td>
    </tr>
  );
}

/**
 * Rows are variants, grouped by the chunking configuration they search: chunk-level metrics
 * only compare within a group. Selecting variants of different groups keeps the
 * document-level columns and says why the chunk-level ones are gone.
 */
export function ResultsTable({ results, cutoff }: { results: RunResultsRead; cutoff: number }) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [comparing, setComparing] = useState(false);
  const corpus = results.corpus_snapshot;
  const qa = results.qa_set_snapshot;
  const crossGroup = comparing && groupsOf(results.groups, selected).length > 1;
  const documentKeys = metricKeys(cutoff);
  const chunkKeys = crossGroup ? [] : chunkMetricKeys(cutoff);
  const span = 2 + documentKeys.length + chunkKeys.length;
  const groups = results.groups
    .map((group) => ({
      ...group,
      variants: comparing
        ? group.variants.filter((variant) => selected.has(variant.variant_id))
        : group.variants,
    }))
    .filter((group) => group.variants.length > 0);

  const toggle = (variant: VariantResultRead) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(variant.variant_id)) next.delete(variant.variant_id);
      else next.add(variant.variant_id);
      return next;
    });

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
      {selected.size > 0 ? (
        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
          {comparing ? (
            <>
              <span>
                Comparing {selected.size} selected variant{selected.size === 1 ? "" : "s"}
              </span>
              <Button variant="ghost" onClick={() => setComparing(false)}>
                Show all
              </Button>
            </>
          ) : (
            <>
              <Button variant="secondary" onClick={() => setComparing(true)}>
                Compare selected ({selected.size})
              </Button>
              <Button variant="ghost" onClick={() => setSelected(new Set())}>
                Clear selection
              </Button>
            </>
          )}
        </div>
      ) : null}
      {crossGroup ? (
        <p
          className="mb-2 rounded-md bg-amber/15 p-3 text-xs leading-5"
          data-testid="cross-group-reason"
        >
          Only document-level metrics are shown. {results.cross_group_metrics.reason}
        </p>
      ) : null}
      <TableFrame>
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line bg-paper text-xs text-ink-muted">
            <tr>
              <th className="w-8 px-2 py-2" />
              <th className="px-4 py-2 font-medium">Variant</th>
              {documentKeys.map((key) => (
                <th key={key} className="px-4 py-2 font-medium">
                  {key}
                </th>
              ))}
              {chunkKeys.map((key) => (
                <th key={key} className="bg-teal/5 px-4 py-2 font-medium">
                  {key}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => [
              <GroupHeader key={group.chunking_configuration_id} group={group} span={span} />,
              ...group.variants.map((variant) => (
                <tr
                  key={variant.variant_id}
                  className={`border-b border-line last:border-0 ${variant.is_baseline ? "bg-amber/10" : ""}`}
                  data-testid={`result-row-${variant.name}`}
                >
                  <td className="px-2 py-3">
                    <input
                      type="checkbox"
                      aria-label={`Select ${variant.name}`}
                      checked={selected.has(variant.variant_id)}
                      onChange={() => toggle(variant)}
                    />
                  </td>
                  <td className="px-4 py-3 font-medium">
                    {variant.name}{" "}
                    {variant.is_baseline ? <Badge tone="info">baseline</Badge> : null}
                  </td>
                  {[...documentKeys, ...chunkKeys].map((key) => {
                    const metric = findMetric(variant, key);
                    return (
                      <td
                        key={key}
                        title={excludedDetail(metric)}
                        className="px-4 py-3 font-mono text-xs whitespace-nowrap"
                      >
                        {formatMetric(metric)}
                      </td>
                    );
                  })}
                </tr>
              )),
            ])}
          </tbody>
        </table>
      </TableFrame>
      <p className="mt-2 text-xs text-ink-muted">
        Each value is the mean over questions, with (questions counted / questions asked); hover a
        value for why questions were excluded. Chunk-level values count only the questions whose
        evidence was confirmed under that configuration: not reviewed and not found are excluded,
        never scored zero.
      </p>
    </div>
  );
}
