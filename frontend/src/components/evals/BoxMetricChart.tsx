"use client";

import { boxStats } from "@/lib/evals/stats";
import { colorForKey, rgba } from "@/lib/evals/colors";

type Row = {
  experiment: string;
  samples: number[];
};

function fmt(n: number) {
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(4);
}

export function BoxMetricChart({
  byExperiment,
}: {
  byExperiment: Record<string, number[]>;
}) {
  const rows: Row[] = Object.entries(byExperiment).map(([experiment, samples]) => ({
    experiment,
    samples,
  }));

  const stats = rows
    .map((r) => ({ experiment: r.experiment, n: r.samples.length, s: boxStats(r.samples) }))
    .filter((x) => x.s);

  if (stats.length === 0) {
    return <div className="font-sans text-sm text-ash">No samples available.</div>;
  }

  let globalMin = Infinity;
  let globalMax = -Infinity;
  for (const r of stats) {
    const s = r.s!;
    globalMin = Math.min(globalMin, s.min);
    globalMax = Math.max(globalMax, s.max);
  }
  if (globalMin === globalMax) {
    globalMin -= 1;
    globalMax += 1;
  }

  const width = 640;
  const heightPer = 42;
  const leftLabel = 220;
  const rightPad = 16;
  const topPad = 10;
  const plotW = width - leftLabel - rightPad;
  const h = topPad * 2 + stats.length * heightPer;

  const x = (v: number) => leftLabel + ((v - globalMin) / (globalMax - globalMin)) * plotW;

  return (
    <div className="w-full overflow-x-auto">
      <svg width={width} height={h} role="img">
        <rect x={0} y={0} width={width} height={h} fill="transparent" />
        <line
          x1={leftLabel}
          x2={width - rightPad}
          y1={topPad}
          y2={topPad}
          stroke="rgba(29, 29, 26, 0.08)"
        />
        <line
          x1={leftLabel}
          x2={width - rightPad}
          y1={h - topPad}
          y2={h - topPad}
          stroke="rgba(29, 29, 26, 0.08)"
        />

        {stats.map((r, idx) => {
          const s = r.s!;
          const color = colorForKey(r.experiment);
          const y = topPad + idx * heightPer + heightPer / 2;
          const yTop = y - 9;
          const yBot = y + 9;

          const xMin = x(s.min);
          const xQ1 = x(s.q1);
          const xMed = x(s.median);
          const xQ3 = x(s.q3);
          const xMax = x(s.max);

          return (
            <g key={r.experiment}>
              <text
                x={leftLabel - 10}
                y={y + 4}
                textAnchor="end"
                fontFamily="var(--font-sans)"
                fontSize={12}
                fill="rgba(29, 29, 26, 0.75)"
              >
                {r.experiment}
              </text>

              <line x1={xMin} x2={xMax} y1={y} y2={y} stroke="rgba(29, 29, 26, 0.25)" />
              <line x1={xMin} x2={xMin} y1={yTop} y2={yBot} stroke="rgba(29, 29, 26, 0.25)" />
              <line x1={xMax} x2={xMax} y1={yTop} y2={yBot} stroke="rgba(29, 29, 26, 0.25)" />

              <rect
                x={Math.min(xQ1, xQ3)}
                y={yTop}
                width={Math.max(1, Math.abs(xQ3 - xQ1))}
                height={yBot - yTop}
                fill={rgba(color, 0.18)}
                stroke={rgba(color, 0.9)}
                rx={6}
              />
              <line x1={xMed} x2={xMed} y1={yTop} y2={yBot} stroke={rgba(color, 0.95)} />

              <text
                x={width - rightPad}
                y={y + 4}
                textAnchor="end"
                fontFamily="var(--font-mono)"
                fontSize={11}
                fill="rgba(29, 29, 26, 0.55)"
              >
                n={r.n} · [{fmt(s.min)}, {fmt(s.q1)}, {fmt(s.median)}, {fmt(s.q3)}, {fmt(s.max)}]
              </text>
            </g>
          );
        })}

        <g>
          <text
            x={leftLabel}
            y={h - 2}
            textAnchor="start"
            fontFamily="var(--font-mono)"
            fontSize={11}
            fill="rgba(29, 29, 26, 0.55)"
          >
            {fmt(globalMin)}
          </text>
          <text
            x={width - rightPad}
            y={h - 2}
            textAnchor="end"
            fontFamily="var(--font-mono)"
            fontSize={11}
            fill="rgba(29, 29, 26, 0.55)"
          >
            {fmt(globalMax)}
          </text>
        </g>
      </svg>
    </div>
  );
}

