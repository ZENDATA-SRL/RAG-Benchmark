import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { configurationsApi, materializationsApi } from "@/api/resources";
import type { DocumentRead } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { queryKeys } from "@/lib/queryClient";
import { toast } from "@/lib/toast";

export function PreviewDialog({
  document,
  onClose,
  onStarted,
}: {
  corpusId: string;
  document: DocumentRead;
  onClose: () => void;
  onStarted: (runId: string) => void;
}) {
  const [configurationId, setConfigurationId] = useState("");
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
        document_ids: [document.id],
      }),
    onSuccess: (result) => {
      if (!result.started) {
        toast.info(result.detail ?? "The same preview is already running.");
      }
      onStarted(result.id);
    },
  });

  return (
    <Dialog title={`Preview on ${document.filename}`} onClose={onClose}>
      <p className="mb-4 text-sm text-ink-muted">
        Run parsing and chunking on this file only. Try a few documents before applying a configuration to the
        whole corpus.
      </p>
      <label className="block text-sm">
        <span className="mb-1 block font-medium">Configuration</span>
        <select
          value={chosen}
          onChange={(event) => setConfigurationId(event.target.value)}
          className="w-full rounded-md border border-line bg-paper px-3 py-1.5"
        >
          {items.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button disabled={!chosen || start.isPending} onClick={() => start.mutate()}>
          Preview
        </Button>
      </div>
    </Dialog>
  );
}
