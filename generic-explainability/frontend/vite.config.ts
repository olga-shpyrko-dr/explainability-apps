import { defineConfig, type UserConfig } from "vite";
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
 * /notebook-sessions/{id}/ports/{port}/. Vite dev must use that as `base`
 * or module URLs resolve to the domain root (404 on /src/App.tsx).
 *
 * `vite preview` does NOT need this — it serves the built dist/ with base "./".
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

function buildApiProxy(notebookBase: string | null): UserConfig["server"] extends infer S
  ? S extends { proxy?: infer P }
    ? P
    : Record<string, string | object>
  : Record<string, string | object> {
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
  return proxy;
}

const listenOptions = {
  port: DEV_PORT,
  strictPort: true,
  allowedHosts: [".datarobot.com", "localhost"] as const,
  host: true as const,
};

export default defineConfig(({ command }) => {
  const notebookBase = command === "serve" ? notebookDevBase() : null;
  const base = command === "build" || command === "preview" ? "./" : (notebookBase ?? "/");
  const proxy = buildApiProxy(notebookBase);

  if (command === "serve") {
    console.log(
      `[vite] base=${base} NOTEBOOK_ID=${process.env.NOTEBOOK_ID ?? "unset"} ` +
        `(use 'npm run preview' in Codespaces if modules 404 at domain root)`
    );
  }

  const server: Record<string, unknown> = {
    ...listenOptions,
    proxy,
  };
  if (notebookBase) {
    server.origin = `${datarobotOrigin()}${notebookBase.replace(/\/$/, "")}`;
  }

  return {
    plugins: [react()],
    base,
    server,
    // vite preview — recommended for Codespace testing (serves dist/, no /src/ requests).
    // Requires backend on :8000 for /api proxy.
    preview: {
      ...listenOptions,
      proxy,
    },
  };
});
