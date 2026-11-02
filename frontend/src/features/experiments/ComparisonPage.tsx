import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { experimentsApi, qaSetsApi } from "@/api/resources";
import type { ComparisonRead, ComparisonVariantRead, ExperimentType } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { queryKeys } from "@/lib/queryClient";

import {
  corpusSnapshotLabels,
  defaultBaseline,
  formatDelta,
  formatValue,
  metricBars,
  notComparedLabels,
  winCounts,
  type Bar,
  type ComparisonColumn,
  type MetricBars,
} from "./comparison";
import {
  answerColumns,
  callMetricKeys,
  chunkMetricKeys,
  CUTOFFS,
  DEFAULT_CUTOFF,
  excludedDetail,
  metricKeys,
  sampleSize,
  setMetricKeys,
} from "./metrics";
import { experimentTypeLabel } from "./status";

interface Section {
  title: string;
  hint: string;
  columns: ComparisonColumn[];
}

const asColumns = (keys: string[]): ComparisonColumn[] => keys.map((key) => ({ key, label: key }));

/**
 * The sections of the comparison: what a retrieval experiment measures, and for a Q&A one
 * also the set of chunks it gathered, its calls and its answers. The two types are never
 * mixed on one page, since they do not measure the same thing.
 */
function sectionsFor(type: ExperimentType, cutoff: number): Section[] {
  const sections: Section[] = [
    {
      title: "Documents",
      hint: "Did the right documents come back? Stable whatever the chunking.",
      columns: asColumns(metricKeys(cutoff)),
    },
    {
      title: "Chunks",
      hint: "Did the evidence itself come back? A share of the confirmed evidence, so it reads across chunkings too; mind the question count.",
      columns: asColumns(chunkMetricKeys(cutoff)),
    },
  ];
  if (type === "qa") {
    sections.push(
      {
        title: "Retrieved set",
        hint: "Everything the system gathered over all its searches, each chunk counted once.",
        columns: asColumns(setMetricKeys(true)),
      },
      {
        title: "Searches",
        hint: "How many searches and hits it took to find the evidence.",
        columns: asColumns(callMetricKeys(true)),
      },
      {
        title: "Answers",
        hint: "Refusals, latency and tokens.",
        columns: answerColumns().map(({ key, label, stat }) => ({ key, label, stat })),
      },
    );
  }
  return sections;
}

function Select({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-xs text-ink-muted">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full min-w-44 rounded-md border border-line bg-paper-raised px-3 py-1.5"
      >
        {children}
      </select>
    </label>
  );
}

/** The change against the baseline, as an arrow and a signed number: never colour alone. */
function Delta({ bar, unit }: { bar: Bar; unit: MetricBars["unit"] }) {
  if (bar.delta === null || bar.verdict === null) return <span className="w-16" />;
  const tone =
    bar.verdict === "better"
      ? "text-teal"
      : bar.verdict === "worse"
        ? "text-danger"
        : "text-ink-muted";
  const arrow = bar.verdict === "same" ? "=" : bar.delta > 0 ? "▲" : "▼";
  return (
    <span className={`w-16 text-right ${tone}`} data-testid="delta">
      {arrow} {formatDelta(bar.delta, unit)}
    </span>
  );
}

