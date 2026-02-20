"""
Jaeger UI Adapter for Posit Connect Traces

This FastAPI application acts as a proxy between Jaeger UI and Connect's traces endpoint,
translating the API formats to make them compatible.
"""

import os
import json
import posixpath
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from urllib.parse import urljoin
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from posit import connect

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Jaeger UI index.html served as processable template to populate BASE_URL
templates = Jinja2Templates(directory="templates")

# Detect runtime environment
POSIT_PRODUCT = os.getenv("POSIT_PRODUCT", "")
IS_RUNNING_IN_CONNECT = POSIT_PRODUCT == "CONNECT"

# Required configuration from environment variables to load traces
# These are always required regardless of where the app is running
INSTRUMENTED_CONTENT_GUID = os.getenv("INSTRUMENTED_CONTENT_GUID", "")
INSTRUMENTED_JOB_KEY = os.getenv("INSTRUMENTED_JOB_KEY", "")

# Connect server configuration
# When running inside Connect (POSIT_PRODUCT=CONNECT), these are provided automatically
# When running outside Connect, these must be provided by the user
CONNECT_SERVER = os.getenv("CONNECT_SERVER", "")
CONNECT_API_KEY = os.getenv("CONNECT_API_KEY", "")
CONNECT_CONTENT_GUID = os.getenv("CONNECT_CONTENT_GUID", "")

# Constants
MICROSECONDS_PER_SECOND = 1_000_000
DEFAULT_TRACE_LIMIT = 1000
MAX_TRACE_LIMIT = 5000

