import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    // Codespace / notebook port proxy forwards as app.*.datarobot.com — Vite 6+ blocks
    // unknown Host headers unless explicitly allowed.
    allowedHosts: [".datarobot.com", "localhost"],
    host: true,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
})