function BarRow({
  bar,
  chart,
  baselineId,
}: {
  bar: Bar;
  chart: MetricBars;
  baselineId: string | null;
}) {
  const { variant, metric } = bar;
  const width = bar.value === null ? 0 : Math.min(100, (bar.value / chart.scaleMax) * 100);
  const tick =
    chart.baselineValue === null
      ? null
      : Math.min(100, (chart.baselineValue / chart.scaleMax) * 100);
  return (
    <div
      className="grid grid-cols-[minmax(7rem,11rem)_1fr_auto] items-center gap-3 py-1.5"
      data-testid={`bar-${variant.name}`}
    >
      <div className="min-w-0">
        <p className="truncate text-sm" title={variant.name}>
          {variant.name}
        </p>
        <p className="truncate text-xs text-ink-muted">
          {variant.experiment_name}
          {variant.variant_id === baselineId ? " · baseline" : ""}
        </p>
      </div>
      <div
        role="img"
        aria-label={`${variant.name}: ${formatValue(bar.value, chart.unit)}`}
        className="relative h-3 rounded-sm bg-ink/5"
      >
        <div
          className={`h-full rounded-r-sm ${bar.isBest ? "bg-teal" : "bg-ink-muted/40"}`}
          style={{ width: `${width}%` }}
        />
        {tick === null ? null : (
          <div
            className="absolute -top-1 -bottom-1 border-l-2 border-dashed border-ink"
            style={{ left: `${tick}%` }}
            title="Baseline"
          />
        )}
      </div>
      <div
        className="flex items-baseline justify-end gap-2 font-mono text-xs"
        title={metric ? excludedDetail(metric) : "No value"}
      >
        <span className="w-12 text-right text-sm font-semibold">
          {formatValue(bar.value, chart.unit)}
        </span>
        <Delta bar={bar} unit={chart.unit} />
        <span
          className={`w-16 text-right ${bar.smallerSample ? "font-semibold text-amber" : "text-ink-muted"}`}
          data-testid={bar.smallerSample ? "smaller-sample" : undefined}
        >
          {metric ? `${bar.smallerSample ? "⚠ " : ""}n=${sampleSize(metric)}` : "—"}
        </span>
      </div>
    </div>
  );
}

function MetricChart({ chart, baselineId }: { chart: MetricBars; baselineId: string | null }) {
  return (
    <div
      className="rounded-lg border border-line bg-paper-raised p-4"
      data-testid={`chart-${chart.column.label}`}
    >
      <div className="mb-1 flex flex-wrap items-baseline gap-x-3">
        <h3 className="font-mono text-sm font-semibold">{chart.column.label}</h3>
        <span className="text-xs text-ink-muted">
          {chart.lowerIsBetter ? "lower is better" : "higher is better"}
        </span>
      </div>
      <p className="mb-2 text-xs leading-5 text-ink-muted">{chart.description}</p>
      <div className="divide-y divide-line/60">
        {chart.bars.map((bar) => (
          <BarRow key={bar.variant.variant_id} bar={bar} chart={chart} baselineId={baselineId} />
        ))}
      </div>
    </div>
  );
}

