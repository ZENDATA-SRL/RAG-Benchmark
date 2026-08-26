import { prettyEnum } from "@/lib/ui/labels";
import type { RAGConfig } from "@/lib/api";

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="font-sans text-xs text-ash">{label}</div>
      <div className="font-sans text-xs font-medium text-charcoal leading-snug">{value}</div>
    </div>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap gap-x-8 gap-y-3">{children}</div>;
}

export function RagConfigSummary({ config }: { config: RAGConfig }) {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:gap-0">
      <section className="space-y-5 lg:pr-8">
        <div className="space-y-3">
          <div className="font-serif text-base tracking-tight text-ink">OCR</div>
          <Row>
            <Field label="Model" value={config.ocr?.model ? prettyEnum(config.ocr.model) : "—"} />
          </Row>
        </div>

        <div className="h-px bg-linen" />

        <div className="space-y-3">
          <div className="font-serif text-base tracking-tight text-ink">Chunker</div>
          <Row>
            <Field
              label="Strategy"
              value={config.chunker?.strategy ? prettyEnum(config.chunker.strategy) : "—"}
            />
            <Field
              label="Chunk size"
              value={typeof config.chunker?.chunk_size === "number" ? config.chunker.chunk_size : "—"}
            />
            <Field
              label="Overlap"
              value={typeof config.chunker?.overlap_size === "number" ? config.chunker.overlap_size : "—"}
            />
          </Row>
        </div>

        <div className="h-px bg-linen" />

        <div className="space-y-3">
          <div className="font-serif text-base tracking-tight text-ink">Embedder</div>
          <Row>
            <Field
              label="Provider"
              value={config.embedder?.provider?.trim() || "—"}
            />
            <Field
              label="Model"
              value={config.embedder?.model?.trim() || "—"}
            />
          </Row>
        </div>

        <div className="h-px bg-linen" />

        <div className="space-y-3">
          <div className="font-serif text-base tracking-tight text-ink">Vector DB</div>
          <Row>
            <Field
              label="Backend"
              value={
                config.vectordb?.backend
                  ? config.vectordb.backend === "azure_search"
                    ? "Azure Search"
                    : "ChromaDB"
                  : "—"
              }
            />
          </Row>
        </div>
      </section>

      <section className="space-y-5 lg:border-l lg:border-linen lg:pl-8">
        <div className="space-y-3">
          <div className="font-serif text-base tracking-tight text-ink">LLM</div>
          <Row>
            <Field label="Provider" value={config.llm?.provider?.trim() || "—"} />
            <Field label="Model" value={config.llm?.model?.trim() || "—"} />
          </Row>
        </div>

        <div className="h-px bg-linen" />

        <div className="space-y-3">
          <div className="font-serif text-base tracking-tight text-ink">Solver</div>
          <Row>
            <Field
              label="Top K"
              value={typeof config.solver?.top_k === "number" ? config.solver.top_k : "—"}
            />
            <Field
              label="Reranking"
              value={
                config.solver
                  ? config.solver.reranking
                    ? prettyEnum(config.solver.reranking)
                    : "None"
                  : "—"
              }
            />
            <Field
              label="HYDE"
              value={config.solver ? (config.solver.hyde ? "Enabled" : "Disabled") : "—"}
            />
            <Field
              label="Hybrid"
              value={config.solver ? (config.solver.hybrid ? "Enabled" : "Disabled") : "—"}
            />
          </Row>
          <Row>
            <Field
              label="Strategy"
              value={config.solver?.strategy ? prettyEnum(config.solver.strategy) : "—"}
            />
          </Row>
        </div>
      </section>
    </div>
  );
}
