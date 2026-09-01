import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { componentsApi, configurationsApi } from "@/api/resources";
import type { ChunkingConfigurationComposed, ComponentWithVersionsRead } from "@/api/types";
import { defaultsFromSchema, SchemaForm, type JsonSchema } from "@/components/SchemaForm";
import { Button } from "@/components/ui/Button";
import { queryKeys } from "@/lib/queryClient";
import { toast } from "@/lib/toast";

type Step = "parser" | "chunker" | "summary";

function ofType(components: ComponentWithVersionsRead[] | undefined, type: string) {
  return (components ?? []).filter((component) => component.type === type);
}

function versionsOf(component: ComponentWithVersionsRead | undefined) {
  return component?.versions ?? [];
}

function pickVersion(component: ComponentWithVersionsRead | undefined, versionId: string) {
  return versionsOf(component).find((version) => version.id === versionId);
}

function strategyOf(component: ComponentWithVersionsRead | undefined): string {
  const fromCaps = versionsOf(component)[0]?.capabilities?.strategy;
  if (typeof fromCaps === "string" && fromCaps) {
    return fromCaps;
  }
  return component?.key ?? "recursive";
}

export function ConfigurationWizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("parser");
  const [parserId, setParserId] = useState<string | null>(null);
  const [parserVersionId, setParserVersionId] = useState<string | null>(null);
  const [parserParams, setParserParams] = useState<Record<string, unknown> | null>(null);
  const [chunkerId, setChunkerId] = useState<string | null>(null);
  const [chunkerVersionId, setChunkerVersionId] = useState<string | null>(null);
  const [chunkerParams, setChunkerParams] = useState<Record<string, unknown> | null>(null);
  const [name, setName] = useState("");
  const [composed, setComposed] = useState<ChunkingConfigurationComposed | null>(null);

  const components = useQuery({
    queryKey: queryKeys.components,
    queryFn: () => componentsApi.list(),
  });

  const parsers = ofType(components.data, "parser");
  const chunkers = ofType(components.data, "chunker");
  const parser = parsers.find((item) => item.id === parserId) ?? parsers[0];
  const chunker = chunkers.find((item) => item.id === chunkerId) ?? chunkers[0];
  const parserVersion =
    pickVersion(parser, parserVersionId ?? "") ?? versionsOf(parser).find((version) => version.is_available);
  const chunkerVersion =
    pickVersion(chunker, chunkerVersionId ?? "") ?? versionsOf(chunker).find((version) => version.is_available);

  const parserSchema = (parserVersion?.params_schema ?? { type: "object", properties: {} }) as JsonSchema;
  const chunkerSchema = (chunkerVersion?.params_schema ?? { type: "object", properties: {} }) as JsonSchema;
  const effectiveParserParams = parserParams ?? defaultsFromSchema(parserSchema);
  const effectiveChunkerParams = chunkerParams ?? defaultsFromSchema(chunkerSchema);

  const compose = useMutation({
    mutationFn: () => {
      const chunkSize =
        typeof effectiveChunkerParams.chunk_size === "number" ? effectiveChunkerParams.chunk_size : undefined;
      const overlap =
        typeof effectiveChunkerParams.overlap === "number" ? effectiveChunkerParams.overlap : undefined;
      const rest = { ...effectiveChunkerParams };
      delete rest.chunk_size;
      delete rest.overlap;
      return configurationsApi.compose({
        parsing_component_version_id: parserVersion?.id ?? "",
        parsing_profile_name: `${parser?.key ?? "parser"} ${parserVersion?.version ?? ""}`.trim(),
        parsing_params: effectiveParserParams,
        chunking_component_version_id: chunkerVersion?.id ?? "",
        chunking_profile_name: `${chunker?.key ?? "chunker"}${chunkSize ?? ""}`,
        chunking_strategy: strategyOf(chunker),
        chunk_size: chunkSize,
        overlap,
        chunking_params: rest,
        name: name.trim() || null,
      });
    },
    onSuccess: (result) => {
      setComposed(result);
      if (result.created) {
        toast.success("Configuration created.");
      }
    },
  });

  return (
    <div className="mx-auto max-w-2xl">
      <p className="text-xs text-ink-muted">
        <Link to="/configurations" className="hover:underline">
          Configurations
        </Link>
        <span> / compose</span>
      </p>
      <h1 className="mt-2 text-2xl font-semibold">Compose a chunking configuration</h1>
      <ol className="mt-4 flex gap-4 text-xs font-medium">
        {(["parser", "chunker", "summary"] as Step[]).map((item, index) => (
          <li key={item} className={item === step ? "text-rust" : "text-ink-muted"}>
            {index + 1}. {item}
          </li>
        ))}
      </ol>

      {composed ? (
        <div className="mt-6 rounded-xl border border-line bg-paper-raised p-5">
          {composed.created ? (
            <p className="text-sm">Configuration <strong>{composed.configuration.name}</strong> is ready.</p>
          ) : (
            <div>
              <p className="text-sm font-medium">This configuration already exists.</p>
              <p className="mt-2 text-sm text-ink-muted">
                {composed.detail ??
                  "An identical parser + chunker pair was reused. A different name cannot create a duplicate."}
              </p>
              <p className="mt-2 text-sm">
                Use <strong>{composed.configuration.name}</strong> — it is the same row.
              </p>
            </div>
          )}
          <div className="mt-4 flex gap-2">
            <Button onClick={() => navigate("/configurations")}>Use this configuration</Button>
          </div>
        </div>
      ) : (
        <div className="mt-6 rounded-xl border border-line bg-paper-raised p-5">
          {step === "parser" ? (
            <ComponentStep
              label="Parser"
              components={parsers}
              selectedId={parser?.id ?? ""}
              versionId={parserVersion?.id ?? ""}
              onSelect={(id) => {
                setParserId(id);
                const next = parsers.find((item) => item.id === id);
                const version = versionsOf(next).find((item) => item.is_available) ?? versionsOf(next)[0];
                setParserVersionId(version?.id ?? null);
                setParserParams(null);
              }}
              onVersion={(id) => {
                setParserVersionId(id);
                setParserParams(null);
              }}
              schema={parserSchema}
              formData={effectiveParserParams}
              onChange={setParserParams}
            />
          ) : null}
          {step === "chunker" ? (
            <ComponentStep
              label="Chunker"
              components={chunkers}
              selectedId={chunker?.id ?? ""}
              versionId={chunkerVersion?.id ?? ""}
              onSelect={(id) => {
                setChunkerId(id);
                const next = chunkers.find((item) => item.id === id);
                const version = versionsOf(next).find((item) => item.is_available) ?? versionsOf(next)[0];
                setChunkerVersionId(version?.id ?? null);
                setChunkerParams(null);
              }}
              onVersion={(id) => {
                setChunkerVersionId(id);
                setChunkerParams(null);
              }}
              schema={chunkerSchema}
              formData={effectiveChunkerParams}
              onChange={setChunkerParams}
            />
          ) : null}
          {step === "summary" ? (
            <div className="space-y-4 text-sm">
              <p>
                <span className="text-ink-muted">Parser</span> {parser?.display_name} v{parserVersion?.version}
              </p>
              <p>
                <span className="text-ink-muted">Chunker</span> {chunker?.display_name} v{chunkerVersion?.version}
                {typeof effectiveChunkerParams.chunk_size === "number" ? ` · size ${effectiveChunkerParams.chunk_size}` : ""}
                {typeof effectiveChunkerParams.overlap === "number" ? ` · overlap ${effectiveChunkerParams.overlap}` : ""}
              </p>
              <label className="block">
                <span className="mb-1 block font-medium">Name (optional)</span>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className="w-full rounded-md border border-line bg-paper px-3 py-1.5"
                  placeholder="Shown if this pair is new"
                />
              </label>
              <p className="text-xs text-ink-muted">
                The name is not part of identity. Asking twice with different names returns the same configuration.
              </p>
            </div>
          ) : null}

          <div className="mt-6 flex justify-between">
            <Button
              variant="secondary"
              onClick={() => setStep(step === "summary" ? "chunker" : "parser")}
              disabled={step === "parser"}
            >
              Back
            </Button>
            {step === "summary" ? (
              <Button onClick={() => compose.mutate()} disabled={compose.isPending}>
                {compose.isPending ? "Composing…" : "Compose"}
              </Button>
            ) : (
              <Button onClick={() => setStep(step === "parser" ? "chunker" : "summary")}>Next</Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ComponentStep({
  label,
  components,
  selectedId,
  versionId,
  onSelect,
  onVersion,
  schema,
  formData,
  onChange,
}: {
  label: string;
  components: ComponentWithVersionsRead[];
  selectedId: string;
  versionId: string;
  onSelect: (id: string) => void;
  onVersion: (id: string) => void;
  schema: JsonSchema;
  formData: Record<string, unknown>;
  onChange: (data: Record<string, unknown>) => void;
}) {
  const selected = components.find((item) => item.id === selectedId);
  return (
    <div className="space-y-4">
      <label className="block text-sm">
        <span className="mb-1 block font-medium">{label}</span>
        <select
          value={selectedId}
          onChange={(event) => onSelect(event.target.value)}
          className="w-full rounded-md border border-line bg-paper px-3 py-1.5"
        >
          {components.map((component) => (
            <option key={component.id} value={component.id}>
              {component.display_name}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-sm">
        <span className="mb-1 block font-medium">Version</span>
        <select
          value={versionId}
          onChange={(event) => onVersion(event.target.value)}
          className="w-full rounded-md border border-line bg-paper px-3 py-1.5"
        >
          {versionsOf(selected).map((version) => (
            <option key={version.id} value={version.id} disabled={!version.is_available}>
              v{version.version}
              {version.is_available ? "" : ` — unavailable: ${version.unavailable_reason ?? ""}`}
            </option>
          ))}
        </select>
      </label>
      <SchemaForm schema={schema} formData={formData} onChange={onChange} />
    </div>
  );
}
