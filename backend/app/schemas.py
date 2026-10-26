from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Intent = Literal[
    "qa_recommendation",
    "booking_lookup",
    "booking_create",
    "small_talk",
]
ConversationState = Literal[
    "idle",
    "collecting",
    "awaiting_confirmation",
    "booking",
    "completed",
]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    patient_id: str = "P001"

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message cannot be blank")
        return value


class SourceRef(BaseModel):
    type: Literal["clinic", "doctor", "treatment"]
    id: str
    label: str


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    booking_id: str
    patient_id: str
    doctor_id: str
    doctor_name: str
    treatment_id: str
    treatment_name: str
    booking_date: date
    booking_time: time
    status: str
    notes: str | None = None
    created_at: datetime | None = None


class BookingDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    draft_id: str
    conversation_id: str
    doctor_id: str | None = None
    treatment_id: str | None = None
    booking_date: date | None = None
    booking_time: time | None = None
    notes: str | None = None
    status: str


class BookingCreateRequest(BaseModel):
    patient_id: str = "P001"
    doctor_id: str
    treatment_id: str
    booking_date: date
    booking_time: time
    notes: str | None = Field(default=None, max_length=1000)
    draft_id: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    intent: Intent
    state: ConversationState
    sources: list[SourceRef] = Field(default_factory=list)
    draft: BookingDraftOut | None = None
    booking: BookingOut | None = None
    requires_confirmation: bool = False
    llm_mode: str = "mock"


class BookingListResponse(BaseModel):
    bookings: list[BookingOut]


class HealthResponse(BaseModel):
    status: str
    database: str
    llm_mode: str


class TranscriptSummaryRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=20_000)

    @field_validator("transcript")
    @classmethod
    def strip_transcript(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("transcript cannot be blank")
        return value


class TranscriptSummaryResponse(BaseModel):
    chief_complaint: str = ""
    diagnosis: str = ""
    medication: str = ""
    doctor_instructions: str = ""

