import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // "./" for production (Custom App sub-path). Relative index.html script tag
  // ensures dev works through DR notebook port proxy (.../ports/5173/).
  base: "./",
  server: {
    // Codespace / notebook port proxy forwards as app.*.datarobot.com — Vite 6+ blocks
    // unknown Host headers unless explicitly allowed.
    allowedHosts: [".datarobot.com", "localhost"],
    host: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
})
