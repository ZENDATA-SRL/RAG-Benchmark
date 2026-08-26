import { Shell } from "@/components/layout/Shell";
import { Card } from "@/components/ui/Card";
import { Divider } from "@/components/ui/Divider";
import { api, ApiError } from "@/lib/api";
import { ConfigsClient } from "./ConfigsClient";

export const dynamic = "force-dynamic";

export default async function ConfigsPage() {
  let configs: Awaited<ReturnType<typeof api.configs.rag.list>> = [];
  let backendError: { status?: number; message: string } | null = null;
  try {
    configs = await api.configs.rag.list();
  } catch (e) {
    if (e instanceof ApiError) {
      backendError = { status: e.status, message: e.message };
    } else {
      backendError = { message: "Failed to contact backend." };
    }
  }

  return (
    <Shell contentWidth="wide">
      <div className="space-y-6">
        <header className="space-y-2">
          <h1 className="font-serif text-3xl tracking-tight text-ink leading-snug">Configs</h1>
          <p className="font-serif text-xl text-slate leading-[1.7] max-w-prose">
            Saved RAGConfig objects persisted by the backend.
          </p>
        </header>

        <Divider />

        {backendError ? (
          <Card>
            <div className="space-y-2">
              <div className="font-sans text-sm font-medium text-charcoal">
                Backend error{backendError.status ? ` (${backendError.status})` : ""}
              </div>
              <div className="font-sans text-sm text-ash">
                The backend returned an error while loading configs. Make sure it’s running and
                reachable at{" "}
                <span className="font-mono text-xs text-ash">NEXT_PUBLIC_API_BASE_URL</span>.
              </div>
            </div>
          </Card>
        ) : configs.length === 0 ? (
          <Card>
            <div className="space-y-2">
              <div className="font-sans text-sm font-medium text-charcoal">No configs yet</div>
              <div className="font-sans text-sm text-ash">
                Create one in the Run screen and it will appear here.
              </div>
            </div>
          </Card>
        ) : (
          <ConfigsClient configs={configs} />
        )}
      </div>
    </Shell>
  );
}

