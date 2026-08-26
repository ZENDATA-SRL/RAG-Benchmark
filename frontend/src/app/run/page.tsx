"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Shell } from "@/components/layout/Shell";
import { Card } from "@/components/ui/Card";
import { Divider } from "@/components/ui/Divider";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { RagConfigEditor } from "@/components/config/RagConfigEditor";
import { RagConfigSummary } from "@/components/config/RagConfigSummary";
import { Select } from "@/components/ui/Select";
import { api, ApiError } from "@/lib/api";
import type { Dataset, OCRModel, ChunkerStrategy, RAGConfig, RAGConfigSchema, SolverStrategy } from "@/lib/api";

const defaultSchema: RAGConfigSchema = {
  name: "",
  ocr: { model: "pypdf" as OCRModel },
  chunker: {
    strategy: "recursive_character" as ChunkerStrategy,
    chunk_size: 1000,
    overlap_size: 0,
  },
  embedder: { provider: "openai", model: "text-embedding-3-large" },
  vectordb: { backend: "chromadb", config: {} },
  llm: { provider: "openai", model: "gpt-4.1-mini" },
  solver: {
    top_k: 10,
    reranking: null,
    hyde: false,
    hybrid: false,
    strategy: "single_shot" as SolverStrategy,
  },
};

function toSchema(c: Partial<RAGConfig> | null | undefined): RAGConfigSchema {
  return {
    name: (c?.name ?? "").trim(),
    ocr: { model: c?.ocr?.model ?? defaultSchema.ocr.model },
    chunker: {
      strategy: c?.chunker?.strategy ?? defaultSchema.chunker.strategy,
      chunk_size:
        typeof c?.chunker?.chunk_size === "number" ? c.chunker.chunk_size : defaultSchema.chunker.chunk_size,
      overlap_size:
        typeof c?.chunker?.overlap_size === "number"
          ? c.chunker.overlap_size
          : defaultSchema.chunker.overlap_size,
    },
    embedder: {
      provider: c?.embedder?.provider ?? defaultSchema.embedder.provider,
      model: c?.embedder?.model ?? defaultSchema.embedder.model,
    },
    vectordb: {
      backend: c?.vectordb?.backend ?? defaultSchema.vectordb.backend,
      config: c?.vectordb?.config ?? defaultSchema.vectordb.config,
    },
    llm: {
      provider: c?.llm?.provider ?? defaultSchema.llm.provider,
      model: c?.llm?.model ?? defaultSchema.llm.model,
    },
    solver: {
      top_k: typeof c?.solver?.top_k === "number" ? c.solver.top_k : defaultSchema.solver.top_k,
      reranking: c?.solver?.reranking ?? defaultSchema.solver.reranking,
      hyde: c?.solver?.hyde ?? defaultSchema.solver.hyde,
      hybrid: c?.solver?.hybrid ?? defaultSchema.solver.hybrid,
      strategy: c?.solver?.strategy ?? defaultSchema.solver.strategy,
    },
  };
}

