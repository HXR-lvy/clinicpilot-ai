

---

# 🏥 ClinicPilot AI —— Take-Home Technical Assignment

## 📌 Context & Overview

**ClinicPilot AI** is an intelligent assistant prototype designed to streamline medical clinic operations. The system guides patients through a complete interactive journey: **inquiring about clinic/doctor details**, **receiving treatment recommendations based on their needs**, **checking existing bookings**, and **completing automated appointment bookings via AI natural conversation**.

As an **AI Software Engineer** candidate, your task is to build a functional end-to-end MVP. We value **clean architecture, intent routing logic, AI orchestration/tool-calling quality (API or MCP), and database persistence** over complex UI styling.

**If you find any requirement does not make sence, feel free to modfiy or change it. And also feel free to make any assumption you need.

##You can use any AI coding tools to complete the tasks

---

## 🛠️ Tech Stack & Flexibility

You are free to choose the libraries and frameworks that best fit your architectural vision:

* **AI & RAG Engine**: Python 3.10+ (Framework open: **LangGraph**, **LangChain**, **LlamaIndex**, **CrewAI**, or custom Agent architecture).
* **Tool Calling / Protocol**: Standard **REST API Function Calling** OR **MCP (Model Context Protocol)**.
* **Backend API**: **NestJS (Node.js)** OR **FastAPI (Python)**.
* **Frontend UI**: **React** (Vite / Next.js / CRA) — *Keep it simple and functional*.
* **Database**: **SQLite**, **PostgreSQL**, or **MySQL** (Local database to store and read booking records).
* **Observability & DevOps (Optional)**: Langfuse, OpenTelemetry, Docker, Kubernetes.

---

## 🚀 Core Tasks & Requirements

### 🔴 Core Task 1: AI Service & Agentic Workflow (Required)

Build an AI core that handles multi-turn conversation, intent classification, and automated booking:

1. **Clinical Knowledge & Treatment Recommendation (RAG)**:
* Index `clinics.csv`, `doctors.csv`, and `treatments.csv`.
* When patients describe their needs/symptoms, the AI should provide accurate clinic information and recommend appropriate treatment services and doctors.


2. **Intent Analysis & Conversational Booking (Agent Tool-Calling)**:
* The AI must dynamically analyze user intent during the conversation:
* **Q&A / Recommendation Intent** $\rightarrow$ RAG Retrieval & Advice generation.
* **Existing Booking Queries** $\rightarrow$ Query existing appointment history (`patient_bookings.csv`) for the current patient **via standard REST API calls or MCP (Model Context Protocol) tool integration**.
* **New Booking Intent** $\rightarrow$ Identify missing booking parameters (Doctor, Treatment, Preferred Date & Time).


* **Parameter Extraction & Automated Booking Execution**: If any booking parameter is missing, the AI should naturally prompt the user. Once all parameters are collected, the Chatbot Agent **must trigger a REST API endpoint or execute an MCP tool to successfully save the new booking into the database**.
* *(Note: You do NOT need to handle schedule conflict/overbooking logic. Assume all requested timeslots are available).*


3. **Single-Patient Context Assumption (Simplified Demo Flow)**:
* **For Demo Simplicity**: Assume the user interacting with the Chatbot is **always the same predefined patient** (e.g., Patient ID: `P001`, John Doe).
* Pre-load or inject this patient's profile, medical/allergy history, and existing booking records into the conversation context so the AI can answer personalized questions (e.g., *"When is my next appointment?"* or *"Can I book an appointment for my peanut allergy?"*) without requiring authentication or manual ID input.



---

### 🔴 Core Task 2: Backend API Service & Database Persistence (Required)

Build a Backend API (**NestJS** or **FastAPI**) connected to a local relational database:

1. **Database Schema**:
* Seed your database using the provided CSV files.
* Ensure a `patient_bookings` table is present to persist new bookings generated during Chatbot interactions.


