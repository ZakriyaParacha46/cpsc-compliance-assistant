import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// In dev, /api is proxied to the API so the browser sees one origin, the same
// shape as prod. `npm run dev:mock` skips the API and serves sample data.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": process.env.API_ORIGIN ?? "http://localhost:8000" },
  },
});
