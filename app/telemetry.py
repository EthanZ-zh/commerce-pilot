from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.trace import Tracer

from app.config import Settings

INSTRUMENTATION_NAME = "commerce-pilot"
_configured = False


def get_tracer() -> Tracer:
    return trace.get_tracer(INSTRUMENTATION_NAME)


def build_tracer_provider(settings: Settings) -> TracerProvider:
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.version": "0.1.0",
                "deployment.environment.name": settings.app_env,
            }
        )
    )
    if settings.otel_exporter_otlp_endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
            )
        )
    if settings.otel_console_exporter:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    return provider


def configure_telemetry(app: FastAPI, settings: Settings) -> TracerProvider | None:
    global _configured
    if not settings.otel_enabled or _configured:
        return None
    provider = build_tracer_provider(settings)
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="/api/v1/health",
    )
    _configured = True
    return provider
