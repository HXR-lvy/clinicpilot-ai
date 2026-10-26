from __future__ import annotations

from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.booking_tools import HttpBookingToolClient
from app.config import Settings
from app.llm import DeepSeekClient
from app.main import create_app


def _trace_provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def test_fastapi_and_sqlalchemy_requests_create_spans(settings: Settings):
    provider, exporter = _trace_provider()
    application = create_app(settings, tracer_provider=provider)

    with TestClient(application) as client:
        response = client.get("/api/bookings", params={"patient_id": "P001"})

    assert response.status_code == 200
    spans = exporter.get_finished_spans()
    assert any(span.name.startswith("GET /api/bookings") for span in spans)
    assert any(span.name.startswith("SELECT") for span in spans)


def test_rest_tool_span_records_result_without_booking_content():
    provider, exporter = _trace_provider()
    tracer = provider.get_tracer("test")
    tool = HttpBookingToolClient(
        base_url="http://testserver",
        timeout_seconds=2,
        tracer=tracer,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"bookings": []})
        ),
    )

    tool.get_patient_bookings("P001")

    span = next(
        span
        for span in exporter.get_finished_spans()
        if span.name == "agent.tool.get_patient_bookings"
    )
    assert span.attributes["agent.tool.transport"] == "rest"
    assert span.attributes["agent.tool.result_count"] == 0
    assert "agent.tool.duration_ms" in span.attributes


def test_deepseek_span_records_token_usage_without_prompt_content(settings: Settings):
    provider, exporter = _trace_provider()
    tracer = provider.get_tracer("test")
    live_settings = settings.model_copy(
        update={"llm_mode": "live", "deepseek_api_key": "test-key"}
    )
    deepseek = DeepSeekClient(live_settings, tracer=tracer)
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content='{"intent":"small_talk","confidence":0.9}')
            )
        ],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=4),
    )
    deepseek.client.chat.completions.create = lambda **_: response
    private_message = "This private message must not appear in trace attributes"

    decision = deepseek.route(
        message=private_message,
        today=settings.demo_today,
        patient_context={"patient": {"patient_id": "P001"}},
        catalog={"doctors": [], "treatments": [], "clinics": []},
        conversation_state="idle",
        draft=None,
        history=[],
    )

    assert decision.intent == "small_talk"
    span = next(
        span
        for span in exporter.get_finished_spans()
        if span.name == "gen_ai.deepseek.route"
    )
    assert span.attributes["gen_ai.usage.input_tokens"] == 12
    assert span.attributes["gen_ai.usage.output_tokens"] == 4
    assert all(private_message not in str(value) for value in span.attributes.values())
