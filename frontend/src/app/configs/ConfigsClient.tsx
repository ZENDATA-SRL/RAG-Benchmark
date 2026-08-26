"use client";

import { useMemo, useState } from "react";
import type { RAGConfig } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { RagConfigSummary } from "@/components/config/RagConfigSummary";
import { Divider } from "@/components/ui/Divider";

function configLabel(c: RAGConfig) {
  const name = (c.name ?? "").trim();
  return name.length > 0 ? name : c.id;
}

export function ConfigsClient({ configs }: { configs: RAGConfig[] }) {
  const sorted = useMemo(() => {
    // Prefer stable ordering: created_at desc when available, else by name/id.
    return [...configs].sort((a, b) => {
      const at = a.created_at ? Date.parse(a.created_at) : NaN;
      const bt = b.created_at ? Date.parse(b.created_at) : NaN;
      if (Number.isFinite(at) && Number.isFinite(bt) && at !== bt) return bt - at;
      return configLabel(a).localeCompare(configLabel(b));
    });
  }, [configs]);

  const [selectedId, setSelectedId] = useState<string>(() => sorted[0]?.id ?? "");

  const selected = useMemo(() => sorted.find((c) => c.id === selectedId) ?? null, [sorted, selectedId]);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_1fr]">
      <Card className="p-0 overflow-hidden">
        <div className="px-4 py-4 border-b border-linen bg-eggshell">
          <div className="font-sans text-sm font-medium text-charcoal">Saved configurations</div>
          <div className="mt-1 font-sans text-xs text-ash">{sorted.length} total</div>
        </div>

        <div className="max-h-[70vh] overflow-auto p-2">
          <div className="space-y-1">
            {sorted.map((c) => {
              const active = c.id === selectedId;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setSelectedId(c.id)}
                  className={[
                    "w-full text-left px-3 py-2 rounded-md border transition-colors duration-100",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-coral focus-visible:ring-offset-2",
                    active
                      ? "bg-linen border-dune text-charcoal"
                      : "bg-eggshell border-linen text-ash hover:bg-linen hover:text-charcoal hover:border-dune",
                  ].join(" ")}
                >
                  <div className="font-sans text-sm font-medium truncate">{configLabel(c)}</div>
                  <div className="mt-1 font-mono text-[11px] text-ash truncate">{c.id}</div>
                </button>
              );
            })}
          </div>
        </div>
      </Card>

      <Card className="p-0">
        {selected ? (
          <div className="p-6 space-y-5">
            <div className="space-y-1">
              <div className="font-sans text-xs text-ash">Configuration</div>
              <div className="font-serif text-2xl tracking-tight text-ink">{configLabel(selected)}</div>
              <div className="font-mono text-xs text-ash break-all">{selected.id}</div>
            </div>

            <Divider />

            <RagConfigSummary config={selected} />
          </div>
        ) : (
          <div className="p-6">
            <div className="font-sans text-sm text-ash">Select a configuration to preview.</div>
          </div>
        )}
      </Card>
    </div>
  );
}

