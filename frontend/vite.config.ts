import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "ISSUEPILOT_");
  const apiTarget =
    process.env.ISSUEPILOT_API_TARGET || env.ISSUEPILOT_API_TARGET || "http://localhost:8000";
  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": apiTarget,
        "/health": apiTarget,
      },
    },
  };
});
