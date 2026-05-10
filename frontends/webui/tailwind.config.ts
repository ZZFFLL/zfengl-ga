import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        app: {
          bg: "#f4f6f8",
          canvas: "#f8fafb",
          shell: "#161a22",
          shellMuted: "#252b35",
          sidebar: "#edf1f5",
          panel: "#ffffff",
          surface: "#f7f9fb",
          composer: "#ffffff",
          line: "#d9e0e8",
          lineStrong: "#b8c3cf",
          text: "#1d2430",
          textStrong: "#111827",
          muted: "#5b6678",
          mutedSoft: "#8a95a5",
          primary: "#0f766e",
          primarySoft: "#e7f5f2",
          primarySubtle: "#f0faf8",
          info: "#0e7490",
          success: "#16845b",
          danger: "#c2413d",
          warning: "#b26a18",
          codeBg: "#111827",
          codeText: "#eef2ff",
          userBubble: "#172033"
        }
      },
      boxShadow: {
        panel: "0 14px 34px rgba(17, 24, 39, 0.075)",
        soft: "0 5px 16px rgba(17, 24, 39, 0.045)",
        composer: "0 12px 34px rgba(17, 24, 39, 0.10)"
      }
    }
  },
  plugins: []
} satisfies Config;
