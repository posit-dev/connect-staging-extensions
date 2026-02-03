"""
Jaeger Query API endpoints for the UI.

Implements the REST API that jaeger-ui expects.
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from database import (
    Operation,
    ResourceAttribute,
    Service,
    Span,
    SpanAttribute,
    SpanEvent,
    Trace,
    get_db,
)
from transformers import db_models_to_jaeger, parse_duration

router = APIRouter()


def _api_response(data, total=None, limit=0, offset=0, errors=None):
    """Standard Jaeger API response format."""
    if total is None:
        total = len(data) if isinstance(data, list) else 0
    return {
        "data": data,
        "total": total,
        "limit": limit,
        "offset": offset,
        "errors": errors,
    }


@router.get("/services")
def get_services(db: Session = Depends(get_db)):
    """
    List all services.

    Returns: {"data": ["service1", "service2"], ...}
    """
    services = db.query(Service.name).order_by(Service.last_seen.desc()).all()
    service_names = [s.name for s in services]
    return _api_response(service_names)


@router.get("/services/{service}/operations")
def get_service_operations(service: str, db: Session = Depends(get_db)):
    """
    List operations for a specific service.

    Returns: {"data": ["GET /users", "POST /login"], ...}
    """
    operations = (
        db.query(Operation.operation_name)
        .filter(Operation.service_name == service)
        .distinct()
        .order_by(Operation.operation_name)
        .all()
    )
    operation_names = [op.operation_name for op in operations]
    return _api_response(operation_names)


@router.get("/operations")
def get_operations(
    service: Optional[str] = Query(None),
    spanKind: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    List operations with optional filters.

    Query params:
    - service: filter by service name
    - spanKind: filter by span kind (server, client, etc.)

    Returns: {"data": [{"name": "GET /users", "spanKind": "server"}], ...}
    """
    query = db.query(Operation)

    if service:
        query = query.filter(Operation.service_name == service)

    if spanKind:
        query = query.filter(Operation.span_kind == spanKind)

    operations = query.order_by(Operation.operation_name).all()

    data = [
        {
            "name": op.operation_name,
            "spanKind": op.span_kind,
        }
        for op in operations
    ]

    return _api_response(data)


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str, db: Session = Depends(get_db)):
    """
    Get a specific trace by ID.

    Returns: {"data": [<trace in Jaeger format>], ...}
    """
    # Query trace
    trace = db.query(Trace).filter(Trace.trace_id == trace_id).first()
    if not trace:
        return _api_response([], errors=[{"code": 404, "msg": "Trace not found"}])

    # Query all spans for this trace
    spans = db.query(Span).filter(Span.trace_id == trace_id).all()

    # Query span attributes
    span_attributes = db.query(SpanAttribute).filter(SpanAttribute.trace_id == trace_id).all()

    # Query span events
    span_events = db.query(SpanEvent).filter(SpanEvent.trace_id == trace_id).all()

    # Query resource attributes
    resource_attributes = db.query(ResourceAttribute).filter(ResourceAttribute.trace_id == trace_id).all()

    # Transform to Jaeger format
    jaeger_trace = db_models_to_jaeger(trace, spans, span_attributes, span_events, resource_attributes)

    return _api_response([jaeger_trace])