# Global Connect client - initialized at startup
connect_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown"""
    # Startup: Initialize the Connect client
    global connect_client
    logger.info(f"Starting application (Running in Connect: {IS_RUNNING_IN_CONNECT})")

    # Validate configuration based on runtime environment
    if not IS_RUNNING_IN_CONNECT:
        # When running outside Connect, we need these variables
        if not CONNECT_SERVER or not CONNECT_API_KEY:
            logger.warning(
                "Running outside Connect but CONNECT_SERVER or CONNECT_API_KEY not set. "
                "The application will start but won't be able to fetch traces. "
                "Configuration instructions will be shown to the user."
            )

    # Connect client automatically picks up CONNECT_SERVER and CONNECT_API_KEY from environment
    # Try to initialize, but allow app to start even if configuration is incomplete
    logger.info("Initializing Connect client")
    try:
        connect_client = connect.Client()
        logger.info("Connect client initialized successfully")
    except ValueError as e:
        logger.warning(f"Failed to initialize Connect client: {e}")
        logger.warning("Application will start but configuration is required to fetch traces")
        connect_client = None

    logger.info("Application startup complete")

    yield

    # Shutdown: Clean up resources if needed
    logger.info("Shutting down application")
    connect_client = None


app = FastAPI(
    title="Connect Traces Viewer",
    description="Jaeger UI adapter for Posit Connect job traces",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SpanData(BaseModel):
    """Represents a span in OpenTelemetry format"""
    trace_id: str
    span_id: str
    name: str
    start_time_unix_nano: str
    end_time_unix_nano: Optional[str] = None
    parent_span_id: Optional[str] = None
    kind: Optional[int] = None
    status: Optional[Dict[str, Any]] = None


class JaegerTrace(BaseModel):
    """Jaeger trace format"""
    traceID: str
    spans: List[Dict[str, Any]]
    processes: Dict[str, Any]
    warnings: Optional[List[str]] = None


class LegacyTracesResponse(BaseModel):
    """Response model for legacy /api/traces endpoint"""
    data: List[JaegerTrace]


class ServiceResponse(BaseModel):
    """Response model for /api/v3/services endpoint"""
    services: List[str]


class OperationInfo(BaseModel):
    """Information about an operation"""
    name: str
    spanKind: str = "unspecified"


class OperationsResponse(BaseModel):
    """Response model for /api/v3/operations endpoint"""
    operations: List[OperationInfo]


class OTLPTracesResponse(BaseModel):
    """Response model for /api/v3/traces endpoint"""
    result: Dict[str, Any] = Field(description="Contains resourceSpans array")


class TraceResponse(BaseModel):
    """Response model for /api/v3/traces/{trace_id} endpoint"""
    result: Dict[str, Any] = Field(description="Contains resourceSpans for a single trace")


class DependenciesResponse(BaseModel):
    """Response model for /api/v3/dependencies endpoint"""
    result: Dict[str, List[Any]] = Field(default={"dependencies": []})


def fetch_traces_from_connect(
    trace_id: Optional[str] = None,
    limit: int = DEFAULT_TRACE_LIMIT,
    offset: int = 0,
    start_time_min: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], int, int]:
    """
    Fetch traces from Connect's traces endpoint.

    Args:
        trace_id: Optional trace ID to filter by
        limit: Maximum number of traces to return
        offset: Number of traces to skip
        start_time_min: Minimum start time in RFC3339 format

    Returns:
        tuple of (traces, total_count, file_size)
    """
    if not INSTRUMENTED_CONTENT_GUID or not INSTRUMENTED_JOB_KEY:
        logger.error("Missing configuration: INSTRUMENTED_CONTENT_GUID or INSTRUMENTED_JOB_KEY")
        raise HTTPException(
            status_code=500,
            detail="Missing configuration. Set INSTRUMENTED_CONTENT_GUID, and INSTRUMENTED_JOB_KEY environment variables."
        )

    if not connect_client:
        logger.error("Connect client not initialized")
        raise HTTPException(
            status_code=500,
            detail="Connect client not initialized. Application may not have started correctly."
        )
    path = f"v1/content/{INSTRUMENTED_CONTENT_GUID}/jobs/{INSTRUMENTED_JOB_KEY}/traces"
    params = {
        "limit": min(limit, MAX_TRACE_LIMIT),
        "offset": max(0, offset),
    }

    if trace_id:
        params["trace_id"] = trace_id

    if start_time_min:
        # Convert RFC3339 to Unix timestamp if needed
        try:
            dt = datetime.fromisoformat(start_time_min.replace('Z', '+00:00'))
            params["since"] = str(int(dt.timestamp()))
        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to convert start_time_min '{start_time_min}': {e}")

    try:
        logger.info(f"Fetching traces: trace_id={trace_id}, limit={params['limit']}, offset={params['offset']}")
        with connect_client.get(path, params=params, stream=True) as response:
            response.raise_for_status()

            # Get headers
            total_count = int(response.headers.get("X-Total-Count", "0"))
            file_size = int(response.headers.get("X-Trace-File-Size", "0"))

            # Read the response content
            # The posit.connect library uses requests under the hood
            text = response.text.strip()
            logger.info(f"Fetched traces successfully: total_count={total_count}, file_size={file_size}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch traces from Connect: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch traces from Connect: {str(e)}"
        )

    # Parse NDJSON response
    traces = []
    skipped_lines = 0
    if text:
        for line_num, line in enumerate(text.split('\n'), 1):
            line = line.strip()
            if line:
                try:
                    traces.append(json.loads(line))
                except json.JSONDecodeError as e:
                    # Log but continue - partial lines can happen with streaming
                    # This is expected for incomplete lines at stream boundaries
                    logger.debug(f"Skipped malformed JSON line {line_num}: {e}")
                    skipped_lines += 1
                    continue

    if skipped_lines > 0:
        logger.warning(f"Skipped {skipped_lines} malformed lines while parsing traces")

    logger.info(f"Parsed {len(traces)} traces successfully")
    return traces, total_count, file_size


def convert_hex_to_base64(hex_string: str) -> str:
    """Convert hex trace/span ID to base64 for Jaeger UI"""
    try:
        bytes_data = bytes.fromhex(hex_string)
        import base64
        return base64.b64encode(bytes_data).decode('utf-8')
    except Exception:
        return hex_string


def transform_otlp_to_jaeger_format(otlp_traces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Transform OpenTelemetry traces to Jaeger's expected format.

    The Connect endpoint returns OTLP format, which is what Jaeger v3 uses,
    but we need to ensure proper field naming and structure.
    """
    # Use a dictionary for O(1) trace lookup instead of O(n) list search
    traces_by_id: Dict[str, Dict[str, Any]] = {}

    for otlp_trace in otlp_traces:
        # OTLP format is already compatible, but we need to ensure it's structured correctly
        # and extract individual traces by trace ID

        resource_spans = otlp_trace.get("resourceSpans", [])

        for resource_span in resource_spans:
            scope_spans = resource_span.get("scopeSpans", [])

            for scope_span in scope_spans:
                spans = scope_span.get("spans", [])

                for span in spans:
                    # Group spans by trace ID
                    trace_id = span.get("traceId", "")

                    # Get or create trace object using dictionary lookup
                    if trace_id not in traces_by_id:
                        traces_by_id[trace_id] = {
                            "traceID": trace_id,
                            "spans": [],
                            "processes": {},
                            "warnings": None
                        }

                    trace_obj = traces_by_id[trace_id]

                    # Convert span to Jaeger format
                    process_id = f"p{len(trace_obj['processes'])}"

                    # Add process info (service)
                    if process_id not in trace_obj["processes"]:
                        resource_attrs = resource_span.get("resource", {}).get("attributes", [])
                        service_name = "unknown"
                        tags = []

                        for attr in resource_attrs:
                            key = attr.get("key", "")
                            value = attr.get("value", {})

                            if key == "service.name":
                                service_name = value.get("stringValue", "unknown")

                            # Add as tag
                            tag_value = None
                            if "stringValue" in value:
                                tag_value = value["stringValue"]
                            elif "intValue" in value:
                                tag_value = value["intValue"]
                            elif "boolValue" in value:
                                tag_value = value["boolValue"]

                            if tag_value is not None:
                                tags.append({
                                    "key": key,
                                    "type": "string" if isinstance(tag_value, str) else "int64" if isinstance(tag_value, int) else "bool",
                                    "value": tag_value
                                })

                        trace_obj["processes"][process_id] = {
                            "serviceName": service_name,
                            "tags": tags
                        }

                    # Convert span
                    jaeger_span = {
                        "traceID": trace_id,
                        "spanID": span.get("spanId", ""),
                        "operationName": span.get("name", ""),
                        "processID": process_id,
                        "startTime": int(span.get("startTimeUnixNano", "0")) // 1000,  # Convert to microseconds
                        "duration": 0,
                        "tags": [],
                        "logs": [],
                        "references": []
                    }

                    # Calculate duration
                    if "endTimeUnixNano" in span:
                        start = int(span["startTimeUnixNano"])
                        end = int(span["endTimeUnixNano"])
                        jaeger_span["duration"] = (end - start) // 1000  # Convert to microseconds

                    # Add parent reference if exists
                    if "parentSpanId" in span and span["parentSpanId"]:
                        jaeger_span["references"].append({
                            "refType": "CHILD_OF",
                            "traceID": trace_id,
                            "spanID": span["parentSpanId"]
                        })

                    # Add span attributes as tags
                    for attr in span.get("attributes", []):
                        key = attr.get("key", "")
                        value = attr.get("value", {})

                        tag_value = None
                        tag_type = "string"

                        if "stringValue" in value:
                            tag_value = value["stringValue"]
                            tag_type = "string"
                        elif "intValue" in value:
                            tag_value = value["intValue"]
                            tag_type = "int64"
                        elif "boolValue" in value:
                            tag_value = value["boolValue"]
                            tag_type = "bool"

                        if tag_value is not None:
                            jaeger_span["tags"].append({
                                "key": key,
                                "type": tag_type,
                                "value": tag_value
                            })

                    trace_obj["spans"].append(jaeger_span)

    # Convert dictionary values back to list
    return list(traces_by_id.values())

