import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { configurationsApi, materializationsApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { queryKeys } from "@/lib/queryClient";
import { toast } from "@/lib/toast";

export function MaterializeDialog({
  corpusId,
  selectedIds,
  onClose,
  onStarted,
}: {
  corpusId: string;
  selectedIds: string[];
  onClose: () => void;
  onStarted: (runId: string) => void;
}) {
  const [configurationId, setConfigurationId] = useState("");
  const [scope, setScope] = useState<"corpus" | "selected">("corpus");

  const configurations = useQuery({
    queryKey: queryKeys.configurations,
    queryFn: configurationsApi.list,
  });

  const items = configurations.data?.items ?? [];
  const chosen = configurationId || items[0]?.id || "";

  const start = useMutation({
    mutationFn: () =>
      materializationsApi.start({
        chunking_configuration_id: chosen,
        ...(scope === "selected" && selectedIds.length > 0
          ? { document_ids: selectedIds }
          : { corpus_id: corpusId }),
      }),
    onSuccess: (result) => {
      if (!result.started) {
        toast.info(result.detail ?? "The same run is already in progress.");
      }
      onStarted(result.id);
    },
  });

  return (
    <Dialog title="Materialise chunks" onClose={onClose}>
      {items.length === 0 ? (
        <p className="text-sm text-ink-muted">
          Compose a configuration first. The form is generated from the registry — no fields are hard-coded.
        </p>
      ) : (
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            start.mutate();
          }}
        >
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Configuration</span>
            <select
              value={chosen}
              onChange={(event) => setConfigurationId(event.target.value)}
              className="w-full rounded-md border border-line bg-paper px-3 py-1.5"
            >
              {items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {item.parsing_profile.name} + {item.chunking_profile.name}
                </option>
              ))}
            </select>
          </label>
          <fieldset className="space-y-2 text-sm">
            <legend className="mb-1 font-medium">Scope</legend>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="scope"
                checked={scope === "corpus"}
                onChange={() => setScope("corpus")}
              />
              Entire corpus
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
            A second click on the same work reports the same run. That is not an error.
          </p>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!chosen || start.isPending}>
              Start
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