export default function RunPage() {
  const router = useRouter();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState<string>("");
  const [isLoadingDatasets, setIsLoadingDatasets] = useState(true);

  const [configs, setConfigs] = useState<RAGConfig[]>([]);
  const [ragConfigId, setRagConfigId] = useState<string>("");
  const [mode, setMode] = useState<"select" | "create">("create");
  const [editorKey, setEditorKey] = useState(0);
  const [editorInitial, setEditorInitial] = useState<RAGConfigSchema | undefined>(undefined);
  const [activeSchema, setActiveSchema] = useState<RAGConfigSchema | null>(null);

  const [experimentName, setExperimentName] = useState("");
  const [runStatus, setRunStatus] = useState<"idle" | "running" | "ok" | "error">(
    "idle",
  );
  const [runMessage, setRunMessage] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setIsLoadingDatasets(true);
      try {
        const list = await api.datasets.list();
        if (cancelled) return;
        const runnable = (
          await Promise.all(
            list.map(async (d) => {
              try {
                const [docs, qs] = await Promise.all([
                  api.datasets.listDocuments(d.id),
                  api.datasets.listQuestions(d.id),
                ]);
                return docs.length > 0 && qs.length > 0 ? d : null;
              } catch {
                return null;
              }
            }),
          )
        ).filter((d): d is Dataset => !!d);

        if (cancelled) return;
        setDatasets(runnable);
        if (!datasetId && runnable.length > 0) setDatasetId(runnable[0]!.id);
      } catch {
        if (!cancelled) setDatasets([]);
      } finally {
        if (!cancelled) setIsLoadingDatasets(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await api.configs.rag.list();
        if (cancelled) return;
        setConfigs(list);
        if (!ragConfigId && list.length > 0) setRagConfigId(list[0]!.id);
      } catch {
        if (!cancelled) setConfigs([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ragConfigId]);

  const selectedConfig = useMemo(
    () => configs.find((c) => c.id === ragConfigId) ?? null,
    [configs, ragConfigId],
  );

  useEffect(() => {
    if (mode !== "select") return;
    if (!selectedConfig) {
      setActiveSchema(null);
      return;
    }
    setActiveSchema(toSchema(selectedConfig));
  }, [mode, selectedConfig]);

  const canRun = useMemo(() => {
    return !!datasetId && !!activeSchema && experimentName.trim().length > 0;
  }, [datasetId, activeSchema, experimentName]);

  return (
    <Shell>
      <div className="space-y-6">
        <header className="space-y-2">
          <h1 className="font-serif text-3xl tracking-tight text-ink leading-snug">Run</h1>
          <p className="font-serif text-xl text-slate leading-[1.7]">
            Select a dataset and a configuration, then run an experiment over the dataset questions.
          </p>
        </header>

        <Divider />

        <Card>
          <div className="space-y-4">
            <div className="font-serif text-xl tracking-tight text-ink">Select dataset</div>

            <div className="space-y-1">
              <div className="font-sans text-sm font-medium text-charcoal">Dataset</div>
              <Select
                value={datasetId || null}
                onChange={(v) => setDatasetId(v)}
                placeholder={
                  isLoadingDatasets
                    ? "Loading datasets…"
                    : datasets.length === 0
                      ? "No configured datasets available."
                      : "Select a dataset…"
                }
                disabled={isLoadingDatasets || datasets.length === 0}
                options={datasets.map((d) => ({ value: d.id, label: d.name }))}
              />
              {datasetId ? (
                <div className="font-mono text-xs text-ash break-all">{datasetId}</div>
              ) : null}
            </div>
          </div>
        </Card>

        <Card>
          <div className="space-y-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="font-serif text-xl tracking-tight text-ink">Configuration</div>
                <div className="mt-2 font-sans text-sm text-ash">
                  Configure the pipeline, then save it for reuse. You can also load a saved configuration.
                </div>
              </div>
              {mode === "create" ? (
                <Button variant="secondary" onClick={() => setMode("select")}>
                  Load saved configuration
                </Button>
              ) : null}
            </div>

            {mode === "select" ? (
              <div className="space-y-5">
                <div className="space-y-1">
                  <div className="font-sans text-sm font-medium text-charcoal">
                    Saved configurations
                  </div>
                  <Select
                    value={ragConfigId || null}
                    onChange={(v) => setRagConfigId(v)}
                    placeholder={configs.length === 0 ? "No saved configurations" : "Select a saved configuration…"}
                    disabled={configs.length === 0}
                    options={configs.map((c) => ({
                      value: c.id,
                      label: (c.name && c.name.trim().length > 0 ? c.name : c.id) as string,
                    }))}
                  />
                </div>

                {selectedConfig ? <RagConfigSummary config={selectedConfig} /> : null}

                <div className="flex flex-col sm:flex-row gap-3 pt-4">
                  <Button
                    disabled={!selectedConfig}
                    onClick={() => {
                      if (!selectedConfig) return;
                      const schema = toSchema(selectedConfig);
                      setEditorInitial(schema);
                      setEditorKey((k) => k + 1);
                      setActiveSchema(schema);
                      setMode("create");
                    }}
                  >
                    Use this configuration
                  </Button>
                  <Button variant="secondary" onClick={() => setMode("create")}>
                    Back to editor
                  </Button>
                </div>
              </div>
            ) : (
              <RagConfigEditor
                key={editorKey}
                initial={editorInitial}
                onChange={(draft) => setActiveSchema(draft)}
                onSaved={(saved) => {
                  setConfigs((prev) => [saved, ...prev.filter((c) => c.id !== saved.id)]);
                  setRagConfigId(saved.id);
                  // activeSchema is already kept in sync via the editor's onChange; keep it,
                  // but ensure we never crash if backend returned a partial config.
                  setActiveSchema((prev) => prev ?? toSchema(saved));
                  setMode("create");
                }}
              />
            )}
          </div>
        </Card>

        <Card>
          <div className="space-y-4">
            <div>
              <div className="font-serif text-xl tracking-tight text-ink">Experiment run</div>
              <div className="mt-1 font-sans text-sm text-ash">
                This triggers the combined backend run: ingestion (if needed) plus an experiment run,
                storing the generated answers.
              </div>
            </div>

            <div className="space-y-1">
              <div className="font-sans text-sm font-medium text-charcoal">Experiment name</div>
              <Input
                value={experimentName}
                placeholder="e.g. baseline_v1"
                onChange={(e) => setExperimentName(e.target.value)}
              />
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <Button
                disabled={!canRun || runStatus === "running"}
                onClick={async () => {
                  if (!datasetId) return;
                  if (!activeSchema) return;
                  const name = experimentName.trim();
                  if (!name) return;

                  setRunStatus("running");
                  setRunMessage("");
                  try {
                    await api.core.run(datasetId, name, activeSchema);
                    setRunStatus("ok");
                    setRunMessage("Run completed (status: ok). Redirecting to Experiments…");
                    router.push("/experiments");
                  } catch (e) {
                    setRunStatus("error");
                    if (e instanceof ApiError) {
                      setRunMessage(
                        typeof e.payload === "string" ? e.payload : `Request failed (${e.status}).`,
                      );
                      return;
                    }
                    setRunMessage(e instanceof Error ? e.message : "Run failed.");
                  }
                }}
              >
                {runStatus === "running" ? "Running…" : "Run experiment"}
              </Button>
            </div>

            {runMessage ? (
              <div
                className={`font-sans text-sm ${
                  runStatus === "error"
                    ? "text-red-700"
                    : runStatus === "ok"
                      ? "text-sage"
                      : "text-ash"
                }`}
              >
                {runMessage}
              </div>
            ) : null}
          </div>
        </Card>
      </div>
    </Shell>
  );
}

