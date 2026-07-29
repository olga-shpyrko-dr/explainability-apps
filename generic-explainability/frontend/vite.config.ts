import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const DEV_PORT = Number(process.env.VITE_DEV_PORT || process.env.PORT || 5173);

function datarobotOrigin(): string {
  try {
    return new URL(process.env.DATAROBOT_ENDPOINT || "https://app.datarobot.com/api/v2").origin;
  } catch {
    return "https://app.datarobot.com";
  }
}

/**
 * When running in a DataRobot Codespace, the UI is accessed via
 * /notebook-sessions/{id}/ports/{port}/. Vite must use that as `base`
 * or module URLs resolve to the domain root (404 on /src/App.tsx).
 */
function notebookDevBase(): string | null {
  const explicit = process.env.VITE_DEV_BASE?.trim();
  if (explicit) {
    return explicit.endsWith("/") ? explicit : `${explicit}/`;
  }

  const notebookId =
    process.env.NOTEBOOK_ID ||
    process.env.DATAROBOT_NOTEBOOK_ID ||
    process.env.NOTEBOOK_SESSION_ID;
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

  if (command === "serve") {
    console.log(
      `[vite] base=${base} NOTEBOOK_ID=${process.env.NOTEBOOK_ID ?? "unset"} ` +
        `(set NOTEBOOK_ID or VITE_DEV_BASE if modules 404 at domain root)`
    );
  }

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

  const server: Record<string, unknown> = {
    port: DEV_PORT,
    strictPort: true,
    allowedHosts: [".datarobot.com", "localhost"],
    host: true,
    proxy,
  };
  if (notebookBase) {
  // Ensures @vite/client and module imports use the proxied path, not domain root.
    server.origin = `${datarobotOrigin()}${notebookBase.replace(/\/$/, "")}`;
  }

  return {
    plugins: [react()],
    base,
    server,
  };
});
