/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // S2Cool design tokens
        "s2-bg": "#09090b",
        "s2-card": "#18181b",
        "s2-border": "#27272a",
        "s2-gold": "#fbbf24",
        "s2-red": "#ef4444",
        "s2-cyan": "#22d3ee",
        "s2-blue": "#3b82f6",
        "s2-text": "#f4f4f5",
        "s2-muted": "#a1a1aa",
      },
      fontFamily: {
        sans: ["Inter", "Roboto", "system-ui", "sans-serif"],
        mono: [
          "JetBrains Mono",
          "Fira Code",
          "ui-monospace",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};
