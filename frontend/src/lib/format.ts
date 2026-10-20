export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function shortHash(hash: string, length = 10): string {
  return hash.length <= length ? hash : `${hash.slice(0, length)}…`;
}

export function chunkPage(metadata: Record<string, unknown> | undefined): number | null {
  const span = metadata?.page_span;
  if (Array.isArray(span) && typeof span[0] === "number" && span[0] > 0) {
    return span[0];
  }
  const page = metadata?.page;
  return typeof page === "number" && page > 0 ? page : null;
}

const LAST_CORPUS_KEY = "rag-bench.lastCorpusId";

export function rememberCorpus(id: string): void {
  sessionStorage.setItem(LAST_CORPUS_KEY, id);
}

export function lastCorpusId(): string | null {
  return sessionStorage.getItem(LAST_CORPUS_KEY);
}
