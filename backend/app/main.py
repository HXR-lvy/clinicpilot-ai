from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from .chat import ChatService
from .config import Settings
from .database import Base, build_engine, build_session_factory, session_dependency
from .repositories import (
    DomainNotFoundError,
    DomainValidationError,
    create_booking,
    list_bookings,
)
from .schemas import (
    BookingCreateRequest,
    BookingListResponse,
    BookingOut,
    ChatRequest,
    ChatResponse,
    HealthResponse,
)
from .seed import seed_database


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    engine = build_engine(app_settings)
    session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        Base.metadata.create_all(engine)
        with session_factory() as session:
            seed_database(session, app_settings.mock_data_dir)
        yield
        engine.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        version="1.0.0",
        description="Grounded clinic assistant, appointment workflow, and booking API.",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.session_factory = session_factory
    application.state.engine = engine
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_session():
        yield from session_dependency(session_factory)

    @application.exception_handler(DomainNotFoundError)
    async def handle_not_found(_, exc: DomainNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(DomainValidationError)
    async def handle_validation(_, exc: DomainValidationError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.get("/api/health", response_model=HealthResponse)
    def health(session: Session = Depends(get_session)):
        session.execute(text("SELECT 1"))
        return HealthResponse(
            status="ok",
            database="connected",
            llm_mode=app_settings.llm_mode,
        )

    @application.post("/api/chat", response_model=ChatResponse)
    def chat(request: ChatRequest, session: Session = Depends(get_session)):
        request.patient_id = request.patient_id or app_settings.default_patient_id
        return ChatService(session, app_settings).handle(request)

    @application.get("/api/bookings", response_model=BookingListResponse)
    def bookings(
        patient_id: str = Query(default=app_settings.default_patient_id, min_length=1),
        session: Session = Depends(get_session),
    ):
        return BookingListResponse(bookings=list_bookings(session, patient_id))

    @application.post(
        "/api/bookings",
        response_model=BookingOut,
        status_code=status.HTTP_201_CREATED,
    )
    def create_appointment(
        request: BookingCreateRequest, session: Session = Depends(get_session)
    ):
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

    return application


app = create_app()

