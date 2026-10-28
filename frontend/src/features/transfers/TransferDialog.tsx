import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { configurationsApi, embeddingProfilesApi, transfersApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { ApiError, errorToastText } from "@/lib/errors";
import { queryKeys } from "@/lib/queryClient";
import { toast } from "@/lib/toast";

type Uncovered = { question_id: string; text: string; reason: string };

const DEFAULT_WEIGHTS = { semantic: 0.5, lexical: 0.35, positional: 0.15 };
const DEFAULT_THRESHOLDS = { high: 0.75, low: 0.45, preselect: 0.9 };

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block text-xs">
      <span className="mb-1 block text-ink-muted">{label}</span>
      <input
        type="number"
        min={0}
        max={1}
        step={0.05}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full rounded-md border border-line bg-paper-raised px-2 py-1"
      />
    </label>
  );
}

/**
 * Starts a job ranking the chunks of each question's gold documents in a configuration:
 * from the question and its answer, or from the chunks confirmed in another configuration.
 */
export function TransferDialog({
  qaSetId,
  targetConfigurationId,
  onClose,
}: {
  qaSetId: string;
  targetConfigurationId: string;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [target, setTarget] = useState(targetConfigurationId);
  const [source, setSource] = useState("");
  const [embedding, setEmbedding] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS);
  const [thresholds, setThresholds] = useState(DEFAULT_THRESHOLDS);
  const [uncovered, setUncovered] = useState<Uncovered[] | null>(null);

  const configurations = useQuery({
    queryKey: queryKeys.configurations,
    queryFn: configurationsApi.list,
  });
  const embeddings = useQuery({
    queryKey: queryKeys.embeddingProfiles,
    queryFn: embeddingProfilesApi.list,
  });

  const create = useMutation({
    mutationFn: (excludeUncovered: boolean) =>
      transfersApi.create({
        qa_set_id: qaSetId,
        target_configuration_id: target,
        source_configuration_id: source || null,
        embedding_profile_id: embedding || null,
        signal_weights: weights,
        confidence_thresholds: thresholds,
        exclude_uncovered: excludeUncovered,
      }),
    // The uncovered questions are answered in the dialog, not by a toast.
    meta: { silent: true },
    onSuccess: async (job) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.transfers(qaSetId) });
      if (job.excluded.length > 0) {
        toast.info(`${job.excluded.length} question(s) left out: their documents have no chunks.`);
      }
      navigate(`/transfers/${job.id}`);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "uncovered_questions_choice_required") {
        setUncovered((error.details.uncovered_questions as Uncovered[]) ?? []);
        return;
      }
      toast.error(errorToastText(error));
    },
  });

  const items = configurations.data?.items ?? [];

  return (
    <Dialog title="Suggest evidence chunks" onClose={onClose} wide>
      <div className="space-y-4 text-sm">
        <p className="text-xs leading-5 text-ink-muted">
          Ranks every chunk of each question&apos;s gold documents, so the review starts from the
          likely ones. From another configuration, the chunks confirmed there are looked for and a
          near-identical copy comes already ticked. Nothing becomes evidence until you confirm it.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="block">
            <span className="mb-1 block text-xs text-ink-muted">Annotate under</span>
            <select
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              className="w-full rounded-md border border-line bg-paper-raised px-2 py-1"
              aria-label="Target configuration"
            >
              {items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-muted">Starting from</span>
            <select
              value={source}
              onChange={(event) => setSource(event.target.value)}
              className="w-full rounded-md border border-line bg-paper-raised px-2 py-1"
              aria-label="Source configuration"
            >
              <option value="">Question and answer</option>
              {items
                .filter((item) => item.id !== target)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    Evidence confirmed in {item.name}
                  </option>
                ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-ink-muted">Embedder</span>
            <select
              value={embedding}
              onChange={(event) => setEmbedding(event.target.value)}
              className="w-full rounded-md border border-line bg-paper-raised px-2 py-1"
              aria-label="Embedding profile"
            >
              <option value="">The one of the latest index, if any</option>
              {(embeddings.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <button
          type="button"
          className="text-xs text-rust hover:underline"
          onClick={() => setAdvanced((current) => !current)}
        >
          {advanced ? "Hide" : "Show"} weights and thresholds
        </button>
        {advanced ? (
          <div className="grid gap-3 rounded-md border border-line p-3 sm:grid-cols-3">
            <NumberField
              label="Semantic weight"
              value={weights.semantic}
              onChange={(semantic) => setWeights({ ...weights, semantic })}
            />
            <NumberField
              label="Lexical weight"
              value={weights.lexical}
              onChange={(lexical) => setWeights({ ...weights, lexical })}
            />
            <NumberField
              label="Positional weight"
              value={weights.positional}
              onChange={(positional) => setWeights({ ...weights, positional })}
            />
            <NumberField
              label="High band from"
              value={thresholds.high}
              onChange={(high) => setThresholds({ ...thresholds, high })}
            />
            <NumberField
              label="Low band below"
              value={thresholds.low}
              onChange={(low) => setThresholds({ ...thresholds, low })}
            />
            <NumberField
              label="Pre-select from lexical"
              value={thresholds.preselect}
              onChange={(preselect) => setThresholds({ ...thresholds, preselect })}
            />
            <p className="text-[11px] text-ink-muted sm:col-span-3">
              Starting values, not a calibration: they are saved with the job.
            </p>
          </div>
        ) : null}

        {uncovered ? (
          <div className="rounded-md bg-amber/15 p-3 text-xs leading-5" data-testid="uncovered">
            <p className="font-medium">
              {uncovered.length} question(s) cannot be ranked: their gold documents have no chunks
              under this configuration (or they have no gold document).
            </p>
            <ul className="mt-1 list-disc pl-4">
              {uncovered.slice(0, 5).map((item) => (
                <li key={item.question_id}>{item.text}</li>
              ))}
            </ul>
            <p className="mt-1">
              Materialise the configuration on those documents, or leave them out of this job.
            </p>
          </div>
        ) : null}

        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          {uncovered ? (
            <Button onClick={() => create.mutate(true)} disabled={create.isPending}>
              Leave them out and start
            </Button>
          ) : (
            <Button onClick={() => create.mutate(false)} disabled={!target || create.isPending}>
              Start
            </Button>
          )}
        </div>
      </div>
    </Dialog>
  );
}
