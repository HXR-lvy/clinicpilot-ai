# ClinicPilot AI

ClinicPilot AI is a functional take-home MVP for clinic information, grounded treatment recommendations, patient booking lookup, multi-turn appointment collection, and database-backed booking creation.

The demo uses one predefined patient, `P001` (John Doe), as allowed by the assignment. React renders the chat and a live view of SQLite records; FastAPI owns intent routing, validation, the booking state machine, executable domain tools, and persistence.

## Stack

- FastAPI, Pydantic, SQLAlchemy
- SQLite with CSV seeding
- Local TF-IDF retrieval plus exact relational lookups
- DeepSeek OpenAI-compatible Chat Completions API
- React 19, TypeScript, Vite
- Pytest and the TypeScript production build for verification

No Docker or external vector database is required.

## Prerequisites

- Python 3.10 or newer
- Node.js 20 or newer and npm
- PowerShell examples below target Windows; equivalent commands work on macOS/Linux
- A DeepSeek API Key is only required for live-model mode

## 1. Configure the environment

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks activation, invoke the virtual-environment Python directly from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

The default `.env.example` runs `LLM_MODE=mock`, so the complete workflow works without a model key.

## 2. Initialize the database

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m app.seed --reset
```

This recreates the application tables and idempotently imports:

| Dataset | Expected rows |
|---|---:|
| `clinics.csv` | 2 |
| `doctors.csv` | 4 |
| `treatments.csv` | 5 |
| `patients.csv` | 3 |
| `patient_bookings.csv` | 4 |
| `patient_treatment_history.csv` | 2 |

The API also creates missing tables and seeds missing records on startup. `--reset` is only needed when you want to discard local chat and booking changes.

## 3. Run the backend

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

OpenAPI is available at `http://localhost:8000/docs`; health is at `http://localhost:8000/api/health`.

## 4. Run the frontend

In a second terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

The frontend reads `VITE_API_BASE_URL` when supplied; otherwise it calls `http://localhost:8000` directly. To use another backend URL, create `frontend/.env.local`:

```text
VITE_API_BASE_URL=http://localhost:8000
```

## Live DeepSeek mode

Set these values in the root `.env`, then restart FastAPI:

```text
LLM_MODE=live
DEEPSEEK_API_KEY=your-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
LLM_TIMEOUT_SECONDS=30
LLM_FALLBACK_TO_MOCK=true
```

Live mode uses non-thinking Chat Completions with JSON routing, server-side Pydantic validation, and `thinking.type=disabled`. `LLM_FALLBACK_TO_MOCK=true` keeps the mandatory booking path demonstrable if the external service is temporarily unavailable; the response and database message metadata identify degraded turns. Set it to `false` if failures must be explicit. See the [DeepSeek Tool Calls guide](https://api-docs.deepseek.com/guides/tool_calls/) and [Chat Completion reference](https://api-docs.deepseek.com/api/create-chat-completion/).

## Demo path

Use a fixed `DEMO_TODAY=2026-10-26` in `.env` if you want relative date phrases to behave identically to the seeded scenario.

1. Ask `What are Metro Care's opening hours?` and inspect the clinic source ID.
2. Ask `I have a skin rash. Which doctor do you recommend?` and inspect the doctor/treatment evidence.
3. Ask `When is my next appointment?`; the answer should reference `B1001` on `2026-11-05`.
4. Ask `Book a general health checkup with Dr. Sarah Jenkins.` The assistant should ask for a preferred date and time.
5. Reply `November 20, 2026 at 10:00 AM.` The assistant should summarize the draft and request confirmation.
6. Reply `yes`. The booking list refetches `GET /api/bookings` and displays the new record.
7. Restart FastAPI and refresh the page to demonstrate that the record still exists in SQLite.

The profile question `Can I book an appointment for my peanut allergy?` uses the known allergy context and asks for any missing appointment slot. The assistant does not diagnose or prescribe.

## API summary

```http
POST /api/chat
GET  /api/bookings?patient_id=P001
POST /api/bookings
GET  /api/health
```

Example booking:

```json
{
  "patient_id": "P001",
  "doctor_id": "D103",
  "treatment_id": "T003",
  "booking_date": "2026-12-02",
  "booking_time": "14:00:00",
  "notes": "Skin concern."
}
```

Unknown entities return `404`; invalid patient/doctor/treatment relationships and payload validation errors return `422`. Reusing the same `draft_id` returns the already-created booking rather than duplicating it.

## Verification

Backend tests:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest
```

Frontend production build:

```powershell
Set-Location frontend
npm run build
```

The backend suite covers seed data, next-booking lookup, the full multi-turn booking flow, restart persistence, incompatible doctor/treatment pairs, idempotent creation, emergency handling, retrieval, dates, and confirmation phrases.

## Project layout

```text
backend/app/       FastAPI API, models, seed, RAG, LLM adapter, workflow tools
backend/tests/     deterministic API and workflow tests
frontend/src/      React chat and live bookings workbench
mock-data/         provided CSV datasets used for reproducible seeding
TECH_DOC.md        architecture and design rationale
.env.example       safe local defaults
```

## Scope and limitations

- Authentication and multi-patient access control are intentionally out of scope for the fixed `P001` demo.
- Schedule conflicts, payments, cancellations, and real EHR integration are not implemented, as allowed by the assignment.
- Times are stored as clinic-local wall-clock values with no timezone conversion.
- The assistant is a clinic information and booking tool, not a diagnostic or prescribing system.

