"""
Jaeger Backend - FastAPI Application Entry Point

Serves the Jaeger UI and provides:
1. OTLP/HTTP trace ingestion endpoint (POST /v1/traces)
2. Jaeger Query API for the UI (/api/*)
3. Static file serving for the React UI
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from database import init_db
from otlp_service import router as otlp_router
from query_service import router as query_router

DIST_DIR = Path(__file__).parent / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown."""
    # Startup: Initialize database
    init_db()
    print("Database initialized")
    yield
    # Shutdown: (cleanup if needed in future)


app = FastAPI(
    title="Jaeger Tracing Backend",
    description="OpenTelemetry OTLP collector with Jaeger UI",
    version="0.1.0",
    lifespan=lifespan,
)

# OTLP ingestion endpoint - POST /v1/traces
app.include_router(otlp_router)

# Jaeger Query API - /api/*
app.include_router(query_router, prefix="/api")


# UI Configuration endpoint
@app.get("/api/config")
def get_ui_config():
    """
    Return UI configuration for jaeger-ui.

    The UI calls this endpoint on startup to configure features.
    """
    return {
        "archiveEnabled": False,
        "dependencies": {"menuEnabled": True},
        "menu": [],
        "search": {"maxLookback": {"label": "7 Days", "value": "7d"}},
        "tracking": {"gaID": None},
    }


# Health check endpoint
@app.get("/api/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}


# Mount static files (JS, CSS, assets) - must come before SPA fallback
if DIST_DIR.exists():
    app.mount("/static", StaticFiles(directory=DIST_DIR / "static"), name="static")
else:
    print(f"Warning: dist directory not found at {DIST_DIR}")


# SPA fallback - serve index.html for all unmatched routes
# This must be the last route registered
@app.get("/{full_path:path}")
async def serve_spa(full_path: str, request: Request):
    """
    Serve the SPA for any non-API route.

    This allows the React app to handle client-side routing.
    Injects the correct base URL for Posit Connect content paths.
    """
    index_path = DIST_DIR / "index.html"
    if not index_path.exists():
        return {"error": "UI not found", "path": str(DIST_DIR)}

    # Read the HTML file
    html_content = index_path.read_text()

    # Determine the base URL - use the root path from the request
    # In Posit Connect, this will be something like /content/{guid}/
    # Use "or" to handle empty string case (default for localhost)
    base_url = request.scope.get("root_path", "/") or "/"
    if base_url and not base_url.endswith("/"):
        base_url += "/"

    # Replace the base href in the HTML
    html_content = html_content.replace(
        '<base href="/" data-inject-target="BASE_URL" />',
        f'<base href="{base_url}" data-inject-target="BASE_URL" />'
    )

    return Response(content=html_content, media_type="text/html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
