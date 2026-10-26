import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { embeddingProfilesApi, indexBuildsApi, vectorStoreProfilesApi } from "@/api/resources";
import type { IndexBuildRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { TableFrame } from "@/components/ui/TableFrame";
import { formatDate, shortHash } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";
import { toast } from "@/lib/toast";

import { QueryPanel } from "../retrieval/QueryPanel";
import { IndexBuildDialog } from "./IndexBuildDialog";
import { ProfileDialog, type ProfileKind } from "./ProfileDialog";
import { buildStatusTone, canQuery, canStart, hasRunningBuild } from "./status";

const POLL_MS = 3000;

function BuildDetailDialog({ build, onClose }: { build: IndexBuildRead; onClose: () => void }) {
  const detail = useQuery({
    queryKey: queryKeys.indexBuild(build.id),
    queryFn: () => indexBuildsApi.get(build.id),
    refetchInterval: (query) => (query.state.data?.status === "running" ? POLL_MS : false),
  });
  const current = detail.data ?? build;

  const rows: [string, string][] = [
    ["Status", current.status],
    ["Chunks", detail.data ? String(detail.data.chunk_count) : "…"],
    ["Collection", current.external_index_ref],
    ["Fingerprint", shortHash(current.chain_fingerprint, 16)],
    ["Workflow", current.workflow_id ?? "never started"],
    ["Created", formatDate(current.created_at)],
  ];

  return (
    <Dialog title={current.name} onClose={onClose}>
      <dl className="grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-ink-muted">{label}</dt>
            <dd className="font-mono text-xs break-all">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 text-xs text-ink-muted">
        The chunk count is what the build indexes now; it grows while chunks are being materialised.
      </p>
    </Dialog>
  );
}

function ProfileList({
  title,
  items,
  describe,
  onCreate,
}: {
  title: string;
  items: { id: string; name: string; config_hash: string }[];
  describe: (id: string) => string;
  onCreate: () => void;
}) {
  return (
    <section className="rounded-xl border border-line bg-paper-raised p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold">{title}</h2>
        <Button variant="secondary" onClick={onCreate}>
          New
        </Button>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-ink-muted">None yet.</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {items.map((item) => (
            <li key={item.id} className="flex items-baseline justify-between gap-3">
              <span className="font-medium">{item.name}</span>
              <span className="truncate text-xs text-ink-muted">{describe(item.id)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function IndexesPage() {
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const prefillSnapshot = params.get("snapshot") ?? undefined;
  const prefillCorpus = params.get("corpus") ?? undefined;
  const [creating, setCreating] = useState(Boolean(prefillSnapshot));
  const [profileKind, setProfileKind] = useState<ProfileKind | null>(null);
  const [inspecting, setInspecting] = useState<IndexBuildRead | null>(null);
  const [querying, setQuerying] = useState<IndexBuildRead | null>(null);

  const builds = useQuery({
    queryKey: queryKeys.indexBuilds,
    queryFn: () => indexBuildsApi.list(),
    refetchInterval: (query) => (hasRunningBuild(query.state.data?.items ?? []) ? POLL_MS : false),
  });
  const embeddings = useQuery({
    queryKey: queryKeys.embeddingProfiles,
    queryFn: embeddingProfilesApi.list,
  });
  const vectorStores = useQuery({
    queryKey: queryKeys.vectorStoreProfiles,
    queryFn: vectorStoreProfilesApi.list,
  });

  const start = useMutation({
    mutationFn: (id: string) => indexBuildsApi.start(id),
    onSuccess: async (result) => {
      if (result.started) toast.success(`Indexing "${result.name}" started.`);
      else toast.info(result.detail ?? "The same build is already running.");
      await queryClient.invalidateQueries({ queryKey: queryKeys.indexBuilds });
    },
  });

  const embeddingName = (id: string) =>
    embeddings.data?.items.find((item) => item.id === id)?.name ?? "—";
  const vectorStoreName = (id: string) =>
    vectorStores.data?.items.find((item) => item.id === id)?.name ?? "—";
  const items = builds.data?.items ?? [];

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Indexes</h1>
          <p className="mt-1 text-sm text-ink-muted">
            An index build embeds the chunks of a snapshot and writes them to a vector store.
            Experiments choose among builds that already exist.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>New index build</Button>
      </div>

      {builds.isLoading ? <TableSkeleton /> : null}
      {builds.isSuccess && items.length === 0 ? (
        <EmptyState
          title="No index builds yet"
          body="Freeze a snapshot on a corpus, create an embedding and a vector store profile, then build the index."
          action={<Button onClick={() => setCreating(true)}>New index build</Button>}
        />
      ) : null}

      {items.length > 0 ? (
        <TableFrame>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-paper text-xs text-ink-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Embedding</th>
                <th className="px-4 py-2 font-medium">Vector store</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Created</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((build) => (
                <tr key={build.id} className="border-b border-line last:border-0">
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      className="text-left font-medium hover:underline"
                      onClick={() => setInspecting(build)}
                    >
                      {build.name}
                    </button>
                  </td>
                  <td className="px-4 py-3">{embeddingName(build.embedding_profile_id)}</td>
                  <td className="px-4 py-3">{vectorStoreName(build.vector_store_profile_id)}</td>
                  <td className="px-4 py-3">
                    <Badge tone={buildStatusTone(build.status)}>{build.status}</Badge>
                  </td>
                  <td className="px-4 py-3 text-ink-muted">{formatDate(build.created_at)}</td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {canQuery(build) ? (
                      <Button variant="ghost" onClick={() => setQuerying(build)}>
                        Try query
                      </Button>
                    ) : null}
                    <Button
                      variant="ghost"
                      disabled={!canStart(build) || start.isPending}
                      onClick={() => start.mutate(build.id)}
                    >
                      {build.status === "pending" ? "Start" : "Restart"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableFrame>
      ) : null}

      <div className="mt-8 grid gap-4 md:grid-cols-2">
        <ProfileList
          title="Embedding profiles"
          items={embeddings.data?.items ?? []}
          describe={(id) => {
            const profile = embeddings.data?.items.find((item) => item.id === id);
            const model = profile?.params?.model_name;
            return [
              typeof model === "string" ? model : null,
              profile?.dimensions ? `${profile.dimensions}d` : null,
            ]
              .filter(Boolean)
              .join(" · ");
          }}
          onCreate={() => setProfileKind("embedder")}
        />
        <ProfileList
          title="Vector store profiles"
          items={vectorStores.data?.items ?? []}
          describe={(id) => {
            const space = vectorStores.data?.items.find((item) => item.id === id)?.index_params
              ?.space;
            return typeof space === "string" ? `space ${space}` : "";
          }}
          onCreate={() => setProfileKind("vector_store")}
        />
      </div>

      {creating ? (
        <IndexBuildDialog
          initialCorpusId={prefillCorpus}
          initialSnapshotId={prefillSnapshot}
          onClose={() => {
            setCreating(false);
            if (prefillSnapshot) setParams(new URLSearchParams());
          }}
        />
      ) : null}
      {profileKind ? (
        <ProfileDialog kind={profileKind} onClose={() => setProfileKind(null)} />
      ) : null}
      {inspecting ? (
        <BuildDetailDialog build={inspecting} onClose={() => setInspecting(null)} />
      ) : null}
      {querying ? <QueryPanel build={querying} onClose={() => setQuerying(null)} /> : null}
    </div>
  );
}
