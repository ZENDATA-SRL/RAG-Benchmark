"use client";

import { useId, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
import { Checkbox } from "@/components/ui/Checkbox";
import type {
  ChunkerStrategy,
  OCRModel,
  RAGConfig,
  RAGConfigSchema,
  RerankingMode,
  SolverStrategy,
  SolverConfigSchema,
  VectorDBBackend,
} from "@/lib/api";
import { api, ApiError } from "@/lib/api";
import { prettyEnum } from "@/lib/ui/labels";

const ocrModels: OCRModel[] = ["pypdf", "tesseract", "easyocr", "azure_document_intelligence"];
const chunkStrategies: ChunkerStrategy[] = [
  "recursive_character",
  "character",
  "markdown",
  "fixed_size",
];

const llmProviders = ["openai", "azure_openai", "anthropic", "gemini", "qwen"] as const;
type LlmProvider = (typeof llmProviders)[number];

// Note: keep only base model names (no date-suffixed releases).
const openaiLlmModels: string[] = [
  "gpt-5.4-pro",
  "gpt-5.4-thinking",
  "gpt-5.4",
  "gpt-5.4-mini",
  "gpt-5.4-nano",
  "gpt-5.3-instant",
  "gpt-5.2",
  "gpt-5.1-pro",
  "gpt-5.1-thinking",
  "gpt-5.1-instant",
  // Older baseline options (kept for compatibility)
  "gpt-4o",
  "gpt-4o-mini",
  "gpt-4.1",
  "gpt-4.1-mini",
];

const llmModelsByProvider: Record<LlmProvider, string[]> = {
  openai: openaiLlmModels,
  azure_openai: openaiLlmModels,
  anthropic: [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
  ],
  gemini: ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
  qwen: [
    "qwen3.5-plus",
    "qwen3.5-flash",
    "qwen3.5-397b-a17b",
    "qwen3.5-122b-a10b",
    "qwen3.5-35b-a3b",
    "qwen3.5-27b",
    "qwen3.5-9b",
    "qwen3.5-4b",
    "qwen3.5-2b",
    "qwen3.5-0.8b",
  ],
};

function anthropicModelLabel(modelId: string) {
  const m = /^claude-(.+)-(\d+)-(\d+)$/.exec(modelId);
  if (!m) return modelId;
  const [, family, major, minor] = m;
  return `${family}-${major}.${minor}`;
}

function qwenModelLabel(modelId: string) {
  const m = /^qwen(\d+(?:\.\d+)?)-(.*)$/.exec(modelId);
  if (!m) return modelId;
  const [, version, rest] = m;
  return `${version}-${rest}`;
}

const embedderProviders = ["openai", "azure_openai", "qwen"] as const;
type EmbedderProvider = (typeof embedderProviders)[number];

const openaiEmbedderModels: string[] = ["text-embedding-3-large", "text-embedding-3-small"];

const embedderModelsByProvider: Record<EmbedderProvider, string[]> = {
  openai: openaiEmbedderModels,
  azure_openai: openaiEmbedderModels,
  qwen: ["text-embedding-v3", "text-embedding-v2"],
};

const vectorDbBackends: VectorDBBackend[] = ["azure_search", "chromadb"];

const defaultRag: RAGConfigSchema = {
  name: "",
  ocr: { model: "pypdf" },
  chunker: { strategy: "recursive_character", chunk_size: 1000, overlap_size: 0 },
  embedder: { provider: "openai", model: "text-embedding-3-large" },
  vectordb: { backend: "chromadb", config: {} },
  llm: { provider: "openai", model: "gpt-4.1-mini" },
  solver: { top_k: 10, reranking: null, hyde: false, hybrid: false, strategy: "single_shot" },
};

function normalizeRagDraft(draft: RAGConfigSchema): RAGConfigSchema {
  if (draft.vectordb.backend !== "chromadb") return draft;
  if (!draft.solver.hybrid) return draft;
  return { ...draft, solver: { ...draft.solver, hybrid: false } };
}

function missingFields(draft: RAGConfigSchema): string[] {
  const missing: string[] = [];

  if (!draft.name || draft.name.trim().length === 0) missing.push("Configuration name");
  if (!draft.ocr.model) missing.push("OCR model");

  if (!draft.chunker.strategy) missing.push("Chunker strategy");
  if (!Number.isFinite(draft.chunker.chunk_size) || draft.chunker.chunk_size < 1)
    missing.push("Chunk size (>= 1)");
  if (!Number.isFinite(draft.chunker.overlap_size) || draft.chunker.overlap_size < 0)
    missing.push("Overlap (>= 0)");

  if (draft.embedder.provider.trim().length === 0) missing.push("Embedder provider");
  if (draft.embedder.model.trim().length === 0) missing.push("Embedder model");

  if (!draft.vectordb.backend) missing.push("Vector DB");

  if (draft.llm.provider.trim().length === 0) missing.push("LLM provider");
  if (draft.llm.model.trim().length === 0) missing.push("LLM model");

  if (!Number.isFinite(draft.solver.top_k) || draft.solver.top_k < 1) missing.push("Top K (>= 1)");
  if (!draft.solver.strategy) missing.push("Solver strategy");

  return missing;
}

function NumberField({
  label,
  value,
  onChange,
  min,
}: {
  label: string;
  value: number;
  min?: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="space-y-1">
      <div className="font-sans text-sm font-medium text-charcoal">{label}</div>
      <Input
        type="number"
        min={min}
        value={Number.isFinite(value) ? String(value) : ""}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw.trim().length === 0) return;
          const parsed = Number(raw);
          if (!Number.isFinite(parsed)) return;
          onChange(parsed);
        }}
      />
    </div>
  );
}

