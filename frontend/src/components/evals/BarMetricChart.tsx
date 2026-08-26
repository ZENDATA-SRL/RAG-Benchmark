"use client";

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
} from "recharts";
import { mean } from "@/lib/evals/stats";
import { colorForKey } from "@/lib/evals/colors";

export function BarMetricChart({
  byExperiment,
}: {
  byExperiment: Record<string, number[]>;
}) {
  const data = Object.entries(byExperiment).map(([experiment, samples]) => ({
    experiment,
    value: mean(samples) ?? 0,
    n: samples.length,
  }));

  return (
    <div className="h-[240px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 16, left: 8 }}>
          <CartesianGrid stroke="rgba(29, 29, 26, 0.08)" strokeDasharray="3 3" />
          <XAxis
            dataKey="experiment"
            tick={{ fill: "rgba(29, 29, 26, 0.70)", fontSize: 12 }}
            axisLine={{ stroke: "rgba(29, 29, 26, 0.12)" }}
            tickLine={{ stroke: "rgba(29, 29, 26, 0.12)" }}
            interval={0}
            angle={-20}
            textAnchor="end"
            height={60}
          />
          <YAxis
            tick={{ fill: "rgba(29, 29, 26, 0.70)", fontSize: 12 }}
            axisLine={{ stroke: "rgba(29, 29, 26, 0.12)" }}
            tickLine={{ stroke: "rgba(29, 29, 26, 0.12)" }}
          />
          <Tooltip
            contentStyle={{
              background: "#faf9f5",
              border: "1px solid #e8e6dc",
              borderRadius: 8,
              boxShadow: "0 4px 12px rgba(29,29,26,0.05)",
              fontFamily: "var(--font-sans)",
              fontSize: 12,
              color: "#1d1d1a",
            }}
            formatter={(v: unknown, _name, item: any) => {
              const n = item?.payload?.n;
              return [typeof v === "number" ? v.toFixed(4) : String(v), `mean (n=${n ?? 0})`];
            }}
          />
          <Bar dataKey="value" radius={[6, 6, 0, 0]}>
            {data.map((d) => (
              <Cell key={d.experiment} fill={colorForKey(d.experiment)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

