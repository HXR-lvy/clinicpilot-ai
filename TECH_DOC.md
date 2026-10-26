# ClinicPilot AI Technical Design

## 1. Goals and architecture

ClinicPilot AI is an end-to-end clinic assistant MVP focused on a reliable, demonstrable workflow rather than complex UI styling. The required path is: grounded question answering and recommendation, existing booking lookup, multi-turn collection of new booking slots, explicit confirmation, database creation, and a UI refresh sourced from the database.

```text
React workbench
  POST /api/chat
        |
        v
FastAPI ChatService and state machine
  |-- patient context loader
  |-- DeepSeek structured router or deterministic mock router
  |-- validated domain tools
        |-- search_clinic_knowledge
        |-- upsert_booking_draft
        |-- cancel_booking_draft
        |
        | REST agent tools
        |   GET  /api/bookings
        |   POST /api/bookings
        v
FastAPI public booking service
        |
        v
SQLite
  CSV-seeded clinic catalog and patient records
  conversations, messages, booking drafts, persisted bookings
        |
        v
React refetches GET /api/bookings after every assistant turn
```

The backend is one FastAPI service with separated concerns inside it. Splitting the AI process from the API would add network and lifecycle overhead without improving the assignment's core demonstration. The AI layer is replaceable independently through the router and answer interfaces.

## 2. Intent recognition and AI orchestration

The router returns a validated `RouteDecision` object:

```json
{
  "intent": "booking_create",
  "confidence": 0.9,
  "doctor_id": "D101",
  "treatment_id": "T001",
  "booking_date": "2026-11-20",
  "booking_time": "10:00:00",
  "notes": null,
  "confirmation": "unknown"
}
```

Supported intents are `qa_recommendation`, `booking_lookup`, `booking_create`, and `small_talk`. The prompt includes the current date, patient context, allowed catalog IDs, active draft, conversation state, and recent messages. Relative dates are resolved against clinic-local wall time. DeepSeek returns JSON with thinking disabled; Pydantic then validates every field and rejects unknown values or malformed dates.

The router does not directly write data. It chooses an intent and supplies candidate slots. `ChatService` controls which domain tool is legal for that state. This separation is intentional: medical and booking facts must remain server-validated even when the language model is uncertain or unavailable.

Mock mode uses the same intent and state interfaces for deterministic development and tests. In live mode, routing or answer failures can fall back to mock when `LLM_FALLBACK_TO_MOCK=true`; every affected response reports `mock-fallback` and the database message metadata records the mode.

## 3. Booking state machine and tools

```text
idle
  | new booking intent
  v
collecting  <---- missing doctor / treatment / date / time
  | all slots present
  v
awaiting_confirmation
  | explicit yes                 | no
  v                              v
booking -> completed            idle (draft cancelled)
```

The active draft is stored in `booking_drafts`, not only in process memory. Each field update is validated and committed. A changed doctor may cause an incompatible treatment to be cleared; a changed treatment may similarly clear an incompatible doctor. When one side uniquely determines the other through `doctor_treatments`, the server fills the missing side; otherwise it asks the patient to choose from the valid options.

| Tool | Responsibility | Safety rule |
|---|---|---|
| `search_clinic_knowledge` | TF-IDF retrieval plus exact payloads | Returns source IDs and never invents a service |
| `get_patient_bookings` | Calls `GET /api/bookings` over REST | Always queries persisted records, never relies on model memory |
| `upsert_booking_draft` | Persists partial booking slots | Validates IDs and doctor/treatment compatibility |
| `create_booking` | Calls `POST /api/bookings` over REST | Requires complete draft and explicit confirmation |
| `cancel_booking_draft` | Marks a rejected draft cancelled | Does not delete history |

The agent does not write booking rows through the ORM. Its `get_patient_bookings` and `create_booking` tools use an injected `httpx` client against `TOOL_API_BASE_URL`. The public API validates the request, resolves doctor/treatment compatibility, and commits the record. A `draft_id` is unique on the persisted booking, so a retry after an ambiguous network failure returns the existing booking rather than duplicating it.

The client maps `404` to a domain-not-found error, `422` to a validation error, and transport, malformed-response, or server failures to `BookingToolsUnavailableError`. The public `/api/chat` route reports that condition as `503`. When creation fails after confirmation, the conversation and draft remain in `awaiting_confirmation`, allowing a later retry.

## 4. Retrieval strategy

The data is deliberately small and structured, so the system uses a hybrid approach:

1. Normalize CSV rows into relational SQLite tables.
2. Build retrievable documents from clinic policies and hours, doctor specialties and biographies, and treatment instructions.
3. Add a narrow synonym expansion for common booking language such as `rash` to dermatology and `knee` to orthopedics.
4. Build per-term inverse document frequency, TF-IDF document vectors, and cosine similarity in local Python.
5. Return the top six documents with source refs plus a scored compatible doctor/treatment pair.
6. Feed exact relational payloads to the answer layer; price, IDs, and policy values are not reconstructed from model memory.

