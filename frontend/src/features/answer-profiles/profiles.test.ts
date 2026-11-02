import { describe, expect, it } from "vitest";

import type { AnswerProfileRead, ComponentWithVersionsRead } from "@/api/types";

import {
  answerSystems,
  compactParams,
  formatParamValue,
  parentChoices,
  promptExcerpt,
} from "./profiles";

describe("answer profile helpers", () => {
  it("keeps only answer systems", () => {
    const components = [
      { id: "a", type: "answer_system" },
      { id: "b", type: "embedder" },
    ] as ComponentWithVersionsRead[];
    expect(answerSystems(components).map((item) => item.id)).toEqual(["a"]);
  });

  it("drops emptied fields so they hash like fields left out", () => {
    expect(compactParams({ model: "m", region: "", temperature: 0 })).toEqual({
      model: "m",
      temperature: 0,
    });
  });

  it("shows a prompt on one shortened line", () => {
    expect(promptExcerpt({ system_prompt: "Answer\n  from the passages." })).toBe(
      "Answer from the passages.",
    );
    expect(promptExcerpt({ system_prompt: "x".repeat(100) }, 10)).toBe(`${"x".repeat(9)}…`);
    expect(promptExcerpt({})).toBe("");
  });

  it("formats parameter values for a diff", () => {
    expect(formatParamValue("text")).toBe("text");
    expect(formatParamValue(0.5)).toBe("0.5");
    expect(formatParamValue(undefined)).toBe("—");
  });

  it("offers as parents only the profiles of the same version", () => {
    const profiles = [
      { id: "p1", component_version_id: "v1" },
      { id: "p2", component_version_id: "v2" },
    ] as AnswerProfileRead[];
    expect(parentChoices(profiles, "v1").map((item) => item.id)).toEqual(["p1"]);
  });
});
