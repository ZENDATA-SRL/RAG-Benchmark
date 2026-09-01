import { useCallback, useState } from "react";

import { documentsApi } from "@/api/resources";
import type { UploadFileResult } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { errorToastText } from "@/lib/errors";

import { UploadSummary } from "./UploadSummary";
import { partitionFiles, toUploadResult } from "./uploadValidation";

type FileProgress = { name: string; percent: number; status: "pending" | "uploading" | "done" };

export function UploadDialog({
  corpusId,
  onClose,
  onFinished,
}: {
  corpusId: string;
  onClose: () => void;
  onFinished: () => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<FileProgress[]>([]);
  const [results, setResults] = useState<UploadFileResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (fileList: FileList | File[]) => {
      const files = Array.from(fileList);
      const { accepted, rejected } = partitionFiles(files);
      const localResults = rejected.map(toUploadResult);
      setError(null);
      setResults(null);
      setProgress(accepted.map((file) => ({ name: file.name, percent: 0, status: "pending" })));

      if (accepted.length === 0) {
        setResults(localResults);
        return;
      }

      setBusy(true);
      const remote: UploadFileResult[] = [];
      try {
        for (const file of accepted) {
          setProgress((current) =>
            current.map((item) =>
              item.name === file.name ? { ...item, status: "uploading", percent: 0 } : item,
            ),
          );
          const response = await documentsApi.upload(corpusId, [file], (percent) => {
            setProgress((current) =>
              current.map((item) => (item.name === file.name ? { ...item, percent } : item)),
            );
          });
          remote.push(...(response.results ?? []));
          setProgress((current) =>
            current.map((item) =>
              item.name === file.name ? { ...item, status: "done", percent: 100 } : item,
            ),
          );
        }
        setResults([...remote, ...localResults]);
        onFinished();
      } catch (cause) {
        setError(errorToastText(cause));
        setResults([...remote, ...localResults]);
      } finally {
        setBusy(false);
      }
    },
    [corpusId, onFinished],
  );

  return (
    <Dialog title="Upload documents" onClose={onClose} wide>
      {results ? (
        <>
          <UploadSummary results={results} corpusId={corpusId} />
          <div className="mt-5 flex justify-end">
            <Button onClick={onClose}>Done</Button>
          </div>
        </>
      ) : (
        <>
          <label
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center ${
              dragging ? "border-rust bg-rust/5" : "border-line bg-paper"
            }`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              void run(event.dataTransfer.files);
            }}
          >
            <input
              type="file"
              multiple
              accept=".pdf,application/pdf"
              className="hidden"
              onChange={(event) => {
                if (event.target.files) {
                  void run(event.target.files);
                }
              }}
            />
            <p className="font-medium">Drop PDFs here, or click to browse</p>
            <p className="mt-1 text-xs text-ink-muted">
              PDF only, up to 200 MB each. Other types are skipped and do not block the rest.
            </p>
          </label>
          {progress.length > 0 ? (
            <ul className="mt-4 space-y-2">
              {progress.map((item) => (
                <li key={item.name}>
                  <ProgressBar
                    value={item.percent}
                    max={100}
                    label={`${item.name} · ${item.status}`}
                  />
                </li>
              ))}
            </ul>
          ) : null}
          {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
          {busy ? <p className="mt-3 text-xs text-ink-muted">Uploading… unsupported files were already set aside.</p> : null}
        </>
      )}
    </Dialog>
  );
}
