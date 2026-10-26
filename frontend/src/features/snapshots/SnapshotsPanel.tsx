import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { snapshotsApi } from "@/api/resources";
import { TableFrame } from "@/components/ui/TableFrame";
import { formatDate, shortHash } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

export function SnapshotsPanel({ corpusId }: { corpusId: string }) {
  const snapshots = useQuery({
    queryKey: queryKeys.corpusSnapshots(corpusId),
    queryFn: () => snapshotsApi.list(corpusId),
    enabled: Boolean(corpusId),
  });

  const items = snapshots.data?.items ?? [];
  if (items.length === 0) {
    return null;
  }

  return (
    <section className="mt-6">
      <h2 className="mb-2 text-sm font-semibold">Snapshots</h2>
      <TableFrame>
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line bg-paper text-xs text-ink-muted">
            <tr>
              <th className="px-3 py-2 font-medium">Label</th>
              <th className="px-3 py-2 font-medium">Documents</th>
              <th className="px-3 py-2 font-medium">Composition</th>
              <th className="px-3 py-2 font-medium">Frozen</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {items.map((snapshot) => (
              <tr key={snapshot.id} className="border-b border-line last:border-0">
                <td className="px-3 py-2 font-medium">{snapshot.label}</td>
                <td className="px-3 py-2">{snapshot.document_count}</td>
                <td className="px-3 py-2 font-mono text-xs text-ink-muted">
                  {shortHash(snapshot.composition_hash)}
                </td>
                <td className="px-3 py-2 text-ink-muted">{formatDate(snapshot.frozen_at)}</td>
                <td className="px-3 py-2 text-right">
                  <Link
                    to={`/indexes?corpus=${corpusId}&snapshot=${snapshot.id}`}
                    className="text-sm font-medium text-rust hover:underline"
                  >
                    Build index
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableFrame>
    </section>
  );
}
