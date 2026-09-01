import { Link } from "react-router-dom";

import type { FileOutcome, UploadFileResult } from "@/api/types";
import { Badge } from "@/components/ui/Badge";

import { countOutcomes } from "./uploadValidation";

const LABELS: Record<FileOutcome, { title: string; tone: "good" | "info" | "warn" | "bad"; note: string }> = {
  imported: { title: "Imported", tone: "good", note: "New documents stored by content hash." },
  skipped_duplicate: {
    title: "Duplicates",
    tone: "info",
    note: "Already known. Not an error — the existing document was reused.",
  },
  skipped_unsupported: {
    title: "Unsupported",
    tone: "warn",
    note: "Skipped so the rest of the batch could continue.",
  },
  failed: { title: "Failed", tone: "bad", note: "Could not be stored." },
};

const ORDER: FileOutcome[] = ["imported", "skipped_duplicate", "skipped_unsupported", "failed"];

export function UploadSummary({
  results,
  corpusId,
}: {
  results: UploadFileResult[];
  corpusId?: string;
}) {
  const counts = countOutcomes(results);

  return (
    <div className="space-y-4" data-testid="upload-summary">
      <div className="flex flex-wrap gap-2">
        {ORDER.map((outcome) => (
          <Badge key={outcome} tone={LABELS[outcome].tone}>
            {`${counts[outcome]} ${LABELS[outcome].title.toLowerCase()}`}
          </Badge>
        ))}
      </div>
      {ORDER.map((outcome) => {
        const items = results.filter((result) => result.outcome === outcome);
        if (items.length === 0) {
          return null;
        }
        const meta = LABELS[outcome];
        return (
          <section key={outcome} data-testid={`upload-${outcome}`}>
            <h3 className="text-sm font-semibold">{meta.title}</h3>
            <p className="mb-2 text-xs text-ink-muted">{meta.note}</p>
            <ul className="space-y-1 text-sm">
              {items.map((item, index) => (
                <li key={`${item.filename}-${index}`} className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-medium">{item.filename}</span>
                  {item.outcome === "skipped_duplicate" && item.document_id ? (
                    <Link
                      className="text-rust underline-offset-2 hover:underline"
                      to={
                        corpusId
                          ? `/corpora/${corpusId}?document=${item.document_id}`
                          : `/documents/${item.document_id}`
                      }
                    >
                      open existing document
                    </Link>
                  ) : null}
                  {item.error_reason ? (
                    <span className="text-ink-muted">{item.error_reason}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
