import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// --------------------------------------------------------------------------
// Vite dev server config.
// The proxy forwards /v1/* and /production_metrics.json calls to the FastAPI
// backend so we can develop the frontend independently with `npm run dev`.
// --------------------------------------------------------------------------
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/v1": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/production_metrics.json": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
