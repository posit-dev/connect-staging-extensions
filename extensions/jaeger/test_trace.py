#!/usr/bin/env python3
"""
Simple test script to send a trace via OTLP to the Jaeger backend.
"""

import time

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Configure the OTLP exporter
exporter = OTLPSpanExporter(
    endpoint="https://dogfood.team.pct.posit.it/content/1525a7ba-5f27-44d5-8429-dfd210cee692/v1/traces",
)

# Create a tracer provider with resource attributes
resource = Resource.create(
    {
        "service.name": "test-service",
        "service.version": "1.0.0",
        "deployment.environment": "development",
    }
)

provider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(exporter)
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

# Create a tracer
tracer = trace.get_tracer(__name__)

# Create a test trace
print("Creating test trace...")
with tracer.start_as_current_span("http-request") as parent_span:
    parent_span.set_attribute("http.method", "GET")
    parent_span.set_attribute("http.url", "/api/users")
    parent_span.set_attribute("http.status_code", 200)

    # Simulate some work
    time.sleep(0.1)

    # Create a child span
    with tracer.start_as_current_span("database-query") as child_span:
        child_span.set_attribute("db.system", "postgresql")
        child_span.set_attribute("db.statement", "SELECT * FROM users")
        child_span.add_event("query-start")
        time.sleep(0.05)
        child_span.add_event("query-end")

    # Create another child span
    with tracer.start_as_current_span("cache-check") as child_span:
        child_span.set_attribute("cache.hit", True)
        time.sleep(0.02)

print("✓ Trace sent successfully!")
print("\nWaiting for spans to be flushed...")
time.sleep(2)  # Give time for batch processor to flush

print("\nNow you can:")
print("1. Check API: curl http://localhost:8000/api/services")
print("2. Open UI: http://localhost:8000")
print("3. Search for service: test-service")
