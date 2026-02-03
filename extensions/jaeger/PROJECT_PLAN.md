# Jaeger Backend Implementation Plan

A Python backend for jaeger-ui that serves as both the REST API for the Jaeger UI and an OpenTelemetry collector for traces, using SQLite for storage.

## Architecture Overview

```text
┌─────────────────┐     ┌──────────────────────────────────────────────┐
│                 │     │           Python FastAPI Backend             │
│   Jaeger UI     │────▶│                                              │
│   (React)       │     │  ┌─────────────────┐  ┌──────────────────┐   │
│                 │     │  │  Jaeger Query   │  │  OTLP Receiver   │   │
└─────────────────┘     │  │  API /api/*     │  │  POST /v1/traces │   │
                        │  └────────┬────────┘  └────────┬─────────┘   │
                        │           │                    │             │
                        │           │    ┌───────────────┘             │
                        │           │    │                             │
                        │           ▼    ▼                             │
                        │  ┌──────────────────────────────────────┐    │
                        │  │         SQLite Database              │    │
                        │  │  (traces, spans, services)           │    │
                        │  └──────────────────────────────────────┘    │
                        └──────────────────────────────────────────────┘
                                            ▲
                                            │ OTLP/HTTP (POST /v1/traces)
                        ┌───────────────────┴───────────────────┐
                        │     Instrumented Applications         │
                        │   (OpenTelemetry SDK)                 │
                        └───────────────────────────────────────┘
```

### Why OTLP/HTTP Instead of gRPC

The original plan proposed a gRPC server on port 4317. However, this won't work well in Posit Connect:

- Connect controls port allocation and proxying
- Only the HTTP port assigned by Connect is accessible
- A separate gRPC port would require additional network configuration

**Solution:** Use OTLP/HTTP transport instead. OTLP supports three transports:
1. gRPC (port 4317) - Not Connect-friendly
2. HTTP/protobuf (port 4318, path `/v1/traces`) - **Our choice**
3. HTTP/JSON (same as above) - Also supported

OTLP/HTTP uses the same FastAPI server, works through Connect's proxy, and is well-supported by OpenTelemetry SDKs.

## Project Structure

```text
extensions/jaeger/
├── app.py                  # FastAPI application, routes, static files
├── database.py             # SQLAlchemy models + connection management
├── otlp_service.py         # OTLP/HTTP ingestion endpoint
├── query_service.py        # Jaeger Query API endpoints
├── transformers.py         # Data format conversions (OTLP ↔ Jaeger)
├── requirements.txt        # Python dependencies (existing)
├── manifest.json           # Connect extension manifest (existing)
├── dist/                   # Built jaeger-ui static files
└── jaeger-ui/              # Jaeger UI source (for reference)
```

### File Responsibilities

| File | Purpose | Key Classes/Functions |
| ---- | ------- | --------------------- |
| `app.py` | Application entry point. Wires together routes, middleware, static files, lifespan events. | `app`, `lifespan()` |
| `database.py` | Database schema (SQLAlchemy models) and connection management. Single source of truth for data model. | `Trace`, `Span`, `SpanAttribute`, `get_db()`, `init_db()` |
| `otlp_service.py` | Receives OTLP/HTTP trace data, parses protobuf, calls transformers, writes to DB. | `receive_traces()`, `parse_otlp_request()` |
| `query_service.py` | Implements Jaeger Query API. Reads from DB, calls transformers, returns JSON. | `get_services()`, `get_trace()`, `search_traces()` |
| `transformers.py` | Stateless conversion functions between formats. Isolates format complexity. | `otlp_to_db_models()`, `db_models_to_jaeger()`, `parse_duration()` |

## Component Specifications

### 1. Database Layer (`database.py`)

#### SQLite Schema Design

