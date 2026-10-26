import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { corporaApi, qaSetsApi, questionsApi } from "@/api/resources";
import type { QuestionCreate, QuestionRead } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { queryKeys } from "@/lib/queryClient";

import { editorMode, sameIds } from "./evidence";

type Answer = { text: string; is_primary: boolean };

const TITLES = {
  create: "New question",
  edit: "Edit question",
  replace: "Replace frozen question",
} as const;

export function QuestionEditor({
  qaSetId,
  originCorpusId,
  question,
  onClose,
}: {
  qaSetId: string;
  originCorpusId: string | null;
  question: QuestionRead | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const mode = editorMode(question);
  const [text, setText] = useState(question?.text ?? "");
  const [tags, setTags] = useState((question?.tags ?? []).join(", "));
  const [answerable, setAnswerable] = useState(question?.answerable ?? true);
  const [answers, setAnswers] = useState<Answer[]>(
    question?.expected_answers.map((answer) => ({ ...answer })) ?? [],
  );
  const initialGold = question?.gold_documents.map((doc) => doc.document_id) ?? [];
  const [gold, setGold] = useState<string[]>(initialGold);
  const [documentFilter, setDocumentFilter] = useState("");

  const documents = useQuery({
    queryKey: queryKeys.corpusDocuments(originCorpusId ?? ""),
    queryFn: () => corporaApi.documents(originCorpusId ?? ""),
    enabled: Boolean(originCorpusId),
  });

  const corpusDocuments = documents.data?.items ?? [];
  const needle = documentFilter.trim().toLowerCase();
  // Selected documents stay visible while filtering, so a choice is never hidden.
  const shownDocuments = corpusDocuments.filter(
    (document) =>
      !needle || gold.includes(document.id) || document.filename.toLowerCase().includes(needle),
  );

  const body = (): QuestionCreate => ({
    text: text.trim(),
    tags: tags
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean),
    answerable,
    expected_answers: answers
      .filter((answer) => answer.text.trim())
      .map((answer) => ({ text: answer.text.trim(), is_primary: answer.is_primary })),
    gold_document_ids: gold,
  });

  const save = useMutation({
    mutationFn: async () => {
      const payload = body();
      if (mode === "create") return qaSetsApi.createQuestion(qaSetId, payload);
      if (mode === "replace") return questionsApi.replace(question!.id, payload);
      // Gold documents have their own call: unlike the rest, they can change after a freeze.
      const { text, tags, answerable, expected_answers } = payload;
      const changes = { text, tags, answerable, expected_answers };
      const updated = await questionsApi.update(question!.id, changes);
      return sameIds(gold, initialGold)
        ? updated
        : questionsApi.setGoldDocuments(question!.id, gold);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.qaSetScope(qaSetId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.qaSets });
      onClose();
    },
  });

  const updateAnswer = (index: number, change: Partial<Answer>) =>
    setAnswers((current) =>
      current.map((answer, i) => {
        if (change.is_primary)
          return { ...answer, ...(i === index ? change : { is_primary: false }) };
        return i === index ? { ...answer, ...change } : answer;
      }),
    );

  return (
    <Dialog title={TITLES[mode]} onClose={onClose} wide>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        {mode === "replace" ? (
          <p className="rounded-md bg-amber/15 p-3 text-xs leading-5" data-testid="replace-warning">
            A snapshot holds this question, so it cannot change: saving creates a new question that
            takes its place in the set. Past snapshots and experiments keep the old one. Evidence
            confirmed on the old question is not copied and has to be reviewed again.
          </p>
        ) : null}
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Question</span>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={3}
            required
            className="w-full rounded-md border border-line bg-paper-raised px-2 py-1"
          />
        </label>
        <div className="flex flex-wrap gap-4">
          <label className="block flex-1 text-sm">
            <span className="mb-1 block font-medium">Tags</span>
            <input
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              placeholder="comma separated"
              className="w-full rounded-md border border-line bg-paper-raised px-2 py-1"
            />
          </label>
          <label className="flex items-center gap-2 self-end pb-1 text-sm">
            <input
              type="checkbox"
              checked={answerable}
              onChange={(event) => setAnswerable(event.target.checked)}
            />
            Answerable
          </label>
        </div>

        <fieldset className="space-y-2">
          <legend className="mb-1 text-sm font-medium">Expected answers</legend>
          {answers.map((answer, index) => (
            <div key={index} className="flex items-start gap-2">
              <textarea
                aria-label={`Expected answer ${index + 1}`}
                value={answer.text}
                onChange={(event) => updateAnswer(index, { text: event.target.value })}
                rows={2}
                className="flex-1 rounded-md border border-line bg-paper-raised px-2 py-1 text-sm"
              />
              <label className="flex items-center gap-1 pt-1 text-xs text-ink-muted">
                <input
                  type="radio"
                  name="primary-answer"
                  checked={answer.is_primary}
                  onChange={() => updateAnswer(index, { is_primary: true })}
                />
                primary
              </label>
              <Button
                type="button"
                variant="ghost"
                aria-label={`Remove answer ${index + 1}`}
                onClick={() => setAnswers((current) => current.filter((_, i) => i !== index))}
              >
                ×
              </Button>
            </div>
          ))}
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              setAnswers((current) => [...current, { text: "", is_primary: current.length === 0 }])
            }
          >
            Add answer
          </Button>
        </fieldset>

        <fieldset>
          <legend className="mb-1 text-sm font-medium">
            Gold documents
            {originCorpusId ? (
              <span className="ml-2 font-normal text-ink-muted">
                {gold.length} of {corpusDocuments.length} selected
              </span>
            ) : null}
          </legend>
          {!originCorpusId ? (
            <p className="text-xs text-ink-muted">
              The set has no origin corpus: gold documents come from the evidence chunks you
              confirm.
            </p>
          ) : documents.isPending ? (
            <p className="text-xs text-ink-muted">Loading the documents of the origin corpus…</p>
          ) : documents.isError ? (
            <p className="text-xs text-danger">
              Could not load the documents of the origin corpus.
            </p>
          ) : corpusDocuments.length === 0 ? (
            <p className="text-xs text-ink-muted">The origin corpus has no documents yet.</p>
          ) : (
            <div className="space-y-2">
              <input
                type="search"
                aria-label="Filter documents"
                value={documentFilter}
                onChange={(event) => setDocumentFilter(event.target.value)}
                placeholder="Filter by filename"
                className="w-full rounded-md border border-line bg-paper-raised px-2 py-1 text-sm"
              />
              <div
                className="max-h-64 space-y-1 overflow-y-auto rounded-md border border-line p-2"
                data-testid="gold-documents"
              >
                {shownDocuments.map((document) => (
                  <label key={document.id} className="flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      checked={gold.includes(document.id)}
                      onChange={(event) =>
                        setGold((current) =>
                          event.target.checked
                            ? [...current, document.id]
                            : current.filter((id) => id !== document.id),
                        )
                      }
                    />
                    <span className="font-mono">{document.filename}</span>
                  </label>
                ))}
                {shownDocuments.length === 0 ? (
                  <p className="text-xs text-ink-muted">No document matches the filter.</p>
                ) : null}
              </div>
            </div>
          )}
          <p className="mt-1 text-xs text-ink-muted">
            Optional: confirming evidence chunks adds their documents here.
          </p>
        </fieldset>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!text.trim() || save.isPending}>
            {mode === "replace" ? "Replace" : "Save"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