# Jaeger UI is a SPA. Including all routes needed by Jaeger UI to serve the HTML template.
@app.get("/", response_class=HTMLResponse)
@app.get("/search", response_class=HTMLResponse)
@app.get("/trace/{file_path:path}", response_class=HTMLResponse)
@app.get("/dependencies", response_class=HTMLResponse)
@app.get("/monitor", response_class=HTMLResponse)
async def jaeger_index(request: Request):
    # Check if required environment variables are set or if Connect client is not initialized
    missing_config = (not INSTRUMENTED_CONTENT_GUID or
                     not INSTRUMENTED_JOB_KEY or
                     connect_client is None)

    if missing_config:
        # Determine what configuration is missing
        missing_connect_config = (not IS_RUNNING_IN_CONNECT and
                                 (not CONNECT_SERVER or not CONNECT_API_KEY))

        return templates.TemplateResponse(
            request=request,
            name="instructions.html",
            context={
                "has_content_guid": bool(INSTRUMENTED_CONTENT_GUID),
                "has_job_key": bool(INSTRUMENTED_JOB_KEY),
                "is_running_in_connect": IS_RUNNING_IN_CONNECT,
                "has_connect_server": bool(CONNECT_SERVER),
                "has_connect_api_key": bool(CONNECT_API_KEY),
                "missing_connect_config": missing_connect_config,
                "connect_client_initialized": connect_client is not None
            }
        )

    # Set base URLs based on where we're running
    if IS_RUNNING_IN_CONNECT:
        # Inside Connect, use the full path with content GUID
        app_base_url = urljoin(CONNECT_SERVER, posixpath.join("content", CONNECT_CONTENT_GUID))
        assets_base_url = urljoin(app_base_url, "static")
    else:
        # Outside Connect, use simple paths without proxy awareness
        app_base_url = "/"
        assets_base_url = "/static"

    return templates.TemplateResponse(
        request=request, name="index.html", context={"app_base_url": app_base_url, "assets_base_url": assets_base_url}
    )

