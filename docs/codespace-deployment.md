# Deploying to DataRobot Codespace

The app runs as a single FastAPI service on one port. The React frontend is
built to static files and served by the backend, so no separate Node process
is needed in production.

---

## 1. Build the frontend

Run this once before uploading (or as the first step in your Codespace startup
script):

```bash
cd frontend
npm install
npm run build        # produces frontend/dist/
cd ..
```

---

## 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

If `aiofiles` is not already in `requirements.txt`, add it — FastAPI's
`StaticFiles` requires it:

```bash
pip install aiofiles
```

---

## 3. Set environment variables

In the Codespace environment settings, add:

| Variable | Value |
|---|---|
| `DATAROBOT_API_TOKEN` | Your DataRobot API token |
| `DATAROBOT_ENDPOINT` | `https://app.eu.datarobot.com/api/v2` |
| `DR_GATEWAY_MODEL` | `azure/gpt-5-2025-08-07` (or any Chat model ID) |

All other variables (SQL export, alternative LLM providers) are optional.

---

## 4. Start the app

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8080
```

Use whatever port the Codespace exposes (commonly `8080`). The `--reload` flag
is not needed in production.

On first start the PE pipeline runs (~2–5 min). Subsequent starts are fast
— the prediction dataset ID is cached in `backend/.prediction_dataset_cache.json`.

---

## 5. Verify

Open the Codespace URL in a browser. You should see the app UI.
API health check: `GET /api/health` → `{"status": "ok", "rows_loaded": 6668, ...}`

---

## Local dev (unchanged)

```bash
# Terminal 1 — backend
cd backend && uvicorn main:app --reload --port 8000

# Terminal 2 — frontend with hot reload
cd frontend && npm run dev
```

The Vite dev server proxies `/api/*` to `localhost:8000` automatically.
`VITE_API_URL` is no longer needed for local dev.
