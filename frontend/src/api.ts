import type { ChatResponse, HealthResponse, Booking } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep the status-based message when the body is not JSON.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function sendChat(
  message: string,
  conversationId: string | null,
): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      patient_id: "P001",
    }),
  });
  return parseResponse<ChatResponse>(response);
}

export async function getBookings(): Promise<Booking[]> {
  const response = await fetch(`${API_BASE}/api/bookings?patient_id=P001`);
  const result = await parseResponse<{ bookings: Booking[] }>(response);
  return result.bookings;
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE}/api/health`);
  return parseResponse<HealthResponse>(response);
}