Doctor/treatment compatibility is explicit because the CSVs have no join column:

| Doctor | Supported treatment |
|---|---|
| `D101` | `T001`, `T004` |
| `D102` | `T002` |
| `D103` | `T003` |
| `D104` | `T005` |

## 5. Database design

The six source tables preserve the assignment CSV fields: `clinics`, `doctors`, `treatments`, `patients`, `patient_bookings`, and `patient_treatment_history`.

Supporting tables:

- `doctor_treatments`: validated many-to-many treatment capabilities.
- `conversations`: conversation ID, patient, state, timestamps.
- `messages`: user/assistant history, routed intent, tool trace, metadata JSON.
- `booking_drafts`: durable multi-turn slot collection and confirmation status.

`patient_bookings` extends the source fields with `draft_id` and `created_at`. `draft_id` is nullable for CSV seed records and unique for agent-created records. Seeding uses SQLAlchemy `merge` by primary key, so repeated initialization does not duplicate the 20 source rows.

Default patient context is loaded from `patients`, `patient_bookings`, and `patient_treatment_history`. John Doe's known allergies and both seeded appointments are included in every turn.

## 6. Public interfaces

### `POST /api/chat`

```json
{
  "message": "Book a general health checkup with Dr. Sarah Jenkins.",
  "conversation_id": null,
  "patient_id": "P001"
}
```

Response fields: `conversation_id`, `message`, `intent`, `state`, `sources`, `draft`, `booking`, `requires_confirmation`, and `llm_mode`.

### `POST /api/summarize`

Accepts a non-empty `transcript` of at most 20,000 characters and returns exactly:

```json
{
  "chief_complaint": "",
  "diagnosis": "",
  "medication": "",
  "doctor_instructions": ""
}
```

Live mode asks DeepSeek for JSON and validates the result. Mock mode uses deterministic label extraction. The endpoint is stateless and never persists the transcript or summary. It is an information structuring tool, not a diagnosis service.

### `POST /api/bookings`

Accepts patient, doctor, treatment, ISO date, time, optional notes, and optional draft ID. Returns `201` plus the persisted booking. Unknown entities map to `404`; invalid relationships and payloads map to `422`; repeated draft IDs return the original record.

### `GET /api/bookings?patient_id=P001`

Returns all patient appointments ordered by booking date and time, with joined doctor and treatment display names. The React app calls this endpoint after every assistant response rather than inserting a local-only row.

### `GET /api/health`

Checks database connectivity and exposes the configured model mode.

## 7. Failure handling and safety

- Empty or oversized chat messages fail Pydantic validation.
- Unknown patient, doctor, treatment, conversation, or booking IDs are rejected.
- Incompatible doctor/treatment pairs are rejected before insert.
- Missing booking slots produce focused follow-up prompts and preserve the draft.
- Only an explicit confirmation creates an appointment; a clear rejection cancels the draft.
- Network and JSON model failures can use deterministic fallback routing, preserving the core demo.
- REST booking unavailability returns `503`; a failed create leaves the confirmed draft intact for retry.
- Chest pain, breathing difficulty, severe bleeding, unconsciousness, and similar phrases return clinic emergency guidance and stop booking.
- The assistant is prompted as an information and booking system, not a diagnostic or prescribing system.

## 8. Observability

OpenTelemetry is opt-in through `OTEL_ENABLED`. FastAPI requests and SQLAlchemy operations are instrumented, and the REST booking client and DeepSeek adapter create explicit spans. Model spans record operation, model, duration, token usage, status, and fallback events. Prompts, user messages, and transcripts are not attached to spans.

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to export spans to an external OTLP-compatible collector. Without an endpoint, enabled traces use the console exporter; when tracing is disabled, OpenTelemetry remains a no-op. `TOOL_API_BASE_URL` defaults to `http://127.0.0.1:8000`, so Agent booking operations traverse the real REST endpoint.

## 9. Verification and future work

Pytest validates seed counts, next-appointment selection, the REST tool wire contract, error mapping, retry-safe drafts, multi-turn collection, persistence, incompatible pairs, idempotency, emergency behavior, retrieval, summaries, date parsing, confirmation parsing, and OpenTelemetry spans. The frontend production build validates TypeScript and bundling.

For production, the next steps would be authentication, authorization, per-clinic timezone handling, transactional schedule locking, deletion/cancellation policies, audit logging, encrypted PHI storage, rate limiting, and integration with a real EHR or MCP server. The current `P001` assumption is explicit and limited to the take-home demo.

