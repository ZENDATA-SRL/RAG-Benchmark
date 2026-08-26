"use client";

import { Listbox, ListboxButton, ListboxOption, ListboxOptions } from "@headlessui/react";
import { Check, ChevronDown } from "lucide-react";

export type SelectOption<T extends string> = {
  value: T;
  label: string;
  disabled?: boolean;
};

/** Controlled empty state for Listbox — must not appear in `options[].value`. */
function emptyListboxValue<T extends string>(): T {
  return "" as T;
}

export function Select<T extends string>({
  value,
  onChange,
  options,
  placeholder = "Select…",
  disabled,
}: {
  value: T | null;
  onChange: (value: T) => void;
  options: SelectOption<T>[];
  placeholder?: string;
  disabled?: boolean;
}) {
  const selected = value ? options.find((o) => o.value === value) ?? null : null;
  // Headless Listbox uses `undefined` for “uncontrolled”; `null` was coerced to that before and
  // triggered React’s uncontrolled→controlled warning. Empty string keeps it controlled with no match.
  const listboxValue = value ?? emptyListboxValue<T>();

  return (
    <Listbox value={listboxValue} onChange={onChange} disabled={disabled}>
      <div className="relative">
        <ListboxButton
          className={[
            "w-full px-3 py-2 pr-10 bg-eggshell border border-linen rounded-md",
            "font-sans text-sm text-charcoal text-left",
            "focus:outline-none focus:border-stone focus:ring-1 focus:ring-stone",
            "transition-colors duration-150",
            "disabled:opacity-50 disabled:cursor-not-allowed",
          ].join(" ")}
        >
          <span className={selected ? "text-charcoal" : "text-ash"}>
            {selected ? selected.label : placeholder}
          </span>
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-ash">
            <ChevronDown className="h-[18px] w-[18px]" />
          </span>
        </ListboxButton>

        <ListboxOptions
          anchor="bottom start"
          className={[
            "z-50 mt-2 w-[var(--button-width)]",
            "rounded-xl border border-linen bg-eggshell shadow-panel p-1",
            "focus:outline-none",
          ].join(" ")}
          style={{}}
        >
          {options.map((opt) => (
            <ListboxOption
              key={opt.value}
              value={opt.value}
              disabled={opt.disabled}
              className={({ focus, selected }) =>
                [
                  "flex items-center justify-between gap-3 rounded-lg px-3 py-2",
                  "font-sans text-sm",
                  opt.disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer",
                  focus ? "bg-linen text-charcoal" : "text-charcoal",
                  selected ? "font-medium" : "font-normal",
                ].join(" ")
              }
            >
              {({ selected }) => (
                <>
                  <span className="min-w-0 truncate">{opt.label}</span>
                  {selected ? <Check className="h-4 w-4 text-coral" /> : null}
                </>
              )}
            </ListboxOption>
          ))}
        </ListboxOptions>
      </div>
    </Listbox>
  );
}

