import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** Remove the frontend-only prefix before forwarding requests to FastAPI. */
function removeApiPrefix(path) {
  return path.replace(/^\/api/, "");
}

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: removeApiPrefix,
      },
    },
  },
});
