from __future__ import annotations

import json
import logging
import re
from datetime import date
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .llm import (
    DeepSeekClient,
    LLMUnavailableError,
    MockDecisionEngine,
    RouteDecision,
)
from .models import BookingDraft, Clinic, Doctor, DoctorTreatment, Treatment
from .repositories import (
    DomainNotFoundError,
    DomainValidationError,
    append_message,
    create_booking,
    doctor_supports_treatment,
    get_doctor,
    get_or_create_conversation,
    get_patient,
    get_treatment,
    list_bookings,
    next_upcoming_booking,
    patient_context,
    recent_messages,
)
from .retrieval import KnowledgeDocument, KnowledgeRetriever, RetrievalResult
from .schemas import (
    BookingDraftOut,
    BookingOut,
    ChatRequest,
    ChatResponse,
    SourceRef,
)
from .temporal import has_safety_red_flag


logger = logging.getLogger(__name__)


class AgentToolbox:
    """Validated domain tools exposed to the conversational orchestrator."""

    def __init__(self, session: Session, settings: Settings, patient_id: str):
        self.session = session
        self.settings = settings
        self.patient_id = patient_id
        self.calls: list[str] = []

    def search_clinic_knowledge(self, query: str) -> RetrievalResult:
        self.calls.append("search_clinic_knowledge")
        return KnowledgeRetriever(self.session).search(query)

    def get_patient_bookings(self) -> tuple[list[BookingOut], BookingOut | None]:
        self.calls.append("get_patient_bookings")
        today = self.settings.demo_today or date.today()
        bookings = list_bookings(self.session, self.patient_id)
        return bookings, next_upcoming_booking(self.session, self.patient_id, today)

    def get_active_draft(self, conversation_id: str) -> BookingDraft | None:
        return self.session.scalar(
            select(BookingDraft)
            .where(
                BookingDraft.conversation_id == conversation_id,
                BookingDraft.status.in_(("collecting", "awaiting_confirmation")),
            )
            .order_by(BookingDraft.updated_at.desc())
        )

    def upsert_booking_draft(
        self,
        conversation_id: str,
        draft: BookingDraft | None,
        decision: RouteDecision,
    ) -> BookingDraft:
        self.calls.append("upsert_booking_draft")
        if draft is None:
            draft = BookingDraft(
                draft_id=str(uuid4()),
                conversation_id=conversation_id,
                status="collecting",
            )
            self.session.add(draft)
            self.session.flush()

        if decision.doctor_id:
            previous_doctor = draft.doctor_id
            get_doctor(self.session, decision.doctor_id)
            draft.doctor_id = decision.doctor_id
            if previous_doctor != draft.doctor_id and draft.treatment_id:
                if not doctor_supports_treatment(
                    self.session, draft.doctor_id, draft.treatment_id
                ):
                    draft.treatment_id = None

        if decision.treatment_id:
            previous_treatment = draft.treatment_id
            get_treatment(self.session, decision.treatment_id)
            draft.treatment_id = decision.treatment_id
            if previous_treatment != draft.treatment_id and draft.doctor_id:
                if not doctor_supports_treatment(
                    self.session, draft.doctor_id, draft.treatment_id
                ):
                    draft.doctor_id = None

        if decision.booking_date is not None:
            draft.booking_date = decision.booking_date
        if decision.booking_time is not None:
            draft.booking_time = decision.booking_time
        if decision.notes:
            draft.notes = decision.notes

        if draft.doctor_id and draft.treatment_id:
            if not doctor_supports_treatment(
                self.session, draft.doctor_id, draft.treatment_id
            ):
                raise DomainValidationError(
                    "The selected doctor does not offer the selected treatment"
                )

        draft.status = "collecting"
        self.session.commit()
        self.session.refresh(draft)
        return draft

    def create_booking_from_draft(self, draft: BookingDraft) -> BookingOut:
        self.calls.append("create_booking")
        if not all(
            (draft.doctor_id, draft.treatment_id, draft.booking_date, draft.booking_time)
        ):
            raise DomainValidationError("The booking draft is incomplete")
        booking, _ = create_booking(
            self.session,
            patient_id=self.patient_id,
            doctor_id=draft.doctor_id,
            treatment_id=draft.treatment_id,
            booking_date=draft.booking_date,
            booking_time=draft.booking_time,
            notes=draft.notes,
            draft_id=draft.draft_id,
        )
        draft.status = "completed"
        self.session.commit()
        return booking

    def cancel_draft(self, draft: BookingDraft) -> None:
        self.calls.append("cancel_booking_draft")
        draft.status = "cancelled"
        self.session.commit()