@app.get("/api/traces", response_model=None)
def search_traces_legacy(
    service: Optional[str] = Query(None, max_length=255),
    operation: Optional[str] = Query(None, max_length=255),
    start: Optional[int] = Query(None, ge=0, description="Start time in microseconds"),
    end: Optional[int] = Query(None, ge=0, description="End time in microseconds"),
    limit: Optional[int] = Query(20, ge=1, le=MAX_TRACE_LIMIT),
    lookback: Optional[str] = Query(None),
    minDuration: Optional[str] = Query(None),
    maxDuration: Optional[str] = Query(None),
):
    """
    Legacy Jaeger API endpoint: GET /api/traces
    This is called by Jaeger UI and expects Jaeger's internal format (not OTLP).
    """
    logger.info(f"Legacy trace search: service={service}, operation={operation}, start={start}, limit={limit}")

    # Convert start time from microseconds to RFC3339 format if provided
    start_time_min = None
    if start:
        try:
            # Convert microseconds to seconds
            start_seconds = start / MICROSECONDS_PER_SECOND
            # Create datetime with UTC timezone and format as RFC3339
            start_dt = datetime.fromtimestamp(start_seconds, tz=timezone.utc)
            start_time_min = start_dt.isoformat()
        except (ValueError, OSError) as e:
            logger.warning(f"Invalid start time {start}: {e}")

    # Fetch traces from Connect
    traces, total_count, file_size = fetch_traces_from_connect(
        limit=limit,
        start_time_min=start_time_min
    )

    # Transform to Jaeger's internal format (with spans array)
    jaeger_traces = transform_otlp_to_jaeger_format(traces)

    # Filter by service/operation if specified
    if service or operation:
        filtered_traces = []
        for trace in jaeger_traces:
            match = False
            for span in trace.get("spans", []):
                process = trace.get("processes", {}).get(span.get("processID", ""), {})
                span_service = process.get("serviceName", "")
                span_operation = span.get("operationName", "")

                if service and service != span_service:
                    continue
                if operation and operation != span_operation:
                    continue

                match = True
                break

            if match:
                filtered_traces.append(trace)

        jaeger_traces = filtered_traces
        logger.info(f"Filtered to {len(jaeger_traces)} traces matching criteria")

    # Legacy API returns {"data": [...]} with Jaeger format traces
    # Include pagination metadata in headers
    response = JSONResponse({
        "data": jaeger_traces
    })
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Trace-File-Size"] = str(file_size)
    return response


