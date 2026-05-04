import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        app: {
          bg: "#f5f6f8",
          sidebar: "#f6f7fa",
          panel: "#ffffff",
          surface: "#fafbfe",
          composer: "#fbfcff",
          line: "#dfe5f1",
          text: "#1f2430",
          muted: "#6f7a92",
          primary: "#516dd2",
          primarySoft: "#eef2ff",
          success: "#1f8a5b",
          danger: "#ca4141",
          warning: "#b77a1e",
          userBubble: "#5b75d7"
        }
      },
      boxShadow: {
        panel: "0 18px 44px rgba(34, 44, 72, 0.1)",
        soft: "0 8px 24px rgba(30, 38, 62, 0.06)"
      }
    }
  },
  plugins: []
} satisfies Config;
