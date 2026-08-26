import Link from "next/link";
import { Shell } from "@/components/layout/Shell";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Divider } from "@/components/ui/Divider";
import { api, ApiError } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ExperimentsPage() {
  let experiments: Awaited<ReturnType<typeof api.experiments.list>> = [];
  let backendError: { status?: number; message: string } | null = null;
  try {
    experiments = await api.experiments.list();
  } catch (e) {
    if (e instanceof ApiError) {
      backendError = { status: e.status, message: e.message };
    } else {
      backendError = { message: "Failed to contact backend." };
    }
  }

  return (
    <Shell>
      <div className="space-y-6">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-2">
            <h1 className="font-serif text-3xl tracking-tight text-ink leading-snug">
              Experiments
            </h1>
            <p className="font-serif text-xl text-slate leading-[1.7]">
              Runs created by the backend for a dataset and configuration.
            </p>
          </div>
          <div className="sm:pb-1">
            <Link href="/run">
              <Button>Run an experiment</Button>
            </Link>
          </div>
        </header>

        <Divider />

        {backendError ? (
          <Card>
            <div className="space-y-2">
              <div className="font-sans text-sm font-medium text-charcoal">
                Backend error{backendError.status ? ` (${backendError.status})` : ""}
              </div>
              <div className="font-sans text-sm text-ash">
                The backend returned an error while loading experiments. Make sure it’s running
                and reachable at{" "}
                <span className="font-mono text-xs text-ash">NEXT_PUBLIC_API_BASE_URL</span>.
              </div>
            </div>
          </Card>
        ) : experiments.length === 0 ? (
          <Card>
            <div className="space-y-2">
              <div className="font-sans text-sm font-medium text-charcoal">
                No experiments yet
              </div>
              <div className="font-sans text-sm text-ash">
                Run one from the Run page and it will appear here.
              </div>
            </div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {experiments.map((e) => (
              <Card key={e.id} className="p-0">
                <div className="p-6 flex items-start justify-between gap-4">
                  <div className="min-w-0 space-y-3">
                    <div className="space-y-1">
                      <div className="font-sans text-sm text-ash">Experiment</div>
                      <div className="font-serif text-2xl tracking-tight text-ink truncate">
                        {e.name}
                      </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <div className="font-sans text-xs text-ash">Experiment ID</div>
                        <div className="font-mono text-xs text-ash break-all">{e.id}</div>
                      </div>
                      <div className="space-y-1">
                        <div className="font-sans text-xs text-ash">Dataset ID</div>
                        <div className="font-mono text-xs text-ash break-all">
                          {e.dataset_id}
                        </div>
                      </div>
                    </div>
                    <div className="font-sans text-sm text-ash">
                      Created:{" "}
                      <span className="font-mono text-xs text-ash">{e.created_at}</span>
                    </div>
                  </div>
                  <Link href={`/experiments/${e.id}`}>
                    <Button variant="secondary">Open</Button>
                  </Link>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </Shell>
  );
}

