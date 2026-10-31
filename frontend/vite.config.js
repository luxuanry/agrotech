import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, /api calls are proxied to the FastAPI server on port 8000,
// and /agent-api calls to the NOVA rewriter agent (uv run nova-rewriter-api) on port 8001.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/agent-api": "http://127.0.0.1:8001",
      "/api": "http://127.0.0.1:8000",
    },
  },
});
