import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { corporaApi, qaSetsApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { formatDate } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

function CreateQaSetDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [corpusId, setCorpusId] = useState("");

  const corpora = useQuery({ queryKey: queryKeys.corpora, queryFn: corporaApi.list });
  const create = useMutation({
    mutationFn: () =>
      qaSetsApi.create({
        name: name.trim(),
        description: description.trim() || null,
        origin_corpus_id: corpusId || null,
      }),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.qaSets });
      onClose();
      navigate(`/qa-sets/${created.id}`);
    },
  });

  return (
    <Dialog title="New QA set" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Name</span>
          <input
            required
            maxLength={200}
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-full rounded-md border border-line bg-paper px-3 py-1.5"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Description</span>
          <textarea
            maxLength={2000}
            rows={3}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            className="w-full rounded-md border border-line bg-paper px-3 py-1.5"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Origin corpus (optional)</span>
          <select
            value={corpusId}
            onChange={(event) => setCorpusId(event.target.value)}
            className="w-full rounded-md border border-line bg-paper px-3 py-1.5"
          >
            <option value="">None</option>
            {(corpora.data?.items ?? []).map((corpus) => (
              <option key={corpus.id} value={corpus.id}>
                {corpus.name}
              </option>
            ))}
          </select>
        </label>
        <p className="text-xs text-ink-muted">
          The corpus is only a note of where the questions come from. Gold documents are resolved by
          file name when the questions are imported.
        </p>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!name.trim() || create.isPending}>
            Create
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function QaSetsPage() {
  const [creating, setCreating] = useState(false);
  const qaSets = useQuery({ queryKey: queryKeys.qaSets, queryFn: qaSetsApi.list });
  const items = qaSets.data?.items ?? [];

  return (
    <div>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">QA sets</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Questions with the documents that answer them. Freeze a set to use it in an experiment.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>New QA set</Button>
      </div>

      {qaSets.isLoading ? <TableSkeleton /> : null}
      {qaSets.isSuccess && items.length === 0 ? (
        <EmptyState
          title="No QA set yet"
          body="Create one, then import its questions from a CSV or JSONL file."
          action={<Button onClick={() => setCreating(true)}>Create a QA set</Button>}
        />
      ) : null}

      <ul className="grid gap-3">
        {items.map((qaSet) => (
          <li key={qaSet.id}>
            <Link
              to={`/qa-sets/${qaSet.id}`}
              className="block rounded-xl border border-line bg-paper-raised px-5 py-4 hover:border-ink/25"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="font-semibold">{qaSet.name}</h2>
                  <p className="mt-1 text-sm text-ink-muted">
                    {qaSet.description || "No description"}
                  </p>
                </div>
                <div className="text-right text-xs text-ink-muted">
                  <p>
                    {qaSet.question_count ?? 0}{" "}
                    {qaSet.question_count === 1 ? "question" : "questions"}
                  </p>
                  <p>{formatDate(qaSet.created_at)}</p>
                </div>
              </div>
            </Link>
          </li>
        ))}
      </ul>

      {creating ? <CreateQaSetDialog onClose={() => setCreating(false)} /> : null}
    </div>
  );
}
