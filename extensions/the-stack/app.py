from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from posit.connect import Client
from posit.connect.errors import ClientError

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Content Observability")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ClientError)
async def handle_client_error(request: Request, exc: ClientError):
    if exc.error_code == 212:
        return JSONResponse(
            status_code=400,
            content={"error_code": 212, "setup_required": True},
        )
    return JSONResponse(
        status_code=exc.http_status,
        content={"error_code": exc.error_code, "error_message": exc.error_message},
    )


def _client(request: Request) -> Client:
    client = Client()
    user_session_token = request.headers.get("Posit-Connect-User-Session-Token")
    if user_session_token:
        client = client.with_user_session_token(user_session_token)
    return client


@app.get("/api/content")
def list_content(request: Request):
    with _client(request) as client:
        items = client.content.find()
        return [
            {
                "guid": item["guid"],
                "name": item["name"],
                "title": item.get("title", ""),
                "app_mode": item.get("app_mode", ""),
            }
            for item in items
        ]


@app.get("/api/content/{guid}")
def get_content(guid: str, request: Request):
    with _client(request) as client:
        item = client.content.get(guid)
        return {
            "guid": item["guid"],
            "name": item["name"],
            "title": item.get("title", ""),
            "app_mode": item.get("app_mode", ""),
        }


@app.get("/api/traces")
def get_traces(
    request: Request,
    guid: str = Query(...),
    from_time: Optional[str] = Query(None, alias="from"),
    to_time: Optional[str] = Query(None, alias="to"),
    job_key: Optional[str] = None,
    trace_id: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0,
):
    with _client(request) as client:
        params: dict = {"limit": limit, "offset": offset}
        if from_time:
            params["from"] = from_time
        if to_time:
            params["to"] = to_time
        if job_key:
            params["job_key"] = job_key
        if trace_id:
            params["trace_id"] = trace_id

        resp = client.get(f"v1/content/{guid}/traces", params=params)
        total = int(resp.headers.get("X-Total-Count", "0"))
        rows = []
        for line in resp.text.strip().split("\n"):
            if line:
                rows.append(json.loads(line))
        return {"rows": rows, "total": total}


@app.get("/api/logs")
def get_logs(
    request: Request,
    guid: str = Query(...),
    from_time: Optional[str] = Query(None, alias="from"),
    to_time: Optional[str] = Query(None, alias="to"),
    job_key: Optional[str] = None,
    severity: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0,
):
    with _client(request) as client:
        params: dict = {"limit": limit, "offset": offset}
        if from_time:
            params["from"] = from_time
        if to_time:
            params["to"] = to_time
        if job_key:
            params["job_key"] = job_key
        if severity:
            params["severity"] = severity
        if search:
            params["search"] = search

        resp = client.get(f"v1/content/{guid}/logs", params=params)
        return resp.json()


@app.get("/api/metrics")
def get_metrics(
    request: Request,
    guid: str = Query(...),
    from_time: Optional[str] = Query(None, alias="from"),
    to_time: Optional[str] = Query(None, alias="to"),
    job_key: Optional[str] = None,
):
    with _client(request) as client:
        params: dict = {}
        if from_time:
            params["from"] = from_time
        if to_time:
            params["to"] = to_time
        if job_key:
            params["job_key"] = job_key

        resp = client.get(f"v1/content/{guid}/metrics", params=params)
        return resp.json()


@app.get("/api/logs/tail")
def tail_logs(
    request: Request,
    guid: str = Query(...),
    from_time: Optional[str] = Query(None, alias="from"),
    to_time: Optional[str] = Query(None, alias="to"),
    job_key: Optional[str] = None,
    severity: Optional[str] = None,
    search: Optional[str] = None,
):
    def event_stream():
        with _client(request) as client:
            params: dict = {}
            if from_time:
                params["from"] = from_time
            if to_time:
                params["to"] = to_time
            if job_key:
                params["job_key"] = job_key
            if severity:
                params["severity"] = severity
            if search:
                params["search"] = search

            resp = client.get(
                f"v1/content/{guid}/logs/tail",
                params=params,
                stream=True,
            )
            for chunk in resp.iter_content(chunk_size=4096):
                yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file = STATIC_DIR / full_path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(STATIC_DIR / "index.html")
