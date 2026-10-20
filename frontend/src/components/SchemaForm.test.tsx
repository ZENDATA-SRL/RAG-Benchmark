import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { defaultsFromSchema, SchemaForm, type JsonSchema } from "./SchemaForm";

const FICTIONAL_SCHEMA: JsonSchema = {
  type: "object",
  title: "Fictional parser",
  properties: {
    temperature: {
      type: "number",
      title: "Temperature",
      default: 0.2,
      minimum: 0,
      maximum: 1,
    },
    enable_ocr: {
      type: "boolean",
      title: "Enable OCR",
      default: false,
    },
    chunk_size: {
      type: "integer",
      title: "Chunk size",
      default: 400,
      minimum: 1,
    },
  },
};

function Harness() {
  const [data, setData] = useState(defaultsFromSchema(FICTIONAL_SCHEMA));
  return (
    <div>
      <SchemaForm schema={FICTIONAL_SCHEMA} formData={data} onChange={setData} />
      <output data-testid="form-json">{JSON.stringify(data)}</output>
    </div>
  );
}

describe("SchemaForm", () => {
  it("renders fields from an arbitrary schema with no hardcoded keys", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.getByText("Temperature")).toBeInTheDocument();
    expect(screen.getByText("Enable OCR")).toBeInTheDocument();
    expect(screen.getByRole("slider")).toBeInTheDocument();

    await user.click(screen.getByRole("switch"));
    expect(screen.getByTestId("form-json").textContent).toContain('"enable_ocr":true');
  });

  it("accepts registry schemas declared as draft 2020-12 with extra properties allowed", () => {
    const schema: JsonSchema = {
      $schema: "https://json-schema.org/draft/2020-12/schema",
      type: "object",
      additionalProperties: true,
      properties: { region: { type: "string", title: "Region", default: "eu-central-1" } },
    };

    render(<SchemaForm schema={schema} formData={defaultsFromSchema(schema)} onChange={() => {}} />);

    expect(screen.getByText("Region")).toBeInTheDocument();
    expect(screen.queryByText(/invalid parameter/)).not.toBeInTheDocument();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
