"""OpenTelemetry Distributed Tracing & W3C TraceContext Subsystem for CompFlow."""

from __future__ import annotations

import logging
import socket
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ALWAYS_ON, ParentBased, TraceIdRatioBased
from opentelemetry.trace import Status, StatusCode

from comp_flow.core.config import settings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

_TRACING_INITIALIZED = False


def create_resource() -> Resource:
    """Constructs OpenTelemetry Resource attributes identifying service and cloud topology."""
    return Resource.create(
        {
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.version": settings.APP_VERSION,
            "deployment.environment": settings.ENVIRONMENT,
            "host.name": socket.gethostname(),
            "cloud.provider": "onprem",
            "cloud.platform": "talos-kubernetes",
            "cluster.name": "talos-baremetal",
        }
    )


def create_sampler() -> Any:
    """Configures adaptive parent-based sampling based on environment settings."""
    if not settings.OTEL_ENABLED:
        return ALWAYS_OFF
    if settings.OTEL_SAMPLING_RATIO >= 1.0:
        return ALWAYS_ON
    return ParentBased(TraceIdRatioBased(settings.OTEL_SAMPLING_RATIO))


def init_tracer_provider() -> TracerProvider:
    """Initializes and registers the OpenTelemetry TracerProvider."""
    resource = create_resource()
    sampler = create_sampler()
    provider = TracerProvider(resource=resource, sampler=sampler)

    if settings.ENVIRONMENT in ("test", "testing"):
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
        trace.set_tracer_provider(provider)
        return provider

    if settings.OTEL_ENABLED:
        try:
            exporter = OTLPSpanExporter(
                endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
                insecure=settings.OTEL_INSECURE_GRPC,
            )
            processor = BatchSpanProcessor(
                exporter,
                max_queue_size=2048,
                schedule_delay_millis=500,
                max_export_batch_size=512,
            )
            provider.add_span_processor(processor)
            logger.info(
                f"OpenTelemetry OTLP exporter initialized targeting {settings.OTEL_EXPORTER_OTLP_ENDPOINT}"
            )
        except Exception as exc:
            logger.warning(
                f"Failed to initialize OTLP Span Exporter ({exc}); running local tracing only."
            )

    trace.set_tracer_provider(provider)
    return provider


def setup_tracing(app: FastAPI | None = None, engine: AsyncEngine | None = None) -> None:
    """Registers auto-instrumentations for FastAPI, SQLAlchemy, and Redis."""
    global _TRACING_INITIALIZED
    if _TRACING_INITIALIZED:
        return

    provider = init_tracer_provider()

    # 1. Instrument FastAPI HTTP requests
    if app is not None:
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=provider,
            excluded_urls="/healthz,/readyz,/metrics,/favicon.ico",
        )

    # 2. Instrument SQLAlchemy Database Queries
    if engine is not None:
        SQLAlchemyInstrumentor().instrument(
            engine=engine.sync_engine,
            tracer_provider=provider,
        )

    # 3. Instrument Redis Cache Calls
    RedisInstrumentor().instrument(tracer_provider=provider)

    _TRACING_INITIALIZED = True
    logger.info("OpenTelemetry distributed tracing setup complete.")


def get_tracer(name: str = "compflow") -> trace.Tracer:
    """Returns an OpenTelemetry tracer instance."""
    return trace.get_tracer(name, settings.APP_VERSION)


def get_current_trace_id() -> str | None:
    """Returns active 32-hex trace ID for response headers and TSE troubleshooting."""
    span = trace.get_current_span()
    if span is not None and span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, "032x")
    return None


@contextmanager
def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    tracer_name: str = "compflow",
) -> Generator[trace.Span, None, None]:
    """Context manager creating a traced child span with custom domain attributes."""
    tracer = get_tracer(tracer_name)
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                if v is not None:
                    span.set_attribute(
                        k, str(v) if isinstance(v, (int, float, bool, str)) else repr(v)
                    )
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
