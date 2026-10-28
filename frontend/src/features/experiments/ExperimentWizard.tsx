import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import {
  corporaApi,
  experimentsApi,
  indexBuildsApi,
  qaSetsApi,
  retrievalProfilesApi,
  snapshotsApi,
} from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { queryKeys } from "@/lib/queryClient";

import { ChunkGoldCoverage } from "./ChunkGoldCoverage";
import { experimentErrorMessage } from "./errors";
import { canCreateExperiment, crossVariants, selectableBuilds } from "./variants";

const selectClass = "w-full rounded-md border border-line bg-paper px-3 py-1.5";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium">{label}</span>
      {children}
    </label>
  );
}

function toggle(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

export function ExperimentWizard({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [corpusId, setCorpusId] = useState("");
  const [corpusSnapshotId, setCorpusSnapshotId] = useState("");
  const [qaSetId, setQaSetId] = useState("");
  const [qaSnapshotId, setQaSnapshotId] = useState("");
  const [buildIds, setBuildIds] = useState<string[]>([]);
  const [profileIds, setProfileIds] = useState<string[]>([]);
  const [baselineKey, setBaselineKey] = useState<string | null>(null);
  const [repetitions, setRepetitions] = useState(1);
  const [excludeUncovered, setExcludeUncovered] = useState(false);

  const corpora = useQuery({ queryKey: queryKeys.corpora, queryFn: corporaApi.list });
  const corpusSnapshots = useQuery({
    queryKey: queryKeys.corpusSnapshots(corpusId),
    queryFn: () => snapshotsApi.list(corpusId),
    enabled: Boolean(corpusId),
  });
  const qaSets = useQuery({ queryKey: queryKeys.qaSets, queryFn: qaSetsApi.list });
  const qaSnapshots = useQuery({
    queryKey: queryKeys.qaSetSnapshots(qaSetId),
    queryFn: () => qaSetsApi.snapshots(qaSetId),
    enabled: Boolean(qaSetId),
  });
  const builds = useQuery({
    queryKey: queryKeys.indexBuilds,
    queryFn: () => indexBuildsApi.list(),
  });
  const profiles = useQuery({
    queryKey: queryKeys.retrievalProfiles,
    queryFn: retrievalProfilesApi.list,
  });
  const coverage = useQuery({
    queryKey: queryKeys.coverageCheck(corpusSnapshotId, qaSnapshotId),
    queryFn: () => experimentsApi.coverage(corpusSnapshotId, qaSnapshotId),
    enabled: Boolean(corpusSnapshotId && qaSnapshotId),
  });

  const allBuilds = builds.data?.items ?? [];
  const choices = selectableBuilds(allBuilds, corpusSnapshotId);
  const hiddenCount =
    allBuilds.filter((build) => build.corpus_snapshot_id === corpusSnapshotId).length -
    choices.length;
  const chosenBuilds = choices.filter((build) => buildIds.includes(build.id));
  const chosenProfiles = (profiles.data?.items ?? []).filter((profile) =>
    profileIds.includes(profile.id),
  );
  const variants = crossVariants(chosenBuilds, chosenProfiles, baselineKey);
  const uncovered = coverage.data?.uncovered_count ?? null;

  const create = useMutation({
    mutationFn: () =>
      experimentsApi.create({
        name: name.trim(),
        type: "retrieval",
        corpus_snapshot_id: corpusSnapshotId,
        qa_set_snapshot_id: qaSnapshotId,
        repetitions,
        uncovered_policy: uncovered ? "exclude" : null,
        variants: variants.map((choice) => choice.variant),
      }),
    meta: { silent: true },
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.experiments });
      onClose();
      navigate(`/experiments/${created.id}`);
    },
  });

  const canCreate = canCreateExperiment({
    name,
    variantCount: variants.length,
    uncoveredCount: uncovered,
    excludeUncovered,
  });
  const errorText = create.error
    ? (experimentErrorMessage(create.error) ?? (create.error as Error).message)
    : null;

  return (
    <Dialog title="New experiment" onClose={onClose} wide>
      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <Field label="Name">
          <input
            required
            maxLength={200}
            value={name}
            onChange={(event) => setName(event.target.value)}
            className={selectClass}
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Corpus">
            <select
              value={corpusId}
              onChange={(event) => {
                setCorpusId(event.target.value);
                setCorpusSnapshotId("");
                setBuildIds([]);
              }}
              className={selectClass}
            >
              <option value="">Select a corpus…</option>
              {(corpora.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Corpus snapshot">
            <select
              value={corpusSnapshotId}
              disabled={!corpusId}
              onChange={(event) => {
                setCorpusSnapshotId(event.target.value);
                setBuildIds([]);
                setExcludeUncovered(false);
              }}
              className={selectClass}
            >
              <option value="">Select a snapshot…</option>
              {(corpusSnapshots.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label} · {item.document_count}{" "}
                  {item.document_count === 1 ? "document" : "documents"}
                </option>
              ))}
            </select>
          </Field>
          <Field label="QA set">
            <select
              value={qaSetId}
              onChange={(event) => {
                setQaSetId(event.target.value);
                setQaSnapshotId("");
              }}
              className={selectClass}
            >
              <option value="">Select a QA set…</option>
              {(qaSets.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="QA set snapshot">
            <select
              value={qaSnapshotId}
              disabled={!qaSetId}
              onChange={(event) => {
                setQaSnapshotId(event.target.value);
                setExcludeUncovered(false);
              }}
              className={selectClass}
            >
              <option value="">Select a snapshot…</option>
              {(qaSnapshots.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label} · {item.question_count} questions
                </option>
              ))}
            </select>
          </Field>
        </div>

        {coverage.data ? (
          <section
            className="rounded-md border border-line bg-paper p-3 text-sm"
            data-testid="coverage-check"
          >
            {coverage.data.uncovered_count === 0 ? (
              <p>
                Every gold document of the {coverage.data.question_count} questions is in the corpus
                snapshot.
              </p>
            ) : (
              <>
                <p className="font-medium">
                  {coverage.data.uncovered_count} of {coverage.data.question_count} questions have
                  gold documents outside the corpus snapshot.
                </p>
                <p className="mt-1 text-xs text-ink-muted">
                  Their answer is not in the search space, so counting them would punish retrieval
                  for something it cannot do.
                </p>
                <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto text-xs">
                  {coverage.data.uncovered.map((item) => (
                    <li key={item.question_id}>
                      {item.text}
                      <span className="block font-mono text-danger">
                        missing: {item.missing_documents.map((doc) => doc.filename).join(", ")}
                      </span>
                    </li>
                  ))}
                </ul>
                <label className="mt-3 flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={excludeUncovered}
                    onChange={(event) => setExcludeUncovered(event.target.checked)}
                  />
                  Exclude them from the metrics
                </label>
              </>
            )}
          </section>
        ) : null}

        {corpusSnapshotId ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <fieldset className="text-sm">
              <legend className="mb-1 font-medium">Index builds of this snapshot</legend>
              {choices.length === 0 ? (
                <p className="text-ink-muted">No ready index build for this snapshot.</p>
              ) : (
                choices.map((build) => (
                  <label key={build.id} className="flex items-center gap-2 py-0.5">
                    <input
                      type="checkbox"
                      checked={buildIds.includes(build.id)}
                      onChange={() => setBuildIds(toggle(buildIds, build.id))}
                    />
                    {build.name}
                  </label>
                ))
              )}
              {hiddenCount > 0 ? (
                <p className="mt-1 text-xs text-ink-muted">
                  {hiddenCount} more build{hiddenCount === 1 ? " is" : "s are"} not ready yet.
                </p>
              ) : null}
              <p className="mt-1 text-xs text-ink-muted">
                Builds of other snapshots are not offered: every variant must search the same
                documents.
              </p>
            </fieldset>
            <fieldset className="text-sm">
              <legend className="mb-1 font-medium">Retrieval profiles</legend>
              {(profiles.data?.items ?? []).map((profile) => (
                <label key={profile.id} className="flex items-center gap-2 py-0.5">
                  <input
                    type="checkbox"
                    checked={profileIds.includes(profile.id)}
                    onChange={() => setProfileIds(toggle(profileIds, profile.id))}
                  />
                  {profile.name} · top-{profile.top_k}
                </label>
              ))}
            </fieldset>
          </div>
        ) : null}

        {chosenBuilds.length > 0 && qaSetId ? (
          <ChunkGoldCoverage
            qaSetId={qaSetId}
            configurationIds={[
              ...new Set(chosenBuilds.map((build) => build.chunking_configuration_id)),
            ]}
          />
        ) : null}

        {variants.length > 0 ? (
          <fieldset className="text-sm" data-testid="variant-list">
            <legend className="mb-1 font-medium">Variants (baseline)</legend>
            {variants.map((choice) => (
              <label key={choice.key} className="flex items-center gap-2 py-0.5">
                <input
                  type="radio"
                  name="baseline"
                  checked={choice.variant.is_baseline}
                  onChange={() => setBaselineKey(choice.key)}
                />
                {choice.label}
              </label>
            ))}
            <button
              type="button"
              className="mt-1 text-xs text-rust hover:underline"
              onClick={() => setBaselineKey(null)}
            >
              No baseline
            </button>
          </fieldset>
        ) : null}

        <Field label="Repetitions">
          <input
            type="number"
            min={1}
            max={20}
            value={repetitions}
            onChange={(event) => setRepetitions(Math.max(1, Number(event.target.value) || 1))}
            className="w-24 rounded-md border border-line bg-paper px-3 py-1.5"
          />
        </Field>

        {errorText ? (
          <p className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
            {errorText}
          </p>
        ) : null}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!canCreate || create.isPending}>
            Create
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
