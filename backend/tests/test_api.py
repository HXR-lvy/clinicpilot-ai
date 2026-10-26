from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_and_seeded_bookings(client: TestClient):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "database": "connected",
        "llm_mode": "mock",
    }

    response = client.get("/api/bookings", params={"patient_id": "P001"})
    assert response.status_code == 200
    bookings = response.json()["bookings"]
    assert [booking["booking_id"] for booking in bookings] == ["B1001", "B1004"]
    assert bookings[0]["doctor_name"] == "Dr. Sarah Jenkins"


def test_next_appointment_lookup_uses_database(client: TestClient):
    response = client.post(
        "/api/chat",
        json={"message": "When is my next appointment?", "patient_id": "P001"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "booking_lookup"
    assert "B1001" in payload["message"]
    assert "2026-11-05" in payload["message"]


def test_multi_turn_booking_persists_and_survives_restart(
    client: TestClient, settings: Settings
):
    first = client.post(
        "/api/chat",
        json={
            "message": "Book a general health checkup with Dr. Sarah Jenkins.",
            "patient_id": "P001",
        },
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["intent"] == "booking_create"
    assert first_payload["state"] == "collecting"
    assert first_payload["draft"]["doctor_id"] == "D101"
    assert first_payload["draft"]["treatment_id"] == "T001"

    second = client.post(
        "/api/chat",
        json={
            "message": "November 20, 2026 at 10:00 AM.",
            "conversation_id": first_payload["conversation_id"],
            "patient_id": "P001",
        },
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["state"] == "awaiting_confirmation"
    assert second_payload["requires_confirmation"] is True

    third = client.post(
        "/api/chat",
        json={
            "message": "yes, please",
            "conversation_id": first_payload["conversation_id"],
            "patient_id": "P001",
        },
    )
    assert third.status_code == 200
    third_payload = third.json()
    assert third_payload["state"] == "completed"
    booking = third_payload["booking"]
    assert booking["booking_id"] == "B1005"
    assert booking["booking_date"] == "2026-11-20"
    assert booking["booking_time"] == "10:00:00"

    bookings = client.get("/api/bookings", params={"patient_id": "P001"}).json()["bookings"]
    assert len(bookings) == 3
    assert any(item["booking_id"] == "B1005" for item in bookings)

    restarted_app = create_app(settings)
    with TestClient(restarted_app) as restarted_client:
        persisted = restarted_client.get(
            "/api/bookings", params={"patient_id": "P001"}
        ).json()["bookings"]
    assert any(item["booking_id"] == "B1005" for item in persisted)


def test_booking_api_validates_doctor_treatment_pair(client: TestClient):
    response = client.post(
        "/api/bookings",
        json={
            "patient_id": "P001",
            "doctor_id": "D102",
            "treatment_id": "T003",
            "booking_date": "2026-12-01",
            "booking_time": "15:00:00",
        },
    )
    assert response.status_code == 422
    assert "does not support" in response.json()["detail"]


def test_booking_api_is_idempotent_for_draft(client: TestClient):
    request = {
        "patient_id": "P001",
        "doctor_id": "D103",
        "treatment_id": "T003",
        "booking_date": "2026-12-02",
        "booking_time": "14:00:00",
        "draft_id": "draft-idempotency-test",
    }
    first = client.post("/api/bookings", json=request)
    second = client.post("/api/bookings", json=request)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["booking_id"] == second.json()["booking_id"]


def test_emergency_red_flag_short_circuits_booking(client: TestClient):
    response = client.post(
        "/api/chat",
        json={
            "message": "I have chest pain and cannot breathe. Book me an appointment.",
            "patient_id": "P001",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "emergency" in payload["message"].lower()
    assert payload["booking"] is None


def test_unknown_patient_returns_404(client: TestClient):
    response = client.get("/api/bookings", params={"patient_id": "P999"})
    assert response.status_code == 404


def test_named_clinic_question_answers_about_named_clinic(client: TestClient):
    response = client.post(
        "/api/chat",
        json={"message": "What are Metro Care's opening hours?", "patient_id": "P001"},
    )
    assert response.status_code == 200
    assert "Metro Care Health Clinic" in response.json()["message"]


def test_allergy_booking_prompt_uses_patient_context(client: TestClient):
    response = client.post(
        "/api/chat",
        json={
            "message": "Can I book an appointment for my peanut allergy?",
            "patient_id": "P001",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "collecting"
    assert "Peanuts" in payload["message"]
    assert payload["draft"]["doctor_id"] == "D101"
    assert payload["draft"]["treatment_id"] == "T001"


def test_live_mode_without_key_falls_back_deterministically(settings: Settings):
    live_settings = settings.model_copy(update={"llm_mode": "live"})
    application = create_app(live_settings)
    with TestClient(application) as live_client:
        response = live_client.post(
            "/api/chat",
            json={"message": "When is my next appointment?", "patient_id": "P001"},
        )
    assert response.status_code == 200
    assert response.json()["llm_mode"] == "mock-fallback"
    assert "B1001" in response.json()["message"]

