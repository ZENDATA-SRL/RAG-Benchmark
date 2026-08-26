"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Shell } from "@/components/layout/Shell";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Divider } from "@/components/ui/Divider";
import { XlsxUpload } from "@/components/benchmark/XlsxUpload";
import { api } from "@/lib/api";

export default function DatasetDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const datasetId = params.id;

  const [datasetName, setDatasetName] = useState<string>(datasetId);
  const [documentsDone, setDocumentsDone] = useState(false);
  const [questionsDone, setQuestionsDone] = useState(false);
  const [isLoadingState, setIsLoadingState] = useState(true);

  const [documents, setDocuments] = useState<Awaited<ReturnType<typeof api.datasets.listDocuments>>>(
    [],
  );
  const [questions, setQuestions] = useState<Awaited<ReturnType<typeof api.datasets.listQuestions>>>(
    [],
  );
  const [visualizeOpen, setVisualizeOpen] = useState<null | "questions" | "documents">(null);

  const [danger, setDanger] = useState<"idle" | "deleting" | "error">("idle");
  const [dangerMsg, setDangerMsg] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setIsLoadingState(true);
      try {
        const [docsRes, qsRes] = await Promise.allSettled([
          api.datasets.listDocuments(datasetId),
          api.datasets.listQuestions(datasetId),
        ]);

        if (cancelled) return;

        if (docsRes.status === "fulfilled") {
          setDocuments(docsRes.value);
          setDocumentsDone(docsRes.value.length > 0);
        }
        if (qsRes.status === "fulfilled") {
          setQuestions(qsRes.value);
          setQuestionsDone(qsRes.value.length > 0);
        }
      } catch {
        if (cancelled) return;
        // If backend is unavailable, fall back to current optimistic local state.
      } finally {
        if (!cancelled) setIsLoadingState(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const all = await api.datasets.list();
        const found = all.find((d) => d.id === datasetId);
        if (!cancelled) setDatasetName(found?.name ?? datasetId);
      } catch {
        if (!cancelled) setDatasetName(datasetId);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  const hasQuestions = questions.length > 0;
  const hasDocuments = documents.length > 0;

  return (
    <Shell contentWidth={visualizeOpen ? "wide" : "chat"}>
      <div className="space-y-6">
        <header className="flex items-start justify-between gap-4">
          <div className="space-y-2 min-w-0">
            <div className="font-sans text-sm text-ash">Dataset</div>
            <h1 className="font-serif text-3xl tracking-tight text-ink leading-snug truncate">
              {datasetName}
            </h1>
            <div className="font-mono text-xs text-ash break-all">{datasetId}</div>
          </div>
          <Button variant="secondary" onClick={() => router.push("/datasets")}>
            Back
          </Button>
        </header>

        <Divider />

        <Card>
          <div className="space-y-6">
            <div className="space-y-2">
              <div className="font-serif text-xl tracking-tight text-ink">Upload</div>
              <div className="font-sans text-sm text-ash">
                Upload documents first. Once that finishes, you can upload questions referencing
                those documents.
              </div>
            </div>

            {documentsDone ? (
              <div className="flex items-center justify-between gap-4 rounded-lg border border-linen bg-paper px-4 py-3">
                <div className="min-w-0">
                  <div className="font-sans text-sm font-medium text-charcoal">
                    Step 1 — Documents
                  </div>
                  <div className="mt-1 font-sans text-sm text-ash">
                    Documents already uploaded.
                  </div>
                </div>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setVisualizeOpen((v) => (v === "documents" ? null : "documents"));
                  }}
                  disabled={!hasDocuments}
                >
                  {visualizeOpen === "documents" ? "Hide" : "Visualize"}
                </Button>
              </div>
            ) : (
              <XlsxUpload
                label="Step 1 — Documents file"
                help="Accepted: .xlsx or .csv. Expected columns: file_name (or filename), file_url"
                disabled={documentsDone}
                onUpload={async (file) => {
                  const res = await api.datasets.uploadDocumentsXlsx(datasetId, file);
                  setDocumentsDone(true);
                  setDocuments(await api.datasets.listDocuments(datasetId));
                  return res;
                }}
              />
            )}

            {visualizeOpen === "documents" ? (
              <>
                <Divider />
                <div className="rounded-xl border border-linen bg-paper overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full border-separate border-spacing-0">
                      <thead>
                        <tr className="bg-linen">
                          <th className="px-4 py-3 text-left font-sans text-xs font-medium text-slate border-b border-linen border-r border-linen">
                            Name
                          </th>
                          <th className="px-4 py-3 text-left font-sans text-xs font-medium text-slate border-b border-linen border-r border-linen">
                            Source URL
                          </th>
                          <th className="px-4 py-3 text-left font-sans text-xs font-medium text-slate border-b border-linen border-r border-linen">
                            Blob URL
                          </th>
                          <th className="px-4 py-3 text-right font-sans text-xs font-medium text-slate border-b border-linen">
                            Document ID
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-linen">
                        {documents.map((d, idx) => (
                          <tr
                            key={d.id}
                            className={[
                              idx % 2 === 0 ? "bg-pampas" : "bg-eggshell",
                              "hover:bg-linen/60",
                            ].join(" ")}
                          >
                            <td className="px-4 py-3 align-top border-r border-linen">
                              <div className="min-w-[240px] max-w-[360px]">
                                <div className="font-sans text-sm text-charcoal truncate">
                                  {d.name}
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-3 align-top border-r border-linen">
                              <div className="min-w-[320px] max-w-[520px]">
                                <div className="font-mono text-[11px] text-ash/80 break-all leading-tight">
                                  {d.url}
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-3 align-top border-r border-linen">
                              <div className="min-w-[320px] max-w-[520px]">
                                <div className="font-mono text-[11px] text-ash/80 break-all leading-tight">
                                  {d.blob_url}
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-3 align-top text-right">
                              <div className="min-w-[240px] max-w-[360px] ml-auto">
                                <div className="font-mono text-[11px] text-ash/80 break-all leading-tight">
                                  {d.id}
                                </div>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            ) : null}

            {isLoadingState ? (
              <div className="rounded-lg border border-linen bg-paper px-4 py-3">
                <div className="font-sans text-sm font-medium text-charcoal">
                  Checking progress…
                </div>
                <div className="mt-1 font-sans text-sm text-ash">
                  Loading documents/questions state from the backend.
                </div>
              </div>
            ) : documentsDone ? (
              <>
                <Divider />
                {questionsDone ? (
                  <div className="flex items-center justify-between gap-4 rounded-lg border border-linen bg-paper px-4 py-3">
                    <div className="min-w-0">
                      <div className="font-sans text-sm font-medium text-charcoal">
                        Step 2 — Questions
                      </div>
                      <div className="mt-1 font-sans text-sm text-ash">
                        Questions already uploaded.
                      </div>
                    </div>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setVisualizeOpen((v) => (v === "questions" ? null : "questions"));
                      }}
                      disabled={!hasQuestions}
                    >
                      {visualizeOpen === "questions" ? "Hide" : "Visualize"}
                    </Button>
                  </div>
                ) : (
                  <XlsxUpload
                    label="Step 2 — Questions file"
                    help="Accepted: .xlsx or .csv. Expected columns: query, answer, filename, file_url"
                    disabled={questionsDone}
                    onUpload={async (file) => {
                      const res = await api.datasets.uploadQuestionsXlsx(datasetId, file);
                      setQuestionsDone(true);
                      setQuestions(await api.datasets.listQuestions(datasetId));
                      return res;
                    }}
                  />
                )}
                {questionsDone ? (
                  <div className="font-sans text-sm text-sage">
                    Questions uploaded successfully.
                  </div>
                ) : null}

                {visualizeOpen === "questions" ? (
                  <>
                    <Divider />
                    <div className="rounded-xl border border-linen bg-paper overflow-hidden">
                      <div className="overflow-x-auto">
                        <table className="w-full border-separate border-spacing-0">
                          <thead>
                            <tr className="bg-linen">
                              <th className="px-4 py-3 text-left font-sans text-xs font-medium text-slate border-b border-linen border-r border-linen">
                                Query
                              </th>
                              <th className="px-4 py-3 text-left font-sans text-xs font-medium text-slate border-b border-linen border-r border-linen">
                                Expected answer
                              </th>
                              <th className="px-4 py-3 text-left font-sans text-xs font-medium text-slate border-b border-linen border-r border-linen">
                                Document ID
                              </th>
                              <th className="px-4 py-3 text-right font-sans text-xs font-medium text-slate border-b border-linen">
                                Question ID
                              </th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-linen">
                            {questions.map((q, idx) => (
                              <tr
                                key={q.id}
                                className={[
                                  idx % 2 === 0 ? "bg-pampas" : "bg-eggshell",
                                  "hover:bg-linen/60",
                                ].join(" ")}
                              >
                                <td className="px-4 py-3 align-top border-r border-linen">
                                  <div className="min-w-[320px] max-w-[520px]">
                                    <div className="font-sans text-sm text-charcoal line-clamp-3 whitespace-pre-wrap">
                                      {q.query}
                                    </div>
                                  </div>
                                </td>
                                <td className="px-4 py-3 align-top border-r border-linen">
                                  <div className="min-w-[320px] max-w-[520px]">
                                    <div className="font-sans text-sm text-charcoal line-clamp-3 whitespace-pre-wrap">
                                      {q.answer}
                                    </div>
                                  </div>
                                </td>
                                <td className="px-4 py-3 align-top border-r border-linen">
                                  <div className="min-w-[240px] max-w-[360px]">
                                    <div className="font-mono text-[11px] text-ash/80 break-all leading-tight">
                                      {q.document_id}
                                    </div>
                                  </div>
                                </td>
                                <td className="px-4 py-3 align-top text-right">
                                  <div className="min-w-[240px] max-w-[360px] ml-auto">
                                    <div className="font-mono text-[11px] text-ash/80 break-all leading-tight">
                                      {q.id}
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </>
                ) : null}
              </>
            ) : (
              <div className="rounded-lg border border-linen bg-paper px-4 py-3">
                <div className="font-sans text-sm font-medium text-charcoal">
                  Step 2 — Questions file
                </div>
                <div className="mt-1 font-sans text-sm text-ash">
                  Upload documents first to unlock this step.
                </div>
              </div>
            )}
          </div>
        </Card>

        <Card className="border-red-200">
          <div className="space-y-3">
            <div className="font-serif text-xl tracking-tight text-ink">Danger zone</div>
            <div className="font-sans text-sm text-ash">
              Deleting a dataset will remove its documents, questions, and derived artifacts.
            </div>
            <div className="flex flex-col sm:flex-row gap-3">
              <Button
                variant="danger"
                disabled={danger === "deleting"}
                onClick={async () => {
                  setDanger("deleting");
                  setDangerMsg("");
                  try {
                    await api.datasets.delete(datasetId);
                    router.push("/datasets");
                  } catch (e) {
                    setDanger("error");
                    setDangerMsg(e instanceof Error ? e.message : "Delete failed.");
                  } finally {
                    setDanger("idle");
                  }
                }}
              >
                {danger === "deleting" ? "Deleting…" : "Delete dataset"}
              </Button>
            </div>
            {dangerMsg ? <div className="font-sans text-sm text-red-700">{dangerMsg}</div> : null}
          </div>
        </Card>
      </div>
    </Shell>
  );
}

