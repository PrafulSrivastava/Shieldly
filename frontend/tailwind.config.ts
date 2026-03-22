import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        void: {
          DEFAULT: "#0A0A0F",
          light: "#12121A",
          lighter: "#1A1A25",
          border: "#252530",
        },
        danger: {
          DEFAULT: "#FF1744",
          dark: "#D50000",
          glow: "rgba(255,23,68,0.15)",
        },
        amber: {
          DEFAULT: "#FF9800",
          dark: "#F57C00",
        },
        shield: {
          DEFAULT: "#00E676",
          dark: "#00C853",
        },
      },
      fontFamily: {
        display: ['"Bebas Neue"', "Impact", "sans-serif"],
        mono: ['"IBM Plex Mono"', "monospace"],
      },
      keyframes: {
        "radar-pulse": {
          "0%": { transform: "scale(0.15)", opacity: "0.45" },
          "100%": { transform: "scale(2.8)", opacity: "0" },
        },
        "glow-pulse": {
          "0%, 100%": {
            boxShadow:
              "0 0 20px rgba(255,23,68,0.3), 0 0 60px rgba(255,23,68,0.1)",
          },
          "50%": {
            boxShadow:
              "0 0 40px rgba(255,23,68,0.5), 0 0 100px rgba(255,23,68,0.25)",
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
      },
    },
  },
  plugins: [],
} satisfies Config;
