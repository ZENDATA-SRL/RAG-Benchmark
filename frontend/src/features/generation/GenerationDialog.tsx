import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { useNavigate } from "react-router-dom";

import { configurationsApi, generationApi } from "@/api/resources";
import type { GenerationCreate } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { errorToastText } from "@/lib/errors";
import { queryKeys } from "@/lib/queryClient";
import { toast } from "@/lib/toast";

const INPUT = "w-full rounded-md border border-line bg-paper-raised px-2 py-1";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-xs">
      <span className="mb-1 block text-ink-muted">{label}</span>
      {children}
    </label>
  );
}

/**
 * Starts a job where an agent reads the documents of the set's corpus, or only the ones
 * ticked, and proposes questions with their answer and evidence chunks; nothing enters the
 * set until it is accepted.
 */
export function GenerationDialog({
  qaSetId,
  configurationId,
  onClose,
}: {
  qaSetId: string;
  configurationId: string;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [configuration, setConfiguration] = useState(configurationId);
  const [perDocument, setPerDocument] = useState(3);
  const [crossDocument, setCrossDocument] = useState(0);
  const [excluded, setExcluded] = useState<string[]>([]);
  // "chosen" reads only the ticked documents, so a few can be picked from a large corpus.
  const [scope, setScope] = useState<"all" | "chosen">("all");
  const [chosen, setChosen] = useState<string[]>([]);
  const [filter, setFilter] = useState("");
  const [provider, setProvider] = useState<GenerationCreate["provider"]>("bedrock");
  const [model, setModel] = useState("");
  const [region, setRegion] = useState("");
  const [temperature, setTemperature] = useState(0.3);
  const [language, setLanguage] = useState("");
  const [instructions, setInstructions] = useState("");
  const [maxSteps, setMaxSteps] = useState(40);

  const configurations = useQuery({
    queryKey: queryKeys.configurations,
    queryFn: configurationsApi.list,
  });

  const body: GenerationCreate = {
    qa_set_id: qaSetId,
    chunking_configuration_id: configuration,
    per_document: perDocument,
    cross_document: crossDocument,
    excluded_document_ids: scope === "all" ? excluded : [],
    // With nothing ticked yet the corpus is still listed, but nothing can start.
    document_ids: scope === "chosen" && chosen.length > 0 ? chosen : null,
    // The documents that cannot be read are listed below as left out, so the choice is
    // made here and not by a refusal.
    exclude_unmaterialized: true,
    provider,
    model: model.trim(),
    region: provider === "bedrock" && region.trim() ? region.trim() : null,
    temperature,
    language: language.trim() || null,
    instructions: instructions.trim() || null,
    max_steps: maxSteps,
  };
  const estimate = useQuery({
    queryKey: queryKeys.generationEstimate(
      JSON.stringify([
        qaSetId,
        configuration,
        perDocument,
        crossDocument,
        body.excluded_document_ids,
        body.document_ids,
        maxSteps,
      ]),
    ),
    // The model does not change the estimate; a placeholder lets it show before one is typed.
    queryFn: () => generationApi.estimate({ ...body, model: body.model || "-" }),
    enabled: Boolean(configuration),
    retry: false,
    meta: { silent: true },
  });

  const create = useMutation({
    mutationFn: () => generationApi.create(body),
    onSuccess: async (job) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.generations(qaSetId) });
      if (job.excluded.length > 0) {
        toast.info(`${job.excluded.length} document(s) left out: no chunks or text here.`);
      }
      navigate(`/generation-jobs/${job.id}`);
    },
  });

  const documents = estimate.data?.documents ?? [];
  const flip = (current: string[], documentId: string) =>
    current.includes(documentId)
      ? current.filter((item) => item !== documentId)
      : [...current, documentId];
  const toggle = (documentId: string) =>
    scope === "all"
      ? setExcluded((current) => flip(current, documentId))
      : setChosen((current) => flip(current, documentId));
  const ticked = (documentId: string) =>
    scope === "all" ? !excluded.includes(documentId) : chosen.includes(documentId);
  const needle = filter.trim().toLowerCase();
  const listed = needle
    ? documents.filter((document) => document.filename.toLowerCase().includes(needle))
    : documents;
  const nothingChosen = scope === "chosen" && chosen.length === 0;
  const numbers = nothingChosen ? undefined : estimate.data?.estimate;

  return (
    <Dialog title="Generate questions" onClose={onClose} wide>
      <div className="space-y-4 text-sm">
        <p className="text-xs leading-5 text-ink-muted">
          An agent reads each document in its chunks and proposes questions with their expected
          answer and the chunks that hold it, quoting them. Every proposal goes through your review:
          only the accepted ones enter the set, tagged <code>generated</code>.
        </p>

        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Chunks of">
            <select
              value={configuration}
              onChange={(event) => setConfiguration(event.target.value)}
              className={INPUT}
              aria-label="Chunking configuration"
            >
              <option value="">Choose a configuration</option>
              {(configurations.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Questions per document">
            <input
              type="number"
              min={0}
              max={50}
              value={perDocument}
              onChange={(event) => setPerDocument(Number(event.target.value))}
              className={INPUT}
              aria-label="Questions per document"
            />
          </Field>
          <Field label="Questions across documents">
            <input
              type="number"
              min={0}
              max={200}
              value={crossDocument}
              onChange={(event) => setCrossDocument(Number(event.target.value))}
              className={INPUT}
              aria-label="Questions across documents"
            />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Provider">
            <select
              value={provider}
              onChange={(event) => setProvider(event.target.value as GenerationCreate["provider"])}
              className={INPUT}
              aria-label="Provider"
            >
              <option value="bedrock">bedrock</option>
              <option value="openai">openai</option>
            </select>
          </Field>
          <Field label="Model">
            <input
              value={model}
              onChange={(event) => setModel(event.target.value)}
              placeholder={provider === "openai" ? "gpt-4o-mini" : "Bedrock model id"}
              className={INPUT}
              aria-label="Model"
            />
          </Field>
          {provider === "bedrock" ? (
            <Field label="Region">
              <input
                value={region}
                onChange={(event) => setRegion(event.target.value)}
                placeholder="the profile's"
                className={INPUT}
              />
            </Field>
          ) : null}
          <Field label="Temperature">
            <input
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={temperature}
              onChange={(event) => setTemperature(Number(event.target.value))}
              className={INPUT}
            />
          </Field>
          <Field label="Language">
            <input
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              placeholder="the documents'"
              className={INPUT}
            />
          </Field>
          <Field label="Steps per unit">
            <input
              type="number"
              min={5}
              max={200}
              value={maxSteps}
              onChange={(event) => setMaxSteps(Number(event.target.value))}
              className={INPUT}
            />
          </Field>
        </div>
        <Field label="Instruction for the generator">
          <textarea
            value={instructions}
            onChange={(event) => setInstructions(event.target.value)}
            placeholder="e.g. questions a help desk operator would ask"
            rows={2}
            className={INPUT}
          />
        </Field>

        {documents.length > 0 ? (
          <div>
            <div className="mb-1 flex flex-wrap items-center gap-3 text-xs">
              <span className="text-ink-muted">Documents to read</span>
              <label className="flex items-center gap-1">
                <input
                  type="radio"
                  name="generation-scope"
                  checked={scope === "all"}
                  onChange={() => setScope("all")}
                />
                all of the corpus
              </label>
              <label className="flex items-center gap-1">
                <input
                  type="radio"
                  name="generation-scope"
                  checked={scope === "chosen"}
                  onChange={() => setScope("chosen")}
                />
                only the ones I tick
              </label>
              <input
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                placeholder="Filter by name"
                aria-label="Filter documents"
                className="ml-auto w-40 rounded-md border border-line bg-paper-raised px-2 py-0.5"
              />
            </div>
            <ul
              className="max-h-40 space-y-1 overflow-y-auto rounded-md border border-line p-2 text-xs"
              data-testid="generation-documents"
            >
              {listed.map((document) => (
                <li key={document.document_id}>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={document.materialised && ticked(document.document_id)}
                      disabled={!document.materialised}
                      onChange={() => toggle(document.document_id)}
                    />
                    <span>{document.filename}</span>
                    {document.materialised ? null : (
                      <span className="text-ink-muted">no chunks or text here: left out</span>
                    )}
                  </label>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {nothingChosen ? (
          <p className="text-xs text-ink-muted">
            Tick the documents to read: one for questions on it alone, two or three for a question
            across them.
          </p>
        ) : estimate.error ? (
          <p className="text-xs text-danger">{errorToastText(estimate.error)}</p>
        ) : null}
        {numbers ? (
          <p className="text-xs text-ink-muted" data-testid="generation-estimate">
            {numbers.target_questions} question(s) over {numbers.documents} document(s):{" "}
            {numbers.document_units} unit(s) per document and {numbers.cross_units} across
            documents, at most {numbers.max_model_calls} model calls.
          </p>
        ) : null}

        <div className="rounded-md bg-amber/15 p-3 text-xs leading-5" data-testid="bias-warning">
          The questions are written from the chunks of this configuration, so it starts favoured
          against configurations with other boundaries. Compare configurations on the document-level
          metrics, or transfer the evidence to the others, and read the <code>generated</code> tags
          apart from the questions written by hand.
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => create.mutate()}
            disabled={!configuration || !model.trim() || !numbers || create.isPending}
          >
            Start
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
