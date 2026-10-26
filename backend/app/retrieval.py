from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Clinic, Doctor, DoctorTreatment, Treatment
from .schemas import SourceRef


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "can",
    "do",
    "does",
    "for",
    "from",
    "has",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "please",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
    "would",
    "you",
}

SYNONYMS = {
    "allergy": "allergies general practice preventative checkup",
    "allergies": "allergy general practice preventative checkup",
    "peanut": "allergy general practice preventative checkup",
    "annual": "routine checkup preventative",
    "checkup": "general health preventative",
    "chemical": "skin dermatology",
    "acne": "skin dermatology",
    "eczema": "skin dermatology",
    "rash": "skin dermatology",
    "skin": "dermatology consultation",
    "child": "pediatric pediatrics vaccination",
    "kid": "pediatric pediatrics vaccination",
    "vaccination": "pediatric vaccine immunization",
    "vaccine": "vaccination immunization",
    "flu": "immunization flu shot",
    "shot": "immunization injection",
    "knee": "joint orthopedics pain",
    "joint": "orthopedics pain",
    "sore": "pain orthopedics",
    "fever": "general practice checkup",
    "cough": "general practice checkup",
}


@dataclass
class KnowledgeDocument:
    source_type: str
    source_id: str
    label: str
    text: str
    payload: object


@dataclass
class Recommendation:
    doctor: Doctor
    treatment: Treatment
    clinic: Clinic
    score: float


@dataclass
class RetrievalResult:
    documents: list[KnowledgeDocument] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    recommendation: Recommendation | None = None


def _tokens(text: str) -> list[str]:
    base_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in STOPWORDS and len(token) > 1
    ]
    expanded = list(base_tokens)
    for token in base_tokens:
        expanded.extend(SYNONYMS.get(token, "").split())
    return expanded


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    counts = Counter(tokens)
    if not counts:
        return {}
    total = sum(counts.values())
    vector = {
        term: (count / total) * idf.get(term, 1.0)
        for term, count in counts.items()
    }
    norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
    return {term: value / norm for term, value in vector.items()}


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    return sum(value * right.get(term, 0.0) for term, value in left.items())


class KnowledgeRetriever:
    def __init__(self, session: Session):
        self.session = session
        self.clinics = session.scalars(select(Clinic)).all()
        self.doctors = session.scalars(select(Doctor)).all()
        self.treatments = session.scalars(select(Treatment)).all()
        clinic_by_id = {item.clinic_id: item for item in self.clinics}
        doctor_by_id = {item.doctor_id: item for item in self.doctors}
        treatment_by_id = {item.treatment_id: item for item in self.treatments}

        self.documents: list[KnowledgeDocument] = []
        for clinic in self.clinics:
            self.documents.append(
                KnowledgeDocument(
                    source_type="clinic",
                    source_id=clinic.clinic_id,
                    label=clinic.clinic_name,
                    text=(
                        f"{clinic.clinic_name} {clinic.address} {clinic.phone} "
                        f"hours open operating schedule {clinic.operating_hours} "
                        f"cancellation policy fee {clinic.cancellation_policy} "
                        f"emergency urgent {clinic.emergency_instructions}"
                    ),
                    payload=clinic,
                )
            )
        for doctor in self.doctors:
            clinic = clinic_by_id[doctor.clinic_id]
            self.documents.append(
                KnowledgeDocument(
                    source_type="doctor",
                    source_id=doctor.doctor_id,
                    label=doctor.full_name,
                    text=(
                        f"{doctor.full_name} doctor physician {doctor.specialty} "
                        f"languages {doctor.languages_spoken} fee "
                        f"{doctor.consultation_fee_usd:.2f} dollars {doctor.bio} "
                        f"clinic {clinic.clinic_name} {clinic.address}"
                    ),
                    payload=doctor,
                )
            )
        for treatment in self.treatments:
            self.documents.append(
                KnowledgeDocument(
                    source_type="treatment",
                    source_id=treatment.treatment_id,
                    label=treatment.treatment_name,
                    text=(
                        f"{treatment.treatment_name} service {treatment.category} "
                        f"duration {treatment.duration_minutes} minutes price "
                        f"{treatment.price_usd:.2f} dollars preparation "
                        f"{treatment.pre_treatment_instructions}"
                    ),
                    payload=treatment,
                )
            )

        self.pair_candidates: list[tuple[str, Doctor, Treatment, Clinic]] = []
        pair_rows = self.session.execute(
            select(DoctorTreatment.doctor_id, DoctorTreatment.treatment_id)
        ).all()
        for doctor_id, treatment_id in pair_rows:
            doctor = doctor_by_id.get(doctor_id)
            treatment = treatment_by_id.get(treatment_id)
            if doctor is None or treatment is None:
                continue
            clinic = clinic_by_id[doctor.clinic_id]
            pair_text = " ".join(
                (
                    doctor.full_name,
                    doctor.specialty,
                    doctor.bio,
                    treatment.treatment_name,
                    treatment.category,
                    treatment.pre_treatment_instructions,
                    clinic.clinic_name,
                )
            )
            self.pair_candidates.append((pair_text, doctor, treatment, clinic))

        corpus = [document.text for document in self.documents]
        corpus.extend(pair_text for pair_text, *_ in self.pair_candidates)
        tokenized_corpus = [_tokens(text) for text in corpus]
        document_frequency: Counter[str] = Counter()
        for tokens in tokenized_corpus:
            document_frequency.update(set(tokens))
        corpus_size = len(tokenized_corpus)
        self.idf = {
            term: math.log((1 + corpus_size) / (1 + frequency)) + 1
            for term, frequency in document_frequency.items()
        }
        self._document_vectors = [
            _tfidf_vector(tokens, self.idf) for tokens in tokenized_corpus
        ]

    def search(self, query: str, top_k: int = 6) -> RetrievalResult:
        query_tokens = _tokens(query)
        query_vector = _tfidf_vector(query_tokens, self.idf)
        if not query_vector:
            return RetrievalResult()
        query_terms = set(query_tokens)

        scored_documents: list[tuple[float, KnowledgeDocument]] = []
        for document, vector in zip(
            self.documents, self._document_vectors[: len(self.documents)], strict=True
        ):
            score = _cosine(query_vector, vector)
            label_terms = set(_tokens(document.label))
            score += 0.35 * len(query_terms & label_terms)
            if score > 0:
                scored_documents.append((score, document))
        scored_documents.sort(key=lambda item: item[0], reverse=True)
        top_documents = [document for _, document in scored_documents[:top_k]]

        pair_start = len(self.documents)
        scored_pairs: list[tuple[float, Recommendation]] = []
        for index, (_, doctor, treatment, clinic) in enumerate(self.pair_candidates):
            vector = self._document_vectors[pair_start + index]
            score = _cosine(query_vector, vector)
            scored_pairs.append(
                (score, Recommendation(doctor, treatment, clinic, score))
            )
        scored_pairs.sort(key=lambda item: item[0], reverse=True)
        recommendation = (
            scored_pairs[0][1] if scored_pairs and scored_pairs[0][0] > 0 else None
        )

        sources = [
            SourceRef(
                type=document.source_type,  # type: ignore[arg-type]
                id=document.source_id,
                label=document.label,
            )
            for document in top_documents
        ]
        return RetrievalResult(
            documents=top_documents,
            sources=sources,
            recommendation=recommendation,
        )


def find_department_recommendation(
    session: Session, query: str
) -> Recommendation | None:
    return KnowledgeRetriever(session).search(query, top_k=6).recommendation

