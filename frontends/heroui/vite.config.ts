import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const bridgeTarget = env.GA_HEROUI_API_TARGET || "http://127.0.0.1:14169";
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5178,
      proxy: {
        "/status": bridgeTarget,
        "/config": bridgeTarget,
        "/model-profile": bridgeTarget,
        "/model-profiles": bridgeTarget,
        "/sessions": bridgeTarget,
        "/session": bridgeTarget,
        "/sops": bridgeTarget,
        "/path": bridgeTarget,
        "/ws": {
          target: bridgeTarget,
          ws: true,
        },
      },
    },
  };
});
