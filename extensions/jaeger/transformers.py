"""
Data transformation functions between OTLP, database models, and Jaeger JSON formats.

Timestamp conventions:
- OTLP protobuf: nanoseconds since Unix epoch
- Internal storage (SQLite): microseconds since Unix epoch (INTEGER)
- Jaeger API: microseconds since Unix epoch
- Conversion: nanoseconds // 1000 = microseconds
"""

import json
import re
from collections import defaultdict
from typing import Any

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span as OTLPSpan

from database import (
    EventAttribute,
    Operation,
    ResourceAttribute,
    Service,
    Span,
    SpanAttribute,
    SpanEvent,
    Trace,
)


def format_trace_id(trace_id_bytes: bytes) -> str:
    """Convert 16-byte trace ID to 32-char hex string."""
    return trace_id_bytes.hex()


def format_span_id(span_id_bytes: bytes) -> str:
    """Convert 8-byte span ID to 16-char hex string."""
    return span_id_bytes.hex()


def extract_service_name(resource_spans: ResourceSpans) -> str:
    """
    Extract service name from resource attributes.

    Looks for the "service.name" attribute.
    Returns "unknown-service" if not found.
    """
    for attr in resource_spans.resource.attributes:
        if attr.key == "service.name":
            return _any_value_to_string(attr.value)
    return "unknown-service"


def _any_value_to_string(value: AnyValue) -> str:
    """Convert OTLP AnyValue to string."""
    if value.HasField("string_value"):
        return value.string_value
    elif value.HasField("int_value"):
        return str(value.int_value)
    elif value.HasField("double_value"):
        return str(value.double_value)
    elif value.HasField("bool_value"):
        return str(value.bool_value)
    else:
        return ""


def _any_value_to_python(value: AnyValue) -> tuple[Any, str]:
    """
    Convert OTLP AnyValue to Python value and type string.

    Returns: (value, type_name)
    where type_name is one of: string, int, float, bool
    """
    if value.HasField("string_value"):
        return (value.string_value, "string")
    elif value.HasField("int_value"):
        return (value.int_value, "int")
    elif value.HasField("double_value"):
        return (value.double_value, "float")
    elif value.HasField("bool_value"):
        return (value.bool_value, "bool")
    elif value.HasField("array_value"):
        # Convert array to JSON string
        array_items = [_any_value_to_python(v)[0] for v in value.array_value.values]
        return (json.dumps(array_items), "string")
    elif value.HasField("kvlist_value"):
        # Convert map to JSON string
        kv_dict = {kv.key: _any_value_to_python(kv.value)[0] for kv in value.kvlist_value.values}
        return (json.dumps(kv_dict), "string")
    else:
        return ("", "string")


