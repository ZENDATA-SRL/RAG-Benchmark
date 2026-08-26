import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger";

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const base =
    "inline-flex items-center justify-center gap-2 px-5 py-2.5 font-sans font-medium text-sm rounded-md transition-colors duration-150 ease-out disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-coral focus-visible:ring-offset-2";

  const styles =
    variant === "primary"
      ? "bg-coral text-white border border-transparent hover:bg-coral-deep"
      : variant === "danger"
        ? "bg-transparent text-red-700 border border-red-200 hover:bg-red-50"
        : "bg-transparent text-charcoal border border-linen hover:bg-linen hover:border-dune";

  return <button className={`${base} ${styles} ${className}`} {...props} />;
}