@router.get("/traces")
def search_traces(
    service: str = Query(..., description="Service name (required)"),
    operation: Optional[str] = Query(None, description="Operation name filter"),
    start: Optional[int] = Query(None, description="Start time in microseconds"),
    end: Optional[int] = Query(None, description="End time in microseconds"),
    limit: int = Query(20, description="Max traces to return (max 100)", le=100),
    minDuration: Optional[str] = Query(None, description="Minimum duration (e.g., '100ms')"),
    maxDuration: Optional[str] = Query(None, description="Maximum duration (e.g., '5s')"),
    tags: Optional[str] = Query(None, description="JSON-encoded tag filters"),
    db: Session = Depends(get_db),
):
    """
    Search traces with filters.

    Query params:
    - service: service name (required)
    - operation: operation name filter
    - start: start time in microseconds
    - end: end time in microseconds
    - limit: max traces to return (default 20)
    - minDuration: minimum duration (e.g., "100ms", "1s")
    - maxDuration: maximum duration
    - tags: JSON-encoded tag filters (e.g., '{"http.status_code":"200"}')

    Returns: {"data": [<traces in Jaeger format>], ...}
    """
    # Build query
    query = db.query(Trace).filter(Trace.service_name == service)

    # Filter by operation
    if operation:
        query = query.filter(Trace.root_operation == operation)

    # Filter by time range
    if start:
        query = query.filter(Trace.start_time >= start)
    if end:
        query = query.filter(Trace.end_time <= end)

    # Filter by duration
    if minDuration:
        min_duration_us = parse_duration(minDuration)
        if min_duration_us:
            query = query.filter(Trace.duration >= min_duration_us)

    if maxDuration:
        max_duration_us = parse_duration(maxDuration)
        if max_duration_us:
            query = query.filter(Trace.duration <= max_duration_us)

    # Filter by tags (if provided)
    if tags:
        try:
            tags_dict = json.loads(tags)
            # For each tag filter, find traces that have spans with matching attributes
            for key, value in tags_dict.items():
                # Subquery to find trace_ids with matching span attributes
                matching_trace_ids = (
                    db.query(SpanAttribute.trace_id)
                    .filter(
                        and_(
                            SpanAttribute.key == key,
                            SpanAttribute.value == str(value),
                        )
                    )
                    .distinct()
                    .subquery()
                )
                query = query.filter(Trace.trace_id.in_(matching_trace_ids))
        except json.JSONDecodeError:
            # Invalid JSON - ignore tags filter
            pass

    # Order by start time descending (newest first)
    query = query.order_by(Trace.start_time.desc())

    # Apply limit
    query = query.limit(limit)

    # Execute query
    traces = query.all()

    if not traces:
        return _api_response([], limit=limit)

    # Optimize: Bulk fetch all related data for all traces at once
    trace_ids = [trace.trace_id for trace in traces]

    # Bulk query all spans for these traces
    all_spans = db.query(Span).filter(Span.trace_id.in_(trace_ids)).all()
    spans_by_trace = {}
    for span in all_spans:
        spans_by_trace.setdefault(span.trace_id, []).append(span)

    # Bulk query all span attributes for these traces
    all_attributes = db.query(SpanAttribute).filter(SpanAttribute.trace_id.in_(trace_ids)).all()
    attributes_by_trace = {}
    for attr in all_attributes:
        attributes_by_trace.setdefault(attr.trace_id, []).append(attr)

    # Bulk query all span events for these traces
    all_events = db.query(SpanEvent).filter(SpanEvent.trace_id.in_(trace_ids)).all()
    events_by_trace = {}
    for event in all_events:
        events_by_trace.setdefault(event.trace_id, []).append(event)

    # Bulk query all resource attributes for these traces
    all_resources = db.query(ResourceAttribute).filter(ResourceAttribute.trace_id.in_(trace_ids)).all()
    resources_by_trace = {}
    for resource in all_resources:
        resources_by_trace.setdefault(resource.trace_id, []).append(resource)

    # Transform to Jaeger format
    jaeger_traces = []
    for trace in traces:
        spans = spans_by_trace.get(trace.trace_id, [])
        span_attributes = attributes_by_trace.get(trace.trace_id, [])
        span_events = events_by_trace.get(trace.trace_id, [])
        resource_attributes = resources_by_trace.get(trace.trace_id, [])

        jaeger_trace = db_models_to_jaeger(
            trace, spans, span_attributes, span_events, resource_attributes
        )
        jaeger_traces.append(jaeger_trace)

    return _api_response(jaeger_traces, limit=limit)


@router.get("/dependencies")
def get_dependencies(
    endTs: Optional[int] = Query(None, description="End timestamp in milliseconds"),
    lookback: Optional[int] = Query(None, description="Lookback in milliseconds"),
    db: Session = Depends(get_db),
):
    """
    Get service dependencies.

    For now, returns empty array. Future enhancement:
    - Analyze parent-child span relationships across services
    - Build service dependency graph

    Returns: {"data": [], ...}
    """
    # TODO: Implement dependency graph computation
    # This would involve:
    # 1. Finding spans where parent and child have different services
    # 2. Aggregating call counts and metrics
    # 3. Building edges between services

    return _api_response([])
