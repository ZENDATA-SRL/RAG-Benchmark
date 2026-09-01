import Form from "@rjsf/core";
import type {
  RJSFSchema,
  RJSFValidationError,
  StrictRJSFSchema,
  UiSchema,
  WidgetProps,
} from "@rjsf/utils";
import validator from "@rjsf/validator-ajv8";
import { useMemo } from "react";

export type JsonSchema = RJSFSchema;

type Props = {
  schema: JsonSchema;
  formData: Record<string, unknown>;
  onChange: (data: Record<string, unknown>) => void;
  onSubmit?: (data: Record<string, unknown>) => void;
  disabled?: boolean;
  id?: string;
};

function ToggleWidget(props: WidgetProps) {
  const { id, value, disabled, label, onChange } = props;
  return (
    <label className="flex items-center gap-3 text-sm">
      <button
        type="button"
        id={id}
        role="switch"
        aria-checked={Boolean(value)}
        disabled={disabled}
        onClick={() => onChange(!value)}
        className={`relative h-6 w-10 rounded-full transition ${value ? "bg-teal" : "bg-line"}`}
      >
        <span
          className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition ${
            value ? "translate-x-4" : ""
          }`}
        />
      </button>
      <span>{label}</span>
    </label>
  );
}

function SliderNumberWidget(props: WidgetProps) {
  const { id, value, disabled, onChange, schema } = props;
  const min = typeof schema.minimum === "number" ? schema.minimum : 1;
  const max = typeof schema.maximum === "number" ? schema.maximum : Math.max(min + 4000, 8000);
  const step = typeof schema.multipleOf === "number" ? schema.multipleOf : 1;
  const numeric = typeof value === "number" ? value : min;

  return (
    <div className="flex items-center gap-3">
      <input
        type="range"
        id={id}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        value={numeric}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-2 flex-1 accent-rust"
      />
      <input
        type="number"
        aria-label={props.label}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        value={numeric}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-24 rounded-md border border-line bg-paper-raised px-2 py-1 font-mono text-sm"
      />
    </div>
  );
}

function TextWidget(props: WidgetProps) {
  const { id, value, disabled, placeholder, onChange, schema } = props;
  const isNumber = schema.type === "number" || schema.type === "integer";
  return (
    <input
      id={id}
      type={isNumber ? "number" : "text"}
      disabled={disabled}
      placeholder={placeholder}
      value={value ?? ""}
      onChange={(event) =>
        onChange(isNumber ? (event.target.value === "" ? undefined : Number(event.target.value)) : event.target.value)
      }
      className="w-full rounded-md border border-line bg-paper-raised px-3 py-1.5 text-sm"
    />
  );
}

function SelectWidget(props: WidgetProps) {
  const { id, value, disabled, options, onChange } = props;
  return (
    <select
      id={id}
      disabled={disabled}
      value={value ?? ""}
      onChange={(event) => onChange(event.target.value)}
      className="w-full rounded-md border border-line bg-paper-raised px-3 py-1.5 text-sm"
    >
      {(options.enumOptions ?? []).map((option) => (
        <option key={String(option.value)} value={String(option.value)}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

const widgets = {
  CheckboxWidget: ToggleWidget,
  RangeWidget: SliderNumberWidget,
  TextWidget,
  SelectWidget,
};

function uiSchemaFor(schema: StrictRJSFSchema): UiSchema {
  const ui: UiSchema = {};
  const properties = schema.properties ?? {};
  for (const [key, definition] of Object.entries(properties)) {
    if (typeof definition !== "object" || definition === null || Array.isArray(definition)) {
      continue;
    }
    if (key === "chunk_size" || definition.title === "Chunk size") {
      ui[key] = { "ui:widget": "range" };
    }
  }
  return ui;
}

function transformErrors(errors: RJSFValidationError[]): RJSFValidationError[] {
  return errors.map((error) => {
    const path = (error.property ?? "").replace(/^\./, "") || "<root>";
    return {
      ...error,
      message: `invalid parameter at ${path}: ${error.message ?? "does not match the schema"}`,
    };
  });
}

export function SchemaForm({ schema, formData, onChange, onSubmit, disabled, id }: Props) {
  const uiSchema = useMemo(() => uiSchemaFor(schema), [schema]);

  return (
    <Form
      id={id}
      schema={schema}
      uiSchema={uiSchema}
      formData={formData}
      validator={validator}
      widgets={widgets}
      disabled={disabled}
      showErrorList={false}
      liveValidate
      transformErrors={transformErrors}
      onChange={(event) => onChange((event.formData ?? {}) as Record<string, unknown>)}
      onSubmit={(event) => onSubmit?.((event.formData ?? {}) as Record<string, unknown>)}
      className="schema-form space-y-4"
    >
      {onSubmit ? null : <div />}
    </Form>
  );
}

export function defaultsFromSchema(schema: JsonSchema): Record<string, unknown> {
  const defaults: Record<string, unknown> = {};
  const properties = schema.properties ?? {};
  for (const [key, definition] of Object.entries(properties)) {
    if (typeof definition === "object" && definition !== null && "default" in definition) {
      defaults[key] = definition.default;
    }
  }
  return defaults;
}
