from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Span, Status, StatusCode, Tracer
from sqlalchemy.engine import Engine

from .config import Settings


@dataclass
class TelemetryRuntime:
    provider: trace.TracerProvider
    tracer: Tracer
    enabled: bool
    owns_provider: bool = False

    def instrument(self, application: FastAPI, engine: Engine) -> None:
        if not self.enabled:
            return
        FastAPIInstrumentor.instrument_app(
            application,
            tracer_provider=self.provider,
        )
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=self.provider,
        )

    def shutdown(self) -> None:
        if self.owns_provider and isinstance(self.provider, TracerProvider):
            self.provider.shutdown()


def setup_telemetry(
    settings: Settings,
    tracer_provider: trace.TracerProvider | None = None,
) -> TelemetryRuntime:
    owns_provider = tracer_provider is None
    enabled = tracer_provider is not None or settings.otel_enabled

    if tracer_provider is None:
        if settings.otel_enabled:
            tracer_provider = TracerProvider(
                resource=Resource.create(
                    {"service.name": settings.otel_service_name}
                )
            )
            if settings.otel_exporter_otlp_endpoint:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                    OTLPSpanExporter,
                )

                exporter = OTLPSpanExporter(
                    endpoint=settings.otel_exporter_otlp_endpoint,
                    timeout=settings.tool_api_timeout_seconds,
                )
            else:
                exporter = ConsoleSpanExporter()
            tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
        else:
            tracer_provider = trace.NoOpTracerProvider()

    return TelemetryRuntime(
        provider=tracer_provider,
        tracer=tracer_provider.get_tracer("clinicpilot-ai"),
        enabled=enabled,
        owns_provider=owns_provider,
    )


def record_span_error(span: Span, exc: BaseException) -> None:
    span.set_attribute("error.type", type(exc).__name__)
    span.set_status(Status(StatusCode.ERROR))
