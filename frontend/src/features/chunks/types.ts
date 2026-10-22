import type { ReactNode } from "react";

/** Minimal chunk shape shared by inspection, annotation, and transfer. */
export type NavigableChunk = {
  id: string;
  ordinal: number;
  text: string;
  text_normalized?: string | null;
  metadata: Record<string, unknown>;
};

export type PageSpan = {
  first: number;
  last: number;
};

export type ChunkNavigatorProps = {
  chunks: NavigableChunk[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  renderChunkActions?: (chunk: NavigableChunk) => ReactNode;
  showNormalized?: boolean;
};

function asPage(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : null;
}

/** Inclusive page range. Prefers `page_span`, falls back to `page`. */
export function pageSpanOf(chunk: NavigableChunk): PageSpan | null {
  const raw = chunk.metadata.page_span;
  if (Array.isArray(raw) && raw.length >= 2) {
    const first = asPage(raw[0]);
    const last = asPage(raw[1]);
    if (first !== null && last !== null) {
      return first <= last ? { first, last } : { first: last, last: first };
    }
  }
  const page = asPage(chunk.metadata.page);
  return page === null ? null : { first: page, last: page };
}

export function pageOf(chunk: NavigableChunk): number | null {
  return pageSpanOf(chunk)?.first ?? null;
}

export function coversPage(chunk: NavigableChunk, page: number): boolean {
  const span = pageSpanOf(chunk);
  return span !== null && page >= span.first && page <= span.last;
}

export function formatPageSpan(span: PageSpan): string {
  return span.first === span.last ? `page ${span.first}` : `pages ${span.first}–${span.last}`;
}
