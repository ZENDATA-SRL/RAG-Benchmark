"use client";

import { useMemo, useState } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { BarMetricChart } from "./BarMetricChart";
import { BoxMetricChart } from "./BoxMetricChart";

type PlotKind = "bar" | "box";

function Segmented({
  value,
  onChange,
}: {
  value: PlotKind;
  onChange: (v: PlotKind) => void;
}) {
  const base =
    "inline-flex rounded-md border border-linen bg-paper overflow-hidden shadow-xs";

  const item = (active: boolean) =>
    [
      "px-3 py-2 font-sans text-sm font-medium transition-colors duration-150",
      active ? "bg-linen text-charcoal" : "bg-transparent text-ash hover:bg-linen/60 hover:text-charcoal",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-coral focus-visible:ring-offset-2",
    ].join(" ");

  return (
    <div className={base} role="group" aria-label="Plot type">
      <button type="button" className={item(value === "bar")} onClick={() => onChange("bar")}>
        Bar
      </button>
      <button type="button" className={item(value === "box")} onClick={() => onChange("box")}>
        Box
      </button>
    </div>
  );
}

export function MetricCard({
  metricName,
  byExperiment,
}: {
  metricName: string;
  byExperiment: Record<string, number[]>;
}) {
  const [plot, setPlot] = useState<PlotKind>("bar");

  const totalSamples = useMemo(() => {
    let n = 0;
    for (const arr of Object.values(byExperiment)) n += arr.length;
    return n;
  }, [byExperiment]);

  const experimentCount = useMemo(() => Object.keys(byExperiment).length, [byExperiment]);

  return (
    <Card>
      <div className="space-y-4">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
          <div className="min-w-0">
            <div className="font-serif text-xl tracking-tight text-ink break-words">{metricName}</div>
            <div className="mt-1 font-sans text-sm text-ash">
              {experimentCount} configs · {totalSamples} samples
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Segmented value={plot} onChange={setPlot} />
            <Button
              variant="secondary"
              className="px-3 py-2"
              onClick={() => setPlot((p) => (p === "bar" ? "box" : "bar"))}
              aria-label="Toggle plot type"
            >
              Toggle
            </Button>
          </div>
        </div>

        <div className="rounded-xl border border-linen bg-paper p-4">
          {plot === "bar" ? <BarMetricChart byExperiment={byExperiment} /> : <BoxMetricChart byExperiment={byExperiment} />}
        </div>
      </div>
    </Card>
  );
}

