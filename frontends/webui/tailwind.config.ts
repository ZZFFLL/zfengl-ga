import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        app: {
          bg: "#f5f7fb",
          sidebar: "#f1f3f8",
          panel: "#ffffff",
          surface: "#f6f8fb",
          composer: "#fbfcff",
          line: "#d8deeb",
          text: "#202532",
          muted: "#657086",
          primary: "#4f67c9",
          primarySoft: "#eef2ff",
          success: "#1f8a5b",
          danger: "#ca4141",
          warning: "#b77a1e",
          userBubble: "#5870d2"
        }
      },
      boxShadow: {
        panel: "0 18px 44px rgba(28, 37, 65, 0.08)",
        soft: "0 6px 18px rgba(28, 37, 65, 0.045)"
      }
    }
  },
  plugins: []
} satisfies Config;
