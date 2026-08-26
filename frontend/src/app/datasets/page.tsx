import Link from "next/link";
import { Shell } from "@/components/layout/Shell";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Divider } from "@/components/ui/Divider";
import { api, ApiError } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DatasetsPage() {
  let datasets: Awaited<ReturnType<typeof api.datasets.list>> = [];
  let backendError: { status?: number; message: string } | null = null;
  try {
    datasets = await api.datasets.list();
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
            <h1 className="font-serif text-3xl tracking-tight text-ink leading-snug">Datasets</h1>
            <p className="font-serif text-xl text-slate leading-[1.7]">
              Create a dataset, upload documents, then upload questions.
            </p>
          </div>
          <div className="sm:pb-1">
            <Link href="/datasets/new">
              <Button>Create dataset</Button>
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
                The backend returned an error while loading datasets. Make sure it’s running and
                reachable at{" "}
                <span className="font-mono text-xs text-ash">NEXT_PUBLIC_API_BASE_URL</span>.
              </div>
            </div>
          </Card>
        ) : datasets.length === 0 ? (
          <Card>
            <div className="space-y-2">
              <div className="font-sans text-sm font-medium text-charcoal">No datasets yet</div>
              <div className="font-sans text-sm text-ash">
                Create one to begin uploading documents and questions.
              </div>
            </div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {datasets.map((d) => (
              <Card key={d.id} className="p-0">
                <div className="p-6 flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="font-sans text-sm text-ash">Dataset</div>
                    <div className="mt-1 font-serif text-2xl tracking-tight text-ink truncate">
                      {d.name}
                    </div>
                    <div className="mt-2 font-mono text-xs text-ash break-all">{d.id}</div>
                  </div>
                  <Link href={`/datasets/${d.id}`}>
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

