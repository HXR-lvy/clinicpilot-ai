from __future__ import annotations

import logging
from time import perf_counter
from typing import Protocol

import httpx
from opentelemetry import trace
from pydantic import ValidationError

from .observability import record_span_error
from .repositories import DomainNotFoundError, DomainValidationError
from .schemas import BookingCreateRequest, BookingListResponse, BookingOut


logger = logging.getLogger(__name__)


class BookingToolsUnavailableError(Exception):
    pass


class BookingToolClient(Protocol):
    def get_patient_bookings(self, patient_id: str) -> list[BookingOut]: ...

    def create_booking(self, request: BookingCreateRequest) -> BookingOut: ...

    def close(self) -> None: ...


class HttpBookingToolClient:
    """REST-backed booking tools used by the conversational agent."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
        tracer: trace.Tracer | None = None,
    ):
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
        )
        self._tracer = tracer or trace.get_tracer("clinicpilot-ai")

    def get_patient_bookings(self, patient_id: str) -> list[BookingOut]:
        started = perf_counter()
        with self._tracer.start_as_current_span(
            "agent.tool.get_patient_bookings",
            attributes={
                "agent.tool.name": "get_patient_bookings",
                "agent.tool.transport": "rest",
                "patient.id": patient_id,
            },
        ) as span:
            try:
                response = self._client.get(
                    "/api/bookings",
                    params={"patient_id": patient_id},
                )
                payload = self._decode_response(response)
                result = BookingListResponse.model_validate(payload)
                span.set_attribute("http.response.status_code", response.status_code)
                span.set_attribute("agent.tool.result_count", len(result.bookings))
                return result.bookings
            except (
                DomainNotFoundError,
                DomainValidationError,
                BookingToolsUnavailableError,
            ) as exc:
                record_span_error(span, exc)
                raise
            except (httpx.HTTPError, ValidationError) as exc:
                record_span_error(span, exc)
                raise BookingToolsUnavailableError(
                    f"Booking query failed: {type(exc).__name__}"
                ) from exc
            except Exception as exc:
                record_span_error(span, exc)
                raise
            finally:
                elapsed_ms = round((perf_counter() - started) * 1000, 2)
                span.set_attribute("agent.tool.duration_ms", elapsed_ms)
                logger.info(
                    "agent_tool name=get_patient_bookings transport=rest duration_ms=%s",
                    elapsed_ms,
                )

    def create_booking(self, request: BookingCreateRequest) -> BookingOut:
        started = perf_counter()
        with self._tracer.start_as_current_span(
            "agent.tool.create_booking",
            attributes={
                "agent.tool.name": "create_booking",
                "agent.tool.transport": "rest",
                "patient.id": request.patient_id,
                "doctor.id": request.doctor_id,
                "treatment.id": request.treatment_id,
            },
        ) as span:
            try:
                response = self._client.post(
                    "/api/bookings",
                    json=request.model_dump(mode="json"),
                )
                payload = self._decode_response(response)
                booking = BookingOut.model_validate(payload)
                span.set_attribute("http.response.status_code", response.status_code)
                span.set_attribute("booking.id", booking.booking_id)
                return booking
            except (
                DomainNotFoundError,
                DomainValidationError,
                BookingToolsUnavailableError,
            ) as exc:
                record_span_error(span, exc)
                raise
            except (httpx.HTTPError, ValidationError) as exc:
                record_span_error(span, exc)
                raise BookingToolsUnavailableError(
                    f"Booking creation failed: {type(exc).__name__}"
                ) from exc
            except Exception as exc:
                record_span_error(span, exc)
                raise
            finally:
                elapsed_ms = round((perf_counter() - started) * 1000, 2)
                span.set_attribute("agent.tool.duration_ms", elapsed_ms)
                logger.info(
                    "agent_tool name=create_booking transport=rest duration_ms=%s",
                    elapsed_ms,
                )

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _decode_response(response: httpx.Response) -> dict:
        detail = "Booking service request failed"
        try:
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
                detail = payload["detail"]
        except ValueError:
            payload = None

        if response.status_code == 404:
            raise DomainNotFoundError(detail)
        if response.status_code == 422:
            raise DomainValidationError(detail)
        if response.status_code != 200 and response.status_code != 201:
            raise BookingToolsUnavailableError(
                f"Booking service returned HTTP {response.status_code}"
            )
        if not isinstance(payload, dict):
            raise BookingToolsUnavailableError(
                "Booking service returned a non-JSON response"
            )
        return payload
