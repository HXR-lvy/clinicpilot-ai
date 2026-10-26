from __future__ import annotations

import json
import re
from datetime import date, time
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from .config import Settings
from .retrieval import KnowledgeRetriever
from .schemas import Intent
from .temporal import extract_date, extract_time, is_affirmative, is_negative


class LLMUnavailableError(Exception):
    pass


class RouteDecision(BaseModel):
    intent: Intent
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    doctor_id: str | None = None
    treatment_id: str | None = None
    booking_date: date | None = None
    booking_time: time | None = None
    notes: str | None = None
    confirmation: Literal["yes", "no", "unknown"] = "unknown"


class DeepSeekClient:
    def __init__(self, settings: Settings):
        if not settings.deepseek_api_key:
            raise LLMUnavailableError("DEEPSEEK_API_KEY is not configured")
        self.settings = settings
        self.client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
        )

    def route(
        self,
        *,
        message: str,
        today: date,
        patient_context: dict,
        catalog: dict,
        conversation_state: str,
        draft: dict | None,
        history: list[dict[str, str]],
    ) -> RouteDecision:
        schema = {
            "intent": "qa_recommendation | booking_lookup | booking_create | small_talk",
            "confidence": "number from 0 to 1",
            "doctor_id": "known doctor ID or null",
            "treatment_id": "known treatment ID or null",
            "booking_date": "YYYY-MM-DD or null",
            "booking_time": "HH:MM:SS or null",
            "notes": "short appointment note or null",
            "confirmation": "yes | no | unknown",
        }
        system = f"""
You are the deterministic intent router for ClinicPilot AI, a clinic information and booking assistant.
Return exactly one JSON object and no markdown. Follow this schema:
{json.dumps(schema)}

Rules:
- Use booking_lookup for questions about the patient's existing or next appointments.
- Use booking_create when the user wants to reserve, change, or confirm a new appointment.
- Use qa_recommendation for clinic facts, symptoms, doctors, treatments, prices, policies, or recommendations.
- Use small_talk only for greetings or messages unrelated to clinic operations.
- Only use doctor_id and treatment_id values present in the catalog.
- Resolve relative dates against today and clinic-local wall time.
- If a field is unknown, return null. Never invent an ID or time.
- confirmation is yes only for explicit confirmation of a proposed booking, no for explicit rejection, otherwise unknown.
- This system does not diagnose. Do not invent medical facts.

Today: {today.isoformat()}
Conversation state: {conversation_state}
Patient context: {json.dumps(patient_context, ensure_ascii=False)}
Catalog: {json.dumps(catalog, ensure_ascii=False)}
Active booking draft: {json.dumps(draft, default=str, ensure_ascii=False) if draft else "null"}
Recent conversation: {json.dumps(history[-8:], ensure_ascii=False)}
""".strip()
        try:
            response = self.client.chat.completions.create(
                model=self.settings.deepseek_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": message},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=700,
                extra_body={"thinking": {"type": "disabled"}},
            )
            content = response.choices[0].message.content or "{}"
            return RouteDecision.model_validate_json(_strip_code_fence(content))
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            raise LLMUnavailableError(f"DeepSeek returned an invalid route: {exc}") from exc
        except Exception as exc:
            raise LLMUnavailableError(f"DeepSeek routing request failed: {exc}") from exc

    def answer(
        self,
        *,
        message: str,
        patient_context: dict,
        evidence: list[dict],
    ) -> str:
        system = """
You are ClinicPilot AI, a concise clinic information and appointment assistant.
Answer in the language used by the patient. Use only the supplied evidence and patient context.
Never diagnose, prescribe, or claim that a service exists if it is absent from the evidence.
State exact fees, hours, IDs, names, and instructions when relevant. Do not invent citations.
If there is an emergency red flag, tell the patient to call emergency services immediately.
Keep the response under 180 words and use short paragraphs or bullets.
""".strip()
        payload = {
            "patient_context": patient_context,
            "evidence": evidence,
        }
        try:
            response = self.client.chat.completions.create(
                model=self.settings.deepseek_model,
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": f"Question: {message}\n\nGrounding data:\n{json.dumps(payload, ensure_ascii=False, default=str)}",
                    },
                ],
                temperature=0.2,
                max_tokens=500,
                extra_body={"thinking": {"type": "disabled"}},
            )
            content = (response.choices[0].message.content or "").strip()
            if not content:
                raise LLMUnavailableError("DeepSeek returned an empty answer")
            return content
        except LLMUnavailableError:
            raise
        except Exception as exc:
            raise LLMUnavailableError(f"DeepSeek answer request failed: {exc}") from exc


class MockDecisionEngine:
    """Development router that exercises the same state and tool workflow as live mode."""

    def __init__(self, session: Session):
        self.session = session

    def route(
        self,
        *,
        message: str,
        today: date,
        catalog: dict,
        conversation_state: str,
    ) -> RouteDecision:
        lowered = message.lower().strip()
        confirmation = (
            "yes"
            if is_affirmative(message)
            else "no"
            if is_negative(message)
            else "unknown"
        )

        doctor_id = next(
            (
                doctor["doctor_id"]
                for doctor in catalog["doctors"]
                if doctor["doctor_id"].lower() in lowered
                or doctor["full_name"].lower() in lowered
                or doctor["full_name"].lower().removeprefix("dr. ") in lowered
            ),
            None,
        )
        treatment_id = next(
            (
                treatment["treatment_id"]
                for treatment in catalog["treatments"]
                if treatment["treatment_id"].lower() in lowered
                or treatment["treatment_name"].lower() in lowered
            ),
            None,
        )

        recommendation = KnowledgeRetriever(self.session).search(message).recommendation
        booking_date = extract_date(message, today)
        booking_time = extract_time(message)

        lookup_phrases = (
            "my appointment",
            "my appointments",
            "my booking",
            "my bookings",
            "next appointment",
            "appointment history",
            "when is",
            "check my",
        )
        booking_action_phrases = (
            "book",
            "schedule",
            "reserve",
            "make an appointment",
            "change the appointment",
            "change my appointment",
        )
        greeting = re.sub(r"[^a-z ]", "", lowered).strip() in {
            "hi",
            "hello",
            "hey",
            "good morning",
            "good afternoon",
            "thanks",
            "thank you",
        }

        if confirmation != "unknown" and conversation_state == "awaiting_confirmation":
            intent: Intent = "booking_create"
        elif any(phrase in lowered for phrase in lookup_phrases):
            intent = "booking_lookup"
        elif any(phrase in lowered for phrase in booking_action_phrases):
            intent = "booking_create"
        elif conversation_state == "collecting" and (
            booking_date is not None or booking_time is not None
        ):
            intent = "booking_create"
        elif greeting:
            intent = "small_talk"
        elif recommendation is not None and recommendation.score > 0:
            intent = "qa_recommendation"
        else:
            intent = "small_talk"

        if recommendation is not None and intent in {"qa_recommendation", "booking_create"}:
            doctor_id = doctor_id or recommendation.doctor.doctor_id
            treatment_id = treatment_id or recommendation.treatment.treatment_id

        return RouteDecision(
            intent=intent,
            confidence=0.9 if intent != "small_talk" else 0.7,
            doctor_id=doctor_id,
            treatment_id=treatment_id,
            booking_date=booking_date,
            booking_time=booking_time,
            notes=None,
            confirmation=confirmation,
        )


def _strip_code_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped

