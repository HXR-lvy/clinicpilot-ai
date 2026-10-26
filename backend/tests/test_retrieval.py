from __future__ import annotations

from fastapi.testclient import TestClient

from app.retrieval import KnowledgeRetriever


def test_rag_recommends_dermatology_for_skin_rash(client: TestClient):
    with client.app.state.session_factory() as session:
        result = KnowledgeRetriever(session).search("I have a painful skin rash")
    assert result.recommendation is not None
    assert result.recommendation.doctor.doctor_id == "D103"
    assert result.recommendation.treatment.treatment_id == "T003"
    assert any(source.id == "D103" for source in result.sources)


def test_rag_retrieves_clinic_policy(client: TestClient):
    with client.app.state.session_factory() as session:
        result = KnowledgeRetriever(session).search(
            "What is the cancellation policy and opening hours?"
        )
    assert result.documents
    assert any(source.type == "clinic" for source in result.sources)


def test_named_clinic_ranking_prefers_requested_clinic(client: TestClient):
    with client.app.state.session_factory() as session:
        result = KnowledgeRetriever(session).search("What are Metro Care's opening hours?")
    clinic_sources = [source for source in result.sources if source.type == "clinic"]
    assert clinic_sources[0].id == "C001"

