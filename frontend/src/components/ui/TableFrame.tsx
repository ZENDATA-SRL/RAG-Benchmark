import type { ReactNode } from "react";

// Bounded to the viewport so a long table scrolls inside its frame instead of stretching the
// page; the `table-frame` rule in index.css keeps the column names visible while scrolling.
export function TableFrame({ children }: { children: ReactNode }) {
  return (
    <div className="table-frame max-h-[calc(100vh-10rem)] overflow-auto rounded-xl border border-line bg-paper-raised">
      {children}
    </div>
  );
}
