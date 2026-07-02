import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build straight into the Python package so `mark web` serves the latest build.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/mark/web/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8321",
      "/media": "http://127.0.0.1:8321",
    },
  },
});
