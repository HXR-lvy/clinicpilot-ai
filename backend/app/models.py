from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Clinic(Base):
    __tablename__ = "clinics"

    clinic_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    clinic_name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(64), nullable=False)
    operating_hours: Mapped[str] = mapped_column(Text, nullable=False)
    cancellation_policy: Mapped[str] = mapped_column(Text, nullable=False)
    emergency_instructions: Mapped[str] = mapped_column(Text, nullable=False)


class Doctor(Base):
    __tablename__ = "doctors"

    doctor_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.clinic_id"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    specialty: Mapped[str] = mapped_column(String(120), nullable=False)
    languages_spoken: Mapped[str] = mapped_column(String(255), nullable=False)
    consultation_fee_usd: Mapped[float] = mapped_column(nullable=False)
    bio: Mapped[str] = mapped_column(Text, nullable=False)


class Treatment(Base):
    __tablename__ = "treatments"

    treatment_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    treatment_name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    price_usd: Mapped[float] = mapped_column(nullable=False)
    pre_treatment_instructions: Mapped[str] = mapped_column(Text, nullable=False)


class DoctorTreatment(Base):
    __tablename__ = "doctor_treatments"

    doctor_id: Mapped[str] = mapped_column(
        ForeignKey("doctors.doctor_id"), primary_key=True
    )
    treatment_id: Mapped[str] = mapped_column(
        ForeignKey("treatments.treatment_id"), primary_key=True
    )


class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    dob: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str] = mapped_column(String(32), nullable=False)
    phone: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False)
    known_allergies: Mapped[str] = mapped_column(Text, nullable=False)
    emergency_contact: Mapped[str] = mapped_column(String(255), nullable=False)


class PatientBooking(Base):
    __tablename__ = "patient_bookings"

    booking_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id"), nullable=False)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.doctor_id"), nullable=False)
    treatment_id: Mapped[str] = mapped_column(
        ForeignKey("treatments.treatment_id"), nullable=False
    )
    booking_date: Mapped[date] = mapped_column(Date, nullable=False)
    booking_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_id: Mapped[str | None] = mapped_column(
        ForeignKey("booking_drafts.draft_id"), unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class PatientTreatmentHistory(Base):
    __tablename__ = "patient_treatment_history"

    record_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id"), nullable=False)
    doctor_id: Mapped[str] = mapped_column(ForeignKey("doctors.doctor_id"), nullable=False)
    visit_date: Mapped[date] = mapped_column(Date, nullable=False)
    chief_complaint: Mapped[str] = mapped_column(Text, nullable=False)
    diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    prescribed_medication: Mapped[str] = mapped_column(Text, nullable=False)
    doctor_notes: Mapped[str] = mapped_column(Text, nullable=False)


class Conversation(Base):
    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.patient_id"), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="idle", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Message(Base):
    __tablename__ = "messages"

    message_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.conversation_id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class BookingDraft(Base):
    __tablename__ = "booking_drafts"

    draft_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.conversation_id"), nullable=False, index=True
    )
    doctor_id: Mapped[str | None] = mapped_column(ForeignKey("doctors.doctor_id"), nullable=True)
    treatment_id: Mapped[str | None] = mapped_column(
        ForeignKey("treatments.treatment_id"), nullable=True
    )
    booking_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    booking_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="collecting", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

