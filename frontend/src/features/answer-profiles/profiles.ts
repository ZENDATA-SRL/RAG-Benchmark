import type { AnswerProfileRead, ComponentWithVersionsRead } from "@/api/types";

/** The registry components that answer questions: the only ones an answer profile can use. */
export function answerSystems(
  components: ComponentWithVersionsRead[],
): ComponentWithVersionsRead[] {
  return components.filter((component) => component.type === "answer_system");
}

/**
 * The parameters as sent to the server. A text field emptied by hand is an empty string, which
 * the server would hash as a different profile from the field left out: it is dropped.
 */
export function compactParams(params: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== "" && value !== undefined),
  );
}

/** The start of a prompt on one line, for a table cell. */
export function promptExcerpt(params: Record<string, unknown>, length = 80): string {
  const prompt = typeof params.system_prompt === "string" ? params.system_prompt : "";
  const flat = prompt.replace(/\s+/g, " ").trim();
  return flat.length > length ? `${flat.slice(0, length - 1)}…` : flat;
}

/** A parameter value as shown in a diff: strings as they are, the rest as JSON. */
export function formatParamValue(value: unknown): string {
  if (value === undefined || value === null) return "—";
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** Profiles another profile can be derived from: those of the same answer system version. */
export function parentChoices(
  profiles: AnswerProfileRead[],
  componentVersionId: string | undefined,
): AnswerProfileRead[] {
  return profiles.filter((profile) => profile.component_version_id === componentVersionId);
}