class ChatService:
    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings

    def handle(self, request: ChatRequest) -> ChatResponse:
        patient = get_patient(self.session, request.patient_id)
        conversation = get_or_create_conversation(
            self.session, request.conversation_id, request.patient_id
        )
        toolbox = AgentToolbox(self.session, self.settings, request.patient_id)
        active_draft = toolbox.get_active_draft(conversation.conversation_id)
        context = patient_context(self.session, request.patient_id)
        catalog = self._catalog()
        history = [
            {"role": message.role, "content": message.content}
            for message in recent_messages(self.session, conversation.conversation_id)
        ]
        today = self.settings.demo_today or date.today()

        decision, llm_mode = self._route(
            message=request.message,
            today=today,
            context=context,
            catalog=catalog,
            conversation_state=conversation.state,
            draft=active_draft,
            history=history,
        )
        append_message(
            self.session,
            conversation.conversation_id,
            "user",
            request.message,
            intent=decision.intent,
        )

        response = self._dispatch(
            request=request,
            decision=decision,
            toolbox=toolbox,
            conversation=conversation,
            active_draft=active_draft,
            context=context,
            llm_mode=llm_mode,
        )
        append_message(
            self.session,
            conversation.conversation_id,
            "assistant",
            response.message,
            intent=response.intent,
            tool_name=",".join(toolbox.calls) or None,
            metadata_json=json.dumps(
                {
                    "state": response.state,
                    "source_ids": [source.id for source in response.sources],
                    "llm_mode": response.llm_mode,
                }
            ),
        )
        logger.info(
            "chat_turn conversation_id=%s intent=%s state=%s tools=%s mode=%s",
            conversation.conversation_id,
            response.intent,
            response.state,
            toolbox.calls,
            response.llm_mode,
        )
        return response

    def _route(
        self,
        *,
        message: str,
        today: date,
        context: dict,
        catalog: dict,
        conversation_state: str,
        draft: BookingDraft | None,
        history: list[dict[str, str]],
    ) -> tuple[RouteDecision, str]:
        mock_engine = MockDecisionEngine(self.session)
        if self.settings.llm_mode == "mock":
            return (
                mock_engine.route(
                    message=message,
                    today=today,
                    catalog=catalog,
                    conversation_state=conversation_state,
                ),
                "mock",
            )

        try:
            live_client = DeepSeekClient(self.settings)
            draft_payload = (
                BookingDraftOut.model_validate(draft).model_dump(mode="json")
                if draft
                else None
            )
            return (
                live_client.route(
                    message=message,
                    today=today,
                    patient_context=context,
                    catalog=catalog,
                    conversation_state=conversation_state,
                    draft=draft_payload,
                    history=history,
                ),
                "live",
            )
        except LLMUnavailableError as exc:
            if not self.settings.llm_fallback_to_mock:
                raise
            logger.warning("DeepSeek routing degraded to mock: %s", exc)
            return (
                mock_engine.route(
                    message=message,
                    today=today,
                    catalog=catalog,
                    conversation_state=conversation_state,
                ),
                "mock-fallback",
            )

    def _dispatch(
        self,
        *,
        request: ChatRequest,
        decision: RouteDecision,
        toolbox: AgentToolbox,
        conversation,
        active_draft: BookingDraft | None,
        context: dict,
        llm_mode: str,
    ) -> ChatResponse:
        if has_safety_red_flag(request.message):
            retrieval = toolbox.search_clinic_knowledge("emergency instructions")
            message = self._emergency_message(retrieval)
            conversation.state = "idle"
            self.session.commit()
            return ChatResponse(
                conversation_id=conversation.conversation_id,
                message=message,
                intent="qa_recommendation",
                state="idle",
                sources=retrieval.sources,
                llm_mode=llm_mode,
            )

        if decision.intent == "booking_lookup":
            return self._booking_lookup(request, decision, toolbox, conversation, llm_mode)

        if decision.intent == "booking_create":
            return self._booking_flow(
                request,
                decision,
                toolbox,
                conversation,
                active_draft,
                context,
                llm_mode,
            )

        if decision.intent == "qa_recommendation":
            return self._knowledge_answer(
                request, decision, toolbox, conversation, context, llm_mode
            )

        conversation.state = "idle" if conversation.state == "idle" else conversation.state
        self.session.commit()
        message = (
            "Hello! I can help with clinic information, treatment recommendations, "
            "checking your appointments, or booking a new visit. What can I help with?"
        )
        return ChatResponse(
            conversation_id=conversation.conversation_id,
            message=message,
            intent="small_talk",
            state=conversation.state,
            llm_mode=llm_mode,
        )

    def _knowledge_answer(
        self,
        request: ChatRequest,
        decision: RouteDecision,
        toolbox: AgentToolbox,
        conversation,
        context: dict,
        llm_mode: str,
    ) -> ChatResponse:
        retrieval = toolbox.search_clinic_knowledge(request.message)
        answer_mode = llm_mode
        if llm_mode == "live":
            try:
                evidence = self._evidence_payload(retrieval)
                message = DeepSeekClient(self.settings).answer(
                    message=request.message,
                    patient_context=context,
                    evidence=evidence,
                )
            except LLMUnavailableError as exc:
                if not self.settings.llm_fallback_to_mock:
                    raise
                logger.warning("DeepSeek answer degraded to mock: %s", exc)
                message = self._mock_knowledge_answer(
                    request.message, retrieval, context
                )
                answer_mode = "mock-fallback"
        else:
            message = self._mock_knowledge_answer(request.message, retrieval, context)

        self.session.commit()
        return ChatResponse(
            conversation_id=conversation.conversation_id,
            message=message,
            intent="qa_recommendation",
            state=conversation.state,
            sources=retrieval.sources,
            llm_mode=answer_mode,
        )

    def _booking_lookup(
        self,
        request: ChatRequest,
        decision: RouteDecision,
        toolbox: AgentToolbox,
        conversation,
        llm_mode: str,
    ) -> ChatResponse:
        bookings, next_booking = toolbox.get_patient_bookings()
        conversation.state = "idle"
        if next_booking is None:
            message = "You do not have any upcoming confirmed appointments."
        else:
            message = (
                f"Your next appointment is {next_booking.booking_date.isoformat()} at "
                f"{next_booking.booking_time.strftime('%H:%M')} with "
                f"{next_booking.doctor_name} for {next_booking.treatment_name} "
                f"({next_booking.booking_id})."
            )
            earlier = [booking for booking in bookings if booking != next_booking]
            if earlier:
                message += " You also have other appointment records in the bookings panel."
        self.session.commit()
        sources = []
        if next_booking:
            sources = [
                SourceRef(type="doctor", id=next_booking.doctor_id, label=next_booking.doctor_name),
                SourceRef(
                    type="treatment",
                    id=next_booking.treatment_id,
                    label=next_booking.treatment_name,
                ),
            ]
        return ChatResponse(
            conversation_id=conversation.conversation_id,
            message=message,
            intent="booking_lookup",
            state="idle",
            sources=sources,
            llm_mode=llm_mode,
        )

    def _booking_flow(
        self,
        request: ChatRequest,
        decision: RouteDecision,
        toolbox: AgentToolbox,
        conversation,
        active_draft: BookingDraft | None,
        context: dict,
        llm_mode: str,
    ) -> ChatResponse:
        if (
            active_draft is not None
            and active_draft.status == "awaiting_confirmation"
            and decision.confirmation == "no"
        ):
            toolbox.cancel_draft(active_draft)
            conversation.state = "idle"
            self.session.commit()
            return ChatResponse(
                conversation_id=conversation.conversation_id,
                message="No problem. I have not created the appointment. What would you like to do instead?",
                intent="booking_create",
                state="idle",
                llm_mode=llm_mode,
            )

        draft = active_draft
        try:
            if decision.confirmation != "yes" or draft is None:
                draft = toolbox.upsert_booking_draft(
                    conversation.conversation_id, draft, decision
                )
            draft = self._fill_unambiguous_slots(draft)
        except (DomainNotFoundError, DomainValidationError) as exc:
            conversation.state = "collecting" if draft else conversation.state
            self.session.commit()
            return ChatResponse(
                conversation_id=conversation.conversation_id,
                message=f"I could not apply those booking details: {exc}. Please choose another valid option.",
                intent="booking_create",
                state=conversation.state,
                draft=BookingDraftOut.model_validate(draft) if draft else None,
                llm_mode=llm_mode,
            )

        missing_message = self._missing_slot_message(draft, context, request.message)
        if missing_message:
            draft.status = "collecting"
            conversation.state = "collecting"
            self.session.commit()
            return ChatResponse(
                conversation_id=conversation.conversation_id,
                message=missing_message,
                intent="booking_create",
                state="collecting",
                draft=BookingDraftOut.model_validate(draft),
                llm_mode=llm_mode,
            )

        conversation.state = "awaiting_confirmation"
        draft.status = "awaiting_confirmation"
        self.session.commit()

        if decision.confirmation == "yes" and active_draft is not None:
            conversation.state = "booking"
            self.session.commit()
            booking = toolbox.create_booking_from_draft(draft)
            conversation.state = "completed"
            self.session.commit()
            return ChatResponse(
                conversation_id=conversation.conversation_id,
                message=(
                    f"Your appointment is confirmed. Booking {booking.booking_id}: "
                    f"{booking.booking_date.isoformat()} at "
                    f"{booking.booking_time.strftime('%H:%M')} with {booking.doctor_name} "
                    f"for {booking.treatment_name}. It has been saved to the database."
                ),
                intent="booking_create",
                state="completed",
                sources=[
                    SourceRef(type="doctor", id=booking.doctor_id, label=booking.doctor_name),
                    SourceRef(
                        type="treatment",
                        id=booking.treatment_id,
                        label=booking.treatment_name,
                    ),
                ],
                draft=BookingDraftOut.model_validate(draft),
                booking=booking,
                llm_mode=llm_mode,
            )

        doctor = get_doctor(self.session, draft.doctor_id)
        treatment = get_treatment(self.session, draft.treatment_id)
        return ChatResponse(
            conversation_id=conversation.conversation_id,
            message=(
                "Please confirm this appointment: "
                f"{draft.booking_date.isoformat()} at "
                f"{draft.booking_time.strftime('%H:%M')} with {doctor.full_name} "
                f"for {treatment.treatment_name}. Reply yes to book it."
            ),
            intent="booking_create",
            state="awaiting_confirmation",
            sources=[
                SourceRef(type="doctor", id=doctor.doctor_id, label=doctor.full_name),
                SourceRef(
                    type="treatment",
                    id=treatment.treatment_id,
                    label=treatment.treatment_name,
                ),
            ],
            draft=BookingDraftOut.model_validate(draft),
            requires_confirmation=True,
            llm_mode=llm_mode,
        )

    def _fill_unambiguous_slots(self, draft: BookingDraft) -> BookingDraft:
        if draft.doctor_id and not draft.treatment_id:
            treatment_ids = self.session.scalars(
                select(DoctorTreatment.treatment_id).where(
                    DoctorTreatment.doctor_id == draft.doctor_id
                )
            ).all()
            if len(treatment_ids) == 1:
                draft.treatment_id = treatment_ids[0]
                self.session.commit()
        elif draft.treatment_id and not draft.doctor_id:
            doctor_ids = self.session.scalars(
                select(DoctorTreatment.doctor_id).where(
                    DoctorTreatment.treatment_id == draft.treatment_id
                )
            ).all()
            if len(doctor_ids) == 1:
                draft.doctor_id = doctor_ids[0]
                self.session.commit()
        return draft

    def _missing_slot_message(
        self, draft: BookingDraft, context: dict, user_message: str
    ) -> str | None:
        allergy_context = ""
        if "allerg" in user_message.lower():
            allergy_context = (
                "I have your known allergies on file: "
                f"{context['patient']['known_allergies']}. I can book a clinic visit to discuss "
                "the concern, but I cannot provide a diagnosis. "
            )

        if not draft.doctor_id and not draft.treatment_id:
            return allergy_context + (
                "I can help book that. Which doctor or treatment would you like? "
                "You can also describe your concern and I can suggest an available option."
            )

        if not draft.doctor_id:
            treatment = get_treatment(self.session, draft.treatment_id)
            doctors = self.session.scalars(
                select(Doctor)
                .join(DoctorTreatment, Doctor.doctor_id == DoctorTreatment.doctor_id)
                .where(DoctorTreatment.treatment_id == treatment.treatment_id)
            ).all()
            options = ", ".join(doctor.full_name for doctor in doctors)
            return allergy_context + f"For {treatment.treatment_name}, the available doctors are {options}. Which doctor would you prefer?"

        if not draft.treatment_id:
            doctor = get_doctor(self.session, draft.doctor_id)
            treatments = self.session.scalars(
                select(Treatment)
                .join(
                    DoctorTreatment,
                    Treatment.treatment_id == DoctorTreatment.treatment_id,
                )
                .where(DoctorTreatment.doctor_id == doctor.doctor_id)
            ).all()
            options = ", ".join(treatment.treatment_name for treatment in treatments)
            return allergy_context + (
                f"{doctor.full_name} offers {options}. Which treatment do you need?"
            )

        if draft.booking_date is None and draft.booking_time is None:
            return allergy_context + "What date and time would you prefer for the appointment?"
        if draft.booking_date is None:
            return allergy_context + "What date would you prefer for the appointment?"
        if draft.booking_time is None:
            return allergy_context + "What time would you prefer for the appointment?"
        return None

    def _mock_knowledge_answer(
        self, query: str, retrieval: RetrievalResult, context: dict
    ) -> str:
        lowered = query.lower()
        query_words = set(re.findall(r"[a-z0-9]+", lowered))
        if any(term in lowered for term in ("hour", "open", "close", "schedule")):
            clinics = [
                document.payload
                for document in retrieval.documents
                if document.source_type == "clinic"
            ]
            if clinics:
                clinic = max(
                    clinics,
                    key=lambda item: len(
                        query_words & set(re.findall(r"[a-z0-9]+", item.clinic_name.lower()))
                    ),
                )
                return (
                    f"{clinic.clinic_name} is located at {clinic.address}. "
                    f"Its operating hours are: {clinic.operating_hours}. "
                    f"You can call {clinic.phone}."
                )

        if any(term in lowered for term in ("cancel", "cancellation", "no-show")):
            clinics = [
                document.payload
                for document in retrieval.documents
                if document.source_type == "clinic"
            ]
            if clinics:
                clinic = max(
                    clinics,
                    key=lambda item: len(
                        query_words & set(re.findall(r"[a-z0-9]+", item.clinic_name.lower()))
                    ),
                )
                return (
                    f"{clinic.clinic_name}'s cancellation policy: "
                    f"{clinic.cancellation_policy}"
                )

        matching_doctor = next(
            (
                document.payload
                for document in retrieval.documents
                if document.source_type == "doctor"
                and document.payload.full_name.lower() in lowered
            ),
            None,
        )
        if matching_doctor is not None:
            return (
                f"{matching_doctor.full_name} specializes in {matching_doctor.specialty}. "
                f"Languages: {matching_doctor.languages_spoken}. Consultation fee: "
                f"${matching_doctor.consultation_fee_usd:.2f}. {matching_doctor.bio}"
            )

        recommendation = retrieval.recommendation
        if recommendation is not None and recommendation.score > 0:
            doctor = recommendation.doctor
            treatment = recommendation.treatment
            allergies = context["patient"]["known_allergies"]
            return (
                f"Based on the available services, I recommend {doctor.full_name} "
                f"({doctor.specialty}) for {treatment.treatment_name}. Consultation fee: "
                f"${doctor.consultation_fee_usd:.2f}; treatment price: ${treatment.price_usd:.2f}; "
                f"duration: {treatment.duration_minutes} minutes. "
                f"Preparation: {treatment.pre_treatment_instructions} "
                f"Your profile lists these known allergies: {allergies}. "
                "This is a service recommendation, not a medical diagnosis."
            )

        if retrieval.documents:
            document = retrieval.documents[0]
            return (
                f"I found information for {document.label}: {document.text}. "
                "Please tell me which detail you need and I can narrow it down."
            )

        return (
            "I could not find that in the available clinic data. I can help with these clinics, "
            "doctors, treatments, policies, or appointment booking instead."
        )

    def _emergency_message(self, retrieval: RetrievalResult) -> str:
        clinics = [
            document.payload
            for document in retrieval.documents
            if document.source_type == "clinic"
        ]
        clinic = clinics[0] if clinics else self.session.scalar(select(Clinic))
        guidance = (
            clinic.emergency_instructions
            if clinic
            else "For a medical emergency, call your local emergency number immediately."
        )
        return f"This may be a medical emergency. {guidance}"

    def _evidence_payload(self, retrieval: RetrievalResult) -> list[dict]:
        return [
            {
                "source_type": document.source_type,
                "source_id": document.source_id,
                "label": document.label,
                "text": document.text,
            }
            for document in retrieval.documents
        ]

    def _catalog(self) -> dict:
        doctors = self.session.scalars(select(Doctor)).all()
        treatments = self.session.scalars(select(Treatment)).all()
        clinics = self.session.scalars(select(Clinic)).all()
        return {
            "clinics": [
                {
                    "clinic_id": clinic.clinic_id,
                    "clinic_name": clinic.clinic_name,
                    "operating_hours": clinic.operating_hours,
                }
                for clinic in clinics
            ],
            "doctors": [
                {
                    "doctor_id": doctor.doctor_id,
                    "clinic_id": doctor.clinic_id,
                    "full_name": doctor.full_name,
                    "specialty": doctor.specialty,
                }
                for doctor in doctors
            ],
            "treatments": [
                {
                    "treatment_id": treatment.treatment_id,
                    "treatment_name": treatment.treatment_name,
                    "category": treatment.category,
                }
                for treatment in treatments
            ],
        }

