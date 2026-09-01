import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
};

const styles: Record<Variant, string> = {
  primary: "bg-rust text-white hover:bg-rust-dark disabled:bg-line disabled:text-ink-muted",
  secondary: "border border-line bg-paper-raised text-ink hover:border-ink/30",
  ghost: "text-ink-muted hover:bg-ink/5 hover:text-ink",
  danger: "bg-danger text-white hover:bg-danger/90",
};

export function Button({ variant = "primary", className = "", ...props }: Props) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed ${styles[variant]} ${className}`}
      {...props}
    />
  );
}
