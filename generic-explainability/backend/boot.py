"""
Fast ASGI entry for DataRobot Custom Application deploy probes.

Uvicorn loads this module first (not main.py) so /health responds in seconds
while pandas, datarobot, and batch-scoring imports run in the background.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from starlette.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_main_app: Any = None
_load_error: str | None = None


def _add_datarobot_middleware(application: FastAPI) -> None:
    try:
        from datarobot_asgi_middleware import DataRobotASGIMiddleware

        application.add_middleware(DataRobotASGIMiddleware, health_endpoint="/health")
    except ImportError:
        logger.warning("datarobot-asgi-middleware not installed — proxy paths may not work")


async def _preload_main() -> None:
    """Import the full API in the background after the probe server is listening."""
    global _main_app, _load_error
    try:
        logger.info("Loading explainability API in background…")
        from main import app as main_app, kickoff_bootstrap

        kickoff_bootstrap()
        _main_app = main_app
        logger.info("Explainability API loaded")
    except Exception as exc:
        _load_error = str(exc)
        logger.exception("Failed to load explainability API")


class _LazyMainASGI:
    """Forward traffic to main.app once background import completes."""

    async def __call__(self, scope, receive, send):
        global _main_app, _load_error
        if scope.get("path") == "/health":
            response = JSONResponse({"status": "healthy"})
            await response(scope, receive, send)
            return
        if _main_app is None:
            if _load_error:
                response = JSONResponse(
                    {"detail": f"API failed to load: {_load_error}"},
                    status_code=503,
                )
                await response(scope, receive, send)
                return
            for _ in range(600):
                if _main_app is not None:
                    break
                if _load_error:
                    response = JSONResponse(
                        {"detail": f"API failed to load: {_load_error}"},
                        status_code=503,
                    )
                    await response(scope, receive, send)
                    return
                await asyncio.sleep(0.5)
            if _main_app is None:
                response = JSONResponse(
                    {"detail": "API is still loading, please retry shortly."},
                    status_code=503,
                )
                await response(scope, receive, send)
                return
        await _main_app(scope, receive, send)


@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("Probe server listening — loading full API in background")
    asyncio.create_task(_preload_main())
    yield


app = FastAPI(title="Explainability API", lifespan=lifespan)
_add_datarobot_middleware(app)


@app.get("/health", include_in_schema=False)
def platform_health():
    return {"status": "healthy"}


app.mount("/", _LazyMainASGI())