def otlp_to_db_models(
    otlp_request: ExportTraceServiceRequest,
) -> tuple[list[Trace], list[Span], list[SpanAttribute], list[SpanEvent], list[EventAttribute], list[ResourceAttribute], list[Service], list[Operation]]:
    """
    Convert OTLP ExportTraceServiceRequest to database model instances.

    Returns a tuple of lists ready for batch insertion:
    (traces, spans, span_attributes, span_events, event_attributes, resource_attributes, services, operations)
    """
    traces_dict = {}  # trace_id -> Trace
    spans_list = []
    span_attributes_list = []
    span_events_list = []
    event_attributes_list = []
    resource_attributes_list = []
    services_dict = {}  # service_name -> Service
    operations_dict = {}  # (service_name, operation_name, span_kind) -> Operation

    for resource_spans in otlp_request.resource_spans:
        service_name = extract_service_name(resource_spans)

        # Track service
        if service_name not in services_dict:
            services_dict[service_name] = Service(name=service_name)

        # Extract resource attributes
        for scope_spans in resource_spans.scope_spans:
            for otlp_span in scope_spans.spans:
                trace_id = format_trace_id(otlp_span.trace_id)
                span_id = format_span_id(otlp_span.span_id)
                parent_span_id = format_span_id(otlp_span.parent_span_id) if otlp_span.parent_span_id else None

                # Convert timestamps: nanoseconds -> microseconds
                start_time_us = otlp_span.start_time_unix_nano // 1000
                end_time_us = otlp_span.end_time_unix_nano // 1000
                duration_us = end_time_us - start_time_us

                # Map span kind
                span_kind_map = {
                    0: "UNSPECIFIED",
                    1: "INTERNAL",
                    2: "SERVER",
                    3: "CLIENT",
                    4: "PRODUCER",
                    5: "CONSUMER",
                }
                span_kind = span_kind_map.get(otlp_span.kind, "INTERNAL")

                # Map status code
                status_code_map = {
                    0: "UNSET",
                    1: "OK",
                    2: "ERROR",
                }
                status_code = status_code_map.get(otlp_span.status.code, "UNSET")
                status_message = otlp_span.status.message if otlp_span.status.message else None

                # Create Span model
                span = Span(
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    operation_name=otlp_span.name,
                    service_name=service_name,
                    start_time=start_time_us,
                    duration=duration_us,
                    span_kind=span_kind,
                    status_code=status_code,
                    status_message=status_message,
                )
                spans_list.append(span)

                # Track operation
                op_key = (service_name, otlp_span.name, span_kind)
                if op_key not in operations_dict:
                    operations_dict[op_key] = Operation(
                        service_name=service_name,
                        operation_name=otlp_span.name,
                        span_kind=span_kind,
                    )

                # Extract span attributes
                for attr in otlp_span.attributes:
                    value, value_type = _any_value_to_python(attr.value)
                    span_attr = SpanAttribute(
                        trace_id=trace_id,
                        span_id=span_id,
                        key=attr.key,
                        value=str(value),
                        value_type=value_type,
                    )
                    span_attributes_list.append(span_attr)

                # Extract span events
                for event in otlp_span.events:
                    event_timestamp_us = event.time_unix_nano // 1000
                    span_event = SpanEvent(
                        trace_id=trace_id,
                        span_id=span_id,
                        timestamp=event_timestamp_us,
                        name=event.name,
                    )
                    span_events_list.append(span_event)

                    # Note: We'll need to handle event attributes after we insert the span_event to get its ID
                    # For now, we'll store them separately and handle in the service layer

                # Update or create trace record
                if trace_id not in traces_dict:
                    # This is the first span for this trace - initialize trace
                    traces_dict[trace_id] = Trace(
                        trace_id=trace_id,
                        start_time=start_time_us,
                        end_time=end_time_us,
                        duration=duration_us,
                        service_name=service_name,
                        root_operation=otlp_span.name,
                        span_count=1,
                    )
                else:
                    # Update trace bounds and count
                    trace = traces_dict[trace_id]
                    trace.start_time = min(trace.start_time, start_time_us)
                    trace.end_time = max(trace.end_time, end_time_us)
                    trace.duration = trace.end_time - trace.start_time
                    trace.span_count += 1

                    # Use root span (no parent) for service/operation
                    if not parent_span_id:
                        trace.service_name = service_name
                        trace.root_operation = otlp_span.name

        # Extract resource attributes (per trace)
        for otlp_span in scope_spans.spans:
            trace_id = format_trace_id(otlp_span.trace_id)
            for attr in resource_spans.resource.attributes:
                value, _ = _any_value_to_python(attr.value)
                resource_attr = ResourceAttribute(
                    trace_id=trace_id,
                    service_name=service_name,
                    key=attr.key,
                    value=str(value),
                )
                resource_attributes_list.append(resource_attr)

    return (
        list(traces_dict.values()),
        spans_list,
        span_attributes_list,
        span_events_list,
        event_attributes_list,  # Empty for now
        resource_attributes_list,
        list(services_dict.values()),
        list(operations_dict.values()),
    )