```sql
-- Traces table: stores trace-level metadata
CREATE TABLE traces (
    trace_id TEXT PRIMARY KEY,
    start_time INTEGER NOT NULL,      -- microseconds since epoch
    end_time INTEGER NOT NULL,        -- microseconds since epoch
    duration INTEGER NOT NULL,        -- microseconds
    service_name TEXT NOT NULL,       -- root span's service name
    root_operation TEXT NOT NULL,     -- root span's operation name
    span_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Spans table: stores individual spans
CREATE TABLE spans (
    span_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    parent_span_id TEXT,
    operation_name TEXT NOT NULL,
    service_name TEXT NOT NULL,
    start_time INTEGER NOT NULL,      -- microseconds since epoch
    duration INTEGER NOT NULL,        -- microseconds
    span_kind TEXT,                   -- INTERNAL, SERVER, CLIENT, etc.
    status_code TEXT,                 -- UNSET, OK, ERROR
    status_message TEXT,
    PRIMARY KEY (trace_id, span_id),
    FOREIGN KEY (trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
);

-- Span attributes (tags)
CREATE TABLE span_attributes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    span_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    value_type TEXT DEFAULT 'string', -- string, int, float, bool
    FOREIGN KEY (trace_id, span_id) REFERENCES spans(trace_id, span_id) ON DELETE CASCADE
);

-- Span events (logs)
CREATE TABLE span_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    span_id TEXT NOT NULL,
    timestamp INTEGER NOT NULL,       -- microseconds since epoch
    name TEXT NOT NULL,
    FOREIGN KEY (trace_id, span_id) REFERENCES spans(trace_id, span_id) ON DELETE CASCADE
);

-- Event attributes
CREATE TABLE event_attributes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    FOREIGN KEY (event_id) REFERENCES span_events(id) ON DELETE CASCADE
);

-- Resource attributes (per trace/service)
CREATE TABLE resource_attributes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    service_name TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    FOREIGN KEY (trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
);

-- Services table: for fast service listing
CREATE TABLE services (
    name TEXT PRIMARY KEY,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Operations table: for fast operation listing per service
CREATE TABLE operations (
    service_name TEXT NOT NULL,
    operation_name TEXT NOT NULL,
    span_kind TEXT,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (service_name, operation_name, span_kind),
    FOREIGN KEY (service_name) REFERENCES services(name) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX idx_traces_start_time ON traces(start_time DESC);
CREATE INDEX idx_traces_service ON traces(service_name);
CREATE INDEX idx_spans_service ON spans(service_name);
CREATE INDEX idx_spans_operation ON spans(operation_name);
CREATE INDEX idx_span_attributes_key_value ON span_attributes(key, value);
```

#### SQLAlchemy Models

Implement SQLAlchemy ORM models matching the schema above with appropriate relationships.

### 2. OTLP Receiver (`otlp_service.py`)

Implements OTLP/HTTP trace ingestion endpoint.

#### OTLP/HTTP Protocol

OpenTelemetry SDKs can send traces via HTTP POST to `/v1/traces`:

- **Content-Type**: `application/x-protobuf` (binary) or `application/json`
- **Request Body**: `ExportTraceServiceRequest` protobuf message
- **Response**: `ExportTraceServiceResponse` with partial success info

#### Endpoint Implementation

```python
from fastapi import APIRouter, Request, Response
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

router = APIRouter()

@router.post("/v1/traces")
async def receive_traces(request: Request, db: Session = Depends(get_db)):
    """
    Receive OTLP trace data via HTTP and store in SQLite.

    Supports both protobuf and JSON content types.

    Processing steps:
    1. Parse request body based on Content-Type
    2. Extract ResourceSpans from request
    3. For each resource, extract service name from attributes
    4. For each span, convert timestamps (nanoseconds → microseconds)
    5. Transform to DB models via transformers.otlp_to_db_models()
    6. Batch insert into SQLite
    7. Update services and operations tables
    8. Return ExportTraceServiceResponse
    """
    content_type = request.headers.get("content-type", "")
    body = await request.body()

    if "application/x-protobuf" in content_type:
        otlp_request = ExportTraceServiceRequest()
        otlp_request.ParseFromString(body)
    elif "application/json" in content_type:
        from google.protobuf.json_format import Parse
        otlp_request = Parse(body, ExportTraceServiceRequest())
    else:
        # Default to protobuf
        otlp_request = ExportTraceServiceRequest()
        otlp_request.ParseFromString(body)

    # Process and store traces
    store_traces(db, otlp_request)

    # Return success response
    response = ExportTraceServiceResponse()
    return Response(
        content=response.SerializeToString(),
        media_type="application/x-protobuf"
    )
```

#### Client Configuration

Applications using OpenTelemetry SDK configure the exporter to use HTTP:

```python
# Python SDK example
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

exporter = OTLPSpanExporter(
    endpoint="https://your-connect-server/content/jaeger/v1/traces"
)
```

```bash
# Environment variable configuration
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_ENDPOINT=https://your-connect-server/content/jaeger
```

### 3. Query Service REST API (`query_service.py`)

Implement the Jaeger Query API endpoints that jaeger-ui expects.

#### Required Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/services` | GET | List all services |
| `/api/services/{service}/operations` | GET | List operations for a service |
| `/api/operations` | GET | List operations with filters (service, spanKind) |
| `/api/traces` | GET | Search traces with query parameters |
| `/api/traces/{traceId}` | GET | Get a specific trace by ID |
| `/api/dependencies` | GET | Get service dependencies |

#### Search Query Parameters (`/api/traces`)

