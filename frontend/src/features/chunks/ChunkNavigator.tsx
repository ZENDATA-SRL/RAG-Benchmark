import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useRef } from "react";

import {
  coversPage,
  formatPageSpan,
  pageSpanOf,
  type ChunkNavigatorProps,
  type NavigableChunk,
} from "./types";

export function ChunkNavigator({
  chunks,
  selectedId,
  onSelect,
  renderChunkActions,
  showNormalized = false,
}: ChunkNavigatorProps) {
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: chunks.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 220,
    overscan: 6,
    measureElement: (element) => element.getBoundingClientRect().height,
  });

  useEffect(() => {
    const index = chunks.findIndex((chunk) => chunk.id === selectedId);
    if (index >= 0) {
      virtualizer.scrollToIndex(index, { align: "auto" });
    }
  }, [chunks, selectedId, virtualizer]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
        return;
      }
      if (!chunks.length) {
        return;
      }
      event.preventDefault();
      const current = Math.max(
        0,
        chunks.findIndex((chunk) => chunk.id === selectedId),
      );
      const next =
        event.key === "ArrowDown"
          ? Math.min(chunks.length - 1, current + 1)
          : Math.max(0, current - 1);
      onSelect(chunks[next].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [chunks, onSelect, selectedId]);

  if (chunks.length === 0) {
    return <p className="p-4 text-sm text-ink-muted">No chunks for this configuration yet.</p>;
  }

  return (
    <div
      ref={parentRef}
      className="h-full overflow-y-auto"
      data-testid="chunk-navigator"
      tabIndex={0}
    >
      <div className="relative w-full" style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map((item) => {
          const chunk = chunks[item.index];
          return (
            <div
              key={chunk.id}
              data-index={item.index}
              ref={virtualizer.measureElement}
              className="absolute top-0 left-0 w-full px-2 pb-2"
              style={{ transform: `translateY(${item.start}px)` }}
            >
              <ChunkRow
                chunk={chunk}
                selected={chunk.id === selectedId}
                showNormalized={showNormalized}
                onSelect={onSelect}
                actions={renderChunkActions?.(chunk)}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function scrollToPage(chunks: NavigableChunk[], page: number): string | null {
  const match = chunks.find((chunk) => coversPage(chunk, page));
  return match?.id ?? null;
}

function ChunkRow({
  chunk,
  selected,
  showNormalized,
  onSelect,
  actions,
}: {
  chunk: NavigableChunk;
  selected: boolean;
  showNormalized: boolean;
  onSelect: (id: string) => void;
  actions?: React.ReactNode;
}) {
  const span = pageSpanOf(chunk);
  const text = showNormalized && chunk.text_normalized ? chunk.text_normalized : chunk.text;
  // A container and not a button: the actions (annotation marks) are buttons themselves,
  // and a button cannot hold another. Clicking anywhere on the row still selects it.
  return (
    <div
      data-chunk-id={chunk.id}
      onClick={() => onSelect(chunk.id)}
      className={`w-full cursor-pointer rounded-lg border px-3 py-2 text-left ${
        selected ? "border-rust bg-rust/5" : "border-line bg-paper-raised"
      }`}
    >
      <div className="mb-1 flex items-center justify-between gap-2 text-[11px] text-ink-muted">
        <span>
          #{chunk.ordinal}
          {span ? ` · ${formatPageSpan(span)}` : ""}
        </span>
        {actions}
      </div>
      <button
        type="button"
        aria-pressed={selected}
        className="block w-full text-left text-sm whitespace-pre-wrap"
      >
        {text}
      </button>
    </div>
  );
}
