import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Shared proxy config — applied to both the dev server and `vite preview`.
// Production traffic is handled by CloudFront → ALB routing rules.
const apiProxy = {
  "/v1": { target: "http://localhost:8000", changeOrigin: true },
};

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: apiProxy },
  preview: { proxy: apiProxy },
});
