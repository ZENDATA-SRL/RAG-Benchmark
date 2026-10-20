import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { snapshotsApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { queryKeys } from "@/lib/queryClient";
import { toast } from "@/lib/toast";

export function SnapshotDialog({
  corpusId,
  selectedIds,
  onClose,
}: {
  corpusId: string;
  selectedIds: string[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState("");
  const [scope, setScope] = useState<"corpus" | "selected">(
    selectedIds.length > 0 ? "selected" : "corpus",
  );

  const freeze = useMutation({
    mutationFn: () =>
      snapshotsApi.create(corpusId, {
        label: label.trim(),
        document_ids: scope === "selected" ? selectedIds : null,
      }),
    onSuccess: async (result) => {
      if (result.created) {
        toast.success(
          `Snapshot "${result.snapshot.label}" frozen with ${result.snapshot.document_count} ${
            result.snapshot.document_count === 1 ? "document" : "documents"
          }.`,
        );
      } else {
        toast.info(result.detail ?? "A snapshot with the same documents already existed.");
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.corpusSnapshots(corpusId) });
      onClose();
    },
  });

  return (
    <Dialog title="Freeze snapshot" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          freeze.mutate();
        }}
      >
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Label</span>
          <input
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="e.g. v1 — March selection"
            maxLength={200}
            className="w-full rounded-md border border-line bg-paper px-3 py-1.5"
            autoFocus
          />
        </label>
        <fieldset className="space-y-2 text-sm">
          <legend className="mb-1 font-medium">Documents</legend>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="scope"
              checked={scope === "corpus"}
              onChange={() => setScope("corpus")}
            />
            Every stored document of the corpus
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="scope"
              checked={scope === "selected"}
              disabled={selectedIds.length === 0}
              onChange={() => setScope("selected")}
            />
            Selected documents ({selectedIds.length})
          </label>
        </fieldset>
        <p className="text-xs text-ink-muted">
          A snapshot is the search space of an index. It never changes, even if documents are later
          removed from the corpus. Freezing the same documents twice returns the existing snapshot.
        </p>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!label.trim() || freeze.isPending}>
            Freeze
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
