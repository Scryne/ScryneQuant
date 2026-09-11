import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Geliştirmede API trader sürecinde çalışıyor (K-036): `/api` oraya proxy'leniyor.
// Üretimde proxy yok — FastAPI hem API'yi hem bu build'i servis ediyor, yani tek origin,
// tek süreç. Geliştirmenin üretimden tek farkı bu satır.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8787", changeOrigin: true } },
  },
  build: { outDir: "dist", sourcemap: true },
});