2. **Core Endpoints**:
* `POST /api/chat`: Accepts user messages + optional `patient_id`. Handles intent analysis, forwards requests to the AI engine, and returns responses.
* `POST /api/bookings` (or MCP Tool): Endpoint called by the AI Agent to persist new appointment bookings into the database.
* `GET /api/bookings`: Retrieves the latest list of patient bookings from the database to reflect new AI-created appointments in real time on the UI.


3. **Engineering Standards**:
* Modular architecture with clear separation of concerns.
* Proper request validation, ORM/SQL query execution, and error-handling middleware.



---

### 🔴 Core Task 3: React Frontend Workbench (Required - Simple Demo UI)

Build a lightweight, functional React interface to demonstrate the system end-to-end.

> ⚠️ **Note**: Visual aesthetics and complex CSS styling are **NOT** evaluated here. A clean, basic UI (e.g., using Tailwind, Ant Design, MUI, or plain CSS) that smooths out the live demo flow is all that is required.

1. **Features**:
* **Interactive Chat Panel**: Send messages, receive recommendations, check existing appointments, and converse naturally to complete a booking.
* **Live Bookings Display Panel**: A table or list view that updates (or offers a refresh button) to show newly created bookings stored in the database right after the Chatbot confirms the appointment.



---

### 🌟 Optional / Bonus Tasks (Nice to Have)

* **Speech Transcript Summarizer**: An endpoint or tool that takes raw doctor-patient conversation text and generates a structured medical JSON summary (`chief_complaint`, `diagnosis`, `medication`, `doctor_instructions`).
* **LLM Observability (e.g., Langfuse)**: Tracing LLM calls, latency, and token consumption.
* **Containerization & Deployment**: `docker-compose.yml` or Kubernetes deployment manifests (`/k8s`).

---

## 📊 Provided Datasets (Mock Data)

You will find 6 CSV files in the repository:

* `clinics.csv`: Operational hours, cancellation policies, and emergency guides.
* `doctors.csv`: Doctor specialties, fees, and bio data.
* `treatments.csv`: Available medical services and pre-treatment instructions.
* `patients.csv`: Patient demographics and allergy records.
* `patient_bookings.csv`: Initial appointment records.
* `patient_treatment_history.csv`: Past medical visit logs and doctor notes.

---

## 📬 Submission Rules & Timeline

1. **Timeline**:
* You have **24 hours** from receiving this assignment email to submit your work.
* If you need an extension due to prior commitments, please reply to the email and let us know in advance.


2. **Code Repository**:
* Push your complete source code to a **Public GitHub Repository** and reply with the repository link.


3. **Technical Documentation (`TECH_DOC.md`)**:
* Provide a technical design document explaining your **architectural choices**, **intent recognition approach**, **AI Tool-Calling / MCP / State machine workflow**, and database schema design.


4. **Local Setup Guide (`README.md`)**:
* Step-by-step instructions on how to set up environment variables, initialize/seed the database, and run the backend and frontend locally.


5. **Interview Live Demo**:
* In the upcoming technical interview, you will start with a **Live Demo** of your project running locally on your machine.
* We will test the full flow: *asking questions $\rightarrow$ getting treatment recommendations $\rightarrow$ checking existing appointments $\rightarrow$ booking a new appointment via Chatbot Agent $\rightarrow$ verifying the database record in the UI*.



---

## 📦 Suggested Repository Structure

```text
├── ai-service/             # AI / RAG / Agentic Booking Workflow (Python)
├── backend/                # Backend API & Database Connection (NestJS or FastAPI)
├── frontend/               # React Frontend (Chatbot + Live Bookings View)
├── mock-data/              # Provided CSV datasets
├── TECH_DOC.md             # Architecture & Design Rationale (Required)
├── README.md               # Local Setup & Run Instructions (Required)
└── docker-compose.yml      # (Optional)

```