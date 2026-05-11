import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        app: {
          bg: "#f7f7f5",
          canvas: "#ffffff",
          shell: "#ffffff",
          shellMuted: "#f3f3f1",
          sidebar: "#f3f3f1",
          panel: "#ffffff",
          surface: "#f6f6f3",
          composer: "#ffffff",
          line: "#e3e1dc",
          lineStrong: "#c9c5bd",
          text: "#242424",
          textStrong: "#111111",
          muted: "#6f6f6b",
          mutedSoft: "#9a9892",
          primary: "#0f766e",
          primarySoft: "#e6f4ef",
          primarySubtle: "#f1f8f5",
          info: "#256f8a",
          success: "#16845b",
          danger: "#b42318",
          warning: "#a15c07",
          codeBg: "#111827",
          codeText: "#eef2ff",
          userBubble: "#ffffff"
        }
      },
      boxShadow: {
        panel: "0 1px 2px rgba(15, 23, 42, 0.04)",
        soft: "0 1px 2px rgba(15, 23, 42, 0.05)",
        composer: "0 8px 30px rgba(15, 23, 42, 0.08)"
      }
    }
  },
  plugins: []
} satisfies Config;
