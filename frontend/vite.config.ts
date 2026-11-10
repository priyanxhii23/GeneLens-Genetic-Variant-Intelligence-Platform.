import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development every /api request is proxied to the FastAPI backend,
// so the browser never needs CORS and no backend URL is hard-coded.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: {
    chunkSizeWarningLimit: 4000,
    rollupOptions: { output: { manualChunks: { plotly: ["plotly.js-cartesian-dist-min"] } } },
  },
});
