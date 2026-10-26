export type SourceRef = {
  type: "clinic" | "doctor" | "treatment";
  id: string;
  label: string;
};

export type BookingDraft = {
  draft_id: string;
  conversation_id: string;
  doctor_id: string | null;
  treatment_id: string | null;
  booking_date: string | null;
  booking_time: string | null;
  notes: string | null;
  status: string;
};

export type Booking = {
  booking_id: string;
  patient_id: string;
  doctor_id: string;
  doctor_name: string;
  treatment_id: string;
  treatment_name: string;
  booking_date: string;
  booking_time: string;
  status: string;
  notes: string | null;
  created_at: string | null;
};

export type ChatResponse = {
  conversation_id: string;
  message: string;
  intent: string;
  state: string;
  sources: SourceRef[];
  draft: BookingDraft | null;
  booking: Booking | null;
  requires_confirmation: boolean;
  llm_mode: string;
};

export type HealthResponse = {
  status: string;
  database: string;
  llm_mode: string;
};

export type UiMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  intent?: string;
  sources?: SourceRef[];
  mode?: string;
};