function InfoTooltip({
  label,
  children,
}: {
  label: string;
  children: string;
}) {
  const id = useId();
  return (
    <span className="relative inline-flex group">
      <span
        tabIndex={0}
        className="cursor-help select-none font-sans text-sm text-ash outline-none hover:text-slate focus-visible:ring-2 focus-visible:ring-coral focus-visible:ring-offset-2 rounded-sm"
        aria-describedby={id}
        role="button"
        aria-label={label}
      >
        ⓘ
      </span>
      <span
        id={id}
        role="tooltip"
        className="pointer-events-none invisible absolute bottom-full left-1/2 z-10 mb-2 w-[min(20rem,calc(100vw-2rem))] -translate-x-1/2 rounded-md border border-linen bg-eggshell px-3 py-2 font-sans text-xs leading-relaxed text-charcoal shadow-md opacity-0 transition-opacity duration-150 group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
      >
        {children}
      </span>
    </span>
  );
}

export function RagConfigEditor({
  onSaved,
  initial,
  onChange,
}: {
  initial?: RAGConfigSchema;
  onSaved?: (config: RAGConfig) => void;
  onChange?: (draft: RAGConfigSchema) => void;
}) {
  const [draft, setDraft] = useState<RAGConfigSchema>(() => normalizeRagDraft(initial ?? defaultRag));
  const [status, setStatus] = useState<"idle" | "saving" | "error" | "done">("idle");
  const [message, setMessage] = useState<string>("");

  const solver = draft.solver;
  const isChromaDb = draft.vectordb.backend === "chromadb";

  const hasValidNumbers = useMemo(() => {
    return (
      Number.isFinite(draft.chunker.chunk_size) &&
      Number.isFinite(draft.chunker.overlap_size) &&
      Number.isFinite(solver.top_k)
    );
  }, [draft.chunker.chunk_size, draft.chunker.overlap_size, solver.top_k]);

  const missing = useMemo(() => missingFields(draft), [draft]);
  const canSave = missing.length === 0 && hasValidNumbers && status !== "saving";

  const llmModelOptions = useMemo(() => {
    const provider = (draft.llm.provider as LlmProvider) ?? "openai";
    const models = llmModelsByProvider[provider] ?? llmModelsByProvider.openai;
    return models.map((m) => ({
      value: m,
      label:
        provider === "anthropic"
          ? anthropicModelLabel(m)
          : provider === "qwen"
            ? qwenModelLabel(m)
            : m,
    }));
  }, [draft.llm.provider]);

  const embedderModelOptions = useMemo(() => {
    const provider = (draft.embedder.provider as EmbedderProvider) ?? "openai";
    const models = embedderModelsByProvider[provider] ?? embedderModelsByProvider.openai;
    return models.map((m) => ({ value: m, label: m }));
  }, [draft.embedder.provider]);

  useEffect(() => {
    onChange?.(draft);
  }, [draft, onChange]);

  return (
    <div className="space-y-4">
      <Card>
        <div className="space-y-4">
          <div>
            <div className="font-serif text-xl tracking-tight text-ink">Name</div>
            <div className="mt-1 font-sans text-sm text-ash">
              Give this configuration a short, memorable name (required).
            </div>
          </div>

          <div className="space-y-1">
            <div className="font-sans text-sm font-medium text-charcoal">Configuration name</div>
            <Input
              value={draft.name}
              placeholder="e.g. baseline-rag"
              onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
            />
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <div className="space-y-4">
            <div>
              <div className="font-serif text-xl tracking-tight text-ink">OCR</div>
              <div className="mt-1 font-sans text-sm text-ash">
                Select the OCR extraction strategy for documents.
              </div>
            </div>

            <div className="space-y-1">
              <div className="font-sans text-sm font-medium text-charcoal">Model</div>
              <Select
                value={draft.ocr.model}
                onChange={(v) => setDraft((d) => ({ ...d, ocr: { ...d.ocr, model: v } }))}
                options={ocrModels.map((m) => ({ value: m, label: prettyEnum(m) }))}
              />
            </div>
          </div>
        </Card>

        <Card>
          <div className="space-y-4">
            <div>
              <div className="font-serif text-xl tracking-tight text-ink">Chunker</div>
              <div className="mt-1 font-sans text-sm text-ash">
                Configure how extracted text is split into chunks.
              </div>
            </div>

            <div className="space-y-1">
              <div className="font-sans text-sm font-medium text-charcoal">Strategy</div>
              <Select
                value={draft.chunker.strategy}
                onChange={(v) => setDraft((d) => ({ ...d, chunker: { ...d.chunker, strategy: v } }))}
                options={chunkStrategies.map((s) => ({ value: s, label: prettyEnum(s) }))}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <NumberField
                label="Chunk size"
                min={1}
                value={draft.chunker.chunk_size}
                onChange={(v) =>
                  setDraft((d) => ({ ...d, chunker: { ...d.chunker, chunk_size: v } }))
                }
              />
              <NumberField
                label="Overlap"
                min={0}
                value={draft.chunker.overlap_size}
                onChange={(v) =>
                  setDraft((d) => ({ ...d, chunker: { ...d.chunker, overlap_size: v } }))
                }
              />
            </div>
          </div>
        </Card>

        <Card>
          <div className="space-y-4">
            <div>
              <div className="font-serif text-xl tracking-tight text-ink">Vector DB</div>
              <div className="mt-1 font-sans text-sm text-ash">
                Select the vector database used for retrieval.
              </div>
            </div>

            <div className="space-y-1">
              <div className="font-sans text-sm font-medium text-charcoal">Backend</div>
              <Select
                value={draft.vectordb.backend}
                onChange={(backend) =>
                  setDraft((d) => ({
                    ...d,
                    vectordb: { ...d.vectordb, backend },
                    solver: backend === "chromadb" ? { ...d.solver, hybrid: false } : d.solver,
                  }))
                }
                options={vectorDbBackends.map((b) => ({
                  value: b,
                  label: b === "azure_search" ? "Azure Search" : "ChromaDB",
                }))}
              />
            </div>
          </div>
        </Card>

        <Card>
          <div className="space-y-4">
            <div>
              <div className="font-serif text-xl tracking-tight text-ink">LLM</div>
              <div className="mt-1 font-sans text-sm text-ash">
                Controls the language model used by the solver.
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="space-y-1">
                <div className="font-sans text-sm font-medium text-charcoal">Provider</div>
                <Select
                  value={(draft.llm.provider as LlmProvider) ?? "openai"}
                  onChange={(provider) => {
                    const models = llmModelsByProvider[provider];
                    setDraft((d) => {
                      const nextModel = models.includes(d.llm.model) ? d.llm.model : models[0]!;
                      return { ...d, llm: { provider, model: nextModel } };
                    });
                  }}
                  options={llmProviders.map((p) => ({ value: p, label: prettyEnum(p) }))}
                />
              </div>
              <div className="space-y-1">
                <div className="font-sans text-sm font-medium text-charcoal">Model</div>
                <Select
                  value={draft.llm.model || null}
                  onChange={(model) => setDraft((d) => ({ ...d, llm: { ...d.llm, model } }))}
                  placeholder="Select a model…"
                  options={llmModelOptions}
                />
              </div>
            </div>
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <div className="space-y-4">
            <div>
              <div className="font-serif text-xl tracking-tight text-ink">Embedder</div>
              <div className="mt-1 font-sans text-sm text-ash">
                Controls embeddings used for retrieval.
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="space-y-1">
                <div className="font-sans text-sm font-medium text-charcoal">Provider</div>
                <Select
                  value={(draft.embedder.provider as EmbedderProvider) ?? "openai"}
                  onChange={(provider) => {
                    const models = embedderModelsByProvider[provider];
                    setDraft((d) => {
                      const nextModel = models.includes(d.embedder.model) ? d.embedder.model : models[0]!;
                      return { ...d, embedder: { provider, model: nextModel } };
                    });
                  }}
                  options={embedderProviders.map((p) => ({ value: p, label: prettyEnum(p) }))}
                />
              </div>
              <div className="space-y-1">
                <div className="font-sans text-sm font-medium text-charcoal">Model</div>
                <Select
                  value={draft.embedder.model || null}
                  onChange={(model) => setDraft((d) => ({ ...d, embedder: { ...d.embedder, model } }))}
                  placeholder="Select a model…"
                  options={embedderModelOptions}
                />
              </div>
            </div>
          </div>
        </Card>
      </div>

      <Card>
        <div className="space-y-4">
          <div>
            <div className="font-serif text-xl tracking-tight text-ink">Solver</div>
            <div className="mt-1 font-sans text-sm text-ash">
              Retrieval strategy parameters (top_k, hybrid/hyde, reranking).
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <NumberField
              label="Top K"
              min={1}
              value={solver.top_k}
              onChange={(v) =>
                setDraft((d) => ({ ...d, solver: { ...d.solver, top_k: v } as SolverConfigSchema }))
              }
            />
            <div className="space-y-1 md:col-span-2">
              <div className="font-sans text-sm font-medium text-charcoal">
                Reranking
              </div>
              <Select
                value={(solver.reranking ?? "none") as RerankingMode | "none"}
                onChange={(v) =>
                  setDraft((d) => ({
                    ...d,
                    solver: { ...d.solver, reranking: v === "none" ? null : (v as RerankingMode) },
                  }))
                }
                options={[
                  { value: "none", label: "No reranking" },
                  { value: "llm", label: "LLM" },
                  { value: "semantic", label: "Semantic" },
                ]}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Checkbox
              label="HYDE"
              checked={solver.hyde}
              onChange={(v) => setDraft((d) => ({ ...d, solver: { ...d.solver, hyde: v } }))}
            />
            <Checkbox
              label={
                <span className="inline-flex items-center gap-2">
                  <span>Hybrid retrieval</span>
                  {isChromaDb ? (
                    <InfoTooltip label="Hybrid retrieval availability">
                      Hybrid retrieval is currently not available with ChromaDB.
                    </InfoTooltip>
                  ) : null}
                </span>
              }
              checked={solver.hybrid}
              disabled={isChromaDb}
              onChange={(v) => setDraft((d) => ({ ...d, solver: { ...d.solver, hybrid: v } }))}
            />
          </div>

          <div className="space-y-1">
            <div className="font-sans text-sm font-medium text-charcoal">Strategy</div>
            <Select
              value={solver.strategy}
              onChange={(v) =>
                setDraft((d) => ({
                  ...d,
                  solver: { ...d.solver, strategy: v as SolverStrategy },
                }))
              }
              options={[
                { value: "single_shot", label: "Single shot" },
                { value: "planned_multihop", label: "Planned multi-hop" },
              ]}
            />
          </div>
        </div>
      </Card>

      <div className="flex flex-col sm:flex-row gap-3">
        <Button
          disabled={!canSave}
          onClick={async () => {
            if (!canSave) {
              setStatus("error");
              setMessage(
                missing.length > 0
                  ? `Complete the configuration before saving: ${missing.join(", ")}.`
                  : "Complete the configuration before saving.",
              );
              return;
            }

            setStatus("saving");
            setMessage("");
            try {
              const saved = await api.configs.rag.resolveAndPersist(draft);
              // Some backends respond with only IDs for nested config blocks.
              // Best-effort hydrate so callers can safely read nested fields.
              const hydrated = await api.configs.rag.getById(saved.id).catch(() => saved);
              setStatus("done");
              setMessage(`Saved configuration: ${saved.id}`);
              onSaved?.(hydrated);
            } catch (e) {
              setStatus("error");
              if (e instanceof ApiError) {
                setMessage(
                  typeof e.payload === "string" ? e.payload : `Request failed (${e.status}).`,
                );
                return;
              }
              setMessage(e instanceof Error ? e.message : "Failed to save config.");
            }
          }}
        >
          {status === "saving" ? "Saving…" : "Save configuration"}
        </Button>
        <Button
          variant="secondary"
          disabled={status === "saving"}
          onClick={() => {
            setDraft(defaultRag);
            setStatus("idle");
            setMessage("");
          }}
        >
          Reset defaults
        </Button>
      </div>

      {!canSave && status !== "saving" ? (
        <div className="font-sans text-sm text-ash">
          Fill all required fields to enable saving.
          {missing.length > 0 ? (
            <>
              {" "}
              Missing: <span className="font-sans font-medium text-charcoal">{missing.join(", ")}</span>.
            </>
          ) : null}
        </div>
      ) : null}

      {message ? (
        <div
          className={`font-sans text-sm ${
            status === "error" ? "text-red-700" : status === "done" ? "text-sage" : "text-ash"
          }`}
        >
          {message}
        </div>
      ) : null}
    </div>
  );
}

