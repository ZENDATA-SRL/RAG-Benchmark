import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { retrievalApi, retrievalProfilesApi } from "@/api/resources";
import type { IndexBuildRead, RetrievalStrategy, RetrieveResponse } from "@/api/types";
import { defaultsFromSchema, SchemaForm, type JsonSchema } from "@/components/SchemaForm";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { queryKeys } from "@/lib/queryClient";
import { toast } from "@/lib/toast";

import { describeProfile, describeTimings, hitLink, RETRIEVAL_PROFILE_SCHEMA } from "./query";

const schema = RETRIEVAL_PROFILE_SCHEMA as unknown as JsonSchema;
const SNIPPET_CHARS = 280;

function NewProfileForm({ first, onCreated }: { first: boolean; onCreated: (id: string) => void }) {
  const queryClient = useQueryClient();
  const [fields, setFields] = useState<Record<string, unknown>>(() => defaultsFromSchema(schema));

  const create = useMutation({
    mutationFn: () =>
      retrievalProfilesApi.create({
        strategy: fields.strategy as RetrievalStrategy,
        top_k: Number(fields.top_k),
        score_threshold: typeof fields.score_threshold === "number" ? fields.score_threshold : null,
      }),
    onSuccess: async (result) => {
      if (result.created) toast.success(`Profile "${result.profile.name}" created.`);
      else toast.info(result.detail ?? `An identical profile exists as "${result.profile.name}".`);
      await queryClient.invalidateQueries({ queryKey: queryKeys.retrievalProfiles });
      onCreated(result.profile.id);
    },
  });

  return (
    <div className="space-y-3 rounded-lg border border-line bg-paper p-4">
      <div>
        <h3 className="text-sm font-semibold">New retrieval profile</h3>
        <p className="text-xs text-ink-muted">
          {first
            ? "No retrieval profile exists yet: create one to query this index."
            : "How many chunks to return, and how good they must be."}
        </p>
      </div>
      <SchemaForm schema={schema} formData={fields} onChange={setFields} />
      <div className="flex justify-end">
        <Button
          type="button"
          disabled={!fields.top_k || !fields.strategy || create.isPending}
          onClick={() => create.mutate()}
        >
          Create profile
        </Button>
      </div>
    </div>
  );
}

function Results({ response }: { response: RetrieveResponse }) {
  if (response.hits.length === 0) {
    return <p className="text-sm text-ink-muted">No chunk matched.</p>;
  }
  return (
    <ol className="space-y-2">
      {response.hits.map((hit) => {
        const link = hitLink(response, hit);
        const heading = (
          <span className="flex flex-wrap items-baseline gap-x-3 text-xs text-ink-muted">
            <span className="font-mono font-semibold text-ink">#{hit.rank}</span>
            <span className="font-mono">{hit.score.toFixed(3)}</span>
            <span>{hit.filename ?? "chunk no longer in the database"}</span>
            {hit.page ? <span>page {hit.page}</span> : null}
          </span>
        );
        const snippet = (hit.text ?? "").slice(0, SNIPPET_CHARS);
        const body = (
          <>
            {heading}
            <span className="mt-1 block text-sm whitespace-pre-line">
              {snippet}
              {(hit.text?.length ?? 0) > SNIPPET_CHARS ? "…" : ""}
            </span>
          </>
        );
        return (
          <li key={`${hit.rank}-${hit.chunk_id ?? "gone"}`}>
            {link ? (
              <Link
                to={link}
                className="block rounded-lg border border-line bg-paper p-3 hover:border-ink-muted"
              >
                {body}
              </Link>
            ) : (
              <div className="rounded-lg border border-dashed border-line p-3">{body}</div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** Manual query against a ready index build, with each hit linking to its chunk. */
export function QueryPanel({ build, onClose }: { build: IndexBuildRead; onClose: () => void }) {
  const [profileId, setProfileId] = useState<string>("");
  const [creatingProfile, setCreatingProfile] = useState(false);
  const [query, setQuery] = useState("");

  const profiles = useQuery({
    queryKey: queryKeys.retrievalProfiles,
    queryFn: retrievalProfilesApi.list,
  });
  const items = profiles.data?.items ?? [];
  const chosen = profileId || items[0]?.id || "";
  // With no profile the form is the only way forward, so it stays open and has no toggle.
  const noProfiles = profiles.isSuccess && items.length === 0;
  const showForm = creatingProfile || noProfiles;

  const search = useMutation({
    mutationFn: () =>
      retrievalApi.retrieve({
        index_build_id: build.id,
        retrieval_profile_id: chosen,
        query: query.trim(),
      }),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (chosen && query.trim()) search.mutate();
  };

  return (
    <Dialog title={`Query "${build.name}"`} onClose={onClose} wide>
      <div className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="block min-w-64 flex-1 text-sm">
            <span className="mb-1 block font-medium">Retrieval profile</span>
            <select
              value={chosen}
              onChange={(event) => setProfileId(event.target.value)}
              disabled={items.length === 0}
              className="w-full rounded-md border border-line bg-paper px-3 py-1.5"
            >
              {items.length === 0 ? <option value="">No profile yet</option> : null}
              {items.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.name} — {describeProfile(profile)}
                </option>
              ))}
            </select>
          </label>
          {noProfiles ? null : (
            <Button
              type="button"
              variant="secondary"
              onClick={() => setCreatingProfile((value) => !value)}
            >
              {creatingProfile ? "Cancel" : "New profile"}
            </Button>
          )}
        </div>

        {showForm ? (
          <NewProfileForm
            first={noProfiles}
            onCreated={(id) => {
              setProfileId(id);
              setCreatingProfile(false);
            }}
          />
        ) : null}

        <form onSubmit={submit} className="flex flex-wrap gap-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Type a question or paste a sentence"
            maxLength={10000}
            className="min-w-64 flex-1 rounded-md border border-line bg-paper px-3 py-1.5 text-sm"
          />
          <Button type="submit" disabled={!chosen || !query.trim() || search.isPending}>
            {search.isPending ? "Searching…" : "Search"}
          </Button>
        </form>

        {search.data ? (
          <div className="space-y-2">
            <p className="text-xs text-ink-muted">
              {search.data.hits.length} hits in {describeTimings(search.data.timings)}
            </p>
            <Results response={search.data} />
          </div>
        ) : null}
      </div>
    </Dialog>
  );
}
