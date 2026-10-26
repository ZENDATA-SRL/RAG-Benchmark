import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { qaSetsApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { queryKeys } from "@/lib/queryClient";

import { ImportSummary } from "./ImportSummary";

export function ImportDialog({ qaSetId, onClose }: { qaSetId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);

  const upload = useMutation({
    mutationFn: (selected: File) => qaSetsApi.importFile(qaSetId, selected),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.qaSet(qaSetId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.qaSets });
    },
  });

  return (
    <Dialog title="Import questions" onClose={onClose} wide>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (file) upload.mutate(file);
        }}
      >
        <label className="block text-sm">
          <span className="mb-1 block font-medium">CSV or JSONL file</span>
          <input
            type="file"
            accept=".csv,.jsonl"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <p className="text-xs text-ink-muted">
          CSV columns: <span className="font-mono">question</span>,{" "}
          <span className="font-mono">answer</span> (optional, the expected answer),{" "}
          <span className="font-mono">gold_files</span> (several separated by{" "}
          <span className="font-mono">|</span>), <span className="font-mono">tags</span> (separated
          by <span className="font-mono">|</span>), <span className="font-mono">answerable</span>.
          Gold files are matched to the library by file name. The chunks that hold the answer are
          not part of the file: they are confirmed later, per chunking configuration. Importing the
          same file again does not duplicate questions.
        </p>
        {upload.data ? <ImportSummary summary={upload.data} /> : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            {upload.data ? "Close" : "Cancel"}
          </Button>
          <Button type="submit" disabled={!file || upload.isPending}>
            Import
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
