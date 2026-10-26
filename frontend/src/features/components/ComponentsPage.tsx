import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import { componentsApi } from "@/api/resources";
import type { ComponentVersionRead, ComponentWithVersionsRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { queryKeys } from "@/lib/queryClient";

/** Line icons in the same 24px stroke style, one per pipeline stage. */
function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className="size-5 shrink-0"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

const fallbackIcon = (
  <Icon>
    <rect x="4" y="4" width="16" height="16" rx="2" />
    <path d="M9 9h6v6H9z" />
  </Icon>
);

/**
 * What each component type does in the benchmark pipeline, in pipeline order, so the
 * page reads as the path a document takes from ingestion to the judged answer.
 */
const typeInfo: Record<string, { label: string; description: string; icon: ReactNode }> = {
  source: {
    label: "Sources",
    description: "Where documents come from before they enter a corpus.",
    icon: (
      <Icon>
        <path d="M4 7c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z" />
        <path d="M4 7v10c0 1.7 3.6 3 8 3s8-1.3 8-3V7" />
        <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
      </Icon>
    ),
  },
  parser: {
    label: "Parsers",
    description: "Turn a PDF into text and layout elements with their page positions.",
    icon: (
      <Icon>
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
        <path d="M14 3v5h5" />
        <path d="M9 13h6M9 17h4" />
      </Icon>
    ),
  },
  chunker: {
    label: "Chunkers",
    description: "Split the parsed text into the chunks that get embedded and retrieved.",
    icon: (
      <Icon>
        <rect x="4" y="4" width="16" height="5" rx="1" />
        <rect x="4" y="11" width="7" height="9" rx="1" />
        <rect x="13" y="11" width="7" height="9" rx="1" />
      </Icon>
    ),
  },
  embedder: {
    label: "Embedders",
    description: "Map each chunk and each query to a vector.",
    icon: (
      <Icon>
        <circle cx="6" cy="6" r="2" />
        <circle cx="18" cy="8" r="2" />
        <circle cx="9" cy="18" r="2" />
        <path d="M8 6.5l8 1M7 8l1.5 8M16.5 9.5L10.5 16.5" />
      </Icon>
    ),
  },
  vector_store: {
    label: "Vector stores",
    description: "Hold the vectors of an index and answer nearest-neighbour searches.",
    icon: (
      <Icon>
        <path d="M12 3l8 4.5-8 4.5-8-4.5z" />
        <path d="M4 12l8 4.5 8-4.5" />
        <path d="M4 16.5L12 21l8-4.5" />
      </Icon>
    ),
  },
  reranker: {
    label: "Rerankers",
    description: "Reorder the retrieved chunks by relevance to the query.",
    icon: (
      <Icon>
        <path d="M7 4v16M4 17l3 3 3-3" />
        <path d="M17 20V4M14 7l3-3 3 3" />
      </Icon>
    ),
  },
  answer_system: {
    label: "Answer systems",
    description: "Generate an answer from the question and the retrieved chunks.",
    icon: (
      <Icon>
        <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />
        <path d="M9 11h6M9 14h4" />
      </Icon>
    ),
  },
  judge: {
    label: "Judges",
    description: "Score the generated answers against the expected ones.",
    icon: (
      <Icon>
        <path d="M12 4v16M8 20h8" />
        <path d="M5 8h14" />
        <path d="M5 8l-2.5 6a2.5 2.5 0 0 0 5 0z" />
        <path d="M19 8l-2.5 6a2.5 2.5 0 0 0 5 0z" />
      </Icon>
    ),
  },
};

const typeOrder = Object.keys(typeInfo);

function groupByType(components: ComponentWithVersionsRead[]) {
  const groups = new Map<string, ComponentWithVersionsRead[]>();
  for (const component of components) {
    const list = groups.get(component.type) ?? [];
    list.push(component);
    groups.set(component.type, list);
  }
  // Known types follow the pipeline; any type the UI does not know yet goes last.
  const rank = (type: string) =>
    typeOrder.includes(type) ? typeOrder.indexOf(type) : typeOrder.length;
  return [...groups.entries()].sort(([a], [b]) => rank(a) - rank(b));
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={`size-4 shrink-0 text-ink-muted transition-transform ${open ? "rotate-90" : ""}`}
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}

type SchemaProperty = { type?: unknown; default?: unknown; description?: unknown; title?: unknown };

function formatValue(value: unknown) {
  if (value === undefined) return "—";
  return typeof value === "string" ? value : JSON.stringify(value);
}

function ParamsTable({ schema }: { schema: Record<string, unknown> }) {
  const properties = (schema.properties as Record<string, SchemaProperty> | undefined) ?? {};
  const entries = Object.entries(properties);
  if (entries.length === 0) {
    return <p className="text-xs text-ink-muted">No parameters.</p>;
  }
  return (
    <table className="w-full text-left text-xs">
      <thead className="text-ink-muted">
        <tr>
          <th className="py-1 pr-3 font-medium">Name</th>
          <th className="py-1 pr-3 font-medium">Type</th>
          <th className="py-1 font-medium">Default</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([name, property]) => (
          <tr key={name} className="border-t border-line align-top">
            <td className="py-1 pr-3">
              <span className="font-mono">{name}</span>
              {typeof property.description === "string" ? (
                <p className="mt-0.5 text-ink-muted">{property.description}</p>
              ) : null}
            </td>
            <td className="py-1 pr-3 font-mono text-ink-muted">{formatValue(property.type)}</td>
            <td className="py-1 font-mono break-all">{formatValue(property.default)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function VersionCard({ version }: { version: ComponentVersionRead }) {
  const [showParams, setShowParams] = useState(false);
  const paramCount = Object.keys(
    (version.params_schema.properties as Record<string, unknown> | undefined) ?? {},
  ).length;

  return (
    <div className="rounded-lg border border-line bg-paper px-3 py-3">
      <div className="flex items-center justify-between gap-2">
        <p className="font-mono text-sm">v{version.version}</p>
        {version.is_available ? (
          <Badge tone="good">available</Badge>
        ) : (
          <Badge tone="bad">unavailable</Badge>
        )}
      </div>
      <p className="mt-1 text-xs text-ink-muted">
        {version.runtime}
        {version.endpoint ? ` · ${version.endpoint}` : ""}
      </p>
      {!version.is_available && version.unavailable_reason ? (
        <p className="mt-2 text-xs text-danger">{version.unavailable_reason}</p>
      ) : null}
      <button
        type="button"
        onClick={() => setShowParams((open) => !open)}
        aria-expanded={showParams}
        className="mt-2 flex items-center gap-1 text-xs text-ink-muted hover:text-ink"
      >
        <Chevron open={showParams} />
        Parameters ({paramCount})
      </button>
      {showParams ? (
        <div className="mt-2">
          <ParamsTable schema={version.params_schema} />
        </div>
      ) : null}
    </div>
  );
}

function TypeSection({
  type,
  components,
  open,
  onToggle,
}: {
  type: string;
  components: ComponentWithVersionsRead[];
  open: boolean;
  onToggle: () => void;
}) {
  const info = typeInfo[type];
  const unavailable = components.filter((component) =>
    (component.versions ?? []).every((version) => !version.is_available),
  ).length;

  return (
    <section className="rounded-xl border border-line bg-paper-raised">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <Chevron open={open} />
        <span className="text-rust">{info?.icon ?? fallbackIcon}</span>
        <span className="min-w-0 flex-1">
          <span className="block font-semibold">{info?.label ?? type}</span>
          {info ? <span className="block text-xs text-ink-muted">{info.description}</span> : null}
        </span>
        {unavailable > 0 ? <Badge tone="bad">{`${unavailable} unavailable`}</Badge> : null}
        <Badge>{`${components.length} ${components.length === 1 ? "component" : "components"}`}</Badge>
      </button>
      {open ? (
        <ul className="grid gap-3 border-t border-line p-4 md:grid-cols-2">
          {components.map((component) => (
            <li key={component.id} className="rounded-lg border border-line bg-paper-raised p-3">
              <h3 className="font-semibold">{component.display_name}</h3>
              <p className="font-mono text-xs text-ink-muted">{component.key}</p>
              <div className="mt-3 grid gap-2">
                {(component.versions ?? []).map((version) => (
                  <VersionCard key={version.id} version={version} />
                ))}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export function ComponentsPage() {
  const query = useQuery({
    queryKey: queryKeys.components,
    queryFn: () => componentsApi.list(),
  });
  // Sections start collapsed so the page opens on an overview of the pipeline stages.
  const [openTypes, setOpenTypes] = useState<Set<string>>(new Set());

  const groups = groupByType(query.data ?? []);

  function toggle(type: string) {
    setOpenTypes((current) => {
      const next = new Set(current);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Components</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Read-only registry, grouped by pipeline stage. Parameter forms are generated from each
            version&apos;s JSON Schema.
          </p>
        </div>
        {groups.length > 0 ? (
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => setOpenTypes(new Set(groups.map(([type]) => type)))}
            >
              Expand all
            </Button>
            <Button variant="secondary" onClick={() => setOpenTypes(new Set())}>
              Collapse all
            </Button>
          </div>
        ) : null}
      </div>
      {query.isLoading ? <TableSkeleton /> : null}
      {query.isSuccess && groups.length === 0 ? (
        <EmptyState
          title="Registry is empty"
          body="The API seeds builtin parser and chunker on startup. If you see this, the API is running without seed."
        />
      ) : null}
      <div className="space-y-3">
        {groups.map(([type, components]) => (
          <TypeSection
            key={type}
            type={type}
            components={components}
            open={openTypes.has(type)}
            onToggle={() => toggle(type)}
          />
        ))}
      </div>
    </div>
  );
}
