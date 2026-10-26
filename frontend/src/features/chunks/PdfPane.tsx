import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { fetchDocumentBytes } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { errorToastText } from "@/lib/errors";
import { queryKeys } from "@/lib/queryClient";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// Same build as react-pdf's API (5.4.296), served from /public so Vite's
// prebundle cannot pick up a leftover worker from another pdfjs-dist version.
pdfjs.GlobalWorkerOptions.workerSrc = `${import.meta.env.BASE_URL}pdf.worker.min.mjs`;

export function PdfPane({
  documentId,
  page,
  onPageChange,
}: {
  documentId: string;
  page: number;
  onPageChange: (page: number) => void;
}) {
  const [pageCount, setPageCount] = useState(1);
  const current = Math.min(Math.max(page, 1), pageCount);
  const pdf = useQuery({
    queryKey: queryKeys.documentContent(documentId),
    queryFn: () => fetchDocumentBytes(documentId),
    staleTime: Infinity,
    meta: { silent: true },
  });
  const file = useMemo(
    () => (pdf.data ? new Blob([pdf.data], { type: "application/pdf" }) : null),
    [pdf.data],
  );

  return (
    <div className="flex h-full min-h-0 flex-col bg-ink/5">
      <div className="flex items-center justify-between border-b border-line px-3 py-2 text-xs">
        <Button variant="ghost" disabled={current <= 1} onClick={() => onPageChange(current - 1)}>
          Previous
        </Button>
        <span>
          Page {current} / {pageCount}
        </span>
        <Button
          variant="ghost"
          disabled={current >= pageCount}
          onClick={() => onPageChange(current + 1)}
        >
          Next
        </Button>
      </div>
      <div className="flex min-h-0 flex-1 justify-center overflow-auto p-4">
        {pdf.isError ? (
          <p className="text-sm text-danger">{errorToastText(pdf.error)}</p>
        ) : file ? (
          <Document
            file={file}
            onLoadSuccess={({ numPages }) => setPageCount(numPages)}
            loading={<p className="text-sm text-ink-muted">Rendering PDF…</p>}
            error={<p className="text-sm text-danger">Could not render this PDF.</p>}
          >
            <Page
              pageNumber={current}
              width={560}
              renderAnnotationLayer={false}
              onClick={() => onPageChange(current)}
            />
          </Document>
        ) : (
          <p className="text-sm text-ink-muted">Loading PDF…</p>
        )}
      </div>
    </div>
  );
}
