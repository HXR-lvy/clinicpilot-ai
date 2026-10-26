from __future__ import annotations

import json

import httpx
import pytest

from app.booking_tools import (
    BookingToolsUnavailableError,
    HttpBookingToolClient,
)
from app.repositories import DomainNotFoundError, DomainValidationError
from app.schemas import BookingCreateRequest


BOOKING = {
    "booking_id": "B2001",
    "patient_id": "P001",
    "doctor_id": "D103",
    "doctor_name": "Dr. Emily Chen",
    "treatment_id": "T003",
    "treatment_name": "Dermatology Consultation",
    "booking_date": "2026-12-02",
    "booking_time": "14:00:00",
    "status": "Confirmed",
    "notes": "Skin concern.",
    "created_at": "2026-10-26T10:00:00Z",
}


def _client(handler) -> HttpBookingToolClient:
    return HttpBookingToolClient(
        base_url="http://testserver",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )


def test_rest_booking_tools_use_expected_http_contract():
    observed: list[tuple[str, str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            observed.append(
                (
                    request.method,
                    request.url.path,
                    dict(request.url.params),
                )
            )
            return httpx.Response(200, json={"bookings": [BOOKING]})

        body = json.loads(request.content)
        observed.append((request.method, request.url.path, body))
        return httpx.Response(201, json=BOOKING)

    tool = _client(handler)
    bookings = tool.get_patient_bookings("P001")
    created = tool.create_booking(
        BookingCreateRequest(
            patient_id="P001",
            doctor_id="D103",
            treatment_id="T003",
            booking_date="2026-12-02",
            booking_time="14:00:00",
            notes="Skin concern.",
            draft_id="draft-rest-test",
        )
    )

    assert bookings[0].booking_id == "B2001"
    assert created.booking_id == "B2001"
    assert observed[0] == ("GET", "/api/bookings", {"patient_id": "P001"})
    assert observed[1][0:2] == ("POST", "/api/bookings")
    assert observed[1][2]["draft_id"] == "draft-rest-test"


@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [
        (404, DomainNotFoundError),
        (422, DomainValidationError),
        (500, BookingToolsUnavailableError),
    ],
)
def test_rest_booking_tool_status_mapping(status_code, exception_type):
    tool = _client(
        lambda _: httpx.Response(status_code, json={"detail": "mapped error"})
    )

    with pytest.raises(exception_type):
        tool.get_patient_bookings("P001")


def test_rest_booking_tool_network_failure_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    tool = _client(handler)
    with pytest.raises(BookingToolsUnavailableError):
        tool.get_patient_bookings("P001")
