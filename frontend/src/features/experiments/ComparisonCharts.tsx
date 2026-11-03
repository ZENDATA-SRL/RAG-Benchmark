import { useEffect, useRef, useState, type RefObject } from "react";

import type { ComparisonVariantRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";

import { formatDelta, formatValue, type Bar, type MetricBars } from "./comparison";
import { excludedDetail, sampleSize } from "./metrics";

// One colour per variant, in the order the variants are listed; they repeat past eight.
const SERIES_COLORS = [
  "#2f6f6a",
  "#c45c26",
  "#c4922a",
  "#4a5f9a",
  "#8a4f7d",
  "#6b8f3a",
  "#9b2c2c",
  "#5c564c",
];

function seriesColor(index: number): string {
  return SERIES_COLORS[index % SERIES_COLORS.length];
}

/** The change against the baseline, as an arrow and a signed number: never colour alone. */
export function Delta({ bar, unit }: { bar: Bar; unit: MetricBars["unit"] }) {
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

/** The width of an element, followed as the window or the layout changes. */
function useMeasuredWidth(): [RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

const PLOT_HEIGHT = 220;
const AXIS_WIDTH = 34;
const LABEL_HEIGHT = 44;
const TOP_PADDING = 14;
const TICKS = [0, 0.25, 0.5, 0.75, 1];

/**
 * Every 0–1 metric of a section on one chart: the metrics along the axis, one column per
 * variant in each group. The shared scale makes the metrics comparable by eye, which the
 * one-chart-per-metric view could not do without scrolling.
 */
export function GroupedChart({
  charts,
  variants,
  baselineId,
}: {
  charts: MetricBars[];
  variants: ComparisonVariantRead[];
  baselineId: string | null;
}) {
  const [frame, available] = useMeasuredWidth();
  // The groups share the whole width of the section, so the chart fills the screen whatever
  // the number of metrics; below a minimum width it scrolls instead of squeezing the labels.
  const minGroup = Math.max(72, variants.length * 19 + 24);
  const groupWidth = Math.max(minGroup, (available - AXIS_WIDTH) / charts.length);
  const barWidth = Math.min(44, (groupWidth - 24) / variants.length - 3);
  const width = AXIS_WIDTH + charts.length * groupWidth;
  const height = TOP_PADDING + PLOT_HEIGHT + LABEL_HEIGHT;
  const y = (value: number) => TOP_PADDING + PLOT_HEIGHT * (1 - Math.min(1, Math.max(0, value)));
  const showValues = barWidth >= 26;

  return (
    <div data-testid="grouped-chart">
      <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label="Variants">
        {variants.map((variant, index) => (
          <li key={variant.variant_id} className="flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ backgroundColor: seriesColor(index) }}
            />
            <span>{variant.name}</span>
            {variant.variant_id === baselineId ? <Badge tone="info">baseline</Badge> : null}
          </li>
        ))}
      </ul>
      <div ref={frame} className="overflow-x-auto">
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label="Metrics by variant"
          className="max-w-none"
        >
          {TICKS.map((tick) => (
            <g key={tick}>
              <line
                x1={AXIS_WIDTH}
                x2={width}
                y1={y(tick)}
                y2={y(tick)}
                className="stroke-line"
                strokeDasharray={tick === 0 ? undefined : "3 3"}
              />
              <text
                x={AXIS_WIDTH - 6}
                y={y(tick) + 3}
                textAnchor="end"
                className="fill-ink-muted font-mono text-[10px]"
              >
                {tick.toFixed(tick === 0 || tick === 1 ? 0 : 2)}
              </text>
            </g>
          ))}
          {charts.map((chart, groupIndex) => {
            const left = AXIS_WIDTH + groupIndex * groupWidth;
            const inner = variants.length * (barWidth + 3) - 3;
            const start = left + (groupWidth - inner) / 2;
            const smaller = chart.bars.some((bar) => bar.smallerSample);
            return (
              <g key={chart.column.label}>
                <title>{chart.description}</title>
                {chart.bars.map((bar, index) => {
                  const x = start + index * (barWidth + 3);
                  const value = bar.value ?? 0;
                  return (
                    <g key={bar.variant.variant_id}>
                      <title>
                        {`${bar.variant.name} · ${chart.column.label}: ${formatValue(bar.value, "ratio")}${
                          bar.metric ? ` (n=${sampleSize(bar.metric)})` : ""
                        }`}
                      </title>
                      {bar.value === null ? null : (
                        <rect
                          x={x}
                          y={y(value)}
                          width={barWidth}
                          height={PLOT_HEIGHT - (y(value) - TOP_PADDING)}
                          rx={2}
                          fill={seriesColor(variants.indexOf(bar.variant))}
                          opacity={bar.smallerSample ? 0.55 : 1}
                        />
                      )}
                      {showValues && bar.value !== null ? (
                        <text
                          x={x + barWidth / 2}
                          y={y(value) - 3}
                          textAnchor="middle"
                          className="fill-ink font-mono text-[9px]"
                        >
                          {bar.isBest ? "★" : ""}
                          {formatValue(bar.value, "ratio")}
                        </text>
                      ) : null}
                    </g>
                  );
                })}
                <text
                  x={left + groupWidth / 2}
                  y={TOP_PADDING + PLOT_HEIGHT + 16}
                  textAnchor="middle"
                  className="fill-ink font-mono text-[11px]"
                >
                  {chart.column.label}
                </text>
                {smaller ? (
                  <text
                    x={left + groupWidth / 2}
                    y={TOP_PADDING + PLOT_HEIGHT + 30}
                    textAnchor="middle"
                    className="fill-amber text-[10px]"
                  >
                    ⚠ smaller n
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
      </div>
      <p className="mt-1 text-xs text-ink-muted">
        {showValues ? "★ best on the metric. " : ""}Faded columns rest on fewer questions than the
        variant with the most. Hover a column for the exact value and sample.
      </p>
    </div>
  );
}

/**
 * Metrics that are not a 0–1 score (a rank, a count, a time) do not share a scale, so they
 * are read as a table: one row per metric, one column per variant, the best highlighted.
 */
export function MetricTable({
  charts,
  variants,
  baselineId,
}: {
  charts: MetricBars[];
  variants: ComparisonVariantRead[];
  baselineId: string | null;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-paper-raised">
      <table className="w-full border-collapse text-sm" data-testid="metric-table">
        <thead>
          <tr className="border-b border-line text-left text-xs text-ink-muted">
            <th className="px-3 py-2 font-medium">Metric</th>
            {variants.map((variant, index) => (
              <th key={variant.variant_id} className="px-3 py-2 font-medium">
                <span className="flex items-center gap-1.5">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-sm"
                    style={{ backgroundColor: seriesColor(index) }}
                  />
                  <span className="max-w-40 truncate text-ink" title={variant.name}>
                    {variant.name}
                  </span>
                  {variant.variant_id === baselineId ? <Badge tone="info">baseline</Badge> : null}
                </span>
                <span className="block max-w-48 truncate" title={variant.experiment_name}>
                  {variant.experiment_name}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {charts.map((chart) => (
            <tr
              key={chart.column.label}
              className="border-b border-line/60 last:border-0"
              data-testid={`row-${chart.column.label}`}
            >
              <th scope="row" className="px-3 py-2 text-left align-top" title={chart.description}>
                <span className="font-mono text-xs font-semibold">{chart.column.label}</span>
                <span className="block text-xs font-normal text-ink-muted">
                  {chart.lowerIsBetter ? "lower is better" : "higher is better"}
                </span>
              </th>
              {chart.bars.map((bar) => (
                <td
                  key={bar.variant.variant_id}
                  className={`px-3 py-2 align-top font-mono ${bar.isBest ? "bg-teal/10" : ""}`}
                  title={bar.metric ? excludedDetail(bar.metric) : "No value"}
                >
                  <span className="font-semibold">
                    {bar.isBest ? "★ " : ""}
                    {formatValue(bar.value, chart.unit)}
                  </span>
                  <span className="flex items-baseline gap-2 text-xs">
                    <Delta bar={bar} unit={chart.unit} />
                    <span
                      className={bar.smallerSample ? "font-semibold text-amber" : "text-ink-muted"}
                    >
                      {bar.metric
                        ? `${bar.smallerSample ? "⚠ " : ""}n=${sampleSize(bar.metric)}`
                        : "—"}
                    </span>
                  </span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
