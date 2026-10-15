import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Fail loudly rather than drifting to another port: the backend's CORS
    // allowlist names 5173 specifically.
    strictPort: true,
  },
});
