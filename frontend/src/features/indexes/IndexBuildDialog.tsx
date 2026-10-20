import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import {
  configurationsApi,
  corporaApi,
  embeddingProfilesApi,
  indexBuildsApi,
  snapshotsApi,
  vectorStoreProfilesApi,
} from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { queryKeys } from "@/lib/queryClient";
import { toast } from "@/lib/toast";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium">{label}</span>
      {children}
    </label>
  );
}

const selectClass = "w-full rounded-md border border-line bg-paper px-3 py-1.5";

export function IndexBuildDialog({
  initialCorpusId,
  initialSnapshotId,
  onClose,
}: {
  initialCorpusId?: string;
  initialSnapshotId?: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [corpusId, setCorpusId] = useState(initialCorpusId ?? "");
  const [snapshotId, setSnapshotId] = useState(initialSnapshotId ?? "");
  const [configurationId, setConfigurationId] = useState("");
  const [embeddingId, setEmbeddingId] = useState("");
  const [vectorStoreId, setVectorStoreId] = useState("");
  const [name, setName] = useState("");
  const [startNow, setStartNow] = useState(true);

  const corpora = useQuery({ queryKey: queryKeys.corpora, queryFn: corporaApi.list });
  const snapshots = useQuery({
    queryKey: queryKeys.corpusSnapshots(corpusId),
    queryFn: () => snapshotsApi.list(corpusId),
    enabled: Boolean(corpusId),
  });
  const configurations = useQuery({
    queryKey: queryKeys.configurations,
    queryFn: configurationsApi.list,
  });
  const embeddings = useQuery({
    queryKey: queryKeys.embeddingProfiles,
    queryFn: embeddingProfilesApi.list,
  });
  const vectorStores = useQuery({
    queryKey: queryKeys.vectorStoreProfiles,
    queryFn: vectorStoreProfilesApi.list,
  });

  // An empty choice falls back to the first option, as the materialise dialog does.
  const snapshot = snapshotId || snapshots.data?.items[0]?.id || "";
  const configuration = configurationId || configurations.data?.items[0]?.id || "";
  const embedding = embeddingId || embeddings.data?.items[0]?.id || "";
  const vectorStore = vectorStoreId || vectorStores.data?.items[0]?.id || "";
  const ready = Boolean(snapshot && configuration && embedding && vectorStore);

  const create = useMutation({
    mutationFn: async () => {
      const result = await indexBuildsApi.create({
        corpus_snapshot_id: snapshot,
        chunking_configuration_id: configuration,
        embedding_profile_id: embedding,
        vector_store_profile_id: vectorStore,
        name: name.trim() || null,
      });
      const launch = startNow ? await indexBuildsApi.start(result.index_build.id) : null;
      return { result, launch };
    },
    onSuccess: async ({ result, launch }) => {
      if (!result.created) {
        toast.info(result.detail ?? "An identical index build already existed and was reused.");
      } else {
        toast.success(`Index build "${result.index_build.name}" created.`);
      }
      if (launch && !launch.started) {
        toast.info(launch.detail ?? "The same build is already running.");
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.indexBuilds });
      onClose();
    },
  });

  const missing = [
    embeddings.isSuccess && embeddings.data.items.length === 0 ? "an embedding profile" : null,
    vectorStores.isSuccess && vectorStores.data.items.length === 0
      ? "a vector store profile"
      : null,
    configurations.isSuccess && configurations.data.items.length === 0
      ? "a chunking configuration"
      : null,
    corpusId && snapshots.isSuccess && snapshots.data.items.length === 0
      ? "a snapshot of this corpus"
      : null,
  ].filter(Boolean);

  return (
    <Dialog title="New index build" onClose={onClose} wide>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Corpus">
            <select
              value={corpusId}
              onChange={(event) => {
                setCorpusId(event.target.value);
                setSnapshotId("");
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
          <Field label="Snapshot">
            <select
              value={snapshot}
              onChange={(event) => setSnapshotId(event.target.value)}
              disabled={!corpusId}
              className={selectClass}
            >
              {(snapshots.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label} · {item.document_count}{" "}
                  {item.document_count === 1 ? "document" : "documents"}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Chunking configuration">
            <select
              value={configuration}
              onChange={(event) => setConfigurationId(event.target.value)}
              className={selectClass}
            >
              {(configurations.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Embedding profile">
            <select
              value={embedding}
              onChange={(event) => setEmbeddingId(event.target.value)}
              className={selectClass}
            >
              {(embeddings.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                  {item.dimensions ? ` · ${item.dimensions}d` : ""}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Vector store profile">
            <select
              value={vectorStore}
              onChange={(event) => setVectorStoreId(event.target.value)}
              className={selectClass}
            >
              {(vectorStores.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Name (optional)">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={200}
              placeholder="Derived from snapshot, configuration and embedder"
              className={selectClass}
            />
          </Field>
        </div>

        {missing.length > 0 ? (
          <p className="rounded-md bg-amber/15 px-3 py-2 text-sm">
            Create {missing.join(", ")} first.
          </p>
        ) : null}

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={startNow}
            onChange={(event) => setStartNow(event.target.checked)}
          />
          Start indexing right away
        </label>
        <p className="text-xs text-ink-muted">
          A build is identified by snapshot, configuration, embedder and vector store together: the
          same four choices return the existing build instead of indexing again.
        </p>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!ready || create.isPending}>
            {startNow ? "Create and start" : "Create"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