| Parameter | Type | Description |
|-----------|------|-------------|
| `service` | string | Service name (required) |
| `operation` | string | Operation name filter |
| `start` | integer | Start time in microseconds |
| `end` | integer | End time in microseconds |
| `limit` | integer | Max traces to return (default 20) |
| `minDuration` | string | Minimum duration (e.g., "1ms", "500us") |
| `maxDuration` | string | Maximum duration |
| `tags` | string | JSON-encoded tag filters |

#### Response Formats

All responses follow the Jaeger API format:

```json
{
  "data": [...],
  "total": 0,
  "limit": 0,
  "offset": 0,
  "errors": null
}
```

**Trace Response Format:**

```json
{
  "data": [{
    "traceID": "abc123",
    "spans": [{
      "traceID": "abc123",
      "spanID": "def456",
      "operationName": "HTTP GET /api/users",
      "references": [],
      "startTime": 1704067200000000,
      "duration": 150000,
      "tags": [{"key": "http.method", "type": "string", "value": "GET"}],
      "logs": [],
      "processID": "p1",
      "warnings": null
    }],
    "processes": {
      "p1": {
        "serviceName": "my-service",
        "tags": [{"key": "host.name", "type": "string", "value": "localhost"}]
      }
    }
  }]
}
```

### 4. Data Transformers (`transformers.py`)

Isolates all format conversion logic. This is critical because three different formats are in play:

1. **OTLP Protobuf** - Wire format from OpenTelemetry SDKs (nanosecond timestamps)
2. **SQLite/SQLAlchemy** - Storage format (microsecond timestamps, normalized tables)
3. **Jaeger JSON** - API response format for jaeger-ui (microsecond timestamps, denormalized)

```python
"""
Stateless transformation functions between trace formats.

Timestamp conventions:
- OTLP: nanoseconds since Unix epoch
- Jaeger/Internal: microseconds since Unix epoch
- Conversion: ns // 1000 = μs
"""

def otlp_to_db_models(
    resource_spans: ResourceSpans,
) -> tuple[list[Trace], list[Span], list[SpanAttribute], ...]:
    """
    Convert OTLP ResourceSpans to SQLAlchemy model instances.

    Handles:
    - Timestamp conversion (ns → μs)
    - Service name extraction from resource attributes
    - Span kind enum mapping
    - Attribute type detection and serialization
    - Event extraction
    """
    pass


def db_models_to_jaeger(
    trace: Trace,
    spans: list[Span],
    attributes: list[SpanAttribute],
    events: list[SpanEvent],
    resources: list[ResourceAttribute],
) -> dict:
    """
    Convert DB models to Jaeger API response format.

    Output format matches what jaeger-ui expects:
    {
        "traceID": "...",
        "spans": [...],
        "processes": {"p1": {...}, ...}
    }

    Handles:
    - Process ID assignment (group spans by service)
    - Reference formatting (CHILD_OF, FOLLOWS_FROM)
    - Tag type annotation (string, int64, float64, bool)
    - Log/event formatting
    """
    pass


def parse_duration(duration_str: str | None) -> int | None:
    """
    Parse duration string to microseconds.

    Examples:
    - "100ms" → 100000
    - "1.5s" → 1500000
    - "500us" → 500
    - "2m" → 120000000
    """
    pass


def format_trace_id(trace_id_bytes: bytes) -> str:
    """Convert 16-byte trace ID to 32-char hex string."""
    return trace_id_bytes.hex()


def format_span_id(span_id_bytes: bytes) -> str:
    """Convert 8-byte span ID to 16-char hex string."""
    return span_id_bytes.hex()
```

### 5. Application Entry Point (`app.py`)

Wires together all components with proper lifecycle management.

```python
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import init_db, cleanup_old_traces
from query_service import router as query_router
from otlp_service import router as otlp_router

DIST_DIR = Path(__file__).parent / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown."""
    # Startup
    init_db()
    yield
    # Shutdown (cleanup if needed)


app = FastAPI(
    title="Jaeger Tracing",
    lifespan=lifespan,
)

# OTLP ingestion endpoint
app.include_router(otlp_router)

# Jaeger Query API
app.include_router(query_router, prefix="/api")

# UI Configuration (inline - simple enough to not need separate file)
@app.get("/api/config")
def get_ui_config():
    """Return UI configuration for jaeger-ui."""
    return {
        "archiveEnabled": False,
        "dependencies": {"menuEnabled": True},
        "menu": [],
        "search": {"maxLookback": {"label": "7 Days", "value": "7d"}},
        "tracking": {"gaID": None},
    }

# Static files (JS, CSS, assets)
app.mount("/static", StaticFiles(directory=DIST_DIR / "static"), name="static")

# SPA fallback - serve index.html for all unmatched routes
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve the SPA for any non-API route."""
    return FileResponse(DIST_DIR / "index.html")
```

## Implementation Tasks

### Phase 1: Foundation

