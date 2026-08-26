"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Shell } from "@/components/layout/Shell";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { api, ApiError } from "@/lib/api";
import { DATASET_NAME_RULES_LINES, isValidDatasetName } from "@/lib/dataset-name";

function DatasetNameRulesTooltip() {
  const id = "dataset-name-rules-tooltip";
  return (
    <span className="relative inline-flex group">
      <span
        tabIndex={0}
        className="cursor-help select-none font-sans text-sm text-ash outline-none hover:text-slate focus-visible:ring-2 focus-visible:ring-coral focus-visible:ring-offset-2 rounded-sm"
        aria-describedby={id}
        role="button"
        aria-label="Dataset name rules"
      >
        ⓘ
      </span>
      <span
        id={id}
        role="tooltip"
        className="pointer-events-none invisible absolute bottom-full left-1/2 z-10 mb-2 w-[min(20rem,calc(100vw-2rem))] -translate-x-1/2 rounded-md border border-linen bg-eggshell px-3 py-2 font-sans text-xs leading-relaxed text-charcoal shadow-md opacity-0 transition-opacity duration-150 group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
      >
        <span className="block font-medium text-slate mb-1">Name must:</span>
        <ul className="list-disc space-y-1 pl-4 text-ash">
          {DATASET_NAME_RULES_LINES.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </span>
    </span>
  );
}

export default function NewDatasetPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [status, setStatus] = useState<"idle" | "creating" | "error">("idle");
  const [error, setError] = useState<string>("");
  const trimmed = name.trim();
  const nameInvalid = trimmed.length > 0 && !isValidDatasetName(trimmed);

  return (
    <Shell>
      <div className="space-y-6">
        <header className="space-y-2">
          <h1 className="font-serif text-3xl tracking-tight text-ink leading-snug">
            Create dataset
          </h1>
          <p className="font-serif text-xl text-slate leading-[1.7]">
            Give the dataset a name. You’ll upload documents and questions in the next step.
          </p>
        </header>

        <Card>
          <div className="space-y-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2 font-sans text-sm font-medium text-charcoal">
                <span>Name</span>
                <DatasetNameRulesTooltip />
              </div>
              <Input
                value={name}
                invalid={nameInvalid}
                placeholder="e.g. finance-policies-v1"
                onChange={(e) => setName(e.target.value)}
              />
              {nameInvalid ? (
                <p className="font-sans text-sm text-red-700">
                  Use 3–63 characters: lowercase letters, digits, hyphens; start and end with a
                  letter or number.
                </p>
              ) : null}
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <Button
                disabled={
                  status === "creating" || trimmed.length === 0 || !isValidDatasetName(trimmed)
                }
                onClick={async () => {
                  setStatus("creating");
                  setError("");
                  try {
                    const created = await api.datasets.create({ name: name.trim() });
                    router.push(`/datasets/${created.id}`);
                  } catch (e) {
                    setStatus("error");
                    if (e instanceof ApiError) {
                      setError(typeof e.payload === "string" ? e.payload : e.message);
                      return;
                    }
                    setError(e instanceof Error ? e.message : "Failed to create dataset.");
                  } finally {
                    setStatus("idle");
                  }
                }}
              >
                {status === "creating" ? "Creating…" : "Create"}
              </Button>
              <Button variant="secondary" onClick={() => router.push("/datasets")}>
                Cancel
              </Button>
            </div>

            {error ? <div className="font-sans text-sm text-red-700">{error}</div> : null}
          </div>
        </Card>
      </div>
    </Shell>
  );
}

