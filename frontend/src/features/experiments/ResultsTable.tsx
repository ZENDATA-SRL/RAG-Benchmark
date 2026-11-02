import { useState } from "react";

import type { ResultGroupRead, RunResultsRead, VariantResultRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { TableFrame } from "@/components/ui/TableFrame";

import {
  answerColumns,
  callMetricKeys,
  chunkMetricKeys,
  allVariants,
  describeCoverage,
  excludedDetail,
  findMetric,
  formatCeiling,
  formatAnswerMetric,
  formatMetric,
  groupsOf,
  metricGuide,
  metricKeys,
  setMetricKeys,
  type MetricGuideEntry,
} from "./metrics";

/** The explanation of every column on screen, closed by default: it is reference, not content. */
function MetricGuide({ entries }: { entries: MetricGuideEntry[] }) {
  if (entries.length === 0) return null;
  return (
    <details className="mt-3 text-xs" data-testid="metric-guide">
      <summary className="cursor-pointer font-medium">How to read these metrics</summary>
      <dl className="mt-2 grid gap-x-4 gap-y-2 sm:grid-cols-[max-content_1fr]">
        {entries.map((entry) => (
          <div key={entry.label} className="contents">
            <dt className="font-mono">{entry.label}</dt>
            <dd className="text-ink-muted">
              {entry.description} <span className="italic">({entry.reading})</span>
            </dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

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

/** A header cell spanning the columns of one family of metrics, shown on Q&A runs only. */
function SectionHeader({ label, span, tone }: { label: string; span: number; tone?: string }) {
  if (span === 0) return null;
  return (
    <th colSpan={span} className={`px-4 pt-2 font-semibold ${tone ?? ""}`}>
      {label}
    </th>
  );
}

/**
 * Rows are variants, grouped by the chunking configuration they search: chunk-level metrics
 * only compare within a group. Selecting variants of different groups keeps the
 * document-level columns and says why the chunk-level ones are gone.
 *
 * A retrieval run shows the ranked metrics only. A Q&A run adds the metrics on the set of
 * chunks its executions gathered, on their calls and on the answers (refusals, latency,
 * tokens), in sections of their own: there the ranked metrics are those of each execution's
 * first call.
 */
export function ResultsTable({ results, cutoff }: { results: RunResultsRead; cutoff: number }) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [comparing, setComparing] = useState(false);
  const corpus = results.corpus_snapshot;
  const qaSnapshot = results.qa_set_snapshot;
  const crossGroup = comparing && groupsOf(results.groups, selected).length > 1;
  const qa = results.experiment_type === "qa";
  const documentKeys = metricKeys(cutoff);
  const chunkKeys = crossGroup ? [] : chunkMetricKeys(cutoff);
  const setKeys = qa ? setMetricKeys(!crossGroup) : [];
  const callKeys = qa ? callMetricKeys(!crossGroup) : [];
  const answers = qa ? answerColumns() : [];
  const valueKeys = [...documentKeys, ...chunkKeys, ...setKeys, ...callKeys];
  const span = 2 + valueKeys.length + answers.length;
  const guide = metricGuide(allVariants(results.groups), [
    ...valueKeys.map((key) => ({ key, label: key })),
    ...answers.map(({ key, label, stat }) => ({ key, label, stat })),
  ]);
  const describe = (key: string) => guide.find((entry) => entry.label === key)?.description;
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
          detail={`${qaSnapshot.label}${qaSnapshot.question_count != null ? ` · ${qaSnapshot.question_count} questions` : ""}`}
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
            {qa ? (
              <tr data-testid="result-sections">
                <th colSpan={2} />
                <SectionHeader
                  label="Ranked, first call"
                  span={documentKeys.length + chunkKeys.length}
                />
                <SectionHeader label="Set" span={setKeys.length} tone="bg-amber/5" />
                <SectionHeader label="Calls" span={callKeys.length} tone="bg-ink/5" />
                <SectionHeader label="Answer" span={answers.length} tone="bg-rust/5" />
              </tr>
            ) : null}
            <tr>
              <th className="w-8 px-2 py-2" />
              <th className="px-4 py-2 font-medium">Variant</th>
              {documentKeys.map((key) => (
                <th key={key} title={describe(key)} className="px-4 py-2 font-medium">
                  {key}
                </th>
              ))}
              {chunkKeys.map((key) => (
                <th key={key} title={describe(key)} className="bg-teal/5 px-4 py-2 font-medium">
                  {key}
                </th>
              ))}
              {setKeys.map((key) => (
                <th key={key} title={describe(key)} className="bg-amber/5 px-4 py-2 font-medium">
                  {key}
                </th>
              ))}
              {callKeys.map((key) => (
                <th key={key} title={describe(key)} className="bg-ink/5 px-4 py-2 font-medium">
                  {key}
                </th>
              ))}
              {answers.map((column) => (
                <th
                  key={column.label}
                  title={describe(column.label)}
                  className="bg-rust/5 px-4 py-2 font-medium"
                >
                  {column.label}
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
                  {valueKeys.map((key) => {
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
                  {answers.map((column) => {
                    const metric = findMetric(variant, column.key);
                    return (
                      <td
                        key={column.label}
                        title={excludedDetail(metric)}
                        className="px-4 py-3 font-mono text-xs whitespace-nowrap"
                      >
                        {formatAnswerMetric(metric, column)}
                      </td>
                    );
                  })}
                </tr>
              )),
            ])}
          </tbody>
        </table>
      </TableFrame>
      <MetricGuide entries={guide} />
      <p className="mt-2 text-xs text-ink-muted">
        Each value is the mean over questions (the median for the rank and call-position metrics),
        with (questions counted / questions asked); hover a value for why questions were excluded
        and a column name for what it measures. A question with no value, such as a first relevant
        rank when nothing relevant was found, is not counted. Chunk-level values count only the
        questions whose evidence was confirmed under that configuration: not reviewed and not found
        are excluded, never scored zero.
        {qa
          ? " Set metrics count each distinct chunk once; read them next to the set size and the share of repeated hits. Refusal accuracy counts the unanswerable questions too: refusing them is the right answer."
          : null}
      </p>
    </div>
  );
}