def db_models_to_jaeger(
    trace: Trace,
    spans: list[Span],
    span_attributes: list[SpanAttribute],
    span_events: list[SpanEvent],
    resource_attributes: list[ResourceAttribute],
) -> dict:
    """
    Convert database models to Jaeger JSON format.

    Returns a dict matching the Jaeger API response format.
    """
    # Group attributes by span
    attributes_by_span = defaultdict(list)
    for attr in span_attributes:
        attributes_by_span[(attr.trace_id, attr.span_id)].append(attr)

    # Group events by span
    events_by_span = defaultdict(list)
    for event in span_events:
        events_by_span[(event.trace_id, event.span_id)].append(event)

    # Group resource attributes by service
    resources_by_service = defaultdict(list)
    for res_attr in resource_attributes:
        resources_by_service[res_attr.service_name].append(res_attr)

    # Build processes dict (service -> process ID)
    processes = {}
    service_to_process_id = {}
    process_counter = 1

    for span in spans:
        if span.service_name not in service_to_process_id:
            process_id = f"p{process_counter}"
            service_to_process_id[span.service_name] = process_id
            process_counter += 1

            # Build process tags
            process_tags = []
            for res_attr in resources_by_service[span.service_name]:
                process_tags.append({
                    "key": res_attr.key,
                    "type": "string",
                    "value": res_attr.value,
                })

            processes[process_id] = {
                "serviceName": span.service_name,
                "tags": process_tags,
            }

    # Build spans array
    jaeger_spans = []
    for span in spans:
        # Build references (parent-child relationship)
        references = []
        if span.parent_span_id:
            references.append({
                "refType": "CHILD_OF",
                "traceID": span.trace_id,
                "spanID": span.parent_span_id,
            })

        # Build tags
        tags = []
        for attr in attributes_by_span[(span.trace_id, span.span_id)]:
            # Map value_type to Jaeger tag type
            type_map = {
                "string": "string",
                "int": "int64",
                "float": "float64",
                "bool": "bool",
            }
            tag_type = type_map.get(attr.value_type, "string")

            tags.append({
                "key": attr.key,
                "type": tag_type,
                "value": attr.value,
            })

        # Add span kind as tag
        tags.append({
            "key": "span.kind",
            "type": "string",
            "value": span.span_kind,
        })

        # Add status as tag
        if span.status_code and span.status_code != "UNSET":
            tags.append({
                "key": "otel.status_code",
                "type": "string",
                "value": span.status_code,
            })
            if span.status_message:
                tags.append({
                    "key": "otel.status_description",
                    "type": "string",
                    "value": span.status_message,
                })

        # Build logs (from events)
        logs = []
        for event in events_by_span[(span.trace_id, span.span_id)]:
            logs.append({
                "timestamp": event.timestamp,
                "fields": [
                    {"key": "event", "type": "string", "value": event.name}
                ],
            })

        jaeger_span = {
            "traceID": span.trace_id,
            "spanID": span.span_id,
            "operationName": span.operation_name,
            "references": references,
            "startTime": span.start_time,
            "duration": span.duration,
            "tags": tags,
            "logs": logs,
            "processID": service_to_process_id[span.service_name],
            "warnings": None,
        }
        jaeger_spans.append(jaeger_span)

    return {
        "traceID": trace.trace_id,
        "spans": jaeger_spans,
        "processes": processes,
    }


def parse_duration(duration_str: str | None) -> int | None:
    """
    Parse duration string to microseconds.

    Examples:
    - "100ms" -> 100000 microseconds
    - "1.5s" -> 1500000 microseconds
    - "500us" -> 500 microseconds
    - "2m" -> 120000000 microseconds
    - "1h" -> 3600000000 microseconds

    Returns None if invalid or None input.
    """
    if not duration_str:
        return None

    # Pattern: number followed by unit
    match = re.match(r"^(\d+(?:\.\d+)?)(us|ms|s|m|h)$", duration_str.strip())
    if not match:
        return None

    value_str, unit = match.groups()
    value = float(value_str)

    # Convert to microseconds
    unit_to_us = {
        "us": 1,
        "ms": 1000,
        "s": 1000000,
        "m": 60000000,
        "h": 3600000000,
    }

    return int(value * unit_to_us[unit])
