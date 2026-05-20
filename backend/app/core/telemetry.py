"""
Observability setup: OpenTelemetry tracing + Prometheus metrics.
Both are no-ops unless OTEL_ENABLED=true (tracing) or called explicitly (metrics).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI
    from app.core.config import Settings


def setup_tracing(app: "FastAPI", settings: "Settings") -> None:
    """Configure OTel tracing and instrument FastAPI, SQLAlchemy, Redis."""
    if not settings.OTEL_ENABLED:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from app.core.database import engine

    resource = Resource(attributes={
        "service.name": settings.APP_NAME,
        "deployment.environment": settings.APP_ENV,
    })
    exporter = OTLPSpanExporter(
        endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        insecure=True,
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, enable_commenter=True)
    RedisInstrumentor().instrument(tracer_provider=provider)


def setup_metrics(app: "FastAPI") -> None:
    """Expose GET /metrics in Prometheus text format."""
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