@app.get("/api/v3/traces/{trace_id}", response_model=TraceResponse)
def get_trace(trace_id: str):
    """
    Get a specific trace by ID.
    Jaeger UI endpoint: GET /api/v3/traces/{trace_id}
    """
    logger.info(f"Fetching trace by ID: {trace_id}")
    traces, _, _ = fetch_traces_from_connect(trace_id=trace_id, limit=0)

    if not traces:
        logger.warning(f"Trace not found: {trace_id}")
        raise HTTPException(status_code=404, detail="Trace not found")

    # Transform to Jaeger format
    jaeger_traces = transform_otlp_to_jaeger_format(traces)

    if not jaeger_traces:
        logger.warning(f"Trace transformation failed for: {trace_id}")
        raise HTTPException(status_code=404, detail="Trace not found")

    logger.info(f"Successfully retrieved trace: {trace_id}")
    # Return the first matching trace
    return JSONResponse({
        "result": {
            "resourceSpans": traces[0].get("resourceSpans", [])
        }
    })


@app.get("/api/v3/traces", response_model=OTLPTracesResponse)
def search_traces(
    service: Optional[str] = Query(None, max_length=255, description="Service name"),
    operation: Optional[str] = Query(None, max_length=255, description="Operation name"),
    start_time_min: Optional[str] = Query(None, description="Start time minimum (RFC3339)"),
    start_time_max: Optional[str] = Query(None, description="Start time maximum (RFC3339)"),
    num_traces: Optional[int] = Query(100, ge=1, le=MAX_TRACE_LIMIT, description="Number of traces to return"),
):
    """
    Search for traces.
    Jaeger UI endpoint: GET /api/v3/traces

    Returns: Object with data array containing traces
    """
    logger.info(f"V3 trace search: service={service}, operation={operation}, num_traces={num_traces}")

    # Fetch traces from Connect
    traces, total_count, file_size = fetch_traces_from_connect(
        limit=num_traces,
        start_time_min=start_time_min
    )

    # Jaeger API v3 uses OTLP format (OpenTelemetry Protocol)
    # The data from Connect is already in OTLP format, so we just need to wrap it
    # Extract all resourceSpans from all traces
    all_resource_spans = []
    for trace in traces:
        resource_spans = trace.get("resourceSpans", [])

        # Filter by service/operation if specified
        if service or operation:
            filtered_rs = []
            for rs in resource_spans:
                # Check service name in resource attributes
                service_name = None
                for attr in rs.get("resource", {}).get("attributes", []):
                    if attr.get("key") == "service.name":
                        service_name = attr.get("value", {}).get("stringValue")
                        break

                if service and service_name != service:
                    continue

                # If operation filter is set, check spans
                if operation:
                    scope_spans = rs.get("scopeSpans", [])
                    has_matching_operation = False
                    for ss in scope_spans:
                        for span in ss.get("spans", []):
                            if span.get("name") == operation:
                                has_matching_operation = True
                                break
                        if has_matching_operation:
                            break

                    if not has_matching_operation:
                        continue

                filtered_rs.append(rs)

            all_resource_spans.extend(filtered_rs)
        else:
            all_resource_spans.extend(resource_spans)

    logger.info(f"Returning {len(all_resource_spans)} resource spans")

    # Return in Jaeger API v3 format with pagination metadata
    response = JSONResponse({
        "result": {
            "resourceSpans": all_resource_spans
        }
    })
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["X-Trace-File-Size"] = str(file_size)
    return response


