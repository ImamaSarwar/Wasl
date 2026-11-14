import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend runs on :5173 and forwards /api/* to the FastAPI backend on :8000,
// so the browser never hits CORS problems.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
