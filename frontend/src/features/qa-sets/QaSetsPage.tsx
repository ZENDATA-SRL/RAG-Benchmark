import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { corporaApi, qaSetsApi } from "@/api/resources";
import type { QASetRead } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { formatDate } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

export function CreateQaSetDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [corpusId, setCorpusId] = useState("");
  // The name follows the chosen corpus until the user types one of their own.
  const [nameEdited, setNameEdited] = useState(false);

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
            onChange={(event) => {
              setName(event.target.value);
              setNameEdited(event.target.value.trim() !== "");
            }}
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
            onChange={(event) => {
              const next = event.target.value;
              setCorpusId(next);
              if (!nameEdited) {
                setName(corpora.data?.items.find((corpus) => corpus.id === next)?.name ?? "");
              }
            }}
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
  const corpora = useQuery({ queryKey: queryKeys.corpora, queryFn: corporaApi.list });
  const items = qaSets.data?.items;

  // One group per origin corpus, sorted by corpus name; sets without a corpus come last.
  const groups = useMemo(() => {
    const names = new Map((corpora.data?.items ?? []).map((corpus) => [corpus.id, corpus.name]));
    const byCorpus = new Map<string | null, QASetRead[]>();
    for (const qaSet of items ?? []) {
      const key = qaSet.origin_corpus_id ?? null;
      byCorpus.set(key, [...(byCorpus.get(key) ?? []), qaSet]);
    }
    return [...byCorpus.entries()]
      .map(([corpusId, groupItems]) => ({
        corpusId,
        name: corpusId ? (names.get(corpusId) ?? "Unknown corpus") : "No corpus",
        items: groupItems,
      }))
      .sort((a, b) => {
        if (!a.corpusId || !b.corpusId) return a.corpusId ? -1 : b.corpusId ? 1 : 0;
        return a.name.localeCompare(b.name);
      });
  }, [items, corpora.data]);

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
      {qaSets.isSuccess && groups.length === 0 ? (
        <EmptyState
          title="No QA set yet"
          body="Create one, then import its questions from a CSV or JSONL file."
          action={<Button onClick={() => setCreating(true)}>Create a QA set</Button>}
        />
      ) : null}

      <div className="space-y-8">
        {groups.map((group) => (
          <section key={group.corpusId ?? "none"}>
            <h2 className="mb-2 flex items-baseline gap-2 text-sm font-semibold">
              {group.corpusId ? (
                <Link to={`/corpora/${group.corpusId}`} className="hover:underline">
                  {group.name}
                </Link>
              ) : (
                <span>{group.name}</span>
              )}
              <span className="text-xs font-normal text-ink-muted">
                {group.items.length} {group.items.length === 1 ? "set" : "sets"}
              </span>
            </h2>
            <QaSetList items={group.items} />
          </section>
        ))}
      </div>

      {creating ? <CreateQaSetDialog onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

function QaSetList({ items }: { items: QASetRead[] }) {
  return (
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
  );
}
