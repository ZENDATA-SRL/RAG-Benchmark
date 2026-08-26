"use client";

import { useEffect, useMemo, useState } from "react";
import { Shell } from "@/components/layout/Shell";
import { Card } from "@/components/ui/Card";
import { Divider } from "@/components/ui/Divider";
import { api } from "@/lib/api";
import type { Dataset, Evaluation } from "@/lib/api/types";
import { transformEvaluation, splitMetricsByGroup } from "@/lib/evals/transform";
import { MetricCard } from "@/components/evals/MetricCard";
import { coverageToRagMetrics } from "@/lib/evals/coverage";

function Select({
  value,
  onChange,
  options,
  placeholder,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string }>;
  placeholder: string;
  disabled?: boolean;
}) {
  return (
    <select
      className={[
        "w-full px-3 py-2 pr-8 bg-eggshell border border-linen rounded-md",
        "font-sans text-sm text-charcoal",
        "focus:outline-none focus:border-stone focus:ring-1 focus:ring-stone",
        "transition-colors duration-150 appearance-none cursor-pointer",
        disabled ? "opacity-60 cursor-not-allowed" : "",
      ].join(" ")}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
    >
      <option value="" disabled>
        {placeholder}
      </option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export default function EvalsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetsState, setDatasetsState] = useState<"loading" | "idle" | "error">("loading");
  const [datasetsError, setDatasetsError] = useState("");

  const [datasetId, setDatasetId] = useState<string>("");
  const [evals, setEvals] = useState<Evaluation | null>(null);
  const [evalsState, setEvalsState] = useState<"idle" | "loading" | "error">("idle");
  const [evalsError, setEvalsError] = useState("");

  const [coverageState, setCoverageState] = useState<"idle" | "loading" | "error">("idle");
  const [coverageError, setCoverageError] = useState("");
  const [coverageByExperimentKey, setCoverageByExperimentKey] = useState<
    Record<string, import("@/lib/api/types").ExperimentQuestionDocumentChunkCoverageRow[]>
  >({});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setDatasetsState("loading");
      setDatasetsError("");
      try {
        const res = await api.datasets.list();
        if (cancelled) return;
        setDatasets(res);
        setDatasetsState("idle");
      } catch (e) {
        if (cancelled) return;
        setDatasets([]);
        setDatasetsState("error");
        setDatasetsError(e instanceof Error ? e.message : "Failed to load datasets.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!datasetId) {
        setEvals(null);
        setEvalsState("idle");
        setEvalsError("");
        setCoverageByExperimentKey({});
        setCoverageState("idle");
        setCoverageError("");
        return;
      }
      setEvalsState("loading");
      setEvalsError("");
      try {
        const res = await api.evals.getDataset(datasetId);
        if (cancelled) return;
        setEvals(res);
        setEvalsState("idle");
      } catch (e) {
        if (cancelled) return;
        setEvals(null);
        setEvalsState("error");
        setEvalsError(e instanceof Error ? e.message : "Failed to load evaluations.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  const datasetOptions = useMemo(
    () => datasets.map((d) => ({ value: d.id, label: d.name })),
    [datasets],
  );

  const transformed = useMemo(() => (evals ? transformEvaluation(evals) : null), [evals]);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!datasetId || !transformed) {
        setCoverageByExperimentKey({});
        setCoverageState("idle");
        setCoverageError("");
        return;
      }

      setCoverageState("loading");
      setCoverageError("");
      setCoverageByExperimentKey({});

      try {
        const all = await api.experiments.list();
        const inDataset = all.filter((e) => e.dataset_id === datasetId);
        const idByName = new Map(inDataset.map((e) => [e.name, e.id]));

        const pairs = transformed.experimentKeys
          .map((k) => {
            // `experimentKey` is `${name} · ${cfgId}` or just `${name}`.
            const name = k.split(" · ")[0] ?? k;
            const id = idByName.get(name);
            return id ? ({ expKey: k, expId: id } as const) : null;
          })
          .filter(Boolean) as Array<{ expKey: string; expId: string }>;

        const results = await Promise.allSettled(
          pairs.map(async ({ expKey, expId }) => {
            const rows = await api.experiments.questionDocumentChunkCoverage(expId);
            return { expKey, rows };
          }),
        );

        if (cancelled) return;

        const next: Record<
          string,
          import("@/lib/api/types").ExperimentQuestionDocumentChunkCoverageRow[]
        > = {};
        const errs: string[] = [];

        for (const r of results) {
          if (r.status === "fulfilled") next[r.value.expKey] = r.value.rows;
          else errs.push(r.reason instanceof Error ? r.reason.message : "Coverage request failed.");
        }

        setCoverageByExperimentKey(next);
        if (errs.length > 0) {
          setCoverageState("error");
          setCoverageError(errs[0] ?? "Failed to load coverage metrics.");
        } else {
          setCoverageState("idle");
          setCoverageError("");
        }
      } catch (e) {
        if (cancelled) return;
        setCoverageByExperimentKey({});
        setCoverageState("error");
        setCoverageError(e instanceof Error ? e.message : "Failed to load coverage metrics.");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [datasetId, transformed]);

  const coverageRagMetrics = useMemo(() => {
    if (!transformed) return null;
    return coverageToRagMetrics({ byExperimentCoverage: coverageByExperimentKey });
  }, [coverageByExperimentKey, transformed]);

  const mergedMetrics = useMemo(() => {
    if (!transformed) return null;
    return {
      ...transformed.metrics,
      ...(coverageRagMetrics ?? {}),
    };
  }, [coverageRagMetrics, transformed]);

  const grouped = useMemo(
    () => (mergedMetrics ? splitMetricsByGroup(mergedMetrics) : null),
    [mergedMetrics],
  );

  const evalMetricNames = useMemo(() => {
    if (!grouped) return [];
    return Object.keys(grouped.evals).sort((a, b) => a.localeCompare(b));
  }, [grouped]);

  const ragMetricNames = useMemo(() => {
    if (!grouped) return [];
    return Object.keys(grouped.rag).sort((a, b) => a.localeCompare(b));
  }, [grouped]);

  return (
    <Shell contentWidth="wide">
      <div className="space-y-6">
        <header className="space-y-2">
          <div className="font-sans text-sm text-ash">Evals</div>
          <h1 className="font-serif text-3xl tracking-tight text-ink leading-snug">Evaluation graphs</h1>
          <div className="font-sans text-sm text-ash">
            Select a dataset to compare metric performance across experiments/configurations.
          </div>
        </header>

        <Divider />

        <Card>
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="md:col-span-2">
                <div className="font-sans text-xs text-ash mb-2">Dataset</div>
                <Select
                  value={datasetId}
                  onChange={setDatasetId}
                  options={datasetOptions}
                  placeholder={datasetsState === "loading" ? "Loading datasets…" : "Select a dataset…"}
                  disabled={datasetsState !== "idle"}
                />
                {datasetsState === "error" ? (
                  <div className="mt-2 font-sans text-sm text-red-700">{datasetsError}</div>
                ) : null}
              </div>
              <div className="md:col-span-1">
                <div className="font-sans text-xs text-ash mb-2">Status</div>
                <div className="rounded-lg border border-linen bg-paper px-4 py-3">
                  <div className="font-sans text-sm font-medium text-charcoal">
                    {evalsState === "loading"
                      ? "Loading…"
                      : evalsState === "error"
                        ? "Error"
                        : datasetId
                          ? "Ready"
                          : "Choose a dataset"}
                  </div>
                  <div className="mt-1 font-sans text-sm text-ash">
                    {evalsState === "loading"
                      ? "Fetching /evals/{dataset_id} and assembling metrics."
                      : evalsState === "error"
                        ? "Could not load evaluations for this dataset."
                        : datasetId
                          ? "Scroll down to see charts."
                          : "Metrics appear after selection."}
                  </div>
                </div>
              </div>
            </div>

            {evalsState === "error" ? (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
                <div className="font-sans text-sm font-medium text-red-700">Failed to load</div>
                <div className="mt-1 font-sans text-sm text-red-700/90">{evalsError}</div>
              </div>
            ) : null}

            {datasetId && evalsState === "idle" ? (
              <div className="rounded-lg border border-linen bg-paper px-4 py-3">
                <div className="font-sans text-sm font-medium text-charcoal">RAG coverage metrics</div>
                <div className="mt-1 font-sans text-sm text-ash">
                  {coverageState === "loading"
                    ? "Loading /core/experiment/{id}/question-document-chunk-coverage…"
                    : coverageState === "error"
                      ? "Some coverage metrics failed to load; showing what’s available."
                      : "Loaded coverage metrics for matching experiments."}
                </div>
                {coverageState === "error" && coverageError ? (
                  <div className="mt-2 font-sans text-sm text-red-700">{coverageError}</div>
                ) : null}
              </div>
            ) : null}
          </div>
        </Card>

        {transformed && grouped ? (
          <div className="space-y-10">
            <section className="space-y-4">
              <div className="space-y-1">
                <div className="font-serif text-2xl tracking-tight text-ink">Evals</div>
                <div className="font-sans text-sm text-ash">
                  Metrics grouped by score name, compared across experiments/configurations.
                </div>
              </div>
              {evalMetricNames.length === 0 ? (
                <Card>
                  <div className="font-sans text-sm text-ash">No eval metrics found for this dataset.</div>
                </Card>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {evalMetricNames.map((name) => (
                    <MetricCard key={name} metricName={name} byExperiment={grouped.evals[name]!.byExperiment} />
                  ))}
                </div>
              )}
            </section>

            <section className="space-y-4">
              <div className="space-y-1">
                <div className="font-serif text-2xl tracking-tight text-ink">RAG evaluations</div>
                <div className="font-sans text-sm text-ash">
                  Same payload, split by metric-name heuristic (adjustable later if needed).
                </div>
              </div>
              {ragMetricNames.length === 0 ? (
                <Card>
                  <div className="font-sans text-sm text-ash">No RAG evaluation metrics found for this dataset.</div>
                </Card>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {ragMetricNames.map((name) => (
                    <MetricCard key={name} metricName={name} byExperiment={grouped.rag[name]!.byExperiment} />
                  ))}
                </div>
              )}
            </section>
          </div>
        ) : null}
      </div>
    </Shell>
  );
}

