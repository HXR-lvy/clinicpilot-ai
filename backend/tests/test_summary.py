from fastapi.testclient import TestClient


TRANSCRIPT = (
    "Patient: I have had a sore throat for three days.\n"
    "Diagnosis: viral pharyngitis.\n"
    "Medication: Take ibuprofen as needed.\n"
    "Doctor instructions: Rest and return if the fever worsens."
)


def test_summarize_returns_structured_mock_summary(client: TestClient):
    response = client.post("/api/summarize", json={"transcript": TRANSCRIPT})

    assert response.status_code == 200
    assert response.json() == {
        "chief_complaint": "I have had a sore throat for three days",
        "diagnosis": "viral pharyngitis",
        "medication": "Take ibuprofen as needed",
        "doctor_instructions": "Rest and return if the fever worsens",
    }


def test_summarize_rejects_blank_and_oversized_transcripts(client: TestClient):
    blank = client.post("/api/summarize", json={"transcript": "   "})
    oversized = client.post("/api/summarize", json={"transcript": "x" * 20_001})

    assert blank.status_code == 422
    assert oversized.status_code == 422


def test_summarize_does_not_persist_raw_transcript(client: TestClient):
    response = client.post("/api/summarize", json={"transcript": TRANSCRIPT})
    assert response.status_code == 200

    with client.app.state.session_factory() as session:
        from app.models import Message
        from sqlalchemy import func, select

        assert session.scalar(select(func.count()).select_from(Message)) == 0
