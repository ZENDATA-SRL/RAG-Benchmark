import { Shell } from "@/components/layout/Shell";
import { Card } from "@/components/ui/Card";
import { Divider } from "@/components/ui/Divider";
import { api, ApiError } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ExperimentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: experimentId } = await params;

  let experiment: Awaited<ReturnType<typeof api.experiments.getById>> | null = null;
  let answers: Awaited<ReturnType<typeof api.experiments.listAnswers>> = [];
  let coverage: Awaited<ReturnType<typeof api.experiments.questionDocumentChunkCoverage>> = [];
  let questions: Awaited<ReturnType<typeof api.datasets.listQuestions>> = [];
  let backendError: { status?: number; message: string } | null = null;

  try {
    const [e, a, c] = await Promise.all([
      api.experiments.getById(experimentId),
      api.experiments.listAnswers(experimentId),
      api.experiments.questionDocumentChunkCoverage(experimentId),
    ]);
    experiment = e;
    answers = a;
    coverage = c;

    try {
      questions = await api.datasets.listQuestions(e.dataset_id);
    } catch {
      questions = [];
    }
  } catch (err) {
    if (err instanceof ApiError) {
      backendError = { status: err.status, message: err.message };
    } else {
      backendError = { message: "Failed to contact backend." };
    }
  }

  return (
    <Shell contentWidth="wide">
      <div className="space-y-6">
        <header className="space-y-2">
          <h1 className="font-serif text-3xl tracking-tight text-ink leading-snug">
            Experiment
          </h1>
          <p className="font-serif text-xl text-slate leading-[1.7]">
            Answers generated for dataset questions.
          </p>
        </header>

        <Divider />

        {backendError ? (
          <Card>
            <div className="space-y-2">
              <div className="font-sans text-sm font-medium text-charcoal">
                Backend error{backendError.status ? ` (${backendError.status})` : ""}
              </div>
              <div className="font-sans text-sm text-ash">
                The backend returned an error while loading this experiment. Make sure it’s
                running and reachable at{" "}
                <span className="font-mono text-xs text-ash">NEXT_PUBLIC_API_BASE_URL</span>.
              </div>
            </div>
          </Card>
        ) : experiment ? (
          <>
            <Card>
              <div className="space-y-4">
                <div className="space-y-1">
                  <div className="font-sans text-sm text-ash">Name</div>
                  <div className="font-serif text-2xl tracking-tight text-ink">
                    {experiment.name}
                  </div>
                </div>

                <Divider />

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <div className="font-sans text-xs text-ash">Experiment ID</div>
                    <div className="font-mono text-xs text-ash break-all">{experiment.id}</div>
                  </div>
                  <div className="space-y-1">
                    <div className="font-sans text-xs text-ash">Dataset ID</div>
                    <div className="font-mono text-xs text-ash break-all">
                      {experiment.dataset_id}
                    </div>
                  </div>
                  <div className="space-y-1 sm:col-span-2">
                    <div className="font-sans text-xs text-ash">Created</div>
                    <div className="font-mono text-xs text-ash">{experiment.created_at}</div>
                  </div>
                </div>
              </div>
            </Card>

            <Card>
              <div className="space-y-4">
                <div>
                  <div className="font-serif text-xl tracking-tight text-ink">
                    Results
                  </div>
                  <div className="mt-1 font-sans text-sm text-ash">
                    One row per question. Presence = the answer used at least one chunk from the
                    question’s document; Absence = none.
                  </div>
                  <div className="mt-2 font-sans text-sm text-ash">
                    To inspect results correlated to the content of the answers, open{" "}
                    <a
                      href="https://langfuse.com"
                      target="_blank"
                      rel="noreferrer"
                      className="text-coral-deep underline decoration-coral/40 underline-offset-2 hover:decoration-coral"
                    >
                      Langfuse
                    </a>
                    .
                  </div>
                </div>

                <Divider />

                {answers.length === 0 && coverage.length === 0 ? (
                  <div className="font-sans text-sm text-ash">No results were returned.</div>
                ) : (() => {
                  const answerByQuestionId = new Map(answers.map((a) => [a.question_id, a]));
                  const expectedByQuestionId = new Map(questions.map((q) => [q.id, q.answer]));
                  const rows =
                    coverage.length > 0
                      ? coverage
                      : answers.map((a) => ({
                        question_id: a.question_id,
                        question: "",
                        document_id: "",
                        document_name: "",
                        document_url: "",
                        total_answer_chunks: 0,
                        answer_chunks_from_document: 0,
                        has_document_chunks: false,
                      }));

                  return (
                    <div className="rounded-xl border border-linen bg-paper overflow-hidden">
                      <div className="overflow-x-auto">
                        <table className="w-full border-separate border-spacing-0">
                          <thead>
                            <tr className="bg-linen">
                              <th className="px-4 py-3 text-left font-sans text-xs font-medium text-slate border-b border-linen border-r border-linen">
                                Question
                              </th>
                              <th className="px-4 py-3 text-left font-sans text-xs font-medium text-slate border-b border-linen border-r border-linen">
                                Expected answer
                              </th>
                              <th className="px-4 py-3 text-left font-sans text-xs font-medium text-slate border-b border-linen border-r border-linen">
                                Answer
                              </th>
                              <th className="px-4 py-3 text-left font-sans text-xs font-medium text-slate border-b border-linen border-r border-linen">
                                Right document
                              </th>
                              <th className="px-4 py-3 text-left font-sans text-xs font-medium text-slate border-b border-linen border-r border-linen">
                                Coverage
                              </th>
                              <th className="px-4 py-3 text-right font-sans text-xs font-medium text-slate border-b border-linen">
                                Presence
                              </th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-linen">
                            {rows.map((row, idx) => {
                              const a = answerByQuestionId.get(row.question_id);
                              const expected = expectedByQuestionId.get(row.question_id);
                              const isPresent = row.has_document_chunks;
                              return (
                                <tr
                                  key={row.question_id}
                                  className={[
                                    idx % 2 === 0 ? "bg-pampas" : "bg-eggshell",
                                    "hover:bg-linen/60",
                                  ].join(" ")}
                                >
                                  <td className="px-4 py-3 align-top border-r border-linen">
                                    <div className="min-w-[260px] max-w-[420px]">
                                      <div className="font-sans text-sm text-charcoal line-clamp-2">
                                        {row.question || "—"}
                                      </div>
                                      <div className="mt-1 font-mono text-[11px] text-ash/80 break-all leading-tight">
                                        {row.question_id}
                                      </div>
                                    </div>
                                  </td>
                                  <td className="px-4 py-3 align-top border-r border-linen">
                                    <div className="min-w-[240px] max-w-[420px]">
                                      <div className="font-sans text-sm text-charcoal line-clamp-3 whitespace-pre-wrap">
                                        {expected ?? "—"}
                                      </div>
                                    </div>
                                  </td>
                                  <td className="px-4 py-3 align-top border-r border-linen">
                                    <div className="min-w-[320px] max-w-[560px]">
                                      <div className="font-sans text-sm text-charcoal line-clamp-3 whitespace-pre-wrap">
                                        {a?.answer ?? "—"}
                                      </div>
                                    </div>
                                  </td>
                                  <td className="px-4 py-3 align-top border-r border-linen">
                                    <div className="min-w-[220px] max-w-[340px]">
                                      <div className="font-sans text-sm text-charcoal truncate">
                                        {row.document_name || "—"}
                                      </div>
                                      <div className="mt-1 font-mono text-[11px] text-ash/80 break-all leading-tight">
                                        {row.document_url || "—"}
                                      </div>
                                    </div>
                                  </td>
                                  <td className="px-4 py-3 align-top border-r border-linen">
                                    <div className="min-w-[140px]">
                                      <div className="font-mono text-sm font-semibold text-ink">
                                        {row.total_answer_chunks > 0
                                          ? `${row.answer_chunks_from_document}/${row.total_answer_chunks}`
                                          : "—"}
                                      </div>
                                    </div>
                                  </td>
                                  <td className="px-4 py-3 align-top text-right">
                                    <span
                                      className={[
                                        "inline-flex items-center justify-center h-7 min-w-[96px] px-3 rounded-sm border font-sans text-xs font-medium",
                                        isPresent
                                          ? "bg-sage/15 text-sage border-sage/30"
                                          : "bg-red-50 text-red-700 border-red-200",
                                      ].join(" ")}
                                    >
                                      {isPresent ? "Present" : "Absent"}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  );
                })()}
              </div>
            </Card>
          </>
        ) : (
          <Card>
            <div className="space-y-2">
              <div className="font-sans text-sm font-medium text-charcoal">Not found</div>
              <div className="font-sans text-sm text-ash">
                No experiment data was returned for this ID.
              </div>
              <div className="font-mono text-xs text-ash break-all">{experimentId}</div>
            </div>
          </Card>
        )}
      </div>
    </Shell>
  );
}

