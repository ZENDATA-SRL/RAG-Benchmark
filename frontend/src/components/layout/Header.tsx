import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { queryKeys } from "@/lib/queryClient";

function ServiceDot({ ok, label }: { ok: boolean | null; label: string }) {
  const tone = ok === null ? "bg-line" : ok ? "bg-teal" : "bg-danger";
  const text = ok === null ? "checking" : ok ? "up" : "down";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-muted">
      <span className={`h-1.5 w-1.5 rounded-full ${tone}`} />
      {label} {text}
    </span>
  );
}

export function Header() {
  const health = useQuery({
    queryKey: queryKeys.health,
    queryFn: () => api.get<{ status: string }>("/health"),
    refetchInterval: 15_000,
    meta: { silent: true },
    retry: 0,
  });

  return (
    <header className="flex h-12 items-center justify-between border-b border-line bg-paper-raised px-6">
      <p className="text-sm text-ink-muted">Corpus → configuration → materialise → inspect</p>
      <ServiceDot ok={health.isSuccess ? health.data.status === "ok" : health.isError ? false : null} label="API" />
    </header>
  );
}
