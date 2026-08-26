import forms from "@tailwindcss/forms";
import typography from "@tailwindcss/typography";
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        // Warm neutrals — primary surface and text palette
        eggshell: "#faf9f5",
        paper: "#f2f0e8",
        pampas: "#f4f3ee",
        linen: "#e8e6dc",
        dune: "#b0aea5",
        stone: "#a2a09a",
        ash: "#767570",
        slate: "#54544f",
        charcoal: "#1d1d1a",
        ink: "#141413",

        // Accent — Anthropic burnt orange / coral
        coral: {
          DEFAULT: "#d97757",
          light: "#e8927c",
          soft: "#f0c4b0",
          deep: "#c15f3c",
        },

        // Secondary accents
        denim: "#6a9bcc",
        sage: "#788c5d",

        // Dark mode surfaces
        dark: {
          ink: "#0f0f0e",
          base: "#1a1917",
          surface: "#222220",
          border: "#2e2d2a",
          muted: "#3d3c38",
        },

        // Semantic aliases (map to CSS vars for theme switching)
        bg: {
          DEFAULT: "var(--color-bg)",
          subtle: "var(--color-bg-subtle)",
          muted: "var(--color-bg-muted)",
          overlay: "var(--color-bg-overlay)",
        },
        text: {
          primary: "var(--color-text-primary)",
          secondary: "var(--color-text-secondary)",
          tertiary: "var(--color-text-tertiary)",
          muted: "var(--color-text-muted)",
        },
        border: {
          DEFAULT: "var(--color-border)",
          strong: "var(--color-border-strong)",
        },
        accent: {
          DEFAULT: "var(--color-accent)",
          hover: "var(--color-accent-hover)",
          soft: "var(--color-accent-soft)",
        },
      },

      fontFamily: {
        serif: [
          "Tiempos Text",
          "Galaxie Copernicus",
          "Georgia",
          "Times New Roman",
          "serif",
        ],
        headline: ["Tiempos Headline", "Tiempos Text", "Georgia", "serif"],
        sans: [
          "Styrene A",
          "Styrene B",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "sans-serif",
        ],
        mono: ["Berkeley Mono", "ui-monospace", "Fira Code", "Cascadia Code", "monospace"],
      },

      fontSize: {
        xs: ["0.75rem", { lineHeight: "1rem", letterSpacing: "0.01em" }],
        sm: ["0.875rem", { lineHeight: "1.25rem", letterSpacing: "0" }],
        base: ["1rem", { lineHeight: "1.7rem", letterSpacing: "0" }],
        lg: ["1.125rem", { lineHeight: "1.75rem", letterSpacing: "-0.005em" }],
        xl: ["1.25rem", { lineHeight: "1.75rem", letterSpacing: "-0.01em" }],
        "2xl": ["1.5rem", { lineHeight: "2rem", letterSpacing: "-0.015em" }],
        "3xl": ["1.875rem", { lineHeight: "2.25rem", letterSpacing: "-0.02em" }],
        "4xl": ["2.25rem", { lineHeight: "2.5rem", letterSpacing: "-0.025em" }],
        "5xl": ["3rem", { lineHeight: "1.1", letterSpacing: "-0.035em" }],
        "6xl": ["3.75rem", { lineHeight: "1.05", letterSpacing: "-0.04em" }],
        "7xl": ["4.5rem", { lineHeight: "1.0", letterSpacing: "-0.04em" }],
      },

      borderRadius: {
        none: "0",
        sm: "4px",
        DEFAULT: "6px",
        md: "8px",
        lg: "12px",
        xl: "16px",
        "2xl": "20px",
        "3xl": "28px",
        full: "9999px",
      },

      boxShadow: {
        xs: "0 1px 2px 0 rgba(29, 29, 26, 0.04)",
        sm: "0 1px 3px 0 rgba(29, 29, 26, 0.06), 0 1px 2px -1px rgba(29, 29, 26, 0.04)",
        DEFAULT:
          "0 4px 6px -1px rgba(29, 29, 26, 0.06), 0 2px 4px -2px rgba(29, 29, 26, 0.04)",
        md: "0 4px 6px -1px rgba(29, 29, 26, 0.06), 0 2px 4px -2px rgba(29, 29, 26, 0.04)",
        lg: "0 10px 15px -3px rgba(29, 29, 26, 0.08), 0 4px 6px -4px rgba(29, 29, 26, 0.04)",
        xl: "0 20px 25px -5px rgba(29, 29, 26, 0.08), 0 8px 10px -6px rgba(29, 29, 26, 0.04)",
        "2xl": "0 25px 50px -12px rgba(29, 29, 26, 0.12)",
        inner: "inset 0 2px 4px 0 rgba(29, 29, 26, 0.04)",
        "chat-input": "0 0 0 1px rgba(29, 29, 26, 0.08), 0 2px 8px 0 rgba(29, 29, 26, 0.06)",
        "card-hover":
          "0 8px 16px -4px rgba(29, 29, 26, 0.10), 0 4px 6px -4px rgba(29, 29, 26, 0.06)",
        panel: "0 0 0 1px rgba(29, 29, 26, 0.06), 0 4px 12px 0 rgba(29, 29, 26, 0.05)",
        none: "none",
      },

      spacing: {
        px: "1px",
        0: "0",
        0.5: "2px",
        1: "4px",
        1.5: "6px",
        2: "8px",
        2.5: "10px",
        3: "12px",
        3.5: "14px",
        4: "16px",
        5: "20px",
        6: "24px",
        7: "28px",
        8: "32px",
        9: "36px",
        10: "40px",
        11: "44px",
        12: "48px",
        14: "56px",
        16: "64px",
        18: "72px",
        20: "80px",
        24: "96px",
        28: "112px",
        32: "128px",
        36: "144px",
        40: "160px",
        48: "192px",
        56: "224px",
        64: "256px",
        72: "288px",
        80: "320px",
        96: "384px",
      },

      maxWidth: {
        chat: "48rem",
        prose: "65ch",
        content: "720px",
        wide: "960px",
        "full-hd": "1440px",
      },

      animation: {
        "fade-in": "fadeIn 0.2s ease-out",
        "fade-up": "fadeUp 0.3s ease-out",
        "slide-in-left": "slideInLeft 0.25s ease-out",
        "pulse-soft": "pulseSoft 2s ease-in-out infinite",
      },

      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideInLeft: {
          "0%": { opacity: "0", transform: "translateX(-12px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
      },

      typography: {
        anthropic: {
          css: {
            "--tw-prose-body": "#1d1d1a",
            "--tw-prose-headings": "#141413",
            "--tw-prose-lead": "#54544f",
            "--tw-prose-links": "#d97757",
            "--tw-prose-bold": "#1d1d1a",
            "--tw-prose-counters": "#767570",
            "--tw-prose-bullets": "#b0aea5",
            "--tw-prose-hr": "#e8e6dc",
            "--tw-prose-quotes": "#1d1d1a",
            "--tw-prose-quote-borders": "#d97757",
            "--tw-prose-captions": "#767570",
            "--tw-prose-code": "#1d1d1a",
            "--tw-prose-pre-code": "#faf9f5",
            "--tw-prose-pre-bg": "#141413",
            "--tw-prose-th-borders": "#e8e6dc",
            "--tw-prose-td-borders": "#e8e6dc",
            fontFamily: "var(--font-sans)",
            fontSize: "1rem",
            lineHeight: "1.7",
            h1: {
              fontFamily: "var(--font-headline)",
              fontWeight: "400",
              letterSpacing: "-0.025em",
              lineHeight: "1.15",
            },
            h2: {
              fontFamily: "var(--font-serif)",
              fontWeight: "400",
              letterSpacing: "-0.02em",
              lineHeight: "1.2",
            },
            h3: {
              fontFamily: "var(--font-serif)",
              fontWeight: "500",
              letterSpacing: "-0.015em",
            },
            blockquote: {
              fontStyle: "italic",
              fontFamily: "var(--font-serif)",
              borderLeftWidth: "2px",
            },
            a: {
              textDecoration: "underline",
              textDecorationColor: "rgba(217, 119, 87, 0.4)",
              textUnderlineOffset: "2px",
              "&:hover": {
                textDecorationColor: "#d97757",
              },
            },
          },
        },
      },
    },
  },
  plugins: [typography, forms],
};

export default config;

