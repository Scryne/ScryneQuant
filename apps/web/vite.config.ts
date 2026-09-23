import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Geliştirmede API trader sürecinde çalışıyor (K-036): `/api` oraya proxy'leniyor.
// Üretimde proxy yok — FastAPI hem API'yi hem bu build'i servis ediyor, yani tek origin,
// tek süreç. Geliştirmenin üretimden tek farkı bu satır.
// İki giriş, tek build: `index.html` koşunun kendi panosu (8787, koşu süreci servis eder),
// `pano.html` bütün koşuları gösteren salt okunur gözlem panosu (8788, ayrı süreç). İkisi
// token'ları, ilkel bileşenleri ve biçim yardımcılarını **paylaşıyor** — ayrı bir Vite
// projesi açmak o paylaşımı kopyalamak olurdu ve iki ekran zamanla birbirinden ayrışırdı.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Bot paneli (`bot.html`) `sq execution pano` (8790) sunucusunu okur; önce eşleşmeli.
      "/api/bot": { target: "http://127.0.0.1:8790", changeOrigin: true },
      "/api/aktif": { target: "http://127.0.0.1:8790", changeOrigin: true },
      "/api": { target: "http://127.0.0.1:8787", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      input: {
        index: fileURLToPath(new URL("index.html", import.meta.url)),
        pano: fileURLToPath(new URL("pano.html", import.meta.url)),
        bot: fileURLToPath(new URL("bot.html", import.meta.url)),
        // K-134: aktif demo botlar; `sq execution pano` kök sayfası.
        aktif: fileURLToPath(new URL("aktif.html", import.meta.url)),
      },
    },
  },
});
