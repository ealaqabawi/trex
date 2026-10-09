"""TRAX dashboard API — FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import os

from api.routes import (
    health,
    overview,
    market,
    options,
    scanner as scanner_route,
    intelligence,
    strategy,
    agents,
    risk,
    telegram,
    settings as settings_route,
)
from memory.db import init_db

APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="TRAX Financial Intelligence",
    version=APP_VERSION,
    description=(
        "Local-first AI financial intelligence and 0DTE options research "
        "platform. Research/paper modes only; live execution is a hard "
        "disabled default."
    ),
    lifespan=lifespan,
)

# The dashboard dev server runs on 5173; prod bundles are served off the
# same origin. CORS stays wide only in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# Each router mounts under /api/v1/<section>.
app.include_router(health.router, prefix="/api/v1/health", tags=["health"])
app.include_router(overview.router, prefix="/api/v1/overview", tags=["overview"])
app.include_router(market.router, prefix="/api/v1/market", tags=["market"])
app.include_router(options.router, prefix="/api/v1/options", tags=["options"])
app.include_router(scanner_route.router, prefix="/api/v1/scanner", tags=["scanner"])
app.include_router(intelligence.router, prefix="/api/v1/intelligence", tags=["intelligence"])
app.include_router(strategy.router, prefix="/api/v1/strategy", tags=["strategy"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(risk.router, prefix="/api/v1/risk", tags=["risk"])
app.include_router(telegram.router, prefix="/api/v1/telegram", tags=["telegram"])
app.include_router(settings_route.router, prefix="/api/v1/settings", tags=["settings"])


# Serve the built frontend when it exists; the dev server owns the UI
# otherwise.
_DIST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "dashboard", "dist")
if os.path.isdir(_DIST_DIR):
    app.mount("/", StaticFiles(directory=_DIST_DIR, html=True), name="dashboard")


@app.exception_handler(Exception)
def _unhandled(_, exc):
    return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})