/** How many metrics each variant leads: the answer to "which one is better" in one glance. */
function Summary({
  variants,
  charts,
  baselineId,
}: {
  variants: ComparisonVariantRead[];
  charts: MetricBars[];
  baselineId: string | null;
}) {
  const counts = winCounts(charts);
  const notCompared = notComparedLabels(charts);
  return (
    <section aria-label="Summary" className="mb-6" data-testid="comparison-summary">
      <h2 className="mb-1 text-sm font-semibold">Best on</h2>
      {notCompared.length > 0 ? (
        <p className="mb-2 text-xs text-ink-muted" data-testid="not-compared">
          Not counted, since only one variant has a value: {notCompared.join(", ")}.
        </p>
      ) : null}
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {variants.map((variant) => {
          const count = counts.get(variant.variant_id) ?? { wins: 0, of: 0, missing: 0 };
          const share = count.of === 0 ? 0 : (count.wins / count.of) * 100;
          return (
            <div
              key={variant.variant_id}
              className="rounded-lg border border-line bg-paper-raised p-3"
              data-testid={`summary-${variant.name}`}
            >
              <p className="truncate text-sm font-medium" title={variant.name}>
                {variant.name}{" "}
                {variant.variant_id === baselineId ? <Badge tone="info">baseline</Badge> : null}
              </p>
              <p className="truncate text-xs text-ink-muted">
                {variant.experiment_name} · {variant.chunking_configuration_name}
              </p>
              <div className="mt-2 h-2 rounded-sm bg-ink/5">
                <div className="h-full rounded-r-sm bg-teal" style={{ width: `${share}%` }} />
              </div>
              <p className="mt-1 font-mono text-xs">
                {count.wins} of {count.of} metrics
                {count.missing > 0 ? (
                  <span
                    className="ml-2 text-amber"
                    title="No value on these metrics, so it cannot lead them: typically the chunk-level ones, when no question has confirmed evidence under its chunking configuration."
                  >
                    ⚠ {count.missing} without a value
                  </span>
                ) : null}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Notices({ comparison }: { comparison: ComparisonRead }) {
  const corpora = corpusSnapshotLabels(comparison.variants);
  return (
    <>
      {corpora.length > 1 ? (
        <p
          className="mb-3 rounded-md bg-amber/15 p-3 text-xs leading-5"
          data-testid="corpus-notice"
        >
          These variants searched different corpus snapshots ({corpora.join(", ")}). The documents
          to search among are part of what is measured, so read the differences with care.
        </p>
      ) : null}
      {comparison.skipped.length > 0 ? (
        <p className="mb-3 text-xs text-ink-muted" data-testid="skipped-notice">
          Left out, with no finished run:{" "}
          {comparison.skipped.map((item, index) => (
            <span key={item.experiment_id}>
              {index > 0 ? ", " : ""}
              <Link to={`/experiments/${item.experiment_id}`} className="underline">
                {item.experiment_name}
              </Link>
            </span>
          ))}
          .
        </p>
      ) : null}
    </>
  );
}

function Legend() {
  return (
    <p className="mb-4 text-xs leading-5 text-ink-muted" data-testid="comparison-legend">
      <span className="mr-1 inline-block h-2 w-4 rounded-sm bg-teal align-middle" /> best on the
      metric ·{" "}
      <span className="mx-1 inline-block h-3 border-l-2 border-dashed border-ink align-middle" />
      baseline · ▲ ▼ change against the baseline, in points for a 0–1 score and in % for a time or a
      count, green when it is an improvement · <span className="text-amber">⚠ n</span> fewer
      questions counted than the variant with the most: that value rests on another set of
      questions. Hover a value for why questions were excluded.
    </p>
  );
}

/**
 * Side-by-side comparison of every variant run on one QA set snapshot. Each metric is a
 * small bar chart on a shared scale, so the best variant and the distance from the baseline
 * can be read at a glance; the number of questions behind each value stays on the row.
 */
export function ComparisonPage() {
  const [params, setParams] = useSearchParams();
  const qaSetId = params.get("qaSet") ?? "";
  const type: ExperimentType = params.get("type") === "qa" ? "qa" : "retrieval";
  const [cutoff, setCutoff] = useState<number>(DEFAULT_CUTOFF);
  const [baselineChoice, setBaselineChoice] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  const qaSets = useQuery({ queryKey: queryKeys.qaSets, queryFn: qaSetsApi.list });
  const snapshots = useQuery({
    queryKey: queryKeys.qaSetSnapshots(qaSetId),
    queryFn: () => qaSetsApi.snapshots(qaSetId),
    enabled: qaSetId !== "",
  });
  const snapshotItems = snapshots.data?.items;
  const requested = params.get("snapshot") ?? "";
  const snapshotId = snapshotItems?.some((item) => item.id === requested)
    ? requested
    : (snapshotItems?.[0]?.id ?? "");
  const comparison = useQuery({
    queryKey: queryKeys.comparison(snapshotId, type),
    queryFn: () => experimentsApi.compare(snapshotId, type),
    enabled: snapshotId !== "",
  });

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key === "qaSet") next.delete("snapshot");
    setParams(next);
    setBaselineChoice(null);
    setHidden(new Set());
  };

  const all = useMemo(() => comparison.data?.variants ?? [], [comparison.data]);
  const baselineId = all.some((variant) => variant.variant_id === baselineChoice)
    ? baselineChoice
    : defaultBaseline(all);
  const shown = all.filter((variant) => !hidden.has(variant.variant_id));
  const sections = sectionsFor(type, cutoff).map((section) => ({
    ...section,
    charts: section.columns.flatMap((column) => {
      const chart = metricBars(shown, all, column, baselineId);
      return chart ? [chart] : [];
    }),
  }));
  const allCharts = sections.flatMap((section) => section.charts);

  const toggle = (variantId: string) =>
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(variantId)) next.delete(variantId);
      else next.add(variantId);
      return next;
    });

  return (
    <div>
      <div className="mb-6">
        <Link to="/experiments" className="text-xs text-ink-muted hover:underline">
          ← Experiments
        </Link>
        <h1 className="mt-1 text-2xl font-semibold">Compare variants</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Every variant run on the same frozen questions, metric by metric. Each experiment counts
          with its latest finished run.
        </p>
      </div>

      <div className="mb-5 flex flex-wrap items-end gap-4">
        <Select label="QA set" value={qaSetId} onChange={(value) => setParam("qaSet", value)}>
          <option value="">Select a QA set…</option>
          {(qaSets.data?.items ?? []).map((qaSet) => (
            <option key={qaSet.id} value={qaSet.id}>
              {qaSet.name}
            </option>
          ))}
        </Select>
        <Select
          label="Snapshot"
          value={snapshotId}
          onChange={(value) => setParam("snapshot", value)}
        >
          {(snapshotItems ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {item.label} · {item.question_count} questions
            </option>
          ))}
        </Select>
        <div role="group" aria-label="Experiment type" className="flex gap-1">
          {(["retrieval", "qa"] as const).map((option) => (
            <Button
              key={option}
              variant={type === option ? "primary" : "secondary"}
              aria-pressed={type === option}
              onClick={() => setParam("type", option === "qa" ? "qa" : "")}
            >
              {experimentTypeLabel(option)}
            </Button>
          ))}
        </div>
        <Select
          label="Cutoff"
          value={String(cutoff)}
          onChange={(value) => setCutoff(Number(value))}
        >
          {CUTOFFS.map((option) => (
            <option key={option} value={option}>
              @{option}
            </option>
          ))}
        </Select>
        {all.length > 0 ? (
          <Select
            label="Baseline"
            value={baselineId ?? ""}
            onChange={(value) => setBaselineChoice(value)}
          >
            {all.map((variant) => (
              <option key={variant.variant_id} value={variant.variant_id}>
                {variant.name}
              </option>
            ))}
          </Select>
        ) : null}
      </div>

      {qaSetId === "" ? (
        <EmptyState
          title="Choose a QA set"
          body="The comparison puts side by side the variants of every experiment run on one frozen snapshot of its questions."
        />
      ) : null}
      {comparison.isError ? (
        <p className="text-sm text-danger">The comparison could not be loaded.</p>
      ) : null}
      {comparison.isSuccess && all.length === 0 ? (
        <>
          <Notices comparison={comparison.data} />
          <EmptyState
            title={`No finished ${experimentTypeLabel(type)} experiment`}
            body="Run an experiment of this type on the snapshot, or pick another snapshot or type."
          />
        </>
      ) : null}

      {comparison.isSuccess && all.length > 0 ? (
        <div data-testid="comparison">
          <Notices comparison={comparison.data} />
          <details className="mb-4 text-sm">
            <summary className="cursor-pointer font-medium">
              Variants shown ({shown.length} of {all.length})
            </summary>
            <ul className="mt-2 grid gap-1 sm:grid-cols-2">
              {all.map((variant) => (
                <li key={variant.variant_id}>
                  <label className="flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      checked={!hidden.has(variant.variant_id)}
                      onChange={() => toggle(variant.variant_id)}
                    />
                    <span className="truncate" title={variant.name}>
                      {variant.name}
                    </span>
                    <span className="text-ink-muted">· {variant.experiment_name}</span>
                  </label>
                </li>
              ))}
            </ul>
          </details>
          <Legend />
          <Summary variants={shown} charts={allCharts} baselineId={baselineId} />
          {sections.map((section) =>
            section.charts.length === 0 ? null : (
              <section
                key={section.title}
                className="mb-8"
                data-testid={`section-${section.title}`}
              >
                <h2 className="text-lg font-semibold">{section.title}</h2>
                <p className="mb-3 text-xs text-ink-muted">{section.hint}</p>
                <div className="grid gap-4 xl:grid-cols-2">
                  {section.charts.map((chart) => (
                    <MetricChart key={chart.column.label} chart={chart} baselineId={baselineId} />
                  ))}
                </div>
              </section>
            ),
          )}
        </div>
      ) : null}
    </div>
  );
}
