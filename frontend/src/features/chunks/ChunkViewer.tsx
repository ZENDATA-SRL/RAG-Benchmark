import { useState } from "react";

import type { ChunkRead } from "@/api/types";

import { ChunkNavigator, scrollToPage } from "./ChunkNavigator";
import { ParseViewer } from "./ParseViewer";
import { PdfPane } from "./PdfPane";
import { coversPage, pageSpanOf, type NavigableChunk } from "./types";

type Tab = "chunks" | "parse";

export function toNavigable(chunk: ChunkRead): NavigableChunk {
  return {
    id: chunk.id,
    ordinal: chunk.ordinal,
    text: chunk.text,
    text_normalized: chunk.text_normalized,
    metadata: chunk.metadata ?? {},
  };
}

export function ChunkViewer({
  documentId,
  chunks,
  selectedId,
  onSelect,
  parsingProfileId,
  compare,
}: {
  documentId: string;
  chunks: NavigableChunk[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  parsingProfileId?: string;
  compare?: React.ReactNode;
}) {
  const [tab, setTab] = useState<Tab>("chunks");
  const [normalized, setNormalized] = useState(false);
  const [followSelection, setFollowSelection] = useState(true);
  const [viewerPage, setViewerPage] = useState(1);
  const selected = chunks.find((chunk) => chunk.id === selectedId);
  const span = selected ? pageSpanOf(selected) : pageSpanOf(chunks[0] ?? { id: "", ordinal: 0, text: "", metadata: {} });
  const page = followSelection ? (span?.first ?? 1) : viewerPage;

  const selectChunk = (id: string) => {
    setFollowSelection(true);
    onSelect(id);
  };

  return (
    <div className="grid min-h-[calc(100vh-8rem)] grid-cols-1 gap-0 overflow-hidden rounded-xl border border-line bg-paper-raised lg:grid-cols-2">
      <PdfPane
        documentId={documentId}
        page={page}
        onPageChange={(next) => {
          setFollowSelection(false);
          setViewerPage(next);
          if (selected && coversPage(selected, next)) {
            return;
          }
          const id = scrollToPage(chunks, next);
          if (id) onSelect(id);
        }}
      />
      <div className="flex min-h-[28rem] flex-col border-l border-line">
        <div className="flex items-center justify-between border-b border-line px-3 py-2">
          <div className="flex gap-2 text-sm">
            <TabButton active={tab === "chunks"} onClick={() => setTab("chunks")}>
              Chunks
            </TabButton>
            <TabButton active={tab === "parse"} onClick={() => setTab("parse")}>
              Parse
            </TabButton>
          </div>
          {tab === "chunks" ? (
            <label className="flex items-center gap-2 text-xs text-ink-muted">
              <input
                type="checkbox"
                checked={normalized}
                onChange={(event) => setNormalized(event.target.checked)}
              />
              text_normalized
            </label>
          ) : null}
        </div>
        <div className="min-h-0 flex-1">
          {tab === "chunks" ? (
            <ChunkNavigator
              chunks={chunks}
              selectedId={selectedId}
              onSelect={selectChunk}
              showNormalized={normalized}
            />
          ) : (
            <ParseViewer
              documentId={documentId}
              parsingProfileId={parsingProfileId ?? ""}
              page={page}
            />
          )}
        </div>
        {compare}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-2 py-1 ${active ? "bg-ink/8 font-medium" : "text-ink-muted"}`}
    >
      {children}
    </button>
  );
}
