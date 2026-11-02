import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { answerProfilesApi } from "@/api/resources";
import type { AnswerProfileRead } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { TableFrame } from "@/components/ui/TableFrame";
import { formatDate, shortHash } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

import { AnswerProfileDialog } from "./AnswerProfileDialog";
import { formatParamValue, promptExcerpt } from "./profiles";

/** One profile's parameters, and those that differ from the profile it was derived from. */
function ProfileDetailDialog({
  profile,
  onDerive,
  onClose,
}: {
  profile: AnswerProfileRead;
  onDerive: () => void;
  onClose: () => void;
}) {
  const detail = useQuery({
    queryKey: queryKeys.answerProfile(profile.id),
    queryFn: () => answerProfilesApi.get(profile.id),
  });
  const changes = detail.data?.changed_params ?? [];

  return (
    <Dialog title={profile.name} onClose={onClose} wide>
      <div className="space-y-4 text-sm">
        <dl className="grid grid-cols-[10rem_1fr] gap-y-2">
          {Object.entries(profile.params ?? {}).map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="text-ink-muted">{key}</dt>
              <dd className="font-mono text-xs break-words whitespace-pre-wrap">
                {formatParamValue(value)}
              </dd>
            </div>
          ))}
          <dt className="text-ink-muted">Hash</dt>
          <dd className="font-mono text-xs">{shortHash(profile.config_hash, 16)}</dd>
        </dl>
        {profile.parent_profile_id ? (
          <section data-testid="changed-params">
            <h3 className="mb-1 font-semibold">Changed from the parent</h3>
            {changes.length === 0 ? (
              <p className="text-ink-muted">{detail.isLoading ? "…" : "Nothing."}</p>
            ) : (
              <ul className="space-y-2">
                {changes.map((change) => (
                  <li key={change.key}>
                    <span className="font-medium">{change.key}</span>
                    <span className="block font-mono text-xs text-danger line-through">
                      {formatParamValue(change.parent)}
                    </span>
                    <span className="block font-mono text-xs text-teal">
                      {formatParamValue(change.value)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ) : null}
        <div className="flex justify-end">
          <Button variant="secondary" onClick={onDerive}>
            Derive a new profile
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

export function AnswerProfilesPage() {
  const [creating, setCreating] = useState(false);
  const [deriving, setDeriving] = useState<AnswerProfileRead | null>(null);
  const [inspecting, setInspecting] = useState<AnswerProfileRead | null>(null);

  const profiles = useQuery({
    queryKey: queryKeys.answerProfiles,
    queryFn: answerProfilesApi.list,
  });
  const items = profiles.data?.items ?? [];
  const nameOf = (id: string | null | undefined) =>
    items.find((item) => item.id === id)?.name ?? "—";

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Answer profiles</h1>
          <p className="mt-1 text-sm text-ink-muted">
            An answer system with the model, prompt and settings it answers with. A Q&A experiment
            compares them on the same index and retrieval profile.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>New answer profile</Button>
      </div>

      {profiles.isLoading ? <TableSkeleton /> : null}
      {profiles.isSuccess && items.length === 0 ? (
        <EmptyState
          title="No answer profile yet"
          body="Create one to run a Q&A experiment: pick the model and write the system prompt. Derive a second one to compare prompts."
          action={<Button onClick={() => setCreating(true)}>New answer profile</Button>}
        />
      ) : null}
      {items.length > 0 ? (
        <TableFrame>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-paper text-xs text-ink-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Profile</th>
                <th className="px-4 py-2 font-medium">System prompt</th>
                <th className="px-4 py-2 font-medium">Derived from</th>
                <th className="px-4 py-2 font-medium">Created</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((profile) => (
                <tr
                  key={profile.id}
                  className="border-b border-line last:border-0"
                  data-testid={`answer-profile-${profile.name}`}
                >
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      className="font-medium text-rust hover:underline"
                      onClick={() => setInspecting(profile)}
                    >
                      {profile.name}
                    </button>
                  </td>
                  <td className="max-w-md px-4 py-3 text-xs text-ink-muted">
                    {promptExcerpt(profile.params ?? {})}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {profile.parent_profile_id ? nameOf(profile.parent_profile_id) : "—"}
                  </td>
                  <td className="px-4 py-3 text-xs whitespace-nowrap">
                    {formatDate(profile.created_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button variant="ghost" onClick={() => setDeriving(profile)}>
                      Derive
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableFrame>
      ) : null}

      {creating ? <AnswerProfileDialog onClose={() => setCreating(false)} /> : null}
      {deriving ? (
        <AnswerProfileDialog parent={deriving} onClose={() => setDeriving(null)} />
      ) : null}
      {inspecting ? (
        <ProfileDetailDialog
          profile={inspecting}
          onClose={() => setInspecting(null)}
          onDerive={() => {
            setDeriving(inspecting);
            setInspecting(null);
          }}
        />
      ) : null}
    </div>
  );
}
