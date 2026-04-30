import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        app: {
          bg: "#f7f8fa",
          panel: "#ffffff",
          line: "#dfe5ee",
          text: "#16202f",
          muted: "#657284",
          primary: "#315a7d",
          primarySoft: "#e7eef6",
          success: "#17845b",
          danger: "#c93b3b",
          warning: "#b97814"
        }
      },
      boxShadow: {
        panel: "0 10px 30px rgba(28, 39, 52, 0.08)"
      }
    }
  },
  plugins: []
} satisfies Config;
