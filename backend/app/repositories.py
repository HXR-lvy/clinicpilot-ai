from __future__ import annotations

from datetime import date, datetime, time
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Conversation,
    Doctor,
    DoctorTreatment,
    Message,
    Patient,
    PatientBooking,
    PatientTreatmentHistory,
    Treatment,
)
from .schemas import BookingOut


class DomainNotFoundError(Exception):
    pass


class DomainValidationError(Exception):
    pass


def _booking_to_schema(
    booking: PatientBooking, doctor: Doctor, treatment: Treatment
) -> BookingOut:
    return BookingOut(
        booking_id=booking.booking_id,
        patient_id=booking.patient_id,
        doctor_id=booking.doctor_id,
        doctor_name=doctor.full_name,
        treatment_id=booking.treatment_id,
        treatment_name=treatment.treatment_name,
        booking_date=booking.booking_date,
        booking_time=booking.booking_time,
        status=booking.status,
        notes=booking.notes,
        created_at=booking.created_at,
    )


def get_patient(session: Session, patient_id: str) -> Patient:
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise DomainNotFoundError(f"Patient {patient_id} was not found")
    return patient


def get_doctor(session: Session, doctor_id: str) -> Doctor:
    doctor = session.get(Doctor, doctor_id)
    if doctor is None:
        raise DomainNotFoundError(f"Doctor {doctor_id} was not found")
    return doctor


def get_treatment(session: Session, treatment_id: str) -> Treatment:
    treatment = session.get(Treatment, treatment_id)
    if treatment is None:
        raise DomainNotFoundError(f"Treatment {treatment_id} was not found")
    return treatment


def doctor_supports_treatment(session: Session, doctor_id: str, treatment_id: str) -> bool:
    return (
        session.get(DoctorTreatment, (doctor_id, treatment_id)) is not None
    )


def list_bookings(session: Session, patient_id: str) -> list[BookingOut]:
    get_patient(session, patient_id)
    rows = session.execute(
        select(PatientBooking, Doctor, Treatment)
        .join(Doctor, PatientBooking.doctor_id == Doctor.doctor_id)
        .join(Treatment, PatientBooking.treatment_id == Treatment.treatment_id)
        .where(PatientBooking.patient_id == patient_id)
        .order_by(PatientBooking.booking_date, PatientBooking.booking_time)
    ).all()
    return [_booking_to_schema(*row) for row in rows]


def get_booking(session: Session, booking_id: str) -> BookingOut:
    row = session.execute(
        select(PatientBooking, Doctor, Treatment)
        .join(Doctor, PatientBooking.doctor_id == Doctor.doctor_id)
        .join(Treatment, PatientBooking.treatment_id == Treatment.treatment_id)
        .where(PatientBooking.booking_id == booking_id)
    ).one_or_none()
    if row is None:
        raise DomainNotFoundError(f"Booking {booking_id} was not found")
    return _booking_to_schema(*row)


def next_upcoming_booking(
    session: Session, patient_id: str, today: date
) -> BookingOut | None:
    bookings = list_bookings(session, patient_id)
    for booking in bookings:
        if booking.status == "Confirmed" and booking.booking_date >= today:
            return booking
    return None


def create_booking(
    session: Session,
    *,
    patient_id: str,
    doctor_id: str,
    treatment_id: str,
    booking_date: date,
    booking_time: time,
    notes: str | None = None,
    draft_id: str | None = None,
) -> tuple[BookingOut, bool]:
    if draft_id:
        existing = session.scalar(
            select(PatientBooking).where(PatientBooking.draft_id == draft_id)
        )
        if existing is not None:
            return get_booking(session, existing.booking_id), False

    get_patient(session, patient_id)
    get_doctor(session, doctor_id)
    get_treatment(session, treatment_id)
    if not doctor_supports_treatment(session, doctor_id, treatment_id):
        raise DomainValidationError(
            f"Doctor {doctor_id} does not support treatment {treatment_id}"
        )

    booking_ids = session.scalars(select(PatientBooking.booking_id)).all()
    suffixes = [
        int(booking_id[1:])
        for booking_id in booking_ids
        if booking_id.startswith("B") and booking_id[1:].isdigit()
    ]
    booking_id = f"B{max(suffixes, default=1000) + 1}"
    booking = PatientBooking(
        booking_id=booking_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        treatment_id=treatment_id,
        booking_date=booking_date,
        booking_time=booking_time,
        status="Confirmed",
        notes=notes or "Booked via ClinicPilot AI.",
        draft_id=draft_id,
    )
    session.add(booking)
    session.commit()
    session.refresh(booking)
    return get_booking(session, booking.booking_id), True


def patient_context(session: Session, patient_id: str) -> dict:
    patient = get_patient(session, patient_id)
    history = session.scalars(
        select(PatientTreatmentHistory)
        .where(PatientTreatmentHistory.patient_id == patient_id)
        .order_by(PatientTreatmentHistory.visit_date.desc())
    ).all()
    bookings = list_bookings(session, patient_id)
    return {
        "patient": {
            "patient_id": patient.patient_id,
            "name": f"{patient.first_name} {patient.last_name}",
            "date_of_birth": patient.dob.isoformat(),
            "known_allergies": patient.known_allergies,
            "emergency_contact": patient.emergency_contact,
        },
        "bookings": [booking.model_dump(mode="json") for booking in bookings],
        "treatment_history": [
            {
                "visit_date": record.visit_date.isoformat(),
                "doctor_id": record.doctor_id,
                "chief_complaint": record.chief_complaint,
                "diagnosis": record.diagnosis,
                "prescribed_medication": record.prescribed_medication,
                "doctor_notes": record.doctor_notes,
            }
            for record in history
        ],
    }


def get_or_create_conversation(
    session: Session, conversation_id: str | None, patient_id: str
) -> Conversation:
    get_patient(session, patient_id)
    if conversation_id:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            raise DomainNotFoundError(f"Conversation {conversation_id} was not found")
        if conversation.patient_id != patient_id:
            raise DomainValidationError("Conversation belongs to a different patient")
        return conversation

    conversation = Conversation(
        conversation_id=str(uuid4()), patient_id=patient_id, state="idle"
    )
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def recent_messages(session: Session, conversation_id: str, limit: int = 12) -> list[Message]:
    rows = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.message_id.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


def append_message(
    session: Session,
    conversation_id: str,
    role: str,
    content: str,
    *,
    intent: str | None = None,
    tool_name: str | None = None,
    metadata_json: str | None = None,
) -> None:
    session.add(
        Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            intent=intent,
            tool_name=tool_name,
            metadata_json=metadata_json,
        )
    )
    conversation = session.get(Conversation, conversation_id)
    if conversation is not None:
        conversation.updated_at = datetime.now().astimezone()
    session.commit()

