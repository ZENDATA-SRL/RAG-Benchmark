import { useQuery } from "@tanstack/react-query";

import { componentsApi } from "@/api/resources";
import type { ComponentVersionRead, ComponentWithVersionsRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { queryKeys } from "@/lib/queryClient";

function groupByType(components: ComponentWithVersionsRead[]) {
  const groups = new Map<string, ComponentWithVersionsRead[]>();
  for (const component of components) {
    const list = groups.get(component.type) ?? [];
    list.push(component);
    groups.set(component.type, list);
  }
  return [...groups.entries()];
}

function VersionCard({ version }: { version: ComponentVersionRead }) {
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
      <p className="mt-2 text-xs text-ink-muted">
        Schema fields:{" "}
        {Object.keys((version.params_schema.properties as Record<string, unknown> | undefined) ?? {}).join(", ") ||
          "none"}
      </p>
    </div>
  );
}

export function ComponentsPage() {
  const query = useQuery({
    queryKey: queryKeys.components,
    queryFn: () => componentsApi.list(),
  });

  const groups = groupByType(query.data ?? []);

  return (
    <div>
      <h1 className="text-2xl font-semibold">Components</h1>
      <p className="mt-1 mb-6 text-sm text-ink-muted">
        Read-only registry. Parameter forms are generated from each version&apos;s JSON Schema.
      </p>
      {query.isLoading ? <TableSkeleton /> : null}
      {query.isSuccess && groups.length === 0 ? (
        <EmptyState
          title="Registry is empty"
          body="The API seeds builtin parser and chunker on startup. If you see this, the API is running without seed."
        />
      ) : null}
      <div className="space-y-8">
        {groups.map(([type, components]) => (
          <section key={type}>
            <h2 className="mb-3 font-mono text-xs tracking-widest text-ink-muted uppercase">{type}</h2>
            <ul className="grid gap-3 md:grid-cols-2">
              {components.map((component) => (
                <li key={component.id} className="rounded-xl border border-line bg-paper-raised p-4">
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
          </section>
        ))}
      </div>
    </div>
  );
}
