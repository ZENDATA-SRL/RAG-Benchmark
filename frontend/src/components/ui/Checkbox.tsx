"use client";

import type { ReactNode } from "react";
import { Check } from "lucide-react";

export function Checkbox({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: ReactNode;
  description?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={[
        "w-full text-left rounded-lg border border-linen bg-eggshell px-4 py-3",
        "transition-colors duration-150",
        "hover:bg-linen",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-coral focus-visible:ring-offset-2",
      ].join(" ")}
    >
      <span className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className={[
            "mt-0.5 flex h-5 w-5 items-center justify-center rounded-md border",
            checked ? "border-coral bg-coral text-white" : "border-dune bg-eggshell text-transparent",
          ].join(" ")}
        >
          <Check className="h-4 w-4" />
        </span>
        <span className="min-w-0">
          <span className="block font-sans text-sm font-medium text-charcoal">{label}</span>
          {description ? (
            <span className="mt-0.5 block font-sans text-sm text-ash">{description}</span>
          ) : null}
        </span>
      </span>
    </button>
  );
}