@app.get("/api/v3/services", response_model=ServiceResponse)
def get_services():
    """
    Get list of services.
    Jaeger UI endpoint: GET /api/v3/services

    Returns: Array of service names (not wrapped in result object)
    """
    logger.info("Fetching services list")

    # Fetch a sample of traces to extract services
    traces, _, _ = fetch_traces_from_connect(limit=DEFAULT_TRACE_LIMIT)

    services = set()
    for trace in traces:
        for resource_span in trace.get("resourceSpans", []):
            for attr in resource_span.get("resource", {}).get("attributes", []):
                if attr.get("key") == "service.name":
                    service_name = attr.get("value", {}).get("stringValue")
                    if service_name:
                        services.add(service_name)

    services_list = sorted(list(services))
    logger.info(f"Found {len(services_list)} services")

    # Jaeger UI expects {"services": [...]} format
    return JSONResponse({
        "services": services_list
    })


@app.get("/api/v3/operations", response_model=OperationsResponse)
def get_operations(
    service: str = Query(..., max_length=255, description="Service name")
):
    """
    Get list of operations for a service.
    Jaeger UI endpoint: GET /api/v3/operations

    Returns: Array of operation objects (not wrapped in result object)
    """
    logger.info(f"Fetching operations for service: {service}")

    # Fetch traces and extract operations for the service
    traces, _, _ = fetch_traces_from_connect(limit=DEFAULT_TRACE_LIMIT)

    operations = set()
    for trace in traces:
        for resource_span in trace.get("resourceSpans", []):
            # Check if this resource belongs to the requested service
            service_name = None
            for attr in resource_span.get("resource", {}).get("attributes", []):
                if attr.get("key") == "service.name":
                    service_name = attr.get("value", {}).get("stringValue")
                    break

            if service_name == service:
                for scope_span in resource_span.get("scopeSpans", []):
                    for span in scope_span.get("spans", []):
                        span_name = span.get("name")
                        if span_name:
                            operations.add(span_name)

    operation_list = [
        {"name": op, "spanKind": "unspecified"} for op in sorted(operations)
    ]

    logger.info(f"Found {len(operation_list)} operations for service: {service}")

    # Jaeger UI expects {"operations": [...]} format
    return JSONResponse({
        "operations": operation_list
    })


@app.get("/api/v3/dependencies", response_model=DependenciesResponse)
def get_dependencies():
    """
    Get service dependencies.
    Jaeger UI endpoint: GET /api/v3/dependencies

    Note: This is a simplified implementation that returns empty dependencies.
    A full implementation would analyze parent-child span relationships.
    """
    logger.info("Fetching dependencies (returning empty)")
    return JSONResponse({
        "result": {
            "dependencies": []
        }
    })


# @app.get("/api/config")
# async def get_config():
#     """
#     Return Jaeger UI configuration.
#     This endpoint is called by Jaeger UI on startup.
#     """
#     return JSONResponse({
#         "data": {
#             "archiveEnabled": False,
#             "dependencies": {
#                 "menuEnabled": False
#             },
#             "search": {
#                 "maxLookback": {
#                     "label": "7 Days",
#                     "value": "604800s"
#                 },
#                 "maxLimit": 1500
#             },
#             "tracking": {
#                 "gaID": None,
#                 "trackErrors": False
#             }
#         }
#     })


# @app.get("/health")
# async def health():
#     """Health check endpoint"""
#     return {"status": "healthy"}


# @app.get("/api/status")
# async def status():
#     """API status and configuration endpoint"""
#     return JSONResponse({
#         "status": "ok",
#         "connect_url": CONNECT_SERVER,
#         "content_guid": CONNECT_CONTENT_GUID,
#         "job_key": INSTRUMENTED_JOB_KEY,
#         "jaeger_ui_available": os.path.exists("jaeger-ui"),
#         "endpoints": [
#             "/health",
#             "/api/status",
#             "/api/config",
#             "/api/v3/traces",
#             "/api/v3/traces/{trace_id}",
#             "/api/v3/services",
#             "/api/v3/operations",
#             "/api/v3/dependencies"
#         ]
#     })

# Mount Jaeger UI static assets
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
