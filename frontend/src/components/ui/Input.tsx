import type { InputHTMLAttributes } from "react";

export type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  invalid?: boolean;
};

export function Input({ className = "", invalid, ...props }: InputProps) {
  const state =
    invalid === true
      ? "border-red-300 text-red-800 placeholder:text-red-400/80 focus:border-red-400 focus:ring-red-400"
      : "border-linen text-charcoal placeholder:text-stone focus:border-stone focus:ring-stone";
  return (
    <input
      className={`w-full px-3 py-2 bg-eggshell border rounded-md font-sans text-sm focus:outline-none focus:ring-1 transition-colors duration-150 ${state} ${className}`}
      aria-invalid={invalid === true ? true : undefined}
      {...props}
    />
  );
}

