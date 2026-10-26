from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .config import Settings
from .database import Base, build_engine, build_session_factory
from .models import (
    Clinic,
    Doctor,
    DoctorTreatment,
    Patient,
    PatientBooking,
    PatientTreatmentHistory,
    Treatment,
)


DOCTOR_TREATMENT_PAIRS = (
    ("D101", "T001"),
    ("D101", "T004"),
    ("D102", "T002"),
    ("D103", "T003"),
    ("D104", "T005"),
)


def _read_csv(data_dir: Path, filename: str) -> list[dict[str, str]]:
    path = data_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"Required dataset is missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def seed_database(session: Session, data_dir: Path) -> dict[str, int]:
    clinics = _read_csv(data_dir, "clinics.csv")
    doctors = _read_csv(data_dir, "doctors.csv")
    treatments = _read_csv(data_dir, "treatments.csv")
    patients = _read_csv(data_dir, "patients.csv")
    bookings = _read_csv(data_dir, "patient_bookings.csv")
    history = _read_csv(data_dir, "patient_treatment_history.csv")

    for row in clinics:
        session.merge(Clinic(**row))

    for row in doctors:
        session.merge(
            Doctor(
                doctor_id=row["doctor_id"],
                clinic_id=row["clinic_id"],
                full_name=row["full_name"],
                specialty=row["specialty"],
                languages_spoken=row["languages_spoken"],
                consultation_fee_usd=float(row["consultation_fee_usd"]),
                bio=row["bio"],
            )
        )

    for row in treatments:
        session.merge(
            Treatment(
                treatment_id=row["treatment_id"],
                treatment_name=row["treatment_name"],
                category=row["category"],
                duration_minutes=int(row["duration_minutes"]),
                price_usd=float(row["price_usd"]),
                pre_treatment_instructions=row["pre_treatment_instructions"],
            )
        )

    for doctor_id, treatment_id in DOCTOR_TREATMENT_PAIRS:
        session.merge(
            DoctorTreatment(doctor_id=doctor_id, treatment_id=treatment_id)
        )

    for row in patients:
        session.merge(
            Patient(
                patient_id=row["patient_id"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                dob=date.fromisoformat(row["dob"]),
                gender=row["gender"],
                phone=row["phone"],
                email=row["email"],
                known_allergies=row["known_allergies"],
                emergency_contact=row["emergency_contact"],
            )
        )

    for row in bookings:
        session.merge(
            PatientBooking(
                booking_id=row["booking_id"],
                patient_id=row["patient_id"],
                doctor_id=row["doctor_id"],
                treatment_id=row["treatment_id"],
                booking_date=date.fromisoformat(row["booking_date"]),
                booking_time=time.fromisoformat(row["booking_time"]),
                status=row["status"],
                notes=row["notes"] or None,
            )
        )

    for row in history:
        session.merge(
            PatientTreatmentHistory(
                record_id=row["record_id"],
                patient_id=row["patient_id"],
                doctor_id=row["doctor_id"],
                visit_date=date.fromisoformat(row["visit_date"]),
                chief_complaint=row["chief_complaint"],
                diagnosis=row["diagnosis"],
                prescribed_medication=row["prescribed_medication"],
                doctor_notes=row["doctor_notes"],
            )
        )

    session.commit()
    return {
        "clinics": session.scalar(select(func.count()).select_from(Clinic)) or 0,
        "doctors": session.scalar(select(func.count()).select_from(Doctor)) or 0,
        "treatments": session.scalar(select(func.count()).select_from(Treatment)) or 0,
        "patients": session.scalar(select(func.count()).select_from(Patient)) or 0,
        "patient_bookings": session.scalar(
            select(func.count()).select_from(PatientBooking)
        )
        or 0,
        "patient_treatment_history": session.scalar(
            select(func.count()).select_from(PatientTreatmentHistory)
        )
        or 0,
    }


def initialize_database(engine: Engine, data_dir: Path, reset: bool = False) -> dict[str, int]:
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine)
    with factory() as session:
        return seed_database(session, data_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create and seed the ClinicPilot database")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop all application tables before recreating and seeding them",
    )
    args = parser.parse_args()

    settings = Settings()
    counts = initialize_database(
        build_engine(settings), settings.mock_data_dir, reset=args.reset
    )
    print("Database ready:")
    for table, count in counts.items():
        print(f"  {table}: {count}")


if __name__ == "__main__":
    main()

