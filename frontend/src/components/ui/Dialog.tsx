import { useEffect, type ReactNode } from "react";

import { Button } from "./Button";

export function Dialog({
  title,
  children,
  onClose,
  wide,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-ink/40 p-4 pt-16">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        className={`w-full rounded-xl border border-line bg-paper-raised shadow-xl ${wide ? "max-w-3xl" : "max-w-lg"}`}
      >
        <header className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 id="dialog-title" className="text-base font-semibold">
            {title}
          </h2>
          <Button variant="ghost" onClick={onClose} aria-label="Close">
            ×
          </Button>
        </header>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  onConfirm,
  onClose,
  pending,
}: {
  title: string;
  body: string;
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  pending?: boolean;
}) {
  return (
    <Dialog title={title} onClose={onClose}>
      <p className="text-sm leading-6 text-ink-muted">{body}</p>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose} disabled={pending}>
          Cancel
        </Button>
        <Button variant="danger" onClick={onConfirm} disabled={pending}>
          {confirmLabel}
        </Button>
      </div>
    </Dialog>
  );
}
