import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { corporaApi } from "@/api/resources";
import type { DocumentRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { TableFrame } from "@/components/ui/TableFrame";
import { formatBytes, formatDate, rememberCorpus } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";
import { toast } from "@/lib/toast";
import { UploadDialog } from "@/features/documents/UploadDialog";
import { MaterializeDialog } from "@/features/materializations/MaterializeDialog";
import { PreviewDialog } from "@/features/materializations/PreviewDialog";
import { ProgressPanel } from "@/features/materializations/ProgressPanel";
import { SnapshotDialog } from "@/features/snapshots/SnapshotDialog";
import { SnapshotsPanel } from "@/features/snapshots/SnapshotsPanel";

import { AcquisitionBar } from "./AcquisitionBar";
import { CorpusFormDialog } from "./CorpusFormDialog";
import { DocumentDrawer } from "./DocumentDrawer";

function acquisitionTone(status: string): "good" | "bad" | "warn" | "neutral" {
  if (status === "stored") return "good";
  if (status === "failed") return "bad";
  if (status === "fetching") return "warn";
  return "neutral";
}

export function CorpusDetailPage() {
  const { corpusId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const selectedId = params.get("document");
  const [editing, setEditing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [materializing, setMaterializing] = useState(false);
  const [freezing, setFreezing] = useState(false);
  const [previewing, setPreviewing] = useState<DocumentRead | null>(null);
  const [removing, setRemoving] = useState<DocumentRead | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const corpus = useQuery({
    queryKey: queryKeys.corpus(corpusId),
    queryFn: () => corporaApi.get(corpusId),
    enabled: Boolean(corpusId),
  });
  const documents = useQuery({
    queryKey: queryKeys.corpusDocuments(corpusId),
    queryFn: () => corporaApi.documents(corpusId),
    enabled: Boolean(corpusId),
  });
  const progress = useQuery({
    queryKey: queryKeys.corpusProgress(corpusId),
    queryFn: () => corporaApi.progress(corpusId),
    enabled: Boolean(corpusId),
  });

  const remove = useMutation({
    mutationFn: (documentId: string) => corporaApi.removeDocument(corpusId, documentId),
    onSuccess: async (result) => {
      toast.info(result.detail);
      setRemoving(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.corpusDocuments(corpusId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.corpusProgress(corpusId) });
    },
  });

  const items = useMemo(() => documents.data?.items ?? [], [documents.data?.items]);
  const allSelected = items.length > 0 && items.every((item) => selected.has(item.id));

  const selectedDocuments = useMemo(
    () => items.filter((item) => selected.has(item.id)),
    [items, selected],
  );

  if (corpus.isSuccess) {
    rememberCorpus(corpus.data.id);
  }

  return (
    <div className="-mx-6 -my-6 flex min-h-[calc(100vh-3rem)]">
      <div className="min-w-0 flex-1 px-6 py-6">
        <p className="text-xs text-ink-muted">
          <Link to="/corpora" className="hover:underline">
            Corpora
          </Link>
          <span> / </span>
          <span>{corpus.data?.name ?? "…"}</span>
        </p>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">{corpus.data?.name ?? "Corpus"}</h1>
            <p className="mt-1 text-sm text-ink-muted">
              {corpus.data?.description || "No description"}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Edit
            </Button>
            <Button variant="secondary" onClick={() => setUploading(true)}>
              Upload PDFs
            </Button>
            <Button
              variant="secondary"
              disabled={selectedDocuments.length !== 1}
              onClick={() => {
                const only = selectedDocuments[0] ?? items[0];
                if (only) setPreviewing(only);
              }}
              title="Try one document before the whole corpus"
            >
              Preview on one document
            </Button>
            <Button onClick={() => setMaterializing(true)}>Materialise chunks</Button>
            <Button
              variant="secondary"
              disabled={items.length === 0}
              onClick={() => setFreezing(true)}
              title="Freeze the documents an index will search over"
            >
              Freeze snapshot
            </Button>
          </div>
        </div>

        <div className="mt-4 max-w-xl">
          {progress.data ? <AcquisitionBar progress={progress.data} /> : null}
        </div>
        <p className="mt-1 text-xs text-ink-muted">
          Status here is acquisition (downloaded and stored), not parsing. Parsing lives on a
          configuration.
        </p>

        {runId ? (
          <div className="mt-5">
            <ProgressPanel runId={runId} documents={items} onClose={() => setRunId(null)} />
          </div>
        ) : null}

        <SnapshotsPanel corpusId={corpusId} />

        <div className="mt-6">
          {documents.isLoading ? <TableSkeleton /> : null}
          {documents.isSuccess && items.length === 0 ? (
            <EmptyState
              title="No documents in this corpus"
              body="Upload PDFs to give the pipeline something to parse and chunk."
              action={<Button onClick={() => setUploading(true)}>Upload PDFs</Button>}
            />
          ) : null}
          {items.length > 0 ? (
            <p className="mb-2 text-xs text-ink-muted">
              {items.length} {items.length === 1 ? "document" : "documents"}
              {selected.size > 0 ? ` · ${selected.size} selected` : ""}
            </p>
          ) : null}
          {items.length > 0 ? (
            <TableFrame>
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line bg-paper text-xs text-ink-muted">
                  <tr>
                    <th className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        onChange={() => {
                          setSelected(
                            allSelected ? new Set() : new Set(items.map((item) => item.id)),
                          );
                        }}
                        aria-label="Select all documents"
                      />
                    </th>
                    <th className="px-3 py-2 font-medium">Name</th>
                    <th className="px-3 py-2 font-medium">Size</th>
                    <th className="px-3 py-2 font-medium">Acquisition</th>
                    <th className="px-3 py-2 font-medium">Added</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((document) => (
                    <tr
                      key={document.id}
                      className={`border-b border-line last:border-0 ${selectedId === document.id ? "bg-rust/5" : ""}`}
                    >
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={selected.has(document.id)}
                          onChange={() => {
                            setSelected((current) => {
                              const next = new Set(current);
                              if (next.has(document.id)) next.delete(document.id);
                              else next.add(document.id);
                              return next;
                            });
                          }}
                          aria-label={`Select ${document.filename}`}
                        />
                      </td>
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          className="text-left font-medium hover:underline"
                          onClick={() => {
                            const next = new URLSearchParams(params);
                            next.set("document", document.id);
                            setParams(next);
                          }}
                        >
                          {document.filename}
                        </button>
                      </td>
                      <td className="px-3 py-2 text-ink-muted">
                        {formatBytes(document.size_bytes)}
                      </td>
                      <td className="px-3 py-2">
                        <Badge tone={acquisitionTone(document.status)}>{document.status}</Badge>
                      </td>
                      <td className="px-3 py-2 text-ink-muted">
                        {formatDate(document.created_at)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Button variant="ghost" onClick={() => setPreviewing(document)}>
                          Preview
                        </Button>
                        <Button
                          variant="ghost"
                          onClick={() =>
                            navigate(`/corpora/${corpusId}/documents/${document.id}/chunks`)
                          }
                        >
                          Inspect
                        </Button>
                        <Button variant="ghost" onClick={() => setRemoving(document)}>
                          Remove
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableFrame>
          ) : null}
        </div>
      </div>

      {selectedId ? (
        <DocumentDrawer
          documentId={selectedId}
          onClose={() => {
            const next = new URLSearchParams(params);
            next.delete("document");
            setParams(next);
          }}
        />
      ) : null}

      {editing && corpus.data ? (
        <CorpusFormDialog
          title="Edit corpus"
          initialName={corpus.data.name}
          initialDescription={corpus.data.description ?? ""}
          submitLabel="Save"
          onClose={() => setEditing(false)}
          onSubmit={async (values) => {
            await corporaApi.update(corpusId, values);
            await queryClient.invalidateQueries({ queryKey: queryKeys.corpus(corpusId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.corpora });
            setEditing(false);
          }}
        />
      ) : null}

      {uploading ? (
        <UploadDialog
          corpusId={corpusId}
          onClose={() => setUploading(false)}
          onFinished={async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.corpusDocuments(corpusId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.corpusProgress(corpusId) });
          }}
        />
      ) : null}

      {materializing ? (
        <MaterializeDialog
          corpusId={corpusId}
          selectedIds={[...selected]}
          onClose={() => setMaterializing(false)}
          onStarted={(id) => {
            setRunId(id);
            setMaterializing(false);
          }}
        />
      ) : null}

      {freezing ? (
        <SnapshotDialog
          corpusId={corpusId}
          selectedIds={[...selected]}
          onClose={() => setFreezing(false)}
        />
      ) : null}

      {previewing ? (
        <PreviewDialog
          corpusId={corpusId}
          document={previewing}
          onClose={() => setPreviewing(null)}
          onStarted={(id) => {
            setRunId(id);
            setPreviewing(null);
          }}
        />
      ) : null}

      {removing ? (
        <ConfirmDialog
          title="Remove from corpus"
          body="The document is detached from this corpus. Existing snapshots remain valid: they keep their frozen composition, and the file itself is not deleted."
          confirmLabel="Remove from corpus"
          pending={remove.isPending}
          onClose={() => setRemoving(null)}
          onConfirm={() => remove.mutate(removing.id)}
        />
      ) : null}
    </div>
  );
}