1. **Database Layer** (`database.py`)
   - Define SQLAlchemy models matching the schema
   - Implement `init_db()` for table creation
   - Implement `get_db()` dependency for FastAPI
   - Add indexes for common query patterns

2. **Application Shell** (`app.py`)
   - Set up FastAPI with lifespan
   - Configure static file serving from `dist/`
   - Implement SPA fallback route
   - Add `/api/config` endpoint

### Phase 2: Data Transformers

3. **Transformers** (`transformers.py`)
   - Implement `otlp_to_db_models()` - OTLP protobuf → SQLAlchemy models
   - Implement `db_models_to_jaeger()` - SQLAlchemy models → Jaeger JSON
   - Implement `parse_duration()` - duration string parsing
   - Implement ID formatting helpers

### Phase 3: OTLP Ingestion

4. **OTLP Endpoint** (`otlp_service.py`)
   - Implement `POST /v1/traces` endpoint
   - Handle both protobuf and JSON content types
   - Parse `ExportTraceServiceRequest` message
   - Call transformers and persist to database
   - Update services/operations tables
   - Return `ExportTraceServiceResponse`

### Phase 4: Query API

5. **Service & Operation Endpoints** (`query_service.py`)
   - `GET /api/services` - list all services
   - `GET /api/services/{service}/operations` - operations for a service
   - `GET /api/operations` - operations with filters

6. **Trace Endpoints** (`query_service.py`)
   - `GET /api/traces/{traceId}` - single trace retrieval
   - `GET /api/traces` - search with filters (service, operation, time range, duration, tags)

7. **Dependencies Endpoint** (`query_service.py`)
   - `GET /api/dependencies` - service dependency graph (computed from span references)

### Phase 5: Production Readiness

8. **Data Retention**
   - Implement `cleanup_old_traces()` for TTL-based cleanup
   - Add startup task or scheduled cleanup

9. **Error Handling**
   - Consistent error response format
   - Validation for query parameters
   - Graceful handling of malformed OTLP data

10. **Testing**
    - Unit tests for transformers
    - Integration tests for API endpoints
    - End-to-end test: send OTLP → verify in UI

## Dependencies

Already specified in `requirements.txt`:

```text
fastapi>=0.115.0          # Web framework
uvicorn[standard]>=0.32.0 # ASGI server
pydantic>=2.9.0           # Data validation
sqlalchemy>=2.0.0         # ORM for SQLite
grpcio>=1.60.0            # Required by opentelemetry-proto
grpcio-tools>=1.60.0      # Required by opentelemetry-proto
protobuf>=4.25.0          # Protobuf parsing for OTLP
opentelemetry-proto>=1.27.0 # OTLP message definitions
posit-sdk>=0.6.0          # Posit Connect integration
```

Note: `grpcio` and `grpcio-tools` are dependencies of `opentelemetry-proto` for protobuf handling, not for running a gRPC server.

## Configuration

Environment variables for runtime configuration:

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `JAEGER_DB_PATH` | `./jaeger.db` | SQLite database file path |
| `MAX_TRACES` | `10000` | Max traces to retain (cleanup threshold) |
| `TRACE_TTL_HOURS` | `168` | Trace retention period (7 days) |

## Data Flow Summary

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                           INGESTION PATH                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  OTel SDK                POST /v1/traces              transformers.py   │
│  ────────►  ExportTraceServiceRequest  ────────►  otlp_to_db_models()  │
│             (protobuf, nanoseconds)                       │             │
│                                                           ▼             │
│                                                    SQLAlchemy models    │
│                                                    (microseconds)       │
│                                                           │             │
│                                                           ▼             │
│                                                       SQLite DB         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                            QUERY PATH                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Jaeger UI             GET /api/traces/*             transformers.py    │
│  ◄────────  Jaeger JSON response  ◄────────  db_models_to_jaeger()     │
│             (microseconds)                            ▲                 │
│                                                       │                 │
│                                               SQLAlchemy models         │
│                                               (microseconds)            │
│                                                       ▲                 │
│                                                       │                 │
│                                                   SQLite DB             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

1. **OTLP/HTTP over gRPC** - Works within Connect's HTTP proxy model
2. **Single SQLite file** - Simple deployment, adequate for moderate trace volumes
3. **Separate transformers module** - Isolates format complexity, improves testability
4. **Microsecond timestamps internally** - Matches Jaeger format, avoids repeated conversion
5. **Flat file structure** - Appropriate for this scope; package structure would be overkill

## Notes

- All timestamps in Jaeger format are in **microseconds** (not milliseconds or nanoseconds)
- OTLP uses **nanoseconds** - conversion happens in `otlp_to_db_models()`
- SQLite works well for single-instance deployments; not suitable for high-volume production
- Trace IDs are 32 hex chars (16 bytes), span IDs are 16 hex chars (8 bytes)
