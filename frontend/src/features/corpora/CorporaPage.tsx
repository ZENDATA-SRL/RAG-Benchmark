import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { corporaApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { formatDate, rememberCorpus } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

import { AcquisitionBar } from "./AcquisitionBar";
import { CorpusFormDialog } from "./CorpusFormDialog";

export function CorporaPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);

  const corpora = useQuery({
    queryKey: queryKeys.corpora,
    queryFn: corporaApi.list,
  });

  const items = corpora.data?.items ?? [];

  return (
    <div>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Corpora</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Mutable groupings of documents. Snapshots stay valid when this list changes.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>New corpus</Button>
      </div>

      {corpora.isError ? (
        <EmptyState
          title="Cannot reach the API"
          body="Start the backend on :8000. The UI proxies /api and /health to it."
        />
      ) : null}

      {corpora.isLoading ? <TableSkeleton /> : null}

      {corpora.isSuccess && items.length === 0 ? (
        <EmptyState
          title="No corpus yet"
          body="Create one, then drop PDFs into it. That is the start of every comparison."
          action={<Button onClick={() => setCreating(true)}>Create a corpus</Button>}
        />
      ) : null}

      <ul className="grid gap-3">
        {items.map((corpus) => (
          <CorpusCard key={corpus.id} id={corpus.id} name={corpus.name} description={corpus.description ?? null} createdAt={corpus.created_at} />
        ))}
      </ul>

      {creating ? (
        <CorpusFormDialog
          title="Create corpus"
          submitLabel="Create"
          onClose={() => setCreating(false)}
          onSubmit={async (values) => {
            const created = await corporaApi.create(values);
            await queryClient.invalidateQueries({ queryKey: queryKeys.corpora });
            rememberCorpus(created.id);
            setCreating(false);
            navigate(`/corpora/${created.id}`);
          }}
        />
      ) : null}
    </div>
  );
}

function CorpusCard({
  id,
  name,
  description,
  createdAt,
}: {
  id: string;
  name: string;
  description: string | null;
  createdAt: string;
}) {
  const progress = useQuery({
    queryKey: queryKeys.corpusProgress(id),
    queryFn: () => corporaApi.progress(id),
  });

  return (
    <li>
      <Link
        to={`/corpora/${id}`}
        onClick={() => rememberCorpus(id)}
        className="block rounded-xl border border-line bg-paper-raised px-5 py-4 hover:border-ink/25"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="font-semibold">{name}</h2>
            <p className="mt-1 text-sm text-ink-muted">{description || "No description"}</p>
          </div>
          <span className="text-xs text-ink-muted">{formatDate(createdAt)}</span>
        </div>
        <div className="mt-3">
          {progress.data ? (
            <AcquisitionBar progress={progress.data} />
          ) : (
            <p className="text-xs text-ink-muted">Loading acquisition…</p>
          )}
        </div>
      </Link>
    </li>
  );
}
