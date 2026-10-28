import { useEffect, useRef } from "react";

import type { CandidateRead, RelevanceGrade } from "@/api/types";
import { Badge } from "@/components/ui/Badge";

import { RelevanceToggle } from "../qa-sets/RelevanceToggle";
import { compactText, formatScore } from "./queue";

const BAND_TONES = { high: "good", medium: "info", low: "neutral" } as const;

/** The ranked candidates of a question: read, grade and move on without opening documents. */
export function CandidateList({
  candidates,
  grades,
  selectedIndex,
  onSelect,
  onMark,
  onOpen,
}: {
  candidates: CandidateRead[];
  grades: Map<string, RelevanceGrade>;
  selectedIndex: number;
  onSelect: (index: number) => void;
  onMark: (candidate: CandidateRead, relevance: RelevanceGrade | null) => void;
  onOpen: (candidate: CandidateRead) => void;
}) {
  const selected = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    selected.current?.scrollIntoView?.({ block: "nearest" });
  }, [selectedIndex]);

  if (candidates.length === 0) {
    return (
      <p className="p-4 text-sm text-ink-muted">
        No candidate: the gold documents have no chunk under this configuration. Search the chunks,
        or record that the evidence is not found.
      </p>
    );
  }
  return (
    <ul className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3" data-testid="candidates">
      {candidates.map((candidate, index) => {
        const active = index === selectedIndex;
        return (
          <li
            key={candidate.chunk_id}
            ref={active ? selected : undefined}
            onClick={() => onSelect(index)}
            className={`cursor-pointer rounded-lg border p-3 text-sm ${
              active ? "border-rust bg-rust/5" : "border-line bg-paper-raised"
            }`}
            data-testid="candidate"
            aria-selected={active}
          >
            <div className="mb-1 flex flex-wrap items-center gap-2 text-xs">
              <span className="font-mono text-ink-muted">#{candidate.rank}</span>
              <Badge tone={BAND_TONES[candidate.confidence]}>{candidate.confidence}</Badge>
              {candidate.preselected ? <Badge tone="good">pre-selected</Badge> : null}
              <span
                className="font-mono text-ink-muted"
                title="combined · semantic · lexical · positional"
              >
                {formatScore(candidate.combined_score)} · sem{" "}
                {formatScore(candidate.semantic_score)} · lex {formatScore(candidate.lexical_score)}{" "}
                · pos {formatScore(candidate.positional_score)}
              </span>
              <span className="ml-auto">
                <RelevanceToggle
                  ordinal={candidate.ordinal}
                  value={grades.get(candidate.chunk_id) ?? null}
                  onChange={(relevance) => onMark(candidate, relevance)}
                />
              </span>
            </div>
            <button
              type="button"
              className="mb-1 font-mono text-xs text-rust hover:underline"
              onClick={(event) => {
                event.stopPropagation();
                onOpen(candidate);
              }}
            >
              {candidate.filename} #{candidate.ordinal}
              {candidate.page ? ` · p. ${candidate.page}` : ""}
            </button>
            <p className={`leading-6 ${active ? "" : "line-clamp-4 text-ink-muted"}`}>
              {compactText(candidate.text)}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
