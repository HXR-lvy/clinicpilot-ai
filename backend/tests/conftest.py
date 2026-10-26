from __future__ import annotations

from collections.abc import Generator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.config import ROOT_DIR, Settings
from app.main import create_app
from app.repositories import create_booking, list_bookings
from app.schemas import BookingCreateRequest, BookingOut


class RepositoryBookingToolClient:
    """Deterministic test transport; the production client is exercised separately."""

    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory
        self.calls: list[str] = []
        self.fail_create = False
        self.fail_lookup = False

    def get_patient_bookings(self, patient_id: str) -> list[BookingOut]:
        self.calls.append("get_patient_bookings")
        if self.fail_lookup:
            from app.booking_tools import BookingToolsUnavailableError

            raise BookingToolsUnavailableError("Booking service unavailable")
        with self.session_factory() as session:
            return list_bookings(session, patient_id)

    def create_booking(self, request: BookingCreateRequest) -> BookingOut:
        self.calls.append("create_booking")
        if self.fail_create:
            from app.booking_tools import BookingToolsUnavailableError

            raise BookingToolsUnavailableError("Booking service unavailable")
        with self.session_factory() as session:
            booking, _ = create_booking(
                session,
                patient_id=request.patient_id,
                doctor_id=request.doctor_id,
                treatment_id=request.treatment_id,
                booking_date=request.booking_date,
                booking_time=request.booking_time,
                notes=request.notes,
                draft_id=request.draft_id,
            )
            return booking

    def close(self) -> None:
        return None


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        mock_data_dir=ROOT_DIR / "mock-data",
        llm_mode="mock",
        demo_today=date(2026, 10, 26),
        deepseek_api_key=None,
    )


@pytest.fixture
def test_tools_factory():
    return RepositoryBookingToolClient


@pytest.fixture
def app_factory(test_tools_factory):
    def build(custom_settings: Settings):
        return create_app(
            custom_settings,
            booking_tool_client_factory=test_tools_factory,
        )

    return build


@pytest.fixture
def client(settings: Settings, app_factory) -> Generator[TestClient, None, None]:
    application = app_factory(settings)
    with TestClient(application) as test_client:
        yield test_client

