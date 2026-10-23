import { describe, expect, it } from "vitest";

import { buildStatusTone, canQuery, canStart, hasRunningBuild } from "./status";

describe("index build status", () => {
  it("maps each status to a tone", () => {
    expect(buildStatusTone("ready")).toBe("good");
    expect(buildStatusTone("failed")).toBe("bad");
    expect(buildStatusTone("running")).toBe("warn");
    expect(buildStatusTone("pending")).toBe("neutral");
  });

  it("allows starting anything but a running build", () => {
    expect(canStart({ status: "pending" })).toBe(true);
    expect(canStart({ status: "failed" })).toBe(true);
    expect(canStart({ status: "ready" })).toBe(true);
    expect(canStart({ status: "running" })).toBe(false);
  });

  it("queries only a ready build", () => {
    expect(canQuery({ status: "ready" })).toBe(true);
    expect(canQuery({ status: "running" })).toBe(false);
    expect(canQuery({ status: "pending" })).toBe(false);
    expect(canQuery({ status: "failed" })).toBe(false);
  });

  it("polls only while a build is running", () => {
    expect(hasRunningBuild([{ status: "ready" }, { status: "pending" }])).toBe(false);
    expect(hasRunningBuild([{ status: "ready" }, { status: "running" }])).toBe(true);
  });
});
