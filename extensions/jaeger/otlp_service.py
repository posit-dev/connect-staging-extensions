"""
OTLP/HTTP trace ingestion endpoint.

Receives traces from OpenTelemetry SDKs via HTTP POST /v1/traces
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from google.protobuf.json_format import Parse
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from sqlalchemy.orm import Session

from database import get_db
from transformers import otlp_to_db_models

router = APIRouter()


@router.post("/v1/traces")
async def receive_traces(request: Request, db: Session = Depends(get_db)):
    """
    Receive OTLP trace data via HTTP and store in SQLite.

    Supports both protobuf and JSON content types.

    Processing steps:
    1. Parse request body based on Content-Type
    2. Extract ResourceSpans from request
    3. Convert to DB models via transformers.otlp_to_db_models()
    4. Batch insert into database
    5. Update services and operations tables
    6. Return ExportTraceServiceResponse
    """
    content_type = request.headers.get("content-type", "")
    body = await request.body()

    # Parse OTLP request based on content type
    try:
        if "application/x-protobuf" in content_type:
            otlp_request = ExportTraceServiceRequest()
            otlp_request.ParseFromString(body)
        elif "application/json" in content_type:
            otlp_request = Parse(body, ExportTraceServiceRequest())
        else:
            # Default to protobuf
            otlp_request = ExportTraceServiceRequest()
            otlp_request.ParseFromString(body)
    except Exception as e:
        print(f"Error parsing OTLP request: {e}")
        # Return partial success response
        response = ExportTraceServiceResponse()
        response.partial_success.error_message = f"Failed to parse request: {str(e)}"
        return Response(
            content=response.SerializeToString(),
            media_type="application/x-protobuf",
            status_code=400,
        )

    # Transform OTLP to database models
    try:
        (
            traces,
            spans,
            span_attributes,
            span_events,
            event_attributes,
            resource_attributes,
            services,
            operations,
        ) = otlp_to_db_models(otlp_request)
    except Exception as e:
        print(f"Error transforming OTLP data: {e}")
        response = ExportTraceServiceResponse()
        response.partial_success.error_message = f"Failed to transform data: {str(e)}"
        return Response(
            content=response.SerializeToString(),
            media_type="application/x-protobuf",
            status_code=500,
        )

    # Store in database
    try:
        # Insert/update services
        for service in services:
            existing = db.query(type(service)).filter_by(name=service.name).first()
            if existing:
                existing.last_seen = datetime.utcnow()
            else:
                db.add(service)

        # Insert/update operations
        for operation in operations:
            existing = (
                db.query(type(operation))
                .filter_by(
                    service_name=operation.service_name,
                    operation_name=operation.operation_name,
                    span_kind=operation.span_kind,
                )
                .first()
            )
            if existing:
                existing.last_seen = datetime.utcnow()
            else:
                db.add(operation)

        # Insert traces (or update if exists)
        for trace in traces:
            existing = db.query(type(trace)).filter_by(trace_id=trace.trace_id).first()
            if existing:
                # Update existing trace
                existing.end_time = max(existing.end_time, trace.end_time)
                existing.duration = existing.end_time - existing.start_time
                existing.span_count += trace.span_count
            else:
                db.add(trace)

        # Insert spans
        for span in spans:
            # Check if span already exists
            existing = (
                db.query(type(span))
                .filter_by(trace_id=span.trace_id, span_id=span.span_id)
                .first()
            )
            if not existing:
                db.add(span)

        # Insert span attributes
        for attr in span_attributes:
            # Check if attribute already exists (avoid duplicates)
            existing = (
                db.query(type(attr))
                .filter_by(
                    trace_id=attr.trace_id,
                    span_id=attr.span_id,
                    key=attr.key,
                )
                .first()
            )
            if not existing:
                db.add(attr)

        # Insert span events
        for event in span_events:
            db.add(event)

        # Insert resource attributes
        for res_attr in resource_attributes:
            # Check if resource attribute already exists
            existing = (
                db.query(type(res_attr))
                .filter_by(
                    trace_id=res_attr.trace_id,
                    service_name=res_attr.service_name,
                    key=res_attr.key,
                )
                .first()
            )
            if not existing:
                db.add(res_attr)

        # Commit all changes
        db.commit()

        print(f"✓ Ingested {len(traces)} traces with {len(spans)} spans")

    except Exception as e:
        db.rollback()
        print(f"Error storing traces in database: {e}")
        response = ExportTraceServiceResponse()
        response.partial_success.error_message = f"Failed to store traces: {str(e)}"
        return Response(
            content=response.SerializeToString(),
            media_type="application/x-protobuf",
            status_code=500,
        )

    # Return success response
    response = ExportTraceServiceResponse()
    return Response(
        content=response.SerializeToString(),
        media_type="application/x-protobuf",
    )
