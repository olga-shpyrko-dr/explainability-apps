import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const DEV_PORT = Number(process.env.VITE_DEV_PORT || process.env.PORT || 5173);

/**
 * When running in a DataRobot Codespace, NOTEBOOK_ID is set and the UI is
 * accessed via /notebook-sessions/{id}/ports/{port}/. Vite must use that
 * as `base` or all module URLs resolve to the domain root (blank page).
 * Mirrors af-component-fastapi-backend get_app_base_url().
 */
function notebookDevBase(): string | null {
  const notebookId = process.env.NOTEBOOK_ID;
  if (!notebookId) return null;

  const basePath = process.env.BASE_PATH;
  if (basePath) {
    const normalized = basePath.startsWith("/") ? basePath : `/${basePath}`;
    return normalized.endsWith("/") ? normalized : `${normalized}/`;
  }

  return `/notebook-sessions/${notebookId}/ports/${DEV_PORT}/`;
}

export default defineConfig(({ command }) => {
  const notebookBase = command === "serve" ? notebookDevBase() : null;
  const base = command === "build" ? "./" : (notebookBase ?? "/");

  // Proxy API calls to the FastAPI backend. When base is a sub-path, prefix
  // the proxy key per Vite docs; also keep a plain /api rule for when the
  // notebook proxy strips the path prefix before forwarding to Vite.
  const proxy: Record<string, string | object> = {
    "/api": {
      target: "http://127.0.0.1:8000",
      changeOrigin: true,
    },
  };
  if (notebookBase) {
    const prefixedApi = `${notebookBase}api`.replace(/\/+/g, "/");
    proxy[prefixedApi] = {
      target: "http://127.0.0.1:8000",
      changeOrigin: true,
      rewrite: (path: string) => {
        const match = path.match(/\/api(\/.*)?$/);
        return match ? `/api${match[1] ?? ""}` : path;
      },
    };
  }

  return {
    plugins: [react()],
    base,
    server: {
      port: DEV_PORT,
      strictPort: true,
      allowedHosts: [".datarobot.com", "localhost"],
      host: true,
      proxy,
    },
  };
});
