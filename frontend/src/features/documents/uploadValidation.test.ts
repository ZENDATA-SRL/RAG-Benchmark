import { describe, expect, it } from "vitest";

import { classifyFile, partitionFiles } from "./uploadValidation";

function file(name: string, size = 12, type = "application/pdf"): File {
  return new File([new Uint8Array(size)], name, { type });
}

describe("uploadValidation", () => {
  it("rejects unsupported extensions before upload", () => {
    const reject = classifyFile(file("notes.txt", 20, "text/plain"));
    expect(reject?.outcome).toBe("skipped_unsupported");
  });

  it("lets a mixed batch continue after setting the txt aside", () => {
    const { accepted, rejected } = partitionFiles([
      file("a.pdf"),
      file("notes.txt", 8, "text/plain"),
      file("b.pdf"),
    ]);
    expect(accepted.map((item) => item.name)).toEqual(["a.pdf", "b.pdf"]);
    expect(rejected).toHaveLength(1);
    expect(rejected[0].outcome).toBe("skipped_unsupported");
  });
});
