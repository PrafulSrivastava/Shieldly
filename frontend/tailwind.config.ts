import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#FFF8F3",
        coral: {
          DEFAULT: "#E8634A",
          dark: "#D14E36",
          glow: "rgba(232,99,74,0.15)",
        },
        plum: {
          DEFAULT: "#6B2E4F",
          light: "#8A4A6B",
        },
        lavender: {
          DEFAULT: "#E8DFF5",
          muted: "rgba(232,223,245,0.6)",
        },
        sage: {
          DEFAULT: "#B8CFC0",
          light: "#EBF2EE",
        },
        blush: "#FFE8E0",
        warm: {
          black: "#3A2030",
          muted: "#6B5060",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        body: ["var(--font-body)", "system-ui", "sans-serif"],
      },
      borderRadius: {
        card: "24px",
        pill: "999px",
        small: "12px",
      },
      boxShadow: {
        soft: "0 4px 24px rgba(107, 46, 79, 0.08)",
        lift: "0 12px 40px rgba(232, 99, 74, 0.15)",
        "coral-glow": "0 4px 20px rgba(232, 99, 74, 0.35)",
        "coral-glow-lg": "0 8px 32px rgba(232, 99, 74, 0.45)",
      },
      keyframes: {
        "radar-pulse": {
          "0%": { transform: "scale(0.15)", opacity: "0.45" },
          "100%": { transform: "scale(2.8)", opacity: "0" },
        },
        "glow-pulse": {
          "0%, 100%": {
            boxShadow:
              "0 0 20px rgba(232,99,74,0.25), 0 0 60px rgba(232,99,74,0.08)",
          },
          "50%": {
            boxShadow:
              "0 0 40px rgba(232,99,74,0.4), 0 0 100px rgba(232,99,74,0.18)",
          },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.3" },
        },
        "dot-pulse": {
          "0%, 100%": { opacity: "0.4", transform: "scale(0.85)" },
          "50%": { opacity: "1", transform: "scale(1)" },
        },
        drift: {
          "0%": { transform: "translate(0, 0) scale(1)" },
          "100%": { transform: "translate(30px, -40px) scale(1.05)" },
        },
      },
      animation: {
        "radar-1": "radar-pulse 4s ease-out infinite",
        "radar-2": "radar-pulse 4s ease-out 1.33s infinite",
        "radar-3": "radar-pulse 4s ease-out 2.66s infinite",
        "glow-pulse": "glow-pulse 3s ease-in-out infinite",
        "fade-in": "fade-in 400ms ease forwards",
        "slide-up": "slide-up 450ms ease forwards",
        blink: "blink 1.2s ease-in-out infinite",
        "dot-pulse": "dot-pulse 2s ease-in-out infinite",
        "drift-slow": "drift 18s ease-in-out infinite alternate",
        "drift-mid": "drift 22s ease-in-out infinite alternate-reverse",
        "drift-slower": "drift 26s ease-in-out infinite alternate",
      },
    },
  },
  plugins: [],
} satisfies Config;
