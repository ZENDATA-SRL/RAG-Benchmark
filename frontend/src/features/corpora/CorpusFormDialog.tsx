import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";

export function CorpusFormDialog({
  title,
  initialName = "",
  initialDescription = "",
  submitLabel,
  pending,
  onSubmit,
  onClose,
}: {
  title: string;
  initialName?: string;
  initialDescription?: string;
  submitLabel: string;
  pending?: boolean;
  onSubmit: (values: { name: string; description: string | null }) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);

  return (
    <Dialog title={title} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({ name: name.trim(), description: description.trim() || null });
        }}
      >
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Name</span>
          <input
            required
            maxLength={200}
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-full rounded-md border border-line bg-paper px-3 py-1.5"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Description</span>
          <textarea
            maxLength={2000}
            rows={3}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            className="w-full rounded-md border border-line bg-paper px-3 py-1.5"
          />
        </label>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={pending || !name.trim()}>
            {submitLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
