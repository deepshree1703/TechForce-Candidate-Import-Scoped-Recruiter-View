// Vite settings: React support, and a proxy so the page can call the API without CORS.
// In the browser the page calls /api/v1/candidates; Vite forwards it unchanged to http://api:8000/api/v1/candidates.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // listen on all addresses, so the port is reachable from outside the container
    port: 5173,
    watch: { usePolling: true }, // file changes are seen through the Docker mount on every system
    proxy: {
      "/api": {
        target: "http://api:8000", // the API service name and port in docker-compose.yml
        changeOrigin: true,
      },
    },
  },
});